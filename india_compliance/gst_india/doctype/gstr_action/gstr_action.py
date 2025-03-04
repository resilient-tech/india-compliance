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
        "request_id": request_id,
        "token": token,
        "creation_time": frappe.utils.now_datetime(),
    }

    if status:
        row["status"] = status

    doc.append("actions", row)
    doc.save()
