import base64
import json
from datetime import datetime
from io import BytesIO

import pyqrcode
from barcode import Code128
from barcode.writer import ImageWriter

import frappe
from frappe import _, scrub
from frappe.utils import flt
from erpnext.utilities.regional import temporary_flag

from india_compliance.gst_india.constants.e_waybill import (
    SUB_SUPPLY_TYPES,
    SUPPLY_TYPES,
    TRANSPORT_MODES,
    TRANSPORT_TYPES,
)
from india_compliance.gst_india.overrides.transaction import (
    is_hsn_wise_breakup_needed,
    is_inter_state_supply,
)
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

cess_headers = ["CESS", "CESS Non Advol"]


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


def get_gst_tax_breakup(doc):
    if not doc:
        return

    tax_breakup_data = frappe._dict()
    is_hsn = is_hsn_wise_breakup_needed(doc.doctype + " Item")

    applicable_tax_accounts = (
        ["IGST"] if is_inter_state_supply(doc) else ["CGST", "SGST"]
    )

    with temporary_flag("company", doc.company):
        tax_breakup_data.headers = get_itemised_tax_breakup_header(
            is_hsn, applicable_tax_accounts
        )
        tax_breakup_data.data = get_itemised_tax_breakup_data(
            doc, applicable_tax_accounts, tax_breakup_data.headers, is_hsn
        )

    return json.dumps(tax_breakup_data)


def get_itemised_tax_breakup_header(is_hsn, applicable_tax_accounts):
    if is_hsn:
        return [_("HSN/SAC"), _("Taxable Amount")] + applicable_tax_accounts
    else:
        return [_("Item"), _("Taxable Amount")] + applicable_tax_accounts


def has_non_zero_cess(items):
    if not items:
        return False

    return any(
        any(
            getattr(item, f"{scrub(tax_type)}_rate", 0) != 0
            or getattr(item, f"{scrub(tax_type)}_amount", 0) != 0
            for tax_type in cess_headers
        )
        for item in items
    )


def get_itemised_tax_breakup_data(doc, applicable_tax_accounts, headers, is_hsn):
    if not doc:
        return

    tax_precision = doc.precision("tax_amount", "taxes")
    item_tax_data = frappe._dict()

    if has_non_zero_cess(doc.items):
        applicable_tax_accounts += cess_headers
        headers += cess_headers

    for item in doc.items:
        add_item_tax_data(
            applicable_tax_accounts=applicable_tax_accounts,
            item_tax_data=item_tax_data,
            item=item,
            is_hsn=is_hsn,
            precision=tax_precision,
        )

    return list(item_tax_data.values())


def get_item_key_and_label(item, is_hsn):
    if is_hsn:
        hsn_code = item.gst_hsn_code
        taxes = [item.cgst_rate, item.sgst_rate, item.igst_rate]
        tax_rate = next((rate for rate in taxes if rate != 0), 0)
        return (hsn_code, tax_rate), hsn_code

    else:
        key = item.item_code or item.item_name
        return key, key


def add_item_tax_data(
    item, item_tax_data, applicable_tax_accounts, precision, is_hsn=False
):
    if not item:
        return

    item_key, item_label = get_item_key_and_label(item, is_hsn)

    row = item_tax_data.setdefault(
        item_key,
        frappe._dict({"item": item_label, "taxable_amount": 0}),
    )

    row.taxable_amount += flt(item.taxable_value, precision)
    row_taxes = row.setdefault("taxes", frappe._dict())

    for tax_type in applicable_tax_accounts:
        row_tax = row_taxes.setdefault(
            tax_type, frappe._dict({"tax_rate": 0, "tax_amount": 0})
        )
        if tax_type not in row:
            row_tax.tax_rate = flt(getattr(item, f"{scrub(tax_type)}_rate", 0))

        row_tax.tax_amount += flt(
            getattr(item, f"{scrub(tax_type)}_amount", 0), precision
        )
