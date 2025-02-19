import frappe

from india_compliance.gst_india.constants import GST_CATEGORY_MAP, STATE_NUMBERS
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
            "gst_category": GST_CATEGORY_MAP,
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

    def __init__(self, company, gstin, return_period, gen_date_2b):
        self.company = company
        self.gstin = gstin
        self.return_period = return_period
        self.gen_date_2b = gen_date_2b
        self.category = type(self).__name__[6:]
        self.setup()

    def setup(self):
        self.existing_transaction = self.get_existing_transaction()

    def create_transactions(self, suppliers, rejected_data):
        self.rejected_data = rejected_data or []

        if not suppliers:
            self.handle_missing_transactions()
            return

        transactions = self.get_all_transactions(suppliers)
        total_transactions = len(transactions)
        current_transaction = 0

        for transaction in transactions:
            create_inward_supply(transaction)

            current_transaction += 1
            frappe.publish_realtime(
                "update_2a_2b_transactions_progress",
                {
                    "current_progress": current_transaction * 100 / total_transactions,
                    "return_period": self.return_period,
                },
                user=frappe.session.user,
            )

            if transaction.get("unique_key") in self.existing_transaction:
                self.existing_transaction.pop(transaction.get("unique_key"))

        self.handle_missing_transactions()

    def handle_missing_transactions(self):
        return

    def get_existing_transaction(self):
        return {}

    def get_all_transactions(self, suppliers):
        transactions = []
        for supplier in suppliers:
            transactions.extend(self.get_supplier_transactions(supplier))

        self.update_gstins()

        return transactions

    def get_supplier_transactions(self, supplier):
        return [
            self.get_transaction(frappe._dict(supplier), frappe._dict(invoice))
            for invoice in supplier.get(self.get_key("invoice_key"))
        ]

    def get_transaction(self, supplier, invoice):
        transaction = frappe._dict(
            company=self.company,
            company_gstin=self.gstin,
            classification=self.category,
            **self.get_supplier_details(supplier),
            **self.get_invoice_details(invoice),
            **self.get_download_details(),
            items=self.get_transaction_items(invoice),
        )

        if transaction.get("items"):
            self.update_totals(transaction)

        transaction["unique_key"] = (
            f"{transaction.get('supplier_gstin', '')}-{transaction.get('bill_no', '')}"
        )

        return transaction

    def update_totals(self, transaction):
        for field in ["taxable_value", "igst", "cgst", "sgst", "cess"]:
            transaction[field] = sum(
                [row.get(field) for row in transaction.get("items") if row.get(field)]
            )

    def get_supplier_details(self, supplier):
        return {}

    def get_invoice_details(self, invoice):
        return {}

    def get_download_details(self):
        return {}

    def get_transaction_items(self, invoice):
        return [
            self.get_transaction_item(frappe._dict(item))
            for item in invoice.get(self.get_key("items_key"), [])
        ]

    def get_transaction_item(self, item):
        return frappe._dict()

    def get_key(self, key):
        return self.KEY_MAPS.get(key)

    def set_key(self, key, value):
        self.KEY_MAPS[key] = value

    def update_gstins(self):
        pass
