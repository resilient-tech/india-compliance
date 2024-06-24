from india_compliance.gst_india.overrides.purchase_invoice import (
    set_ineligibility_reason,
)
from india_compliance.gst_india.overrides.sales_invoice import (
    update_dashboard_with_gst_logs,
)
from india_compliance.gst_india.overrides.transaction import (
    ignore_gst_validations,
    validate_mandatory_fields,
    validate_transaction,
)


def get_dashboard_data(data):
    return update_dashboard_with_gst_logs(
        "Purchase Receipt",
        data,
        "e-Waybill Log",
        "Integration Request",
    )


def onload(doc, method=None):
    if ignore_gst_validations(doc, throw=False):
        return

    if (
        validate_mandatory_fields(
            doc, ("company_gstin", "place_of_supply", "gst_category"), throw=False
        )
        is False
    ):
        return

    set_ineligibility_reason(doc, show_alert=False)


def validate(doc, method=None):
    if validate_transaction(doc) is False:
        return

    set_ineligibility_reason(doc)
