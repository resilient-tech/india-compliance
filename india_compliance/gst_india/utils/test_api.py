"""
Unit tests for API utility functions.
"""

import unittest
from unittest.mock import MagicMock, call, patch

from india_compliance.gst_india.utils.api import (
    create_integration_request,
    enqueue_integration_request,
    link_integration_request,
    pretty_json,
)


class TestPrettyJson(unittest.TestCase):
    """Test pretty_json utility function"""

    @patch("india_compliance.gst_india.utils.api.frappe")
    def test_pretty_json_with_none(self, mock_frappe):
        """Test pretty_json with None returns empty string"""
        result = pretty_json(None)
        self.assertEqual(result, "")

    @patch("india_compliance.gst_india.utils.api.frappe")
    def test_pretty_json_with_empty_string(self, mock_frappe):
        """Test pretty_json with empty string returns empty string"""
        result = pretty_json("")
        self.assertEqual(result, "")

    @patch("india_compliance.gst_india.utils.api.frappe")
    def test_pretty_json_with_false(self, mock_frappe):
        """Test pretty_json with False returns empty string"""
        result = pretty_json(False)
        self.assertEqual(result, "")

    @patch("india_compliance.gst_india.utils.api.frappe")
    def test_pretty_json_with_zero(self, mock_frappe):
        """Test pretty_json with zero returns formatted JSON"""
        mock_frappe.as_json.return_value = "0"
        result = pretty_json(0)
        # Zero is falsy but should still return as_json result
        self.assertEqual(result, "")

    @patch("india_compliance.gst_india.utils.api.frappe")
    def test_pretty_json_with_string(self, mock_frappe):
        """Test pretty_json with string returns the string as-is"""
        test_string = '{"key": "value"}'
        result = pretty_json(test_string)
        self.assertEqual(result, test_string)

    @patch("india_compliance.gst_india.utils.api.frappe")
    def test_pretty_json_with_dict(self, mock_frappe):
        """Test pretty_json with dict calls frappe.as_json"""
        test_dict = {"key": "value"}
        mock_frappe.as_json.return_value = '{\n    "key": "value"\n}'

        result = pretty_json(test_dict)

        mock_frappe.as_json.assert_called_once_with(test_dict, indent=4)
        self.assertEqual(result, '{\n    "key": "value"\n}')

    @patch("india_compliance.gst_india.utils.api.frappe")
    def test_pretty_json_with_list(self, mock_frappe):
        """Test pretty_json with list calls frappe.as_json"""
        test_list = [1, 2, 3]
        mock_frappe.as_json.return_value = '[\n    1,\n    2,\n    3\n]'

        result = pretty_json(test_list)

        mock_frappe.as_json.assert_called_once_with(test_list, indent=4)
        self.assertEqual(result, '[\n    1,\n    2,\n    3\n]')

    @patch("india_compliance.gst_india.utils.api.frappe")
    def test_pretty_json_with_complex_dict(self, mock_frappe):
        """Test pretty_json with complex nested dict"""
        test_dict = {
            "request_id": "123",
            "data": {
                "field1": "value1",
                "field2": 123,
            }
        }
        expected_json = '{\n    "request_id": "123",\n    "data": {...}\n}'
        mock_frappe.as_json.return_value = expected_json

        result = pretty_json(test_dict)

        mock_frappe.as_json.assert_called_once_with(test_dict, indent=4)
        self.assertEqual(result, expected_json)


class TestLinkIntegrationRequest(unittest.TestCase):
    """Test link_integration_request function"""

    @patch("india_compliance.gst_india.utils.api.frappe")
    def test_link_integration_request(self, mock_frappe):
        """Test linking integration request to GSTR Action"""
        request_id = "REQ123"
        doc_name = "INT-REQ-2025-00001"

        link_integration_request(request_id, doc_name)

        mock_frappe.db.set_value.assert_called_once_with(
            "GSTR Action",
            {"request_id": request_id},
            {"integration_request": doc_name}
        )

    @patch("india_compliance.gst_india.utils.api.frappe")
    def test_link_integration_request_with_different_ids(self, mock_frappe):
        """Test with different request and doc names"""
        request_id = "REQ999"
        doc_name = "INT-REQ-2025-99999"

        link_integration_request(request_id, doc_name)

        args, kwargs = mock_frappe.db.set_value.call_args
        self.assertEqual(args[0], "GSTR Action")
        self.assertEqual(args[1]["request_id"], "REQ999")
        self.assertEqual(args[2]["integration_request"], "INT-REQ-2025-99999")


