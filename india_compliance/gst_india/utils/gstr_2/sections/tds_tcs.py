"""TDS (GSTR-7) and TCS (GSTR-8) credit. Flat records, one per deductor or operator, no items."""

from india_compliance.gst_india.utils.gstr_2.gstr import take
from india_compliance.gst_returns.fields.gstr2 import DocField as doc
from india_compliance.gst_returns.fields.gstr2 import RawField2a as raw2a

TDS_KEYS = {
    raw2a.DEDUCTOR_GSTIN: doc.SUPPLIER_GSTIN,
    raw2a.DEDUCTOR_NAME: doc.SUPPLIER_NAME,
    raw2a.DEDUCTION_MONTH: doc.SUP_RETURN_PERIOD,
    raw2a.DEDUCTED_VALUE: doc.TAXABLE_VALUE,
    raw2a.IGST: doc.IGST,
    raw2a.CGST: doc.CGST,
    raw2a.SGST: doc.SGST,
}

TCS_KEYS = {
    raw2a.ECOM_GSTIN: doc.SUPPLIER_GSTIN,
    raw2a.TCS_TAXABLE_VALUE: doc.TAXABLE_VALUE,
    raw2a.IGST: doc.IGST,
    raw2a.CGST: doc.CGST,
    raw2a.SGST: doc.SGST,
    raw2a.CESS: doc.CESS,
    raw2a.SUPPLY_VALUE: doc.DOC_VALUE,
}


def get_tds_details(record, gstr):
    details = take(record, TDS_KEYS)
    details[doc.DOC_VALUE] = details[doc.TAXABLE_VALUE]

    return details


def get_tcs_details(record, gstr):
    details = take(record, TCS_KEYS)
    details[doc.SUP_RETURN_PERIOD] = gstr.return_period

    return details
