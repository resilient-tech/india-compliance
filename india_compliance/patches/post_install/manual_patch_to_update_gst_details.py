import frappe

from india_compliance.patches.post_install.improve_item_tax_template import (
    TRANSACTION_ITEM_DOCTYPES,
    get_indian_companies,
    update_gst_details_for_transactions,
    update_gst_treatment_for_transactions,
)
from india_compliance.patches.post_install.set_gst_tax_type import (
    execute as set_gst_tax_type,
)
from india_compliance.patches.post_install.set_gst_tax_type_in_journal_entry import (
    execute as set_gst_tax_type_in_journal_entry,
)


def execute():
    reset_gst_treatment()
    set_gst_tax_type()
    set_gst_tax_type_in_journal_entry()
    update_gst_treatment_for_transactions()

    companies = get_indian_companies()
    update_gst_details_for_transactions(companies)


def reset_gst_treatment():
    for item_doctype in TRANSACTION_ITEM_DOCTYPES:
        # GST Treatment is not required in Material Request Item
        if item_doctype == "Material Request Item":
            continue

        table = frappe.qb.DocType(item_doctype)
        frappe.qb.update(table).set(table.gst_treatment, "").run()
