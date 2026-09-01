"""IMS constants. Categories come from gstr2.Category. Pure, no frappe."""

from india_compliance.gst_returns.fields import gstr2


class DocField(gstr2.DocField):
    FROM_IMS = "is_downloaded_from_ims"
    IMS_ACTION = "ims_action"
    PREVIOUS_IMS_ACTION = "previous_ims_action"
    IS_PENDING_ACTION_ALLOWED = "is_pending_action_allowed"
    IS_SUPPLIER_RETURN_FILED = "is_supplier_return_filed"
    SUPPLIER_RETURN_FORM = "supplier_return_form"
    ITC_REDUCTION_REQUIRED = "itc_reduction_required"
    IS_ITC_REDUCTION_BLOCKED = "is_itc_reduction_blocked"
    DECLARED_IGST = "declared_igst"
    DECLARED_CGST = "declared_cgst"
    DECLARED_SGST = "declared_sgst"
    DECLARED_CESS = "declared_cess"
    REMARKS = "remarks"
    IS_REMARKS_BLOCKED = "is_remarks_blocked"


class RawField:
    # invoice
    SUPPLIER_GSTIN = "stin"
    SUP_RETURN_PERIOD = "rtnprd"
    SUPPLY_TYPE = "inv_typ"
    POS = "pos"
    DOC_VALUE = "val"
    INVOICES = "inv"
    DOC_NUMBER = "inum"
    DOC_DATE = "idt"
    ORIGINAL_DOC_NUMBER = "oinum"
    ORIGINAL_DOC_DATE = "oidt"

    # notes
    NOTE_NUMBER = "nt_num"
    NOTE_DATE = "nt_dt"
    ORIGINAL_NOTE_NUMBER = "ont_num"
    ORIGINAL_NOTE_DATE = "ont_dt"

    # action and supplier filing
    ACTION = "action"
    PREVIOUS_ACTION = "prev_status"
    PENDING_ACTION_BLOCKED = "ispendactblocked"
    SUP_FILING_STATUS = "srcfilstatus"
    SUP_RETURN_FORM = "srcform"

    # amounts
    TAXABLE_VALUE = "txval"
    IGST = "iamt"
    CGST = "camt"
    SGST = "samt"
    CESS = "cess"

    # ITC reversal
    ITC_REDUCTION_REQUIRED = "itcRedReq"
    ITC_REDUCTION_BLOCKED = "isItcRedReqBlocked"
    DECLARED_IGST = "declIgst"
    DECLARED_CGST = "declCgst"
    DECLARED_SGST = "declSgst"
    DECLARED_CESS = "declCess"
    REMARKS = "remarks"
    REMARKS_BLOCKED = "isRemarksBlocked"


# IMS category -> stored classification and doc type
CLASSIFICATION_MAP = {
    "B2B": ["B2B", "Invoice"],
    "B2BA": ["B2BA", "Invoice"],
    "B2BCN": ["CDNR", "Credit Note"],
    "B2BCNA": ["CDNRA", "Credit Note"],
    "B2BDN": ["CDNR", "Debit Note"],
    "B2BDNA": ["CDNRA", "Debit Note"],
}
