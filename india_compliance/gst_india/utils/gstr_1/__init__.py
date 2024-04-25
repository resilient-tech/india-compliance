from enum import Enum

"""
Steps:

5. Export tool to be useful for the user to download the data in Excel or JSON format

WHAT SETTINGS?
- Use API
- Quarterly or Monthly
V - Dates
V - NIL Exempt ignore zero

UI:
- Books data as on
- Listeners: Steps Download / Computing / Reconciling / Loading
- Highlight active tab
- Save utility (save data)
P - For current year, month selectable should not be more than current month or quarter
P - Only from july 2017
P - Date hardcoded


Notes
S - Upload status in books
S - Match status in reconcile
S - Match POS and Customer GSTIN
S - Reconciled data only with differences
S - Doc Issued not showing
- Test with Actual Data
- Refactor and cleanup

Data Export
P - Reconcile excel with all data export
V & P- JSON export with upload status -> Option to export missing in Books with zero values

Future TODO;
- e-Invoice regenerate / Return re-generate
- Actions: create or cancel sales invoice
- e-Commerece supplies
- Bulk generation process

"""


class GSTR1_Categories(Enum):
    """
    Overview Page of GSTR-1
    """

    # Invoice Items Bifurcation
    B2B = "B2B, SEZ, DE"
    B2CL = "B2C (Large)"
    EXP = "Exports"
    B2CS = "B2C (Others)"
    NIL_EXEMPT = "Nil-Rated, Exempted, Non-GST"
    CDNR = "Credit/Debit Notes (Registered)"
    CDNUR = "Credit/Debit Notes (Unregistered)"

    # Other Categories
    AT = "Advances Received"
    TXP = "Advances Adjusted"
    DOC_ISSUE = "Document Issued"
    HSN = "HSN Summary"
    SUPECOM = "Supplies made through E-commerce Operators"


class GSTR1_Gov_Categories(Enum):
    """
    Categories as per GSTR-1 Govt. Portal
    """

    B2B = "b2b"
    B2CL = "b2cl"
    EXP = "exp"
    B2CS = "b2cs"
    NIL_EXEMPT = "nil"
    CDNR = "cdnr"
    CDNUR = "cdnur"
    AT = "at"
    TXP = "txpd"
    DOC_ISSUE = "doc_issue"
    HSN = "hsn"
    SUPECOM = "sup_eco"


class GSTR1_SubCategories(Enum):
    """
    Summary Page of GSTR-1
    """

    # Invoice Items Bifurcation
    B2B_REGULAR = "B2B Regular"
    B2B_REVERSE_CHARGE = "B2B Reverse Charge"
    SEZWP = "SEZ with payment"
    SEZWOP = "SEZ without payment"
    DE = "Deemed Exports"
    B2CL = "B2C (Large)"
    EXPWP = "Exports with payment"
    EXPWOP = "Exports without payment"
    B2CS = "B2C (Others)"
    NIL_EXEMPT = "Nil-Rated, Exempted, Non-GST"
    CDNR = "Credit/Debit Notes (Registered)"
    CDNUR = "Credit/Debit Notes (Unregistered)"

    # Other Sub-Categories
    AT = "Advances Received"
    TXP = "Advances Adjusted"
    HSN = "HSN Summary"
    DOC_ISSUE = "Document Issued"

    # E-Commerce
    SUPECOM_52 = "TCS collected by E-commerce Operator u/s 52"
    SUPECOM_9_5 = "GST Payable on RCM by E-commerce Operator u/s 9(5)"


E_INVOICE_SUB_CATEGORIES = [
    "B2B Regular",
    "B2B Reverse Charge",
    "SEZ with payment",
    "SEZ without payment",
    "Deemed Exports",
    "Exports with payment",
    "Exports without payment",
    "Credit/Debit Notes (Registered)",
]


class DataFields(Enum):
    TRANSACTION_TYPE = "transaction_type"
    CUST_GSTIN = "customer_gstin"
    ECOMMERCE_GSTIN = "ecommerce_gstin"
    CUST_NAME = "customer_name"
    DOC_DATE = "document_date"
    DOC_NUMBER = "document_number"
    DOC_TYPE = "document_type"
    DOC_VALUE = "document_value"
    POS = "place_of_supply"
    DIFF_PERCENTAGE = "diff_percentage"
    REVERSE_CHARGE = "reverse_charge"
    TAXABLE_VALUE = "total_taxable_value"
    ITEMS = "items"
    IGST = "total_igst_amount"
    CGST = "total_cgst_amount"
    SGST = "total_sgst_amount"
    CESS = "total_cess_amount"
    TAX_RATE = "tax_rate"
    SHIPPING_BILL_NUMBER = "shipping_bill_number"
    SHIPPING_BILL_DATE = "shipping_bill_date"
    SHIPPING_PORT_CODE = "shipping_port_code"

    EXEMPTED_AMOUNT = "exempted_amount"
    NIL_RATED_AMOUNT = "nil_rated_amount"
    NON_GST_AMOUNT = "non_gst_amount"

    HSN_CODE = "hsn_code"
    DESCRIPTION = "description"
    UOM = "uom"
    QUANTITY = "quantity"
    TOTAL_QUANTITY = "total_quantity"
    TOTAL_VALUE = "total_value"

    DOCUMENT_NATURE = "document_nature"
    FROM_SR = "from_sr_no"
    TO_SR = "to_sr_no"
    TOTAL_COUNT = "total_count"
    DRAFT_COUNT = "draft_count"
    CANCELLED_COUNT = "cancelled_count"


