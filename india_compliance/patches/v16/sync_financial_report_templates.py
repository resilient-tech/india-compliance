# Copyright (c) 2026, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt


from erpnext.accounts.doctype.financial_report_template.financial_report_template import (
    _sync_templates_for as sync_financial_report_templates,
)

from india_compliance.hooks import app_name


def execute():
    sync_financial_report_templates(app_name)
