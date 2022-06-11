import { autofill_gstin_fields } from "./utils";

class PartyQuickEntryForm extends frappe.ui.form.QuickEntryForm {
    constructor(...args) {
        super(...args);
        this.skip_redirect_on_error = true;
        this.enable_api = frappe.boot.gst_settings.enable_api;
    }

    get_address_fields() {
        return [
            {
                label: __("Primary Address Details"),
                fieldname: "section_break2",
                fieldtype: "Section Break",
                description: this.enable_api
                    ? __(
                          "Permanent address is auto-filled. Change Pincode if you wish to autofill other address."
                      )
                    : "",
                collapsible: 0,
            },
            {
                label: __("Pincode"),
                fieldname: "_pincode",
                fieldtype: "Autocomplete",
                ignore_validation: true,
            },
            {
                label: __("Address Line 1"),
                fieldname: "_address_line1",
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
            },
            {
                label: __("Customer POS Id"),
                fieldname: "customer_pos_id",
                fieldtype: "Data",
                hidden: 1,
            },
        ];
    }

    get_gstin_fields() {
        return [
            {
                label: "GSTIN",
                fieldname: "_gstin",
                fieldtype: "Autocomplete",
                description: this.enable_api
                    ? __("Autofill party information by entering correct GSTIN.")
                    : "",
                ignore_validation: true,
                onchange: _ => {
                    if (!this.enable_api) return;
                    autofill_gstin_fields(this.dialog);
                },
            },
        ];
    }
}

frappe.ui.form.SupplierQuickEntryForm =
    frappe.ui.form.CustomerQuickEntryForm = class CustomerQuickEntryForm extends (
        PartyQuickEntryForm
    ) {
        render_dialog() {
            this.mandatory = [
                ...this.get_gstin_fields(),
                ...this.mandatory,
                ...this.get_variant_fields(),
                ...this.get_address_fields(),
            ];
            super.render_dialog();
        }

        get_variant_fields() {
            return [
                {
                    label: __("Primary Contact Details"),
                    fieldname: "section_break1",
                    fieldtype: "Section Break",
                    collapsible: 0,
                },
                {
                    label: __("Email Id"),
                    fieldname: "email_id",
                    fieldtype: "Data",
                },
                {
                    fieldtype: "Column Break",
                },
                {
                    label: __("Mobile Number"),
                    fieldname: "mobile_no",
                    fieldtype: "Data",
                },
            ];
        }
    };

frappe.ui.form.AddressQuickEntryForm = class AddressQuickEntryForm extends (
    PartyQuickEntryForm
) {
    async render_dialog() {
        const address_fields = this.get_address_fields();
        const fields_to_exclude = address_fields.map(({ fieldname }) => fieldname);
        fields_to_exclude.push("pincode", "address_line1");

        this.mandatory = [
            ...this.get_party_fields(),
            ...this.get_gstin_fields(),
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
                fieldtype: "Autocomplete",
                label: "Party Type",
                options: "Customer\nSupplier",
                onchange: async _ => {
                    // await to avoid clash with onchange of party field
                    await this.dialog.set_value("party", "");
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
                onchange: async _ => {
                    const { party_type, party } = this.dialog.doc;
                    if (!party) return;
                    const { message: gstins } = await frappe.call(
                        "india_compliance.gst_india.utils.get_gstin_list",
                        { party_type, party }
                    );
                    if (!gstins || !gstins.length) return;
                    this.dialog.fields_dict._gstin.set_data(gstins.join("\n"));
                },
            },
            {
                fieldtype: "Section Break",
            },
        ];
    }

    async set_default_values() {
        const default_party = this.get_default_party();
        await this.dialog.set_value("party_type", default_party.party_type);
        this.dialog.set_value("party", default_party.party);
    }

    get_default_party() {
        if (!cur_frm) return { party_type: "Customer", party: "" };

        const { doctype } = cur_frm.doc;
        if (in_list(["Customer", "Supplier"], doctype))
            return { party_type: doctype, party: cur_frm.doc.name };

        const party_type = ic.get_party_type(doctype);
        return { party_type, party: cur_frm.doc[party_type.toLowerCase()] };
    }
};
