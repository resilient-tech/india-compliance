import frappe
from frappe.query_builder import Case

from india_compliance.income_tax_india.constants import NEW_TDS_SECTION, get_tds_section_value


def execute():
    """
    Update tds_section in Tax Withholding Category to 'code - section' format.
    This updates only records where tds_section exactly matches the code.
    """
    twc = frappe.qb.DocType("Tax Withholding Category")
    section_case = Case()
    codes_to_update = []

    for code, (section, _description) in NEW_TDS_SECTION.items():
        if not section:
            continue

        formatted_section = get_tds_section_value(code)

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
