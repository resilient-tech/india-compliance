const WARNING_ICON = `
    <span
        class='warning-icon link-btn mb-auto mt-auto'
        title='2A/2B Status: Unreconciled'
        style='display: block; z-index: 1; top: 5px; width: 24px; height: 24px;'
    >
        <div>${frappe.utils.icon("solid-warning", "md")}</div>
    </span>
`;

frappe.ui.form.on("Payment Entry", {
    setup: override_get_outstanding_documents,

    refresh(frm) {
        add_warning_indicator(frm, frm.doc.__onload?.reconciliation_status_dict);
    },

    company(frm) {
        frappe.call({
            method: "frappe.contacts.doctype.address.address.get_default_address",
            args: {
                doctype: "Company",
                name: frm.doc.company,
            },
            callback(r) {
                frm.set_value("company_address", r.message);
            },
        });
    },

    party(frm) {
        update_gst_details(
            frm,
            "india_compliance.gst_india.overrides.payment_entry.update_party_details"
        );
    },

    customer_address(frm) {
        update_gst_details(frm);
    },
});

function override_get_outstanding_documents(frm) {
    const old_fn = frm.events?.get_outstanding_documents;
    if (!old_fn) return;

    const new_fn = function () {
        old_fn(...arguments);
        if (frm.doc.party_type != "Supplier") return;

        frappe.after_ajax(() => {
            const response = frappe?.last_response?.message || [];

            if (!Array.isArray(response)) return;

            const reconciliation_status_dict = response.reduce((acc, d) => {
                acc[d.voucher_no] = d.reconciliation_status;
                return acc;
            }, {});

            add_warning_indicator(frm, reconciliation_status_dict);
        });
    };

    frm.events.get_outstanding_documents = new_fn;
    const handlers = frappe.ui.form.handlers[frm.doctype];
    handlers["get_outstanding_documents"] = handlers["get_outstanding_documents"].map(
        fn => (fn === old_fn ? new_fn : fn)
    );
}

frappe.ui.form.on("Payment Entry Reference", {
    reference_name(frm, cdt, cdn) {
        const row = frappe.get_doc(cdt, cdn);

        if (row.reference_doctype !== "Purchase Invoice") return;

        frappe.db
            .get_value(
                row.reference_doctype,
                row.reference_name,
                "reconciliation_status"
            )
            .then(response => {
                if (!response.message) return;

                const reconciliation_status_dict = {};
                reconciliation_status_dict[row.reference_name] =
                    response.message.reconciliation_status;

                add_warning_indicator(
                    frm,
                    reconciliation_status_dict,
                    row.reference_name
                );
            });
    },
});

function add_warning_indicator(frm, reconciliation_status_dict, name) {
    if (!reconciliation_status_dict) return;

    let rows = frm.fields_dict.references.grid.grid_rows.filter(
        r => r.doc.reference_doctype === "Purchase Invoice"
    );

    // Add warning indicator to a particular row only
    if (name) rows = rows.filter(r => r.doc.reference_name === name);

    for (const row of rows) {
        if (
            !reconciliation_status_dict[row.doc.reference_name] ||
            reconciliation_status_dict[row.doc.reference_name] !== "Unreconciled"
        )
            continue;

        const target_div = row.columns.reference_name;
        const is_warning_icon_already_present =
            $(target_div).find(".warning-icon").length > 0;

        if (is_warning_icon_already_present) continue;

        $(WARNING_ICON).appendTo(target_div);
        $(target_div).find(".static-area").css("padding-right", "16px");
    }
}

async function update_gst_details(frm, method) {
    if (
        frm.doc.party_type != "Customer" ||
        !frm.doc.party ||
        frm.__updating_gst_details
    )
        return;

    // wait for GSTINs to get fetched
    await frappe.after_ajax();

    const args = {
        doctype: frm.doc.doctype,
        party_details: {
            customer: frm.doc.party,
            customer_address: frm.doc.customer_address,
            billing_address_gstin: frm.doc.billing_address_gstin,
            gst_category: frm.doc.gst_category,
            company_gstin: frm.doc.company_gstin,
        },
        company: frm.doc.company,
    };

    india_compliance.fetch_and_update_gst_details(frm, args, method);
}
