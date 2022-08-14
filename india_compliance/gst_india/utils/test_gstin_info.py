import unittest
from unittest.mock import Mock, patch

import frappe

from india_compliance.gst_india.utils.gstin_info import get_gstin_info


class TestGstinInfo(unittest.TestCase):
    MOCK_GSTIN_INFO = frappe._dict(
        {
            "adadr": [
                {
                    "addr": {
                        "bnm": "",
                        "bno": "8-A",
                        "city": "",
                        "dst": "Vadodara",
                        "flno": "Saimee society No.2",
                        "lg": "",
                        "loc": "Subhanpura",
                        "lt": "",
                        "pncd": "390023",
                        "st": "Near Panchratna Apartment",
                        "stcd": "Gujarat",
                    },
                    "ntr": "Office / Sale Office",
                }
            ],
            "ctb": "Proprietorship",
            "ctj": "RANGE-V",
            "ctjCd": "TA0105",
            "cxdt": "",
            "dty": "Regular",
            "gstin": "24AAUPV7468F1ZW",
            "lgnm": "NALIN VORA",
            "lstupdt": "14/04/2018",
            "nba": [
                "Recipient of Goods or Services",
                "Wholesale Business",
                "Factory / Manufacturing",
                "Works Contract",
                "Office / Sale Office",
            ],
            "pradr": {
                "addr": {
                    "bnm": "National Highway No. 8",
                    "bno": "Plot No. 420",
                    "city": "",
                    "dst": "Vadodara",
                    "flno": "",
                    "lg": "",
                    "loc": "Por-Ramangamdi",
                    "lt": "",
                    "pncd": "391243",
                    "st": "GIDC",
                    "stcd": "Gujarat",
                },
                "ntr": (
                    "Recipient of Goods or Services, Wholesale Business, Factory /"
                    " Manufacturing, Works Contract"
                ),
            },
            "rgdt": "01/07/2017",
            "stj": "Ghatak 42 (Vadodara)",
            "stjCd": "GJ042",
            "sts": "Active",
            "tradeNam": "SHALIBHADRA METAL CORPORATION",
        }
    )

    @classmethod
    def setUpClass(cls):
        cls.gstin = "24AAUPV7468F1ZW"
        cls.mock_public_api_patcher = patch(
            "india_compliance.gst_india.utils.gstin_info.PublicAPI"
        )
        cls.mock_public_api = cls.mock_public_api_patcher.start()

    @classmethod
    def tearDownClass(cls):
        cls.mock_public_api_patcher.stop()

    def test_get_gstin_info(self):
        self.mock_public_api.return_value = Mock()
        self.mock_public_api.return_value.get_gstin_info.return_value = (
            self.MOCK_GSTIN_INFO
        )
        gstin_info = get_gstin_info(self.gstin)
        self.assertDictEqual(
            gstin_info,
            {
                "gstin": "24AAUPV7468F1ZW",
                "business_name": "Shalibhadra Metal Corporation",
                "gst_category": "Registered Regular",
                "status": "Active",
                "all_addresses": [
                    {
                        "address_line1": "Plot No. 420, National Highway No. 8",
                        "address_line2": "GIDC, Por-Ramangamdi",
                        "city": "Vadodara",
                        "state": "Gujarat",
                        "pincode": "391243",
                        "country": "India",
                    },
                    {
                        "address_line1": "8-A, Saimee Society No.2",
                        "address_line2": "Near Panchratna Apartment, Subhanpura",
                        "city": "Vadodara",
                        "state": "Gujarat",
                        "pincode": "390023",
                        "country": "India",
                    },
                ],
                "permanent_address": {
                    "address_line1": "Plot No. 420, National Highway No. 8",
                    "address_line2": "GIDC, Por-Ramangamdi",
                    "city": "Vadodara",
                    "state": "Gujarat",
                    "pincode": "391243",
                    "country": "India",
                },
            },
        )
