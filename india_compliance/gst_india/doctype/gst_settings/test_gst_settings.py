# Copyright (c) 2018, Frappe Technologies Pvt. Ltd. and Contributors
# See license.txt

import unittest
import frappe


class TestGSTSettings(unittest.TestCase):
	def test_validate_multiple_accounts(self):
		gst_settings_doc = frappe.get_single("GST Settings")

		for account in gst_settings_doc.get('gst_accounts'):
			account.is_input_account = True
			account.is_output_account = True

		self.assertRaises(frappe.ValidationError, gst_settings_doc.save)



