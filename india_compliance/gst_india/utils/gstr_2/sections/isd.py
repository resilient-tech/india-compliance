"""Credit distributed by an Input Service Distributor. Amounts sit on the document, no items."""

from india_compliance.gst_india.utils import parse_datetime
from india_compliance.gst_india.utils.gstr_2.gstr import add_original_details, to_period
from india_compliance.gst_returns.fields.gstr2 import (
    AMEND_TYPE,
    ISD_TYPE_2A,
    ISD_TYPE_2B,
    YES_NO,
)
from india_compliance.gst_returns.fields.gstr2 import DocField as doc
from india_compliance.gst_returns.fields.gstr2 import ItemField as item
from india_compliance.gst_returns.fields.gstr2 import RawField2a as raw2a
from india_compliance.gst_returns.fields.gstr2 import RawField2b as raw2b
from india_compliance.gst_returns.steps import decode, set_item_totals, take

# no taxable value is reported against distributed credit
TAX_FIELDS = (doc.IGST, doc.CGST, doc.SGST, doc.CESS)

# "Yes" -> "Y": the rows keep the eligibility as the portal codes it
ITC_ELIGIBILITY_CODE = {value: key for key, value in YES_NO.items()}


def get_document_value(details):
    return sum(details.get(field) or 0 for field in TAX_FIELDS)


KEYS_2A = {
    raw2a.ISD_DOC_TYPE: doc.DOC_TYPE,
    raw2a.ISD_DOC_NUMBER: doc.BILL_NO,
    raw2a.ISD_DOC_DATE: doc.BILL_DATE,
    raw2a.ITC_ELIGIBILITY: doc.ITC_AVAILABILITY,
    raw2a.OTHER_PERIOD: doc.OTHER_RETURN_PERIOD,
    raw2a.AMEND_TYPE: doc.AMENDMENT_TYPE,
    raw2a.IGST: doc.IGST,
    raw2a.CGST: doc.CGST,
    raw2a.SGST: doc.SGST,
    raw2a.ISD_CESS: doc.CESS,
}


def get_document_details_2a(document, gstr):
    details = take(document, KEYS_2A)

    decode(details, doc.DOC_TYPE, ISD_TYPE_2A)
    details[doc.BILL_DATE] = parse_datetime(details[doc.BILL_DATE], day_first=True)
    decode(details, doc.ITC_AVAILABILITY, YES_NO)
    details[doc.OTHER_RETURN_PERIOD] = to_period(details[doc.OTHER_RETURN_PERIOD])
    details[doc.IS_AMENDED] = 1 if document.get(raw2a.AMEND_TYPE) else 0
    decode(details, doc.AMENDMENT_TYPE, AMEND_TYPE)
    details[doc.DOC_VALUE] = get_document_value(details)

    return details


KEYS_2B = {
    raw2b.ISD_DOC_TYPE: doc.DOC_TYPE,
    raw2b.ISD_DOC_NUMBER: doc.BILL_NO,
    raw2b.ISD_DOC_DATE: doc.BILL_DATE,
    raw2b.ITC_ELIGIBILITY: doc.ITC_AVAILABILITY,
    raw2b.IGST: doc.IGST,
    raw2b.CGST: doc.CGST,
    raw2b.SGST: doc.SGST,
    raw2b.CESS: doc.CESS,
}

ORIGINAL_KEYS_2B = {
    raw2b.ORIGINAL_ISD_DOC_NUMBER: doc.ORIGINAL_BILL_NO,
    raw2b.ORIGINAL_ISD_DOC_DATE: doc.ORIGINAL_BILL_DATE,
    raw2b.ORIGINAL_ISD_DOC_TYPE: doc.ORIGINAL_DOC_TYPE,
}


def get_document_details_2b(document, gstr):
    details = take(document, KEYS_2B)

    decode(details, doc.DOC_TYPE, ISD_TYPE_2B)
    details[doc.BILL_DATE] = parse_datetime(details[doc.BILL_DATE], day_first=True)
    decode(details, doc.ITC_AVAILABILITY, YES_NO)
    details[doc.DOC_VALUE] = get_document_value(details)

    return details


def get_amended_document_details_2b(document, gstr):
    details = add_original_details(get_document_details_2b(document, gstr), document, ORIGINAL_KEYS_2B)
    decode(details, doc.ORIGINAL_DOC_TYPE, ISD_TYPE_2B)

    return details


def as_item(transaction):
    """The document's own amounts become its single row, carrying the eligibility that decides how
    the rows of one document fold together."""
    return {
        **{field: transaction.get(field) for field in TAX_FIELDS},
        item.ITC_ELIGIBILITY: ITC_ELIGIBILITY_CODE.get(transaction.get(doc.ITC_AVAILABILITY)),
    }


def group_documents(transactions):
    """Rule 39(1)(b): an ISD passes on the eligible and the ineligible credit of one document
    separately, and the portal reports each part under the same document number. They are one
    document -- kept apart, the second part overwrites the first, since an inward supply is keyed
    by supplier, number and document type."""
    grouped = {}

    for transaction in transactions:
        transaction[doc.ITEMS] = [as_item(transaction)]
        key = (transaction.get(doc.BILL_NO), transaction.get(doc.DOC_TYPE), transaction.get(doc.BILL_DATE))

        if existing := grouped.get(key):
            existing[doc.ITEMS].extend(transaction[doc.ITEMS])
            continue

        grouped[key] = transaction

    for transaction in grouped.values():
        set_item_totals(transaction, transaction[doc.ITEMS], TAX_FIELDS)
        transaction[doc.DOC_VALUE] = get_document_value(transaction)

        # any eligible row makes the document's credit available
        transaction[doc.ITC_AVAILABILITY] = (
            YES_NO["Y"]
            if any(row[item.ITC_ELIGIBILITY] == "Y" for row in transaction[doc.ITEMS])
            else YES_NO["N"]
        )

    return list(grouped.values())
