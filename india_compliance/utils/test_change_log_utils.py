# Copyright (c) 2025, Resilient Tech and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import formatdate, getdate

from india_compliance.utils.change_log_utils import add_versions_in_bulk, update_docs


class TestUpdateDocs(IntegrationTestCase):
    def setUp(self):
        self.todos = [
            frappe.get_doc(
                {
                    "doctype": "ToDo",
                    "description": f"bulk update test {index}",
                    "priority": "Low",
                    "date": "2024-01-01",
                }
            ).insert()
            for index in range(3)
        ]

    def test_updates_documents_and_records_a_version_each(self):
        names = update_docs(
            "ToDo",
            {todo.name: {"priority": "High", "date": "2024-02-05"} for todo in self.todos},
            updater_reference={"doctype": "ToDo", "docname": self.todos[0].name},
        )

        self.assertEqual(sorted(names), sorted(todo.name for todo in self.todos))

        for todo in self.todos:
            self.assertEqual(
                frappe.db.get_value("ToDo", todo.name, ["priority", "date"], as_dict=True),
                {"priority": "High", "date": getdate("2024-02-05")},
            )

            # the cache must not keep serving what was there before
            self.assertEqual(frappe.get_cached_doc("ToDo", todo.name).priority, "High")

            data = self.get_version(todo.name)
            self.assertEqual(
                sorted(data["changed"]),
                sorted(
                    [
                        ["date", formatdate("2024-01-01"), formatdate("2024-02-05")],
                        ["priority", "Low", "High"],
                    ]
                ),
            )
            self.assertEqual(data["updater_reference"]["docname"], self.todos[0].name)

    def test_writes_nothing_where_the_value_already_matches(self):
        todo, unchanged = self.todos[0], self.todos[1]

        names = update_docs(
            "ToDo",
            {todo.name: {"priority": "High"}, unchanged.name: {"priority": unchanged.priority}},
        )

        self.assertEqual(names, [todo.name])
        self.assertIsNone(self.get_version(unchanged.name))

        # a date reported as a string is the same date as the one stored
        self.assertEqual(update_docs("ToDo", {todo.name: {"priority": "High"}}), [])

    def test_writes_no_version_when_it_is_ignored(self):
        todo = self.todos[0]

        self.assertEqual(
            update_docs("ToDo", {todo.name: {"priority": "High"}}, ignore_version=True), [todo.name]
        )

        self.assertEqual(frappe.db.get_value("ToDo", todo.name, "priority"), "High")
        self.assertIsNone(self.get_version(todo.name))

    def test_writes_no_version_for_a_doctype_that_does_not_track_changes(self):
        todo = self.todos[0]

        frappe.make_property_setter(
            {
                "doctype": "ToDo",
                "fieldname": None,
                "property": "track_changes",
                "value": 0,
                "property_type": "Check",
                "doctype_or_field": "DocType",
            },
            validate_fields_for_doctype=False,
        )
        # the class rolls back only at teardown, so the row must go before the next test
        self.addCleanup(frappe.clear_cache, doctype="ToDo")
        self.addCleanup(frappe.db.delete, "Property Setter", {"doc_type": "ToDo"})
        frappe.clear_cache(doctype="ToDo")

        self.assertEqual(update_docs("ToDo", {todo.name: {"priority": "High"}}), [todo.name])

        self.assertEqual(frappe.db.get_value("ToDo", todo.name, "priority"), "High")
        self.assertIsNone(self.get_version(todo.name))

    def test_records_a_version_for_a_write_made_elsewhere(self):
        """
        A caller that wrote with db.set_value records the change itself, since that
        write leaves no timeline entry behind.
        """
        todo = self.todos[0]
        old_values = {"priority": todo.priority}
        new_values = {"priority": "High"}

        frappe.db.set_value("ToDo", todo.name, new_values)
        add_versions_in_bulk(
            [("ToDo", todo.name, old_values, new_values)],
            updater_reference={"doctype": "ToDo", "docname": todo.name},
        )

        data = self.get_version(todo.name)
        self.assertEqual(data["changed"], [["priority", "Low", "High"]])
        self.assertEqual(data["updater_reference"]["docname"], todo.name)

    def test_is_blocked_for_a_field_that_is_not_the_callers_to_set(self):
        todo = self.todos[0]

        for new_values in ({"docstatus": 1}, {"owner": "test@example.com"}, {"not_a_field": "x"}):
            with self.assertRaises(frappe.ValidationError):
                update_docs("ToDo", {todo.name: new_values})

        self.assertEqual(
            frappe.db.get_value("ToDo", todo.name, ["docstatus", "owner"], as_dict=True),
            {"docstatus": 0, "owner": frappe.session.user},
        )

    def test_is_blocked_without_write_access(self):
        todo = self.todos[0]

        test_user = frappe.get_doc("User", "test@example.com")
        test_user.add_roles("Report Manager")
        self.addCleanup(test_user.remove_roles, "Report Manager")
        self.addCleanup(frappe.clear_cache, user=test_user.name)

        frappe.make_property_setter(
            {
                "doctype": "ToDo",
                "fieldname": "priority",
                "property": "permlevel",
                "value": 1,
                "property_type": "Int",
            },
            validate_fields_for_doctype=False,
        )
        # the class rolls back only at teardown, so the row must go before the next test
        self.addCleanup(frappe.clear_cache, doctype="ToDo")
        self.addCleanup(frappe.db.delete, "Property Setter", {"doc_type": "ToDo"})
        frappe.clear_cache(doctype="ToDo")

        with self.set_user(test_user.name):
            self.assertRaises(
                frappe.PermissionError,
                update_docs,
                "ToDo",
                {todo.name: {"priority": "High"}},
            )

        self.assertEqual(frappe.db.get_value("ToDo", todo.name, "priority"), "Low")
        self.assertIsNone(self.get_version(todo.name))

    def get_version(self, docname):
        data = frappe.db.get_value(
            "Version", {"ref_doctype": "ToDo", "docname": docname}, "data", order_by="creation desc"
        )

        return data and frappe.parse_json(data)
