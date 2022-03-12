import json
import re

import frappe
from frappe import _
from frappe.utils import flt, format_date, get_date_str, nowdate

from india_compliance.gst_india.constants.e_waybill import (
    TRANSPORT_MODES,
    VEHICLE_TYPES,
)
from india_compliance.gst_india.utils import get_gst_accounts_by_type


class GSTInvData:
    TAXES = ("cgst", "sgst", "igst", "cess", "cess_non_advol")
    DATE_FORMAT = "dd/mm/yyyy"

    def __init__(self, doc):
        self.doc = doc
        self.gst_accounts = get_gst_accounts_by_type(
            self.doc.company, gst_account_type="Output"
        ).get("Output")

    def get_invoice_details(self):
        doc = self.doc
        self.validate_invoice_dates(doc)
        doc.update(
            {
                "invoice_type": "CRN" if doc.is_return else "INV",
                "invoice_date": format_date(doc.posting_date, self.DATE_FORMAT),
                "base_total": abs(sum([i.taxable_value for i in doc.items])),
                "rounding_adjustment": -doc.rounding_adjustment
                if doc.is_return
                else doc.rounding_adjustment,
                "base_grand_total": abs(doc.base_rounded_total)
                or abs(doc.base_grand_total),
                "grand_total": abs(doc.rounded_total) or abs(doc.grand_total),
                "discount_amount": 0,
            }
        )
        self.get_invoice_tax_details(doc)
        self.validate_invoice_totals(doc)
        self.get_transporter_details(doc)

    def validate_invoice_dates(self, doc):
        if get_date_str(doc.posting_date) > nowdate():
            frappe.throw(
                msg=_("Posting Date cannot be greater than Today's Date."),
                title=_("Invalid Data"),
            )
        # compare posting date and lr date
        if doc.lr_date and get_date_str(doc.posting_date) > get_date_str(doc.lr_date):
            frappe.throw(
                msg=_("Posting Date cannot be greater than LR Date."),
                title=_("Invalid Data"),
            )

    def validate_invoice_totals(self, doc):
        totals = {"base_total", "rounding_adjustment"}.union(
            f"total_{tax}_amount" for tax in self.TAXES
        )
        base_grand_total = 0
        for total in totals:
            base_grand_total += doc.get(total) or 0

        # difference of upto Rs. 2 is allowed
        if abs(doc.get("base_grand_total") - base_grand_total) > 2:
            frappe.throw(
                msg=_(
                    "Total Invoice value is not matching with sum of taxable-value and taxes."
                ),
                title=_("Invalid Data"),
            )

    def get_invoice_tax_details(self, doc):
        for tax in self.TAXES:
            doc.update({f"total_{tax}_amount": 0})

        for row in doc.taxes:
            if not row.tax_amount or row.account_head not in self.gst_accounts:
                continue

            # TODO: Discuss Post. Assuming only one account per rate of tax.
            # Taxable value is including other charges. Hence, other charges not added.
            tax = self.TAXES[self.gst_accounts.index(row.account_head)]
            tax_amount = row.base_tax_amount_after_discount_amount
            doc.update({f"total_{tax}_amount": tax_amount})

    def get_transporter_details(self, doc):
        # TODO: Move `generate_pary_a` to generate e-Waybill function.
        # transporterId is mandatory for generating Part A Slip and transDocNo, transMode and vehicleNo should be blank
        generate_pary_a = (
            doc.mode_of_transport == "Road"
            and not doc.vehicle_no
            or doc.mode_of_transport in ("Rail", "Air", "Ship")
            and not doc.lr_no
        )
        distance = doc.distance if doc.distance and doc.distance < 4000 else 0

        if generate_pary_a:
            doc.update(
                {
                    "mode_of_transport": None,
                    "vehicle_type": None,
                    "vehicle_no": None,
                    "lr_no": None,
                    "lr_date_str": None,
                    "distance": distance,
                    "transporter_gstin": doc.get("transporter_gstin", default=""),
                }
            )
        else:
            doc.update(
                {
                    "mode_of_transport": TRANSPORT_MODES.get(doc.mode_of_transport),
                    "vehicle_type": VEHICLE_TYPES.get(doc.gst_vehicle_type),
                    "vehicle_no": self.sanitize_data(doc.vehicle_no, "vehicle_no"),
                    "lr_no": self.sanitize_data(doc.lr_no, "special_text"),
                    "lr_date_str": format_date(doc.lr_date, self.DATE_FORMAT),
                    "distance": distance,
                    "transporter_gstin": doc.get("transporter_gstin", default=""),
                }
            )

    def get_item_list(self):
        item_list = []

        for row in self.doc.items:
            if row.batch_no:
                batch_expiry_date = frappe.db.get_value(
                    "Batch", row.batch_no, "expiry_date"
                )
                batch_expiry_date_str = format_date(batch_expiry_date, self.DATE_FORMAT)
            else:
                batch_expiry_date_str = ""

            row.update(
                {
                    "qty": abs(row.qty),
                    "rate": abs(row.taxable_value)
                    if flt(row.qty) == 0
                    else abs(row.taxable_value / row.qty),
                    "taxable_value": abs(row.taxable_value),
                    "discount_amount": 0,
                    "is_service_item": "Y"
                    if row.gst_hsn_code and row.gst_hsn_code[:2] == "99"
                    else "N",
                    "hsn_code": int(row.gst_hsn_code),
                    "batch_expiry_date_str": batch_expiry_date_str,
                    "serial_no": "",
                    "item_name": self.sanitize_data(row.item_name, "text"),
                    "uom": "",
                }
            )
            self.get_item_tax_details(row)
            row = self.map_template(self.item_map, row)
            item_list.append(row)

        return item_list

    def get_item_tax_details(self, item):
        for tax in self.TAXES:
            item.update({f"{tax}_amount": 0, f"{tax}_rate": 0})

        for row in self.doc.taxes:
            if not row.tax_amount or row.account_head not in self.gst_accounts:
                continue

            # Remove '_account' from 'cgst_account'
            tax = self.TAXES[self.gst_accounts.index(row.account_head)]
            tax_rate = json.loads(row.item_wise_tax_detail).get(
                item.item_code or item.item_name
            )[0]

            # considers senarios where same item is there multiple times
            tax_amount = (
                tax_rate * item.qty
                if row.charge_type == "On Item Quantity"
                else tax_rate * item.taxable_value / 100
            )
            item.update(
                {
                    f"{tax}_rate": tax_rate,
                    f"{tax}_amount": tax_amount,
                }
            )
        item.update(
            {
                "tax_rate": sum(
                    [flt(item.get(f"{tax}_rate", 0)) for tax in self.TAXES[:3]]
                ),
                "total_value": abs(
                    item.taxable_value
                    + sum([flt(item.get(f"{tax}_amount", 0)) for tax in self.TAXES])
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
                    "Address Lines, City, Pincode{0} are mandatory for address {1}. Please set them and try again."
                ).format(", GSTIN" if gstin_validation else "", address.name),
                title=_("Missing Address Fields"),
            )

    def map_template(self, map, data):
        return {
            key: data.get(value)
            for key, value in map.items()
            if value and data.get(value) is not None
        }

    def sanitize_data(self, data, method, min_length=0, max_length=100):
        if not data or len(data) < min_length:
            return ""

        if method == "text":
            data = re.sub(r"[^\w@#\-\/,&. ]", "", data)
        elif method == "special_text":
            data = re.sub(r"[^\w\-\/. ]", "", data)
        elif method == "vehicle_no":
            data = re.sub(r"[^\w]", "", data).upper()

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
