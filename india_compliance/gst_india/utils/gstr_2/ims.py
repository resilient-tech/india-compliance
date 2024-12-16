import frappe
from frappe.query_builder.functions import IfNull
from frappe.utils.data import format_date

from india_compliance.gst_india.constants import (
    ACTION_MAP,
    CLASSIFICATION_MAP,
    GST_CATEGORY_MAP,
    STATE_NUMBERS,
)
from india_compliance.gst_india.doctype.gst_inward_supply.gst_inward_supply import (
    create_inward_supply,
)
from india_compliance.gst_india.utils import parse_datetime
from india_compliance.gst_india.utils.gstr_2.gstr import get_mapped_value


class IMS:
    VALUE_MAPS = frappe._dict(
        {
            "states": {value: f"{value}-{key}" for key, value in STATE_NUMBERS.items()},
            "action": ACTION_MAP,
            "reverse_action": {v: k for k, v in ACTION_MAP.items()},
            "gst_category": GST_CATEGORY_MAP,
            "reverse_gst_category": {v: k for k, v in GST_CATEGORY_MAP.items()},
            "classification": CLASSIFICATION_MAP,
        }
    )

    def __init__(self, company_gstin=None, company=None):
        self.existing_transactions = self.get_existing_transactions()
        self.company_gstin = company_gstin
        self.company = company

    def create_transactions(self, invoices):
        transactions = self.get_all_transactions(invoices)

        for transaction in transactions:
            create_inward_supply(transaction)

            if transaction.get("unique_key") in self.existing_transactions:
                self.existing_transactions.pop(transaction.get("unique_key"))

        self.handle_missing_transactions()

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
            "supply_type": get_mapped_value(
                invoice.inv_typ, self.VALUE_MAPS.gst_category
            ),
            "place_of_supply": get_mapped_value(invoice.pos, self.VALUE_MAPS.states),
            "document_value": invoice.val,
            "company": self.company,
            "company_gstin": self.company_gstin,
            "is_pending_action_allowed": invoice.ispendactnallwd,
            "previous_ims_action": get_mapped_value(
                invoice.action, self.VALUE_MAPS.action
            ),
            "is_supplier_return_filed": 0 if invoice.srcfilstatus == "Not Filed" else 1,
            "supplier_return_form": invoice.srcform,
            "cgst": invoice.camt,
            "sgst": invoice.samt,
            "igst": invoice.iamt,
            "cess": invoice.cess,
            "taxable_value": invoice.txval,
        }

    def update_transaction_to_gov_format(self, invoice):
        data = {
            "stin": invoice.supplier_gstin,
            "inv_typ": get_mapped_value(
                invoice.supply_type, self.VALUE_MAPS.reverse_gst_category
            ),
            "srcform": invoice.supplier_return_form,
            "rtnprd": invoice.sup_return_period,
            "val": invoice.document_value,
            "pos": get_mapped_value(
                invoice.place_of_supply.split("-")[1], self.VALUE_MAPS.states
            ),
            "prev_status": get_mapped_value(
                invoice.previous_ims_action, self.VALUE_MAPS.reverse_action
            ),
            "iamt": invoice.igst,
            "camt": invoice.cgst,
            "samt": invoice.sgst,
            "cess": invoice.cess,
            "txval": invoice.taxable_value,
        }

        if invoice.ims_action != "No Action":
            data["action"] = get_mapped_value(
                invoice.ims_action, self.VALUE_MAPS.reverse_action
            )

        return data

    def get_existing_transactions(self):
        category = get_mapped_value(
            type(self).__name__.lower(), self.VALUE_MAPS.classification
        )

        inward_supply = frappe.qb.DocType("GST Inward Supply")
        existing_transactions = (
            frappe.qb.from_(inward_supply)
            .select(
                inward_supply.name, inward_supply.supplier_gstin, inward_supply.bill_no
            )
            .where(IfNull(inward_supply.ims_action, "") != "")
            .where(inward_supply.classification == category)
        ).run(as_dict=True)

        return {
            f"{transaction.get('supplier_gstin', '')}-{transaction.get('bill_no', '')}": transaction.get(
                "name"
            )
            for transaction in existing_transactions
        }

    def handle_missing_transactions(self):
        if self.existing_transactions:
            frappe.db.delete(
                "GST Inward Supply",
                {
                    "previous_ims_action": ["is", "set"],
                    "is_supplier_return_filed": 0,
                    "name": ["in", list(self.existing_transactions.values())],
                },
            )


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
