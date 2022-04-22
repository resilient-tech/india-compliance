import frappe

from india_compliance.gst_india.constants import STATE_NUMBERS
from india_compliance.gst_india.doctype.inward_supply.inward_supply import (
    create_inward_supply,
)


def get_mapped_value(value, map):
    return map.get(value)


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
            "isd_type": {"ISDC": "ISD Credit Note", "ISDI": "ISD Invoice"},
            "amend_type": {
                "R": "Receiver GSTIN Amended",
                "N": "Invoice Number Amended",
                "D": "Other Details Amended",
            },
        }
    )

    def __init__(self, gstin, return_period, data):
        self.gstin = gstin
        self.return_period = return_period
        self._data = data
        self.setup()

    def setup(self):
        pass

    def create_transactions(self, category, suppliers):
        if not suppliers:
            return

        for transaction in self.get_all_transactions(category, suppliers):
            create_inward_supply(transaction)

    def get_all_transactions(self, category, suppliers):
        transactions = []
        for supplier in suppliers:
            transactions.extend(self.get_supplier_transactions(category, supplier))

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
