function setup_e_waybill_actions(doctype) {
    if (
        !gst_settings.enable_e_waybill ||
        (doctype == "Delivery Note" && !gst_settings.enable_e_waybill_from_dn)
    )
        return;

    frappe.ui.form.on(doctype, {
        mode_of_transport(frm) {
            frm.set_value("gst_vehicle_type", get_vehicle_type(frm.doc));
        },
        setup(frm) {
            if (!india_compliance.is_api_enabled()) return;

            frappe.realtime.on("e_waybill_pdf_update", message => {
                frappe.model.sync_docinfo(message);
                frm.attachments && frm.attachments.refresh();

                if (message.pdf_deleted) return;

                frappe.show_alert({
                    indicator: "green",
                    message: __("e-Waybill PDF attached successfully"),
                });
            });
        },
        refresh(frm) {
            if (
                frm.doc.docstatus != 1 ||
                frm.is_dirty() ||
                !is_e_waybill_applicable(frm) ||
                (frm.doctype === "Delivery Note" && !frm.doc.customer_address)
            )
                return;

            if (!frm.doc.ewaybill) {
                if (frappe.perm.has_perm(frm.doctype, 0, "submit", frm.doc.name)) {
                    frm.add_custom_button(
                        __("Generate"),
                        () => show_generate_e_waybill_dialog(frm),
                        "e-Waybill"
                    );
                }

                if (
                    has_e_waybill_threshold_met(frm) &&
                    !frm.doc.is_return &&
                    !frm.doc.is_debit_note
                ) {
                    frm.dashboard.add_comment(
                        __(
                            "e-Waybill is applicable for this invoice, but not yet generated or updated."
                        ),
                        "yellow",
                        true
                    );
                }

                return;
            }

            if (!india_compliance.is_api_enabled() || !is_e_waybill_generated_using_api(frm)) {
                return;
            }

            frm.set_df_property("ewaybill", "allow_on_submit", 0);

            if (
                frappe.perm.has_perm(frm.doctype, 0, "submit", frm.doc.name) &&
                is_e_waybill_valid(frm)
            ) {
                frm.add_custom_button(
                    __("Update Vehicle Info"),
                    () => show_update_vehicle_info_dialog(frm),
                    "e-Waybill"
                );

                frm.add_custom_button(
                    __("Update Transporter"),
                    () => show_update_transporter_dialog(frm),
                    "e-Waybill"
                );
            }

            if (
                frappe.perm.has_perm(frm.doctype, 0, "cancel", frm.doc.name) &&
                is_e_waybill_cancellable(frm)
            ) {
                frm.add_custom_button(
                    __("Cancel"),
                    () => show_cancel_e_waybill_dialog(frm),
                    "e-Waybill"
                );
            }

            if (frappe.model.can_print("e-Waybill Log")) {
                frm.add_custom_button(
                    __("Print"),
                    () => {
                        frappe.set_route("print", "e-Waybill Log", frm.doc.ewaybill);
                    },
                    "e-Waybill"
                );
            }

            if (frappe.perm.has_perm(frm.doctype, 0, "write", frm.doc.name)) {
                frm.add_custom_button(
                    __("Attach"),
                    () => fetch_e_waybill_data(frm, { attach: 1 }, () => frm.refresh()),
                    "e-Waybill"
                );
            }
        },
        async on_submit(frm) {
            if (
                // threshold is only met for Sales Invoice
                !has_e_waybill_threshold_met(frm) ||
                frm.doc.ewaybill ||
                frm.doc.is_return ||
                frm.doc.is_debit_note ||
                !india_compliance.is_api_enabled() ||
                !gst_settings.auto_generate_e_waybill ||
                is_e_invoice_applicable(frm) ||
                !is_e_waybill_applicable(frm)
            )
                return;

            frappe.show_alert(__("Attempting to generate e-Waybill"));

            await frappe.xcall(
                "india_compliance.gst_india.utils.e_waybill.generate_e_waybill",
                { doctype: frm.doctype, docname: frm.doc.name }
            );
        },
        before_cancel(frm) {
            // if IRN is present, e-Waybill gets cancelled in e-Invoice action
            if (!india_compliance.is_api_enabled() || frm.doc.irn || !frm.doc.ewaybill) return;

            frappe.validated = false;

            return new Promise(resolve => {
                const continueCancellation = () => {
                    frappe.validated = true;
                    resolve();
                };

                if (!is_e_waybill_cancellable(frm)) {
                    const d = frappe.warn(
                        __("Cannot Cancel e-Waybill"),
                        __(
                            `The e-Waybill created against this invoice cannot be
                            cancelled.<br><br>

                            Do you want to continue anyway?`
                        ),
                        continueCancellation,
                        __("Yes")
                    );

                    d.set_secondary_action_label(__("No"));
                    return;
                }

                return show_cancel_e_waybill_dialog(frm, continueCancellation);
            });
        },
    });
}
function fetch_e_waybill_data(frm, args, callback) {
    if (!args) args = {};

    frappe.call({
        method: "india_compliance.gst_india.utils.e_waybill.fetch_e_waybill_data",
        args: { doctype: frm.doctype, docname: frm.doc.name, ...args },
        callback,
    });
}

