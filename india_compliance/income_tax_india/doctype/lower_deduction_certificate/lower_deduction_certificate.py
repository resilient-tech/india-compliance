# Copyright (c) 2020, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt


import frappe
from erpnext.accounts.utils import get_fiscal_year
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_link_to_form, getdate


class LowerDeductionCertificate(Document):
    def validate(self):
        self.validate_dates()
        self.validate_supplier_against_tax_category()

    def validate_dates(self):
        if getdate(self.valid_upto) < getdate(self.valid_from):
            frappe.throw(_("Valid Upto date cannot be before Valid From date"))

        fiscal_year = get_fiscal_year(fiscal_year=self.fiscal_year, as_dict=True)

        if not (
            fiscal_year.year_start_date
            <= getdate(self.valid_from)
            <= fiscal_year.year_end_date
        ):
            frappe.throw(
                _("Valid From date not in Fiscal Year {0}").format(
                    frappe.bold(self.fiscal_year)
                )
            )

        if not (
            fiscal_year.year_start_date
            <= getdate(self.valid_upto)
            <= fiscal_year.year_end_date
        ):
            frappe.throw(
                _("Valid Upto date not in Fiscal Year {0}").format(
                    frappe.bold(self.fiscal_year)
                )
            )

    def validate_supplier_against_tax_category(self):
        duplicate_certificate = frappe.db.get_value(
            "Lower Deduction Certificate",
            {
                "supplier": self.supplier,
                "tax_withholding_category": self.tax_withholding_category,
                "name": ("!=", self.name),
            },
            ["name", "valid_from", "valid_upto"],
            as_dict=True,
        )
        if duplicate_certificate and self.are_dates_overlapping(duplicate_certificate):
            certificate_link = get_link_to_form(
                "Lower Deduction Certificate", duplicate_certificate.name
            )
            frappe.throw(
                _(
                    "There is already a valid Lower Deduction Certificate {0} for Supplier {1} against category {2} for this time period."
                ).format(
                    certificate_link,
                    frappe.bold(self.supplier),
                    frappe.bold(self.tax_withholding_category),
                )
            )

    def are_dates_overlapping(self, duplicate_certificate):
        valid_from = duplicate_certificate.valid_from
        valid_upto = duplicate_certificate.valid_upto
        if valid_from <= getdate(self.valid_from) <= valid_upto:
            return True
        elif valid_from <= getdate(self.valid_upto) <= valid_upto:
            return True
        elif getdate(self.valid_from) <= valid_from and valid_upto <= getdate(
            self.valid_upto
        ):
            return True
        return False
