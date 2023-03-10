const GSTIN_FIELD_DESCRIPTION = __(
    "Autofill party information by entering their GSTIN"
);

class GSTQuickEntryForm extends frappe.ui.form.QuickEntryForm {
    constructor(...args) {
        super(...args);
        this.skip_redirect_on_error = true;
        this.api_enabled = india_compliance.is_api_enabled() && gst_settings.autofill_party_info;
    }

    render_dialog() {
        super.render_dialog();
        india_compliance.set_state_options(this.dialog);
    }

    get_address_fields() {
        return [
            {
                label: __("Primary Address Details"),
                fieldname: "primary_address_section",
                fieldtype: "Section Break",
                description: this.api_enabled
                    ? __(
                          `When you enter a GSTIN, the permanent address linked to it is
                        auto-filled by default.<br>
                        Change the Pincode to autofill other addresses.`
                      )
                    : "",
                collapsible: 0,
            },
            {
                label: __("Pincode"),
                // set as _pincode so that frappe.ui.form.Layout doesn't override it
                fieldname: "_pincode",
                fieldtype: "Autocomplete",
                ignore_validation: true,
            },
            {
                label: __("Address Line 1"),
                fieldname: "address_line1",
                fieldtype: "Data",
            },
            {
                label: __("Address Line 2"),
                fieldname: "address_line2",
                fieldtype: "Data",
            },
            {
                fieldtype: "Column Break",
            },
            {
                label: __("City"),
                fieldname: "city",
                fieldtype: "Data",
            },
            {
                label: __("State"),
                fieldname: "state",
                fieldtype: "Autocomplete",
                ignore_validation: true,
            },
            {
                label: __("Country"),
                fieldname: "country",
                fieldtype: "Link",
                options: "Country",
                default: frappe.defaults.get_user_default("country"),
                onchange: () => {
                    india_compliance.set_state_options(this.dialog);
                },
            },
            {
                label: __("Customer POS Id"),
                fieldname: "customer_pos_id",
                fieldtype: "Data",
                hidden: 1,
            },
        ];
    }

    get_gstin_field() {
        return [
            {
                label: "GSTIN",
                fieldname: "_gstin",
                fieldtype: "Autocomplete",
                description: this.api_enabled ? GSTIN_FIELD_DESCRIPTION : "",
                ignore_validation: true,
                onchange: () => {
                    const d = this.dialog;
                    if (this.api_enabled) return autofill_fields(d);

                    d.set_value(
                        "gst_category",
                        india_compliance.guess_gst_category(d.doc._gstin, d.doc.country)
                    );
                },
            },
        ];
    }

    update_doc() {
        const doc = super.update_doc();
        doc.pincode = doc._pincode;
        doc.gstin = doc._gstin;
        return doc;
    }
}

class PartyQuickEntryForm extends GSTQuickEntryForm {
    render_dialog() {
        this.mandatory = [
            ...this.get_gstin_field(),
            ...this.mandatory,
            ...this.get_contact_fields(),
            ...this.get_address_fields(),
        ];
        super.render_dialog();
    }

    get_contact_fields() {
        return [
            {
                label: __("Primary Contact Details"),
                fieldname: "primary_contact_section",
                fieldtype: "Section Break",
                collapsible: 0,
            },
            {
                label: __("Email ID"),
                fieldname: "_email_id",
                fieldtype: "Data",
                options: "Email",
            },
            {
                fieldtype: "Column Break",
            },
            {
                label: __("Mobile Number"),
                fieldname: "_mobile_no",
                fieldtype: "Data",
            },
        ];
    }

    update_doc() {
        const doc = super.update_doc();
        // to prevent clash with ERPNext
        doc._address_line1 = doc.address_line1;
        delete doc.address_line1;

        // these fields were suffixed with _ to prevent them from being read only
        doc.email_id = doc._email_id;
        doc.mobile_no = doc._mobile_no;

        return doc;
    }
}

frappe.ui.form.CustomerQuickEntryForm = PartyQuickEntryForm;
frappe.ui.form.SupplierQuickEntryForm = PartyQuickEntryForm;

class AddressQuickEntryForm extends GSTQuickEntryForm {
    async render_dialog() {
        const address_fields = this.get_address_fields();
        const fields_to_exclude = address_fields.map(({ fieldname }) => fieldname);
        fields_to_exclude.push("pincode", "address_line1");

        this.mandatory = [
            ...this.get_dynamic_link_fields(),
            ...this.get_gstin_field(),
            ...this.mandatory.filter(
                field => !fields_to_exclude.includes(field.fieldname)
            ),
            ...address_fields,
        ];
        super.render_dialog();
        this.set_default_values();
    }