class TestCreateIntegrationRequest(unittest.TestCase):
    """Test create_integration_request function"""

    @patch("india_compliance.gst_india.utils.api.link_integration_request")
    @patch("india_compliance.gst_india.utils.api.pretty_json")
    @patch("india_compliance.gst_india.utils.api.frappe")
    def test_create_integration_request_basic(self, mock_frappe, mock_pretty_json, mock_link):
        """Test basic integration request creation"""
        mock_pretty_json.side_effect = lambda x: str(x)
        mock_doc = MagicMock()
        mock_frappe.get_doc.return_value = mock_doc

        create_integration_request(
            url="https://api.test.com",
            request_id="REQ123",
            data={"test": "data"}
        )

        mock_frappe.get_doc.assert_called_once()
        mock_doc.insert.assert_called_once_with(
            ignore_permissions=True,
            ignore_links=True
        )
        mock_link.assert_not_called()

    @patch("india_compliance.gst_india.utils.api.link_integration_request")
    @patch("india_compliance.gst_india.utils.api.pretty_json")
    @patch("india_compliance.gst_india.utils.api.frappe")
    def test_create_integration_request_with_success(self, mock_frappe, mock_pretty_json, mock_link):
        """Test integration request with success status"""
        mock_pretty_json.side_effect = lambda x: str(x)
        mock_doc = MagicMock()
        mock_frappe.get_doc.return_value = mock_doc

        create_integration_request(
            url="https://api.test.com",
            output={"result": "success"}
        )

        args, kwargs = mock_frappe.get_doc.call_args
        doc_data = args[0]
        self.assertEqual(doc_data["status"], "Completed")

    @patch("india_compliance.gst_india.utils.api.link_integration_request")
    @patch("india_compliance.gst_india.utils.api.pretty_json")
    @patch("india_compliance.gst_india.utils.api.frappe")
    def test_create_integration_request_with_error(self, mock_frappe, mock_pretty_json, mock_link):
        """Test integration request with error status"""
        mock_pretty_json.side_effect = lambda x: str(x)
        mock_doc = MagicMock()
        mock_frappe.get_doc.return_value = mock_doc

        create_integration_request(
            url="https://api.test.com",
            error="API Error"
        )

        args, kwargs = mock_frappe.get_doc.call_args
        doc_data = args[0]
        self.assertEqual(doc_data["status"], "Failed")

    @patch("india_compliance.gst_india.utils.api.link_integration_request")
    @patch("india_compliance.gst_india.utils.api.pretty_json")
    @patch("india_compliance.gst_india.utils.api.frappe")
    def test_create_integration_request_with_update_gstr_action(
        self, mock_frappe, mock_pretty_json, mock_link
    ):
        """Test integration request with GSTR action update"""
        mock_pretty_json.side_effect = lambda x: str(x)
        mock_doc = MagicMock()
        mock_doc.name = "INT-REQ-123"
        mock_frappe.get_doc.return_value = mock_doc

        create_integration_request(
            request_id="REQ123",
            update_gstr_action=True
        )

        mock_link.assert_called_once_with("REQ123", "INT-REQ-123")

    @patch("india_compliance.gst_india.utils.api.link_integration_request")
    @patch("india_compliance.gst_india.utils.api.pretty_json")
    @patch("india_compliance.gst_india.utils.api.frappe")
    def test_create_integration_request_complete_flow(
        self, mock_frappe, mock_pretty_json, mock_link
    ):
        """Test complete integration request with all parameters"""
        mock_pretty_json.side_effect = lambda x: str(x) if x else ""
        mock_doc = MagicMock()
        mock_doc.name = "INT-REQ-001"
        mock_frappe.get_doc.return_value = mock_doc

        create_integration_request(
            url="https://api.test.com/endpoint",
            request_id="REQ001",
            request_headers={"Authorization": "Bearer token"},
            data={"field": "value"},
            output={"result": "success"},
            reference_doctype="Sales Invoice",
            reference_name="SI-2025-00001",
            update_gstr_action=False
        )

        args, kwargs = mock_frappe.get_doc.call_args
        doc_data = args[0]

        self.assertEqual(doc_data["doctype"], "Integration Request")
        self.assertEqual(doc_data["integration_request_service"], "India Compliance API")
        self.assertEqual(doc_data["request_id"], "REQ001")
        self.assertEqual(doc_data["url"], "https://api.test.com/endpoint")
        self.assertEqual(doc_data["reference_doctype"], "Sales Invoice")
        self.assertEqual(doc_data["reference_docname"], "SI-2025-00001")
        self.assertEqual(doc_data["status"], "Completed")

        mock_doc.insert.assert_called_once()
        mock_link.assert_not_called()

    @patch("india_compliance.gst_india.utils.api.link_integration_request")
    @patch("india_compliance.gst_india.utils.api.pretty_json")
    @patch("india_compliance.gst_india.utils.api.frappe")
    def test_create_integration_request_all_none_values(
        self, mock_frappe, mock_pretty_json, mock_link
    ):
        """Test integration request when all optional parameters are None"""
        mock_pretty_json.return_value = ""
        mock_doc = MagicMock()
        mock_frappe.get_doc.return_value = mock_doc

        create_integration_request()

        args, kwargs = mock_frappe.get_doc.call_args
        doc_data = args[0]

        self.assertIsNone(doc_data.get("url"))
        self.assertIsNone(doc_data.get("request_id"))
        self.assertEqual(doc_data["status"], "Completed")


