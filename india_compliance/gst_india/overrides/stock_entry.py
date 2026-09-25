from india_compliance.gst_india.constants import E_WAYBILL_STOCK_ENTRY_PURPOSES
from india_compliance.gst_india.overrides.subcontracting_transaction import (
    SubcontractingController,
    set_address_display,
)
from india_compliance.gst_india.utils import is_internal_stock_transfer, is_inward_transaction
from india_compliance.gst_india.utils.custom_transaction_controller import (
    set_gstin_fields_for_e_waybill,
)

STOCK_ENTRY_FIELD_MAP = {"total_taxable_value": "total_taxable_value"}


class StockEntryController(SubcontractingController):
    DOCTYPE = "Stock Entry"
    TAXES_FIELD_MAP = STOCK_ENTRY_FIELD_MAP
    VALIDATES_TRANSACTION_NAME = True

    def is_e_waybill_applicable(self):
        # Purposes not in the eligible set (e.g. Manufacture, Repack — same-premises,
        # no movement of goods between locations) carry no e-Waybill.
        return super().is_e_waybill_applicable() and self.doc.purpose in E_WAYBILL_STOCK_ENTRY_PURPOSES

    def ignore_gst_validations(self):
        if super().ignore_gst_validations():
            return True

        # ignore if company address is not set
        if is_internal_stock_transfer(self.doc) and not self.doc.bill_from_address:
            return True

        return bool(is_inward_transaction(self.doc) and not self.doc.bill_to_address)


def is_e_waybill_applicable(doc):
    return StockEntryController(doc).is_e_waybill_applicable()


def validate(doc, method=None):
    StockEntryController(doc).validate()


def before_save(doc, method=None):
    StockEntryController(doc).before_save()


def onload(doc, method=None):
    set_address_display(doc)

    # e-Waybill data generation reads these; they are only set here, so they are
    # available after run_onload (load_doc) and not on a bare frappe.get_doc.
    set_gstin_fields_for_e_waybill(doc)

    StockEntryController(doc).set_e_waybill_info()


def get_dashboard_data(data):
    return StockEntryController.get_dashboard_data(data)