function show_generate_e_waybill_dialog(frm) {
    const generate_action = values => {
        frappe.call({
            method: "india_compliance.gst_india.utils.e_waybill.generate_e_waybill",
            args: {
                doctype: frm.doctype,
                docname: frm.doc.name,
                values,
            },
            callback: () => frm.refresh(),
        });
    };

    const json_action = async values => {
        const ewb_data = await frappe.xcall(
            "india_compliance.gst_india.utils.e_waybill.generate_e_waybill_json",
            {
                doctype: frm.doctype,
                docnames: frm.doc.name,
                values,
            }
        );

        frm.refresh();
        trigger_file_download(ewb_data, get_e_waybill_file_name(frm.doc.name));
    };

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
            default: frm.doc.transporter,
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
            default: frm.doc.distance,
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
            default:
                frm.doc.gst_transporter_id && frm.doc.gst_transporter_id.length == 15
                    ? frm.doc.gst_transporter_id
                    : "",
        },
        // Sub Supply Type will be visible here for Delivery Note
        {
            label: "Part B",
            fieldname: "section_part_b",
            fieldtype: "Section Break",
        },

        {
            label: "Vehicle No",
            fieldname: "vehicle_no",
            fieldtype: "Data",
            default: frm.doc.vehicle_no,
            onchange: () => update_generation_dialog(d),
        },
        {
            label: "Transport Receipt No",
            fieldname: "lr_no",
            fieldtype: "Data",
            default: frm.doc.lr_no,
            onchange: () => update_generation_dialog(d),
        },
        {
            label: "Transport Receipt Date",
            fieldname: "lr_date",
            fieldtype: "Date",
            default: frm.doc.lr_date,
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
            default: frm.doc.mode_of_transport,
            onchange: () => {
                update_generation_dialog(d);
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
            default: frm.doc.gst_vehicle_type,
        },
    ];

    if (frm.doctype === "Delivery Note") {
        const same_gstin = frm.doc.billing_address_gstin == frm.doc.company_gstin;
        let options;

        if (frm.doc.is_return) {
            if (same_gstin) {
                options = ["For Own Use", "Exhibition or Fairs"];
            } else {
                options = ["Job Work Returns", "SKD/CKD"];
            }
        } else {
            if (same_gstin) {
                options = [
                    "For Own Use",
                    "Exhibition or Fairs",
                    "Line Sales",
                    "Recipient Not Known",
                ];
            } else {
                options = ["Job Work", "SKD/CKD"];
            }
        }

        // Inserted at the end of Part A section
        fields.splice(5, 0, {
            label: "Sub Supply Type",
            fieldname: "sub_supply_type",
            fieldtype: "Select",
            options: options.join("\n"),
            default: options[0],
            reqd: 1,
        });
    }

    const api_enabled = india_compliance.is_api_enabled();

    const d = new frappe.ui.Dialog({
        title: __("Generate e-Waybill"),
        fields,
        primary_action_label: get_primary_action_label_for_generation(frm.doc),
        primary_action(values) {
            d.hide();

            if (api_enabled) {
                generate_action(values);
            } else {
                json_action(values);
            }
        },
        secondary_action_label: api_enabled ? __("Download JSON") : null,
        secondary_action: api_enabled
            ? () => {
                  d.hide();
                  json_action(d.get_values());
              }
            : null,
    });

    d.show();

    // Alert if e-Invoice hasn't been generated
    if (
        frm.doctype === "Sales Invoice" &&
        is_e_invoice_applicable(frm) &&
        !frm.doc.irn
    ) {
        $(`
            <div class="alert alert-warning" role="alert">
                e-Invoice hasn't been generated for this Sales Invoice.
                <a
                    href="https://docs.erpnext.com/docs/v14/user/manual/en/regional/india/generating_e_invoice#what-if-we-generate-e-waybill-before-the-e-invoice"
                    class="alert-link"
                    target="_blank"
                >
                    Learn more
                </a>
            </div>
        `).prependTo(d.wrapper);
    }
}

