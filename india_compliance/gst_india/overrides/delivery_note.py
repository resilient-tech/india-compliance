from india_compliance.gst_india.overrides.sales_invoice import (
    is_shipping_address_in_india,
    validate_port_address,
)
from india_compliance.gst_india.overrides.transaction import (
    validate_transaction,
)
from india_compliance.gst_india.utils import update_dashboard_with_gst_logs
from india_compliance.gst_india.utils.e_waybill_applicability import get_e_waybill_applicability


def onload(doc, method=None):
    if not doc.get("ewaybill"):
        if doc.gst_category == "Overseas" and get_e_waybill_applicability(doc).is_required():
            doc.set_onload("shipping_address_in_india", is_shipping_address_in_india(doc))


def validate(doc, method=None):
    if validate_transaction(doc) is False:
        return

    validate_port_address(doc)


def get_dashboard_data(data):
    return update_dashboard_with_gst_logs("Delivery Note", data, "e-Waybill Log", "Integration Request")
