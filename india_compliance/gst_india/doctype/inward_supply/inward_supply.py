# Copyright (c) 2022, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class InwardSupply(Document):
    def before_save(self):
        if self.classification.endswith("A"):
            self.is_amended = True

        if self.gstr_1_filing_date:
            self.gstr_1_filled = True


def create_inward_supply(transaction):
    filters = {
        "doc_number": transaction.doc_number,
        "doc_date": transaction.doc_date,
        "classification": transaction.classification,
        "supplier_gstin": transaction.supplier_gstin,
    }

    if name := frappe.get_value("Inward Supply", filters):
        inward_supply = frappe.get_doc("Inward Supply", name)
    else:
        inward_supply = frappe.new_doc("Inward Supply")

    inward_supply.update(transaction)
    return inward_supply.save(ignore_permissions=True)
