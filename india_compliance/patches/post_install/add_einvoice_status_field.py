import frappe
from frappe.utils import sbool


def execute():
    # Sales Invoice should have field signed_einvoice
    # and E Invoice Settings should be enabled

    if not frappe.db.has_column("Sales Invoice", "signed_einvoice") or not sbool(
        frappe.db.get_value(
            "E Invoice Settings", "E Invoice Settings", "enable", ignore=True
        )
    ):
        set_not_applicable_status()
        return

    set_pending_status()
    set_generated_status()
    set_cancelled_status()
    set_not_applicable_status()


def set_pending_status():
    filters = {
        "docstatus": ["=", 1],
        "einvoice_status": ["is", "not set"],
        "posting_date": [">=", "2021-04-01"],
        "irn": ["is", "not set"],
        "billing_address_gstin": ["!=", "company_gstin"],
        "gst_category": [
            "in",
            ["Registered Regular", "SEZ", "Overseas", "Deemed Export"],
        ],
    }

    frappe.db.set_value("Sales Invoice", filters, "einvoice_status", "Pending")


def set_generated_status():
    filters = {
        "docstatus": ["!=", 0],
        "einvoice_status": ["is", "not set"],
        "irn": ["is", "set"],
        "irn_cancelled": ["=", 0],
    }

    frappe.db.set_value("Sales Invoice", filters, "einvoice_status", "Generated")


def set_cancelled_status():
    filters = {
        "docstatus": ["!=", 0],
        "einvoice_status": ["is", "not set"],
        "irn_cancelled": ["=", 1],
    }

    frappe.db.set_value("Sales Invoice", filters, "einvoice_status", "Cancelled")


def set_not_applicable_status():
    filters = {
        "docstatus": ["!=", 0],
        "einvoice_status": ["is", "not set"],
        "irn": ["is", "not set"],
    }

    frappe.db.set_value("Sales Invoice", filters, "einvoice_status", "Not Applicable")
