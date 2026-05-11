import frappe
from frappe.query_builder import Case

from india_compliance.income_tax_india.constants import NEW_TDS_SECTIONS, get_tds_section_value


def execute():
    """
    Update tds_section in Tax Withholding Category with section names.
    """
    twc = frappe.qb.DocType("Tax Withholding Category")
    section_case = Case()
    codes_to_update = []

    for entry in NEW_TDS_SECTIONS:
        code = entry["section_code"]
        if not entry["section_name"]:
            continue

        formatted_section = get_tds_section_value(entry)

        section_case = section_case.when(twc.tds_section == code, formatted_section)
        codes_to_update.append(code)

    if not codes_to_update:
        return

    section_case = section_case.else_(twc.tds_section)

    (
        frappe.qb.update(twc)
        .set(twc.tds_section, section_case)
        .where(twc.tds_section.isin(codes_to_update))
        .run()
    )
