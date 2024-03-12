frappe.listview_settings["GSTR 3B Report"] = {
    hide_name_column: true,
    add_fields: ["generation_status"],
    get_indicator: function (doc) {
        var colors = {
            "In Process": "orange",
            Generated: "green",
            Failed: "red",
        };
        return [
            __(doc.generation_status),
            colors[doc.generation_status],
            "generation_status,=," + doc.generation_status,
        ];
    },
};
