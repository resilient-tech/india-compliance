from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from india_compliance.gst_india.api_classes.taxpayer_returns import (
    GSTR1API,
    IMSAPI,
    GSTR2aAPI,
    GSTR2bAPI,
    GSTR3bAPI,
    ReturnsAPI,
)


class TestReturnsAPI(IntegrationTestCase):
    def test_download_files_calls_get_files_with_filedet(self):
        api = ReturnsAPI.__new__(ReturnsAPI)
        api.company_gstin = "27AAAAA0000A1Z5"

        with patch.object(api, "get_files", return_value=frappe._dict({})) as mock_get_files:
            api.download_files(return_period="072026", token="test-token")

        mock_get_files.assert_called_once_with(
            "072026", "test-token", action="FILEDET", endpoint="returns"
        )

    def test_get_return_status_builds_correct_params(self):
        api = ReturnsAPI.__new__(ReturnsAPI)
        api.company_gstin = "27AAAAA0000A1Z5"

        with patch.object(api, "get", return_value=frappe._dict({})) as mock_get:
            api.get_return_status(return_period="072026", reference_id="ref-123")

        mock_get.assert_called_once()
        call_kwargs = mock_get.call_args[1]
        self.assertEqual(call_kwargs["action"], "RETSTATUS")
        self.assertEqual(call_kwargs["return_period"], "072026")
        self.assertEqual(call_kwargs["params"]["ret_period"], "072026")
        self.assertEqual(call_kwargs["params"]["ref_id"], "ref-123")
        self.assertEqual(call_kwargs["endpoint"], "returns")

    def test_proceed_to_file_nil_return_includes_isnil(self):
        api = ReturnsAPI.__new__(ReturnsAPI)
        api.company_gstin = "27AAAAA0000A1Z5"

        with patch.object(api, "post", return_value=frappe._dict({})) as mock_post:
            api.proceed_to_file(return_type="GSTR1", return_period="072026", is_nil_return=True)

        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args[1]
        self.assertEqual(call_kwargs["json"]["action"], "RETNEWPTF")
        self.assertEqual(call_kwargs["json"]["data"]["isnil"], "Y")

    def test_proceed_to_file_normal_return_no_isnil(self):
        api = ReturnsAPI.__new__(ReturnsAPI)
        api.company_gstin = "27AAAAA0000A1Z5"

        with patch.object(api, "post", return_value=frappe._dict({})) as mock_post:
            api.proceed_to_file(return_type="GSTR1", return_period="072026", is_nil_return=False)

        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args[1]
        self.assertNotIn("isnil", call_kwargs["json"]["data"])

    def test_proceed_to_file_data_includes_gstin_and_ret_period(self):
        api = ReturnsAPI.__new__(ReturnsAPI)
        api.company_gstin = "27AAAAA0000A1Z5"

        with patch.object(api, "post", return_value=frappe._dict({})) as mock_post:
            api.proceed_to_file(return_type="GSTR1", return_period="072026", is_nil_return=False)

        mock_post.assert_called_once()
        data = mock_post.call_args[1]["json"]["data"]
        self.assertEqual(data["gstin"], "27AAAAA0000A1Z5")
        self.assertEqual(data["ret_period"], "072026")


class TestGSTR2bAPI(IntegrationTestCase):
    def test_get_data_without_file_num(self):
        api = GSTR2bAPI.__new__(GSTR2bAPI)
        api.company_gstin = "27AAAAA0000A1Z5"

        with patch.object(api, "get", return_value=frappe._dict({})) as mock_get:
            api.get_data(return_period="072026")

        mock_get.assert_called_once()
        call_kwargs = mock_get.call_args[1]
        self.assertEqual(call_kwargs["action"], "GET2B")
        self.assertEqual(call_kwargs["params"], {"rtnprd": "072026"})
        self.assertEqual(call_kwargs["endpoint"], "returns/gstr2b")

    def test_get_data_with_file_num(self):
        api = GSTR2bAPI.__new__(GSTR2bAPI)
        api.company_gstin = "27AAAAA0000A1Z5"

        with patch.object(api, "get", return_value=frappe._dict({})) as mock_get:
            api.get_data(return_period="072026", file_num="12345")

        mock_get.assert_called_once()
        call_kwargs = mock_get.call_args[1]
        self.assertEqual(call_kwargs["params"]["rtnprd"], "072026")
        self.assertEqual(call_kwargs["params"]["file_num"], "12345")

    def test_regenerate_action(self):
        api = GSTR2bAPI.__new__(GSTR2bAPI)
        api.company_gstin = "27AAAAA0000A1Z5"

        with patch.object(api, "put", return_value=frappe._dict({})) as mock_put:
            api.regenerate(return_period="072026")

        mock_put.assert_called_once()
        call_kwargs = mock_put.call_args[1]
        self.assertEqual(call_kwargs["json"]["action"], "GEN2B")
        self.assertEqual(call_kwargs["json"]["data"]["rtin"], "27AAAAA0000A1Z5")
        self.assertEqual(call_kwargs["json"]["data"]["itcprd"], "072026")


