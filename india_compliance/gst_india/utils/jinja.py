import base64
from datetime import datetime
from io import BytesIO

import pyqrcode
from barcode import Code128
from barcode.writer import ImageWriter

from frappe.utils import fmt_money

from india_compliance.gst_india.constants import STATE_NUMBERS
from india_compliance.gst_india.constants.e_invoice import E_INVOICE_DATA_MAP
from india_compliance.gst_india.constants.e_waybill import (
    SUB_SUPPLY_TYPES,
    TRANSPORT_MODES,
    TRANSPORT_TYPES,
)
from india_compliance.gst_india.utils import as_ist


def add_spacing(string, interval):
    """
    Add spaces to string at specified intervals
    (https://stackoverflow.com/a/65979478/4767738)
    """

    string = str(string)
    return " ".join(string[i : i + interval] for i in range(0, len(string), interval))


def get_state(state_number):
    """Get state from State Number"""

    state_number = str(state_number)

    for state, code in STATE_NUMBERS.items():
        if code == state_number:
            return state


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
            "module_width": 0.4,
            "text_distance": 2,
            "font_size": 20,
        },
    )
    barcode_base64 = base64.b64encode(stream.getbuffer()).decode()
    stream.close()

    return barcode_base64


def get_zero_amount_fields(item_list=None):
    fields = ("Qty", "UnitPrice", "Discount", "AssAmt", "GstRt", "CesRt", "TotItemVal")
    if item_list:
        zero_amount_fields = []
        for field in fields:
            zero_amount_fields.append(field) if all(
                item[field] == 0 for item in item_list
            ) else None
        return zero_amount_fields


def get_non_zero_formatted_fields(data):
    """
    Filter out zero fields from data and return them with their respective labels
    returns a list of ordered dicts with formated currency as follows:
    [
        {
            "Sr. No.": 1,
            "Product Description": "Product 1",
            "Taxable Amount": "₹ 100.00",
            ...
        }
    ]
    """
    if isinstance(data, dict):
        data = [data]

    non_zero_keys = set(field for row in data for field in row if row[field] != 0)
    new_data = []

    for row in data:
        new_row = {
            E_INVOICE_DATA_MAP[key]: fmt_values(key, row[key])
            for key in E_INVOICE_DATA_MAP
            if key in non_zero_keys
        }
        new_data.append(new_row)

    return new_data


def fmt_values(key, value):
    if key[-3:] in ["Val", "Amt"]:
        return fmt_money(value, None, "INR")
    return value


def get_address_html(address):
    """Get address html from address dict of e-Invoice data"""

    address_html = []
    address_fields = ["Gstin", "LglNm", "Nm", "Addr1", "Addr2", "Loc"]

    for field in address_fields:
        if field in address:
            address_html.append(f"<p>{address[field]}</p>")

    address_html.append(
        "<p>{0} - {1}</p>".format(get_state(address["Stcd"]), address["Pin"])
    )
    return "".join(address_html)
