// Copyright (c) 2024, Resilient Tech and contributors
// For license information, please see license.txt

frappe.listview_settings["e-Waybill Log"] = {
    hide_name_column: true,

    button: {
        show: function (doc) {
            return doc.reference_name;
        },

        get_label: function () {
            return __("Open Reference");
        },

        get_description: function (doc) {
            return __("Open {0}", [
                `${__(doc.reference_doctype)}: ${doc.reference_name}`,
            ]);
        },

        action: function (doc) {
            frappe.set_route("Form", doc.reference_doctype, doc.reference_name);
        },
    },
};
