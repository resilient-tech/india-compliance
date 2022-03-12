import json

import frappe
from frappe.utils import now


def pretty_json(obj):
    if not obj or isinstance(obj, str):
        return obj

    return json.dumps(obj, indent=4, sort_keys=True, default=get_object_repr)


def get_object_repr(obj):
    try:
        return repr(obj)
    except Exception:
        return "<not serializable>"


# Logging
def create_request_log(
    request_id=None,
    request=None,
    response=None,
    error=None,
    doctype=None,
    docname=None,
):
    return frappe.get_doc(
        {
            "doctype": "Integration Request",
            "integration_type": "Remote",
            "integration_request_service": f"GST India - {request_id}",
            "reference_doctype": doctype,
            "reference_docname": docname,
            "data": pretty_json(request),
            "output": pretty_json(response),
            "error": pretty_json(error),
            "status": "Failed" if error else "Completed",
        }
    ).insert(ignore_permissions=True)


def create_download_log(
    self, gst_return, classification, return_period, no_data_found=False
):
    doctype = "GSTR Download Log"
    log = frappe.db.get_value(
        doctype,
        {
            "gstin": self.comp_gstin,
            "gst_return": gst_return,
            "classification": classification,
            "return_period": return_period,
        },
    )

    if log:
        doc = frappe.get_doc(doctype, log)
    else:
        doc = frappe.get_doc({"doctype": doctype})

    return doc.update(
        {
            "gstin": self.comp_gstin,
            "gst_return": gst_return,
            "classification": classification,
            "return_period": return_period,
            "no_data_found": no_data_found,
            "last_updated_on": now(),
        }
    ).save(ignore_permissions=True)
