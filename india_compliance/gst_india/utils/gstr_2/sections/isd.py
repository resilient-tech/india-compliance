"""Credit distributed by an Input Service Distributor. No rate-wise breakup is reported: the eligible
and the ineligible part of one document arrive as separate rows, and fold into one document with a
row each."""

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
from india_compliance.gst_returns.steps import decode, flip, set_item_totals, take

# the amounts the portal reports against distributed credit; no taxable value, and the item rows
# carry the same field names as the document
TAX_FIELDS = (doc.IGST, doc.CGST, doc.SGST, doc.CESS)

# the rows keep the eligibility under the portal's own name and code
ELIGIBILITY_CODE = flip(YES_NO)


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
    """One part of a document, as its own row: the amounts it contributes and the eligibility they
    were distributed under."""
    return {
        **{field: transaction.get(field) for field in TAX_FIELDS},
        item.ITC_ELIGIBILITY: ELIGIBILITY_CODE.get(transaction.get(doc.ITC_AVAILABILITY)),
    }


def document_key(transaction):
    """What makes two rows parts of one document. Matches how an inward supply is keyed, plus the
    date, so a re-used number in another period stays separate."""
    return (
        transaction.get(doc.SUPPLIER_GSTIN),
        transaction.get(doc.BILL_NO),
        transaction.get(doc.DOC_TYPE),
        transaction.get(doc.BILL_DATE),
    )


def set_totals(document):
    rows = document[doc.ITEMS]

    # an unsplit document re-sums its single row to the value it already had
    set_item_totals(document, rows, TAX_FIELDS)
    document[doc.DOC_VALUE] = get_document_value(document)


def fold_parts(transactions):
    """Rule 39(1)(b): an ISD passes on the eligible and the ineligible credit of one document
    separately, and the portal reports each part under the same document number. Left apart they
    would collide on the inward supply key and the second part would overwrite the first."""
    documents = {}

    for transaction in transactions:
        row = as_item(transaction)
        key = document_key(transaction)

        if document := documents.get(key):
            document[doc.ITEMS].append(row)
            continue

        transaction[doc.ITEMS] = [row]
        documents[key] = transaction

    for document in documents.values():
        set_totals(document)

    return list(documents.values())
