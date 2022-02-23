import re
import frappe


PAN_NUMBER_FORMAT = re.compile("[A-Z]{5}[0-9]{4}[A-Z]{1}")


def validate_pan_for_india(doc, method):
	if doc.get('country') != 'India' or not doc.get('pan'):
		return

	if not PAN_NUMBER_FORMAT.match(doc.pan):
		frappe.throw(_("Invalid PAN No. The input you've entered doesn't match the format of PAN."))
