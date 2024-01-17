{% include "india_compliance/gst_india/client_scripts/e_waybill_applicability.js" %}

const E_WAYBILL_CLASS = {
    "Sales Invoice": SalesInvoiceEwaybill,
    "Purchase Invoice": PurchaseInvoiceEwaybill,
    "Delivery Note": DeliveryNoteEwaybill,
    "Purchase Receipt": PurchaseReceiptEwaybill,
};

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
                frm.doc.e_waybill_status === "Not Applicable" ||
                !is_e_waybill_applicable(frm)
            )
                return;

            if (!frm.doc.ewaybill) {
                if (frm.doc.e_waybill_status === "Pending") {
                    frm.dashboard.add_comment(
                        __(
                            "e-Waybill is applicable for this invoice, but not yet generated or updated."
                        ),
                        "yellow",
                        true
                    );
                }

                if (frappe.perm.has_perm(frm.doctype, 0, "submit", frm.doc.name)) {
                    frm.add_custom_button(
                        __("Generate"),
                        () => show_generate_e_waybill_dialog(frm),
                        "e-Waybill"
                    );

                    frm.add_custom_button(
                        __("Mark as Generated"),
                        () => show_mark_e_waybill_as_generated_dialog(frm),
                        "e-Waybill"
                    );

                    if (!india_compliance.is_api_enabled()) return;

                    frm.add_custom_button(
                        __("Fetch if Generated"),
                        () => show_fetch_if_generated_dialog(frm),
                        "e-Waybill"
                    );
                }

                return;
            }

            if (!india_compliance.is_api_enabled()) {
                if (frappe.perm.has_perm(frm.doctype, 0, "cancel", frm.doc.name)) {
                    frm.add_custom_button(
                        __("Mark as Cancelled"),
                        () => show_mark_e_waybill_as_cancelled_dialog(frm),
                        "e-Waybill"
                    );
                }
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
                !has_extend_validity_expired(frm)
            ) {
                const can_extend = can_extend_e_waybill(frm);
                let btn = frm.add_custom_button(
                    __("Extend Validity"),
                    can_extend ? () => show_extend_validity_dialog(frm) : null,
                    "e-Waybill"
                );
                if (!can_extend) {
                    btn.addClass("disabled");
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

            if (frappe.perm.has_perm(frm.doctype, 0, "cancel", frm.doc.name)) {
                if (is_e_waybill_cancellable(frm)) {
                    india_compliance.add_divider_to_btn_group("e-Waybill");

                    frm.add_custom_button(
                        __("Cancel"),
                        () => show_cancel_e_waybill_dialog(frm),
                        "e-Waybill"
                    );

                    india_compliance.make_text_red("e-Waybill", "Cancel");
                }

                frm.add_custom_button(
                    __("Mark as Cancelled"),
                    () => show_mark_e_waybill_as_cancelled_dialog(frm),
                    "e-Waybill"
                );

                india_compliance.make_text_red("e-Waybill", "Mark as Cancelled");
            }
        },
        async on_submit(frm) {
            if (!auto_generate_e_waybill(frm)) return;

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
    india_compliance.validate_invoice_number(frm.doc.name);
    const generate_action = values => {
        frappe.call({
            method: "india_compliance.gst_india.utils.e_waybill.generate_e_waybill",
            args: {
                doctype: frm.doctype,
                docname: frm.doc.name,
                values: values,
                force: true,
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
        india_compliance.trigger_file_download(
            ewb_data,
            get_e_waybill_file_name(frm.doc.name)
        );
    };

    const api_enabled = india_compliance.is_api_enabled();

    const d = get_generate_e_waybill_dialog(
        {
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
            secondary_action_label:
                api_enabled && frm.doc.doctype ? __("Download JSON") : null,
            secondary_action: api_enabled
                ? () => {
                    d.hide();
                    json_action(d.get_values());
                }
                : null,
        },
        frm
    );

    d.show();

    //Alert if E-waybill cannot be generated using api
    if (!is_e_waybill_generatable(frm)) {
        const address = frm.doc.customer_address || frm.doc.supplier_address;
        const reason = !address
            ? "<strong>party address</strong> is missing."
            : "party <strong>GSTIN is same</strong> as company GSTIN.";
        $(`
            <div class="alert alert-warning" role="alert">
                e-Waybill cannot be generated as ${reason}
            </div>
        `).prependTo(d.wrapper);
        d.disable_primary_action();
    }

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
            onchange: () => update_gst_tranporter_id(d),
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

    india_compliance.primary_to_danger_btn(d);
    d.show();
}

function show_mark_e_waybill_as_cancelled_dialog(frm) {
    const fields = get_cancel_e_waybill_dialog_fields(frm);
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

async function show_update_vehicle_info_dialog(frm) {
    const source_address = await get_source_destination_address(frm, "source_address");
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
                label: "Place of Change",
                fieldname: "place_of_change",
                fieldtype: "Data",
                reqd: 1,
                default: source_address.city,
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
                label: "State",
                fieldname: "state",
                fieldtype: "Autocomplete",
                options: frappe.boot.india_state_options.join("\n"),
                reqd: 1,
                default: source_address.state,
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
    const { valid_upto, extension_scheduled } = frm.doc.__onload?.e_waybill_info || {};
    if (!valid_upto) return;

    const scheduled_time = get_hours(valid_upto, 1, "DD-MM-YYYY HH:mm A");
    const can_extend_now = can_extend_e_waybill_now(valid_upto);
    const destination_address = await get_source_destination_address(
        frm,
        "destination_address"
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
                reqd: 1,
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
                label: "Transport Receipt Date",
                fieldname: "lr_date",
                fieldtype: "Date",
                default: frm.doc.lr_date || "Today",
                mandatory_depends_on: "eval:doc.lr_no",
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
    if (!can_extend_now) {
        d.get_primary_btn().addClass("disabled");
        d.set_secondary_action(() =>
            schedule_e_waybill_extension(frm, d, scheduled_time)
        );
        d.set_secondary_action_label(__("Schedule"));
    }
    if (extension_scheduled) {
        display_extension_scheduled_message(d, scheduled_time);
        prefill_data_from_e_waybill_log(frm, d);
    }
    d.show();
}

function schedule_e_waybill_extension(frm, dialog, scheduled_time) {
    const values = dialog.get_values();
    if (values) {
        frappe.call({
            method: "india_compliance.gst_india.utils.e_waybill.schedule_ewaybill_for_extension",
            args: {
                doctype: frm.doctype,
                docname: frm.docname,
                values,
                scheduled_time,
            },
            callback: () => {
                if (frm.doc.__onload?.e_waybill_info) {
                    frm.doc.__onload.e_waybill_info.extension_scheduled = 1;
                }
            },
        });
    }
    dialog.hide();
}

function display_extension_scheduled_message(dialog, scheduled_time) {
    const message = `<div>Already scheduled for ${scheduled_time}</div>`;
    $(message).prependTo(dialog.footer);
}

function prefill_data_from_e_waybill_log(frm, dialog) {
    frappe.db
        .get_value("e-Waybill Log", frm.doc.ewaybill, ["extension_data"])
        .then(response => {
            const values = response.message;
            const extension_data = JSON.parse(values.extension_data);

            dialog.set_values(extension_data);
        });
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
    return new E_WAYBILL_CLASS[frm.doctype](frm).is_e_waybill_applicable();
}

function is_e_waybill_generatable(frm) {
    return new E_WAYBILL_CLASS[frm.doctype](frm).is_e_waybill_generatable();
}

function auto_generate_e_waybill(frm) {
    return new E_WAYBILL_CLASS[frm.doctype](frm).auto_generate_e_waybill();
}

function can_extend_e_waybill(frm) {
    if (frm.doc.gst_transporter_id != frm.doc.company_gstin) return true;
    return false;
}

function get_hours(date, hours, date_time_format = frappe.defaultDatetimeFormat) {
    return moment(date).add(hours, "hours").format(date_time_format);
}

function can_extend_e_waybill_now(valid_upto) {
    const extend_after = get_hours(valid_upto, -8);
    const extend_before = get_hours(valid_upto, 8);
    const now = frappe.datetime.now_datetime();

    if (extend_after < now && now < extend_before) return true;
    return false;
}

function has_extend_validity_expired(frm) {
    const valid_upto = frm.doc.__onload?.e_waybill_info?.valid_upto;
    const extend_before = get_hours(valid_upto, 8);
    const now = frappe.datetime.now_datetime();

    if (now > extend_before) return true;
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

async function get_source_destination_address(frm, address_type) {
    let address = await frappe.call({
        method: "india_compliance.gst_india.utils.e_waybill.get_source_destination_address",
        args: {
            doctype: frm.doctype,
            docname: frm.docname,
            address_type: address_type,
        },
    });

    return address?.message;
}

function show_sandbox_mode_indicator() {
    $(document).find(".form-sidebar .ic-sandbox-mode").remove();

    if (!gst_settings.sandbox_mode) return;

    $(document)
        .find(".form-sidebar .sidebar-image-section")
        .after(
            `
            <div class="sidebar-menu ic-sandbox-mode">
                <p><label class="indicator-pill no-indicator-dot yellow" title="${__(
                    "Your site has enabled Sandbox Mode in GST Settings."
                )}">${__("Sandbox Mode")}</label></p>
                <p><a class="small text-muted" href="/app/gst-settings" target="_blank">${__(
                    "Sandbox Mode is enabled for GST APIs."
                )}</a></p>
            </div>
            `
        );
}