class GovDataFields(Enum):
    CUST_GSTIN = "ctin"
    ECOMMERCE_GSTIN = "etin"
    DOC_DATE = "idt"
    DOC_NUMBER = "inum"
    DOC_VALUE = "val"
    POS = "pos"
    DIFF_PERCENTAGE = "diff_percent"
    REVERSE_CHARGE = "rchrg"
    TAXABLE_VALUE = "txval"
    ITEMS = "itms"
    IGST = "iamt"
    CGST = "camt"
    SGST = "samt"
    CESS = "csamt"
    TAX_RATE = "rt"
    ITEM_DETAILS = "itm_det"
    SHIPPING_BILL_NUMBER = "sbnum"
    SHIPPING_BILL_DATE = "sbdt"
    SHIPPING_PORT_CODE = "sbpcode"
    SUPPLY_TYPE = "sply_ty"

    EXEMPTED_AMOUNT = "expt_amt"
    NIL_RATED_AMOUNT = "nil_amt"
    NON_GST_AMOUNT = "ngsup_amt"

    HSN_DATA = "data"
    HSN_CODE = "hsn_sc"
    DESCRIPTION = "desc"
    UOM = "uqc"
    QUANTITY = "qty"
    ADDITIONAL_AMOUNT = "ad_amt"

    INDEX = "num"
    FROM_SR = "from"
    TO_SR = "to"
    TOTAL_COUNT = "totnum"
    CANCELLED_COUNT = "cancel"
    DOC_ISSUE_DETAILS = "doc_det"
    DOC_ISSUE_NUMBER = "doc_num"
    DOC_ISSUE_LIST = "docs"
    NET_ISSUE = "net_issue"

    INVOICE_TYPE = "inv_typ"
    INVOICES = "inv"
    EXPORT_TYPE = "exp_typ"
    TYPE = "typ"

    NOTE_TYPE = "ntty"
    NOTE_NUMBER = "nt_num"
    NOTE_DATE = "nt_dt"
    NOTE_DETAILS = "nt"


class ItemFields(Enum):
    INDEX = "idx"
    TAXABLE_VALUE = "taxable_value"
    IGST = "igst_amount"
    CGST = "cgst_amount"
    SGST = "sgst_amount"
    CESS = "cess_amount"
    TAX_RATE = "tax_rate"
    ITEM_DETAILS = "item_details"
    ADDITIONAL_AMOUNT = "additional_amount"


CATEGORY_SUB_CATEGORY_MAPPING = {
    GSTR1_Categories.B2B: (
        GSTR1_SubCategories.B2B_REGULAR,
        GSTR1_SubCategories.B2B_REVERSE_CHARGE,
        GSTR1_SubCategories.SEZWP,
        GSTR1_SubCategories.SEZWOP,
        GSTR1_SubCategories.DE,
    ),
    GSTR1_Categories.B2CL: (GSTR1_SubCategories.B2CL,),
    GSTR1_Categories.EXP: (GSTR1_SubCategories.EXPWP, GSTR1_SubCategories.EXPWOP),
    GSTR1_Categories.B2CS: (GSTR1_SubCategories.B2CS,),
    GSTR1_Categories.NIL_EXEMPT: (GSTR1_SubCategories.NIL_EXEMPT,),
    GSTR1_Categories.CDNR: (GSTR1_SubCategories.CDNR,),
    GSTR1_Categories.CDNUR: (GSTR1_SubCategories.CDNUR,),
    GSTR1_Categories.AT: (GSTR1_SubCategories.AT,),
    GSTR1_Categories.TXP: (GSTR1_SubCategories.TXP,),
    GSTR1_Categories.DOC_ISSUE: (GSTR1_SubCategories.DOC_ISSUE,),
    GSTR1_Categories.HSN: (GSTR1_SubCategories.HSN,),
}


SUB_CATEGORY_GOV_CATEGORY_MAPPING = {
    GSTR1_SubCategories.B2B_REGULAR: GSTR1_Gov_Categories.B2B,
    GSTR1_SubCategories.B2B_REVERSE_CHARGE: GSTR1_Gov_Categories.B2B,
    GSTR1_SubCategories.SEZWP: GSTR1_Gov_Categories.B2B,
    GSTR1_SubCategories.SEZWOP: GSTR1_Gov_Categories.B2B,
    GSTR1_SubCategories.DE: GSTR1_Gov_Categories.B2B,
    GSTR1_SubCategories.B2CL: GSTR1_Gov_Categories.B2CL,
    GSTR1_SubCategories.EXPWP: GSTR1_Gov_Categories.EXP,
    GSTR1_SubCategories.EXPWOP: GSTR1_Gov_Categories.EXP,
    GSTR1_SubCategories.B2CS: GSTR1_Gov_Categories.B2CS,
    GSTR1_SubCategories.NIL_EXEMPT: GSTR1_Gov_Categories.NIL_EXEMPT,
    GSTR1_SubCategories.CDNR: GSTR1_Gov_Categories.CDNR,
    GSTR1_SubCategories.CDNUR: GSTR1_Gov_Categories.CDNUR,
    GSTR1_SubCategories.AT: GSTR1_Gov_Categories.AT,
    GSTR1_SubCategories.TXP: GSTR1_Gov_Categories.TXP,
    GSTR1_SubCategories.DOC_ISSUE: GSTR1_Gov_Categories.DOC_ISSUE,
    GSTR1_SubCategories.HSN: GSTR1_Gov_Categories.HSN,
}
