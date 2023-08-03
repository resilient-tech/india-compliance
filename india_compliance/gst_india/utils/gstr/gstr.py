import frappe

from india_compliance.gst_india.doctype.gst_inward_supply.gst_inward_supply import (
    create_inward_supply,
)


class GSTR:
    def __init__(self, company, gstin, return_period, data, gen_date_2b):
        self.company = company
        self.gstin = gstin
        self.return_period = return_period
        self._data = data
        self.gen_date_2b = gen_date_2b
        # Maps of API keys to doctype fields
        self.keys_map = frappe._dict()
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
            )

            if not current_transaction % 2000:
                # nosemgrep
                frappe.db.commit()

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
            for invoice in supplier.get(self.keys_map.get("invoice_key"))
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
            for item in invoice.get(self.keys_map.get("items_key"))
        ]

    def get_transaction_item(self, item):
        return frappe._dict()
