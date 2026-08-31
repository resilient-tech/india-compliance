from typing import ClassVar

import frappe

from india_compliance.gst_india.utils import get_datetime, parse_datetime
from india_compliance.gst_india.utils.gstr_2.gstr import GSTR, decode, take, to_period
from india_compliance.gst_india.utils.gstr_2.sections import SECTIONS_2A
from india_compliance.gst_returns.fields.gstr2 import Y_N_TO_CHECK
from india_compliance.gst_returns.fields.gstr2 import DocField as doc
from india_compliance.gst_returns.fields.gstr2 import ItemField as item
from india_compliance.gst_returns.fields.gstr2 import RawField2a as raw2a

SUPPLIER_KEYS = {
    raw2a.SUPPLIER_GSTIN: doc.SUPPLIER_GSTIN,
    raw2a.GSTR_3B_FILED: doc.GSTR_3B_FILLED,
    raw2a.GSTR_1_FILING_DATE: doc.GSTR_1_FILING_DATE,
    raw2a.CANCEL_DATE: doc.REGISTRATION_CANCEL_DATE,
    raw2a.SUP_RETURN_PERIOD: doc.SUP_RETURN_PERIOD,
}

ITEM_KEYS = {
    raw2a.TAX_RATE: item.TAX_RATE,
    raw2a.TAXABLE_VALUE: item.TAXABLE_VALUE,
    raw2a.IGST: item.IGST,
    raw2a.CGST: item.CGST,
    raw2a.SGST: item.SGST,
    raw2a.CESS: item.CESS,
}


class GSTR2a(GSTR):
    SECTIONS: ClassVar[dict] = SECTIONS_2A

    def setup(self):
        super().setup()
        self.all_gstins = set()
        self.cancelled_gstins = {}

    def get_supplier_details(self, supplier):
        details = take(supplier, SUPPLIER_KEYS)
        decode(details, doc.GSTR_3B_FILLED, Y_N_TO_CHECK)
        details[doc.GSTR_1_FILING_DATE] = parse_datetime(details[doc.GSTR_1_FILING_DATE])
        details[doc.REGISTRATION_CANCEL_DATE] = parse_datetime(details[doc.REGISTRATION_CANCEL_DATE])
        details[doc.SUP_RETURN_PERIOD] = to_period(details[doc.SUP_RETURN_PERIOD])

        self.update_gstins_list(details)

        return details

    def get_items(self, document):
        # 2A nests each item's amounts under "itm_det"
        return [
            {
                item.ITEM_NUMBER: line.get(raw2a.ITEM_NUMBER, 0),
                **take(line.get(raw2a.ITEM_DETAILS, {}), ITEM_KEYS),
            }
            for line in document.get(raw2a.ITEMS)
        ]

    def update_gstins_list(self, supplier_details):
        self.all_gstins.add(supplier_details.get(doc.SUPPLIER_GSTIN))

        if cancel_date := supplier_details.get(doc.REGISTRATION_CANCEL_DATE):
            self.cancelled_gstins.setdefault(supplier_details[doc.SUPPLIER_GSTIN], cancel_date)

    def get_existing_transaction_filter(self, gst_is):
        return (gst_is.sup_return_period == self.return_period) & (gst_is.gstr_1_filled == 0)

    def handle_missing_transactions(self):
        """
        For GSTR2a, transactions are reflected immediately after it's pushed to GSTR-1.
        At times, it may later be removed from GSTR-1.

        In such cases, we need to delete such unfilled transactions not present in the latest data.
        """

        if self.existing_transaction:
            for inward_supply_name in self.existing_transaction.values():
                frappe.delete_doc("GST Inward Supply", inward_supply_name, ignore_permissions=True)

    def get_download_details(self):
        return {"is_downloaded_from_2a": 1}

    def update_gstins(self):
        if not self.all_gstins:
            return

        frappe.db.set_value(
            "GSTIN",
            {"name": ("in", self.all_gstins)},
            "last_updated_on",
            get_datetime(),
        )
        if not self.cancelled_gstins:
            return

        cancelled_gstins_to_update = frappe.db.get_all(
            "GSTIN",
            filters={
                "name": ("in", self.cancelled_gstins),
                "status": ("!=", "Cancelled"),
            },
            pluck="name",
        )

        for gstin in cancelled_gstins_to_update:
            cancelled_date = self.cancelled_gstins.get(gstin)
            frappe.db.set_value(
                "GSTIN",
                gstin,
                {"cancelled_date": cancelled_date, "status": "Cancelled"},
            )


get_data_handler = GSTR2a.get_data_handler
