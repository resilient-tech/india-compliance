from india_compliance.gst_india.overrides.sales_invoice import (
    update_dashboard_with_gst_logs,
)


def get_dashboard_data(data):
    return update_dashboard_with_gst_logs(
        "Purchase Receipt",
        data,
        "e-Waybill Log",
        "Integration Request",
    )