function show_cancel_e_waybill_dialog(frm, callback) {
    const d = new frappe.ui.Dialog({
        title: __("Cancel e-Waybill"),
        fields: [
            {
                label: "e-Waybill",
                fieldname: "ewaybill",
                fieldtype: "Data",
                read_only: 1,
                default: frm.doc.ewaybill,
            },
            {
                label: "Reason",
                fieldname: "reason",
                fieldtype: "Select",
                reqd: 1,
                default: "Data Entry Mistake",
                options: [
                    "Duplicate",
                    "Order Cancelled",
                    "Data Entry Mistake",
                    "Others",
                ],
            },
            {
                label: "Remark",
                fieldname: "remark",
                fieldtype: "Data",
                mandatory_depends_on: "eval: doc.reason == 'Others'",
            },
        ],
        primary_action_label: __("Cancel"),
        primary_action(values) {
            frappe.call({
                method: "india_compliance.gst_india.utils.e_waybill.cancel_e_waybill",
                args: {
                    doctype: frm.doctype,
                    docname: frm.doc.name,
                    values,
                },
                callback: () => {
                    frm.refresh();
                    if (callback) callback();
                },
            });
            d.hide();
        },
    });

    d.show();
}

function show_update_vehicle_info_dialog(frm) {
    const d = new frappe.ui.Dialog({
        title: __("Update Vehicle Information"),
        fields: [
            {
                label: "e-Waybill",
                fieldname: "ewaybill",
                fieldtype: "Data",
                read_only: 1,
                default: frm.doc.ewaybill,
            },
            {
                label: "Vehicle No",
                fieldname: "vehicle_no",
                fieldtype: "Data",
                default: frm.doc.vehicle_no,
                mandatory_depends_on:
                    "eval: ['Road', 'Ship'].includes(doc.mode_of_transport)",
            },
            {
                label: "Transport Receipt No",
                fieldname: "lr_no",
                fieldtype: "Data",
                default: frm.doc.lr_no,
                mandatory_depends_on:
                    "eval: ['Rail', 'Air', 'Ship'].includes(doc.mode_of_transport)",
            },
            {
                fieldtype: "Column Break",
            },
            {
                label: "Mode Of Transport",
                fieldname: "mode_of_transport",
                fieldtype: "Select",
                options: `\nRoad\nAir\nRail\nShip`,
                default: frm.doc.mode_of_transport,
                mandatory_depends_on: "eval: doc.lr_no",
                onchange: () => update_vehicle_type(d),
            },
            {
                label: "GST Vehicle Type",
                fieldname: "gst_vehicle_type",
                fieldtype: "Select",
                options: `Regular\nOver Dimensional Cargo (ODC)`,
                depends_on: 'eval:["Road", "Ship"].includes(doc.mode_of_transport)',
                read_only_depends_on: "eval: doc.mode_of_transport == 'Ship'",
                default: frm.doc.gst_vehicle_type,
            },
            {
                label: "Transport Receipt Date",
                fieldname: "lr_date",
                fieldtype: "Date",
                default: frm.doc.lr_date,
                mandatory_depends_on: "eval:doc.lr_no",
            },
            {
                fieldtype: "Section Break",
            },
            {
                fieldname: "reason",
                label: "Reason",
                fieldtype: "Select",
                options: [
                    "Due to Break Down",
                    "Due to Trans Shipment",
                    "First Time",
                    "Others",
                ],
                reqd: 1,
            },
            {
                label: "Update e-Waybill Print/Data",
                fieldname: "update_e_waybill_data",
                fieldtype: "Check",
                default: gst_settings.fetch_e_waybill_data,
            },
            {
                fieldtype: "Column Break",
            },
            {
                fieldname: "remark",
                label: "Remark",
                fieldtype: "Data",
                mandatory_depends_on: 'eval: doc.reason == "Others"',
            },
        ],
        primary_action_label: __("Update"),
        primary_action(values) {
            frappe.call({
                method: "india_compliance.gst_india.utils.e_waybill.update_vehicle_info",
                args: {
                    doctype: frm.doctype,
                    docname: frm.doc.name,
                    values,
                },
                callback: () => frm.refresh(),
            });
            d.hide();
        },
    });

    d.show();
}

function show_update_transporter_dialog(frm) {
    const d = new frappe.ui.Dialog({
        title: __("Update Transporter"),
        fields: [
            {
                label: "e-Waybill",
                fieldname: "ewaybill",
                fieldtype: "Data",
                read_only: 1,
                default: frm.doc.ewaybill,
            },
            {
                label: "Transporter",
                fieldname: "transporter",
                fieldtype: "Link",
                options: "Supplier",
                default: frm.doc.transporter,
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
                label: "GST Transporter ID",
                fieldname: "gst_transporter_id",
                fieldtype: "Data",
                reqd: 1,
                default:
                    frm.doc.gst_transporter_id &&
                    frm.doc.gst_transporter_id.length == 15
                        ? frm.doc.gst_transporter_id
                        : "",
            },
            {
                label: "Update e-Waybill Print/Data",
                fieldname: "update_e_waybill_data",
                fieldtype: "Check",
                default: gst_settings.fetch_e_waybill_data,
            },
        ],
        primary_action_label: __("Update"),
        primary_action(values) {
            frappe.call({
                method: "india_compliance.gst_india.utils.e_waybill.update_transporter",
                args: {
                    doctype: frm.doctype,
                    docname: frm.doc.name,
                    values,
                },
                callback: () => frm.refresh(),
            });
            d.hide();
        },
    });

    d.show();
}

