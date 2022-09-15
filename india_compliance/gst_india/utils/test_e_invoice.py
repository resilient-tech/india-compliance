import json
import re
import unittest

import requests
import responses
from responses import matchers

import frappe

from india_compliance.gst_india.utils.e_invoice import (
    cancel_e_invoice,
    generate_e_invoice,
)
from india_compliance.gst_india.utils.tests import create_sales_invoice


class TestEInvoice(unittest.TestCase):
    BASE_URL = "https://asp.resilient.tech"

    MOCK_EWAYBILL_IRN_RESPONSE = frappe._dict(
        {
            "success": True,
            "message": "IRN generated successfully",
            "result": {
                "AckNo": 232210036699007,
                "AckDt": "2022-09-13 16:48:00",
                "Irn": "7799544e995fc8fb8b76258d87d89fc7587528d827f50bdd1712c70c342ba905",
                "SignedInvoice": "eyJhbGciOiJSUzI1NiIsImtpZCI6IkVEQzU3REUxMzU4QjMwMEJBOUY3OTM0MEE2Njk2ODMxRjNDODUwNDciLCJ0eXAiOiJKV1QiLCJ4NXQiOiI3Y1Y5NFRXTE1BdXA5NU5BcG1sb01mUElVRWMifQ.eyJkYXRhIjoie1wiQWNrTm9cIjoyMzIyMTAwMzY2OTkwMDcsXCJBY2tEdFwiOlwiMjAyMi0wOS0xMyAxNjo0ODowMFwiLFwiSXJuXCI6XCI3Nzk5NTQ0ZTk5NWZjOGZiOGI3NjI1OGQ4N2Q4OWZjNzU4NzUyOGQ4MjdmNTBiZGQxNzEyYzcwYzM0MmJhOTA1XCIsXCJWZXJzaW9uXCI6XCIxLjFcIixcIlRyYW5EdGxzXCI6e1wiVGF4U2NoXCI6XCJHU1RcIixcIlN1cFR5cFwiOlwiQjJCXCIsXCJSZWdSZXZcIjpcIk5cIn0sXCJEb2NEdGxzXCI6e1wiVHlwXCI6XCJJTlZcIixcIk5vXCI6XCJ4WGRXMTBcIixcIkR0XCI6XCIxMy8wOS8yMDIyXCJ9LFwiU2VsbGVyRHRsc1wiOntcIkdzdGluXCI6XCIwMUFNQlBHNzc3M00wMDJcIixcIkxnbE5tXCI6XCJfVGVzdCBJbmRpYW4gUmVnaXN0ZXJlZCBDb21wYW55XCIsXCJUcmRObVwiOlwiVGVzdCBJbmRpYW4gUmVnaXN0ZXJlZCBDb21wYW55XCIsXCJBZGRyMVwiOlwiVGVzdCBBZGRyZXNzIC0gMVwiLFwiTG9jXCI6XCJUZXN0IENpdHlcIixcIlBpblwiOjE5MzUwMSxcIlN0Y2RcIjpcIjAxXCJ9LFwiQnV5ZXJEdGxzXCI6e1wiR3N0aW5cIjpcIjM2QU1CUEc3NzczTTAwMlwiLFwiTGdsTm1cIjpcIl9UZXN0IFJlZ2lzdGVyZWQgQ3VzdG9tZXJcIixcIlRyZE5tXCI6XCJUZXN0IFJlZ2lzdGVyZWQgQ3VzdG9tZXJcIixcIlBvc1wiOlwiMDFcIixcIkFkZHIxXCI6XCJUZXN0IEFkZHJlc3MgLSA0XCIsXCJMb2NcIjpcIlRlc3QgQ2l0eVwiLFwiUGluXCI6NTAwMDU1LFwiU3RjZFwiOlwiMzZcIn0sXCJEaXNwRHRsc1wiOntcIk5tXCI6XCJUZXN0IEluZGlhbiBSZWdpc3RlcmVkIENvbXBhbnlcIixcIkFkZHIxXCI6XCJUZXN0IEFkZHJlc3MgLSAxXCIsXCJMb2NcIjpcIlRlc3QgQ2l0eVwiLFwiUGluXCI6MTkzNTAxLFwiU3RjZFwiOlwiMDFcIn0sXCJTaGlwRHRsc1wiOntcIkdzdGluXCI6XCIzNkFNQlBHNzc3M00wMDJcIixcIkxnbE5tXCI6XCJUZXN0IFJlZ2lzdGVyZWQgQ3VzdG9tZXJcIixcIlRyZE5tXCI6XCJUZXN0IFJlZ2lzdGVyZWQgQ3VzdG9tZXJcIixcIkFkZHIxXCI6XCJUZXN0IEFkZHJlc3MgLSA0XCIsXCJMb2NcIjpcIlRlc3QgQ2l0eVwiLFwiUGluXCI6NTAwMDU1LFwiU3RjZFwiOlwiMzZcIn0sXCJJdGVtTGlzdFwiOlt7XCJJdGVtTm9cIjowLFwiU2xOb1wiOlwiMVwiLFwiSXNTZXJ2Y1wiOlwiTlwiLFwiUHJkRGVzY1wiOlwiVGVzdCBUcmFkaW5nIEdvb2RzIDFcIixcIkhzbkNkXCI6XCI2MTE0OTA5MFwiLFwiUXR5XCI6MS4wLFwiVW5pdFwiOlwiTk9TXCIsXCJVbml0UHJpY2VcIjoxMDAuMCxcIlRvdEFtdFwiOjEwMC4wLFwiRGlzY291bnRcIjowLFwiQXNzQW10XCI6MTAwLjAsXCJHc3RSdFwiOjAuMCxcIklnc3RBbXRcIjowLFwiQ2dzdEFtdFwiOjAsXCJTZ3N0QW10XCI6MCxcIkNlc1J0XCI6MCxcIkNlc0FtdFwiOjAsXCJDZXNOb25BZHZsQW10XCI6MCxcIlRvdEl0ZW1WYWxcIjoxMDAuMH1dLFwiVmFsRHRsc1wiOntcIkFzc1ZhbFwiOjEwMC4wLFwiQ2dzdFZhbFwiOjAsXCJTZ3N0VmFsXCI6MCxcIklnc3RWYWxcIjowLFwiQ2VzVmFsXCI6MCxcIkRpc2NvdW50XCI6MCxcIk90aENocmdcIjowLjAsXCJSbmRPZmZBbXRcIjowLjAsXCJUb3RJbnZWYWxcIjoxMDAuMH0sXCJQYXlEdGxzXCI6e1wiQ3JEYXlcIjowLFwiUGFpZEFtdFwiOjAsXCJQYXltdER1ZVwiOjEwMC4wfSxcIkV3YkR0bHNcIjp7XCJUcmFuc01vZGVcIjpcIjFcIixcIkRpc3RhbmNlXCI6MCxcIlZlaE5vXCI6XCJHSjA3REw5MDA5XCIsXCJWZWhUeXBlXCI6XCJSXCJ9fSIsImlzcyI6Ik5JQyJ9.WqkBlPGK0aeR6ssmalJp_C01fC69D_C1CbB2zOBmBPP0TrlSLfvx0Ju_aHBA-gjIIuLOxTw7zL4V83YPDyd1yTJ7pjqDR1_9JQOo0nXB3zbQCc61nDqWDqwDxQSK3RVoQwGPmehgeCliT1Kr61UQX7CTLgL85M6cLFEAIjk7KK7GA7AjrxNeggkQ2TV8XP6zGdGub3oyCaG_a-9smVuyCgdKZ2xOKbOhnvFuHNVng8CIouHgH1s9Wg4Z_V_HZBfEHSsXnP3U4X9B8ZUGVQywwYrRlU8AwXG8ShU1gtWiWbpxnijX8-P7tryjkikkErnl5VqcmdXDShR7_yVCdc_7uQ",
                "SignedQRCode": "eyJhbGciOiJSUzI1NiIsImtpZCI6IkVEQzU3REUxMzU4QjMwMEJBOUY3OTM0MEE2Njk2ODMxRjNDODUwNDciLCJ0eXAiOiJKV1QiLCJ4NXQiOiI3Y1Y5NFRXTE1BdXA5NU5BcG1sb01mUElVRWMifQ.eyJkYXRhIjoie1wiU2VsbGVyR3N0aW5cIjpcIjAxQU1CUEc3NzczTTAwMlwiLFwiQnV5ZXJHc3RpblwiOlwiMzZBTUJQRzc3NzNNMDAyXCIsXCJEb2NOb1wiOlwieFhkVzEwXCIsXCJEb2NUeXBcIjpcIklOVlwiLFwiRG9jRHRcIjpcIjEzLzA5LzIwMjJcIixcIlRvdEludlZhbFwiOjEwMC4wLFwiSXRlbUNudFwiOjEsXCJNYWluSHNuQ29kZVwiOlwiNjExNDkwOTBcIixcIklyblwiOlwiNzc5OTU0NGU5OTVmYzhmYjhiNzYyNThkODdkODlmYzc1ODc1MjhkODI3ZjUwYmRkMTcxMmM3MGMzNDJiYTkwNVwiLFwiSXJuRHRcIjpcIjIwMjItMDktMTMgMTY6NDg6MDBcIn0iLCJpc3MiOiJOSUMifQ.bFOGmLbkRIaHsQU4scmhLL013YbmQDGKvxqfbjx-nuLByrEgA702f-n_xaVEd637z8_x3YF2Ml1M8WTAGqZMT7f854EC79uKIaoXInnu7bYgBUxQ9_z5DDbWFVpmpuskLjeoS6xuiJ8b8nd9gvx0HFcLEHpYvI-hZJq5pephb3RwglmArVL-81yMhRyJuYiKEmsdWY788M2wlFjxBP01FuKODXWYVH5pkluhbhRSFszjfszbMPuWh2KxTGDHTpU55rc3NUEJhmn3CD3BhBO1B-x7DFvMOhZM5zRlRorY5iWOLYWfjaXXSEbjA5dc-6LgKegr_hP6QYBuXkG_Ys96lg",
                "Status": "ACT",
                "EwbNo": 371009149123,
                "EwbDt": "2022-09-13 16:48:00",
                "EwbValidTill": "2022-09-26 23:59:00",
                "Remarks": None,
            },
            "info": [{"InfCd": "EWBPPD", "Desc": "Pin-Pin calc distance: 2467KM"}],
        }
    )

    MOCK_IRN_RESPONSE = frappe._dict(
        {
            "success": True,
            "message": "IRN generated successfully",
            "result": {
                "AckNo": 232210036688676,
                "AckDt": "2022-09-12 18:14:00",
                "Irn": "7de7c050ac0d99f8c99918daf701869d8dc004d4174f262ea3cf6cd31050fd4c",
                "SignedInvoice": "eyJhbGciOiJSUzI1NiIsImtpZCI6IkVEQzU3REUxMzU4QjMwMEJBOUY3OTM0MEE2Njk2ODMxRjNDODUwNDciLCJ0eXAiOiJKV1QiLCJ4NXQiOiI3Y1Y5NFRXTE1BdXA5NU5BcG1sb01mUElVRWMifQ.eyJkYXRhIjoie1wiQWNrTm9cIjoyMzIyMTAwMzY2ODg2NzYsXCJBY2tEdFwiOlwiMjAyMi0wOS0xMiAxODoxNDowMFwiLFwiSXJuXCI6XCI3ZGU3YzA1MGFjMGQ5OWY4Yzk5OTE4ZGFmNzAxODY5ZDhkYzAwNGQ0MTc0ZjI2MmVhM2NmNmNkMzEwNTBmZDRjXCIsXCJWZXJzaW9uXCI6XCIxLjFcIixcIlRyYW5EdGxzXCI6e1wiVGF4U2NoXCI6XCJHU1RcIixcIlN1cFR5cFwiOlwiQjJCXCIsXCJSZWdSZXZcIjpcIk5cIn0sXCJEb2NEdGxzXCI6e1wiVHlwXCI6XCJJTlZcIixcIk5vXCI6XCJCUUhDekJcIixcIkR0XCI6XCIxMi8wOS8yMDIyXCJ9LFwiU2VsbGVyRHRsc1wiOntcIkdzdGluXCI6XCIwMUFNQlBHNzc3M00wMDJcIixcIkxnbE5tXCI6XCJfVGVzdCBJbmRpYW4gUmVnaXN0ZXJlZCBDb21wYW55XCIsXCJUcmRObVwiOlwiVGVzdCBJbmRpYW4gUmVnaXN0ZXJlZCBDb21wYW55XCIsXCJBZGRyMVwiOlwiVGVzdCBBZGRyZXNzIC0gMVwiLFwiTG9jXCI6XCJUZXN0IENpdHlcIixcIlBpblwiOjE5MzUwMSxcIlN0Y2RcIjpcIjAxXCJ9LFwiQnV5ZXJEdGxzXCI6e1wiR3N0aW5cIjpcIjM2QU1CUEc3NzczTTAwMlwiLFwiTGdsTm1cIjpcIl9UZXN0IFJlZ2lzdGVyZWQgQ3VzdG9tZXJcIixcIlRyZE5tXCI6XCJUZXN0IFJlZ2lzdGVyZWQgQ3VzdG9tZXJcIixcIlBvc1wiOlwiMDFcIixcIkFkZHIxXCI6XCJUZXN0IEFkZHJlc3MgLSA0XCIsXCJMb2NcIjpcIlRlc3QgQ2l0eVwiLFwiUGluXCI6NTAwMDU1LFwiU3RjZFwiOlwiMzZcIn0sXCJEaXNwRHRsc1wiOntcIk5tXCI6XCJUZXN0IEluZGlhbiBSZWdpc3RlcmVkIENvbXBhbnlcIixcIkFkZHIxXCI6XCJUZXN0IEFkZHJlc3MgLSAxXCIsXCJMb2NcIjpcIlRlc3QgQ2l0eVwiLFwiUGluXCI6MTkzNTAxLFwiU3RjZFwiOlwiMDFcIn0sXCJTaGlwRHRsc1wiOntcIkdzdGluXCI6XCIzNkFNQlBHNzc3M00wMDJcIixcIkxnbE5tXCI6XCJUZXN0IFJlZ2lzdGVyZWQgQ3VzdG9tZXJcIixcIlRyZE5tXCI6XCJUZXN0IFJlZ2lzdGVyZWQgQ3VzdG9tZXJcIixcIkFkZHIxXCI6XCJUZXN0IEFkZHJlc3MgLSA0XCIsXCJMb2NcIjpcIlRlc3QgQ2l0eVwiLFwiUGluXCI6NTAwMDU1LFwiU3RjZFwiOlwiMzZcIn0sXCJJdGVtTGlzdFwiOlt7XCJJdGVtTm9cIjowLFwiU2xOb1wiOlwiMVwiLFwiSXNTZXJ2Y1wiOlwiTlwiLFwiUHJkRGVzY1wiOlwiVGVzdCBUcmFkaW5nIEdvb2RzIDFcIixcIkhzbkNkXCI6XCI2MTE0OTA5MFwiLFwiUXR5XCI6MS4wLFwiVW5pdFwiOlwiTk9TXCIsXCJVbml0UHJpY2VcIjoxMDAuMCxcIlRvdEFtdFwiOjEwMC4wLFwiRGlzY291bnRcIjowLFwiQXNzQW10XCI6MTAwLjAsXCJHc3RSdFwiOjAuMCxcIklnc3RBbXRcIjowLFwiQ2dzdEFtdFwiOjAsXCJTZ3N0QW10XCI6MCxcIkNlc1J0XCI6MCxcIkNlc0FtdFwiOjAsXCJDZXNOb25BZHZsQW10XCI6MCxcIlRvdEl0ZW1WYWxcIjoxMDAuMH1dLFwiVmFsRHRsc1wiOntcIkFzc1ZhbFwiOjEwMC4wLFwiQ2dzdFZhbFwiOjAsXCJTZ3N0VmFsXCI6MCxcIklnc3RWYWxcIjowLFwiQ2VzVmFsXCI6MCxcIkRpc2NvdW50XCI6MCxcIk90aENocmdcIjowLjAsXCJSbmRPZmZBbXRcIjowLjAsXCJUb3RJbnZWYWxcIjoxMDAuMH0sXCJQYXlEdGxzXCI6e1wiQ3JEYXlcIjowLFwiUGFpZEFtdFwiOjAsXCJQYXltdER1ZVwiOjEwMC4wfSxcIkV3YkR0bHNcIjp7XCJEaXN0YW5jZVwiOjB9fSIsImlzcyI6Ik5JQyJ9.ktXZMYHaKomcRUIU0kStaVFgbv-qI9ATuXcxCbl0gt4Zato8zD4GXEKY_CFwjtvC8HZgWY4QtLT-sfVRL2D8fOUa74FHcnJ9Xsjjx8SPfr0zjSixncRaMzlqoZdbhSaA4Pu7ldg7m_3XgW9QGNqEtClPsUQaKvzXRRYLeFmghbPqUNFJFwUFe6AXgs0YJYUpErKdb_TGh5eoMc4EhxHV4IAgPSdyoRjmTN4xjaUWwYeAKDd1lDn0SEi9S_AuZF96cm8SH7l9409ZmM-YjFIZi8M97mYqajmwZzQeihf1r124QgYjuj-aq8rktQc983UxHNEJQse8LlIIvG3CGfvmvg",
                "SignedQRCode": "eyJhbGciOiJSUzI1NiIsImtpZCI6IkVEQzU3REUxMzU4QjMwMEJBOUY3OTM0MEE2Njk2ODMxRjNDODUwNDciLCJ0eXAiOiJKV1QiLCJ4NXQiOiI3Y1Y5NFRXTE1BdXA5NU5BcG1sb01mUElVRWMifQ.eyJkYXRhIjoie1wiU2VsbGVyR3N0aW5cIjpcIjAxQU1CUEc3NzczTTAwMlwiLFwiQnV5ZXJHc3RpblwiOlwiMzZBTUJQRzc3NzNNMDAyXCIsXCJEb2NOb1wiOlwiQlFIQ3pCXCIsXCJEb2NUeXBcIjpcIklOVlwiLFwiRG9jRHRcIjpcIjEyLzA5LzIwMjJcIixcIlRvdEludlZhbFwiOjEwMC4wLFwiSXRlbUNudFwiOjEsXCJNYWluSHNuQ29kZVwiOlwiNjExNDkwOTBcIixcIklyblwiOlwiN2RlN2MwNTBhYzBkOTlmOGM5OTkxOGRhZjcwMTg2OWQ4ZGMwMDRkNDE3NGYyNjJlYTNjZjZjZDMxMDUwZmQ0Y1wiLFwiSXJuRHRcIjpcIjIwMjItMDktMTIgMTg6MTQ6MDBcIn0iLCJpc3MiOiJOSUMifQ.kreHG_qb5oV2bQH2hTNc_rYC0De6mBt6i3-20j2z7UJdBEqHb7-D3MZAoMwkSwDx15aXSF10ZSmP3tLWD0gjRpqkPC7uJv3VyJNoSZ-s21o0TPma7t9HXXexW4TH9X36o66gZnoHY00PeDvMIBKtuGU863aI8puVA1Ctfe-AWxtWBBjCcWhuyrsg528QCYGVGpZ27qZ5qmUg3v83H4pFvKPVy4S7cQ-oktU1QBw6Mi33ig4x3RVaBpaVcW1UGJZaqshTd87n3UEedc_Ail02k9MhiUP_-IxMmQLb8POGk6JdMNXeA6T7-02HPJiVS_CIZRmnrugR5Olsh7hzw4KG1g",
                "Status": "ACT",
                "EwbNo": None,
                "EwbDt": None,
                "EwbValidTill": None,
                "Remarks": None,
            },
            "info": [
                {
                    "InfCd": "EWBERR",
                    "Desc": [
                        {
                            "ErrorCode": "4019",
                            "ErrorMessage": "Provide Transporter ID in order to generate Part A of e-Way Bill",
                        }
                    ],
                }
            ],
        }
    )

    MOCK_CANCEL_RESPONSE = frappe._dict(
        {
            "message": "E-Invoice is cancelled successfully",
            "result": {
                "CancelDate": "2022-09-13 17:23:00",
                "Irn": "7799544e995fc8fb8b76258d87d89fc7587528d827f50bdd1712c70c342ba905",
            },
            "success": True,
        }
    )

    @classmethod
    def setUpClass(cls):
        frappe.db.savepoint("before_test_e_invoice")

    @classmethod
    def setUp(self):
        frappe.db.set_value(
            "GST Settings",
            "GST Settings",
            {
                "enable_e_invoice": 1,
                "auto_generate_e_invoice": 0,
                "enable_e_waybill": 1,
            },
        )

    @classmethod
    def tearDownClass(cls):
        frappe.db.rollback(save_point="before_test_e_invoice")

    @classmethod
    def tearDown(self):
        frappe.db.set_value(
            "GST Settings",
            "GST Settings",
            {
                "enable_e_invoice": 0,
                "auto_generate_e_invoice": 1,
            },
        )

    @responses.activate
    def test_generate_e_invoice_with_goods_item(self):
        """Generate test e-Invoice for goods item"""
        # ToDo: can't retrieve data error on getewaybill API
        params = {"ewbNo": self.MOCK_EWAYBILL_IRN_RESPONSE.result.get("EwbNo")}

        si = create_sales_invoice(vehicle_no="GJ07DL9009")

        responses.add(
            responses.POST,
            self.BASE_URL + "/test/ei/api/invoice",
            body=json.dumps(self.MOCK_EWAYBILL_IRN_RESPONSE),
            status=200,
        )

        responses.add(
            responses.GET,
            url=self.BASE_URL + "/test/ewb/ewayapi/getewaybill",
            match=[matchers.query_param_matcher(params)],
        )

        generate_e_invoice(si.name)

        self.assertTrue(
            frappe.db.get_value("e-Invoice Log", {"sales_invoice": si.name}, "name"),
        )
        self.assertTrue(
            frappe.db.get_value("e-Waybill Log", {"reference_name": si.name}, "name"),
        )

    @responses.activate
    def test_generate_e_invoice_with_service_item(self):
        """Generate test e-Invoice for Service Item"""
        si = create_sales_invoice(item_code="_Test Service Item")

        responses.add(
            responses.POST,
            self.BASE_URL + "/test/ei/api/invoice",
            body=json.dumps(self.MOCK_IRN_RESPONSE),
            status=200,
        )
        generate_e_invoice(si.name)

        self.assertEqual(
            self.MOCK_IRN_RESPONSE.result.get("Irn"),
            frappe.db.get_value("e-Invoice Log", {"sales_invoice": si.name}, "name"),
        )
        self.assertFalse(si.ewaybill)

    @responses.activate
    def test_return_e_invoice_with_goods_item(self):
        si = create_sales_invoice()
        return_si = create_sales_invoice(qty=-1, is_return=1, return_against=si.name)

        responses.add(
            responses.POST,
            self.BASE_URL + "/test/ei/api/invoice",
            body=json.dumps(self.MOCK_IRN_RESPONSE),
            status=200,
        )
        requests.post(self.BASE_URL + "/test/ei/api/invoice")
        generate_e_invoice(return_si.name)

        self.assertEqual(
            self.MOCK_IRN_RESPONSE.result.get("Irn"),
            frappe.db.get_value(
                "e-Invoice Log", {"sales_invoice": return_si.name}, "name"
            ),
        )
        self.assertFalse(return_si.ewaybill)

    @responses.activate
    def test_debit_note_e_invoice_with_goods_item(self):
        si = create_sales_invoice(is_debit_note=1, qty=0)

        responses.add(
            responses.POST,
            self.BASE_URL + "/test/ei/api/invoice",
            body=json.dumps(self.MOCK_IRN_RESPONSE),
            status=200,
        )
        requests.post(self.BASE_URL + "/test/ei/api/invoice")
        generate_e_invoice(si.name)

        self.assertEqual(
            self.MOCK_IRN_RESPONSE.result.get("Irn"),
            frappe.db.get_value(
                "e-Invoice Log",
                {"sales_invoice": si.name},
                "name",
            ),
        )
        self.assertFalse(si.ewaybill)

    @responses.activate
    def test_cancel_e_invoice(self):
        si = create_sales_invoice()
        values = frappe._dict({"reason": "Others", "remark": "Test"})
        responses.add(
            responses.POST,
            self.BASE_URL + "/test/ei/api/invoice/cancel",
            body=json.dumps(self.MOCK_CANCEL_RESPONSE),
            status=200,
        )

        cancel_e_invoice(si.name, values)

        self.assertFalse(si.irn)
        self.assertFalse(si.ewaybill)

    def test_if_e_invoice_enabled(self):
        if not frappe.db.get_single_value("GST Settings", "enable_e_invoice"):
            self.assertRaisesRegexp(
                frappe.exceptions.ValidationError,
                re.compile(r"^(enable e-Invoicing in GST Settings first*)$"),
            )

    # ToDo: Add other failed cases
