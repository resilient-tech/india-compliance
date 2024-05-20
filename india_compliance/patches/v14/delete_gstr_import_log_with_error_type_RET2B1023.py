import json

import frappe


def execute():
    requests = frappe.get_list(
        "Integration Request",
        filters={"url": ("like", "%gstr2b%"), "data": ("!=", ""), "output": ("!=", "")},
        fields=["data", "output"],
    )

    for request in requests:
        request_data = json.loads(request.data)
        response = json.loads(request.output)

        error = response.get("error", {})
        if error.get("error_cd", "") == "RET2B1023":
            frappe.db.delete(
                "GSTR Import Log",
                filters={
                    "data_not_found": 1,
                    "gstin": request_data.get("gstin", ""),
                    "return_period": request_data.get("rtnprd", ""),
                },
            )
