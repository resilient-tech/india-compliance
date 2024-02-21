import frappe


def execute():
    tds_section = (
        "193",
        "194",
        "194BB",
        "194EE",
        "194A",
        "194B",
        "194C",
        "194D",
        "194F",
        "194G",
        "194H",
        "194I",
        "194JA",
        "194JB",
        "194LA",
        "194I(a)",
        "194I(b)",
        "194LBA",
        "194DA",
        "192A",
        "194LBB",
        "194IA",
        "194N",
    )
    entity_type = ("Individual", "Company", "Company Assessee", "No PAN / Invalid PAN")
    doc = frappe.db.get_all("Tax Withholding Category")
    for d in doc:
        splitted_name = d.name.split(" - ")
        if len(splitted_name) < 3:
            continue
        if splitted_name[1] in tds_section and splitted_name[-1] in entity_type:
            frappe.db.set_value(
                "Tax Withholding Category",
                d.name,
                {"tds_section": splitted_name[1], "entity_type": splitted_name[-1]},
            )
