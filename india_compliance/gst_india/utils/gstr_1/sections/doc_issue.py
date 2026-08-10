"""Documents issued — serial number ranges used in the period, by document kind (table 13).

Portal:    {doc_det: [{doc_num: 1, docs: [{num: 1, from: "1", to: "10", totnum: 10, cancel: 0}]}]}
Canonical: {"Document Issued": {"Invoices for outward supply - 1": {from_sr_no: "1", to_sr_no: "10",
                                                                    total_count: 10, cancelled_count: 0}}}
"""

from india_compliance.gst_returns.fields.gstr1 import DocField as doc
from india_compliance.gst_returns.fields.gstr1 import DocumentNature, SubCategory
from india_compliance.gst_returns.fields.gstr1 import RawField as raw

from . import _shared as s

SUBCATEGORY = SubCategory.DOC_ISSUE.value

KEYS = {
    raw.FROM_SR: doc.FROM_SR,
    raw.TO_SR: doc.TO_SR,
    raw.TOTAL_COUNT: doc.TOTAL_COUNT,
    raw.CANCELLED_COUNT: doc.CANCELLED_COUNT,
    raw.NET_ISSUE: doc.NET_ISSUE,
}

# doc_num -> the kind of document the range covers
DOC_NATURE = {
    1: DocumentNature.OUTWARD_SUPPLY.value,
    2: DocumentNature.INWARD_SUPPLY_UNREGISTERED.value,
    3: DocumentNature.REVISED_INVOICE.value,
    4: DocumentNature.DEBIT_NOTE.value,
    5: DocumentNature.CREDIT_NOTE.value,
    6: DocumentNature.RECEIPT_VOUCHER.value,
    7: DocumentNature.PAYMENT_VOUCHER.value,
    8: DocumentNature.REFUND_VOUCHER.value,
    9: DocumentNature.DELIVERY_CHALLAN_JOB_WORK.value,
    10: DocumentNature.DELIVERY_CHALLAN_APPROVAL.value,
    11: DocumentNature.DELIVERY_CHALLAN_LIQUID_GAS.value,
    12: DocumentNature.DELIVERY_CHALLAN_OTHER.value,
}
DOC_NATURE_CODES = s.flip(DOC_NATURE)

# ranges the report tracks but the portal must not see
NOT_REPORTED = "Excluded from Report"


def to_canonical(gov_data):
    output = {}

    for group in gov_data[raw.DOC_ISSUE_DETAILS]:
        nature = DOC_NATURE.get(group.get(raw.DOC_ISSUE_NUMBER, ""), group.get(raw.DOC_ISSUE_NUMBER, ""))

        for entry in group[raw.DOC_ISSUE_LIST]:
            row = s.with_defaults(s.pick(entry, KEYS), {doc.DOC_TYPE: nature})
            output[" - ".join((nature, entry.get(raw.FROM_SR)))] = (
                row  # keyed "Invoices for outward supply - 1"
            )

    return {SUBCATEGORY: output}


def to_gov(rows, company_gstin=""):
    by_nature = {}

    for row in rows:
        if row[doc.DOC_TYPE].startswith(NOT_REPORTED):
            continue

        by_nature.setdefault(row[doc.DOC_TYPE], []).append(row)

    return {
        raw.DOC_ISSUE_DETAILS: [
            {
                raw.DOC_ISSUE_NUMBER: DOC_NATURE_CODES.get(nature, nature),
                raw.DOC_ISSUE_LIST: [
                    s.with_defaults(s.pick_back(net_issued(row), KEYS), {raw.INDEX: index + 1})
                    for index, row in enumerate(ranges)
                ],
            }
            for nature, ranges in by_nature.items()
        ]
    }


def net_issued(row):
    """Drafts never reached anyone, so count them as cancelled; the rest were issued.

    A new row, so counts do not pile up when the same range is written twice.
    """
    cancelled = (row.get(doc.CANCELLED_COUNT) or 0) + (row.get(doc.DRAFT_COUNT) or 0)

    return {
        **row,
        doc.CANCELLED_COUNT: cancelled,
        doc.NET_ISSUE: row[doc.TOTAL_COUNT] - cancelled,
    }
