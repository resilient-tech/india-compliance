from enum import Enum

from frappe.utils import getdate


class GSTR1_Category(Enum):
    """
    Overview Page of GSTR-1
    """

    # Invoice Items Bifurcation
    B2B = "B2B, SEZ, DE"
    EXP = "Exports"
    B2CL = "B2C (Large)"
    B2CS = "B2C (Others)"
    NIL_EXEMPT = "Nil-Rated, Exempted, Non-GST"
    CDNR = "Credit/Debit Notes (Registered)"
    CDNUR = "Credit/Debit Notes (Unregistered)"

    # Other Categories
    AT = "Advances Received"
    TXP = "Advances Adjusted"
    HSN = "HSN Summary"
    DOC_ISSUE = "Document Issued"
    SUPECOM = "Supplies made through E-commerce Operators"


class GSTR1_SubCategory(Enum):
    """
    Summary Page of GSTR-1
    """

    # Invoice Items Bifurcation
    B2B_REGULAR = "B2B Regular"
    B2B_REVERSE_CHARGE = "B2B Reverse Charge"
    SEZWP = "SEZ With Payment of Tax"
    SEZWOP = "SEZ Without Payment of Tax"
    DE = "Deemed Exports"
    EXPWP = "Export With Payment of Tax"
    EXPWOP = "Export Without Payment of Tax"
    B2CL = "B2C (Large)"
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
    SUPECOM_52 = "Liable to collect tax u/s 52(TCS)"
    SUPECOM_9_5 = "Liable to pay tax u/s 9(5)"


class SUPECOM(Enum):
    US_9_5 = "Liable to pay tax u/s 9(5)"
    US_52 = "Liable to collect tax u/s 52(TCS)"


CATEGORY_SUB_CATEGORY_MAPPING = {
    GSTR1_Category.B2B: (
        GSTR1_SubCategory.B2B_REGULAR,
        GSTR1_SubCategory.B2B_REVERSE_CHARGE,
        GSTR1_SubCategory.SEZWP,
        GSTR1_SubCategory.SEZWOP,
        GSTR1_SubCategory.DE,
    ),
    GSTR1_Category.B2CL: (GSTR1_SubCategory.B2CL,),
    GSTR1_Category.EXP: (GSTR1_SubCategory.EXPWP, GSTR1_SubCategory.EXPWOP),
    GSTR1_Category.B2CS: (GSTR1_SubCategory.B2CS,),
    GSTR1_Category.NIL_EXEMPT: (GSTR1_SubCategory.NIL_EXEMPT,),
    GSTR1_Category.CDNR: (GSTR1_SubCategory.CDNR,),
    GSTR1_Category.CDNUR: (GSTR1_SubCategory.CDNUR,),
    GSTR1_Category.AT: (GSTR1_SubCategory.AT,),
    GSTR1_Category.TXP: (GSTR1_SubCategory.TXP,),
    GSTR1_Category.DOC_ISSUE: (GSTR1_SubCategory.DOC_ISSUE,),
    GSTR1_Category.HSN: (GSTR1_SubCategory.HSN,),
    GSTR1_Category.SUPECOM: (
        GSTR1_SubCategory.SUPECOM_52,
        GSTR1_SubCategory.SUPECOM_9_5,
    ),
}


class GSTR1_DataField(Enum):
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

    FROM_SR = "from_sr_no"
    TO_SR = "to_sr_no"
    TOTAL_COUNT = "total_count"
    DRAFT_COUNT = "draft_count"
    CANCELLED_COUNT = "cancelled_count"
    NET_ISSUE = "net_issue"
    UPLOAD_STATUS = "upload_status"

    ERROR_CD = "error_code"
    ERROR_MSG = "error_message"


class GSTR1_ItemField(Enum):
    INDEX = "idx"
    TAXABLE_VALUE = "taxable_value"
    IGST = "igst_amount"
    CGST = "cgst_amount"
    SGST = "sgst_amount"
    CESS = "cess_amount"
    TAX_RATE = "tax_rate"
    ITEM_DETAILS = "item_details"
    ADDITIONAL_AMOUNT = "additional_amount"


class GovDataField(Enum):
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
    NET_TAXABLE_VALUE = "suppval"

    EXEMPTED_AMOUNT = "expt_amt"
    NIL_RATED_AMOUNT = "nil_amt"
    NON_GST_AMOUNT = "ngsup_amt"

    HSN_DATA = "data"
    HSN_CODE = "hsn_sc"
    DESCRIPTION = "desc"
    UOM = "uqc"
    QUANTITY = "qty"
    ADVANCE_AMOUNT = "ad_amt"

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

    SUPECOM_52 = "clttx"
    SUPECOM_9_5 = "paytx"

    ERROR_CD = "error_cd"
    ERROR_MSG = "error_msg"

    FLAG = "flag"


class GovExcelField(Enum):
    CUST_GSTIN = "GSTIN/UIN of Recipient"
    CUST_NAME = "Receiver Name"
    INVOICE_NUMBER = "Invoice Number"
    INVOICE_DATE = "Invoice date"
    INVOICE_VALUE = "Invoice Value"
    POS = "Place Of Supply"
    REVERSE_CHARGE = "Reverse Charge"
    DIFF_PERCENTAGE = "Applicable % of Tax Rate"
    INVOICE_TYPE = "Invoice Type"
    TAXABLE_VALUE = "Taxable Value"
    ECOMMERCE_GSTIN = "E-Commerce GSTIN"
    TAX_RATE = "Rate"
    IGST = "Integrated Tax Amount"
    CGST = "Central Tax Amount"
    SGST = "State/UT Tax Amount"
    CESS = "Cess Amount"

    NOTE_NO = "Note Number"
    NOTE_DATE = "Note Date"
    NOTE_TYPE = "Note Type"
    NOTE_VALUE = "Note Value"

    PORT_CODE = "Port Code"
    SHIPPING_BILL_NO = "Shipping Bill Number"
    SHIPPING_BILL_DATE = "Shipping Bill Date"

    DESCRIPTION = "Description"
    # NIL_RATED = "Nil Rated Supplies"
    # EXEMPTED = "Exempted (other than nil rated/non-GST supplies)"
    # NON_GST = "Non-GST Supplies"

    HSN_CODE = "HSN"
    UOM = "UQC"
    QUANTITY = "Total Quantity"
    TOTAL_VALUE = "Total Value"


