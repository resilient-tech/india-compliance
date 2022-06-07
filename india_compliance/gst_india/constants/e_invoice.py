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
