import frappe
from frappe.utils.data import format_date

from india_compliance.gst_india.constants import (
    ACTION_MAP,
    GST_CATEGORY_MAP,
    STATE_NUMBERS,
)
from india_compliance.gst_india.doctype.gst_inward_supply.gst_inward_supply import (
    create_inward_supply,
)
from india_compliance.gst_india.doctype.gst_inward_supply.gst_inward_supply import (
    update_previous_ims_action as _update_previous_ims_action,
)
from india_compliance.gst_india.utils import parse_datetime
from india_compliance.gst_india.utils.gstr_2.gstr import get_mapped_value

CLASSIFICATION_MAP = {
    "B2B": ["B2B", "Invoice"],
    "B2BA": ["B2BA", "Invoice"],
    "B2BCN": ["CDNR", "Credit Note"],
    "B2BCNA": ["CDNRA", "Credit Note"],
    "B2BDN": ["CDNR", "Debit Note"],
    "B2BDNA": ["CDNRA", "Debit Note"],
}


class IMS:
    VALUE_MAPS = frappe._dict(
        {
            "states": {value: f"{value}-{key}" for key, value in STATE_NUMBERS.items()},
            "reverse_states": STATE_NUMBERS,
            "action": ACTION_MAP,
            "reverse_action": {v: k for k, v in ACTION_MAP.items()},
            "gst_category": GST_CATEGORY_MAP,
            "reverse_gst_category": {v: k for k, v in GST_CATEGORY_MAP.items()},
            "classification": CLASSIFICATION_MAP,
        }
    )

    def __init__(self, company=None, gstin=None, *args):
        self.company_gstin = gstin
        self.company = company
        self.existing_transactions = self.get_existing_transactions()

    def create_transactions(self, invoices, rejected_data):
        self.reset_previous_ims_action()

        if not invoices:
            self.handle_missing_transactions()
            return

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

    def update_previous_ims_action(self, uploaded_invoices, error_invoices):
        errors = set()

        for supplier in error_invoices:
            for invoice in supplier.get("inv"):

                # same key across categories
                errors.add(f"{invoice.get('inum')}_{supplier.get('stin')}")

        for invoice in uploaded_invoices:
            invoice = self.get_transaction(frappe._dict(invoice))

            # different keys across categories
            if f"{invoice.get('bill_no')}_{invoice.get('supplier_gstin')}" in errors:
                continue

            _update_previous_ims_action(invoice)

    def get_transaction(self, invoice):
        transaction = frappe._dict(
            **self.convert_data_to_internal_format(invoice),
            **self.get_invoice_details(invoice),
        )

        transaction["unique_key"] = (
            f"{transaction.get('supplier_gstin', '')}-{transaction.get('bill_no', '')}"
        )

        return transaction

    def convert_data_to_internal_format(self, invoice):
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
            "is_pending_action_allowed": invoice.ispendactblocked == "N",
            "previous_ims_action": get_mapped_value(
                invoice.action, self.VALUE_MAPS.action
            ),
            "is_downloaded_from_ims": 1,
            "is_supplier_return_filed": 0 if invoice.srcfilstatus == "Not Filed" else 1,
            "supplier_return_form": invoice.srcform,
            "cgst": invoice.camt,
            "sgst": invoice.samt,
            "igst": invoice.iamt,
            "cess": invoice.cess,
            "taxable_value": invoice.txval,
        }

    def convert_data_to_gov_format(self, invoice):
        data = {
            "stin": invoice.supplier_gstin,
            "inv_typ": get_mapped_value(
                invoice.supply_type, self.VALUE_MAPS.reverse_gst_category
            ),
            "srcform": invoice.supplier_return_form,
            "rtnprd": invoice.sup_return_period,
            "val": invoice.document_value,
            "pos": get_mapped_value(
                invoice.place_of_supply.split("-")[1], self.VALUE_MAPS.reverse_states
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
        category, doc_type = get_mapped_value(
            self.ims_category(), self.VALUE_MAPS.classification
        )

        inward_supply = frappe.qb.DocType("GST Inward Supply")
        existing_transactions = (
            frappe.qb.from_(inward_supply)
            .select(
                inward_supply.name, inward_supply.supplier_gstin, inward_supply.bill_no
            )
            .where(inward_supply.is_downloaded_from_2b == 0)
            .where(inward_supply.is_downloaded_from_2a == 0)
            .where(inward_supply.is_downloaded_from_ims == 1)
            .where(inward_supply.is_supplier_return_filed == 0)
            .where(inward_supply.classification == category)
            .where(inward_supply.doc_type == doc_type)
            .where(inward_supply.company_gstin == self.company_gstin)
            .run(as_dict=True)
        )

        return {
            f"{transaction.get('supplier_gstin', '')}-{transaction.get('bill_no', '')}": transaction.get(
                "name"
            )
            for transaction in existing_transactions
        }

    def handle_missing_transactions(self):
        if not self.existing_transactions:
            return

        for inward_supply_name in self.existing_transactions.values():
            frappe.delete_doc("GST Inward Supply", inward_supply_name)

    def reset_previous_ims_action(self):
        category, doc_type = get_mapped_value(
            self.ims_category(), self.VALUE_MAPS.classification
        )
        inward_supply = frappe.qb.DocType("GST Inward Supply")

        (
            frappe.qb.update(inward_supply)
            .set(inward_supply.previous_ims_action, "")
            .where(inward_supply.classification == category)
            .where(inward_supply.doc_type == doc_type)
            .where(inward_supply.company_gstin == self.company_gstin)
            .run()
        )

    def ims_category(self):
        return type(self).__name__.removeprefix("IMS")


class IMSB2B(IMS):
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


class IMSB2BA(IMSB2B):
    def get_invoice_details(self, invoice):
        invoice_details = super().get_invoice_details(invoice)
        invoice_details.update(
            {
                "original_bill_no": invoice.oinum,
                "original_bill_date": parse_datetime(invoice.oidt, day_first=True),
                "is_amended": True,
                "classification": "B2BA",
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


class IMSB2BDN(IMSB2B):
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


class IMSB2BDNA(IMSB2BDN):
    def get_invoice_details(self, invoice):
        invoice_details = super().get_invoice_details(invoice)
        invoice_details.update(
            {
                "original_bill_no": invoice.ont_num,
                "original_bill_date": parse_datetime(invoice.ont_dt, day_first=True),
                "is_amended": True,
                "original_doc_type": "Debit Note",
                "classification": "CDNRA",
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


class IMSB2BCN(IMSB2BDN):
    def get_invoice_details(self, invoice):
        invoice_details = super().get_invoice_details(invoice)
        invoice_details.update(
            {
                "doc_type": "Credit Note",
            }
        )
        return invoice_details


class IMSB2BCNA(IMSB2BDNA):
    def get_invoice_details(self, invoice):
        invoice_details = super().get_invoice_details(invoice)
        invoice_details.update(
            {
                "doc_type": "Credit Note",
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
