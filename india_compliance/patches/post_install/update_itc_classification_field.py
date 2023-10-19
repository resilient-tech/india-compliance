import frappe
from frappe.query_builder.functions import IfNull

from india_compliance.gst_india.utils.custom_fields import delete_old_fields


def execute():
    patch_field_in_purchase_invoice()
    patch_journal_entry()

    delete_old_fields("eligibility_for_itc", "Purchase Invoice")
    delete_old_fields("reversal_type", "Journal Entry")


def patch_field_in_purchase_invoice():
    if "eligibility_for_itc" not in frappe.db.get_table_columns("Purchase Invoice"):
        return

    doctype = frappe.qb.DocType("Purchase Invoice")
    depricated_eligibility_for_itc = (
        "Ineligible As Per Section 17(5)",
        "Ineligible Others",
    )
    (
        frappe.qb.update(doctype)
        .set(doctype.itc_classification, doctype.eligibility_for_itc)
        .where(doctype.eligibility_for_itc.notin(depricated_eligibility_for_itc))
        .run()
    )
    (
        frappe.qb.update(doctype)
        .set(doctype.itc_classification, "All Other ITC")
        .where(IfNull(doctype.itc_classification, "") == "")
        .run()
    )
    (
        frappe.qb.update(doctype)
        .set(doctype.ineligibility_reason, "Ineligible As Per Section 17(5)")
        .where(doctype.eligibility_for_itc.isin(depricated_eligibility_for_itc))
        .run()
    )


def patch_journal_entry():
    if "reversal_type" not in frappe.db.get_table_columns("Journal Entry"):
        return

    doctype = frappe.qb.DocType("Journal Entry")
    (
        frappe.qb.update(doctype)
        .set(doctype.reversal_type, doctype.ineligibility_reason)
        .where(IfNull(doctype.reversal_type, "") != "")
        .run()
    )
