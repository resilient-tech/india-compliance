import frappe


def enqueue_integration_request(**kwargs):
    frappe.enqueue(
        "india_compliance.gst_india.utils.api.create_integration_request", **kwargs
    )


def create_integration_request(data=None, output=None, error=None):
    return frappe.get_doc(
        {
            "doctype": "Integration Request",
            "integration_request_service": "India Compliance API",
            "data": pretty_json(data),
            "output": pretty_json(output),
            "error": pretty_json(error),
            "status": "Failed" if error else "Completed",
        }
    ).insert(ignore_permissions=True)


def pretty_json(obj):
    if not obj:
        return ""

    if isinstance(obj, str):
        return obj

    return frappe.as_json(obj, indent=4)
