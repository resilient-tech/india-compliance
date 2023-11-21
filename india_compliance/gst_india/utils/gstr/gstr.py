import frappe

from india_compliance.gst_india.constants import STATE_NUMBERS
from india_compliance.gst_india.doctype.gst_inward_supply.gst_inward_supply import (
    create_inward_supply,
)


def get_mapped_value(value, mapping):
    return mapping.get(value)


class GSTR:
    # Maps of API keys to doctype fields
    KEY_MAPS = frappe._dict()

    # Maps of API values to doctype values
    VALUE_MAPS = frappe._dict(
        {
            "Y_N_to_check": {"Y": 1, "N": 0},
            "yes_no": {"Y": "Yes", "N": "No"},
            "gst_category": {
                "R": "Regular",
                "SEZWP": "SEZ supplies with payment of tax",
                "SEZWOP": "SEZ supplies with out payment of tax",
                "DE": "Deemed exports",
                "CBW": "Intra-State Supplies attracting IGST",
            },
            "states": {value: f"{value}-{key}" for key, value in STATE_NUMBERS.items()},
            "note_type": {"C": "Credit Note", "D": "Debit Note"},
            "isd_type_2a": {"ISDCN": "ISD Credit Note", "ISD": "ISD Invoice"},
            "isd_type_2b": {"ISDC": "ISD Credit Note", "ISDI": "ISD Invoice"},
            "amend_type": {
                "R": "Receiver GSTIN Amended",
                "N": "Invoice Number Amended",
                "D": "Other Details Amended",
            },
        }
    )

    def __init__(self, company, gstin, return_period, data, gen_date_2b):
        self.company = company
        self.gstin = gstin
        self.return_period = return_period
        self._data = data
        self.gen_date_2b = gen_date_2b
        self.setup()

    def setup(self):
        pass

    def create_transactions(self, category, suppliers):
        if not suppliers:
            return

        transactions = self.get_all_transactions(category, suppliers)
        total_transactions = len(transactions)
        current_transaction = 0

        for transaction in transactions:
            create_inward_supply(transaction)

            current_transaction += 1
            frappe.publish_realtime(
                "update_transactions_progress",
                {
                    "current_progress": current_transaction * 100 / total_transactions,
                    "return_period": self.return_period,
                },
                user=frappe.session.user,
                doctype="Purchase Reconciliation Tool",
            )

    def get_all_transactions(self, category, suppliers):
        transactions = []
        for supplier in suppliers:
            transactions.extend(self.get_supplier_transactions(category, supplier))

        self.update_gstins()

        return transactions

    def get_supplier_transactions(self, category, supplier):
        return [
            self.get_transaction(
                category, frappe._dict(supplier), frappe._dict(invoice)
            )
            for invoice in supplier.get(self.get_key("invoice_key"))
        ]

    def get_transaction(self, category, supplier, invoice):
        return frappe._dict(
            company=self.company,
            company_gstin=self.gstin,
            # TODO: change classification to gstr_category
            classification=category.value,
            **self.get_supplier_details(supplier),
            **self.get_invoice_details(invoice),
            items=self.get_transaction_items(invoice),
        )

    def get_supplier_details(self, supplier):
        return {}

    def get_invoice_details(self, invoice):
        return {}

    def get_transaction_items(self, invoice):
        return [
            self.get_transaction_item(frappe._dict(item))
            for item in invoice.get(self.get_key("items_key"))
        ]

    def get_transaction_item(self, item):
        return frappe._dict()

    def get_key(self, key):
        return self.KEY_MAPS.get(key)

    def set_key(self, key, value):
        self.KEY_MAPS[key] = value

    def update_gstins(self):
        pass
