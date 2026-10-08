from typing import ClassVar

import frappe
from frappe.query_builder.functions import IfNull

from india_compliance.gst_india.utils import parse_datetime
from india_compliance.gst_india.utils.gstr_2.gstr import GSTR
from india_compliance.gst_india.utils.gstr_2.sections import SECTIONS_2B
from india_compliance.gst_returns.fields.gstr2 import DocField as doc
from india_compliance.gst_returns.fields.gstr2 import ItemField as item
from india_compliance.gst_returns.fields.gstr2 import RawField2b as raw2b
from india_compliance.gst_returns.steps import take

SUPPLIER_KEYS = {
    raw2b.SUPPLIER_GSTIN: doc.SUPPLIER_GSTIN,
    raw2b.SUPPLIER_NAME: doc.SUPPLIER_NAME,
    raw2b.GSTR_1_FILING_DATE: doc.GSTR_1_FILING_DATE,
    raw2b.SUP_RETURN_PERIOD: doc.SUP_RETURN_PERIOD,
}

ITEM_KEYS = {
    raw2b.ITEM_NUMBER: item.ITEM_NUMBER,
    raw2b.TAX_RATE: item.TAX_RATE,
    raw2b.TAXABLE_VALUE: item.TAXABLE_VALUE,
    raw2b.IGST: item.IGST,
    raw2b.CGST: item.CGST,
    raw2b.SGST: item.SGST,
    raw2b.CESS: item.CESS,
}


class GSTR2b(GSTR):
    SECTIONS: ClassVar[dict] = SECTIONS_2B

    def get_supplier_details(self, supplier):
        details = take(supplier, SUPPLIER_KEYS)
        details[doc.GSTR_1_FILING_DATE] = parse_datetime(details[doc.GSTR_1_FILING_DATE], day_first=True)

        return details

    def get_items(self, document):
        return [take(line, ITEM_KEYS) for line in document.get(raw2b.ITEMS) or []]

    def get_transaction(self, details, items=None):
        return super().get_transaction(details, [] if items is None else items)

    def get_invalid_transaction_filter(self, gst_is):
        return (gst_is.return_period_2b == self.return_period) | (
            (gst_is.company_gstin == self.gstin)
            & (gst_is.is_downloaded_from_2a == 1)
            & (IfNull(gst_is.return_period_2b, "") == "")
            & (gst_is.sup_return_period == self.return_period)
        )

    def handle_invalid_transactions(self):
        """
        For GSTR2b, only filed transactions are reported. Inward supplies of this period that are
        not in it (dropped from this 2B, or 2A transactions that never reached it):
        1) downloaded from IMS: clear the return_period_2b, as this could change in future.
        2) others: delete them, which unreconciles the linked purchase.
        Transactions rejected from IMS Dashboard are deleted as well.
        """
        self.handle_invalid_ims_transactions()
        self.handle_invalid_2a_2b_transactions()
        self.handle_rejected_transactions()

    def handle_rejected_transactions(self):
        rejected_transactions = self.get_all_transactions(self.rejected_data)

        # delete rejected transactions
        for transaction in rejected_transactions:
            filters = {
                "company_gstin": self.gstin,
                "bill_no": transaction.bill_no,
                "bill_date": transaction.bill_date,
                "classification": transaction.classification,
                "supplier_gstin": transaction.supplier_gstin,
            }

            if transaction.get("doc_type"):
                filters["doc_type"] = transaction.doc_type

            # eligible and ineligible parts of one ISD number are separate inward supplies
            if transaction.classification in ("ISD", "ISDA"):
                filters["itc_availability"] = transaction.get("itc_availability") or ("is", "not set")

            name = frappe.db.get_value("GST Inward Supply", filters)
            # delete doc allows passing only name
            if name:
                frappe.delete_doc("GST Inward Supply", name, ignore_permissions=True)

    def handle_invalid_ims_transactions(self):
        names = [
            transaction.name
            for transaction in self.invalid_transactions.values()
            if transaction.is_downloaded_from_ims
        ]
        if not names:
            return

        # clear return_period_2b
        inward_supply = frappe.qb.DocType("GST Inward Supply")
        (
            frappe.qb.update(inward_supply)
            .set(inward_supply.return_period_2b, "")
            .set(inward_supply.is_downloaded_from_2b, 0)
            .where(inward_supply.name.isin(names))
            .run()
        )

    def handle_invalid_2a_2b_transactions(self):
        for transaction in self.invalid_transactions.values():
            if transaction.is_downloaded_from_ims:
                continue

            frappe.delete_doc("GST Inward Supply", transaction.name, ignore_permissions=True)

    def get_download_details(self):
        return {
            "is_downloaded_from_2b": 1,
            "return_period_2b": self.return_period,
            "gen_date_2b": parse_datetime(self.gen_date_2b, day_first=True),
        }


get_data_handler = GSTR2b.get_data_handler
