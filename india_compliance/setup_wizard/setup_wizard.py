import frappe
from frappe import _

from india_compliance.audit_trail.utils import enable_audit_trail
from india_compliance.gst_india.overrides.party import validate_pan
from india_compliance.gst_india.utils import guess_gst_category, is_api_enabled
from india_compliance.gst_india.utils.gstin_info import get_gstin_info

# Setup Wizard


def get_setup_wizard_stages(args=None):
    if frappe.db.exists("Company"):
        return []

    stages = [
        {
            "status": _("Wrapping up"),
            "fail_msg": _("Failed to enable Audit Trail"),
            "tasks": [
                {
                    "fn": configure_audit_trail,
                    "args": args,
                    "fail_msg": _("Failed to enable Audit Trail"),
                }
            ],
        },
        {
            "status": _("Wrapping up"),
            "fail_msg": _("Failed to Update Company GSTIN"),
            "tasks": [
                {
                    "fn": setup_company_gstin_details,
                    "args": args,
                    "fail_msg": _("Failed to Update Company GSTIN"),
                }
            ],
        },
    ]

    return stages


# A utility functions to perform task on setup wizard stages


def configure_audit_trail(setup_args):
    if setup_args.enable_audit_trail:
        enable_audit_trail()


def setup_company_gstin_details(setup_args):
    if not setup_args.company_gstin:
        return

    company_doc = frappe.get_cached_doc("Company", setup_args.company_name)
    company_doc.gstin = setup_args.company_gstin
    company_doc.gst_category = guess_gst_category(setup_args.company_gstin)
    validate_pan(company_doc)
    company_doc.save()

    if not is_api_enabled() or frappe.get_cached_value(
        "GST Settings", None, "sandbox_mode"
    ):
        return

    gstin_info = get_gstin_info(setup_args.company_gstin)
    if gstin_info.permanent_address:
        create_address(setup_args.company_name, gstin_info.permanent_address)


def create_address(company_name: str, address: dict) -> None:
    address = frappe.new_doc("Address")
    address.append("links", {"link_doctype": "Company", "link_name": company_name})

    for key, value in address.items():
        setattr(address, key, value)
    address.insert()
