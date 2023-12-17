import re

import frappe
from frappe.tests.utils import FrappeTestCase

from india_compliance.gst_india.overrides.transaction import get_valid_accounts

# Creation of Item tax template for indian and foreign company
# Validation of GST Rate


class TestTransaction(FrappeTestCase):
    def test_item_tax_template_for_foreign_company(self):
        doc = create_item_tax_template(
            company="_Test Foreign Company", gst_rate=0, gst_treatment="Exempt"
        )
        self.assertTrue(doc.gst_rate == 0)
        self.assertTrue(doc.gst_treatment == "Exempt")

    def test_item_tax_template_for_indian_company(self):
        doc = create_item_tax_template()
        self.assertTrue(doc.gst_rate == 18)
        self.assertTrue(doc.gst_treatment == "Taxable")

    def test_validate_zero_tax_options(self):
        doc = create_item_tax_template(gst_rate=0, do_not_save=True)
        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"^(GST Rate cannot be zero for.*)$"),
            doc.insert,
        )

    def test_validate_tax_rates(self):
        doc = create_item_tax_template(do_not_save=True)
        doc.gst_rate = 110

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"^(GST Rate should be between 0 and 100)$"),
            doc.insert,
        )

        doc.gst_rate = 18
        doc.taxes[1].tax_rate = 2

        self.assertRaisesRegex(
            frappe.exceptions.ValidationError,
            re.compile(r"^(Plese make sure account tax rates.*)$"),
            doc.save,
        )


def create_item_tax_template(**data):
    doc = frappe.new_doc("Item Tax Template")
    gst_rate = data.get("gst_rate") if data.get("gst_rate") is not None else 18
    doc.update(
        {
            "company": data.get("company") or "_Test Indian Registered Company",
            "title": frappe.generate_hash("", 10),
            "gst_treatment": data.get("gst_treatment") or "Taxable",
            "gst_rate": gst_rate,
        }
    )

    if data.get("taxes"):
        doc.extend("taxes", data.get("taxes"))

        return save_item_tax_template(doc, data)

    __, intra_state_accounts, inter_state_accounts = get_valid_accounts(
        doc.company, for_sales=True, for_purchase=True, throw=False
    )

    if not intra_state_accounts and not inter_state_accounts:
        intra_state_accounts = frappe.get_all(
            "Account",
            filters={
                "company": doc.company,
                "account_type": "Tax",
            },
            pluck="name",
        )

    for account in intra_state_accounts:
        doc.append(
            "taxes",
            {
                "tax_type": account,
                "tax_rate": gst_rate / 2,
            },
        )

    for account in inter_state_accounts:
        doc.append(
            "taxes",
            {
                "tax_type": account,
                "tax_rate": gst_rate,
            },
        )

    return save_item_tax_template(doc, data)


def save_item_tax_template(doc, data):
    if data.get("do_not_save"):
        return doc

    return doc.insert()
