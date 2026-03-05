"""
Unit tests for custom field utility functions.
"""

import functools
import unittest
from unittest.mock import MagicMock, call, patch

from india_compliance.utils.custom_fields import (
    delete_custom_fields,
    delete_old_fields,
    get_custom_fields_creator,
    make_custom_fields,
    toggle_custom_fields,
)


class TestToggleCustomFields(unittest.TestCase):
    """Test toggle_custom_fields function"""

    @patch("india_compliance.utils.custom_fields.frappe")
    def test_toggle_single_doctype_single_field_show(self, mock_frappe):
        """Test toggling visibility of single field in single doctype - show"""
        custom_fields = {
            "Sales Invoice": [{"fieldname": "custom_field"}]
        }

        toggle_custom_fields(custom_fields, True)

        mock_frappe.db.set_value.assert_called_once()
        args, kwargs = mock_frappe.db.set_value.call_args
        self.assertEqual(args[0], "Custom Field")
        self.assertEqual(args[2], "hidden")
        self.assertEqual(args[3], 0)  # not show -> hidden = 0

    @patch("india_compliance.utils.custom_fields.frappe")
    def test_toggle_single_doctype_single_field_hide(self, mock_frappe):
        """Test toggling visibility of single field in single doctype - hide"""
        custom_fields = {
            "Sales Invoice": [{"fieldname": "custom_field"}]
        }

        toggle_custom_fields(custom_fields, False)

        mock_frappe.db.set_value.assert_called_once()
        args, kwargs = mock_frappe.db.set_value.call_args
        self.assertEqual(args[3], 1)  # show = False -> hidden = 1

    @patch("india_compliance.utils.custom_fields.frappe")
    def test_toggle_single_doctype_dict_field(self, mock_frappe):
        """Test toggling with dict field instead of list"""
        custom_fields = {
            "Sales Invoice": {"fieldname": "custom_field"}
        }

        toggle_custom_fields(custom_fields, True)

        mock_frappe.db.set_value.assert_called_once()

    @patch("india_compliance.utils.custom_fields.frappe")
    def test_toggle_multiple_fields(self, mock_frappe):
        """Test toggling multiple fields"""
        custom_fields = {
            "Sales Invoice": [
                {"fieldname": "field1"},
                {"fieldname": "field2"},
                {"fieldname": "field3"},
            ]
        }

        toggle_custom_fields(custom_fields, True)

        self.assertEqual(mock_frappe.db.set_value.call_count, 1)
        args, kwargs = mock_frappe.db.set_value.call_args
        filters = args[1]
        self.assertIn("field1", filters["fieldname"][1])
        self.assertIn("field2", filters["fieldname"][1])
        self.assertIn("field3", filters["fieldname"][1])

    @patch("india_compliance.utils.custom_fields.frappe")
    def test_toggle_multiple_doctypes(self, mock_frappe):
        """Test toggling fields across multiple doctypes"""
        custom_fields = {
            ("Sales Invoice", "Purchase Invoice"): [{"fieldname": "custom_field"}]
        }

        toggle_custom_fields(custom_fields, True)

        self.assertEqual(mock_frappe.db.set_value.call_count, 2)

    @patch("india_compliance.utils.custom_fields.frappe")
    def test_toggle_clears_cache(self, mock_frappe):
        """Test that cache is cleared for affected doctypes"""
        custom_fields = {
            "Sales Invoice": [{"fieldname": "custom_field"}]
        }

        toggle_custom_fields(custom_fields, True)

        mock_frappe.clear_cache.assert_called_with(doctype="Sales Invoice")

    @patch("india_compliance.utils.custom_fields.frappe")
    def test_toggle_multiple_doctypes_clears_cache_for_each(self, mock_frappe):
        """Test that cache is cleared for each doctype"""
        custom_fields = {
            ("Sales Invoice", "Purchase Invoice"): [{"fieldname": "custom_field"}]
        }

        toggle_custom_fields(custom_fields, True)

        expected_calls = [
            call(doctype="Sales Invoice"),
            call(doctype="Purchase Invoice"),
        ]
        mock_frappe.clear_cache.assert_has_calls(expected_calls)