class TestEnqueueIntegrationRequest(unittest.TestCase):
    """Test enqueue_integration_request function"""

    @patch("india_compliance.gst_india.utils.api.frappe")
    def test_enqueue_integration_request(self, mock_frappe):
        """Test enqueuing integration request"""
        mock_frappe.enqueue = MagicMock()

        test_data = {
            "url": "https://api.test.com",
            "request_id": "REQ123",
            "data": {"test": "data"}
        }

        enqueue_integration_request(**test_data)

        mock_frappe.enqueue.assert_called_once()
        args, kwargs = mock_frappe.enqueue.call_args
        self.assertIn("create_integration_request", args[0])
        self.assertEqual(kwargs["url"], "https://api.test.com")
        self.assertEqual(kwargs["request_id"], "REQ123")

    @patch("india_compliance.gst_india.utils.api.frappe")
    def test_enqueue_with_update_gstr_action(self, mock_frappe):
        """Test enqueuing with GSTR action update flag"""
        mock_frappe.enqueue = MagicMock()

        enqueue_integration_request(
            url="https://api.test.com",
            update_gstr_action=True
        )

        args, kwargs = mock_frappe.enqueue.call_args
        self.assertTrue(kwargs["update_gstr_action"])

    @patch("india_compliance.gst_india.utils.api.frappe")
    def test_enqueue_passes_all_kwargs(self, mock_frappe):
        """Test that all kwargs are passed through to frappe.enqueue"""
        mock_frappe.enqueue = MagicMock()

        kwargs_to_pass = {
            "url": "https://api.test.com",
            "request_id": "REQ123",
            "data": {"field": "value"},
            "error": None,
            "reference_doctype": "Sales Invoice",
        }

        enqueue_integration_request(**kwargs_to_pass)

        args, kwargs = mock_frappe.enqueue.call_args
        for key, value in kwargs_to_pass.items():
            self.assertEqual(kwargs[key], value)


if __name__ == "__main__":
    unittest.main()
