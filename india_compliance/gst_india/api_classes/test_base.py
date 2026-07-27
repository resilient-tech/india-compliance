from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from india_compliance.gst_india.api_classes.base import (
    BASE_URL,
    BaseAPI,
    change_base_path,
    check_scheduler_status,
)


class TestBaseAPI(IntegrationTestCase):
    def test_init_raises_when_api_not_enabled(self):
        mock_settings = frappe._dict(enable_api=False)
        with patch.object(frappe, "get_cached_doc", return_value=mock_settings):
            with self.assertRaises(frappe.ValidationError):
                BaseAPI()

    def test_get_url_with_base_path(self):
        api = BaseAPI.__new__(BaseAPI)
        api.BASE_PATH = "commonapi"
        api.sandbox_mode = False

        url = api.get_url("search")

        self.assertEqual(url, f"{BASE_URL}/commonapi/search")

    def test_get_url_sandbox_mode_adds_test_prefix(self):
        api = BaseAPI.__new__(BaseAPI)
        api.BASE_PATH = "commonapi"
        api.sandbox_mode = True

        url = api.get_url("search")

        self.assertEqual(url, f"{BASE_URL}/test/commonapi/search")

    def test_get_url_passes_through_full_https_url(self):
        api = BaseAPI.__new__(BaseAPI)
        api.sandbox_mode = False
        full_url = "https://custom-gsp.example.com/api/v1"

        url = api.get_url(full_url)

        self.assertEqual(url, full_url)

    def test_get_url_no_base_path(self):
        api = BaseAPI.__new__(BaseAPI)
        api.BASE_PATH = ""
        api.sandbox_mode = False

        url = api.get_url("search")

        self.assertEqual(url, f"{BASE_URL}/search")

    def test_get_sensitive_info_mapping_returns_default(self):
        api = BaseAPI.__new__(BaseAPI)

        mapping = api._get_sensitive_info_mapping()

        self.assertEqual(mapping, BaseAPI.DEFAULT_MASK_MAP)

    def test_get_sensitive_info_mapping_merges_overrides(self):
        api = BaseAPI.__new__(BaseAPI)
        api._get_sensitive_info_overrides = lambda: {"headers": ["extra-key"]}

        mapping = api._get_sensitive_info_mapping()

        self.assertEqual(mapping["headers"], ["extra-key"])
        self.assertEqual(mapping["output"], BaseAPI.DEFAULT_MASK_MAP["output"])

    def test_get_sensitive_info_overrides_returns_empty_dict(self):
        api = BaseAPI.__new__(BaseAPI)

        self.assertEqual(api._get_sensitive_info_overrides(), {})

    def test_mask_sensitive_info_masks_matching_keys(self):
        api = BaseAPI.__new__(BaseAPI)
        target = {"password": "secret123", "name": "visible"}

        api._mask_sensitive_info(target, ["password"])

        self.assertEqual(target["password"], BaseAPI.PLACEHOLDER)
        self.assertEqual(target["name"], "visible")

    def test_mask_sensitive_info_skips_non_matching_keys(self):
        api = BaseAPI.__new__(BaseAPI)
        target = {"name": "visible"}

        api._mask_sensitive_info(target, ["password"])

        self.assertEqual(target["name"], "visible")

    def test_mask_sensitive_info_skips_none_target(self):
        api = BaseAPI.__new__(BaseAPI)

        api._mask_sensitive_info(None, ["password"])

    def test_mask_sensitive_info_skips_none_keys(self):
        api = BaseAPI.__new__(BaseAPI)
        target = {"password": "secret"}

        api._mask_sensitive_info(target, None)

        self.assertEqual(target["password"], "secret")

    def test_generate_request_id_starts_with_ic(self):
        api = BaseAPI.__new__(BaseAPI)

        request_id = api.generate_request_id()

        self.assertTrue(request_id.startswith("IC"))

    def test_generate_request_id_default_length(self):
        api = BaseAPI.__new__(BaseAPI)

        request_id = api.generate_request_id()

        self.assertEqual(len(request_id), 12)

    def test_change_base_path_changes_path_inside_wrapper(self):
        original = "original"
        new = "newpath"

        class FakeAPI:
            BASE_PATH = original

            @change_base_path(new)
            def method(self):
                return self.BASE_PATH

        obj = FakeAPI()
        result = obj.method()

        self.assertEqual(result, new)
        self.assertEqual(obj.BASE_PATH, original)

    def test_change_base_path_restores_on_exception(self):
        original = "original"
        new = "newpath"

        class FakeAPI:
            BASE_PATH = original

            @change_base_path(new)
            def method(self):
                raise RuntimeError("boom")

        obj = FakeAPI()

        with self.assertRaises(RuntimeError):
            obj.method()

        self.assertEqual(obj.BASE_PATH, original)

    def test_check_scheduler_status_skips_in_test_mode(self):
        result = check_scheduler_status()
        self.assertIsNone(result)
