import json
import re

import frappe
from frappe import _
from frappe.utils import format_date, getdate, rounded

from india_compliance.gst_india.constants import GST_TAX_TYPES, PINCODE_FORMAT
from india_compliance.gst_india.constants.e_waybill import (
    TRANSPORT_MODES,
    UOMS,
    VEHICLE_TYPES,
)
from india_compliance.gst_india.utils import get_gst_accounts_by_type

ALLOWED_CHARACTERS = {
    0: re.compile(r"[^A-Za-z0-9]"),
    1: re.compile(r"[^A-Za-z0-9@#\-\/,&. ]"),
    2: re.compile(r"[^A-Za-z0-9@#\-\/,&. ]"),
}


class GSTInvoiceData:
    DATE_FORMAT = "dd/mm/yyyy"

    def __init__(self, doc, *, sandbox=False):
        self.doc = doc
        self.sandbox = sandbox
        self.settings = frappe.get_cached_doc("GST Settings")
        self.invoice_details = frappe._dict()

        # CGST Account - TC: "cgst_account"
        self.gst_accounts = {
            v: k
            for k, v in get_gst_accounts_by_type(self.doc.company, "Output").items()
        }

    def get_invoice_details(self):
        rounding_adjustment = self.rounded(self.doc.rounding_adjustment)
        if self.doc.is_return:
            rounding_adjustment = -rounding_adjustment

        grand_total_fieldname = (
            "base_grand_total"
            if self.doc.disable_rounded_total
            else "base_rounded_total"
        )

        self.invoice_details.update(
            {
                "invoice_date": format_date(self.doc.posting_date, self.DATE_FORMAT),
                "base_total": abs(
                    self.rounded(sum(row.taxable_value for row in self.doc.items))
                ),
                "rounding_adjustment": rounding_adjustment,
                "base_grand_total": abs(
                    self.rounded(self.doc.get(grand_total_fieldname))
                ),
                "discount_amount": 0,
                "company_gstin": self.doc.company_gstin,
                "invoice_number": self.doc.name,
            }
        )
        self.update_invoice_details()
        self.get_invoice_tax_details()

    def update_invoice_details(self):
        # to be overrridden
        pass

    def get_invoice_tax_details(self):
        tax_totals = [f"total_{tax}_amount" for tax in GST_TAX_TYPES]

        for key in tax_totals:
            self.invoice_details[key] = 0

        for row in self.doc.taxes:
            if not row.tax_amount or row.account_head not in self.gst_accounts:
                continue

            tax = self.gst_accounts[row.account_head][:-8]
            self.invoice_details[f"total_{tax}_amount"] = abs(
                self.rounded(row.base_tax_amount_after_discount_amount)
            )

        # Other Charges
        current_total = 0
        for total in ["base_total", "rounding_adjustment", *tax_totals]:
            current_total += self.invoice_details.get(total)

        self.invoice_details.other_charges = self.rounded(
            (self.invoice_details.base_grand_total - current_total)
        )

    def validate_mode_of_transport(self, throw=True):
        def _throw(error):
            if throw:
                frappe.throw(error, title=_("Invalid Transporter Details"))

        if not (mode_of_transport := self.doc.mode_of_transport):
            return _throw(
                _(
                    "Either GST Transporter ID or Mode of Transport is required to"
                    " generate e-Waybill"
                )
            )

        if mode_of_transport == "Road" and not self.doc.vehicle_no:
            return _throw(
                _(
                    "Vehicle Number is required to generate e-Waybill for supply via"
                    " Road"
                )
            )
        if mode_of_transport == "Ship" and not (self.doc.vehicle_no and self.doc.lr_no):
            return _throw(
                _(
                    "Vehicle Number and L/R No is required to generate e-Waybill for"
                    " supply via Ship"
                )
            )
        if mode_of_transport in ("Rail", "Air") and not self.doc.lr_no:
            return _throw(
                _(
                    "L/R No. is required to generate e-Waybill for supply via Rail"
                    " or Air"
                )
            )

        return True

    def get_transporter_details(self):
        self.invoice_details.distance = (
            self.doc.distance if self.doc.distance and self.doc.distance < 4000 else 0
        )

        if self.validate_mode_of_transport(False):
            self.invoice_details.update(
                {
                    "mode_of_transport": TRANSPORT_MODES.get(
                        self.doc.mode_of_transport
                    ),
                    "vehicle_type": VEHICLE_TYPES.get(self.doc.gst_vehicle_type) or "R",
                    "vehicle_no": re.sub(
                        ALLOWED_CHARACTERS[0], "", self.doc.vehicle_no
                    ),
                    "lr_no": self.sanitize_value(self.doc.lr_no, False),
                    "lr_date": format_date(self.doc.lr_date, self.DATE_FORMAT)
                    if self.doc.lr_no
                    else "",
                    "gst_transporter_id": self.doc.gst_transporter_id or "",
                    "transporter_name": self.doc.transporter_name or "",
                }
            )

        #  Part A Only
        elif self.doc.gst_transporter_id:
            for_json = getattr(self, "for_json", False)
            self.invoice_details.update(
                {
                    "mode_of_transport": 1 if for_json else "",
                    "vehicle_type": "R" if for_json else "",
                    "vehicle_no": "",
                    "lr_no": "",
                    "lr_date": "",
                    "gst_transporter_id": self.doc.gst_transporter_id,
                    "transporter_name": self.doc.transporter_name or "",
                }
            )

    def validate_invoice(self):
        posting_date = getdate(self.doc.posting_date)

        if posting_date > getdate():
            frappe.throw(
                msg=_("Posting Date cannot be greater than Today's Date"),
                title=_("Invalid Data"),
            )
        # compare posting date and lr date, only if lr no is set
        if (
            self.doc.lr_no
            and self.doc.lr_date
            and posting_date > getdate(self.doc.lr_date)
        ):
            frappe.throw(
                msg=_("Posting Date cannot be greater than LR Date"),
                title=_("Invalid Data"),
            )

    def validate_non_gst_items(self):
        if self.doc.items[0].is_non_gst:
            frappe.throw(
                _("This action cannot be performed for invoices with non-GST items"),
                title=_("Invalid Data"),
            )

    def get_item_list(self):
        self.item_list = []

        for row in self.doc.items:
            item_details = frappe._dict(
                {
                    "item_no": row.idx,
                    "qty": abs(
                        self.rounded(row.qty, self.doc.precision("qty", "items"))
                    ),
                    "taxable_value": abs(self.rounded(row.taxable_value)),
                    "hsn_code": row.gst_hsn_code,
                    "item_name": self.sanitize_value(row.item_name),
                    "uom": row.uom if UOMS.get(row.uom) else "OTH",
                }
            )
            self.update_item_details(item_details, row)
            self.get_item_tax_details(item_details, row)
            self.item_list.append(self.get_item_data(item_details))

    def update_item_details(self, item_details, item):
        # to be overridden
        pass

    def get_item_tax_details(self, item_details, item):
        for tax in GST_TAX_TYPES:
            item_details.update({f"{tax}_amount": 0, f"{tax}_rate": 0})

        for row in self.doc.taxes:
            if not row.tax_amount or row.account_head not in self.gst_accounts:
                continue

            # Remove '_account' from 'cgst_account'
            tax = self.gst_accounts[row.account_head][:-8]
            tax_rate = frappe.parse_json(row.item_wise_tax_detail).get(
                item.item_code or item.item_name
            )[0]

            # considers senarios where same item is there multiple times
            tax_amount = abs(
                self.rounded(
                    tax_rate * item.qty
                    if row.charge_type == "On Item Quantity"
                    else tax_rate * item.taxable_value / 100
                ),
            )

            item_details.update(
                {
                    f"{tax}_rate": tax_rate,
                    f"{tax}_amount": tax_amount,
                }
            )

        item_details.update(
            {
                "tax_rate": sum(
                    self.rounded(item_details.get(f"{tax}_rate", 0))
                    for tax in GST_TAX_TYPES[:3]
                ),
                "total_value": abs(
                    self.rounded(
                        item_details.taxable_value
                        + sum(
                            self.rounded(item_details.get(f"{tax}_amount", 0))
                            for tax in GST_TAX_TYPES
                        )
                    ),
                ),
            }
        )

    def get_address_details(self, address_name, validate_gstin=False):
        address = frappe.get_cached_value(
            "Address",
            address_name,
            (
                "address_title",
                "address_line1",
                "address_line2",
                "city",
                "pincode",
                "country",
                "gstin",
                "gst_state_number",
            ),
            as_dict=True,
        )

        if address.gst_state_number == 97:  # For Other Territory
            address.pincode = 999999

        if address.country != "India":
            address.gst_state_number = 96
            address.pincode = 999999

        self.check_missing_address_fields(address, validate_gstin)

        return frappe._dict(
            {
                "gstin": address.get("gstin") or "URP",
                "state_code": int(address.gst_state_number),
                "address_title": self.sanitize_value(address.address_title, False),
                "address_line1": self.sanitize_value(address.address_line1),
                "address_line2": self.sanitize_value(address.address_line2),
                "city": self.sanitize_value(address.city, max_length=50),
                "pincode": int(address.pincode),
            }
        )

    def check_missing_address_fields(self, address, validate_gstin=False):
        fieldnames = [
            "address_title",
            "address_line1",
            "city",
            "pincode",
            "gst_state_number",
        ]

        if validate_gstin:
            fieldnames.append("gstin")

        for fieldname in fieldnames:
            if address.get(fieldname):
                continue

            frappe.throw(
                _(
                    "{0} is missing in Address {1}. Please update it and try again."
                ).format(
                    frappe.bold(address.meta.get_label(fieldname)),
                    frappe.bold(address.name),
                ),
                title=_("Missing Address Details"),
            )

        if not PINCODE_FORMAT.match(address.pincode):
            frappe.throw(
                _(
                    "PIN Code for Address {0} must be a 6-digit number and cannot start"
                    " with 0"
                ).format(frappe.bold(address.name)),
                title=_("Invalid Data"),
            )

    def get_item_data(self, item_details):
        pass

    @staticmethod
    def sanitize_data(d):
        """Adapted from https://stackoverflow.com/a/27974027/4767738"""

        def _is_truthy(v):
            return v or v == 0

        if isinstance(d, dict):
            return {
                k: v
                for k, v in ((k, GSTInvoiceData.sanitize_data(v)) for k, v in d.items())
                if _is_truthy(v)
            }

        if isinstance(d, list):
            return [v for v in map(GSTInvoiceData.sanitize_data, d) if _is_truthy(v)]

        return d

    @staticmethod
    def rounded(value, precision=2):
        return rounded(value, precision)

    @staticmethod
    def sanitize_value(
        value,
        allow_special_characters=True,
        min_length=0,
        max_length=100,
    ):
        if not value or len(value) < min_length:
            return

        value = re.sub(
            ALLOWED_CHARACTERS[2 if allow_special_characters else 1], "", value
        )

        return value[:max_length]
