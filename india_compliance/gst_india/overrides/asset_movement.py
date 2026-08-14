import frappe
from erpnext.assets.doctype.asset.asset import get_asset_value_after_depreciation
from frappe.utils import flt

from india_compliance.gst_india.overrides.subcontracting_transaction import set_address_display
from india_compliance.gst_india.utils import (
    is_api_enabled,
    is_inward_transaction,
)
from india_compliance.gst_india.utils.transaction_controller import GSTTransactionController

ASSET_MOVEMENT_FIELD_MAP = {"amount": "taxable_value"}


class AssetMovementController(GSTTransactionController):
    DOCTYPE = "Asset Movement"
    TAXES_FIELD_MAP = ASSET_MOVEMENT_FIELD_MAP
    VALIDATES_TRANSACTION_NAME = True

    def is_e_waybill_applicable(self):
        gst_settings = frappe.get_cached_doc("GST Settings")

        return (
            super().is_e_waybill_applicable()
            and is_api_enabled(gst_settings)
            and bool(gst_settings.enable_e_waybill_from_asset_movement)
        )

    @classmethod
    def get_dashboard_data(cls, data):
        # Asset Movement has no standard dashboard, so `fieldname` is unset. frappe's
        # set_open_count bails out without one, and the GST Logs counts would never load.
        data.setdefault("fieldname", "name")

        return super().get_dashboard_data(data)

    def ignore_gst_validations(self):
        if super().ignore_gst_validations():
            return True

        return not (self.doc.taxes or self.doc.bill_from_address or self.doc.bill_to_address)

    def set_fields(self):

        for row in self.doc.assets:
            if not row.asset:
                continue

            row.taxable_value = flt(
                get_asset_value_after_depreciation(row.asset),
                row.precision("taxable_value"),
            )


def is_e_waybill_applicable(doc):
    return AssetMovementController(doc).is_e_waybill_applicable()


def validate(doc, method=None):
    AssetMovementController(doc).validate()


def before_save(doc, method=None):
    AssetMovementController(doc).before_save()


def onload(doc, method=None):
    set_address_display(doc)

    # e-Waybill data generation reads these; they are only set here, so they are
    # available after run_onload (load_doc) and not on a bare frappe.get_doc.
    # company_gstin is the GSTIN generating the e-Waybill.
    if is_inward_transaction(doc):
        doc.company_gstin, doc.supplier_gstin = doc.bill_to_gstin, doc.bill_from_gstin
        doc.gst_category = doc.bill_from_gst_category
    else:
        doc.company_gstin, doc.supplier_gstin = doc.bill_from_gstin, doc.bill_to_gstin
        doc.gst_category = doc.bill_to_gst_category

    AssetMovementController(doc).set_e_waybill_info()


def get_dashboard_data(data):
    return AssetMovementController.get_dashboard_data(data)
