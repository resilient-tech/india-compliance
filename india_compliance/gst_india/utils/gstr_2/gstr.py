from datetime import datetime
from typing import ClassVar

import frappe

from india_compliance.gst_india.constants import GST_CATEGORY_MAP, STATE_NUMBERS
from india_compliance.gst_india.doctype.gst_inward_supply.gst_inward_supply import (
    create_inward_supply,
)
from india_compliance.gst_india.utils import parse_datetime
from india_compliance.gst_returns.fields.gstr2 import DocField as doc
from india_compliance.gst_returns.steps import set_item_totals, take

# gov code -> stored value
GST_CATEGORY = GST_CATEGORY_MAP
STATES = {number: f"{number}-{name}" for name, number in STATE_NUMBERS.items()}

# invoice totals carry the same names as the item amounts
TOTAL_FIELDS = (doc.TAXABLE_VALUE, doc.IGST, doc.CGST, doc.SGST, doc.CESS)


def get_mapped_value(value, mapping):
    return mapping.get(value)


def to_period(value):
    """ "Feb-19" -> "022019"."""
    return value and datetime.strptime(value, "%b-%y").strftime("%m%Y")


def get_unique_key(transaction):
    # supplier_gstin-bill_no-doc_type key matches existing inward supplies
    supplier_gstin = transaction.get("supplier_gstin") or ""
    bill_no = transaction.get("bill_no") or ""
    doc_type = transaction.get("doc_type") or ""

    return f"{supplier_gstin}-{bill_no}-{doc_type}"


def add_original_details(row, document, keys):
    """Amendments carry the document they amend."""
    row.update(take(document, keys))
    row[doc.ORIGINAL_BILL_DATE] = parse_datetime(row[doc.ORIGINAL_BILL_DATE], day_first=True)

    return row


class GSTR:
    """Runs one category of one download: read rows via its section, write inward supplies,
    settle what went missing. The field mapping lives in `sections`."""

    # category -> (get_details, list the documents sit in or None for flat records, has items)
    SECTIONS: ClassVar[dict] = {}

    # category -> callable folding the rows of one document together, for the categories the
    # portal reports in parts
    GROUPED_SECTIONS: ClassVar[dict] = {}

    def __init__(self, company, gstin, return_period, category, gen_date_2b=None):
        self.company = company
        self.gstin = gstin
        self.return_period = return_period
        self.category = category
        self.gen_date_2b = gen_date_2b
        self.setup()

    def setup(self):
        self.existing_transaction = self.get_existing_transaction()
        self.download_details = self.get_download_details()

    def create_transactions(self, suppliers, rejected_data):
        self.rejected_data = rejected_data or []

        if not suppliers:
            self.handle_missing_transactions()
            return

        transactions = self.get_all_transactions(suppliers)
        self.update_gstins()

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

    def get_all_transactions(self, suppliers):
        get_details, docs_key, has_items = self.SECTIONS[self.category]

        if not docs_key:
            return [self.get_transaction(get_details(record, self)) for record in suppliers]

        transactions = list(self.read_suppliers(suppliers, docs_key, get_details, has_items))

        if group_documents := self.GROUPED_SECTIONS.get(self.category):
            transactions = group_documents(transactions)

        return transactions

    def read_suppliers(self, suppliers, docs_key, get_details, has_items):
        for supplier in suppliers:
            for document in supplier.get(docs_key) or []:
                details = {**self.get_supplier_details(supplier), **get_details(document, self)}
                items = self.get_items(document) if has_items else None

                yield self.get_transaction(details, items)

    def get_transaction(self, details, items=None):
        transaction = frappe._dict(
            company=self.company,
            company_gstin=self.gstin,
            classification=self.category,
            **details,
            **self.download_details,
            items=items,
        )

        if items:
            set_item_totals(transaction, items, TOTAL_FIELDS)

        transaction["unique_key"] = get_unique_key(transaction)

        return transaction

    def get_supplier_details(self, supplier):
        return {}

    def get_items(self, document):
        return None

    def get_existing_transaction(self):
        gst_is = frappe.qb.DocType("GST Inward Supply")
        transactions = (
            frappe.qb.from_(gst_is)
            .select(gst_is.name, gst_is.supplier_gstin, gst_is.bill_no, gst_is.doc_type)
            .where(gst_is.classification == self.category)
            .where(self.get_existing_transaction_filter(gst_is))
        ).run(as_dict=True)

        return {get_unique_key(transaction): transaction.get("name") for transaction in transactions}

    def get_existing_transaction_filter(self, gst_is):
        raise NotImplementedError

    def get_download_details(self):
        return {}

    def handle_missing_transactions(self):
        return

    def update_gstins(self):
        pass

    @classmethod
    def get_data_handler(cls, category):
        return cls if category in cls.SECTIONS else None