class TestDeleteOldFields(unittest.TestCase):
    """Test delete_old_fields function"""

    @patch("india_compliance.utils.custom_fields.frappe")
    def test_delete_single_field_single_doctype(self, mock_frappe):
        """Test deleting single field from single doctype"""
        delete_old_fields("field_to_delete", "Sales Invoice")

        mock_frappe.db.delete.assert_called_once()
        args, kwargs = mock_frappe.db.delete.call_args
        self.assertEqual(args[0], "Custom Field")
        filters = args[1]
        self.assertEqual(filters["fieldname"], ("in", ("field_to_delete",)))
        self.assertEqual(filters["dt"], ("in", ("Sales Invoice",)))

    @patch("india_compliance.utils.custom_fields.frappe")
    def test_delete_multiple_fields(self, mock_frappe):
        """Test deleting multiple fields"""
        delete_old_fields(
            ("field1", "field2", "field3"),
            "Sales Invoice"
        )

        mock_frappe.db.delete.assert_called_once()
        args, kwargs = mock_frappe.db.delete.call_args
        filters = args[1]
        self.assertEqual(len(filters["fieldname"][1]), 3)

    @patch("india_compliance.utils.custom_fields.frappe")
    def test_delete_multiple_doctypes(self, mock_frappe):
        """Test deleting from multiple doctypes"""
        delete_old_fields(
            "field_to_delete",
            ("Sales Invoice", "Purchase Invoice")
        )

        mock_frappe.db.delete.assert_called_once()
        args, kwargs = mock_frappe.db.delete.call_args
        filters = args[1]
        self.assertEqual(len(filters["dt"][1]), 2)


class TestDeleteCustomFields(unittest.TestCase):
    """Test delete_custom_fields function"""

    @patch("india_compliance.utils.custom_fields.frappe")
    def test_delete_single_field_single_doctype(self, mock_frappe):
        """Test deleting custom field from single doctype"""
        custom_fields = {
            "Sales Invoice": [{"fieldname": "custom_field"}]
        }

        delete_custom_fields(custom_fields)

        mock_frappe.db.delete.assert_called_once()
        args, kwargs = mock_frappe.db.delete.call_args
        self.assertEqual(args[0], "Custom Field")
        filters = args[1]
        self.assertIn("custom_field", filters["fieldname"][1])
        self.assertEqual(filters["dt"], "Sales Invoice")

    @patch("india_compliance.utils.custom_fields.frappe")
    def test_delete_dict_field(self, mock_frappe):
        """Test deleting with dict field instead of list"""
        custom_fields = {
            "Sales Invoice": {"fieldname": "custom_field"}
        }

        delete_custom_fields(custom_fields)

        mock_frappe.db.delete.assert_called_once()

    @patch("india_compliance.utils.custom_fields.frappe")
    def test_delete_multiple_fields(self, mock_frappe):
        """Test deleting multiple fields from single doctype"""
        custom_fields = {
            "Sales Invoice": [
                {"fieldname": "field1"},
                {"fieldname": "field2"},
            ]
        }

        delete_custom_fields(custom_fields)

        mock_frappe.db.delete.assert_called_once()
        args, kwargs = mock_frappe.db.delete.call_args
        filters = args[1]
        self.assertEqual(len(filters["fieldname"][1]), 2)

    @patch("india_compliance.utils.custom_fields.frappe")
    def test_delete_multiple_doctypes(self, mock_frappe):
        """Test deleting from multiple doctypes"""
        custom_fields = {
            ("Sales Invoice", "Purchase Invoice"): [{"fieldname": "custom_field"}]
        }

        delete_custom_fields(custom_fields)

        self.assertEqual(mock_frappe.db.delete.call_count, 2)

    @patch("india_compliance.utils.custom_fields.frappe")
    def test_delete_clears_cache(self, mock_frappe):
        """Test that cache is cleared"""
        custom_fields = {
            "Sales Invoice": [{"fieldname": "custom_field"}]
        }

        delete_custom_fields(custom_fields)

        mock_frappe.clear_cache.assert_called_with(doctype="Sales Invoice")


