import frappe
from frappe.query_builder.functions import IfNull
from frappe.utils.data import format_date

from india_compliance.gst_india.api_classes.taxpayer_returns import IMSAPI
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
    ACTION_MAP = {"A": "Accept", "R": "Reject", "P": "Pending", "N": "No Action"}

    def __init__(self, company_gstin):
        self.existing_transactions = self.get_existing_transactions()
        self.company_gstin = company_gstin

    def create_transactions(self, invoices):
        transactions = self.get_all_transactions(invoices)

        for transaction in transactions:
            create_inward_supply(transaction)

            if transaction.get("unique_key") in self.existing_transactions:
                self.existing_transactions.pop(transaction.get("unique_key"))

        self.delete_missing_transactions()

    def get_all_transactions(self, invoices):
        transactions = []
        for invoice in invoices:
            invoice = frappe._dict(invoice)
            transactions.append(self.get_transaction(invoice))

        return transactions

    def get_transaction(self, invoice):
        transaction = frappe._dict(
            supplier_gstin=invoice.stin,
            sup_return_period=invoice.rtnprd,
            place_of_supply=self.STATE_MAP[invoice.pos],
            document_value=invoice.val,
            company_gstin=self.company_gstin,
            # Required??
            # gstr_1_filled= invoice.srcfilstatus,
            # source_form = invoice.srcform,
            is_pending_action_allowed=invoice.ispendactnallwd,
            **self.get_invoice_details(invoice),
            items=self.get_transaction_item(invoice),
            ims_action=self.ACTION_MAP.get(invoice.action),
        )

        transaction["unique_key"] = (
            f"{transaction.get('supplier_gstin', '')}-{transaction.get('bill_no', '')}"
        )
        return transaction

    def get_transaction_item(self, invoice):
        return [
            {
                "taxable_value": invoice.txval,
                "igst": invoice.iamt,
                "cgst": invoice.camt,
                "sgst": invoice.samt,
                "cess": invoice.cess,
            }
        ]

    def get_item_details(self, item):
        return {
            "txval": item.taxable_value,
            "iamt": item.igst,
            "camt": item.cgst,
            "samt": item.sgst,
            "cess": item.cess,
        }

    def get_existing_transactions(self):
        inward_supply = frappe.qb.DocType("GST Inward Supply")
        self.existing_transactions = (
            frappe.qb.from_(inward_supply)
            .select(
                inward_supply.name, inward_supply.supplier_gstin, inward_supply.bill_no
            )
            .where(IfNull(inward_supply.sup_return_period, "") == "")
            .where(IfNull(inward_supply.ims_action, "") != "")
        ).run(as_dict=True)

        return {
            f"{transaction.get('supplier_gstin', '')}-{transaction.get('bill_no', '')}": transaction.get(
                "name"
            )
            for transaction in self.existing_transactions
        }

    def delete_missing_transactions(self):
        if self.existing_transactions:
            for inward_supply_name in self.existing_transactions.values():
                frappe.delete_doc("GST Inward Supply", inward_supply_name)


class B2B(IMS):
    def get_invoice_details(self, invoice):
        return {
            "bill_no": invoice.inum,
            "bill_date": parse_datetime(invoice.idt, day_first=True),
            # "supply_type": "", TODO: Check options
            "classification": "B2B",
            "doc_type": "Invoice",  # Custom Field
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
            # "supply_type": "", TODO: Check options
            "classification": "B2B",
            "doc_type": "Debit Note",  # Custom Field
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

    def get_category_details(self, invoice):
        invoice_details = super().get_category_details(invoice)
        invoice_details.update(
            {
                "ont_num": invoice.original_bill_no,
                "ont_dt": format_date(invoice.original_bill_date, "dd-mm-yyyy"),
            }
        )
        return invoice_details


def download_invoices(otp=None):
    company_gstin = "24AAUPV7468F1ZW"

    api = IMSAPI(company_gstin)
    response = api.get_data(
        "GETINV", params={"section": ["B2B", "B2BA", "CN", "DN", "CNA", "DNA"]}, otp=otp
    )  # section is a list

    if response.error_type == "no_docs_found":
        return

    for category in CATEGORIES:
        getattr(ims, category)(company_gstin).create_transactions(
            response.get(category.lower(), [])
        )


def upload_invoices(gstin):
    json_data = get_gov_data()

    api = IMSAPI()
    response = api.save_or_reset_action("SAVE", gstin, json_data)

    print("IMS Invoices Uploaded", response.get("reference_id"))


def reset_invoices(gstin):
    json_data = get_gov_data(is_reset=True)

    api = IMSAPI()
    response = api.save_or_reset_action("RESET", gstin, json_data)

    print("IMS Invoices Reset", response.get("reference_id"))


def get_gov_data(is_reset=False):
    category_key_map = {
        "Invoice_0": "b2b",
        "Invoice_1": "b2ba",
        "Debit Note_0": "b2bdn",
        "Debit Note_1": "b2bdna",
        "Credit Note_0": "b2bcn",
        "Credit Note_1": "b2bcna",
    }

    gst_inward_supply_list = frappe.get_all("GST Inward Supply", pluck="name")
    json_data = {}

    for inv_name in gst_inward_supply_list:
        invoice = frappe.get_doc("GST Inward Supply", inv_name)
        key = f"{invoice.doc_type}_{invoice.is_amended}"

        category = category_key_map[key]
        _class = getattr(ims, category.upper())()

        data = {
            "stin": invoice.supplier_gstin,
            # "inv_typ": invoice.supply_type, TODO: Check options
            "srcform": "",
            "rtnprd": invoice.sup_return_period,
            "val": invoice.document_value,
            "pos": STATE_NUMBERS[invoice.place_of_supply.split("-")[1]],
            "prev_status": invoice.previous_ims_action,
            **_class.get_category_details(invoice),
            **_class.get_item_details(invoice.items[0]),
        }

        if not is_reset:
            data.update(
                {
                    "action": invoice.ims_action,
                }
            )

        if json_data.get(category):
            json_data[category].append(data)
        else:
            json_data[category] = [data]

    return json_data
