frappe.provide("reconciliation");

Object.assign(reconciliation, {
    get_unlinked_docs(selected_rows) {
        const unlinked_docs = new Set();
        selected_rows.forEach(row => {
            unlinked_docs.add(row.purchase_invoice_name);
            unlinked_docs.add(row.inward_supply_name);
        });

        return unlinked_docs;
    },

    async unlink_documents(frm, selected_rows) {
        if (frm.get_active_tab()?.df.fieldname != "invoice_tab") return;
        const _class = frm.reconciliation_tabs;
        const { invoice_tab } = _class.tabs;
        if (!selected_rows) selected_rows = invoice_tab.datatable.get_checked_items();

        if (!selected_rows.length)
            return frappe.show_alert({
                message: __("Please select rows to unlink"),
                indicator: "red",
            });

        // validate selected rows
        selected_rows.forEach(row => {
            if (row.match_status.includes("Missing"))
                frappe.throw(
                    __(
                        "You have selected rows where no match is available. Please remove them before unlinking."
                    )
                );
        });

        // unlink documents & update table
        const { message: r } = await frm._call("unlink_documents", {
            data: selected_rows,
        });

        const unlinked_docs = reconciliation.get_unlinked_docs(selected_rows);

        const new_data = _class.data.filter(
            row =>
                !(
                    unlinked_docs.has(row.purchase_invoice_name) ||
                    unlinked_docs.has(row.inward_supply_name)
                )
        );

        new_data.push(...r);
        _class.refresh(new_data);
        reconciliation.after_successful_action(invoice_tab);
    },

    async link_documents(
        frm,
        purchase_invoice_name,
        inward_supply_name,
        link_doctype,
        alert = true
    ) {
        if (frm.get_active_tab()?.df.fieldname != "invoice_tab") return;

        // link documents & update data.
        const { message: r } = await frm._call("link_documents", {
            purchase_invoice_name,
            inward_supply_name,
            link_doctype,
        });

        const _class = frm.reconciliation_tabs;
        const new_data = _class.data.filter(
            row =>
                !(
                    row.purchase_invoice_name == purchase_invoice_name ||
                    row.inward_supply_name == inward_supply_name
                )
        );

        new_data.push(...r);

        _class.refresh(new_data);
        if (alert) reconciliation.after_successful_action(_class.tabs.invoice_tab);
    },

    async create_new_purchase_invoice(row, company, company_gstin, source_doc) {
        if (row.match_status != "Missing in PI") return;
        const doc = row._inward_supply;

        const { message: supplier } = await frappe.call({
            method: "india_compliance.gst_india.utils.get_party_for_gstin",
            args: {
                gstin: row.supplier_gstin,
            },
        });

        let company_address;
        await frappe.model.get_value(
            "Address",
            { gstin: company_gstin, is_your_company_address: 1 },
            "name",
            r => (company_address = r.name)
        );

        frappe.route_hooks.after_load = frm => {
            function _set_value(values) {
                for (const key in values) {
                    if (values[key] == frm.doc[key]) continue;
                    frm.set_value(key, values[key]);
                }
            }

            const is_return = row.classification.includes("CDNR") ? 1 : 0;
            const multiplier = is_return ? -1 : 1;

            const values = {
                company: company,
                bill_no: doc.bill_no,
                bill_date: doc.bill_date,
                is_reverse_charge: ["Yes", 1].includes(doc.is_reverse_charge) ? 1 : 0,
                is_return: is_return,
            };

            _set_value({
                ...values,
                supplier: supplier,
                shipping_address: company_address,
                billing_address: company_address,
            });

            // validated this on save
            frm._inward_supply = {
                ...values,
                name: row.inward_supply_name,
                company_gstin: doc.company_gstin,
                inward_supply: row.inward_supply,
                supplier_gstin: row.supplier_gstin,
                place_of_supply: doc.place_of_supply,
                cgst: doc.cgst * multiplier,
                sgst: doc.sgst * multiplier,
                igst: doc.igst * multiplier,
                cess: doc.cess * multiplier,
                taxable_value: doc.taxable_value * multiplier,
                source_doc,
            };
        };

        frappe.new_doc("Purchase Invoice");
    },

    after_successful_action(tab) {
        if (tab) tab.datatable.clear_checked_items();
        frappe.show_alert({
            message: "Action applied successfully",
            indicator: "green",
        });
    },
});
