# Copyright (c) 2023, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import add_to_date, now


class GSTRImportLog(Document):
    pass


def create_import_log(
    gstin,
    return_type,
    return_period,
    data_not_found=False,
    classification=None,
    request_id=None,
    retry_after_mins=None,
):
    frappe.enqueue(
        _create_import_log,
        queue="short",
        now=frappe.flags.in_test,
        gstin=gstin,
        return_type=return_type,
        return_period=return_period,
        data_not_found=data_not_found,
        classification=classification,
        request_id=request_id,
        retry_after_mins=retry_after_mins,
    )


def _create_import_log(
    gstin,
    return_type,
    return_period,
    data_not_found=False,
    classification=None,
    request_id=None,
    retry_after_mins=None,
):
    doctype = "GSTR Import Log"
    filters = {
        "gstin": gstin,
        "return_type": return_type,
        "return_period": return_period,
    }

    # TODO: change classification to gstr_category
    if classification:
        filters["classification"] = classification

    if import_log := frappe.db.exists(doctype, filters):
        import_log = frappe.get_doc(doctype, import_log)
    else:
        import_log = frappe.get_doc({"doctype": doctype, **filters})

    if retry_after_mins:
        import_log.request_time = add_to_date(None, minutes=retry_after_mins)

    import_log.update(
        {
            "request_id": request_id,
            "data_not_found": data_not_found,
            "last_updated_on": now(),
        }
    )
    import_log.save(ignore_permissions=True)

    if request_id:
        toggle_scheduled_jobs(False)


def toggle_scheduled_jobs(stopped):
    if scheduled_job := frappe.db.exists(
        "Scheduled Job Type",
        {
            "method": "india_compliance.gst_india.utils.inward_supply.download_queued_request",
        },
    ):
        frappe.db.set_value("Scheduled Job Type", scheduled_job, "stopped", stopped)
