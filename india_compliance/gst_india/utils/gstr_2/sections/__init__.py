"""One module per GSTR-2A/2B category: the key tables and per-document details.

2A and 2B are read-only: the portal payload becomes GST Inward Supply rows, and the payload
itself is kept in the return log's raw data, so there is no write-back direction here.
"""

from india_compliance.gst_returns.fields.gstr2 import RawField2a as raw2a
from india_compliance.gst_returns.fields.gstr2 import RawField2b as raw2b

from . import b2b, cdnr, impg, isd, tds_tcs

# category: (get_details, list the documents sit in or None for flat records, has items)
SECTIONS_2A = {
    "B2B": (b2b.get_invoice_details_2a, raw2a.INVOICES, True),
    "B2BA": (b2b.get_amended_invoice_details_2a, raw2a.INVOICES, True),
    "CDNR": (cdnr.get_note_details_2a, raw2a.NOTES, True),
    "CDNRA": (cdnr.get_amended_note_details_2a, raw2a.NOTES, True),
    "ISD": (isd.get_document_details_2a, raw2a.ISD_DOCS, False),
    "ISDA": (isd.get_document_details_2a, raw2a.ISD_DOCS, False),
    "IMPG": (impg.get_entry_details_2a, None, False),
    "IMPGSEZ": (impg.get_sez_entry_details_2a, None, False),
    "ECOM": (b2b.get_invoice_details_2a, raw2a.INVOICES, True),
    "ECOMA": (b2b.get_amended_invoice_details_2a, raw2a.INVOICES, True),
    "TDS": (tds_tcs.get_tds_details, None, False),
    "TCS": (tds_tcs.get_tcs_details, None, False),
}

SECTIONS_2B = {
    "B2B": (b2b.get_invoice_details_2b, raw2b.INVOICES, True),
    "B2BA": (b2b.get_amended_invoice_details_2b, raw2b.INVOICES, True),
    "CDNR": (cdnr.get_note_details_2b, raw2b.NOTES, True),
    "CDNRA": (cdnr.get_amended_note_details_2b, raw2b.NOTES, True),
    "ISD": (isd.get_document_details_2b, raw2b.ISD_DOCS, False),
    "ISDA": (isd.get_amended_document_details_2b, raw2b.ISD_DOCS, False),
    "ECOM": (b2b.get_invoice_details_2b, raw2b.INVOICES, True),
    "ECOMA": (b2b.get_amended_invoice_details_2b, raw2b.INVOICES, True),
    "IMPG": (impg.get_entry_details_2b, None, False),
    "IMPGSEZ": (impg.get_entry_details_2b, raw2b.BOE_DOCS, False),
}
