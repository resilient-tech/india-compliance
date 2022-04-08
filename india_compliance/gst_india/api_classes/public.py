from math import ceil

import frappe

from india_compliance.gst_india.api_classes.base import BaseAPI
from india_compliance.gst_india.utils import titlecase


class PublicAPI(BaseAPI):
    # map of api category -> india_compliance category
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

    # ####### SAMPLE DATA for GST_CATEGORIES ########
    # "Composition" - 36AASFP8573D2ZN
    # "Input Service Distributor (ISD)" - 29AABCF8078M2ZW - Flipkart
    # "Tax Deductor" - 06DELI09652G1DA, 09ALDN00287A1DD, 27AAFT56212B1DO, 19AAACI1681G1DV
    # "SEZ Developer" - 27AAJCS5738D1Z6 -
    # "United Nation Body" - 0717UNO00157UNO, 0717UNO00211UN2, 2117UNO00002UNF
    # "Consulate or Embassy of Foreign Country" - 0717UNO00154UNU

    # "Tax Collector (Electronic Commerce Operator)" - 29AABCF8078M1C8, 27AAECG3736E1C2 - Cannot be a part of GSTR1
    # "Non Resident Online Services Provider" - 9917SGP29001OST - Google - Cannot be a part of GSTR1

    # "Non Resident Taxable Person" -
    # "Government Department ID" -

    def setup(self):
        self.api_name = "GST Public"
        self.base_path = "commonapi"

    def get_gstin_info(self, gstin):
        if not self.settings.enable_api:
            return

        gstin_info = self.get("search", params={"action": "TP", "gstin": gstin})

        business_name = gstin_info.lgnm
        if gstin_info.ctb == "Proprietorship":
            business_name = gstin_info.tradeNam

        gstin_details = frappe._dict(
            gstin=gstin,
            business_name=titlecase(business_name),
            gstin_info=gstin_info,
        )

        gstin_details.gst_category = self.GST_CATEGORIES[gstin_info.dty]
        if gstin in ("URP", "NA"):
            gstin_details.gst_category = self.GST_CATEGORIES["URP"]

        permanent_address = gstin_info.get("pradr", {})
        if permanent_address:
            # permanent address will be at first position
            addresses = [permanent_address] + gstin_info.get("adadr", [])
            gstin_details.all_addresses = list(map(self._get_address, addresses))
            gstin_details.permanent_address = gstin_details.all_addresses[0]

        return gstin_details

    def _get_address(self, address):
        """:param address: dict of address with a key of 'addr' and 'ntr'"""

        address = address.get("addr", {})
        address_lines = self._extract_address_lines(address)
        return {
            "address_line1": titlecase(address_lines[0]),
            "address_line2": titlecase(address_lines[1]),
            "city": titlecase(address.get("dst")),
            "state": titlecase(address.get("stcd")),
            "pincode": address.get("pncd"),
            "country": "India",
        }

    def _extract_address_lines(self, address):
        """merge and divide address into exactly two lines"""

        keys = ("bno", "bnm", "flno", "st", "loc", "city")
        full_address = [
            address.get(key, "").strip() for key in keys if address.get(key)
        ]
        middle = ceil(len(full_address) / 2)
        return (", ".join(full_address[:middle]), ", ".join(full_address[middle:]))
