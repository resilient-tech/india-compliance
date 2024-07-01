import frappe
from erpnext.subcontracting.doctype.subcontracting_order.subcontracting_order import (
    SubcontractingOrder as _SubcontractingOrder,
)

from india_compliance.gst_india.utils import is_api_enabled
from india_compliance.gst_india.utils.e_waybill import get_e_waybill_info
from india_compliance.gst_india.utils.taxes_controller import (
    SubcontractingTaxesController,
    update_gst_details,
)


class SubcontractingOrder(_SubcontractingOrder, SubcontractingTaxesController):
    FIELD_MAP = {
        "taxes": "taxes",
        "amount": "amount",
        "total_taxes": "total_taxes",
        "qty": "qty",
        "grand_total": "base_rounded_total",
        "company": "company",
    }

    def onload(self):
        super().onload()
        if not self.get("ewaybill"):
            return

        gst_settings = frappe.get_cached_doc("GST Settings")

        if not (
            is_api_enabled(gst_settings)
            and gst_settings.enable_e_waybill
            and gst_settings.enable_e_waybill_for_sc
        ):
            return

        self.set_onload("e_waybill_info", get_e_waybill_info(self))

    def before_save(self):
        update_gst_details(self)

    def before_submit(self):
        update_gst_details(self)

    def before_validate(self):
        super().before_validate()
        self.set_taxes_and_totals()

    def validate(self):
        super().validate()
        self.validate_taxes_and_transaction()
