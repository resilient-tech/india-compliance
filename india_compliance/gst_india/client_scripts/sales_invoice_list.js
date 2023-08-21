const DOCTYPE = "Sales Invoice";
setup_e_waybill_actions(DOCTYPE);

const erpnext_onload = frappe.listview_settings[DOCTYPE].onload;
frappe.listview_settings[DOCTYPE].onload = function (list_view) {
    if (erpnext_onload) {
        erpnext_onload(list_view);
    }

    if (!frappe.perm.has_perm(DOCTYPE, 0, "submit")) return;

    if (gst_settings.enable_e_waybill) {
        add_bulk_action_for_submitted_invoices(
            list_view,
            __("Generate e-Waybill JSON"),
            generate_e_waybill_json
        );

        add_bulk_action_for_submitted_invoices(
            list_view,
            __("Bulk Update Transporter Detail"),
            show_bulk_update_transporter_dialog
        );

        add_bulk_action_for_submitted_invoices(
            list_view,
            __("Enqueue Bulk e-Waybill Generation"),
            enqueue_bulk_e_waybill_generation
        );
    }

    if (india_compliance.is_e_invoice_enabled())
        add_bulk_action_for_submitted_invoices(
            list_view,
            __("Enqueue Bulk e-Invoice Generation"),
            enqueue_bulk_e_invoice_generation
        );
};

function add_bulk_action_for_submitted_invoices(list_view, label, callback) {
    list_view.page.add_actions_menu_item(label, async () => {
        const selected_docs = list_view.get_checked_items();
        const submitted_docs = await validate_if_submitted(selected_docs);
        if (submitted_docs) callback(submitted_docs);
    });
}

async function generate_e_waybill_json(docnames) {
    const ewb_data = await frappe.xcall(
        "india_compliance.gst_india.utils.e_waybill.generate_e_waybill_json",
        { doctype: DOCTYPE, docnames }
    );

    trigger_file_download(ewb_data, get_e_waybill_file_name());
}

function show_bulk_update_transporter_dialog(docnames) {
    const fields = [
        {
            label: "Part A",
            fieldname: "section_part_a",
            fieldtype: "Section Break",
        },
        {
            label: "Transporter",
            fieldname: "transporter",
            fieldtype: "Link",
            options: "Supplier",
            reqd: 1,
            get_query: () => {
                return {
                    filters: {
                        is_transporter: 1,
                    },
                };
            },
            onchange: () => update_gst_tranporter_id(d),
        },
        {
            label: "Distance (in km)",
            fieldname: "distance",
            fieldtype: "Float",
            description:
                "Set as zero to update distance as per the e-Waybill portal (if available)",
        },
        {
            fieldtype: "Column Break",
        },
        {
            label: "GST Transporter ID",
            fieldname: "gst_transporter_id",
            fieldtype: "Data",
        },
        {
            label: "Part B",
            fieldname: "section_part_b",
            fieldtype: "Section Break",
        },

        {
            label: "Vehicle No",
            fieldname: "vehicle_no",
            fieldtype: "Data",
        },
        {
            label: "Transport Receipt No",
            fieldname: "lr_no",
            fieldtype: "Data",
        },
        {
            label: "Transport Receipt Date",
            fieldname: "lr_date",
            fieldtype: "Date",
            mandatory_depends_on: "eval:doc.lr_no",
        },
        {
            fieldtype: "Column Break",
        },

        {
            label: "Mode Of Transport",
            fieldname: "mode_of_transport",
            fieldtype: "Select",
            options: `\nRoad\nAir\nRail\nShip`,
            default: "Road",
            onchange: () => {
                update_vehicle_type(d);
            },
        },
        {
            label: "GST Vehicle Type",
            fieldname: "gst_vehicle_type",
            fieldtype: "Select",
            options: `Regular\nOver Dimensional Cargo (ODC)`,
            depends_on: 'eval:["Road", "Ship"].includes(doc.mode_of_transport)',
            read_only_depends_on: "eval: doc.mode_of_transport == 'Ship'",
        },
    ];

    const d = new frappe.ui.Dialog({
        title: __("Update Transporter Detail"),
        fields,
        primary_action_label: __("Update"),
        primary_action(values) {
            d.hide();

            if (!india_compliance.is_e_waybill_enabled()) {
                frappe.throw(__("Enable e-Waybill from GST Settings"));
            }

            enqueue_bulk_generation(
                "india_compliance.gst_india.utils.e_waybill.enqueue_bulk_update_transporter",
                {
                    doctype: DOCTYPE,
                    docnames,
                    values,
                },
                false
            );
        },
    });

    d.show();
}

async function enqueue_bulk_e_waybill_generation(docnames) {
    enqueue_bulk_generation(
        "india_compliance.gst_india.utils.e_waybill.enqueue_bulk_e_waybill_generation",
        { doctype: DOCTYPE, docnames }
    );
}

async function enqueue_bulk_e_invoice_generation(docnames) {
    enqueue_bulk_generation(
        "india_compliance.gst_india.utils.e_invoice.enqueue_bulk_e_invoice_generation",
        { docnames }
    );
}

async function enqueue_bulk_generation(method, args, api_requests = true) {
    const job_id = await frappe.xcall(method, args);

    const now = frappe.datetime.system_datetime();
    const creation_filter = `[">", "${now}"]`;
    const error_logs_link = frappe.utils.generate_route({
        type: "doctype",
        name: "Error Log",
        route_options: {
            creation: creation_filter,
        },
    });

    let message = __(
        `Bulk Generation has been queued. You can track the
            <a href='{0}'>Background Job</a>,
            <a href='{1}'>Error Log(s)</a>`,
        [frappe.utils.get_form_link("RQ Job", job_id), error_logs_link]
    );

    if (api_requests) {
        const api_requests_link = frappe.utils.generate_route({
            type: "doctype",
            name: "Integration Request",
            route_options: {
                integration_request_service: "India Compliance API",
                creation: creation_filter,
            },
        });

        message += __(`and <a href='{0}'>API Request(s)</a>`, [api_requests_link]);
    }

    frappe.msgprint(message);
}

async function validate_if_submitted(selected_docs) {
    const valid_docs = [];
    const invalid_docs = [];

    for (const doc of selected_docs) {
        if (doc.docstatus != 1) {
            invalid_docs.push(doc.name);
        } else {
            valid_docs.push(doc.name);
        }
    }

    if (!invalid_docs.length) return valid_docs;

    if (!valid_docs.length) {
        frappe.throw(__("This action can only be performed on submitted documents"));
    }

    const confirmed = await new Promise(resolve => {
        frappe.confirm(
            __(
                "This action can only be performed on submitted documents. Do you want to continue without the following documents?<br><br><strong>{0}</strong>",
                [invalid_docs.join("<br>")]
            ),
            () => resolve(true)
        );
    });

    return confirmed ? valid_docs : false;
}
