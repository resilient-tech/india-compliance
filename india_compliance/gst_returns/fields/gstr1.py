"""GSTR-1 constants. Pure, no frappe."""

from enum import Enum


class Category(Enum):
    # overview page
    B2B = "B2B, SEZ, DE"
    EXP = "Exports"
    B2CL = "B2C (Large)"
    B2CS = "B2C (Others)"
    NIL_EXEMPT = "Nil-Rated, Exempted, Non-GST"
    CDNR = "Credit/Debit Notes (Registered)"
    CDNUR = "Credit/Debit Notes (Unregistered)"
    AT = "Advances Received"
    TXP = "Advances Adjusted"
    HSN = "HSN Summary"
    DOC_ISSUE = "Document Issued"
    SUPECOM = "Supplies made through E-commerce Operators"
    ECOM_RCM = "Supplies through E-commerce Operators u/s 9(5)"


class SubCategory(Enum):
    # summary page
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
    AT = "Advances Received"
    TXP = "Advances Adjusted"
    HSN = "HSN Summary"  # back-compat
    HSN_B2B = "HSN Summary - B2B"
    HSN_B2C = "HSN Summary - B2C"
    DOC_ISSUE = "Document Issued"
    SUPECOM_52 = "Liable to collect tax u/s 52(TCS)"
    SUPECOM_9_5 = "Liable to pay tax u/s 9(5)"


class DocField:
    # canonical names
    TRANSACTION_TYPE = "transaction_type"
    CUST_GSTIN = "customer_gstin"
    ECOMMERCE_GSTIN = "ecommerce_gstin"
    ECOMMERCE_OPERATOR_NAME = "ecommerce_operator_name"
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

    # row marker: "D" deletes the row on upload
    FLAG = "flag"


class ItemField:
    INDEX = "idx"
    TAXABLE_VALUE = "taxable_value"
    IGST = "igst_amount"
    CGST = "cgst_amount"
    SGST = "sgst_amount"
    CESS = "cess_amount"
    TAX_RATE = "tax_rate"
    ITEM_DETAILS = "item_details"
    ADDITIONAL_AMOUNT = "additional_amount"


class RawField:
    # portal JSON keys
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

    HSN_DATA = "data"  # back-compat
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

    # e-commerce rows spell the taxes out
    ECOM_IGST = "igst"
    ECOM_CGST = "cgst"
    ECOM_SGST = "sgst"
    ECOM_CESS = "cess"

    HSN_B2B = "hsn_b2b"
    HSN_B2C = "hsn_b2c"

    ERROR_CD = "error_cd"
    ERROR_MSG = "error_msg"

    FLAG = "flag"
    CHECKSUM = "chksum"


class ExcelLabel:
    # column headers
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

    HSN_CODE = "HSN"
    UOM = "UQC"
    QUANTITY = "Total Quantity"
    TOTAL_VALUE = "Total Value"


class JsonKey(Enum):
    # top-level keys in gov JSON
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


class HSNKey(Enum):
    # json keys HSN rows arrive under, for picking excel sheets
    HSN = JsonKey.HSN.value
    HSN_B2B = RawField.HSN_B2B
    HSN_B2C = RawField.HSN_B2C


class SheetName(Enum):
    # gov excel worksheets
    B2B = "b2b,sez,de"
    EXP = "exp"
    B2CL = "b2cl"
    B2CS = "b2cs"
    NIL_EXEMPT = "exemp"
    CDNR = "cdnr"
    CDNUR = "cdnur"
    AT = "at"
    TXP = "atadj"
    HSN = "hsn"
    HSN_B2B = "hsn(b2b)"
    HSN_B2C = "hsn(b2c)"
    DOC_ISSUE = "docs"
    SUPECOM = "eco"
    MASTER = "master"


class B2BInvoiceType(Enum):
    R = "Regular B2B"
    SEWP = "SEZ supplies with payment"
    SEWOP = "SEZ supplies without payment"
    DE = "Deemed Exp"


class CreditDebitNoteType(Enum):
    C = "Credit Note"
    D = "Debit Note"


class NilRatedCategory(Enum):
    INTER_B2B = "Inter-State supplies to registered persons"
    INTER_B2C = "Inter-State supplies to unregistered persons"
    INTRA_B2B = "Intra-State supplies to registered persons"
    INTRA_B2C = "Intra-State supplies to unregistered persons"


class DocumentNature(Enum):
    OUTWARD_SUPPLY = "Invoices for outward supply"
    INWARD_SUPPLY_UNREGISTERED = "Invoices for inward supply from unregistered person"
    REVISED_INVOICE = "Revised Invoice"
    DEBIT_NOTE = "Debit Note"
    CREDIT_NOTE = "Credit Note"
    RECEIPT_VOUCHER = "Receipt voucher"
    PAYMENT_VOUCHER = "Payment Voucher"
    REFUND_VOUCHER = "Refund voucher"
    DELIVERY_CHALLAN_JOB_WORK = "Delivery Challan for job work"
    DELIVERY_CHALLAN_APPROVAL = "Delivery Challan for supply on approval"
    DELIVERY_CHALLAN_LIQUID_GAS = "Delivery Challan in case of liquid gas"
    DELIVERY_CHALLAN_OTHER = (
        "Delivery Challan in cases other than by way of supply (excluding at S no. 9 to 11)"
    )


