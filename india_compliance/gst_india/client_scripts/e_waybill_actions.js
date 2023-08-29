function setup_e_waybill_actions(doctype) {
    if (!gst_settings.enable_e_waybill) return;

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
            if (frm.doc.__onload?.e_waybill_info?.is_generated_in_sandbox_mode)
                frm.get_field("ewaybill").set_description("Generated in Sandbox Mode");

            if (
                frm.doc.docstatus != 1 ||
                frm.is_dirty() ||
                !is_e_waybill_applicable(frm)
            )
                return;

            if (!frm.doc.ewaybill) {
                if (frappe.perm.has_perm(frm.doctype, 0, "submit", frm.doc.name)) {
                    frm.add_custom_button(
                        __("Generate"),
                        () => show_generate_e_waybill_dialog(frm),
                        "e-Waybill"
                    );

                    frm.add_custom_button(
                        __("Fetch if Generated"),
                        () => show_fetch_if_generated_dialog(frm),
                        "e-Waybill"
                    );
                    frm.add_custom_button(
                        __("Mark as Generated"),
                        () => show_mark_e_waybill_as_generated_dialog(frm),
                        "e-Waybill"
                    );
                }

                if (frm.doc.e_waybill_status === "Pending") {
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

            if (!india_compliance.is_api_enabled()) {
                return;
            }

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
                frappe.perm.has_perm(frm.doctype, 0, "submit", frm.doc.name) &&
                can_extend_e_waybill(frm)
            ) {
                frm.add_custom_button(
                    __("Extend Validity"),
                    () => show_extend_validity_dialog(frm),
                    "e-Waybill"
                );
            }

            if (frappe.perm.has_perm(frm.doctype, 0, "cancel", frm.doc.name)) {
                frm.add_custom_button(
                    __("Mark as Cancelled"),
                    () => show_mark_e_waybill_as_cancelled_dialog(frm),
                    "e-Waybill"
                );

                if (is_e_waybill_cancellable(frm)) {
                    frm.add_custom_button(
                        __("Cancel"),
                        () => show_cancel_e_waybill_dialog(frm),
                        "e-Waybill"
                    );
                }
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
                frm.doctype != "Sales Invoice" ||
                !has_e_waybill_threshold_met(frm) ||
                frm.doc.ewaybill ||
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
            if (!india_compliance.is_api_enabled() || frm.doc.irn || !frm.doc.ewaybill)
                return;

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
            callback: () => {
                return frm.refresh();
            },
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

    const api_enabled = india_compliance.is_api_enabled();

    const d = get_generate_e_waybill_dialog({
        title: __("Generate e-Waybill"),
        primary_action_label: get_primary_action_label_for_generation(frm.doc),
        primary_action(values) {
            d.hide();
            if (api_enabled) {
                generate_action(values);
            } else {
                json_action(values);
            }
        },
        secondary_action_label: api_enabled && frm.doc.doctype ? __("Download JSON") : null,
        secondary_action: api_enabled
            ? () => {
                d.hide();
                json_action(d.get_values());
            }
            : null,
    }, frm);

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

function get_generate_e_waybill_dialog(opts, frm) {
    if (!frm) frm = { doc: {} };
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
            onchange: () => update_gst_tranporter_id(d, frm.doc),
        },
        {
            label: "Distance (in km)",
            fieldname: "distance",
            fieldtype: "Float",
            default: frm.doc.distance || 0,
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
                frm.doc.gst_transporter_id?.length == 15
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
            onchange: () => update_generation_dialog(d, frm.doc),
        },
        {
            label: "Transport Receipt No",
            fieldname: "lr_no",
            fieldtype: "Data",
            default: frm.doc.lr_no,
            onchange: () => update_generation_dialog(d, frm.doc),
        },
        {
            label: "Transport Receipt Date",
            fieldname: "lr_date",
            fieldtype: "Date",
            default: frm.doc.lr_date || "Today",
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
            default: frm.doc.mode_of_transport || "Road",
            onchange: () => {
                update_generation_dialog(d, frm.doc);
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
            default: frm.doc.gst_vehicle_type || "Regular",
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

    const is_foreign_transaction =
        frm.doc.gst_category === "Overseas" &&
        frm.doc.place_of_supply === "96-Other Countries";

    if (frm.doctype === "Sales Invoice" && is_foreign_transaction) {
        fields.splice(5, 0, {
            label: "Origin Port / Border Checkpost Address",
            fieldname: "port_address",
            fieldtype: "Link",
            options: "Address",
            default: frm.doc.port_address,
            reqd: frm.doc?.__onload?.shipping_address_in_india != true,
            get_query: () => {
                return {
                    filters: {
                        country: "India",
                    },
                };
            },
        });
    }

    opts.fields = fields;
    const d = new frappe.ui.Dialog(opts);

    return d;
}

function show_fetch_if_generated_dialog(frm) {
    const d = new frappe.ui.Dialog({
        title: __("Fetch e-Waybill"),
        fields: [
            {
                label: "e-Waybill Date",
                fieldname: "e_waybill_date",
                fieldtype: "Date",
                default: frappe.datetime.get_today(),
                description: __(
                    "Retrieve the e-Waybill that was already generated for this invoice on the specified date."
                ),
            },
        ],
        primary_action_label: __("Fetch"),
        primary_action(values) {
            frappe.call({
                method: "india_compliance.gst_india.utils.e_waybill.find_matching_e_waybill",
                args: {
                    doctype: frm.doctype,
                    docname: frm.doc.name,
                    e_waybill_date: values.e_waybill_date,
                },
                callback: () => frm.refresh(),
            });
            d.hide();
        },
    });

    d.show();
}
function show_mark_e_waybill_as_generated_dialog(frm) {
    const d = new frappe.ui.Dialog({
        title: __("Update e-Waybill Details"),
        fields: [
            {
                label: "e-Waybill Number",
                fieldname: "ewaybill",
                fieldtype: "Data",
                reqd: 1,
            },
            {
                label: "e-Waybill Date",
                fieldname: "e_waybill_date",
                fieldtype: "Datetime",
                reqd: 1,
            },
            {
                label: "Valid Upto",
                fieldname: "valid_upto",
                fieldtype: "Datetime",
                reqd: 1,
            },
        ],
        primary_action_label: __("Update"),
        primary_action(values) {
            frappe.call({
                method: "india_compliance.gst_india.utils.e_waybill.mark_e_waybill_as_generated",
                args: {
                    doctype: frm.doctype,
                    docname: frm.doc.name,
                    values,
                },
                callback: () => {
                    d.hide();
                    frm.refresh();
                },
            });
        },
    });

    d.show();
}

function show_cancel_e_waybill_dialog(frm, callback) {
    const d = new frappe.ui.Dialog({
        title: __("Cancel e-Waybill"),
        fields: get_cancel_e_waybill_dialog_fields(frm),
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

function show_mark_e_waybill_as_cancelled_dialog(frm) {
    fields = get_cancel_e_waybill_dialog_fields(frm);
    fields.push({
        label: "Cancelled On",
        fieldname: "cancelled_on",
        fieldtype: "Datetime",
        reqd: 1,
        default: frappe.datetime.now_datetime(),
    });

    const d = new frappe.ui.Dialog({
        title: __("Update Cancelled e-Waybill Details"),
        fields: fields,
        primary_action_label: __("Update"),
        primary_action(values) {
            frappe.call({
                method: "india_compliance.gst_india.utils.e_waybill.mark_e_waybill_as_cancelled",
                args: {
                    doctype: frm.doctype,
                    docname: frm.doc.name,
                    values,
                },
                callback: () => {
                    d.hide();
                    frm.refresh();
                },
            });
        },
    });

    d.show();
}

function get_cancel_e_waybill_dialog_fields(frm) {
    return [
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
            options: ["Duplicate", "Order Cancelled", "Data Entry Mistake", "Others"],
        },
        {
            label: "Remark",
            fieldname: "remark",
            fieldtype: "Data",
            mandatory_depends_on: "eval: doc.reason == 'Others'",
        },
    ];
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

async function show_extend_validity_dialog(frm) {
    const destination_address = await frappe.db.get_doc(
        "Address",
        get_destination_address_name(frm)
    );
    const is_in_movement = "eval: doc.consignment_status === 'In Movement'";
    const is_in_transit = "eval: doc.consignment_status === 'In Transit'";

    const d = new frappe.ui.Dialog({
        title: __("Extend Validity"),
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
                mandatory_depends_on: "eval: doc.mode_of_transport === 'Road'",
            },
            {
                label: "Remaining Distance (in km)",
                fieldname: "remaining_distance",
                fieldtype: "Float",
                default: frm.doc.distance,
            },
            {
                fieldtype: "Column Break",
            },
            {
                label: "Consignment Status",
                fieldname: "consignment_status",
                fieldtype: "Select",
                options: `In Movement\nIn Transit`,
                default: "In Movement",
                reqd: 1,
                onchange: () => update_transit_type(d),
            },
            {
                label: "Mode Of Transport",
                fieldname: "mode_of_transport",
                fieldtype: "Select",
                options: `\nRoad\nAir\nRail\nShip`,
                default: frm.doc.mode_of_transport,
                depends_on: is_in_movement,
                mandatory_depends_on: is_in_movement,
                onchange: () => update_transit_type(d),
            },
            {
                label: "Transit Type",
                fieldname: "transit_type",
                fieldtype: "Select",
                options: `\nRoad\nWarehouse\nOthers`,
                depends_on: is_in_transit,
                mandatory_depends_on: is_in_transit,
            },
            {
                label: "Transport Receipt No",
                fieldname: "lr_no",
                fieldtype: "Data",
                default: frm.doc.lr_no,
                depends_on: is_in_movement,
                mandatory_depends_on:
                    "eval: ['Rail', 'Air', 'Ship'].includes(doc.mode_of_transport) && doc.consignment_status === 'In Movement'",
            },
            {
                fieldtype: "Section Break",
            },
            {
                label: "Address Line1",
                fieldname: "address_line1",
                fieldtype: "Data",
                default: destination_address.address_line1,
                depends_on: is_in_transit,
                mandatory_depends_on: is_in_transit,
            },
            {
                label: "Address Line2",
                fieldname: "address_line2",
                fieldtype: "Data",
                default: destination_address.address_line2,
                depends_on: is_in_transit,
                mandatory_depends_on: is_in_transit,
            },
            {
                label: "Address Line3",
                fieldname: "address_line3",
                fieldtype: "Data",
                default: destination_address.city,
                depends_on: is_in_transit,
                mandatory_depends_on: is_in_transit,
            },
            {
                fieldtype: "Column Break",
            },
            {
                label: "Current Place",
                fieldname: "current_place",
                fieldtype: "Data",
                reqd: 1,
                default: destination_address.city,
            },
            {
                label: "Current Pincode",
                fieldname: "current_pincode",
                fieldtype: "Data",
                reqd: 1,
                default: destination_address.pincode,
            },
            {
                label: "Current State",
                fieldname: "current_state",
                fieldtype: "Autocomplete",
                options: frappe.boot.india_state_options.join("\n"),
                reqd: 1,
                default: destination_address.state,
            },
            {
                fieldtype: "Section Break",
            },
            {
                fieldname: "reason",
                label: "Reason",
                fieldtype: "Select",
                options: [
                    "Natural Calamity",
                    "Law and Order Situation",
                    "Transshipment",
                    "Accident",
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
                mandatory_depends_on: 'eval: doc.reason === "Others"',
            },
        ],
        primary_action_label: __("Extend"),
        primary_action(values) {
            frappe.call({
                method: "india_compliance.gst_india.utils.e_waybill.extend_validity",
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
    if (Math.abs(frm.doc.base_grand_total) >= gst_settings.e_waybill_threshold)
        return true;
}

function is_e_waybill_applicable(frm) {
    if (
        // means company is Indian and not Unregistered
        !frm.doc.company_gstin ||
        !gst_settings.enable_e_waybill ||
        !(
            is_e_waybill_applicable_on_sales_invoice(frm) ||
            is_e_waybill_applicable_on_purchase_invoice(frm) ||
            is_e_waybill_applicable_on_delivery_note(frm)
        )
    )
        return;

    // at least one item is not a service
    for (const item of frm.doc.items) {
        if (item.gst_hsn_code && !item.gst_hsn_code.startsWith("99") && item.qty !== 0)
            return true;
    }
}

function can_extend_e_waybill(frm) {
    function get_hours(date, hours) {
        return moment(date).add(hours, "hours").format(frappe.defaultDatetimeFormat);
    }

    const valid_upto = frm.doc.__onload?.e_waybill_info?.valid_upto;
    const extend_after = get_hours(valid_upto, -8);
    const extend_before = get_hours(valid_upto, 8);
    const now = frappe.datetime.now_datetime();

    if (
        extend_after < now &&
        now < extend_before &&
        frm.doc.gst_transporter_id != frm.doc.company_gstin
    )
        return true;

    return false;
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

function is_e_waybill_applicable_on_sales_invoice(frm) {
    return (
        frm.doctype == "Sales Invoice" &&
        frm.doc.company_gstin !== frm.doc.billing_address_gstin &&
        frm.doc.customer_address &&
        !frm.doc.is_return &&
        !frm.doc.is_debit_note
    );
}

function is_e_waybill_applicable_on_delivery_note(frm) {
    return (
        frm.doctype == "Delivery Note" &&
        frm.doc.customer_address &&
        gst_settings.enable_e_waybill_from_dn
    );
}

function is_e_waybill_applicable_on_purchase_invoice(frm) {
    return (
        frm.doctype == "Purchase Invoice" &&
        frm.doc.supplier_address &&
        frm.doc.company_gstin !== frm.doc.supplier_gstin &&
        gst_settings.enable_e_waybill_from_pi
    );
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

function update_generation_dialog(dialog, doc) {
    const dialog_values = dialog.get_values(true);
    const primary_action_label = get_primary_action_label_for_generation(dialog_values);

    dialog.set_df_property(
        "gst_transporter_id",
        "reqd",
        primary_action_label.includes("Part A") ? 1 : 0
    );

    if (is_empty(doc)) return;

    set_primary_action_label(dialog, primary_action_label);
}

function get_primary_action_label_for_generation(doc) {
    const label = india_compliance.is_api_enabled()
        ? __("Generate")
        : __("Download JSON");

    if (are_transport_details_available(doc)) {
        return label;
    }

    return label + " (Part A)";
}

function is_empty(obj) {
    for (let prop in obj) {
        if (obj.hasOwnProperty(prop)) {
            return false;
        }
    }
    return true;
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

function update_transit_type(dialog) {
    dialog.set_value("transit_type", get_transit_type(dialog.get_values(true)));
}

function get_transit_type(dialog) {
    if (dialog.consignment_status === "In Movement") return "";
    if (dialog.consignment_status === "In Transit") {
        if (dialog.mode_of_transport === "Road") return "Road";
        else return "Others";
    }
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

function get_destination_address_name(frm) {
    if (frm.doc.doctype == "Purchase Invoice") {
        if (frm.doc.is_return) return frm.doc.supplier_address;
        return frm.doc.shipping_address_name || frm.doc.billing_address;
    } else {
        if (frm.doc.is_return)
            return frm.doc.dispatch_address_name || frm.doc.company_address;
        return frm.doc.shipping_address_name || frm.doc.customer_address;
    }
}
