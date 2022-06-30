import frappe
from frappe import _

from india_compliance.gst_india.api_classes.public import PublicAPI
from india_compliance.gst_india.constants import OVERSEAS, REGISTERED, TDS, UNBODY
from india_compliance.gst_india.utils import titlecase, validate_gstin

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


@frappe.whitelist()
def get_gstin_info(gstin):
    if (
        frappe.get_cached_value("User", frappe.session.user, "user_type")
        == "Website User"
    ):
        frappe.throw(_("Not allowed"), frappe.PermissionError)

    validate_gstin(gstin)
    response = PublicAPI().get_gstin_info(gstin)

    business_name = (
        response.tradeNam if response.ctb == "Proprietorship" else response.lgnm
    )

    gstin_info = frappe._dict(
        gstin=response.gstin,
        business_name=titlecase(business_name),
        gst_category=GST_CATEGORIES.get(response.dty, ""),
    )

    if permanent_address := response.get("pradr"):
        # permanent address will be at the first position
        all_addresses = [permanent_address, *response.get("adadr", [])]
        gstin_info.all_addresses = list(map(_get_address, all_addresses))
        gstin_info.permanent_address = gstin_info.all_addresses[0]

    return gstin_info


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

    STRIP_CHARS = "\n\t ,"

    for key in address:
        address[key] = address[key].strip(STRIP_CHARS)

    address_line1 = ", ".join(
        value for key in ("bno", "flno", "bnm") if (value := address.get(key))
    )

    address_line2 = ", ".join(
        value for key in ("loc", "city") if (value := address.get(key))
    )

    if not (street := address.get("st")):
        return address_line1, address_line2

    if len(address_line1) > len(address_line2):
        address_line2 = f"{street}, {address_line2}"
    else:
        address_line1 = f"{address_line1}, {street}"

    return address_line1, address_line2


@frappe.whitelist()
def get_gst_category_from_gstin(gstin):
    gst_category = "Unregistered"

    if UNBODY.match(gstin):
        gst_category = "UIN Holders"
    elif TDS.match(gstin):
        gst_category = "Tax Deductor"
    elif OVERSEAS.match(gstin):
        gst_category = "Overseas"
    elif REGISTERED.match(gstin):
        gst_category = "Registered Regular"

    return frappe._dict(gst_category=gst_category)


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
