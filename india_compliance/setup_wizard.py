import frappe
from frappe import _

from india_compliance.audit_trail.utils import enable_audit_trail
from india_compliance.gst_india.overrides.party import validate_pan
from india_compliance.gst_india.utils import guess_gst_category, is_api_enabled
from india_compliance.gst_india.utils.gstin_info import get_gstin_info

# Setup Wizard


def get_setup_wizard_stages(params=None):
    if frappe.db.exists("Company"):
        return []

    stages = [
        {
            "status": _("Wrapping up"),
            "fail_msg": _("Failed to enable Audit Trail"),
            "tasks": [
                {
                    "fn": configure_audit_trail,
                    "args": params,
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
                    "args": params,
                    "fail_msg": _("Failed to Update Company GSTIN"),
                }
            ],
        },
    ]

    return stages


# A utility functions to perform task on setup wizard stages
def configure_audit_trail(params):
    if params.enable_audit_trail:
        enable_audit_trail()


def setup_company_gstin_details(params):
    if not params.company_gstin:
        return

    if not (params.company_name or frappe.db.exists("Company", params.company_name)):
        return

    gstin_info = frappe._dict()
    if can_fetch_gstin_info():
        gstin_info = get_gstin_info(params.company_gstin, throw_error=False)

    update_company_info(params, gstin_info.gst_category)
    create_address(gstin_info)


def update_company_info(params, gst_category=None):
    if not gst_category:
        gst_category = guess_gst_category(params.company_gstin, params.country)

    company_doc = frappe.get_cached_doc("Company", params.company_name)
    company_doc.gstin = params.company_gstin
    company_doc.gst_category = gst_category
    validate_pan(company_doc)

    company_doc.save()


def create_address(gstin_info: dict) -> None:
    if not gstin_info.permanent_address:
        return

    address = frappe.new_doc("Address")
    address.append(
        "links", {"link_doctype": "Company", "link_name": gstin_info.business_name}
    )

    for key, value in gstin_info.permanent_address.items():
        setattr(address, key, value)

    address.gstin = gstin_info.gstin
    address.gst_category = gstin_info.gst_category

    address.insert()


def can_fetch_gstin_info():
    return is_api_enabled() and not frappe.get_cached_value(
        "GST Settings", None, "sandbox_mode"
    )
