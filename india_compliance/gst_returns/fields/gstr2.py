"""GSTR-2A/2B constants. `Category` also names the IMS categories. Pure, no frappe."""

from enum import Enum


class Category(Enum):
    B2B = "B2B"
    B2BA = "B2BA"
    CDNR = "CDNR"
    CDNRA = "CDNRA"
    ISD = "ISD"
    ISDA = "ISDA"  # both returns read it; only 2B downloads it
    IMPG = "IMPG"
    IMPGSEZ = "IMPGSEZ"

    # IMS
    B2BCN = "B2BCN"
    B2BCNA = "B2BCNA"
    B2BDN = "B2BDN"
    B2BDNA = "B2BDNA"

    ECOM = "ECOM"
    ECOMA = "ECOMA"

    # 2A only
    TDS = "TDS"
    TCS = "TCS"


class DocField:
    # canonical names = GST Inward Supply fields
    COMPANY = "company"
    COMPANY_GSTIN = "company_gstin"
    CLASSIFICATION = "classification"

    SUPPLIER_GSTIN = "supplier_gstin"
    SUPPLIER_NAME = "supplier_name"
    GSTR_3B_FILLED = "gstr_3b_filled"
    GSTR_1_FILING_DATE = "gstr_1_filing_date"
    REGISTRATION_CANCEL_DATE = "registration_cancel_date"
    SUP_RETURN_PERIOD = "sup_return_period"

    BILL_NO = "bill_no"
    BILL_DATE = "bill_date"
    DOC_TYPE = "doc_type"
    SUPPLY_TYPE = "supply_type"
    DOC_VALUE = "document_value"
    TAXABLE_VALUE = "taxable_value"
    IGST = "igst"
    CGST = "cgst"
    SGST = "sgst"
    CESS = "cess"
    POS = "place_of_supply"
    OTHER_RETURN_PERIOD = "other_return_period"
    AMENDMENT_TYPE = "amendment_type"
    IS_AMENDED = "is_amended"
    REVERSE_CHARGE = "is_reverse_charge"
    DIFF_PERCENTAGE = "diffprcnt"
    IRN_SOURCE = "irn_source"
    IRN_NUMBER = "irn_number"
    IRN_GEN_DATE = "irn_gen_date"

    ORIGINAL_BILL_NO = "original_bill_no"
    ORIGINAL_BILL_DATE = "original_bill_date"
    ORIGINAL_DOC_TYPE = "original_doc_type"

    ITC_AVAILABILITY = "itc_availability"
    ITC_REASON = "reason_itc_unavailability"
    PORT_CODE = "port_code"

    FROM_2A = "is_downloaded_from_2a"
    FROM_2B = "is_downloaded_from_2b"
    RETURN_PERIOD_2B = "return_period_2b"
    GEN_DATE_2B = "gen_date_2b"

    ITEMS = "items"
    UNIQUE_KEY = "unique_key"


class ItemField:
    ITEM_NUMBER = "item_number"
    TAX_RATE = "rate"
    TAXABLE_VALUE = "taxable_value"
    IGST = "igst"
    CGST = "cgst"
    SGST = "sgst"
    CESS = "cess"
    ITC_ELIGIBILITY = "itcelg"


