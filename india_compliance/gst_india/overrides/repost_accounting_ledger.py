import frappe


def before_submit(doc, method=None):
    frappe.flags.through_repost_accounting_ledger = True
