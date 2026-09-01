from typing import ClassVar

import frappe

from india_compliance.gst_india.utils import parse_datetime
from india_compliance.gst_india.utils.gstr_2.gstr import GSTR
from india_compliance.gst_india.utils.gstr_2.sections import GROUPED_SECTIONS, SECTIONS_2B
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
    GROUPED_SECTIONS: ClassVar[dict] = GROUPED_SECTIONS

    def get_supplier_details(self, supplier):
        details = take(supplier, SUPPLIER_KEYS)
        details[doc.GSTR_1_FILING_DATE] = parse_datetime(details[doc.GSTR_1_FILING_DATE], day_first=True)

        return details

    def get_items(self, document):
        return [take(line, ITEM_KEYS) for line in document.get(raw2b.ITEMS, [])]

    def get_transaction(self, details, items=None):
        return super().get_transaction(details, [] if items is None else items)

    def get_existing_transaction_filter(self, gst_is):
        return gst_is.return_period_2b == self.return_period

    def handle_missing_transactions(self):
        """
        For GSTR2b, only filed transactions are reported. They may be removed from GSTR-2b later
        if marked as pending / rejected from IMS Dashboard.

        In such cases,
        1) we need to clear the return_period_2b as this could change in future.
        2) and delete the rejected transactions.
        """
        if not self.existing_transaction:
            return

        missing_transactions = list(self.existing_transaction.values())
        rejected_transactions = self.get_all_transactions(self.rejected_data)

        # clear return_period_2b
        inward_supply = frappe.qb.DocType("GST Inward Supply")
        (
            frappe.qb.update(inward_supply)
            .set(inward_supply.return_period_2b, "")
            .set(inward_supply.is_downloaded_from_2b, 0)
            .where(inward_supply.name.isin(missing_transactions))
            .run()
        )

        # delete rejected transactions
        for transaction in rejected_transactions:
            filters = {
                "bill_no": transaction.bill_no,
                "bill_date": transaction.bill_date,
                "classification": transaction.classification,
                "supplier_gstin": transaction.supplier_gstin,
            }

            # doc classification
            if transaction.get("doc_type"):
                filters["doc_type"] = transaction.doc_type

            # delete_doc takes a name, not filters: handed a dict it iterates the keys as names,
            # finds nothing and drops it on ignore_missing
            name = frappe.db.get_value("GST Inward Supply", filters)
            if name:
                frappe.delete_doc("GST Inward Supply", name, ignore_permissions=True)

    def get_download_details(self):
        return {
            "is_downloaded_from_2b": 1,
            "return_period_2b": self.return_period,
            "gen_date_2b": parse_datetime(self.gen_date_2b, day_first=True),
        }


get_data_handler = GSTR2b.get_data_handler
