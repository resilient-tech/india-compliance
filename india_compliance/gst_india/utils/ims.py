import frappe

from india_compliance.gst_india.constants import STATE_NUMBERS
from india_compliance.gst_india.doctype.gst_inward_supply.gst_inward_supply import (
    create_inward_supply,
)
from india_compliance.gst_india.utils import ims, parse_datetime

CATEGORIES = [
    "B2B",
    "B2BA",
    "B2BDN",
    "B2BDNA",
    "B2BCN",
    "B2BCNA",
]


class IMS:
    STATE_MAP = {value: f"{value}-{key}" for key, value in STATE_NUMBERS.items()}

    def create_transactions(self, invoices):
        transactions = self.get_all_transactions(invoices)

        for transaction in transactions:
            create_inward_supply(transaction)

    def get_all_transactions(self, invoices):
        transactions = []
        for invoice in invoices:
            invoice = frappe._dict(invoice)
            transactions.append(self.get_transaction(invoice))

        return transactions

    def get_transaction(self, invoice):
        transaction = frappe._dict(
            {
                **self.get_supplier_details(invoice),
                **self.get_invoice_details(invoice),
                **self.get_status_info(invoice),
            }
        )
        return transaction

    def get_supplier_details(self, invoice):
        return {
            "supplier_gstin": invoice.stin,
            "sup_return_period": invoice.rtnprd,
        }

    def get_status_info(self, invoice):
        return {
            # Required??
            # "source_file_status": invoice.srcfilstatus,
            # "source_form": invoice.srcform,
            # "is_pending_action_allowed": invoice.ispendactnallwd,
        }


class B2B(IMS):
    def get_invoice_details(self, invoice):
        return {
            "bill_no": invoice.inum,
            "bill_date": parse_datetime(invoice.idt, day_first=True),
            "document_value": invoice.val,
            "place_of_supply": self.STATE_MAP[invoice.pos],
            "classification": invoice.inv_typ,
            "doc_type": "Invoice",  # Custom Field
        }


class B2BA(B2B):
    def get_invoice_details(self, invoice):
        invoice_details = super().get_invoice_details(invoice)
        invoice_details.update(
            {
                "original_bill_no": invoice.oinum,
                "original_bill_date": parse_datetime(invoice.oidt, day_first=True),
                "is_amended": True,
                "original_doc_type": "Invoice",
            }
        )
        return invoice_details


class B2BDN(B2B):
    def get_invoice_details(self, invoice):
        return {
            "bill_no": invoice.nt_num,
            "bill_date": parse_datetime(invoice.nt_dt, day_first=True),
            "document_value": invoice.val,
            "place_of_supply": self.STATE_MAP[invoice.pos],
            "classification": invoice.inv_typ,
            "doc_type": "Debit Note",  # Custom Field
        }


class B2BDNA(B2BDN):
    def get_invoice_details(self, invoice):
        invoice_details = super().get_invoice_details(invoice)
        invoice_details.update(
            {
                "original_bill_no": invoice.ont_num,
                "original_bill_date": parse_datetime(invoice.ont_dt, day_first=True),
                "is_amended": True,
                "original_doc_type": "Debit Note",
            }
        )
        return invoice_details


class B2BCN(B2BDN):
    def get_invoice_details(self, invoice):
        invoice_details = super().get_invoice_details(invoice)
        invoice_details.update(
            {
                "doc_type": "Credit Note",  # Custom Field
            }
        )
        return invoice_details


class B2BCNA(B2BCN):
    def get_invoice_details(self, invoice):
        invoice_details = super().get_invoice_details(invoice)
        invoice_details.update(
            {
                "original_bill_no": invoice.ont_num,
                "original_bill_date": parse_datetime(invoice.ont_dt, day_first=True),
                "is_amended": True,
                "original_doc_type": "Credit Note",
            }
        )
        return invoice_details


def download_ims_invoices(json_data):
    for category in CATEGORIES:
        getattr(ims, category)().create_transactions(json_data.get(category.lower()))
