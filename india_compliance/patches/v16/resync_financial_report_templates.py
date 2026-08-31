# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt


import os

import frappe


def execute():
    """
    The ERPNext sync only inserts templates that are missing, so a shipped template never
    picks up later edits. Reloading imports the file when its timestamp is the newer one,
    so bump that timestamp when editing a template.
    """
    path = frappe.get_app_path("india_compliance", "income_tax_india", "financial_report_template")

    for template in os.listdir(path):
        # every fixture is a folder named after the json it holds
        if not os.path.exists(os.path.join(path, template, f"{template}.json")):
            continue

        frappe.reload_doc("income_tax_india", "financial_report_template", template)
