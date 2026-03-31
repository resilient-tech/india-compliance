import frappe
from frappe.query_builder import Case
from frappe.query_builder.functions import IfNull

from india_compliance.income_tax_india.constants import OLD_TDS_SECTIONS, TDS_ENTITY_TYPE

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
    ("194IA", "Individual"): "393(1) Sl.3(i)",
    ("194IA", "Company"): "393(1) Sl.3(i)",
    ("194IA", "No PAN / Invalid PAN"): "393(1) Sl.3(i)",
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
    ("194BA", "Individual"): "1060",
    ("194BA", "Company"): "1060",
    ("194BA", "No PAN / Invalid PAN"): "1060",
    ("194IB", "Individual"): "393(1) Sl.2(i)",
    ("194IB", "Company"): "393(1) Sl.2(i)",
    ("194IB", "No PAN / Invalid PAN"): "393(1) Sl.2(i)",
    ("194IC", "Individual"): "1011",
    ("194IC", "Company"): "1011",
    ("194IC", "No PAN / Invalid PAN"): "1011",
    ("194K", "Individual"): "1013",
    ("194K", "Company"): "1013",
    ("194K", "No PAN / Invalid PAN"): "1013",
    ("194LBA", "Individual"): "1014",
    ("194LBA", "Company"): "1014",
    ("194LBA", "No PAN / Invalid PAN"): "1014",
    ("194LBC", "Individual"): "1018",
    ("194LBC", "Company"): "1018",
    ("194LBC", "No PAN / Invalid PAN"): "1018",
    ("194M", "Individual"): "393(1) Sl.6(ii)",
    ("194M", "Company"): "393(1) Sl.6(ii)",
    ("194M", "No PAN / Invalid PAN"): "393(1) Sl.6(ii)",
    ("194N", "Individual"): "1065",
    ("194N", "Company"): "1065",
    ("194N", "No PAN / Invalid PAN"): "1065",
    ("194O", "Individual"): "1035",
    ("194O", "Company"): "1035",
    ("194O", "No PAN / Invalid PAN"): "1035",
    ("194P", "Individual"): "1032",
    ("194P", "Company"): "1032",
    ("194P", "No PAN / Invalid PAN"): "1032",
    ("194R", "Individual"): "1033",
    ("194R", "Company"): "1033",
    ("194R", "No PAN / Invalid PAN"): "1033",
    ("194S", "Individual"): "1037",
    ("194S", "Company"): "1037",
    ("194S", "No PAN / Invalid PAN"): "1037",
    ("194T", "Individual"): "1067",
    ("194T", "Company"): "1067",
    ("194T", "No PAN / Invalid PAN"): "1067",
    ("195", "Individual"): "1057",
    ("195", "Company"): "1057",
    ("195", "No PAN / Invalid PAN"): "1057",
}


def execute():
    twc = frappe.qb.DocType("Tax Withholding Category")

    # Step 0: Backfill tds_section and entity_type from old-style names [TDS - SECTION - ENTITY]
    # for records that predate these fields
    set_section_and_entity_type_in_tax_withholding_category()

    # Step 1: Preserve old section code before overwriting
    (
        frappe.qb.update(twc)
        .set(twc.old_income_tax_section, twc.tds_section)
        .where(twc.tds_section.isin(OLD_TDS_SECTIONS))
        .where(IfNull(twc.old_income_tax_section, "") == "")
        .run()
    )

    # Step 2: Update tds_section to new codes (only sections with mappings)
    mapped_sections = set(old for old, _ in OLD_TO_NEW)

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
        .where(twc.tds_section.isin(mapped_sections))
        .run()
    )


def set_section_and_entity_type_in_tax_withholding_category():
    doctype = frappe.qb.DocType("Tax Withholding Category")
    categories = (
        frappe.qb.from_(doctype)
        .select(doctype.name)
        .where(IfNull(doctype.tds_section, "") == "")
        .where(IfNull(doctype.entity_type, "") == "")
        .run(pluck=True)
    )

    for category_name in categories:
        splitted_name = category_name.split(" - ")
        # old naming [TDS - SECTION - ENTITY]
        if len(splitted_name) < 3:
            continue

        if splitted_name[1] in OLD_TDS_SECTIONS and splitted_name[-1] in TDS_ENTITY_TYPE:
            (
                frappe.qb.update(doctype)
                .set("tds_section", splitted_name[1])
                .set("entity_type", splitted_name[-1])
                .where(doctype.name == category_name)
                .run()
            )
