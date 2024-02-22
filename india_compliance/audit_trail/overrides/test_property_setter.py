import re

import frappe
from frappe.tests.utils import FrappeTestCase


class TestPropertySetter(FrappeTestCase):
    def test_validate_property_setter_where_audit_trail_enabled_and_doc_is_protected(
        self,
    ):
        frappe.db.set_single_value("Accounts Settings", "enable_audit_trail", 1)
        doc = frappe.get_doc(
            "Property Setter",
            {
                "doctype_or_field": "DocType",
                "doc_type": "Purchase Invoice",
                "property": "track_changes",
            },
        )
        self.assertRaisesRegex(
            frappe.ValidationError,
            re.compile(r"^(Cannot change the Track Changes property for*)"),
            doc.save,
        )

        self.assertRaisesRegex(
            frappe.ValidationError,
            re.compile(r"^(Cannot change the Track Changes property for*)"),
            doc.delete,
        )
        frappe.db.set_single_value("Accounts Settings", "enable_audit_trail", 0)
        doc.delete()

    def test_validate_property_setter_where_audit_trail_enabled_and_doc_is_not_protected(
        self,
    ):
        frappe.db.set_single_value("Accounts Settings", "enable_audit_trail", 0)
        doc = frappe.get_doc(
            "Property Setter",
            {
                "doctype_or_field": "DocType",
                "doc_type": "Purchase Invoice",
                "property": "track_changes",
            },
        )
        doc.save()
        frappe.db.set_single_value("Accounts Settings", "enable_audit_trail", 1)
        doc.doc_type = "Address"
        self.assertRaisesRegex(
            frappe.ValidationError,
            re.compile(r"^(Cannot change the Track Changes property for*)"),
            doc.save,
        )

    def test_property_setter_where_frm_is_new_and_doc_not_protected(self):
        frappe.db.set_single_value("Accounts Settings", "enable_audit_trail", 1)
        doc = frappe.get_doc(
            "Property Setter",
            {
                "doctype_or_field": "DocField",
                "doc_type": "Purchase Receipt",
                "field_name": "in_words",
                "property": "print_hide",
                "value": 0,
            },
        )
        doc.save()
