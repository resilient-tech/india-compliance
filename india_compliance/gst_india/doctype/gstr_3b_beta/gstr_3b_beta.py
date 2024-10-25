# Copyright (c) 2024, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class GSTR3BBeta(Document):
    @frappe.whitelist()
    def fetch_invoice_data(self):
        inward_supplies = frappe.get_all(
            "GST Inward Supply",
            fields=[
                "supplier_gstin",
                "supplier_name",
                "invoice_type",
                "invoice_status",
                "bill_no",
                "bill_date",
                "name",
                "company",
                "company_gstin",
            ],
        )

        invoice_data = {
            invoice["name"]: {
                "supplier_gstin": invoice["supplier_gstin"],
                "supplier": invoice["supplier_name"],
                "invoice_type": invoice["invoice_type"],
                "invoice_status": invoice["invoice_status"],
                "invoice_no": invoice["bill_no"],
                "invoice_name": invoice["name"],
                "invoice_date": invoice["bill_date"],
                "company": invoice["company"],
                "company_gstin": invoice["company_gstin"],
                "is_dirty": 0,
            }
            for invoice in inward_supplies
        }
        return invoice_data

    def before_save(self):
        invoice_to_update = []
        for key, value in self.invoice_data.items():
            if value["is_dirty"]:
                invoice_to_update.append((key, value["invoice_status"]))

        self.update_invoice_status(invoice_to_update)

        self.is_modified = 0
        self.invoice_data = ""

    def update_invoice_status(self, data):
        for invoice in data:
            frappe.db.set_value(
                "GST Inward Supply",
                invoice[0],
                "invoice_status",
                invoice[1],
            )