CATEGORY_SUB_CATEGORY_MAPPING = {
    Category.B2B: (
        SubCategory.B2B_REGULAR,
        SubCategory.B2B_REVERSE_CHARGE,
        SubCategory.SEZWP,
        SubCategory.SEZWOP,
        SubCategory.DE,
    ),
    Category.B2CL: (SubCategory.B2CL,),
    Category.EXP: (SubCategory.EXPWP, SubCategory.EXPWOP),
    Category.B2CS: (SubCategory.B2CS,),
    Category.NIL_EXEMPT: (SubCategory.NIL_EXEMPT,),
    Category.CDNR: (SubCategory.CDNR,),
    Category.CDNUR: (SubCategory.CDNUR,),
    Category.AT: (SubCategory.AT,),
    Category.TXP: (SubCategory.TXP,),
    Category.DOC_ISSUE: (SubCategory.DOC_ISSUE,),
    Category.HSN: (SubCategory.HSN_B2B, SubCategory.HSN_B2C),
    Category.SUPECOM: (SubCategory.SUPECOM_52, SubCategory.SUPECOM_9_5),
}

# back-compat
PREVIOUS_VERSION = {Category.HSN.value: (SubCategory.HSN,)}

SUB_CATEGORY_GOV_CATEGORY_MAPPING = {
    SubCategory.B2B_REGULAR: JsonKey.B2B,
    SubCategory.B2B_REVERSE_CHARGE: JsonKey.B2B,
    SubCategory.SEZWP: JsonKey.B2B,
    SubCategory.SEZWOP: JsonKey.B2B,
    SubCategory.DE: JsonKey.B2B,
    SubCategory.B2CL: JsonKey.B2CL,
    SubCategory.EXPWP: JsonKey.EXP,
    SubCategory.EXPWOP: JsonKey.EXP,
    SubCategory.B2CS: JsonKey.B2CS,
    SubCategory.NIL_EXEMPT: JsonKey.NIL_EXEMPT,
    SubCategory.CDNR: JsonKey.CDNR,
    SubCategory.CDNUR: JsonKey.CDNUR,
    SubCategory.AT: JsonKey.AT,
    SubCategory.TXP: JsonKey.TXP,
    SubCategory.DOC_ISSUE: JsonKey.DOC_ISSUE,
    SubCategory.HSN: JsonKey.HSN,  # back-compat
    SubCategory.HSN_B2B: JsonKey.HSN,
    SubCategory.HSN_B2C: JsonKey.HSN,
    SubCategory.SUPECOM_52: JsonKey.SUPECOM,
    SubCategory.SUPECOM_9_5: JsonKey.SUPECOM,
}

JSON_CATEGORY_EXCEL_CATEGORY_MAPPING = {
    JsonKey.B2B.value: SheetName.B2B.value,
    JsonKey.EXP.value: SheetName.EXP.value,
    JsonKey.B2CL.value: SheetName.B2CL.value,
    JsonKey.B2CS.value: SheetName.B2CS.value,
    JsonKey.NIL_EXEMPT.value: SheetName.NIL_EXEMPT.value,
    JsonKey.CDNR.value: SheetName.CDNR.value,
    JsonKey.CDNUR.value: SheetName.CDNUR.value,
    JsonKey.AT.value: SheetName.AT.value,
    JsonKey.TXP.value: SheetName.TXP.value,
    JsonKey.HSN.value: SheetName.HSN.value,
    JsonKey.DOC_ISSUE.value: SheetName.DOC_ISSUE.value,
    JsonKey.SUPECOM.value: SheetName.SUPECOM.value,
    HSNKey.HSN_B2B.value: SheetName.HSN_B2B.value,
    HSNKey.HSN_B2C.value: SheetName.HSN_B2C.value,
}

QUARTERLY_KEYS = (
    "already_included_docs_for_quarterly",
    "excluded_docs_for_quarterly",
)

SUBCATEGORIES_NOT_CONSIDERED_IN_TOTAL_TAXABLE_VALUE = [
    SubCategory.HSN.value,  # back-compat
    SubCategory.HSN_B2B.value,
    SubCategory.HSN_B2C.value,
    SubCategory.DOC_ISSUE.value,
    SubCategory.SUPECOM_52.value,
]

SUBCATEGORIES_NOT_CONSIDERED_IN_TOTAL_TAX = [
    SubCategory.B2B_REVERSE_CHARGE.value,
    SubCategory.SUPECOM_9_5.value,
    *SUBCATEGORIES_NOT_CONSIDERED_IN_TOTAL_TAXABLE_VALUE,
]
