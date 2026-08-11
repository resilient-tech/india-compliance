"""One module per GSTR-1 category.

Each module holds everything about its category and nothing about any other: the portal key table,
the coded values it uses, and one function per direction. Shared steps live in `_shared`.

    reader(gov_data)                 -> {subcategory: {key: row}}
    writer(rows, company_gstin)      -> the portal's shape for that category
"""

from india_compliance.gst_returns.fields.gstr1 import JsonKey

from . import (
    advances,
    b2b,
    b2cl,
    b2cs,
    cdnr,
    cdnur,
    doc_issue,
    exports,
    hsn,
    nil_rated,
    summary,
    supecom,
)
from ._shared import strip_empty

__all__ = ["SECTIONS", "strip_empty"]

# portal json key -> how to read it, and how to write it back (summary is read only)
SECTIONS = {
    JsonKey.B2B.value: (b2b.to_canonical, b2b.to_gov),
    JsonKey.B2CL.value: (b2cl.to_canonical, b2cl.to_gov),
    JsonKey.EXP.value: (exports.to_canonical, exports.to_gov),
    JsonKey.B2CS.value: (b2cs.to_canonical, b2cs.to_gov),
    JsonKey.NIL_EXEMPT.value: (nil_rated.to_canonical, nil_rated.to_gov),
    JsonKey.CDNR.value: (cdnr.to_canonical, cdnr.to_gov),
    JsonKey.CDNUR.value: (cdnur.to_canonical, cdnur.to_gov),
    JsonKey.HSN.value: (hsn.to_canonical, hsn.to_gov),
    JsonKey.DOC_ISSUE.value: (doc_issue.to_canonical, doc_issue.to_gov),
    JsonKey.AT.value: (advances.received_to_canonical, advances.received_to_gov),
    JsonKey.TXP.value: (advances.adjusted_to_canonical, advances.adjusted_to_gov),
    JsonKey.SUPECOM.value: (supecom.to_canonical, supecom.to_gov),
    JsonKey.RET_SUM.value: (summary.to_canonical, None),
}
