import re

import frappe
from frappe import _
from frappe.utils import escape_html

from india_compliance.gst_india.constants import IFSC_CODE


def validate(doc, method=None):
    if not doc.get("ifsc_code"):
        return

    doc.ifsc_code = re.sub(r"[\s-]", "", doc.ifsc_code).upper()
    if doc.ifsc_code and not IFSC_CODE.match(doc.ifsc_code):
        frappe.throw(
            _(
                "IFSC Code {0} is invalid. It must be 11 characters:"
                " 4 letters, the digit zero, then 6 letters or digits."
            ).format(frappe.bold(escape_html(doc.ifsc_code))),
            title=_("Invalid IFSC Code"),
        )