function is_e_waybill_valid(frm) {
    const e_waybill_info = frm.doc.__onload && frm.doc.__onload.e_waybill_info;
    return (
        e_waybill_info &&
        (!e_waybill_info.valid_upto ||
            frappe.datetime
                .convert_to_user_tz(e_waybill_info.valid_upto, false)
                .diff() > 0)
    );
}

function has_e_waybill_threshold_met(frm) {
    if (
        frm.doc.doctype == "Sales Invoice" &&
        Math.abs(frm.doc.base_grand_total) >= gst_settings.e_waybill_threshold
    )
        return true;
}

function is_e_waybill_applicable(frm) {
    // means company is Indian and not Unregistered
    if (!frm.doc.company_gstin) return;

    // at least one item is not a service
    for (const item of frm.doc.items) {
        if (item.gst_hsn_code && !item.gst_hsn_code.startsWith("99") && item.qty !== 0)
            return true;
    }
}

function is_e_waybill_cancellable(frm) {
    const e_waybill_info = frm.doc.__onload && frm.doc.__onload.e_waybill_info;
    return (
        e_waybill_info &&
        frappe.datetime
            .convert_to_user_tz(e_waybill_info.created_on, false)
            .add("days", 1)
            .diff() > 0
    );
}

function is_e_waybill_generated_using_api(frm) {
    const e_waybill_info = frm.doc.__onload && frm.doc.__onload.e_waybill_info;
    return e_waybill_info && e_waybill_info.created_on;
}

async function update_gst_tranporter_id(dialog) {
    const transporter = dialog.get_value("transporter");
    const { message: response } = await frappe.db.get_value(
        "Supplier",
        transporter,
        "gst_transporter_id"
    );

    dialog.set_value("gst_transporter_id", response.gst_transporter_id);
}

function update_generation_dialog(dialog) {
    const dialog_values = dialog.get_values(true);
    const primary_action_label = get_primary_action_label_for_generation(dialog_values);

    dialog.set_df_property(
        "gst_transporter_id",
        "reqd",
        primary_action_label.includes("Part A") ? 1 : 0
    );

    set_primary_action_label(dialog, primary_action_label);
}

function get_primary_action_label_for_generation(doc) {
    const label = india_compliance.is_api_enabled() ? __("Generate") : __("Download JSON");

    if (are_transport_details_available(doc)) {
        return label;
    }

    return label + " (Part A)";
}

function are_transport_details_available(doc) {
    return (
        (doc.mode_of_transport == "Road" && doc.vehicle_no) ||
        (["Air", "Rail"].includes(doc.mode_of_transport) && doc.lr_no) ||
        (doc.mode_of_transport == "Ship" && doc.lr_no && doc.vehicle_no)
    );
}

function update_vehicle_type(dialog) {
    dialog.set_value("gst_vehicle_type", get_vehicle_type(dialog.get_values(true)));
}

function get_vehicle_type(doc) {
    if (doc.mode_of_transport == "Road") return "Regular";
    if (doc.mode_of_transport == "Ship") return "Over Dimensional Cargo (ODC)";
    return "";
}

/********
 * Utils
 *******/

function trigger_file_download(file_content, file_name) {
    let type = "application/json;charset=utf-8";

    if (!file_name.endsWith(".json")) {
        type = "application/octet-stream";
    }

    const blob = new Blob([file_content], { type: type });

    // Create a link and set the URL using `createObjectURL`
    const link = document.createElement("a");
    link.style.display = "none";
    link.href = URL.createObjectURL(blob);
    link.download = file_name;

    // It needs to be added to the DOM so it can be clicked
    document.body.appendChild(link);
    link.click();

    // To make this work on Firefox we need to wait
    // a little while before removing it.
    setTimeout(() => {
        URL.revokeObjectURL(link.href);
        link.parentNode.removeChild(link);
    }, 0);
}

function get_e_waybill_file_name(docname) {
    let prefix = "Bulk";
    if (docname) {
        prefix = docname.replaceAll(/[^\w_.)( -]/g, "");
    }

    return `${prefix}_e-Waybill_Data_${frappe.utils.get_random(5)}.json`;
}

function set_primary_action_label(dialog, primary_action_label) {
    dialog.get_primary_btn().removeClass("hide").html(primary_action_label);
}
