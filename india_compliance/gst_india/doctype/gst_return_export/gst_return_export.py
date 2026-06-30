# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class GSTReturnExport(Document):
    """
    GST Return Export tool — Phase 1 (GSTR-2A / 2B).

    Milestone 1: scaffolding only. This Single DocType holds the user's filter
    selection (company, GSTIN, GST return, period). The actual behaviour lands
    in later milestones:
      - Sync from GSTN  -> M3 (single period), M6 (range)
      - Prepared summary -> M4
      - Export to Excel  -> M5
    Raw GSTN payloads are persisted via india_compliance.gst_india.utils.returns_export.
    """

    pass
