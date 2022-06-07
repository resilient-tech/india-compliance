CANCEL_REASON_CODES = {
    "Duplicate": "1",
    "Order Cancelled": "3",
    "Data Entry Mistake": "2",
    "Others": "4",
}

E_INVOICE_DATA_MAP = {
    # Value details have been added in between to ensure
    # that the order of the fields in the PDF is appropriate
    ############## ITEM LIST #######################
    "SlNo": "Sr. No.",
    "PrdDesc": "Product Description",
    "HsnCd": "HSN Code",
    "Qty": "Qty",
    "Unit": "UOM",
    "UnitPrice": "Rate",
    ############## VALUE DETAILS ###################
    "AssVal": "Taxable Value",
    "CgstVal": "CGST",
    "SgstVal": "SGST",
    "IgstVal": "IGST",
    "CessVal": "CESS",
    "Discount": "Discount",  # Common Field in Item List
    "OthChrg": "Other Charges",
    "RndOffAmt": "Round Off",
    "TotInvVal": "Total Value",
    ############## VALUE DETAILS END ################
    "AssAmt": "Taxable Amount",
    "GstRt": "Tax Rate",
    "CesRt": "Cess Rate",
    "TotItemVal": "Total",
    ############## ITEM LIST END ####################
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
                ' Export"], doc.gst_category)'
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
