# # Copyright (c) 2024, Frappe Technologies Pvt. Ltd. and contributors
# # For license information, please see license.txt

# import frappe
# from frappe.tests import IntegrationTestCase

# IGNORE_TEST_RECORD_DEPENDENCIES = [
#     "ISD Invoice",
# ]

# # Same PAN (AAQCA8719H), different registration numbers
# FROM_PARTY_GSTIN = "24AAQCA8719H1ZC"
# TO_PARTY_GSTIN = "24AAQCA8719H2ZB"
# DIFFERENT_PAN_GSTIN = "24AANFA2641L1ZF"


# def create_isd_invoice(**kwargs):
#     data = frappe._dict(kwargs)

#     isd_invoice = frappe.get_doc(
#         {
#             "doctype": "ISD Invoice",
#             "naming_series": "ISD-.YYYY.-.MM.-",
#             "from_party_gstin": data.from_party_gstin or FROM_PARTY_GSTIN,
#             "to_party_gstin": data.to_party_gstin or TO_PARTY_GSTIN,
#             "is_unregistered_branch": data.get("is_unregistered_branch", 0),
#             "is_credit_note": data.get("is_credit_note", 0),
#         }
#     )

#     if not data.do_not_save:
#         isd_invoice.insert()

#     return isd_invoice


# class TestISDInvoice(IntegrationTestCase):
#     def test_valid_gstin_passes_validation(self):
#         """Valid GSTINs with same PAN should pass validation"""
#         isd_invoice = create_isd_invoice(do_not_save=True)
#         isd_invoice.validate()

#     def test_invalid_from_party_gstin(self):
#         """Invalid from_party_gstin should throw validation error"""
#         with self.assertRaises(frappe.ValidationError):
#             create_isd_invoice(from_party_gstin="INVALID", do_not_save=True).validate()

#     def test_invalid_to_party_gstin(self):
#         """Invalid to_party_gstin should throw validation error"""
#         with self.assertRaises(frappe.ValidationError):
#             create_isd_invoice(to_party_gstin="INVALID", do_not_save=True).validate()

#     def test_missing_to_party_gstin_for_registered_branch(self):
#         """to_party_gstin is mandatory when is_unregistered_branch is 0"""
#         with self.assertRaises(frappe.ValidationError):
#             create_isd_invoice(
#                 to_party_gstin="", do_not_save=True
#             ).validate()

#     def test_unregistered_branch_skips_to_party_validation(self):
#         """to_party_gstin validation is skipped for unregistered branches"""
#         isd_invoice = create_isd_invoice(
#             is_unregistered_branch=1,
#             to_party_gstin="",
#             do_not_save=True,
#         )
#         isd_invoice.validate()

#     def test_same_from_and_to_gstin(self):
#         """from_party_gstin and to_party_gstin cannot be the same"""
#         with self.assertRaises(frappe.ValidationError):
#             create_isd_invoice(
#                 from_party_gstin=FROM_PARTY_GSTIN,
#                 to_party_gstin=FROM_PARTY_GSTIN,
#                 do_not_save=True,
#             ).validate()

#     def test_different_pan_throws_error(self):
#         """GSTINs with different PANs should throw validation error"""
#         with self.assertRaises(frappe.ValidationError):
#             create_isd_invoice(
#                 from_party_gstin=FROM_PARTY_GSTIN,
#                 to_party_gstin=DIFFERENT_PAN_GSTIN,
#                 do_not_save=True,
#             ).validate()
