const DOCTYPE = "Purchase Invoice";

const erpnext_onload = frappe.listview_settings[DOCTYPE]?.onload;
frappe.listview_settings[DOCTYPE].onload = function (list_view) {
    if (erpnext_onload) {
        erpnext_onload(list_view);
    }

    if (!frappe.perm.has_perm(DOCTYPE, 0, "submit")) return;

    add_bulk_action_for_invoices(list_view, __("ISD Invoice"), handle_isd_invoice);
};

function add_bulk_action_for_invoices(list_view, label, callback, allowed_status) {
    if (!allowed_status) allowed_status = [1];
    list_view.page.add_actions_menu_item(label, async () => {
        const selected_docs = list_view.get_checked_items();
        const submitted_docs = await validate_doc_status(selected_docs, allowed_status);
        if (submitted_docs) callback(submitted_docs);
    });
}

async function handle_isd_invoice(docnames) {
    const pis = await frappe.db.get_list("Purchase Invoice", {
        filters: { name: ["in", docnames] },
        fields: ["name", "posting_date", "supplier", "company", "is_isd_applicable"],
    });

    const non_applicable = pis.filter((p) => !p.is_isd_applicable).map((p) => p.name);
    if (non_applicable.length) {
        frappe.throw(
            __(
                "The following Purchase Invoices are not applicable for ISD: {0}",
                [non_applicable.join(", ")],
            ),
        );
        return;
    }

    const companies = new Set(pis.map((p) => p.company));
    if (companies.size > 1) {
        frappe.throw(__("Selected Purchase Invoices must belong to the same Company."));
        return;
    }

    const min_posting_date = pis.reduce(
        (min, p) => (p.posting_date < min ? p.posting_date : min),
        pis[0].posting_date,
    );
    const summary_result = await frappe.call({
        method: "india_compliance.gst_india.doctype.isd_invoice.isd_invoice.get_purchase_invoices_distribution_summary",
        args: { purchase_invoices: docnames, posting_date: min_posting_date },
    });

    const summary_by_pi = {};
    for (const row of summary_result.message || []) {
        summary_by_pi[row.purchase_invoice] = row;
    }

    const purchase_invoices = pis.map((p) => ({
        name: p.name,
        posting_date: p.posting_date,
        supplier: p.supplier,
        company: p.company,
        total_tax: (summary_by_pi[p.name] || {}).total_tax || 0,
        total_distributed: (summary_by_pi[p.name] || {}).total_distributed || 0,
    }));

    india_compliance.show_isd_invoice_distribution_dialog(purchase_invoices);
}

// TODO: This function is common for both sales and purchase invoice list views. It can be moved to a common utility file in india_compliance app.
async function validate_doc_status(selected_docs, allowed_status) {
    const valid_docs = [];
    const invalid_docs = [];
    const status_map = {
        0: "draft",
        1: "submitted",
        2: "cancelled",
    };

    for (const doc of selected_docs) {
        if (!allowed_status.includes(doc.docstatus)) {
            invalid_docs.push(doc.name);
        } else {
            valid_docs.push(doc.name);
        }
    }

    if (!invalid_docs.length) return valid_docs;

    const allowed_status_str = allowed_status.map((status) => status_map[status]).join(" or ");

    if (!valid_docs.length) {
        frappe.throw(__("This action can only be performed on {0} documents", [allowed_status_str]));
    }

    const confirmed = await new Promise((resolve) => {
        frappe.confirm(
            __(
                "This action can only be performed on {0} documents. Do you want to continue without the following documents?<br><br><strong>{1}</strong>",
                [allowed_status_str, invalid_docs.join("<br>")],
            ),
            () => resolve(true),
        );
    });

    return confirmed ? valid_docs : false;
}
