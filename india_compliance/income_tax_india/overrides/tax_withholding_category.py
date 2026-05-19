import frappe

from india_compliance.income_tax_india.constants import (
    NEW_TDS_SECTIONS,
    get_tds_section_value,
)

ALL_TDS_OPTIONS = [
    {
        "label": get_tds_section_value(e),
        "value": get_tds_section_value(e),
        "description": e.get("description", ""),
    }
    for e in NEW_TDS_SECTIONS
]


def on_change(doc, method=None):
    frappe.cache.delete_value("tax_withholding_accounts")


@frappe.whitelist()
def search_tds_sections(
    doctype: str | None = None,
    txt: str | None = None,
    searchfield: str | None = None,
    start: int = 0,
    page_len: int = 20,
    filters: dict | None = None,
    **kwargs,
):
    txt = (txt or "").strip().casefold()

    if txt:
        matched = [row for row in ALL_TDS_OPTIONS if txt in f"{row['value']} {row['description']}".casefold()]
    else:
        matched = ALL_TDS_OPTIONS

    # Fall back to all options so saved values always validate in autocomplete
    options = matched or ALL_TDS_OPTIONS
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