class TestMakeCustomFields(unittest.TestCase):
    """Test make_custom_fields function"""

    @patch("india_compliance.utils.custom_fields.create_custom_fields")
    @patch("india_compliance.utils.custom_fields.frappe")
    def test_make_custom_fields_adds_module(self, mock_frappe, mock_create):
        """Test that module is added to fields"""
        custom_fields = {
            "Sales Invoice": [{"fieldname": "custom_field"}]
        }

        make_custom_fields(custom_fields, "test_module")

        # Check that module was added
        args, kwargs = mock_create.call_args
        fields_arg = args[0]
        self.assertEqual(fields_arg["Sales Invoice"][0]["module"], "test_module")

    @patch("india_compliance.utils.custom_fields.create_custom_fields")
    @patch("india_compliance.utils.custom_fields.frappe")
    def test_make_custom_fields_converts_dict_to_tuple(self, mock_frappe, mock_create):
        """Test that dict fields are converted to tuple"""
        custom_fields = {
            "Sales Invoice": {"fieldname": "custom_field"}
        }

        make_custom_fields(custom_fields, "test_module")

        args, kwargs = mock_create.call_args
        fields_arg = args[0]
        # Should be converted to tuple
        self.assertIsInstance(fields_arg["Sales Invoice"], tuple)

    @patch("india_compliance.utils.custom_fields.create_custom_fields")
    @patch("india_compliance.utils.custom_fields.frappe")
    def test_make_custom_fields_passes_extra_args(self, mock_frappe, mock_create):
        """Test that extra arguments are passed to create_custom_fields"""
        custom_fields = {
            "Sales Invoice": [{"fieldname": "custom_field"}]
        }

        make_custom_fields(custom_fields, "test_module", ignore_permissions=True)

        args, kwargs = mock_create.call_args
        self.assertTrue("ignore_permissions" in kwargs or len(args) > 1)

    @patch("india_compliance.utils.custom_fields.create_custom_fields")
    @patch("india_compliance.utils.custom_fields.frappe")
    def test_make_custom_fields_multiple_fields(self, mock_frappe, mock_create):
        """Test with multiple fields"""
        custom_fields = {
            "Sales Invoice": [
                {"fieldname": "field1"},
                {"fieldname": "field2"},
            ]
        }

        make_custom_fields(custom_fields, "test_module")

        args, kwargs = mock_create.call_args
        fields_arg = args[0]
        for field in fields_arg["Sales Invoice"]:
            self.assertEqual(field["module"], "test_module")


class TestGetCustomFieldsCreator(unittest.TestCase):
    """Test get_custom_fields_creator function"""

    @patch("india_compliance.utils.custom_fields.create_custom_fields")
    @patch("india_compliance.utils.custom_fields.frappe")
    def test_returns_partial_function(self, mock_frappe, mock_create):
        """Test that function returns a partial function"""
        creator = get_custom_fields_creator("test_module")

        self.assertIsInstance(creator, functools.partial)

    @patch("india_compliance.utils.custom_fields.create_custom_fields")
    @patch("india_compliance.utils.custom_fields.frappe")
    def test_creator_pre_fills_module_name(self, mock_frappe, mock_create):
        """Test that creator pre-fills module_name"""
        creator = get_custom_fields_creator("test_module")
        custom_fields = {
            "Sales Invoice": [{"fieldname": "custom_field"}]
        }

        creator(custom_fields)

        args, kwargs = mock_create.call_args
        fields_arg = args[0]
        self.assertEqual(fields_arg["Sales Invoice"][0]["module"], "test_module")

    @patch("india_compliance.utils.custom_fields.create_custom_fields")
    @patch("india_compliance.utils.custom_fields.frappe")
    def test_creator_can_be_called_multiple_times(self, mock_frappe, mock_create):
        """Test that creator can be used multiple times"""
        creator = get_custom_fields_creator("test_module")

        custom_fields1 = {"Sales Invoice": [{"fieldname": "field1"}]}
        custom_fields2 = {"Purchase Invoice": [{"fieldname": "field2"}]}

        creator(custom_fields1)
        creator(custom_fields2)

        self.assertEqual(mock_create.call_count, 2)


if __name__ == "__main__":
    unittest.main()
