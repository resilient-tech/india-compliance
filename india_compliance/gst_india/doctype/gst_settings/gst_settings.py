# Copyright (c) 2017, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt


import os

import frappe
from frappe import _
from frappe.contacts.doctype.contact.contact import get_default_contact
from frappe.model.document import Document
from frappe.utils import date_diff, get_url, nowdate


class EmailMissing(frappe.ValidationError): pass

class GSTSettings(Document):
	def onload(self):
		data = frappe._dict()
		data.total_addresses = frappe.db.sql('''select count(*) from tabAddress where country = "India"''')
		data.total_addresses_with_gstin = frappe.db.sql('''select distinct count(*)
			from tabAddress where country = "India" and ifnull(gstin, '')!='' ''')
		self.set_onload('data', data)

	def validate(self):
		# Validate duplicate accounts
		self.validate_duplicate_accounts()

	def validate_duplicate_accounts(self):
		account_list = []
		for account in self.get('gst_accounts'):
			for fieldname in ['cgst_account', 'sgst_account', 'igst_account', 'cess_account']:
				if account.get(fieldname) in account_list:
					frappe.throw(_("Account {0} appears multiple times").format(
						frappe.bold(account.get(fieldname))))

				if account.get(fieldname):
					account_list.append(account.get(fieldname))
