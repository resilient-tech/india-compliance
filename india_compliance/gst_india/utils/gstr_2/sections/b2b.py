"""Invoices from registered suppliers. E-commerce 9(5) documents ride the same shape."""

from india_compliance.gst_india.utils import parse_datetime
from india_compliance.gst_india.utils.gstr_2.gstr import (
    GST_CATEGORY,
    STATES,
    add_original_details,
    to_period,
)
from india_compliance.gst_returns.fields.gstr2 import (
    AMEND_TYPE,
    DIFF_PERCENT,
    Y_N_TO_CHECK,
    YES_NO,
)
from india_compliance.gst_returns.fields.gstr2 import DocField as doc
from india_compliance.gst_returns.fields.gstr2 import RawField2a as raw2a
from india_compliance.gst_returns.fields.gstr2 import RawField2b as raw2b
from india_compliance.gst_returns.steps import decode, take

KEYS_2A = {
    raw2a.DOC_NUMBER: doc.BILL_NO,
    raw2a.INVOICE_TYPE: doc.SUPPLY_TYPE,
    raw2a.DOC_DATE: doc.BILL_DATE,
    raw2a.DOC_VALUE: doc.DOC_VALUE,
    raw2a.POS: doc.POS,
    raw2a.OTHER_PERIOD: doc.OTHER_RETURN_PERIOD,
    raw2a.AMEND_TYPE: doc.AMENDMENT_TYPE,
    raw2a.REVERSE_CHARGE: doc.REVERSE_CHARGE,
    raw2a.DIFF_PERCENT: doc.DIFF_PERCENTAGE,
    raw2a.IRN_SOURCE: doc.IRN_SOURCE,
    raw2a.IRN: doc.IRN_NUMBER,
    raw2a.IRN_DATE: doc.IRN_GEN_DATE,
}

ORIGINAL_KEYS_2A = {
    raw2a.ORIGINAL_DOC_NUMBER: doc.ORIGINAL_BILL_NO,
    raw2a.ORIGINAL_DOC_DATE: doc.ORIGINAL_BILL_DATE,
}


def get_invoice_details_2a(invoice, gstr):
    details = take(invoice, KEYS_2A)

    decode(details, doc.SUPPLY_TYPE, GST_CATEGORY)
    details[doc.BILL_DATE] = parse_datetime(details[doc.BILL_DATE], day_first=True)
    decode(details, doc.POS, STATES)
    details[doc.OTHER_RETURN_PERIOD] = to_period(details[doc.OTHER_RETURN_PERIOD])
    decode(details, doc.AMENDMENT_TYPE, AMEND_TYPE)
    decode(details, doc.REVERSE_CHARGE, Y_N_TO_CHECK)
    decode(details, doc.DIFF_PERCENTAGE, DIFF_PERCENT)
    details[doc.IRN_GEN_DATE] = parse_datetime(details[doc.IRN_GEN_DATE], day_first=True)
    details[doc.DOC_TYPE] = "Invoice"

    return details


def get_amended_invoice_details_2a(invoice, gstr):
    return add_original_details(get_invoice_details_2a(invoice, gstr), invoice, ORIGINAL_KEYS_2A)


KEYS_2B = {
    raw2b.DOC_NUMBER: doc.BILL_NO,
    raw2b.INVOICE_TYPE: doc.SUPPLY_TYPE,
    raw2b.DOC_DATE: doc.BILL_DATE,
    raw2b.TAXABLE_VALUE: doc.TAXABLE_VALUE,
    raw2b.IGST: doc.IGST,
    raw2b.CGST: doc.CGST,
    raw2b.SGST: doc.SGST,
    raw2b.CESS: doc.CESS,
    raw2b.DOC_VALUE: doc.DOC_VALUE,
    raw2b.POS: doc.POS,
    raw2b.REVERSE_CHARGE: doc.REVERSE_CHARGE,
    raw2b.ITC_AVAILABILITY: doc.ITC_AVAILABILITY,
    raw2b.ITC_REASON: doc.ITC_REASON,
    raw2b.DIFF_PERCENT: doc.DIFF_PERCENTAGE,
    raw2b.IRN_SOURCE: doc.IRN_SOURCE,
    raw2b.IRN: doc.IRN_NUMBER,
    raw2b.IRN_DATE: doc.IRN_GEN_DATE,
}

ORIGINAL_KEYS_2B = {
    raw2b.ORIGINAL_DOC_NUMBER: doc.ORIGINAL_BILL_NO,
    raw2b.ORIGINAL_DOC_DATE: doc.ORIGINAL_BILL_DATE,
}

# 2B tells why credit is blocked
ITC_AVAILABILITY = {**YES_NO, "T": "Temporary"}
ITC_REASONS = {
    "P": "POS and supplier state are same but recipient state is different",
    "C": "Return filed post annual cut-off",
}


def get_invoice_details_2b(invoice, gstr):
    details = take(invoice, KEYS_2B)

    decode(details, doc.SUPPLY_TYPE, GST_CATEGORY)
    details[doc.BILL_DATE] = parse_datetime(details[doc.BILL_DATE], day_first=True)
    decode(details, doc.POS, STATES)
    decode(details, doc.REVERSE_CHARGE, Y_N_TO_CHECK)
    decode(details, doc.ITC_AVAILABILITY, ITC_AVAILABILITY)
    decode(details, doc.ITC_REASON, ITC_REASONS)
    decode(details, doc.DIFF_PERCENTAGE, DIFF_PERCENT)
    details[doc.IRN_GEN_DATE] = parse_datetime(details[doc.IRN_GEN_DATE], day_first=True)
    details[doc.DOC_TYPE] = "Invoice"

    return details


def get_amended_invoice_details_2b(invoice, gstr):
    return add_original_details(get_invoice_details_2b(invoice, gstr), invoice, ORIGINAL_KEYS_2B)
