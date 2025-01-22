# Copyright (c) 2024, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class GSTRAction(Document):
    pass


def set_gstr_actions(doc, request_type, token, request_id, status=None):
    if not token:
        return

    row = {
        "request_type": request_type,
        "token": token,
        "creation_time": frappe.utils.now_datetime(),
    }

    if status:
        row["status"] = status

    doc.append("actions", row)
    doc.save()
    enqueue_link_integration_request(token, request_id)


def enqueue_link_integration_request(token, request_id):
    """
    Integration request is enqueued. Hence, it's name is not available immediately.
    Hence, link it after the request is processed.
    """
    frappe.enqueue(
        link_integration_request, queue="long", token=token, request_id=request_id
    )


def link_integration_request(token, request_id):
    doc_name = frappe.db.get_value("Integration Request", {"request_id": request_id})
    if doc_name:
        frappe.db.set_value(
            "GSTR Action", {"token": token}, {"integration_request": doc_name}
        )
