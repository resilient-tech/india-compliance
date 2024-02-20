import base64
import json
from datetime import datetime
from io import BytesIO

import pyqrcode
from barcode import Code128
from barcode.writer import ImageWriter

import frappe
from frappe import scrub
from frappe.utils import flt

from india_compliance.gst_india.constants.e_waybill import (
    SUB_SUPPLY_TYPES,
    SUPPLY_TYPES,
    TRANSPORT_MODES,
    TRANSPORT_TYPES,
)
from india_compliance.gst_india.overrides.transaction import is_inter_state_supply
from india_compliance.gst_india.utils import as_ist

E_INVOICE_ITEM_FIELDS = {
    "SlNo": "Sr.",
    "PrdDesc": "Product Description",
    "HsnCd": "HSN Code",
    "Qty": "Qty",
    "Unit": "UOM",
    "UnitPrice": "Rate",
    "Discount": "Discount",
    "AssAmt": "Taxable Amount",
    "GstRt": "Tax Rate",
    "CesRt": "Cess Rate",
    "TotItemVal": "Total",
}

E_INVOICE_AMOUNT_FIELDS = {
    "AssVal": "Taxable Value",
    "CgstVal": "CGST",
    "SgstVal": "SGST",
    "IgstVal": "IGST",
    "CesVal": "CESS",
    "Discount": "Discount",
    "OthChrg": "Other Charges",
    "RndOffAmt": "Round Off",
    "TotInvVal": "Total Value",
}


def add_spacing(string, interval):
    """
    Add spaces to string at specified intervals
    (https://stackoverflow.com/a/65979478/4767738)
    """

    string = str(string)
    return " ".join(string[i : i + interval] for i in range(0, len(string), interval))


def get_supply_type(code):
    return SUPPLY_TYPES[code]


def get_sub_supply_type(code):
    code = int(code)

    for sub_supply_type, _code in SUB_SUPPLY_TYPES.items():
        if _code == code:
            return sub_supply_type


def get_transport_mode(code):
    code = int(code)

    for transport_mode, _code in TRANSPORT_MODES.items():
        if _code == code:
            return transport_mode


def get_transport_type(code):
    return TRANSPORT_TYPES[int(code)]


def get_e_waybill_qr_code(e_waybill, gstin, ewaybill_date):
    e_waybill_date = as_ist(ewaybill_date)
    qr_text = "/".join(
        (
            str(e_waybill),
            gstin,
            datetime.strftime(e_waybill_date, "%d-%m-%Y %H:%M:%S"),
        )
    )
    return get_qr_code(qr_text)


def get_qr_code(qr_text, scale=5):
    return pyqrcode.create(qr_text).png_as_base64_str(scale=scale, quiet_zone=1)


def get_ewaybill_barcode(ewaybill):
    stream = BytesIO()
    Code128(str(ewaybill), writer=ImageWriter()).write(
        stream,
        {
            "module_width": 0.5,
            "module_height": 16.0,
            "text_distance": 6,
            "font_size": 12,
        },
    )
    barcode_base64 = base64.b64encode(stream.getbuffer()).decode()
    stream.close()

    return barcode_base64


def get_non_zero_fields(data, fields):
    """Returns a list of fields with non-zero values"""

    if isinstance(data, dict):
        data = [data]

    non_zero_fields = set()

    for row in data:
        for field in fields:
            if field not in non_zero_fields and row.get(field, 0) != 0:
                non_zero_fields.add(field)

    return non_zero_fields


def get_fields_to_display(data, field_map, mandatory_fields=None):
    fields_to_display = get_non_zero_fields(data, field_map)
    if mandatory_fields:
        fields_to_display.update(mandatory_fields)

    return {
        field: label for field, label in field_map.items() if field in fields_to_display
    }


def get_e_invoice_item_fields(data):
    return get_fields_to_display(data, E_INVOICE_ITEM_FIELDS, {"GstRt"})


def get_e_invoice_amount_fields(data, doc):
    mandatory_fields = set()
    if is_inter_state_supply(doc):
        mandatory_fields.add("IgstVal")
    else:
        mandatory_fields.update(("CgstVal", "SgstVal"))

    return get_fields_to_display(data, E_INVOICE_AMOUNT_FIELDS, mandatory_fields)


def get_gst_breakup(doc):
    gst_breakup_data = GSTBreakup(doc).get()
    return json.dumps(gst_breakup_data)


class GSTBreakup:
    """
    Returns GST breakup data for the given document
    Output could contain HSN/SAC wise breakup or Item wise breakup as per the GST Settings

    example output:
    [
        {
            "HSN/SAC": "1234",
            "Taxable Amount": 1000,
            "CGST": {
                "tax_rate": 9,
                "tax_amount": 90
            },
            "SGST": {
                "tax_rate": 9,
                "tax_amount": 90
            }
        }
    ]
    """

    CESS_HEADERS = ["CESS", "CESS Non Advol"]

    def __init__(self, doc):
        self.doc = doc
        self.tax_headers = ["IGST"] if is_inter_state_supply(doc) else ["CGST", "SGST"]
        self.precision = doc.precision("tax_amount", "taxes")

        if self.has_non_zero_cess():
            self.tax_headers += self.CESS_HEADERS

        self.needs_hsn_wise_breakup = self.is_hsn_wise_breakup_needed()

    def get(self):
        self.gst_breakup_data = {}

        for item in self.doc.items:
            gst_breakup_row = self.get_default_item_tax_row(item)
            gst_breakup_row["Taxable Amount"] += flt(item.taxable_value, self.precision)

            for tax_type in self.tax_headers:
                _tax_type = scrub(tax_type)
                tax_details = gst_breakup_row.setdefault(
                    tax_type,
                    {
                        "tax_rate": flt(item.get(f"{_tax_type}_rate", 0)),
                        "tax_amount": 0,
                    },
                )

                tax_details["tax_amount"] += flt(
                    item.get(f"{_tax_type}_amount", 0), self.precision
                )

        return list(self.gst_breakup_data.values())

    def has_non_zero_cess(self):
        if not self.doc.items:
            return False

        return any(
            any(
                getattr(item, f"{scrub(tax_type)}_amount", 0) != 0
                for tax_type in self.CESS_HEADERS
            )
            for item in self.doc.items
        )

    def get_default_item_tax_row(self, item):
        if self.needs_hsn_wise_breakup:
            hsn_code = item.gst_hsn_code
            tax_rates = [item.cgst_rate, item.sgst_rate, item.igst_rate]
            tax_rate = next((rate for rate in tax_rates if rate != 0), 0)

            return self.gst_breakup_data.setdefault(
                (hsn_code, tax_rate), {"HSN/SAC": hsn_code, "Taxable Amount": 0}
            )

        else:
            item_code = item.item_code or item.item_name
            return self.gst_breakup_data.setdefault(
                item_code, {"Item": item_code, "Taxable Amount": 0}
            )

    def is_hsn_wise_breakup_needed(self):
        if not frappe.get_meta(self.doc.doctype + " Item").has_field("gst_hsn_code"):
            return False

        if not frappe.get_cached_value("GST Settings", None, "hsn_wise_tax_breakup"):
            return False

        return True
