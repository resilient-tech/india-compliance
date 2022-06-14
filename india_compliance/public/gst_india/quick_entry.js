class GSTQuickEntryForm extends frappe.ui.form.QuickEntryForm {
    constructor(...args) {
        super(...args);
        this.skip_redirect_on_error = true;

        const { gst_settings } = frappe.boot;
        this.api_enabled = gst_settings.enable_api && gst_settings.autofill_party_info;
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
                fieldtype: "Data",
            },
            {
                label: __("Country"),
                fieldname: "country",
                fieldtype: "Link",
                options: "Country",
                default: frappe.defaults.get_user_default("country"),
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
                description: this.api_enabled
                    ? __("Autofill party information by entering their GSTIN")
                    : "",
                ignore_validation: true,
                onchange: () => {
                    if (!this.api_enabled) return;
                    autofill_fields(this.dialog);
                },
            },
        ];
    }

    update_doc() {
        const doc = super.update_doc();
        doc.pincode = doc._pincode;
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
        doc._address_line1 = doc.address_line1;
        delete doc.address_line1;
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
            ...this.get_party_fields(),
            ...this.get_gstin_field(),
            ...this.mandatory.filter(
                field => !fields_to_exclude.includes(field.fieldname)
            ),
            ...address_fields,
        ];
        super.render_dialog();
        this.set_default_values();
    }

    get_party_fields() {
        return [
            {
                fieldname: "party_type",
                fieldtype: "Select",
                label: "Party Type",
                options: "Customer\nSupplier",
                onchange: async () => {
                    // await to avoid clash with onchange of party field
                    await this.dialog.set_value("party", "");

                    // dynamic link isn't supported in dialogs, so below hack
                    this.dialog.fields_dict.party.df.options =
                        this.dialog.doc.party_type;
                },
            },
            {
                fieldtype: "Column Break",
            },
            {
                fieldname: "party",
                fieldtype: "Link",
                label: "Party",
                onchange: async () => {
                    const { party_type, party } = this.dialog.doc;
                    if (!party) return;

                    const { message: gstin_list } = await frappe.call(
                        "india_compliance.gst_india.utils.get_gstin_list",
                        { party_type, party }
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
        if (doc.party_type && doc.party) {
            const link = frappe.model.add_child(doc, "Dynamic Link", "links");
            link.link_doctype = doc.party_type;
            link.link_name = doc.party;
        }
        return doc;
    }

    async set_default_values() {
        const default_party = this.get_default_party();
        await this.dialog.set_value("party_type", default_party.party_type);
        this.dialog.set_value("party", default_party.party);
    }

    get_default_party() {
        const doc = cur_frm && cur_frm.doc;
        if (!doc) return { party_type: "Customer", party: "" };

        const { doctype, name } = doc;
        if (in_list(["Customer", "Supplier"], doctype))
            return { party_type: doctype, party: name };

        const party_type = ic.get_party_type(doctype);
        return { party_type, party: doc[party_type.toLowerCase()] || "" };
    }
}

frappe.ui.form.AddressQuickEntryForm = AddressQuickEntryForm;

async function autofill_fields(dialog) {
    const gstin = dialog.doc._gstin;
    if (!gstin || gstin.length != 15) {
        const pincode_field = dialog.fields_dict._pincode;
        pincode_field.set_data([]);
        pincode_field.df.onchange = null;
        return;
    }

    const gstin_info = await get_gstin_info(gstin);
    map_gstin_info(dialog.doc, gstin_info);
    dialog.refresh();

    setup_pincode_field(dialog, gstin_info);
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
    const party_name_field = `${ic.get_party_type(doc.doctype).toLowerCase()}_name`;
    doc[party_name_field] = gstin_info.business_name;
    doc.gst_category = gstin_info.gst_category;
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
