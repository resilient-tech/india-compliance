import frappe
from erpnext.controllers.accounts_controller import get_taxes_and_charges
from frappe.tests import IntegrationTestCase
from frappe.utils import now_datetime

from india_compliance.gst_india.overrides.test_transaction import create_cess_accounts

# Fixtures for all of these are declared in india_compliance/tests/test_records.json
TEST_LOCATION = "_Test Asset Movement Location"
TEST_TARGET_LOCATION = "_Test Asset Movement Target Location"
TEST_ASSET = "_Test Asset Movement Asset"
TEST_ASSET_VALUE = 100000


def get_test_asset(asset_name=TEST_ASSET):
    """Assets are auto-named, so look up the fixture by asset_name instead."""
    return frappe.db.get_value("Asset", {"asset_name": asset_name, "docstatus": 1}, "name")


COMPANY_ADDRESS = "_Test Indian Registered Company-Billing"
COMPANY_PARTY_ADDRESS = "_Test Registered Supplier-Billing"


def create_asset_movement(**data):
    data = frappe._dict(data)
    do_not_save = data.pop("do_not_save", False)
    asset_rows = data.pop("assets", None)
    extra_fields = data.pop("extra_fields", None) or {}

    doc = frappe.get_doc(
        {
            "doctype": "Asset Movement",
            "company": data.company or "_Test Indian Registered Company",
            "purpose": data.purpose or "Transfer",
            "transaction_date": data.transaction_date or now_datetime(),
            **extra_fields,
        }
    )

    for row in asset_rows or [{}]:
        row = frappe._dict(row)
        asset = row.asset or data.asset
        item_data = {
            "asset": asset,
            "target_location": row.target_location
            or (
                TEST_LOCATION
                if frappe.db.get_value("Asset", asset, "location") == TEST_TARGET_LOCATION
                else TEST_TARGET_LOCATION
            ),
        }
        if row.taxable_value is not None:
            item_data["taxable_value"] = row.taxable_value
        if row.item_tax_template:
            item_data["item_tax_template"] = row.item_tax_template

        doc.append("assets", item_data)

    # userGstin is Bill To on a Receipt (inward), Bill From otherwise.
    if doc.purpose == "Receipt":
        default_bill_from, default_bill_to = COMPANY_PARTY_ADDRESS, COMPANY_ADDRESS
    else:
        default_bill_from, default_bill_to = COMPANY_ADDRESS, COMPANY_PARTY_ADDRESS

    doc.bill_from_address = data.bill_from_address if "bill_from_address" in data else default_bill_from
    doc.bill_to_address = data.bill_to_address if "bill_to_address" in data else default_bill_to

    for field in ("ship_from_address", "ship_to_address"):
        if field in data:
            doc.set(field, data.get(field))

    if do_not_save:
        return doc

    doc.insert()

    return doc


class TestAssetMovementGST(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        create_cess_accounts()

        cls.asset = get_test_asset()

        settings = {
            "enable_api": 1,
            "enable_e_waybill": 1,
            "enable_e_waybill_from_asset_movement": 1,
        }
        # leaking these would affect every later test module
        cls.addClassCleanup(
            frappe.db.set_single_value,
            "GST Settings",
            {field: frappe.db.get_single_value("GST Settings", field) for field in settings},
        )
        frappe.db.set_single_value("GST Settings", settings)

    def test_taxable_value_defaults_to_asset_value_after_depreciation(self):
        doc = create_asset_movement(asset=self.asset)
        self.assertEqual(doc.assets[0].taxable_value, TEST_ASSET_VALUE)

        # a value the user entered is left alone
        doc = create_asset_movement(assets=[{"asset": self.asset, "taxable_value": 4200}])
        self.assertEqual(doc.assets[0].taxable_value, 4200)

    def test_gst_validations_skipped_without_taxes_or_addresses(self):
        """An Asset Movement that carries no GST intent must not be validated as one,
        so it stays usable for companies that never generate e-Waybills."""
        doc = create_asset_movement(
            asset=self.asset,
            bill_from_address=None,
            bill_to_address=None,
        )

        self.assertFalse(doc.taxes)
        self.assertFalse(doc.place_of_supply)
        # taxable_value is only defaulted for GST-relevant movements
        self.assertEqual(doc.assets[0].taxable_value, 0)

    def test_taxes_populate_from_template_and_flow_to_asset_rows(self):
        """Simulates fetching a Taxes and Charges Template's rows, for intra- and inter-state,
        along with the Item details the e-Waybill item payload needs from the Asset."""
        scenarios = (
            (
                "In-State",
                COMPANY_PARTY_ADDRESS,
                "Output GST In-state - _TIRC",
                {"cgst_amount": 900, "sgst_amount": 900, "igst_amount": 0},
            ),
            (
                "Out-State",
                "_Test Registered Supplier-Billing-3",  # Karnataka (29)
                "Output GST Out-state - _TIRC",
                {"cgst_amount": 0, "sgst_amount": 0, "igst_amount": 1800},
            ),
        )

        for tax_category, bill_to_address, taxes_and_charges, expected in scenarios:
            with self.subTest(tax_category=tax_category):
                doc = create_asset_movement(
                    assets=[
                        {
                            "asset": self.asset,
                            "taxable_value": 10000,
                            "item_tax_template": "GST 18% - _TIRC",
                        }
                    ],
                    bill_to_address=bill_to_address,
                    extra_fields={
                        "tax_category": tax_category,
                        "taxes_and_charges": taxes_and_charges,
                    },
                    do_not_save=True,
                )
                doc.set(
                    "taxes",
                    get_taxes_and_charges("Sales Taxes and Charges Template", taxes_and_charges),
                )
                doc.insert()

                self.assertEqual(doc.total_taxes, 1800)
                self.assertEqual(doc.base_grand_total, 11800)

                row = doc.assets[0]
                for fieldname, value in expected.items():
                    self.assertEqual(row.get(fieldname), value)

                # selecting an Asset fetches its Item details into the row
                self.assertEqual(row.item_code, frappe.db.get_value("Asset", self.asset, "item_code"))
                self.assertEqual(row.item_name, frappe.db.get_value("Asset", self.asset, "item_name"))
                self.assertEqual(row.qty, frappe.db.get_value("Asset", self.asset, "asset_quantity"))
                self.assertEqual(row.gst_hsn_code, "847130")
                self.assertEqual(row.uom, "Nos")
