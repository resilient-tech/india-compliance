from india_compliance.gst_india.overrides.purchase_invoice import (
    set_ineligibility_reason,
)
from india_compliance.gst_india.overrides.transaction import (
    ignore_gst_validations,
    validate_mandatory_fields,
    validate_transaction,
)
from india_compliance.gst_india.utils import update_dashboard_with_gst_logs
from india_compliance.gst_india.utils.e_waybill import set_e_waybill_info


def get_dashboard_data(data):
    return update_dashboard_with_gst_logs(
        "Purchase Receipt",
        data,
        "e-Waybill Log",
        "Integration Request",
    )


def onload(doc, method=None):
    if ignore_gst_validations(doc):
        return

    if (
        validate_mandatory_fields(doc, ("company_gstin", "place_of_supply", "gst_category"), throw=False)
        is False
    ):
        return

    set_ineligibility_reason(doc, show_alert=False)

    # Load e-waybill info if applicable
    set_e_waybill_info(doc)


def validate(doc, method=None):
    if validate_transaction(doc) is False:
        return

    set_ineligibility_reason(doc)