class RawField2a:
    # supplier
    SUPPLIER_GSTIN = "ctin"
    GSTR_3B_FILED = "cfs3b"
    GSTR_1_FILING_DATE = "fldtr1"
    CANCEL_DATE = "dtcancel"
    SUP_RETURN_PERIOD = "flprdr1"

    # document
    INVOICES = "inv"
    NOTES = "nt"
    ISD_DOCS = "doclist"
    DOC_NUMBER = "inum"
    DOC_DATE = "idt"
    DOC_VALUE = "val"
    INVOICE_TYPE = "inv_typ"
    POS = "pos"
    OTHER_PERIOD = "aspd"
    AMEND_TYPE = "atyp"
    REVERSE_CHARGE = "rchrg"
    DIFF_PERCENT = "diff_percent"
    IRN_SOURCE = "srctyp"
    IRN = "irn"
    IRN_DATE = "irngendate"
    ORIGINAL_DOC_NUMBER = "oinum"
    ORIGINAL_DOC_DATE = "oidt"

    # notes
    NOTE_NUMBER = "nt_num"
    NOTE_TYPE = "ntty"
    NOTE_DATE = "nt_dt"
    ORIGINAL_NOTE_NUMBER = "ont_num"
    ORIGINAL_NOTE_DATE = "ont_dt"

    # ISD
    ISD_DOC_TYPE = "isd_docty"
    ISD_DOC_NUMBER = "docnum"
    ISD_DOC_DATE = "docdt"
    ITC_ELIGIBILITY = "itc_elg"
    ISD_CESS = "cess"  # ISD alone reads cess from "cess", not "csamt"

    # imports
    BOE_NUMBER = "benum"
    BOE_DATE = "bedt"
    IS_AMENDED = "amd"
    PORT_CODE = "portcd"
    SEZ_GSTIN = "sgstin"
    SEZ_TRADE_NAME = "tdname"

    # TDS / TCS
    DEDUCTOR_GSTIN = "gstin_deductor"
    DEDUCTOR_NAME = "deductor_name"
    DEDUCTION_MONTH = "month"
    DEDUCTED_VALUE = "amt_ded"
    ECOM_GSTIN = "etin"
    SUPPLY_VALUE = "sup_val"
    TCS_TAXABLE_VALUE = "tx_val"

    # items and amounts
    ITEMS = "itms"
    ITEM_DETAILS = "itm_det"
    ITEM_NUMBER = "num"
    TAX_RATE = "rt"
    TAXABLE_VALUE = "txval"
    IGST = "iamt"
    CGST = "camt"
    SGST = "samt"
    CESS = "csamt"


class RawField2b:
    # supplier
    SUPPLIER_GSTIN = "ctin"
    SUPPLIER_NAME = "trdnm"
    GSTR_1_FILING_DATE = "supfildt"
    SUP_RETURN_PERIOD = "supprd"

    # document
    INVOICES = "inv"
    NOTES = "nt"
    ISD_DOCS = "doclist"
    BOE_DOCS = "boe"
    DOC_NUMBER = "inum"
    DOC_DATE = "dt"
    DOC_VALUE = "val"
    INVOICE_TYPE = "typ"
    POS = "pos"
    REVERSE_CHARGE = "rev"
    ITC_AVAILABILITY = "itcavl"
    ITC_REASON = "rsn"
    DIFF_PERCENT = "diffprcnt"
    IRN_SOURCE = "srctyp"
    IRN = "irn"
    IRN_DATE = "irngendate"
    ORIGINAL_DOC_NUMBER = "oinum"
    ORIGINAL_DOC_DATE = "oidt"

    # notes; "typ" is the note type here, supply type moves to "suptyp"
    NOTE_NUMBER = "ntnum"
    SUPPLY_TYPE = "suptyp"
    ORIGINAL_NOTE_NUMBER = "ontnum"
    ORIGINAL_NOTE_DATE = "ontdt"
    ORIGINAL_NOTE_TYPE = "onttyp"

    # ISD
    ISD_DOC_TYPE = "doctyp"
    ISD_DOC_NUMBER = "docnum"
    ISD_DOC_DATE = "docdt"
    ITC_ELIGIBILITY = "itcelg"
    ORIGINAL_ISD_DOC_NUMBER = "odocnum"
    ORIGINAL_ISD_DOC_DATE = "odocdt"
    ORIGINAL_ISD_DOC_TYPE = "odoctyp"

    # imports
    BOE_NUMBER = "boenum"
    BOE_DATE = "boedt"
    IS_AMENDED = "isamd"
    PORT_CODE = "portcode"

    # items and amounts
    ITEMS = "items"
    ITEM_NUMBER = "num"
    TAX_RATE = "rt"
    TAXABLE_VALUE = "txval"
    IGST = "igst"
    CGST = "cgst"
    SGST = "sgst"
    CESS = "cess"


# gov code -> ours
Y_N_TO_CHECK = {"Y": 1, "N": 0}
YES_NO = {"Y": "Yes", "N": "No"}
NOTE_TYPE = {"C": "Credit Note", "D": "Debit Note"}
ISD_TYPE_2A = {"ISDCN": "ISD Credit Note", "ISD": "ISD Invoice"}
ISD_TYPE_2B = {"ISDC": "ISD Credit Note", "ISDI": "ISD Invoice"}
AMEND_TYPE = {
    "R": "Receiver GSTIN Amended",
    "N": "Invoice Number Amended",
    "D": "Other Details Amended",
}

# the portal reports no rate difference as no key at all
DIFF_PERCENT = {1: 1, 0.65: 0.65, None: 1}
