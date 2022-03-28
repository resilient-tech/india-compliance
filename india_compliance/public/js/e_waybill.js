function e_waybill_actions(doctype) {
    frappe.ui.form.on(doctype, {
        setup(frm) {
            frappe.realtime.on("e_waybill_generated", function (data) {
                if (
                    data.docname != frm.doc.name ||
                    data.doctype != doctype ||
                    !data.alert
                )
                    return;

                frappe.show_alert({
                    message: data.alert,
                    indicator: "yellow",
                });
            });
        },
        refresh(frm) {
            let settings = frappe.boot.gst_settings;
            if (
                !settings.enable_api ||
                !frappe.perm.has_perm(frm.doctype, 0, "submit", frm.doc.name) ||
                !is_e_waybill_applicable(frm, settings.e_waybill_criteria)
            )
                return;

            if (!frm.doc.ewaybill && frm.doc.docstatus == 1) {
                frm.add_custom_button(
                    "Generate",
                    () => {
                        dialog_generate_e_waybill(frm);
                    },
                    "e-Waybill"
                );
            }
            const now = frappe.datetime.now_datetime(true);

            if (
                frm.doc.docstatus == 1 &&
                frm.doc.ewaybill &&
                frm.doc.e_waybill_validity &&
                get_date(frm.doc.e_waybill_validity) > now
            ) {
                frm.add_custom_button(
                    "Update Vehicle Info",
                    () => {
                        dialog_update_vehicle_info(frm);
                    },
                    "e-Waybill"
                );
                frm.add_custom_button(
                    "Update Transporter",
                    () => {
                        dialog_update_transporter(frm);
                    },
                    "e-Waybill"
                );
                frm.add_custom_button(
                    "Cancel",
                    () => {
                        dialog_cancel_e_waybill(frm);
                    },
                    "e-Waybill"
                );
                // add other buttons
            }
            if (frm.doc.docstatus == 1 && frm.doc.ewaybill) {
                frm.add_custom_button(
                    "Print",
                    () => {
                        attach_or_print_e_waybill(frm, "print");
                    },
                    "e-Waybill"
                );
                frm.add_custom_button(
                    "Attach",
                    () => {
                        attach_or_print_e_waybill(frm, "attach");
                    },
                    "e-Waybill"
                );
            }
        },
    });
}
function attach_or_print_e_waybill(frm, action) {
    frappe.call({
        method: "india_compliance.gst_india.utils.e_waybill.attach_or_print_e_waybill",
        args: {
            doc: frm.doc,
            action: action,
        },
        callback: function () {
            if (action == "print"){
                frappe.set_route("print", "e-waybill-log", frm.doc.ewaybill);
                return;
            }
            frm.reload_doc();
            if (action == "attach") {
                frappe.msgprint(
                    __("e-Waybill generated successfully and attached here.")
                );
            }
        },
    });
}

function dialog_generate_e_waybill(frm) {
    let d = new frappe.ui.Dialog({
        title: "Verify Details",
        fields: [
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
                onchange: function () {
                    get_gst_tranporter_id(d);
                },
            },
            {
                label: "GST Transporter ID",
                fieldname: "gst_transporter_id",
                fieldtype: "Data",
                fetch_from: "transporter.gst_transporter_id",
                default:
                    frm.doc.gst_transporter_id &&
                    frm.doc.gst_transporter_id.length == 15
                        ? frm.doc.gst_transporter_id
                        : "",
            },
            {
                label: "Vehicle No",
                fieldname: "vehicle_no",
                fieldtype: "Data",
                default: frm.doc.vehicle_no,
            },
            {
                label: "Distance (in km)",
                fieldname: "distance",
                fieldtype: "Float",
                default: frm.doc.distance,
            },
            {
                fieldtype: "Column Break",
            },
            {
                label: "Transport Receipt No",
                fieldname: "lr_no",
                fieldtype: "Data",
                default: frm.doc.lr_no,
            },
            {
                label: "Transport Receipt Date",
                fieldname: "lr_date",
                fieldtype: "Date",
                default: frm.doc.lr_date,
            },
            {
                label: "Mode Of Transport",
                fieldname: "mode_of_transport",
                fieldtype: "Select",
                options: `\nRoad\nAir\nRail\nShip`,
                default: frm.doc.mode_of_transport,
            },
            {
                label: "GST Vehicle Type",
                fieldname: "gst_vehicle_type",
                fieldtype: "Select",
                options: `Regular\nOver Dimensional Cargo (ODC)`,
                depends_on: 'eval:(doc.mode_of_transport === "Road")',
                default: frm.doc.gst_vehicle_type,
            },
            {
                fieldtype: "Section Break",
            },
            {
                fieldname: "gst_category",
                label: "GST Category",
                fieldtype: "Select",
                options:
                    "\nRegistered Regular\nRegistered Composition\nUnregistered\nSEZ\nOverseas\nConsumer\nDeemed Export\nUIN Holders",
                fetch_from: "customer_address.gst_category",
                fetch_if_empty: 1,
                default: frm.doc.gst_category,
            },
            {
                fieldtype: "Column Break",
            },
            {
                fieldname: "export_type",
                label: "Export Type",
                fieldtype: "Select",
                depends_on:
                    'eval:in_list(["SEZ", "Overseas", "Deemed Export"], doc.gst_category)',
                options: "\nWith Payment of Tax\nWithout Payment of Tax",
                fetch_from: "customer_address.export_type",
                fetch_if_empty: 1,
                default: frm.doc.export_type,
            },
        ],
        primary_action_label: "Generate",
        primary_action(values) {
            frappe.call({
                method: "india_compliance.gst_india.utils.e_waybill.generate_e_waybill",
                args: {
                    doctype: frm.doc.doctype,
                    docname: frm.doc.name,
                    dialog: values,
                },
                callback: function () {
                    frm.reload_doc();
                },
            });
            d.hide();
        },
    });

    d.show();
}

