import frappe

from india_compliance.income_tax_india.constants import TDS_ENTITY_TYPE, TDS_SECTIONS


def execute():
    docs = frappe.db.get_all("Tax Withholding Category", pluck="name")
    for d in docs:
        splitted_name = d.split(" - ")
        # old naming [TDS - SECTION - ENTITY]
        if len(splitted_name) < 3:
            continue

        if splitted_name[1] in TDS_SECTIONS and splitted_name[-1] in TDS_ENTITY_TYPE:
            frappe.db.set_value(
                "Tax Withholding Category",
                d,
                {"tds_section": splitted_name[1], "entity_type": splitted_name[-1]},
            )
