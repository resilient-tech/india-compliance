import frappe
from frappe import _

from india_compliance.income_tax_india.constants import NEW_TDS_SECTION, get_tds_section_value


def on_change(doc, method=None):
    frappe.cache.delete_value("tax_withholding_accounts")


def validate(doc, method=None):
    if not doc.tds_section:
        return

    valid_values = get_valid_tds_section_values()
    if doc.tds_section in valid_values:
        return

    frappe.throw(_("Invalid TDS Section '{0}'.").format(doc.tds_section))


def get_valid_tds_section_values() -> set[str]:
    return {get_tds_section_value(code) for code in NEW_TDS_SECTION}


@frappe.whitelist()
def search_tds_sections(
    doctype: str,
    txt: str,
    searchfield: str,
    start: int,
    page_len: int,
    filters: dict,
    **kwargs,
):
    txt = (txt or "").strip().casefold()
    all_options = []
    filtered_options = []

    for code, (_section, description) in NEW_TDS_SECTION.items():
        value = get_tds_section_value(code)

        option = {
            "label": value,
            "value": value,
            "description": description,
        }
        all_options.append(option)

        if not txt or txt in f"{value} {description or ''}".casefold():
            filtered_options.append(option)

    options = filtered_options or all_options
    return sorted(options, key=lambda d: d["value"])


def get_tax_withholding_accounts(company):
    def _get_tax_withholding_accounts():
        return set(frappe.get_all("Tax Withholding Account", pluck="account", filters={"company": company}))

    return frappe.cache.hget("tax_withholding_accounts", company, generator=_get_tax_withholding_accounts)


def get_tax_id_for_party(party_type, party):
    # PAN field is only available for Customer and Supplier.
    if party_type in ("Customer", "Supplier"):
        return frappe.db.get_value(party_type, party, "pan")

    return ""
