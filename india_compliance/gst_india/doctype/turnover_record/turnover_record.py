# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
from erpnext.accounts.utils import get_fiscal_year
from frappe import _
from frappe.model.document import Document
from frappe.model.meta import get_field_precision
from frappe.model.naming import make_autoname
from frappe.utils import flt, nowdate

from india_compliance.gst_india.utils import get_state, validate_gstin


class TurnoverRecord(Document):
    def autoname(self):
        fy_prefix = f"{str(self.from_date)[2:4]}-{str(self.to_date)[2:4]}"
        self.name = make_autoname(f"{fy_prefix} {self.gst_state}.##")

    def validate(self):
        self.gstin = validate_gstin(self.gstin)
        self.validate_and_set_gst_state()
        self.validate_mandatory()
        self.validate_duplicate_record()

    def validate_mandatory(self):
        # We are already setting gst_state from gstin if gstin is provided.
        if not self.gst_state:
            frappe.throw(_("Either GSTIN or GST State is required"))

    def validate_and_set_gst_state(self):
        if not self.gstin:
            return

        gstin_state = get_state(self.gstin[:2])
        if not self.gst_state:
            self.gst_state = gstin_state
        elif self.gst_state != gstin_state:
            frappe.throw(_("GSTIN does not match the selected GST State"))

    def validate_duplicate_record(self):
        duplicate = frappe.db.exists(
            "Turnover Record",
            {
                "gst_state": self.gst_state,
                "from_date": ["<=", self.to_date],
                "to_date": [">=", self.from_date],
                "name": ["!=", self.name],
            },
        )
        if duplicate:
            frappe.throw(
                _("Turnover record for this state already exists {0}").format(
                    frappe.utils.get_link_to_form("Turnover Record", duplicate)
                )
            )


def upsert_turnover_record(gstin, gst_state, amount, posting_date):
    _fiscal_year, from_date, to_date = get_fiscal_year(posting_date or nowdate())

    if gstin:
        gst_state = get_state(gstin[:2])

    amount_precision = get_field_precision(frappe.get_meta("Turnover Record").get_field("amount"))
    amount = flt(amount, amount_precision)

    existing = frappe.db.get_value(
        "Turnover Record", {"from_date": from_date, "to_date": to_date, "gst_state": gst_state}
    )

    try:
        if existing:
            frappe.db.set_value("Turnover Record", existing, "amount", amount)
        else:
            doc = frappe.new_doc("Turnover Record")
            doc.from_date = from_date
            doc.to_date = to_date
            doc.gstin = gstin
            doc.gst_state = gst_state
            doc.amount = amount
            doc.insert(ignore_permissions=True)
    except Exception:
        frappe.log_error(
            title=_("Turnover Record upsert failed"),
            message=_(
                "Failed to upsert Turnover Record for from_date={0}, to_date={1}, gst_state={2}, gstin={3}"
            ).format(from_date, to_date, gst_state, gstin),
        )
