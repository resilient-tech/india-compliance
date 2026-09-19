# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt


import os

import frappe

from india_compliance.hooks import app_name


def execute():
    for module in frappe.local.app_modules.get(app_name) or []:
        path = os.path.join(frappe.get_module_path(module), "financial_report_template")

        if not os.path.isdir(path):
            continue

        for template in os.listdir(path):
            # every fixture is a folder named after the json it holds
            if not os.path.exists(os.path.join(path, template, f"{template}.json")):
                continue

            frappe.reload_doc(module, "financial_report_template", template)
