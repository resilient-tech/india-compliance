# Copyright (c) 2024, Resilient Tech and contributors
# For license information, please see license.txt

import random

import requests

import frappe
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


class Pan(Document):
    @frappe.whitelist()
    def update_pan_status(self):
        get_pancard_status(self.pan, True)
        frappe.msgprint("PAN Status Updated")

    def before_save(self):
        self.name = self.pan.upper()


def verhoeff_checksum(number: str) -> int:
    """Calculate the Verhoeff checksum digit."""
    c = 0
    n = len(number)
    for i in range(n):
        c = multiplication_table[c][
            permutation_table[(i + 1) % 8][int(number[n - i - 1])]
        ]
    return inverse_table[c]


def generate_aadhaar_number():
    """Generate a valid Aadhaar number using the Verhoeff algorithm."""
    base_number = "".join(str(random.randint(0, 9)) for _ in range(11))
    check_digit = verhoeff_checksum(base_number)
    return base_number + str(check_digit)


def fetch_pan_status_from_api(aadhaar_number, pan, force_update):
    """This is an unofficial API"""
    url = "https://eportal.incometax.gov.in/iec/servicesapi/getEntity"
    payload = {
        "aadhaarNumber": aadhaar_number,  # this is random generated aadhaar_number
        "pan": pan,
        "preLoginFlag": "Y",
        "serviceName": "linkAadhaarPreLoginService",
    }

    try:
        response = requests.post(url, json=payload)
        return response.json().get("messages", [])
    except ConnectionError:
        msg = "Connection error. Please retry after some time."
    except Exception:
        msg = "An error occurred. Please retry after some time."

    if force_update:
        frappe.throw(msg)
    else:
        return ""


def update_pan_document(pan, status):
    if docname := frappe.db.exists("Pan", pan):
        doc = frappe.get_doc("Pan", docname)
    else:
        doc = frappe.new_doc("Pan")

    doc.update(
        {
            "pan": pan,
            "pan_status": status,
            "last_updated_on": now(),
        }
    )
    doc.save()


def get_pancard_status(pan, force_update):
    aadhaar_number = generate_aadhaar_number()
    messages = fetch_pan_status_from_api(aadhaar_number, pan, force_update)

    if not messages:
        return

    error_code_desc_map = {
        "EF40124": "Valid",  # pan linked to generated aadhar card number
        "EF40026": "Valid",  # pan linked but not to generated aadhar card
        "EF40119": "Valid",  # not an individual taxpayer : AAACS8577K
        "EF40089": "Invalid",  # invalid pan : OIMPS2320M
        "EF40024": "Not-Linked",
        "EF40077": "",  # Invalid Aadhaar number
    }

    status = error_code_desc_map.get(messages[0].get("code", ""), "")
    if not status:
        return

    update_pan_document(pan, status)


@frappe.whitelist()
def get_pan_status(pan, force_update=False):
    if force_update or not frappe.db.exists("Pan", pan):
        get_pancard_status(pan, force_update)

    return frappe.db.get_value("Pan", pan, ["pan_status", "last_updated_on"])
