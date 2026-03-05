"""
Unit tests for change log utility functions.
"""

import unittest
from unittest.mock import MagicMock, patch

from india_compliance.utils.change_log_utils import create_change_log_comment


class TestCreateChangeLogComment(unittest.TestCase):
    """Test create_change_log_comment function"""

    def setUp(self):
        """Set up test fixtures"""
        self.patcher_frappe = patch("india_compliance.utils.change_log_utils.frappe")
        self.patcher_underscore = patch("india_compliance.utils.change_log_utils._")
        self.patcher_get_fullname = patch(
            "india_compliance.utils.change_log_utils.get_fullname"
        )
        self.patcher_escape_html = patch(
            "india_compliance.utils.change_log_utils.escape_html"
        )
        self.patcher_get_date_str = patch(
            "india_compliance.utils.change_log_utils.get_date_str"
        )

        self.mock_frappe = self.patcher_frappe.start()
        self.mock_underscore = self.patcher_underscore.start()
        self.mock_get_fullname = self.patcher_get_fullname.start()
        self.mock_escape_html = self.patcher_escape_html.start()
        self.mock_get_date_str = self.patcher_get_date_str.start()

        # Set up default mock return values
        self.mock_frappe.bold = lambda x: f"<b>{x}</b>"
        self.mock_underscore.side_effect = lambda x: x  # Return input as-is
        self.mock_get_fullname.return_value = "Test User"
        self.mock_escape_html.side_effect = lambda x: x  # Return input as-is
        self.mock_get_date_str.side_effect = lambda x: str(x)  # Return input as-is

    def tearDown(self):
        """Clean up patches"""
        self.patcher_frappe.stop()
        self.patcher_underscore.stop()
        self.patcher_get_fullname.stop()
        self.patcher_escape_html.stop()
        self.patcher_get_date_str.stop()

    def test_no_changes_returns_none(self):
        """Test that no changes returns None"""
        old_values = {"field1": "value1"}
        new_values = {"field1": "value1"}

        result = create_change_log_comment(old_values, new_values)

        self.assertIsNone(result)

    def test_single_field_change(self):
        """Test change in single field"""
        old_values = {"status": "Draft"}
        new_values = {"status": "Submitted"}

        result = create_change_log_comment(old_values, new_values)

        self.assertIsNotNone(result)
        self.assertIn("Draft", result)
        self.assertIn("Submitted", result)
        self.assertIn("<table", result)

    def test_multiple_field_changes(self):
        """Test changes in multiple fields"""
        old_values = {"status": "Draft", "amount": 100}
        new_values = {"status": "Submitted", "amount": 150}

        result = create_change_log_comment(old_values, new_values)

        self.assertIsNotNone(result)
        self.assertIn("Draft", result)
        self.assertIn("Submitted", result)
        self.assertIn("100", result)
        self.assertIn("150", result)

    def test_field_added(self):
        """Test when new field is added"""
        old_values = {"field1": "value1"}
        new_values = {"field1": "value1", "field2": "new_value"}

        result = create_change_log_comment(old_values, new_values)

        self.assertIsNotNone(result)
        self.assertIn("new_value", result)

    def test_field_removed(self):
        """Test when field is removed (set to None)"""
        old_values = {"field1": "value1", "field2": "value2"}
        new_values = {"field1": "value1", "field2": None}

        result = create_change_log_comment(old_values, new_values)

        self.assertIsNotNone(result)
        self.assertIn("<empty>", result)

    def test_field_labels_mapping(self):
        """Test custom field labels"""
        old_values = {"status": "Draft"}
        new_values = {"status": "Submitted"}
        field_labels = {"status": "Document Status"}

        result = create_change_log_comment(
            old_values, new_values, field_labels=field_labels
        )

        self.assertIsNotNone(result)
        self.assertIn("Document Status", result)

    def test_field_labels_filters_fields(self):
        """Test that only labeled fields are included when field_labels provided"""
        old_values = {"status": "Draft", "amount": 100}
        new_values = {"status": "Submitted", "amount": 150}
        field_labels = {"status": "Status"}  # Only status, not amount

        result = create_change_log_comment(
            old_values, new_values, field_labels=field_labels
        )

        self.assertIsNotNone(result)
        self.assertIn("Draft", result)
        self.assertIn("Submitted", result)
        self.assertNotIn("100", result)
        self.assertNotIn("150", result)

    def test_date_field_formatting(self):
        """Test date field formatting"""
        old_values = {"due_date": "2024-01-01"}
        new_values = {"due_date": "2024-01-15"}
        date_fields = ["due_date"]

        result = create_change_log_comment(
            old_values, new_values, date_fields=date_fields
        )

        self.assertIsNotNone(result)
        # Check that get_date_str was called
        self.assertTrue(self.mock_get_date_str.called)

    def test_custom_comment_prefix(self):
        """Test custom comment prefix"""
        old_values = {"status": "Draft"}
        new_values = {"status": "Submitted"}
        comment_prefix = "Changed by {user}"

        result = create_change_log_comment(
            old_values, new_values, comment_prefix=comment_prefix
        )

        self.assertIsNotNone(result)
        self.assertIn("Changed by", result)

    def test_custom_user(self):
        """Test custom user name"""
        old_values = {"status": "Draft"}
        new_values = {"status": "Submitted"}
        custom_user = "Custom User"

        result = create_change_log_comment(
            old_values, new_values, user=custom_user
        )

        self.assertIsNotNone(result)
        self.assertIn(custom_user, result)
        # get_fullname should not be called when user is specified
        self.mock_get_fullname.assert_not_called()

    def test_default_user_when_not_specified(self):
        """Test that get_fullname is called when user is not specified"""
        old_values = {"status": "Draft"}
        new_values = {"status": "Submitted"}

        result = create_change_log_comment(old_values, new_values)

        self.assertIsNotNone(result)
        self.mock_get_fullname.assert_called()

    def test_field_label_generation_from_fieldname(self):
        """Test automatic field label generation from field name"""
        old_values = {"approval_status": "Pending"}
        new_values = {"approval_status": "Approved"}

        result = create_change_log_comment(old_values, new_values)

        self.assertIsNotNone(result)
        self.assertIn("Approval Status", result)

    def test_html_escaping(self):
        """Test that values are properly HTML escaped"""
        old_values = {"notes": "<script>alert('test')</script>"}
        new_values = {"notes": "Safe text"}

        result = create_change_log_comment(old_values, new_values)

        self.assertIsNotNone(result)
        # escape_html should be called
        self.assertTrue(self.mock_escape_html.called)

    def test_none_to_value_change(self):
        """Test change from None to value"""
        old_values = {"description": None}
        new_values = {"description": "New description"}

        result = create_change_log_comment(old_values, new_values)

        self.assertIsNotNone(result)
        self.assertIn("<empty>", result)
        self.assertIn("New description", result)

    def test_value_to_none_change(self):
        """Test change from value to None"""
        old_values = {"description": "Old description"}
        new_values = {"description": None}

        result = create_change_log_comment(old_values, new_values)

        self.assertIsNotNone(result)
        self.assertIn("Old description", result)
        self.assertIn("<empty>", result)

    def test_empty_string_handling(self):
        """Test handling of empty strings"""
        old_values = {"field": ""}
        new_values = {"field": "value"}

        result = create_change_log_comment(old_values, new_values)

        self.assertIsNotNone(result)
        self.assertIn("value", result)

    def test_html_table_structure(self):
        """Test HTML table structure"""
        old_values = {"status": "Draft"}
        new_values = {"status": "Submitted"}

        result = create_change_log_comment(old_values, new_values)

        self.assertIsNotNone(result)
        self.assertIn("<table", result)
        self.assertIn("</table>", result)
        self.assertIn("<thead>", result)
        self.assertIn("<tbody>", result)
        self.assertIn("<tr>", result)
        self.assertIn("<td>", result)

    def test_numeric_values(self):
        """Test handling of numeric values"""
        old_values = {"amount": 100}
        new_values = {"amount": 150}

        result = create_change_log_comment(old_values, new_values)

        self.assertIsNotNone(result)
        self.assertIn("100", result)
        self.assertIn("150", result)

    def test_boolean_values(self):
        """Test handling of boolean values"""
        old_values = {"is_active": True}
        new_values = {"is_active": False}

        result = create_change_log_comment(old_values, new_values)

        self.assertIsNotNone(result)
        self.assertIn("True", result)
        self.assertIn("False", result)


if __name__ == "__main__":
    unittest.main()
