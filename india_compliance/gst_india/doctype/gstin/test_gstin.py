# Copyright (c) 2023, Resilient Tech and Contributors
# See license.txt
import responses
from responses import matchers

from frappe.tests.utils import FrappeTestCase, change_settings

from india_compliance.gst_india.doctype.gstin.gstin import validate_gst_transporter_id

TEST_GSTIN = "24AANFA2641L1ZK"

TRANSPORTER_ID_API_RESPONSE = {
    "success": True,
    "message": "Transporter details are fetched successfully",
    "result": {
        "transin": TEST_GSTIN,
        "tradeName": "_Test Transporter ID Comapany",
        "legalName": "_Test Transporter ID Comapany",
        "address1": "address 1",
        "address2": "address 2",
        "stateCode": "24",
        "pinCode": "390020",
    },
}


class TestGSTIN(FrappeTestCase):
    @responses.activate
    @change_settings("GST Settings", {"validate_gstin_status": 1, "sandbox_mode": 0})
    def test_validate_gst_transporter_id(self):
        self.mock_get_transporter_details_response()

        validate_gst_transporter_id(TEST_GSTIN)

    def mock_get_transporter_details_response(self):
        url = "https://asp.resilient.tech/ewb/Master/GetTransporterDetails"

        responses.add(
            responses.GET,
            url,
            json=TRANSPORTER_ID_API_RESPONSE,
            match=[matchers.query_param_matcher({"trn_no": TEST_GSTIN})],
            status=200,
        )
