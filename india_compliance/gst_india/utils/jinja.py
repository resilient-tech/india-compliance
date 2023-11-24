import base64
from datetime import datetime
from io import BytesIO

import pyqrcode
from barcode import Code128
from barcode.writer import ImageWriter

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
