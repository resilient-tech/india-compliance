from india_compliance.gst_india.overrides.sales_invoice import (
    is_shipping_address_in_india,
    validate_port_address,
)
from india_compliance.gst_india.overrides.transaction import (
    validate_transaction,
)
from india_compliance.gst_india.utils import update_dashboard_with_gst_logs
from india_compliance.gst_india.utils.e_waybill import set_e_waybill_info
from india_compliance.gst_india.utils.e_waybill_actions import (
    is_e_waybill_required,
)


def onload(doc, method=None):
    if not doc.get("ewaybill"):
        if doc.gst_category == "Overseas" and is_e_waybill_required(doc):
            doc.set_onload("shipping_address_in_india", is_shipping_address_in_india(doc))
        return

    set_e_waybill_info(doc)


def validate(doc, method=None):
    if validate_transaction(doc) is False:
        return

    validate_port_address(doc)


def get_dashboard_data(data):
    return update_dashboard_with_gst_logs("Delivery Note", data, "e-Waybill Log", "Integration Request")
