# Copyright (c) 2022, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import add_to_date


class GSTRImportLog(Document):
    pass


def create_import_log(
    gstin,
    return_type,
    return_period,
    classification=None,
    data_not_found=False,
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
    classification=None,
    data_not_found=False,
    request_id=None,
    retry_after_mins=None,
):
    doctype = "GSTR Import Log"
    fields = {
        "gstin": gstin,
        "return_type": return_type,
        "return_period": return_period,
    }

    # TODO: change classification to gstr_category
    if classification:
        fields["classification"] = classification

    if log := frappe.db.get_value(doctype, fields):
        log = frappe.get_doc(doctype, log)
    else:
        log = frappe.get_doc({"doctype": doctype, **fields})

    if retry_after_mins:
        log.request_time = add_to_date(None, minutes=retry_after_mins)

    log.request_id = request_id
    log.data_not_found = data_not_found
    log.last_updated_on = frappe.utils.now()
    log.save(ignore_permissions=True)
    if request_id:
        toggle_scheduled_jobs(False)


def toggle_scheduled_jobs(stopped):
    scheduled_job = frappe.db.get_value(
        "Scheduled Job Type",
        {
            "method": "india_compliance.gst_india.utils.gstr.download_queued_request",
        },
    )

    if scheduled_job:
        frappe.db.set_value("Scheduled Job Type", scheduled_job, "stopped", stopped)