class TestGSTR2aAPI(IntegrationTestCase):
    def test_get_data(self):
        api = GSTR2aAPI.__new__(GSTR2aAPI)
        api.company_gstin = "27AAAAA0000A1Z5"

        with patch.object(api, "get", return_value=frappe._dict({})) as mock_get:
            api.get_data(action="GSTR2A_ACTION", return_period="072026")

        mock_get.assert_called_once()
        call_kwargs = mock_get.call_args[1]
        self.assertEqual(call_kwargs["action"], "GSTR2A_ACTION")
        self.assertEqual(call_kwargs["return_period"], "072026")
        self.assertEqual(call_kwargs["params"]["ret_period"], "072026")
        self.assertEqual(call_kwargs["endpoint"], "returns/gstr2a")


class TestGSTR1API(IntegrationTestCase):
    def test_setup_throws_without_company_gstin(self):
        api = GSTR1API.__new__(GSTR1API)
        api.settings = frappe._dict({"credentials": []})

        with self.assertRaises(frappe.ValidationError):
            api.setup()

    def test_setup_raises_when_credentials_not_found_even_with_doc_gstin(self):
        api = GSTR1API.__new__(GSTR1API)
        api.settings = frappe._dict({"credentials": []})
        doc = frappe._dict({"gstin": "27AAAAA0000A1Z5", "doctype": "GSTR-1", "name": "GSTR1-001"})

        with self.assertRaises(frappe.ValidationError):
            api.setup(doc=doc)

    def test_file_gstr_1_sends_evc_data(self):
        api = GSTR1API.__new__(GSTR1API)
        api.company_gstin = "27AAAAA0000A1Z5"
        summary_data = frappe._dict({"total": 1000})

        with patch.object(api, "post", return_value=frappe._dict({})) as mock_post:
            api.file_gstr_1(return_period="072026", summary_data=summary_data, pan="ABCDE1234F", evc_otp="123456")

        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args[1]
        self.assertEqual(call_kwargs["json"]["action"], "RETFILE")
        self.assertEqual(call_kwargs["json"]["data"], summary_data)
        self.assertEqual(call_kwargs["json"]["st"], "EVC")
        self.assertEqual(call_kwargs["json"]["sid"], "ABCDE1234F|123456")
        self.assertEqual(call_kwargs["endpoint"], "returns/gstr1")


class TestGSTR3bAPI(IntegrationTestCase):
    def test_setup_raises_when_credentials_not_found_for_return_period(self):
        api = GSTR3bAPI.__new__(GSTR3bAPI)
        api.settings = frappe._dict({"credentials": []})

        with self.assertRaises(frappe.ValidationError):
            api.setup(company_gstin="27AAAAA0000A1Z5", return_period="072026")

    def test_file_gstr_3b_sends_evc_data(self):
        api = GSTR3bAPI.__new__(GSTR3bAPI)
        api.company_gstin = "27AAAAA0000A1Z5"
        api.return_period = "072026"
        data = frappe._dict({"sup_details": {}})

        with patch.object(api, "post", return_value=frappe._dict({})) as mock_post:
            api.file_gstr_3b(data=data, pan="ABCDE1234F", evc_otp="123456")

        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args[1]
        self.assertEqual(call_kwargs["json"]["action"], "RETFILE")
        self.assertEqual(call_kwargs["json"]["data"], data)
        self.assertEqual(call_kwargs["json"]["st"], "EVC")
        self.assertEqual(call_kwargs["json"]["sid"], "ABCDE1234F|123456")
        self.assertEqual(call_kwargs["endpoint"], "returns/gstr3b")


class TestIMSAPI(IntegrationTestCase):
    def test_get_request_status_action(self):
        api = IMSAPI.__new__(IMSAPI)
        api.company_gstin = "27AAAAA0000A1Z5"

        with patch.object(api, "get", return_value=frappe._dict({})) as mock_get:
            api.get_request_status(transaction_id="txn-123")

        mock_get.assert_called_once()
        call_kwargs = mock_get.call_args[1]
        self.assertEqual(call_kwargs["action"], "REQSTS")
        self.assertEqual(call_kwargs["endpoint"], "returns/ims")
        self.assertEqual(call_kwargs["params"]["int_tran_id"], "txn-123")
        self.assertEqual(call_kwargs["params"]["gstin"], "27AAAAA0000A1Z5")
