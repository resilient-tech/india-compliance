import frappe
from frappe.utils import getdate


def execute():
    tds_rules = frappe.get_file_json(
        frappe.get_app_path(
            "india_compliance", "income_tax_india", "data", "tds_details.json"
        )
    )
    for rule in tds_rules:
        exists = frappe.db.exists(
            "Tax Withholding Category",
            {
                "tds_section": rule.get("tds_section"),
                "entity_type": rule.get("entity_type"),
            },
        )
        if not exists:
            continue
        doc = frappe.get_doc("Tax Withholding Category", exists)
        for rate in rule["rates"]:
            if not next(
                (
                    row
                    for row in doc.get("rates")
                    if row.get("from_date") <= getdate(rate.get("from_date"))
                    and row.get("to_date") >= getdate(rate.get("to_date"))
                ),
                None,
            ):
                doc.append("rates", rate)
        doc.flags.ignore_permissions = True
        doc.flags.ignore_validate = True
        doc.flags.ignore_mandatory = True
        doc.flags.ignore_links = True
        doc.save()
