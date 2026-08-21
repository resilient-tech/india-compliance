frappe.provide("reconciliation");

Object.assign(reconciliation, {
    // checked rows of the open tab, as invoices. a summary row stands for many
    get_affected_rows(frm) {
        const _class = frm.reconciliation_tabs;
        const active_tab = frm.get_active_tab()?.df.fieldname;
        const checked = _class.tabs[active_tab]?.datatable.get_checked_items() || [];

        if (active_tab == "invoice_tab") return checked;

        const matches = _class.summary_matchers[active_tab];
        if (!matches) return [];

        return _class.filtered_data.filter((row) => checked.some((item) => matches(item, row)));
    },

    get_unlinked_docs(selected_rows) {
        const unlinked_docs = new Set();
        selected_rows.forEach((row) => {
            unlinked_docs.add(row.purchase_invoice_name);
            unlinked_docs.add(row.inward_supply_name);
        });

        return unlinked_docs;
    },

    async unlink_documents(frm, selected_rows) {
        const _class = frm.reconciliation_tabs;
        const tab = _class.tabs[frm.get_active_tab()?.df.fieldname];
        if (!selected_rows) selected_rows = reconciliation.get_affected_rows(frm);

        // nothing to unlink where a side is missing
        const rows = selected_rows.filter((row) => row.purchase_invoice_name && row.inward_supply_name);

        if (!rows.length)
            return frappe.show_alert({
                message: __("Please select linked rows to unlink"),
                indicator: "red",
            });

        const exclude_from_reconciliation = await reconciliation.prompt_unlink_intent(
            rows.length,
            selected_rows.length - rows.length,
        );
        if (exclude_from_reconciliation === null) return; // cancelled

        // unlink documents & update table
        const { message: r } = await frm._call("unlink_documents", {
            data: rows,
            exclude_from_reconciliation,
        });

        const unlinked_docs = reconciliation.get_unlinked_docs(rows);

        const new_data = _class.data.filter(
            (row) =>
                !(unlinked_docs.has(row.purchase_invoice_name) || unlinked_docs.has(row.inward_supply_name)),
        );

        new_data.push(...r);
        _class.refresh(new_data);
        reconciliation.after_successful_action(tab);
    },

    SYNCABLE_FIELDS: [
        { fieldname: "bill_no", label: "Bill No" },
        { fieldname: "bill_date", label: "Bill Date" },
    ],

    async sync_details(frm, selected_rows, fields) {
        const _class = frm.reconciliation_tabs;
        const tab = _class.tabs[frm.get_active_tab()?.df.fieldname];
        if (!selected_rows) selected_rows = reconciliation.get_affected_rows(frm);

        // the server skips these anyway, we filter to tell the two empty cases apart:
        // nothing selected to sync vs nothing left to sync
        //TODO: can't think of any case where this will be needed
        const rows = selected_rows.filter((row) => row.purchase_invoice_name && row.inward_supply_name);

        if (!rows.length)
            return frappe.show_alert({
                message: __("Please select matched rows to sync"),
                indicator: "red",
            });

        if (!fields) {
            fields = await reconciliation.prompt_sync_fields();
            if (fields === null) return; // cancelled

            if (!fields.length)
                return frappe.show_alert({
                    message: __("Please select at least one value to copy"),
                    indicator: "orange",
                });
        }

        let synced_rows;
        try {
            ({ message: synced_rows } = await frm._call("sync_details", { data: rows, fields }));
        } catch {
            return frappe.show_alert({
                message: __("An error occurred while syncing data"),
                indicator: "red",
            });
        }

        if (!synced_rows.length)
            return frappe.show_alert({
                message: __("No changes to sync"),
                indicator: "blue",
            });

        // drop the stale copies before pushing the refreshed ones back, else they double up
        const synced_names = new Set(synced_rows.map((row) => row.inward_supply_name));
        const new_data = _class.data.filter((row) => !synced_names.has(row.inward_supply_name));

        new_data.push(...synced_rows);
        _class.refresh(new_data);

        if (tab) tab.datatable.clear_checked_items();

        frappe.show_alert({
            message: __("{0} synced successfully", [reconciliation.get_field_labels(fields).join(", ")]),
            indicator: "green",
        });
    },

    get_field_labels(fields) {
        return reconciliation.SYNCABLE_FIELDS.filter((field) => fields.includes(field.fieldname)).map(
            (field) => __(field.label),
        );
    },

    prompt_sync_fields() {
        const syncable_fields = reconciliation.SYNCABLE_FIELDS;

        return new Promise((resolve) => {
            const dialog = new frappe.ui.Dialog({
                title: __("Copy Values from 2A/2B"),
                // the checks run across one section, so they read as a single choice
                fields: syncable_fields.flatMap((field, index) => [
                    ...(index ? [{ fieldtype: "Column Break" }] : []),
                    {
                        fieldtype: "Check",
                        fieldname: field.fieldname,
                        label: __(field.label),
                        default: 1,
                    },
                ]),
                primary_action_label: __("Apply"),
                primary_action(values) {
                    resolve(
                        syncable_fields
                            .filter((field) => values[field.fieldname])
                            .map((field) => field.fieldname),
                    );
                    dialog.hide();
                },
            });
            dialog.onhide = () => resolve(null);
            dialog.show();
        });
    },

    prompt_unlink_intent(count, skipped) {
        // gives back the exclude flag, or null if cancelled
        return new Promise((resolve) => {
            const dialog = new frappe.ui.Dialog({
                title: __("Unlink {0} Document(s)", [count]),
                fields: [
                    ...(skipped
                        ? [
                              {
                                  fieldtype: "HTML",
                                  options: `<p class="text-muted">${__(
                                      "Skipping {0} with nothing to unlink.",
                                      [skipped],
                                  )}</p>`,
                              },
                          ]
                        : []),
                    {
                        fieldtype: "Check",
                        fieldname: "exclude_from_reconciliation",
                        label: __("Do not reconcile these again automatically"),
                        description: __("Enable this where you intend to manually reconcile them"),
                        default: 0,
                    },
                ],
                primary_action_label: __("Unlink"),
                primary_action(values) {
                    resolve(!!values.exclude_from_reconciliation);
                    dialog.hide();
                },
            });
            dialog.onhide = () => resolve(null); // no-op if primary already resolved
            dialog.show();
        });
    },

    async link_documents(frm, purchase_invoice_name, inward_supply_name, link_doctype, alert = true) {
        if (frm.get_active_tab()?.df.fieldname != "invoice_tab") return;

        // link documents & update data.
        const { message: r } = await frm._call("link_documents", {
            purchase_invoice_name,
            inward_supply_name,
            link_doctype,
        });

        const _class = frm.reconciliation_tabs;
        const new_data = _class.data.filter(
            (row) =>
                !(
                    row.purchase_invoice_name == purchase_invoice_name ||
                    row.inward_supply_name == inward_supply_name
                ),
        );

        new_data.push(...r);

        _class.refresh(new_data);
        if (alert) reconciliation.after_successful_action(_class.tabs.invoice_tab);
    },

    async create_new_purchase_invoice(row, company, company_gstin, source_doc) {
        if (row.match_status != "Only in 2A/2B") return;
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
            (r) => (company_address = r.name),
        );

        frappe.route_hooks.after_load = (frm) => {
            function _set_value(values) {
                for (const key in values) {
                    if (values[key] == frm.doc[key]) continue;
                    frm.set_value(key, values[key]);
                }
            }

            // only for cn, not for dn
            const is_return = doc.doc_type == "Credit Note" ? 1 : 0;
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
