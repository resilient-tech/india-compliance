"""Bills of entry for imports. Goods from overseas come flat; goods from SEZ name the supplier."""

from india_compliance.gst_india.utils import parse_datetime
from india_compliance.gst_returns.fields.gstr2 import Y_N_TO_CHECK
from india_compliance.gst_returns.fields.gstr2 import DocField as doc
from india_compliance.gst_returns.fields.gstr2 import RawField2a as raw2a
from india_compliance.gst_returns.fields.gstr2 import RawField2b as raw2b
from india_compliance.gst_returns.steps import decode, take

KEYS_2A = {
    raw2a.BOE_NUMBER: doc.BILL_NO,
    raw2a.BOE_DATE: doc.BILL_DATE,
    raw2a.IS_AMENDED: doc.IS_AMENDED,
    raw2a.PORT_CODE: doc.PORT_CODE,
    raw2a.TAXABLE_VALUE: doc.TAXABLE_VALUE,
    raw2a.IGST: doc.IGST,
    raw2a.CESS: doc.CESS,
}

SEZ_KEYS_2A = {
    raw2a.SEZ_GSTIN: doc.SUPPLIER_GSTIN,
    raw2a.SEZ_TRADE_NAME: doc.SUPPLIER_NAME,
}


def get_entry_details_2a(entry, gstr):
    details = {doc.DOC_TYPE: "Bill of Entry", **take(entry, KEYS_2A)}

    details[doc.BILL_DATE] = parse_datetime(details[doc.BILL_DATE], day_first=True)
    decode(details, doc.IS_AMENDED, Y_N_TO_CHECK)
    details[doc.DOC_VALUE] = (
        (details[doc.TAXABLE_VALUE] or 0) + (details[doc.IGST] or 0) + (details[doc.CESS] or 0)
    )

    return details


def get_sez_entry_details_2a(entry, gstr):
    details = get_entry_details_2a(entry, gstr)
    details.update(take(entry, SEZ_KEYS_2A))

    return details


KEYS_2B = {
    raw2b.BOE_NUMBER: doc.BILL_NO,
    raw2b.BOE_DATE: doc.BILL_DATE,
    raw2b.IS_AMENDED: doc.IS_AMENDED,
    raw2b.PORT_CODE: doc.PORT_CODE,
    raw2b.TAXABLE_VALUE: doc.TAXABLE_VALUE,
    raw2b.IGST: doc.IGST,
    raw2b.CESS: doc.CESS,
}


def get_entry_details_2b(entry, gstr):
    details = {doc.DOC_TYPE: "Bill of Entry", **take(entry, KEYS_2B)}

    details[doc.BILL_DATE] = parse_datetime(details[doc.BILL_DATE], day_first=True)
    decode(details, doc.IS_AMENDED, Y_N_TO_CHECK)
    details[doc.DOC_VALUE] = (
        (details[doc.TAXABLE_VALUE] or 0) + (details[doc.IGST] or 0) + (details[doc.CESS] or 0)
    )
    details[doc.ITC_AVAILABILITY] = "Yes"  # always available on imports

    return details
