from datetime import datetime
from enum import Enum

import frappe

from india_compliance.gst_india.constants import STATE_NUMBERS
from india_compliance.gst_india.doctype.gstr_download_log.gstr_download_log import (
    create_download_log,
)
from india_compliance.gst_india.doctype.inward_supply.inward_supply import (
    create_inward_supply,
)
from india_compliance.gst_india.utils.gstr import gstr_2a, gstr_2b


class ICEnum(Enum):
    @classmethod
    def as_dict(cls):
        return frappe._dict({member.name: member.value for member in cls})


class ReturnType(ICEnum):
    GSTR2A = "GSTR2a"
    GSTR2B = "GSTR2b"


class GSTRCategory(ICEnum):
    B2B = "B2B"
    B2BA = "B2BA"
    CDNR = "CDNR"
    CDNRA = "CDNRA"
    ISD = "ISD"
    ISDA = "ISDA"
    IMPG = "IMPG"
    IMPGSEZ = "IMPGSEZ"


MODULE_MAP = {
    ReturnType.GSTR2A: gstr_2a,
    ReturnType.GSTR2B: gstr_2b,
}


def save_gstr(gstin, return_type, return_period, json_data):
    """Save GSTR data to Inward Supply

    :param return_period: str
    :param json_data: dict of list (GSTR category: suppliers)
    """
    create_download_log(gstin, return_type, return_period)

    for category in GSTRCategory:
        data_handler = get_data_handler(return_type, category)(gstin, return_period)
        data_handler.create_transactions(
            category,
            json_data.get(category.value.lower()),
        )


def get_data_handler(return_type, category):
    return getattr(MODULE_MAP[return_type], f"{return_type.value}{category.value}")


class GSTR:
    # Maps of API keys to doctype fields
    KEY_MAPS = frappe._dict()

    # Maps of API values to doctype values
    VALUE_MAPS = frappe._dict(
        {
            "yes_no": {"Y": 1, "N": 0},
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

    def __init__(self, gstin, return_period) -> None:
        self.gstin = gstin
        self.return_period = return_period
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
            transactions.extend(self.get_transactions(category, supplier))

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


def get_mapped_value(value, map):
    return map.get(value)


def map_date_format(date_str, source_format, target_format):
    return datetime.strptime(date_str, source_format).strftime(target_format)
