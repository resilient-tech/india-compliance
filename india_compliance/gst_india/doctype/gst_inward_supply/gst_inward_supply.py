# Copyright (c) 2022, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class GSTInwardSupply(Document):
    def before_save(self):
        if self.classification.endswith("A"):
            self.is_amended = True

        if self.gstr_1_filing_date:
            self.gstr_1_filled = True


def create_inward_supply(transaction):
    filters = {
        "bill_no": transaction.bill_no,
        "bill_date": transaction.bill_date,
        "classification": transaction.classification,
        "supplier_gstin": transaction.supplier_gstin,
    }

    if name := frappe.get_value("GST Inward Supply", filters):
        gst_inward_supply = frappe.get_doc("GST Inward Supply", name)
    else:
        gst_inward_supply = frappe.new_doc("GST Inward Supply")

    gst_inward_supply.update(transaction)
    return gst_inward_supply.save(ignore_permissions=True)