    get_dynamic_link_fields() {
        return [
            {
                fieldname: "link_doctype",
                fieldtype: "Link",
                label: "Link Document Type",
                options: "DocType",
                get_query: () => {
                    return {
                        query: "frappe.contacts.address_and_contact.filter_dynamic_link_doctypes",
                        filters: {
                            fieldtype: "HTML",
                            fieldname: "address_html",
                        },
                    };
                },
                onchange: async () => {
                    const { value, last_value } = this.dialog.get_field("link_doctype");

                    if (value !== last_value) {
                        // await to avoid clash with onchange of link_name field
                        await this.dialog.set_value("link_name", "");
                    }
                },
            },
            {
                fieldtype: "Column Break",
            },
            {
                fieldname: "link_name",
                fieldtype: "Dynamic Link",
                label: "Link Name",
                get_options: df => df.doc.link_doctype,
                onchange: async () => {
                    const { link_doctype, link_name } = this.dialog.doc;

                    if (
                        !link_name ||
                        !in_list(frappe.boot.gst_party_types, link_doctype)
                    )
                        return;

                    const { message: gstin_list } = await frappe.call(
                        "india_compliance.gst_india.utils.get_gstin_list",
                        { party_type: link_doctype, party: link_name }
                    );
                    if (!gstin_list || !gstin_list.length) return;

                    this.dialog.fields_dict._gstin.set_data(gstin_list.join("\n"));
                },
            },
            {
                fieldtype: "Section Break",
            },
        ];
    }

    update_doc() {
        const doc = super.update_doc();
        if (doc.link_doctype && doc.link_name) {
            const link = frappe.model.add_child(doc, "Dynamic Link", "links");
            link.link_doctype = doc.link_doctype;
            link.link_name = doc.link_name;
        }
        return doc;
    }

    async set_default_values() {
        const default_party = this.get_default_party();
        if (default_party && default_party.party) {
            await this.dialog.set_value("link_doctype", default_party.party_type);
            this.dialog.set_value("link_name", default_party.party);
        }
    }

    get_default_party() {
        const doc = cur_frm && cur_frm.doc;
        if (
            doc &&
            frappe.dynamic_link &&
            frappe.dynamic_link.doc === doc
        ) {
            return {
                party_type: frappe.dynamic_link.doctype,
                party: frappe.dynamic_link.doc[frappe.dynamic_link.fieldname]
            };
        }
    }
}

frappe.ui.form.AddressQuickEntryForm = AddressQuickEntryForm;

async function autofill_fields(dialog) {
    const gstin = dialog.doc._gstin;
    const gstin_field = dialog.get_field("_gstin");

    if (!gstin || gstin.length != 15) {
        const pincode_field = dialog.fields_dict._pincode;
        pincode_field.set_data([]);
        pincode_field.df.onchange = null;

        gstin_field.set_description(GSTIN_FIELD_DESCRIPTION);
        return;
    }

    const gstin_info = await get_gstin_info(gstin);
    set_gstin_description(gstin_field, gstin_info.status);
    map_gstin_info(dialog.doc, gstin_info);
    dialog.refresh();

    setup_pincode_field(dialog, gstin_info);
}

function set_gstin_description(gstin_field, status) {
    const STATUS_COLORS = { Active: "green", Cancelled: "red" };

    gstin_field.set_description(
        `<div class="d-flex indicator ${STATUS_COLORS[status] || "orange"}">
            Status:&nbsp;<strong>${status}</strong>
        </div>`
    );
}

function setup_pincode_field(dialog, gstin_info) {
    if (!gstin_info.all_addresses) return;

    const pincode_field = dialog.fields_dict._pincode;
    pincode_field.set_data(
        gstin_info.all_addresses.map(address => {
            return {
                label: address.pincode,
                value: address.pincode,
                description: `${address.address_line1}, ${address.address_line2}, ${address.city}, ${address.state}`,
            };
        })
    );

    pincode_field.df.onchange = () => {
        autofill_address(dialog.doc, gstin_info);
        dialog.refresh();
    };
}

function get_gstin_info(gstin) {
    return frappe
        .call({
            method: "india_compliance.gst_india.utils.gstin_info.get_gstin_info",
            args: { gstin },
        })
        .then(r => r.message);
}

function map_gstin_info(doc, gstin_info) {
    if (!gstin_info) return;

    update_party_info(doc, gstin_info);

    if (gstin_info.permanent_address) {
        update_address_info(doc, gstin_info.permanent_address);
    }
}

function update_party_info(doc, gstin_info) {
    doc.gstin = doc._gstin;
    doc.gst_category = gstin_info.gst_category;

    if (!in_list(frappe.boot.gst_party_types, doc.doctype)) return;

    const party_name_field = `${doc.doctype.toLowerCase()}_name`;
    doc[party_name_field] = gstin_info.business_name;
}

function update_address_info(doc, address) {
    if (!address) return;

    Object.assign(doc, address);
    // set field renamed due conflict with frappe.ui.form.Layout
    doc._pincode = address.pincode;
}

function autofill_address(doc, { all_addresses }) {
    const { _pincode: pincode } = doc;
    if (!pincode || pincode.length !== 6 || !all_addresses) return;

    update_address_info(
        doc,
        all_addresses.find(address => address.pincode == pincode)
    );
}
