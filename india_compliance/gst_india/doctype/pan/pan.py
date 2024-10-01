# Copyright (c) 2024, Resilient Tech and contributors
# For license information, please see license.txt

import random

import requests

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now

multiplication_table = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    [1, 2, 3, 4, 0, 6, 7, 8, 9, 5],
    [2, 3, 4, 0, 1, 7, 8, 9, 5, 6],
    [3, 4, 0, 1, 2, 8, 9, 5, 6, 7],
    [4, 0, 1, 2, 3, 9, 5, 6, 7, 8],
    [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
    [6, 5, 9, 8, 7, 1, 0, 4, 3, 2],
    [7, 6, 5, 9, 8, 2, 1, 0, 4, 3],
    [8, 7, 6, 5, 9, 3, 2, 1, 0, 4],
    [9, 8, 7, 6, 5, 4, 3, 2, 1, 0],
]

permutation_table = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    [1, 5, 7, 6, 2, 8, 3, 0, 9, 4],
    [5, 8, 0, 3, 7, 9, 6, 1, 4, 2],
    [8, 9, 1, 6, 0, 4, 3, 5, 2, 7],
    [9, 4, 5, 3, 1, 2, 6, 8, 7, 0],
    [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
    [2, 7, 9, 3, 8, 0, 6, 4, 1, 5],
    [7, 0, 4, 6, 9, 1, 3, 2, 5, 8],
]

inverse_table = [0, 4, 3, 2, 1, 5, 6, 7, 8, 9]


class PAN(Document):
    @frappe.whitelist()
    def update_pan_status(self):
        fetch_and_update_pan_status(self.pan, True)
        frappe.msgprint(_("PAN Status Updated"))

    def before_save(self):
        self.name = self.pan.upper()


@frappe.whitelist()
def get_pan_status(pan, force_update=False):
    if not force_update and (
        pan_status := frappe.db.get_value("PAN", pan, ["pan_status", "last_updated_on"])
    ):
        return pan_status

    pan_doc = fetch_and_update_pan_status(pan, throw=force_update)
    if not pan_doc:
        return ("", "")

    return (pan_doc.pan_status, pan_doc.last_updated_on)


def fetch_and_update_pan_status(pan, throw, duplicate=False):
    pan_check_result = fetch_pan_status(pan, throw)

    if not pan_check_result:
        return

    error_code_desc_map = {
        "EF40124": "Valid",  # pan linked to generated aadhar card number
        "EF40026": "Valid",  # pan linked but not to generated aadhar card
        "EF40119": "Valid",  # not an individual taxpayer : AAACS8577K
        "EF40089": "Invalid",  # invalid pan : OIMPS2320M
        "EF40024": "Not Linked",
        "EF40077": "",  # Invalid Aadhaar number
    }

    error_code = pan_check_result.get("code", "")

    # if invalid Aadhaar number then check pan status one more time
    if not duplicate and error_code == "EF40077":
        return fetch_and_update_pan_status(pan, throw, duplicate=True)

    status = error_code_desc_map.get(error_code, "")

    if not status:
        return

    # Update PAN status
    if docname := frappe.db.exists("PAN", pan):
        doc = frappe.get_doc("PAN", docname)
    else:
        doc = frappe.new_doc("PAN")

    doc.update(
        {
            "pan": pan,
            "pan_status": status,
            "last_updated_on": now(),
        }
    )
    doc.save(ignore_permissions=True)

    return doc


def fetch_pan_status(pan, throw=False):
    """
    This is an unofficial API
    Use random generated aadhaar number to ensure request is not blocked
    """

    url = "https://eportal.incometax.gov.in/iec/servicesapi/getEntity"

    try:
        payload = {
            "aadhaarNumber": generate_random_aadhar_number(),
            "pan": pan,
            "preLoginFlag": "Y",
            "serviceName": "linkAadhaarPreLoginService",
        }

        response = requests.post(url, json=payload)
        messages = response.json().get("messages", [])

        return messages[0] if messages else {}

    except Exception as e:
        if not throw:
            return

        frappe.throw(
            _("An error occurred while fetching PAN status. {0}. <br><br> {1}").format(
                e, frappe.get_traceback()
            )
        )


def generate_random_aadhar_number():
    """
    Generate a valid Aadhaar number using the Verhoeff algorithm.
    """
    base_number = "".join(str(random.randint(0, 9)) for _ in range(11))
    check_digit = verhoeff_checksum(base_number)
    return base_number + str(check_digit)


def verhoeff_checksum(number: str) -> int:
    """Calculate the Verhoeff checksum digit."""
    checksum = 0
    length = len(number)
    for index in range(length):
        digit = int(number[length - index - 1])
        permuted_digit = permutation_table[(index + 1) % 8][digit]
        checksum = multiplication_table[checksum][permuted_digit]

    return inverse_table[checksum]
