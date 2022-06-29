import base64
from datetime import datetime
from io import BytesIO

import pyqrcode
from barcode import Code128
from barcode.writer import ImageWriter

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


def get_non_zero_fields(data, fields):
    """Returns a list of fields with non-zero values in order of fields specified"""

    if isinstance(data, dict):
        data = [data]

    non_zero_fields = []
    for row in data:
        for field in fields:
            if row.get(field, 0) != 0 and field not in non_zero_fields:
                non_zero_fields.append(field)
                continue

    return non_zero_fields
