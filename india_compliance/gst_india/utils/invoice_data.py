import json
import re

import frappe
from frappe import _
from frappe.utils import cint, flt, format_date, get_date_str, nowdate

from india_compliance.gst_india.constants.e_waybill import (
    TRANSPORT_MODES,
    UOMS,
    VEHICLE_TYPES,
)
from india_compliance.gst_india.utils import get_gst_accounts_by_type


class GSTInvoiceData:
    TAXES = ("cgst", "sgst", "igst", "cess", "cess_non_advol")
    DATE_FORMAT = "dd/mm/yyyy"

    def __init__(self, doc, json_download=False, sandbox=False):
        self.doc = doc
        self.json_download = json_download
        self.sandbox = sandbox
        self.gst_accounts = {
            v: k
            for k, v in get_gst_accounts_by_type(self.doc.company, "Output").items()
        }
        self.settings = frappe.get_cached_doc("GST Settings")

    def get_invoice_details(self):
        self.invoice_details = frappe._dict()
        self.update_invoice_details()
        self.get_invoice_tax_details()

    def update_invoice_details(self):
        self.invoice_details.update(
            {
                "invoice_date": format_date(self.doc.posting_date, self.DATE_FORMAT),
                "base_total": abs(
                    round(sum([i.taxable_value for i in self.doc.items]), 2)
                ),
                "rounding_adjustment": round(-self.doc.rounding_adjustment, 2)
                if self.doc.is_return
                else round(self.doc.rounding_adjustment, 2),
                "base_grand_total": round(abs(self.doc.base_rounded_total), 2)
                or round(abs(self.doc.base_grand_total), 2),
                "discount_amount": 0,
                "company_gstin": self.doc.company_gstin,
                "invoice_number": self.doc.name,
            }
        )

    def get_invoice_tax_details(self):
        for tax in self.TAXES:
            self.invoice_details.update({f"total_{tax}_amount": 0})

        for row in self.doc.taxes:
            if not row.tax_amount or row.account_head not in self.gst_accounts:
                continue

            tax = self.gst_accounts[row.account_head][:-8]
            tax_amount = round(abs(row.base_tax_amount_after_discount_amount), 2)
            self.invoice_details.update({f"total_{tax}_amount": tax_amount})

        self.get_other_charges()

    def get_other_charges(self):
        totals = {"base_total", "rounding_adjustment"}.union(
            f"total_{tax}_amount" for tax in self.TAXES
        )
        base_grand_total = 0
        for total in totals:
            base_grand_total += self.invoice_details.get(total)

        self.invoice_details.other_charges = round(
            (self.invoice_details.base_grand_total - base_grand_total), 2
        )

    def get_transporter_details(self):
        distance = (
            cint(self.doc.distance)
            if self.doc.distance and self.doc.distance < 4000
            else 0
        )
        transport_mode = self.doc.get("mode_of_transport")
        missing_transport_details = (
            not transport_mode
            or transport_mode == "Road"
            and not self.doc.get("vehicle_no")
            or (transport_mode == "Ship")
            and not self.doc.get("vehicle_no")
            and not self.doc.get("lr_no")
            or transport_mode in ["Rail", "Air"]
            and not self.doc.get("lr_no")
        )
        if missing_transport_details:
            if not self.doc.get("gst_transporter_id"):
                self.invoice_details.distance = distance
                return
            generate_part_a = True

        if generate_part_a:
            self.invoice_details.update(
                {
                    "mode_of_transport": 1 if self.json_download else "",
                    "vehicle_type": "R" if self.json_download else "",
                    "vehicle_no": "",
                    "lr_no": "",
                    "lr_date_str": "",
                    "distance": distance,
                    "gst_transporter_id": self.doc.get("gst_transporter_id"),
                    "transporter_name": self.doc.get("transporter_name", default=""),
                }
            )
        else:
            self.invoice_details.update(
                {
                    "mode_of_transport": TRANSPORT_MODES.get(
                        self.doc.mode_of_transport
                    ),
                    "vehicle_type": VEHICLE_TYPES.get(self.doc.gst_vehicle_type) or "R",
                    "vehicle_no": self.sanitize_data(self.doc.vehicle_no, "vehicle_no"),
                    "lr_no": self.sanitize_data(self.doc.lr_no, "special_text"),
                    "lr_date_str": format_date(self.doc.lr_date, self.DATE_FORMAT),
                    "distance": distance,
                    "gst_transporter_id": self.doc.get(
                        "gst_transporter_id", default=""
                    ),
                    "transporter_name": self.doc.get("transporter_name", default=""),
                }
            )

    def pre_validate_invoice(self):
        if get_date_str(self.doc.posting_date) > nowdate():
            frappe.throw(
                msg=_("Posting Date cannot be greater than Today's Date"),
                title=_("Invalid Data"),
            )
        # compare posting date and lr date
        if self.doc.lr_date and get_date_str(self.doc.posting_date) > get_date_str(
            self.doc.lr_date
        ):
            frappe.throw(
                msg=_("Posting Date cannot be greater than LR Date"),
                title=_("Invalid Data"),
            )

    def validate_company(self):
        country, gst_category = frappe.get_cached_value(
            "Company", self.doc.company, ("country", "gst_category")
        )
        if country != "India":
            frappe.throw(
                _("Company selected is not an Indian Company"),
                title=_("Invalid Company"),
            )
        if gst_category == "Unregistered":
            frappe.throw(_("Please set the GST Category in the company master"))

    def validate_non_gst_items(self):
        if self.doc.items[0].is_non_gst:
            frappe.throw(
                msg=_(
                    "You have Non GST Items in this Invoice for which e-Waybill is not"
                    " applicable"
                ),
                title=_("Invalid Data"),
            )

    def get_item_list(self):
        self.item_list = []

        for row in self.doc.items:
            self.item_details = frappe._dict()
            self.update_item_details(row)
            self.get_item_tax_details(row)
            self.item_list.append(self.get_item_map() or {})

        self.item_list = ", ".join(self.item_list)

    def update_item_details(self, row):
        self.item_details.update(
            {
                "item_no": row.idx,
                "qty": round(abs(row.qty), 2),
                "taxable_value": round(abs(row.taxable_value), 2),
                "hsn_code": int(row.gst_hsn_code),
                "item_name": self.sanitize_data(row.item_name, "text"),
                "uom": row.uom if UOMS.get(row.uom) else "OTH",
            }
        )

    def get_item_tax_details(self, item):
        for tax in self.TAXES:
            self.item_details.update({f"{tax}_amount": 0, f"{tax}_rate": 0})

        for row in self.doc.taxes:
            if not row.tax_amount or row.account_head not in self.gst_accounts:
                continue

            # Remove '_account' from 'cgst_account'
            tax = self.gst_accounts[row.account_head][:-8]
            tax_rate = json.loads(row.item_wise_tax_detail).get(
                item.item_code or item.item_name
            )[0]

            # considers senarios where same item is there multiple times
            tax_amount = round(
                abs(
                    tax_rate * item.qty
                    if row.charge_type == "On Item Quantity"
                    else tax_rate * item.taxable_value / 100
                ),
                2,
            )
            self.item_details.update(
                {
                    f"{tax}_rate": tax_rate,
                    f"{tax}_amount": tax_amount,
                }
            )
        self.item_details.update(
            {
                "tax_rate": sum(
                    [
                        flt(self.item_details.get(f"{tax}_rate", 0))
                        for tax in self.TAXES[:3]
                    ]
                ),
                "total_value": round(
                    abs(
                        self.item_details.taxable_value
                        + sum(
                            [
                                flt(self.item_details.get(f"{tax}_amount", 0))
                                for tax in self.TAXES
                            ]
                        )
                    ),
                    2,
                ),
            }
        )

    def get_address_details(self, address_name, gstin_validation=False):
        addr = frappe.get_doc("Address", address_name)

        if addr.gst_state_number == 97:  # For Other Territory
            addr.pincode = 999999

        if addr.country != "India":
            addr.gst_state_number = 96
            addr.pincode = 999999

        self.check_missing_address_fields(addr, gstin_validation)
        party_address_details = {
            "gstin": addr.get("gstin") or "URP",
            "state_code": int(addr.gst_state_number),
            "address_title": self.sanitize_data(addr.address_title, "special_text"),
            "address_line1": self.sanitize_data(addr.address_line1, "text"),
            "address_line2": self.sanitize_data(addr.address_line2, "text"),
            "city": self.sanitize_data(addr.city, "text", max_length=50),
            "pincode": self.validate_data(addr.pincode, "pincode"),
        }
        return frappe._dict(party_address_details)

    def check_missing_address_fields(self, address, gstin_validation):
        if (
            (not address.gstin and gstin_validation)
            or not address.city
            or not address.pincode
            or not address.address_title
            or not address.address_line1
            or not address.gst_state_number
        ):

            frappe.throw(
                msg=_(
                    "Address Lines, City, Pincode{0} are mandatory for address {1}."
                    " Please set them and try again."
                ).format(", GSTIN" if gstin_validation else "", address.name),
                title=_("Missing Address Fields"),
            )

    def get_invoice_map(self):
        pass

    def get_item_map(self):
        pass

    def map_template(self, map, data):
        return {
            key: data.get(value)
            for key, value in map.items()
            if value and data.get(value) is not None
        }

    def sanitize_invoice_map(self, invoice_data):
        copy = invoice_data.copy()
        for key, value in copy.items():
            if isinstance(value, list):
                for idx, d in enumerate(value):
                    santized_dict = self.sanitize_invoice_map(d)
                    if santized_dict:
                        invoice_data[key][idx] = santized_dict
                    else:
                        invoice_data[key].pop(idx)

                if not invoice_data[key]:
                    invoice_data.pop(key, None)

            elif isinstance(value, dict):
                santized_dict = self.sanitize_invoice_map(value)
                if santized_dict:
                    invoice_data[key] = santized_dict
                else:
                    invoice_data.pop(key, None)

            elif not value and value != 0 or value == "None":
                invoice_data.pop(key, None)

        return invoice_data

    def sanitize_data(self, data, method, min_length=0, max_length=100):
        if not data or len(data) < min_length:
            return ""

        if method == "text":
            data = re.sub(r"[^\w@#\-\/,&. ]|[_]", "", data)
        elif method == "special_text":
            data = re.sub(r"[^\w\-\/. ]|[_]", "", data)
        elif method == "vehicle_no":
            data = re.sub(r"[^\w]|[_]", "", data).upper()

        return data[:max_length]

    def validate_data(self, data, method):
        if not data:
            return ""

        if method == "pincode":
            pattern = re.compile(r"^[1-9][0-9]{5}$")
            if not pattern.match(data):
                frappe.throw(
                    msg=_("Field {} must be with 6 digits.").format(method),
                    title=_("Invalid Data"),
                )
            data = int(data)

        return data
