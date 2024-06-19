# Copyright (c) 2023, Resilient Tech and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import date_diff, format_date, get_datetime

from india_compliance.gst_india.utils import is_api_enabled, validate_gstin_check_digit
from india_compliance.gst_india.utils.gstin_info import (
    fetch_gstin_status,
    fetch_transporter_id_status,
)

GSTIN_STATUS = {
    "ACT": "Active",
    "CNL": "Cancelled",
    "INA": "Inactive",
    "PRO": "Provisional",
    "SUS": "Suspended",
}

GSTIN_BLOCK_STATUS = {"U": 0, "B": 1}


class GSTIN(Document):
    def before_save(self):
        self.status = GSTIN_STATUS.get(self.status, self.status)
        self.is_blocked = GSTIN_BLOCK_STATUS.get(self.is_blocked, 0)
        self.last_updated_on = get_datetime()

        if not self.cancelled_date and self.status == "Cancelled":
            self.cancelled_date = self.registration_date

    @frappe.whitelist()
    def update_gstin_status(self):
        """
        Permission check not required as GSTIN details are public and user has access to doc.
        """
        # hard refresh will always use public API
        create_or_update_gstin_status(self.gstin, throw=True)

    @frappe.whitelist()
    def update_transporter_id_status(self):
        """
        Permission check not required as GSTIN details are public and user has access to doc.
        """
        create_or_update_gstin_status(self.gstin, is_transporter_id=True)


def get_gstr_1_filed_upto(gstin):
    if not gstin:
        return

    return frappe.db.get_value("GSTIN", gstin, "gstr_1_filed_upto")


def create_or_update_gstin_status(
    gstin=None,
    response=None,
    transaction_date=None,
    callback=None,
    is_transporter_id=False,
    throw=False,
):
    doctype = "GSTIN"

    if not response:
        if is_transporter_id:
            response = fetch_transporter_id_status(gstin, throw=throw)
        else:
            response = fetch_gstin_status(gstin=gstin, throw=throw)

        if not response:
            return

    if frappe.db.exists(doctype, response.get("gstin")):
        doc = frappe.get_doc(doctype, response.pop("gstin"))
    else:
        doc = frappe.new_doc(doctype)

    doc.update(response)
    doc.save(ignore_permissions=True)

    if callback:
        callback(doc, transaction_date)

    return doc


### GSTIN Status Validation ###


def get_and_validate_gstin_status(gstin, transaction_date):
    """
    Get and validate GSTIN status.
    Enqueues fetching GSTIN status if required and hence best suited for Backend use.
    """
    if not gstin:
        return

    if not is_status_refresh_required(gstin, transaction_date):
        if not frappe.db.exists("GSTIN", gstin):
            return

        doc = frappe.get_doc("GSTIN", gstin)
        validate_gstin_status(doc, transaction_date, throw=True)

    else:
        # Don't delay the response if API is required
        frappe.enqueue(
            create_or_update_gstin_status,
            enqueue_after_commit=True,
            queue="short",
            gstin=gstin,
            transaction_date=transaction_date,
            callback=validate_gstin_status,
        )


@frappe.whitelist()
def get_gstin_status(gstin, transaction_date=None, force_update=False):
    """
    Get GSTIN status. Responds immediately, and best suited for Frontend use.
    Permission check not required as GSTIN details are public where GSTIN is known.
    """
    if not gstin:
        return

    if not force_update and not is_status_refresh_required(gstin, transaction_date):
        if not frappe.db.exists("GSTIN", gstin):
            return

        return frappe.get_doc("GSTIN", gstin)

    return create_or_update_gstin_status(gstin, throw=force_update)


def validate_gstin_status(gstin_doc, transaction_date=None, throw=False):
    if not (gstin_doc and transaction_date):
        return

    def _throw(message):
        if throw:
            frappe.throw(message)

        else:
            frappe.log_error(
                title=_("Invalid Party GSTIN"),
                message=message,
            )

    registration_date = gstin_doc.registration_date
    cancelled_date = gstin_doc.cancelled_date

    if not registration_date:
        return _throw(
            _(
                "Registration date not found for party GSTIN {0}. Please make sure GSTIN is registered."
            ).format(gstin_doc.gstin)
        )

    if date_diff(transaction_date, registration_date) < 0:
        return _throw(
            _(
                "Party GSTIN {1} is registered on {0}. Please make sure that document date is on or after {0}."
            ).format(format_date(registration_date), gstin_doc.gstin)
        )

    if (
        gstin_doc.status == "Cancelled"
        and date_diff(transaction_date, cancelled_date) >= 0
    ):
        return _throw(
            _(
                "Party GSTIN {1} is cancelled on {0}. Please make sure that document date is before {0}."
            ).format(format_date(cancelled_date), gstin_doc.gstin)
        )

    if gstin_doc.status not in ("Active", "Cancelled"):
        return _throw(
            _("Status of Party GSTIN {1} is {0}").format(
                gstin_doc.status, gstin_doc.gstin
            )
        )


def is_status_refresh_required(gstin, transaction_date):
    settings = frappe.get_cached_doc("GST Settings")

    if (
        not settings.validate_gstin_status
        or not is_api_enabled(settings)
        or settings.sandbox_mode
    ):
        return

    doc = frappe.db.get_value(
        "GSTIN", gstin, ["last_updated_on", "status"], as_dict=True
    )

    if not doc:
        return True

    if not transaction_date:  # not from transactions
        return False

    if doc.status not in ("Active", "Cancelled"):
        return True

    days_since_last_update = date_diff(get_datetime(), doc.get("last_updated_on"))
    return days_since_last_update >= settings.gstin_status_refresh_interval


### GST Transporter ID Validation ###


@frappe.whitelist()
def validate_gst_transporter_id(transporter_id):
    """
    Validates GST Transporter ID and warns user if transporter_id is not Active.
    Just suggestive and not enforced.

    Only for Frontend use.

    Args:
        transporter_id (str): GST Transporter ID
    """
    if not transporter_id:
        return

    gstin = None

    # Check if GSTIN doc exists
    if frappe.db.exists("GSTIN", transporter_id):
        gstin = frappe.get_doc("GSTIN", transporter_id)

    # Check if transporter_id starts with 88 or is not valid GSTIN and use Transporter ID API
    elif transporter_id[:2] == "88" or has_gstin_check_digit_failed(transporter_id):
        gstin = create_or_update_gstin_status(
            transporter_id,
            is_transporter_id=True,
        )

    # Use GSTIN API
    else:
        gstin = create_or_update_gstin_status(transporter_id)

    if not gstin:
        return

    # If GSTIN status is not Active and transporter_id_status is None, use Transporter ID API
    if gstin.status != "Active" and not gstin.transporter_id_status:
        gstin = create_or_update_gstin_status(
            transporter_id,
            is_transporter_id=True,
        )

    # Return if GSTIN or transporter_id_status is Active
    if gstin.status == "Active" or gstin.transporter_id_status == "Active":
        return

    frappe.msgprint(
        _("GST Transporter ID {0} seems to be Invalid").format(transporter_id),
        indicator="orange",
    )


def has_gstin_check_digit_failed(gstin):
    try:
        validate_gstin_check_digit(gstin)

    except frappe.ValidationError:
        return True

    return False