class GovJsonKey(Enum):
    """
    Categories / Keys as per Govt JSON file
    """

    B2B = "b2b"
    EXP = "exp"
    B2CL = "b2cl"
    B2CS = "b2cs"
    NIL_EXEMPT = "nil"
    CDNR = "cdnr"
    CDNUR = "cdnur"
    AT = "at"
    TXP = "txpd"
    HSN = "hsn"
    DOC_ISSUE = "doc_issue"
    SUPECOM = "supeco"
    RET_SUM = "sec_sum"


class GovExcelSheetName(Enum):
    """
    Categories / Worksheets as per Gov Excel file
    """

    B2B = "b2b, sez, de"
    EXP = "exp"
    B2CL = "b2cl"
    B2CS = "b2cs"
    NIL_EXEMPT = "exemp"
    CDNR = "cdnr"
    CDNUR = "cdnur"
    AT = "at"
    TXP = "atadj"
    HSN = "hsn"
    DOC_ISSUE = "docs"


SUB_CATEGORY_GOV_CATEGORY_MAPPING = {
    GSTR1_SubCategory.B2B_REGULAR: GovJsonKey.B2B,
    GSTR1_SubCategory.B2B_REVERSE_CHARGE: GovJsonKey.B2B,
    GSTR1_SubCategory.SEZWP: GovJsonKey.B2B,
    GSTR1_SubCategory.SEZWOP: GovJsonKey.B2B,
    GSTR1_SubCategory.DE: GovJsonKey.B2B,
    GSTR1_SubCategory.B2CL: GovJsonKey.B2CL,
    GSTR1_SubCategory.EXPWP: GovJsonKey.EXP,
    GSTR1_SubCategory.EXPWOP: GovJsonKey.EXP,
    GSTR1_SubCategory.B2CS: GovJsonKey.B2CS,
    GSTR1_SubCategory.NIL_EXEMPT: GovJsonKey.NIL_EXEMPT,
    GSTR1_SubCategory.CDNR: GovJsonKey.CDNR,
    GSTR1_SubCategory.CDNUR: GovJsonKey.CDNUR,
    GSTR1_SubCategory.AT: GovJsonKey.AT,
    GSTR1_SubCategory.TXP: GovJsonKey.TXP,
    GSTR1_SubCategory.DOC_ISSUE: GovJsonKey.DOC_ISSUE,
    GSTR1_SubCategory.HSN: GovJsonKey.HSN,
    GSTR1_SubCategory.SUPECOM_52: GovJsonKey.SUPECOM,
    GSTR1_SubCategory.SUPECOM_9_5: GovJsonKey.SUPECOM,
}

JSON_CATEGORY_EXCEL_CATEGORY_MAPPING = {
    GovJsonKey.B2B.value: GovExcelSheetName.B2B.value,
    GovJsonKey.EXP.value: GovExcelSheetName.EXP.value,
    GovJsonKey.B2CL.value: GovExcelSheetName.B2CL.value,
    GovJsonKey.B2CS.value: GovExcelSheetName.B2CS.value,
    GovJsonKey.NIL_EXEMPT.value: GovExcelSheetName.NIL_EXEMPT.value,
    GovJsonKey.CDNR.value: GovExcelSheetName.CDNR.value,
    GovJsonKey.CDNUR.value: GovExcelSheetName.CDNUR.value,
    GovJsonKey.AT.value: GovExcelSheetName.AT.value,
    GovJsonKey.TXP.value: GovExcelSheetName.TXP.value,
    GovJsonKey.HSN.value: GovExcelSheetName.HSN.value,
    GovJsonKey.DOC_ISSUE.value: GovExcelSheetName.DOC_ISSUE.value,
}


class GSTR1_B2B_InvoiceType(Enum):
    R = "Regular B2B"
    SEWP = "SEZ supplies with payment"
    SEWOP = "SEZ supplies without payment"
    DE = "Deemed Exp"


SUBCATEGORIES_NOT_CONSIDERED_IN_TOTAL_TAXABLE_VALUE = [
    GSTR1_SubCategory.HSN.value,
    GSTR1_SubCategory.DOC_ISSUE.value,
    GSTR1_SubCategory.SUPECOM_52.value,
    GSTR1_SubCategory.SUPECOM_9_5.value,
]

SUBCATEGORIES_NOT_CONSIDERED_IN_TOTAL_TAX = [
    GSTR1_SubCategory.B2B_REVERSE_CHARGE.value,
    *SUBCATEGORIES_NOT_CONSIDERED_IN_TOTAL_TAXABLE_VALUE,
]


B2C_LIMIT = [
    ("2024-07-31", 2_50_000),
    ("2099-03-31", 1_00_000),
]


def get_b2c_limit(date):
    if isinstance(date, str):
        date = getdate(date)

    for limit_date, limit in B2C_LIMIT:
        if date <= getdate(limit_date):
            return limit

    return B2C_LIMIT[-1][1]
