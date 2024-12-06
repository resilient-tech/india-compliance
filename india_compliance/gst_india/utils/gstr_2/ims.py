import frappe
from frappe.utils.data import format_date

from india_compliance.gst_india.constants import GST_CATEGORY_MAP, STATE_NUMBERS
from india_compliance.gst_india.doctype.gst_inward_supply.gst_inward_supply import (
    create_inward_supply,
)
from india_compliance.gst_india.utils import parse_datetime

ACTION_MAP = {"A": "Accepted", "R": "Rejected", "P": "Pending", "N": "No Action"}


class IMS:
    STATE_MAP = {value: f"{value}-{key}" for key, value in STATE_NUMBERS.items()}

    def __init__(self, company_gstin=None, company=None):
        self.company_gstin = company_gstin
        self.company = company

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
            **self.update_transaction_to_internal_format(invoice),
            **self.get_invoice_details(invoice),
        )

        transaction["unique_key"] = (
            f"{transaction.get('supplier_gstin', '')}-{transaction.get('bill_no', '')}"
        )
        return transaction

    def update_transaction_to_internal_format(self, invoice):
        return {
            "supplier_gstin": invoice.stin,
            "sup_return_period": invoice.rtnprd,
            "supply_type": GST_CATEGORY_MAP[invoice.inv_typ],
            "place_of_supply": self.STATE_MAP[invoice.pos],
            "document_value": invoice.val,
            "company": self.company,
            "company_gstin": self.company_gstin,
            "is_pending_action_allowed": invoice.ispendactnallwd,
            "previous_ims_action": ACTION_MAP.get(invoice.action),
            "is_supplier_return_filed": 0 if invoice.srcfilstatus == "Not Filed" else 1,
            "supplier_ret_frm": invoice.srcform,
            "cgst": invoice.camt,
            "sgst": invoice.samt,
            "igst": invoice.iamt,
            "cess": invoice.cess,
            "taxable_value": invoice.txval,
        }

    def update_transaction_to_gov_format(self, invoice):
        gst_category_map = {v: k for k, v in GST_CATEGORY_MAP.items()}
        action_map = {v: k for k, v in ACTION_MAP.items()}

        data = {
            "stin": invoice.supplier_gstin,
            "inv_typ": gst_category_map[invoice.supply_type],
            "srcform": invoice.supplier_ret_frm,
            "rtnprd": invoice.sup_return_period,
            "val": invoice.document_value,
            "pos": STATE_NUMBERS[invoice.place_of_supply.split("-")[1]],
            "prev_status": action_map[invoice.previous_ims_action],
            "iamt": invoice.igst,
            "camt": invoice.cgst,
            "samt": invoice.sgst,
            "cess": invoice.cess,
            "txval": invoice.taxable_value,
        }

        if invoice.ims_action != "No Action":
            data["action"] = action_map[invoice.ims_action]

        return data


class B2B(IMS):
    def get_invoice_details(self, invoice):
        return {
            "bill_no": invoice.inum,
            "bill_date": parse_datetime(invoice.idt, day_first=True),
            "classification": "B2B",
            "doc_type": "Invoice",
        }

    def get_category_details(self, invoice):
        return {
            "inum": invoice.bill_no,
            "idt": format_date(invoice.bill_date, "dd-mm-yyyy"),
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

    def get_category_details(self, invoice):
        invoice_details = super().get_category_details(invoice)
        invoice_details.update(
            {
                "oinum": invoice.original_bill_no,
                "oidt": format_date(invoice.original_bill_date, "dd-mm-yyyy"),
            }
        )
        return invoice_details


class B2BDN(B2B):
    def get_invoice_details(self, invoice):
        return {
            "bill_no": invoice.nt_num,
            "bill_date": parse_datetime(invoice.nt_dt, day_first=True),
            "classification": "CDNR",
            "doc_type": "Debit Note",
        }

    def get_category_details(self, invoice):
        return {
            "nt_num": invoice.bill_no,
            "nt_dt": format_date(invoice.bill_date, "dd-mm-yyyy"),
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

    def get_category_details(self, invoice):
        invoice_details = super().get_category_details(invoice)
        invoice_details.update(
            {
                "ont_num": invoice.original_bill_no,
                "ont_dt": format_date(invoice.original_bill_date, "dd-mm-yyyy"),
            }
        )
        return invoice_details


class B2BCN(B2BDN):
    def get_invoice_details(self, invoice):
        invoice_details = super().get_invoice_details(invoice)
        invoice_details.update(
            {
                "doc_type": "Credit Note",
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

    def get_category_details(self, invoice):
        invoice_details = super().get_category_details(invoice)
        invoice_details.update(
            {
                "ont_num": invoice.original_bill_no,
                "ont_dt": format_date(invoice.original_bill_date, "dd-mm-yyyy"),
            }
        )
        return invoice_details
