CANCEL_REASON_CODES = {
    "Duplicate": "1",
    "Order Cancelled": "3",
    "Data Entry Mistake": "2",
    "Others": "4",
}

E_INVOICE_FIELDS = {
    "Sales Invoice": [
        {
            "fieldname": "irn",
            "label": "IRN",
            "fieldtype": "Data",
            "read_only": 1,
            "insert_after": "customer",
            "no_copy": 1,
            "print_hide": 1,
            "depends_on": (
                'eval:in_list(["Registered Regular", "SEZ", "Overseas", "Deemed'
                ' Export"], doc.gst_category) && doc.irn_cancelled === 0'
            ),
            "translatable": 0,
        },
        {
            "fieldname": "einvoice_status",
            "label": "e-Invoice Status",
            "fieldtype": "Select",
            "insert_after": "status",
            "options": "\nPending\nGenerated\nCancelled\nFailed",
            "default": None,
            "hidden": 1,
            "no_copy": 1,
            "print_hide": 1,
            "read_only": 1,
            "translatable": 0,
        },
    ]
}