function dialog_cancel_e_waybill(frm) {
    let d = new frappe.ui.Dialog({
        title: "Are you sure you would like to cancel Ewaybill",
        fields: [
            {
                label: "Ewaybill",
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
                default: "3-Data Entry Error",
                options: [
                    "1-Duplicate",
                    "2-Order Cancelled",
                    "3-Data Entry Error",
                    "4-Others",
                ],
            },
            {
                label: "Remark",
                fieldname: "remark",
                fieldtype: "Data",
                mandatory_depends_on: "eval: doc.reason == '4-Others'",
            },
        ],
        primary_action_label: "Cancel Ewaybill",
        primary_action(values) {
            frappe.call({
                method: "india_compliance.gst_india.utils.e_waybill.cancel_e_waybill",
                args: {
                    doc: frm.doc,
                    dialog: values,
                },
                callback: function () {
                    frm.reload_doc();
                    frappe.msgprint(__("E-waybill Cancelled Successfully."));
                },
            });
            d.hide();
        },
    });

    d.show();
}

function dialog_update_vehicle_info(frm) {
    let d = new frappe.ui.Dialog({
        title: "Update Vehicle Information",
        fields: [
            {
                label: "Ewaybill",
                fieldname: "ewaybill",
                fieldtype: "Data",
                read_only: 1,
                default: frm.doc.ewaybill,
            },
            {
                label: "Vehicle No",
                fieldname: "vehicle_no",
                fieldtype: "Data",
                reqd: 1,
                default: frm.doc.vehicle_no,
            },
            {
                label: "Transport Receipt No",
                fieldname: "lr_no",
                fieldtype: "Data",
                default: frm.doc.lr_no,
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
            },
            {
                label: "GST Vehicle Type",
                fieldname: "gst_vehicle_type",
                fieldtype: "Select",
                options: `Regular\nOver Dimensional Cargo (ODC)`,
                depends_on: 'eval:(doc.mode_of_transport === "Road")',
                default: frm.doc.gst_vehicle_type,
            },
            {
                label: "Transport Receipt Date",
                fieldname: "lr_date",
                fieldtype: "Date",
                default: frm.doc.lr_date,
            },
            {
                fieldtype: "Section Break",
            },
            {
                fieldname: "reason",
                label: "Reason",
                fieldtype: "Select",
                options: [
                    "1-Due to Break Down",
                    "2-Due to Trans Shipment",
                    "3-Others",
                    "4-First Time",
                ],
                reqd: 1,
            },
            {
                label: "Update e-Waybill Print/Data",
                fieldname: "update_e_waybill_data",
                fieldtype: "Check",
                default:
                    frappe.boot.gst_settings.get_data_for_print == 1 ? 1 : 0,
            },
            {
                fieldtype: "Column Break",
            },
            {
                fieldname: "remark",
                label: "Remark",
                fieldtype: "Data",
                mandatory_depends_on: 'eval: doc.reason == "3-Others"',
            },
        ],
        primary_action_label: "Update Vehicle Info",
        primary_action(values) {
            frappe.call({
                method: "india_compliance.gst_india.utils.e_waybill.update_vehicle_info",
                args: {
                    doc: frm.doc,
                    dialog: values,
                },
                callback: function () {
                    frm.reload_doc();
                    frappe.msgprint(
                        __("Vehicle Information Updated Successfully.")
                    );
                },
            });
            d.hide();
        },
    });

    d.show();
}

function dialog_update_transporter(frm) {
    let d = new frappe.ui.Dialog({
        title: "Update Transporter",
        fields: [
            {
                label: "Ewaybill",
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
                onchange: function () {
                    get_gst_tranporter_id(d);
                },
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
                default: frappe.boot.gst_settings.get_data_for_print || 0,
            },
        ],
        primary_action_label: "Update Transporter",
        primary_action(values) {
            frappe.call({
                method: "india_compliance.gst_india.utils.e_waybill.update_transporter",
                args: {
                    doc: frm.doc,
                    dialog: values,
                },
                callback: function () {
                    frm.reload_doc();
                    frappe.msgprint(__("Transporter Updated Successfully."));
                },
            });
            d.hide();
        },
    });

    d.show();
}

async function get_gst_tranporter_id(d) {
    const transporter = d.fields_dict.transporter.value;
    const { message: r } = await frappe.db.get_value(
        "Supplier",
        transporter,
        "gst_transporter_id"
    );
    d.set_value("gst_transporter_id", r.gst_transporter_id);
}

function get_date(text) {
  return moment(text, frappe.datetime.get_user_date_fmt() + " " + frappe.datetime.get_user_time_fmt())._d;
}

Date.prototype.addHours = function (h) {
    this.setTime(this.getTime() + h * 60 * 60 * 1000);
    return this;
};

function is_e_waybill_applicable(frm, e_waybill_criteria) {
    if (frm.doc.base_grand_total < e_waybill_criteria) return false;
    for (let item of frm.doc.items) {
        if (!item.gst_hsn_code.startsWith("99")) return true;
    }
    return false;
}
