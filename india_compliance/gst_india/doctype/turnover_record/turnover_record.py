# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
from erpnext.accounts.utils import get_fiscal_year
from frappe import _
from frappe.model.document import Document
from frappe.model.meta import get_field_precision
from frappe.model.naming import make_autoname
from frappe.query_builder.functions import Sum
from frappe.utils import add_years, flt, getdate, nowdate

from india_compliance.gst_india.utils import get_state, validate_gstin
from india_compliance.gst_india.utils.gstr_1.gstr_1_data import GSTR1Query


class TurnoverRecord(Document):
    def autoname(self):
        fy_prefix = f"{str(self.from_date)[2:4]}-{str(self.to_date)[2:4]}"
        self.name = make_autoname(f"{fy_prefix} {self.gst_state}.##")

    def validate(self):
        validate_gstin(self.gstin)
        self.validate_and_set_gst_state()
        self.validate_duplicate_record()

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


def get_relevant_period(posting_date=None):
    """
    The "relevant period" is the financial year *preceding* the year in which the credit is
    distributed.
    """
    _, from_date, to_date = get_fiscal_year(posting_date or nowdate())
    return add_years(getdate(from_date), -1), add_years(getdate(to_date), -1)


def get_turnover_amount(gst_state, posting_date=None):
    from_date, to_date = get_relevant_period(posting_date)

    filters = {"gst_state": gst_state, "from_date": ["<=", to_date], "to_date": [">=", from_date]}

    return frappe.db.get_value("Turnover Record", filters, "amount")


def upsert_turnover_record(gstin, gst_state, amount, posting_date=None):
    from_date, to_date = get_relevant_period(posting_date)

    if gstin:
        gst_state = get_state(gstin[:2])

    amount_precision = get_field_precision(frappe.get_meta("Turnover Record").get_field("amount"))
    amount = flt(amount, amount_precision)

    existing_filters = {"gst_state": gst_state, "from_date": ["<=", to_date], "to_date": [">=", from_date]}
    existing = frappe.db.get_value("Turnover Record", existing_filters)

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


def get_turnover_from_sales_invoices(gstin, from_date, to_date, company=None):
    """Used by distribution dialog when no Turnover Records exists"""

    if not gstin:
        return 0

    filters = {"company_gstin": gstin, "from_date": from_date, "to_date": to_date}
    if company:
        filters["company"] = company

    base_query = GSTR1Query(filters).get_base_query()
    amount = frappe.qb.from_(base_query).select(Sum(base_query.taxable_value)).run()[0][0]

    return flt(amount)
