from unittest import mock

import frappe
from frappe.tests import IntegrationTestCase

from india_compliance.gst_india.utils.transaction_data import (
    GSTTransactionData,
    validate_gst_tax_rate,
)


class TestTransactionDataUtils(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        frappe.db.savepoint("before_test_transaction_data_utils")

    @classmethod
    def tearDownClass(cls):
        frappe.db.rollback(save_point="before_test_transaction_data_utils")

    # =========================================================================
    # GSTTransactionData.__init__ for purchase doctypes
    # =========================================================================

    def test_init_for_purchase_invoice_sets_supplier_name_field(self):
        doc = frappe._dict(
            {
                "doctype": "Purchase Invoice",
                "is_reverse_charge": 0,
                "supplier_name": "Test Supplier",
            }
        )
        gst_data = GSTTransactionData(doc)
        self.assertEqual(gst_data.party_name_field, "supplier_name")

    def test_init_for_purchase_receipt_sets_supplier_name_field(self):
        doc = frappe._dict(
            {
                "doctype": "Purchase Receipt",
                "is_reverse_charge": 0,
                "supplier_name": "Test Supplier",
            }
        )
        gst_data = GSTTransactionData(doc)
        self.assertEqual(gst_data.party_name_field, "supplier_name")

    def test_init_for_stock_entry_sets_supplier_name_field(self):
        doc = frappe._dict(
            {
                "doctype": "Stock Entry",
                "is_reverse_charge": 0,
                "supplier_name": "Test Supplier",
            }
        )
        gst_data = GSTTransactionData(doc)
        self.assertEqual(gst_data.party_name_field, "supplier_name")

    def test_init_for_subcontracting_receipt_sets_supplier_name_field(self):
        doc = frappe._dict(
            {
                "doctype": "Subcontracting Receipt",
                "is_reverse_charge": 0,
                "supplier_name": "Test Supplier",
            }
        )
        gst_data = GSTTransactionData(doc)
        self.assertEqual(gst_data.party_name_field, "supplier_name")

    def test_init_for_sales_invoice_keeps_customer_name_field(self):
        doc = frappe._dict(
            {
                "doctype": "Sales Invoice",
                "is_reverse_charge": 0,
                "customer_name": "Test Customer",
            }
        )
        gst_data = GSTTransactionData(doc)
        self.assertEqual(gst_data.party_name_field, "customer_name")

    def test_init_for_purchase_with_reverse_charge_sets_is_purchase_rcm(self):
        doc = frappe._dict(
            {
                "doctype": "Purchase Invoice",
                "is_reverse_charge": 1,
                "supplier_name": "Test Supplier",
            }
        )
        gst_data = GSTTransactionData(doc)
        self.assertTrue(gst_data.is_purchase_rcm)

    def test_init_for_purchase_without_reverse_charge_does_not_set_rcm(self):
        doc = frappe._dict(
            {
                "doctype": "Purchase Invoice",
                "is_reverse_charge": 0,
                "supplier_name": "Test Supplier",
            }
        )
        gst_data = GSTTransactionData(doc)
        self.assertFalse(gst_data.is_purchase_rcm)

    @mock.patch("frappe.db.get_value", return_value="Subcon Customer")
    def test_init_for_stock_entry_with_subcontracting_inward_fetches_customer_name(
        self, mock_get_value
    ):
        doc = frappe._dict(
            {
                "doctype": "Stock Entry",
                "is_reverse_charge": 0,
                "supplier_name": None,
                "subcontracting_inward_order": "SCIO-00001",
            }
        )
        gst_data = GSTTransactionData(doc)
        self.assertEqual(gst_data.party_name, "Subcon Customer")
        mock_get_value.assert_called_once_with(
            "Subcontracting Inward Order",
            "SCIO-00001",
            "customer_name",
        )

    # =========================================================================
    # GSTTransactionData.sanitize_value — static method
    # =========================================================================

    def test_sanitize_value_removes_non_alphanumeric_with_regex_1(self):
        result = GSTTransactionData.sanitize_value("Hello@World!", regex=1)
        self.assertEqual(result, "HelloWorld")

    def test_sanitize_value_preserves_hyphen_slash_dot_and_space_with_regex_2(self):
        result = GSTTransactionData.sanitize_value("AB/CD-12.34 XY", regex=2)
        self.assertEqual(result, "AB/CD-12.34 XY")

    def test_sanitize_value_removes_special_chars_with_regex_2(self):
        result = GSTTransactionData.sanitize_value("Hello@World#", regex=2)
        self.assertEqual(result, "HelloWorld")

    def test_sanitize_value_preserves_extended_chars_with_regex_3(self):
        result = GSTTransactionData.sanitize_value(
            "Item@Name #1 (A&B), Co.", regex=3
        )
        self.assertEqual(result, "Item@Name #1 (A&B), Co.")

    def test_sanitize_value_below_min_length_returns_none(self):
        result = GSTTransactionData.sanitize_value("ab", min_length=3)
        self.assertIsNone(result)

    def test_sanitize_value_at_min_length_passes_through(self):
        result = GSTTransactionData.sanitize_value("abc", min_length=3)
        self.assertEqual(result, "abc")

    def test_sanitize_value_truncates_at_max_length(self):
        result = GSTTransactionData.sanitize_value("A" * 150, max_length=100)
        self.assertEqual(len(result), 100)
        self.assertEqual(result, "A" * 100)

    def test_sanitize_value_with_fieldname_throws_for_short_value(self):
        with self.assertRaises(frappe.ValidationError):
            GSTTransactionData.sanitize_value(
                "ab",
                fieldname="address_title",
                reference_doctype="Address",
                reference_name="ADDR-00001",
            )

    def test_sanitize_value_with_regex_makes_value_too_short_returns_none(self):
        result = GSTTransactionData.sanitize_value("a!b", regex=1, min_length=3)
        self.assertIsNone(result)

    def test_sanitize_value_with_fieldname_and_regex_makes_value_too_short_throws(
        self,
    ):
        with self.assertRaises(frappe.ValidationError):
            GSTTransactionData.sanitize_value(
                "a!b",
                regex=1,
                fieldname="address_line1",
                reference_doctype="Address",
                reference_name="ADDR-00001",
            )

    # =========================================================================
    # GSTTransactionData.sanitize_data — static method
    # =========================================================================

    def test_sanitize_data_filters_empty_strings_and_none_from_dict(self):
        data = {"key1": "value", "key2": "", "key3": None}
        result = GSTTransactionData.sanitize_data(data)
        self.assertEqual(result, {"key1": "value"})

    def test_sanitize_data_filters_empty_strings_and_none_from_list(self):
        data = ["value", "", None]
        result = GSTTransactionData.sanitize_data(data)
        self.assertEqual(result, ["value"])

    def test_sanitize_data_preserves_zero_in_dict(self):
        data = {"key1": 0, "key2": None, "key3": ""}
        result = GSTTransactionData.sanitize_data(data)
        self.assertEqual(result, {"key1": 0})

    def test_sanitize_data_preserves_zero_in_list(self):
        data = ["value", 0, "", None]
        result = GSTTransactionData.sanitize_data(data)
        self.assertEqual(result, ["value", 0])

    def test_sanitize_data_preserves_zero_float_in_dict(self):
        data = {"key1": 0.0, "key2": None}
        result = GSTTransactionData.sanitize_data(data)
        self.assertEqual(result, {"key1": 0.0})

    def test_sanitize_data_recursively_filters_nested_dict(self):
        data = {"outer": {"inner": 42, "empty": "", "nil": None}}
        result = GSTTransactionData.sanitize_data(data)
        self.assertEqual(result, {"outer": {"inner": 42}})

    def test_sanitize_data_recursively_filters_nested_list(self):
        data = {"items": ["a", "", None, 0], "meta": "keep"}
        result = GSTTransactionData.sanitize_data(data)
        self.assertEqual(result, {"items": ["a", 0], "meta": "keep"})

    # =========================================================================
    # GSTTransactionData.get_progressive_item_tax_amount
    # =========================================================================

    def test_get_progressive_item_tax_amount_normal(self):
        doc = frappe._dict(
            {"doctype": "Sales Invoice", "is_reverse_charge": 0, "customer_name": "Test"}
        )
        gst_data = GSTTransactionData(doc)
        result = gst_data.get_progressive_item_tax_amount(9.0, "cgst")
        self.assertEqual(result, 9.0)
        self.assertEqual(gst_data.rounding_errors["cgst_rounding_error"], 0.0)

    def test_get_progressive_item_tax_amount_accumulates_rounding_error(self):
        doc = frappe._dict(
            {"doctype": "Sales Invoice", "is_reverse_charge": 0, "customer_name": "Test"}
        )
        gst_data = GSTTransactionData(doc)
        gst_data.rounding_errors["igst_rounding_error"] = 0.006

        result = gst_data.get_progressive_item_tax_amount(9.0, "igst")

        self.assertEqual(result, 9.01)
        self.assertAlmostEqual(gst_data.rounding_errors["igst_rounding_error"], -0.004)

    # =========================================================================
    # GSTTransactionData.update_totals_for_refund
    # =========================================================================

    def test_update_totals_for_refund_reduces_grand_total(self):
        doc = frappe._dict(
            {
                "doctype": "Purchase Invoice",
                "is_reverse_charge": 0,
                "supplier_name": "Test Supplier",
                "taxes": [
                    frappe._dict(
                        {
                            "gst_tax_type": "cgst_refund",
                            "base_tax_amount_after_discount_amount": 10.0,
                        }
                    ),
                    frappe._dict(
                        {
                            "gst_tax_type": "sgst_refund",
                            "base_tax_amount_after_discount_amount": 5.0,
                        }
                    ),
                ],
            }
        )
        gst_data = GSTTransactionData(doc)
        gst_data.transaction_details.grand_total = 100.0
        gst_data.update_totals_for_refund()

        self.assertEqual(gst_data.transaction_details.grand_total, 85.0)

    def test_update_totals_for_refund_skips_non_refund_tax_types(self):
        doc = frappe._dict(
            {
                "doctype": "Purchase Invoice",
                "is_reverse_charge": 0,
                "supplier_name": "Test Supplier",
                "taxes": [
                    frappe._dict(
                        {
                            "gst_tax_type": "cgst",
                            "base_tax_amount_after_discount_amount": 10.0,
                        }
                    ),
                    frappe._dict(
                        {
                            "gst_tax_type": "cgst_refund",
                            "base_tax_amount_after_discount_amount": 5.0,
                        }
                    ),
                ],
            }
        )
        gst_data = GSTTransactionData(doc)
        gst_data.transaction_details.grand_total = 100.0
        gst_data.update_totals_for_refund()

        self.assertEqual(gst_data.transaction_details.grand_total, 95.0)

    # =========================================================================
    # GSTTransactionData.group_same_items
    # =========================================================================

    def test_group_same_items_groups_by_item_code_and_sums_qty_and_taxable_value(
        self,
    ):
        doc = frappe._dict(
            {
                "doctype": "Sales Invoice",
                "is_reverse_charge": 0,
                "customer_name": "Test",
                "group_same_items": 1,
                "items": [
                    frappe._dict(
                        {
                            "item_code": "ITEM-001",
                            "idx": 1,
                            "qty": 2.0,
                            "taxable_value": 100.0,
                            "gst_hsn_code": "61149090",
                            "uom": "Nos",
                            "stock_uom": "Nos",
                            "gst_treatment": "Taxable",
                            "item_name": "Test Item",
                            "cgst_amount": 9.0,
                            "sgst_amount": 9.0,
                            "igst_amount": 0.0,
                            "cess_amount": 0.0,
                            "cess_non_advol_amount": 0.0,
                        }
                    ),
                    frappe._dict(
                        {
                            "item_code": "ITEM-001",
                            "idx": 2,
                            "qty": 3.0,
                            "taxable_value": 150.0,
                            "gst_hsn_code": "61149090",
                            "uom": "Nos",
                            "stock_uom": "Nos",
                            "gst_treatment": "Taxable",
                            "item_name": "Test Item",
                            "cgst_amount": 13.5,
                            "sgst_amount": 13.5,
                            "igst_amount": 0.0,
                            "cess_amount": 0.0,
                            "cess_non_advol_amount": 0.0,
                        }
                    ),
                ],
            }
        )
        gst_data = GSTTransactionData(doc)
        grouped = gst_data.group_same_items()

        self.assertEqual(len(grouped), 1)
        self.assertEqual(grouped[0].item_code, "ITEM-001")
        self.assertEqual(grouped[0].qty, 5.0)
        self.assertEqual(grouped[0].taxable_value, 250.0)
        self.assertEqual(grouped[0].cgst_amount, 22.5)
        self.assertEqual(grouped[0].sgst_amount, 22.5)

    def test_group_same_items_does_not_group_different_item_codes(self):
        doc = frappe._dict(
            {
                "doctype": "Sales Invoice",
                "is_reverse_charge": 0,
                "customer_name": "Test",
                "group_same_items": 1,
                "items": [
                    frappe._dict(
                        {
                            "item_code": "ITEM-001",
                            "idx": 1,
                            "qty": 2.0,
                            "taxable_value": 100.0,
                            "gst_hsn_code": "61149090",
                            "uom": "Nos",
                            "stock_uom": "Nos",
                            "gst_treatment": "Taxable",
                            "item_name": "Test Item",
                            "cgst_amount": 9.0,
                            "sgst_amount": 9.0,
                            "igst_amount": 0.0,
                            "cess_amount": 0.0,
                            "cess_non_advol_amount": 0.0,
                        }
                    ),
                    frappe._dict(
                        {
                            "item_code": "ITEM-002",
                            "idx": 2,
                            "qty": 1.0,
                            "taxable_value": 50.0,
                            "gst_hsn_code": "84713090",
                            "uom": "Nos",
                            "stock_uom": "Nos",
                            "gst_treatment": "Taxable",
                            "item_name": "Other Item",
                            "cgst_amount": 4.5,
                            "sgst_amount": 4.5,
                            "igst_amount": 0.0,
                            "cess_amount": 0.0,
                            "cess_non_advol_amount": 0.0,
                        }
                    ),
                ],
            }
        )
        gst_data = GSTTransactionData(doc)
        grouped = gst_data.group_same_items()

        self.assertEqual(len(grouped), 2)

    # =========================================================================
    # validate_gst_tax_rate — module-level function
    # =========================================================================

    def test_validate_gst_tax_rate_valid_rate_does_not_throw(self):
        item = frappe._dict({"item_code": "TEST", "idx": 1})
        validate_gst_tax_rate(18.0, item)

    def test_validate_gst_tax_rate_zero_rate_does_not_throw(self):
        item = frappe._dict({"item_code": "TEST", "idx": 1})
        validate_gst_tax_rate(0.0, item)

    def test_validate_gst_tax_rate_invalid_rate_throws_error(self):
        item = frappe._dict({"item_code": "TEST", "idx": 1})
        with self.assertRaises(frappe.ValidationError):
            validate_gst_tax_rate(99.0, item)

    # =========================================================================
    # GSTTransactionData.set_address_gstin_map
    # =========================================================================

    def test_set_address_gstin_map_creates_mapping_from_doc_fields(self):
        doc = frappe._dict(
            {
                "doctype": "Sales Invoice",
                "is_reverse_charge": 0,
                "customer_name": "Test",
                "customer_address": "CUST-ADDR-001",
                "billing_address_gstin": "29AAAAA0000A1Z5",
                "company_address": "COMP-ADDR-001",
                "company_gstin": "29AAQCA8719H1ZC",
                "supplier_address": "SUPP-ADDR-001",
                "supplier_gstin": "24AAAAA0000A1Z5",
                "billing_address": "BILL-ADDR-001",
                "bill_from_address": "FROM-ADDR-001",
                "bill_from_gstin": "29AAAAA0000A1Z6",
                "bill_to_address": "TO-ADDR-001",
                "bill_to_gstin": "29AAAAA0000A1Z7",
            }
        )
        gst_data = GSTTransactionData(doc)
        gst_data.set_address_gstin_map()

        self.assertEqual(
            gst_data.address_gstin_map["CUST-ADDR-001"],
            "29AAAAA0000A1Z5",
        )
        self.assertEqual(
            gst_data.address_gstin_map["COMP-ADDR-001"],
            "29AAQCA8719H1ZC",
        )
        self.assertEqual(
            gst_data.address_gstin_map["SUPP-ADDR-001"],
            "24AAAAA0000A1Z5",
        )
        self.assertEqual(gst_data.address_gstin_map["BILL-ADDR-001"], "29AAQCA8719H1ZC")
        self.assertEqual(
            gst_data.address_gstin_map["FROM-ADDR-001"],
            "29AAAAA0000A1Z6",
        )
        self.assertEqual(
            gst_data.address_gstin_map["TO-ADDR-001"],
            "29AAAAA0000A1Z7",
        )

    def test_set_address_gstin_map_handles_missing_fields(self):
        doc = frappe._dict(
            {
                "doctype": "Sales Invoice",
                "is_reverse_charge": 0,
                "customer_name": "Test",
            }
        )
        gst_data = GSTTransactionData(doc)
        gst_data.set_address_gstin_map()

        for value in gst_data.address_gstin_map.values():
            self.assertIsNone(value)
