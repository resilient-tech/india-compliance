from enum import Enum

"""
Steps:

1. GST Settings to enable APIs for GSTR-1
2. Go to GSTR-1 Beta and click Generate
3. 3 processes will be enqueued
    - Prepare GSTR-1 Data as per GST Portal (Same as above if not filed: To be handled in JS) and summarize
    - Prepare GSTR-1 Data as per Books and summarize
    - Prepare Reconciliation Data and summarize: Update books data with the status on GSTR-1 Portal (Optional: Use case??) (upload status only when not filed)

4. Once the data is prepared, setup listeners to check the status and load the data in the front-end
5. Export tool to be useful for the user to download the data in Excel or JSON format

WHAT SETTINGS?
- Use API
- Quarterly or Monthly


WHAT DATA to be SAVED?
- 8 files to be saved in GSTR-1 Log

GSTR-1 LOG:
- is_latest_data (for books)
- Show Report
- Books data as on

UI:
- Books data as on
- Listeners: Steps Download / Computing / Reconciling / Loading


- GSTR1 Log Fields
- Save utility (save data)
- Render to return JSON

- Download => Map => Save => Pass on the data for Reco
- Query => Process => Map => Save => Pass on the data for Reco
- Process => Update => Save => Pass on the data for rendering

- Render

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
    NIL_RATED = "Nil-Rated"
    EXEMPTED = "Exempted"
    NON_GST = "Non-GST"
    CDNR = "Credit/Debit Notes (Registered)"
    CDNUR = "Credit/Debit Notes (Unregistered)"

    # Other Sub-Categories
    AT = "Advances Received"
    TXP = "Advances Adjusted"
    HSN = "HSN Summary"
    DOC_ISSUE = "Document Issued"


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

    FROM_SR = "from_sr_no"
    TO_SR = "to_sr_no"
    TOTAL_COUNT = "total_count"
    DRAFT_COUNT = "draft_count"
    CANCELLED_COUNT = "cancelled_count"


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
    GSTR1_Categories.NIL_EXEMPT: (
        GSTR1_SubCategories.NIL_RATED,
        GSTR1_SubCategories.EXEMPTED,
        GSTR1_SubCategories.NON_GST,
    ),
    GSTR1_Categories.CDNR: (GSTR1_SubCategories.CDNR,),
    GSTR1_Categories.CDNUR: (GSTR1_SubCategories.CDNUR,),
}
