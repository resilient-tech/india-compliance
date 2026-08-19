from india_compliance.gst_india.constants import E_WAYBILL_STOCK_ENTRY_PURPOSES
from india_compliance.gst_india.overrides.subcontracting_transaction import (
    SubcontractingController,
    set_address_display,
)
from india_compliance.gst_india.utils import is_outward_stock_entry

STOCK_ENTRY_FIELD_MAP = {"total_taxable_value": "total_taxable_value"}


class StockEntryController(SubcontractingController):
    DOCTYPE = "Stock Entry"
    TAXES_FIELD_MAP = STOCK_ENTRY_FIELD_MAP
    VALIDATES_TRANSACTION_NAME = True

    def is_e_waybill_applicable(self):
        # Inward purposes (Delivery, RM Return) carry only an e-Waybill; the
        # principal reports them in ITC-04 / GSTR-1, not the company (job worker).
        return super().is_e_waybill_applicable() and self.doc.purpose in E_WAYBILL_STOCK_ENTRY_PURPOSES

    def ignore_gst_validations(self):
        if super().ignore_gst_validations():
            return True

        # ignore if company address is not set
        if is_outward_stock_entry(self.doc) and not self.doc.bill_from_address:
            return True

        return bool(self.doc.is_return and not self.doc.bill_to_address)


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
    doc.company_gstin = doc.bill_from_gstin
    doc.supplier_gstin = doc.bill_to_gstin
    doc.gst_category = doc.bill_to_gst_category

    StockEntryController(doc).set_e_waybill_info()


def get_dashboard_data(data):
    return StockEntryController.get_dashboard_data(data)
