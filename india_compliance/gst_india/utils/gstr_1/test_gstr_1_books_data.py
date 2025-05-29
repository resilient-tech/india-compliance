import frappe
from frappe.tests import IntegrationTestCase, change_settings
from frappe.utils import getdate

from india_compliance.gst_india.overrides.company import create_default_company_account
from india_compliance.gst_india.utils.gstr_1 import (
    GSTR1_SubCategory,
)
from india_compliance.gst_india.utils.gstr_1.gstr_1_json_map import GSTR1BooksData
from india_compliance.gst_india.utils.tests import (
    _append_taxes,
    append_item,
    create_sales_invoice,
)

today = getdate()
month = today.strftime("%B")
year = today.year

FILTERS = frappe._dict(
    {
        "company": "_Test Indian Registered Company",
        "company_gstin": "24AAQCA8719H1ZC",
        "year": year,
        "month_or_quarter": month,
        "from_date": today,
        "to_date": today,
    }
)


class TestGSTR1BooksData(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        # setup cess account
        cls.cess_account = setup_cess_account()

    def test_b2b_regular_transaction(self):
        si = create_sales_invoice(
            customer="_Test Registered Customer", is_in_state=True, do_not_submit=True
        )
        append_item(si, "Test Item", rate=100.0, qty=1.0)
        _append_taxes(si, "CESS", rate=2)
        si.save()
        si.submit()

        data = GSTR1BooksData(filters=FILTERS).prepare_mapped_data()
        self.assertDictEq(
            {
                "transaction_type": "Invoice",
                "document_value": 120.0,
                "place_of_supply": "24-Gujarat",
                "reverse_charge": "N",
                "document_type": "Regular B2B",
                "total_taxable_value": 100.0,
                "total_igst_amount": 0.0,
                "total_cgst_amount": 9.0,
                "total_sgst_amount": 9.0,
                "total_cess_amount": 2.0,
                "items": [
                    {
                        "taxable_value": 100.0,
                        "igst_amount": 0.0,
                        "cgst_amount": 9.0,
                        "sgst_amount": 9.0,
                        "cess_amount": 2.0,
                        "tax_rate": 18.0,
                    }
                ],
            },
            data[GSTR1_SubCategory.B2B_REGULAR.value][si.name],
        )

    def test_b2b_regular_transaction_with_gst_inclusive_price(self):
        si = create_sales_invoice(
            customer="_Test Registered Customer", do_not_submit=True
        )
        _append_taxes(si, ["CGST", "SGST"], included_in_print_rate=True)
        _append_taxes(si, "CESS", rate=2, included_in_print_rate=True)
        si.save()
        si.submit()

        data = GSTR1BooksData(filters=FILTERS).prepare_mapped_data()
        self.assertDictEq(
            {
                "transaction_type": "Invoice",
                "document_value": 100.0,
                "place_of_supply": "24-Gujarat",
                "reverse_charge": "N",
                "document_type": "Regular B2B",
                "total_taxable_value": 83.33,
                "total_igst_amount": 0.0,
                "total_cgst_amount": 7.5,
                "total_sgst_amount": 7.5,
                "total_cess_amount": 1.67,
                "items": [
                    {
                        "taxable_value": 83.33,
                        "igst_amount": 0.0,
                        "cgst_amount": 7.5,
                        "sgst_amount": 7.5,
                        "cess_amount": 1.67,
                        "tax_rate": 18.0,
                    }
                ],
            },
            data[GSTR1_SubCategory.B2B_REGULAR.value][si.name],
        )

    def test_b2b_rounding_adjustment(self):
        pass

    @change_settings("GST Settings", {"enable_reverse_charge_in_sales": 1})
    def test_b2b_rcm_transaction(self):
        si = create_sales_invoice(
            customer="_Test Registered Customer",
            is_reverse_charge=True,
            is_in_state=True,
            is_in_state_rcm=True,
        )

        data = GSTR1BooksData(filters=FILTERS).prepare_mapped_data()
        self.assertDictEq(
            {
                "transaction_type": "Invoice",
                "document_value": 100.0,  # Unchanged for RCM
                "reverse_charge": "Y",
                "document_type": "Regular B2B",
                "total_taxable_value": 100.0,
                "total_igst_amount": 0.0,
                "total_cgst_amount": 9.0,
                "total_sgst_amount": 9.0,
                "total_cess_amount": 0.0,
                "items": [
                    {
                        "taxable_value": 100.0,
                        "igst_amount": 0.0,
                        "cgst_amount": 9.0,
                        "sgst_amount": 9.0,
                        "cess_amount": 0.0,
                        "tax_rate": 18.0,
                    }
                ],
            },
            data[GSTR1_SubCategory.B2B_REVERSE_CHARGE.value][si.name],
        )

    @change_settings("GST Settings", {"enable_overseas_transactions": 1})
    def test_sez_without_tax(self):
        pass

    @change_settings("GST Settings", {"enable_overseas_transactions": 1})
    def test_sez_with_tax(self):
        pass

    @change_settings("GST Settings", {"enable_overseas_transactions": 1})
    def test_deemed_export_transaction(self):
        # Create a new address
        pass

    @change_settings("GST Settings", {"enable_overseas_transactions": 1})
    def test_export_without_tax(self):
        pass

    @change_settings("GST Settings", {"enable_overseas_transactions": 1})
    def test_export_with_tax(self):
        # Foreign Customer + IGST
        pass

    def test_b2cl_transaction(self):
        # Unregistered + Interstate + POS + Value > 1 L
        pass

    def test_cdnr_transaction(self):
        # Create B2B and CN from SI
        pass

    def test_cdnur_transaction(self):
        # Create Export and CN from SI
        pass

    def test_nil_exempt_transaction(self):
        # Create B2B (CGST) and B2C (IGST) Invoice
        pass

    def test_b2cs_transaction(self):
        # 3-4 transactions with different POS
        pass

    def test_hsn_summary_without_bifurcation(self):
        pass

    # change settings
    def test_hsn_summary_with_bifurcation(self):
        pass

    def test_document_issued_summary(self):
        pass

    def test_advance_received(self):
        pass

    def test_advance_adjusted(self):
        pass

    def test_quarterly_filing_data(self):
        pass

    def test_transaction_split_b2b_nil(self):
        # Create B2B with Taxable and Nil Items
        pass

    def assertDictEq(self, expected: dict, actual: dict):
        """
        Partial Comparision of Dict
        """
        for k, v in expected.items():
            if isinstance(v, dict):
                self.assertDictEq(v, actual.get(k, {}))

            if isinstance(v, list | tuple):
                for i, row in enumerate(v):
                    if isinstance(row, dict):
                        self.assertDictEq(row, v[i])

            self.assertEqual(v, actual.get(k))


def setup_cess_account(company="_Test Indian Registered Company"):
    # create cess account
    create_default_company_account(company, "Output Tax CESS", "Duties and Taxes")
    account = frappe.db.get_value(
        "Account",
        {"account_name": "Output Tax CESS", "company": company, "is_group": 0},
    )

    # update this to GST Settings
    gst_settings = frappe.get_doc("GST Settings")
    for row in gst_settings.gst_accounts:
        if row.company != company or row.account_type != "Output":
            continue

        row.cess_account = account
        break

    gst_settings.save()

    # update this to item tax templates
    item_templates = frappe.get_all(
        "Item Tax Template",
        {"company": company, "gst_treatment": "Taxable"},
        pluck="name",
    )

    for name in item_templates:
        template = frappe.get_doc("Item Tax Template", name)
        template.append("taxes", {"tax_type": account, "tax_rate": 2})
        template.save()

    return account
