from india_compliance.gst_india.overrides.sales_invoice import _get_dashboard_data


def get_delivery_note_dashboard(data):
    return _get_dashboard_data(data, ("e-Waybill Log",))
