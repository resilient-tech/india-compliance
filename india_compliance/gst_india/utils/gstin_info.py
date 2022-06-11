from math import ceil

import frappe

from india_compliance.gst_india.utils import titlecase

# ####### SAMPLE DATA for GST_CATEGORIES ########
# "Composition"                             36AASFP8573D2ZN
# "Input Service Distributor (ISD)"         29AABCF8078M2ZW     Flipkart
# "Tax Deductor"                            06DELI09652G1DA 09ALDN00287A1DD 27AAFT56212B1DO 19AAACI1681G1DV
# "SEZ Developer"                           27AAJCS5738D1Z6
# "United Nation Body"                      0717UNO00157UNO 0717UNO00211UN2 2117UNO00002UNF
# "Consulate or Embassy of Foreign Country" 0717UNO00154UNU

# ###### CANNOT BE A PART OF GSTR1 ######
# "Tax Collector (e-Commerce Operator)"     29AABCF8078M1C8 27AAECG3736E1C2
# "Non Resident Online Services Provider"   9917SGP29001OST      Google

# "Non Resident Taxable Person"
# "Government Department ID"

GST_CATEGORIES = {
    "Regular": "Registered Regular",
    "Input Service Distributor (ISD)": "Registered Regular",
    "Composition": "Registered Composition",
    "Tax Deductor": "Tax Deductor",
    "SEZ Unit": "SEZ",
    "SEZ Developer": "SEZ",
    "United Nation Body": "UIN Holders",
    "Consulate or Embassy of Foreign Country": "UIN Holders",
    "URP": "Unregistered",
}


def process_gstin_info_for_autofill(gstin_info):
    business_name = (
        gstin_info.tradeNam if gstin_info.ctb == "Proprietorship" else gstin_info.lgnm
    )

    gstin_details = frappe._dict(
        gstin=gstin_info.gstin,
        business_name=titlecase(business_name),
        gstin_info=gstin_info,
        gst_category=GST_CATEGORIES.get(gstin_info.dty, ""),
    )

    if permanent_address := gstin_info.get("pradr"):
        # permanent address will be at the first position
        addresses = [permanent_address] + gstin_info.get("adadr", [])
        gstin_details.all_addresses = list(map(_get_address, addresses))
        gstin_details.permanent_address = gstin_details.all_addresses[0]

    return gstin_details


def _get_address(address):
    """:param address: dict of address with a key of 'addr' and 'ntr'"""

    address = address.get("addr", {})
    address_lines = _extract_address_lines(address)
    return {
        "address_line1": titlecase(address_lines[0]),
        "address_line2": titlecase(address_lines[1]),
        "city": titlecase(address.get("dst")),
        "state": titlecase(address.get("stcd")),
        "pincode": address.get("pncd"),
        "country": "India",
    }


def _extract_address_lines(address):
    """merge and divide address into exactly two lines"""

    keys = ("bno", "bnm", "flno", "st", "loc", "city")
    full_address = [address.get(key, "").strip() for key in keys if address.get(key)]
    middle = ceil(len(full_address) / 2)
    return (", ".join(full_address[:middle]), ", ".join(full_address[middle:]))
