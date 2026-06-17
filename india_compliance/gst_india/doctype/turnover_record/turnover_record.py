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


# TODO: index gstin and gst_state in turnover record
#
class TurnoverRecord(Document):
    def autoname(self):
        fy_prefix = f"{str(self.from_date)[2:4]}-{str(self.to_date)[2:4]}"
        self.name = make_autoname(f"{fy_prefix} {self.gst_state}.##")

    def validate(self):
        validate_gstin(self.gstin)
        if self.gstin and get_state(self.gstin[:2]) != self.gst_state:
            # for registered company, gstin and gst gst_state are compulsory and validated
            frappe.throw(_("GSTIN does not match selected gst_state"))

        # TODO: validate one state should have only one turnover


def upsert_turnover_record(
    gstin,
    gst_state,
    amount,
):
    _, from_date, to_date = get_fiscal_year(nowdate())

    amount_precision = get_field_precision(frappe.get_meta("Turnover Record").get_field("amount"))
    amount = flt(amount, amount_precision)

    if gstin:
        filters = {"from_date": from_date, "to_date": to_date, "gstin": gstin}
    else:
        filters = {"from_date": from_date, "to_date": to_date, "gst_state": gst_state, "gstin": ""}

    existing = frappe.db.get_all("Turnover Record", filters=filters, pluck="name", limit=1)
    existing = existing[0] if existing else None

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
