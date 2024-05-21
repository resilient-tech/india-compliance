import json

import frappe


def execute():
    requests = frappe.get_all(
        "Integration Request",
        filters={
            "url": ("like", "%gstr2b%"),
            "data": ("!=", ""),
            "output": ("like", "%RET2B1023%"),
        },
        fields=["data", "output"],
    )

    for request in requests:
        request_data = json.loads(request.data)

        frappe.db.delete(
            "GSTR Import Log",
            filters={
                "data_not_found": 1,
                "return_type": "GSTR2b",
                "gstin": request_data.get("gstin", ""),
                "return_period": request_data.get("rtnprd", ""),
            },
        )
