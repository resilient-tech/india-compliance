import frappe
from frappe.query_builder import Case

from india_compliance.income_tax_india.overrides.company import (
    create_or_update_tax_withholding_category,
)

# (old_section, entity_type) -> new_code
OLD_TO_NEW = {
    ("192A", "Individual"): "1004",
    ("192A", "No PAN / Invalid PAN"): "1004",
    ("193", "Individual"): "1019",
    ("193", "Company"): "1019",
    ("193", "No PAN / Invalid PAN"): "1019",
    ("194", "Individual"): "1029",
    ("194", "Company"): "1029",
    ("194", "No PAN / Invalid PAN"): "1029",
    ("194A", "Individual"): "1022",
    ("194A", "Company"): "1022",
    ("194A", "No PAN / Invalid PAN"): "1022",
    ("194B", "Individual"): "1058",
    ("194B", "Company"): "1058",
    ("194B", "No PAN / Invalid PAN"): "1058",
    ("194BB", "Individual"): "1062",
    ("194BB", "Company"): "1062",
    ("194BB", "No PAN / Invalid PAN"): "1062",
    ("194C", "Individual"): "1023",
    ("194C", "Company"): "1024",
    ("194C", "No PAN / Invalid PAN"): "1024",
    ("194D", "Individual"): "1005",
    ("194D", "Company"): "1005",
    ("194D", "Company Assessee"): "1005",
    ("194D", "No PAN / Invalid PAN"): "1005",
    ("194DA", "Individual"): "1030",
    ("194DA", "Company"): "1030",
    ("194DA", "No PAN / Invalid PAN"): "1030",
    ("194EE", "Individual"): "1066",
    ("194EE", "Company"): "1066",
    ("194EE", "No PAN / Invalid PAN"): "1066",
    ("194G", "Individual"): "1063",
    ("194G", "Company"): "1063",
    ("194G", "No PAN / Invalid PAN"): "1063",
    ("194H", "Individual"): "1006",
    ("194H", "Company"): "1006",
    ("194H", "No PAN / Invalid PAN"): "1006",
    ("194I(a)", "Individual"): "1008",
    ("194I(a)", "Company"): "1008",
    ("194I(a)", "No PAN / Invalid PAN"): "1008",
    ("194I(b)", "Individual"): "1009",
    ("194I(b)", "Company"): "1009",
    ("194I(b)", "No PAN / Invalid PAN"): "1009",
    ("194IA", "Individual"): "1012",
    ("194IA", "Company"): "1012",
    ("194IA", "No PAN / Invalid PAN"): "1012",
    ("194JA", "Individual"): "1026",
    ("194JA", "Company"): "1026",
    ("194JA", "No PAN / Invalid PAN"): "1026",
    ("194JB", "Individual"): "1027",
    ("194JB", "Company"): "1027",
    ("194JB", "No PAN / Invalid PAN"): "1027",
    ("194LA", "Individual"): "1012",
    ("194LA", "Company"): "1012",
    ("194LA", "No PAN / Invalid PAN"): "1012",
    ("194LBB", "Individual"): "1017",
    ("194LBB", "Company"): "1017",
    ("194LBB", "No PAN / Invalid PAN"): "1017",
    ("194Q", "Individual"): "1031",
    ("194Q", "Company"): "1031",
    ("194Q", "No PAN / Invalid PAN"): "1031",
}


def execute():
    twc = frappe.qb.DocType("Tax Withholding Category")

    (
        frappe.qb.update(twc)
        .set(twc.old_income_tax_section, twc.tds_section)
        .where(twc.tds_section.isnotnull())
        .where(twc.tds_section != "")
        .run()
    )

    section_case = Case()
    for (old_section, entity_type), new_code in OLD_TO_NEW.items():
        section_case = section_case.when(
            (twc.tds_section == old_section) & (twc.entity_type == entity_type),
            new_code,
        )
    section_case = section_case.else_(twc.tds_section)

    (
        frappe.qb.update(twc)
        .set(twc.tds_section, section_case)
        .where(twc.tds_section.isnotnull())
        .where(twc.tds_section != "")
        .run()
    )

    company_list = frappe.get_all("Company", filters={"country": "India"}, pluck="name", order_by="lft asc")
    for company in company_list:
        create_or_update_tax_withholding_category(company)
