import re

import frappe
from erpnext.assets.doctype.asset.asset import get_asset_value_after_depreciation
from frappe.tests import IntegrationTestCase, change_settings
from frappe.utils import flt, now_datetime

from india_compliance.gst_india.overrides.test_transaction import create_cess_accounts
from india_compliance.gst_india.overrides.transaction import ItemGSTDetails

# Fixtures for all of these are declared in india_compliance/tests/test_records.json
TEST_FIXED_ASSET_ITEM = "_Test Asset Movement Fixed Asset"
TEST_LOCATION = "_Test Asset Movement Location"
TEST_TARGET_LOCATION = "_Test Asset Movement Target Location"
TEST_ASSET = "_Test Asset Movement Asset"
TEST_ASSET_QTY_4 = "_Test Asset Movement Asset Qty 4"
TEST_ASSET_UNREGISTERED = "_Test Asset Movement Asset Unregistered"
TEST_ASSET_VALUE = 100000


def get_test_asset(asset_name=TEST_ASSET):
    """Return the name of a submitted Asset fixture, looked up by its asset_name.

    Assets are auto-named from a naming series, so the fixtures can't be referenced
    by name directly.
    """
    return frappe.db.get_value("Asset", {"asset_name": asset_name, "docstatus": 1}, "name")


def create_asset_movement(**data):
    data = frappe._dict(data)
    do_not_save = data.pop("do_not_save", False)
    submit = data.pop("submit", False)
    asset_rows = data.pop("assets", None)

    doc = frappe.get_doc(
        {
            "doctype": "Asset Movement",
            "company": data.company or "_Test Indian Registered Company",
            "purpose": data.purpose or "Transfer",
            "transaction_date": data.transaction_date or now_datetime(),
        }
    )

    for row in asset_rows or [{}]:
        row = frappe._dict(row)
        item_data = {
            "asset": row.asset or data.asset,
            "target_location": row.get("target_location", TEST_TARGET_LOCATION),
        }
        if row.taxable_value is not None:
            item_data["taxable_value"] = row.taxable_value

        doc.append("assets", item_data)

    doc.bill_from_address = (
        data.bill_from_address if "bill_from_address" in data else "_Test Indian Registered Company-Billing"
    )
    doc.bill_to_address = (
        data.bill_to_address if "bill_to_address" in data else "_Test Registered Supplier-Billing"
    )

    if do_not_save:
        return doc

    doc.insert()

    if submit:
        doc.submit()

    return doc


def _append_output_taxes(doc, accounts, company_abbr="_TIRC", rate=9, charge_type="On Net Total", **kwargs):
    """Local replacement for the shared `_append_taxes`, which defaults to Input Tax
    accounts for any doctype outside SALES_DOCTYPES. An Asset Movement is validated
    as an outward (sales-side) supply and needs Output accounts."""
    if isinstance(accounts, str):
        accounts = [accounts]

    for account in accounts:
        doc.append(
            "taxes",
            {
                "charge_type": charge_type,
                "account_head": f"Output Tax {account} - {company_abbr}",
                "description": account,
                "rate": rate,
                "cost_center": f"Main - {company_abbr}",
                **kwargs,
            },
        )


class TestAssetMovementGST(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        create_cess_accounts()

        cls.asset = get_test_asset()
        cls.asset_qty_4 = get_test_asset(TEST_ASSET_QTY_4)

        frappe.db.set_single_value(
            "GST Settings",
            {
                "enable_api": 1,
                "enable_e_waybill": 1,
                "enable_e_waybill_from_asset_movement": 1,
            },
        )

    # Taxable Value

    def test_taxable_value_defaults_to_wdv(self):
        doc = create_asset_movement(asset=self.asset)
        self.assertEqual(
            doc.assets[0].taxable_value,
            flt(
                get_asset_value_after_depreciation(self.asset),
                doc.assets[0].precision("taxable_value"),
            ),
        )

    def test_user_entered_taxable_value_survives(self):
        doc = create_asset_movement(assets=[{"asset": self.asset, "taxable_value": 5000}])
        self.assertEqual(doc.assets[0].taxable_value, 5000)

        doc.save()
        self.assertEqual(doc.assets[0].taxable_value, 5000)

    # Tax Calculation

    def test_intra_state_taxes_and_totals(self):
        doc = create_asset_movement(
            assets=[{"asset": self.asset, "taxable_value": 10000}],
            do_not_save=True,
        )
        _append_output_taxes(doc, ["CGST", "SGST"], rate=9)
        doc.insert()

        self.assertEqual(doc.total_taxes, 1800)
        self.assertEqual(doc.base_grand_total, 11800)
        self.assertEqual(doc.assets[0].cgst_rate, 9)
        self.assertEqual(doc.assets[0].cgst_amount, 900)
        self.assertEqual(doc.assets[0].sgst_rate, 9)
        self.assertEqual(doc.assets[0].sgst_amount, 900)

    def test_taxes_and_totals_persist_after_reload(self):
        """Regression: taxable_value / GST amounts are only computed in validate, so
        they must exist as real fields on Asset Movement Item to survive a save."""
        doc = create_asset_movement(
            assets=[{"asset": self.asset, "taxable_value": 10000}],
            do_not_save=True,
        )
        _append_output_taxes(doc, ["CGST", "SGST"], rate=9)
        doc.insert()

        doc.reload()

        self.assertEqual(doc.assets[0].taxable_value, 10000)
        self.assertEqual(doc.assets[0].cgst_amount, 900)
        self.assertEqual(doc.assets[0].sgst_amount, 900)
        self.assertEqual(doc.total_taxes, 1800)
        self.assertEqual(doc.base_grand_total, 11800)

    def test_hsn_and_uom_fetched_from_asset_item(self):
        """Both are required for the e-Waybill item payload."""
        doc = create_asset_movement(asset=self.asset)

        self.assertEqual(doc.assets[0].gst_hsn_code, "847130")
        self.assertEqual(doc.assets[0].uom, "Nos")

    def test_inter_state_supply_accepts_igst(self):
        doc = create_asset_movement(
            assets=[{"asset": self.asset, "taxable_value": 10000}],
            bill_to_address="_Test Registered Supplier-Billing-3",  # Karnataka (29)
            do_not_save=True,
        )
        _append_output_taxes(doc, "IGST", rate=18)
        doc.insert()

        self.assertEqual(doc.place_of_supply[:2], "29")
        self.assertEqual(doc.total_taxes, 1800)
        self.assertEqual(doc.assets[0].igst_rate, 18)
        self.assertEqual(doc.assets[0].igst_amount, 1800)

    def test_inter_state_supply_rejects_cgst_sgst(self):
        doc = create_asset_movement(
            assets=[{"asset": self.asset, "taxable_value": 10000}],
            bill_to_address="_Test Registered Supplier-Billing-3",  # Karnataka (29)
            do_not_save=True,
        )
        _append_output_taxes(doc, ["CGST", "SGST"], rate=9)

        self.assertRaisesRegex(
            frappe.ValidationError,
            "Cannot charge CGST/SGST for inter-state supplies",
            doc.insert,
        )

    def test_cess_non_advol_uses_asset_quantity(self):
        doc = create_asset_movement(
            assets=[{"asset": self.asset_qty_4, "taxable_value": 10000}],
            do_not_save=True,
        )
        _append_output_taxes(doc, ["CGST", "SGST"], rate=9)
        _append_output_taxes(doc, "Cess Non Advol", rate=10, charge_type="On Item Quantity")
        doc.insert()

        self.assertEqual(doc.assets[0].qty, 4)
        self.assertEqual(doc.assets[0].cess_non_advol_rate, 10)
        self.assertEqual(doc.assets[0].cess_non_advol_amount, 40)

    def test_item_tax_template_defaulted(self):
        doc = create_asset_movement(asset=self.asset, do_not_save=True)
        _append_output_taxes(doc, ["CGST", "SGST"], rate=9)
        doc.insert()

        self.assertEqual(doc.assets[0].item_tax_template, "GST 18% - _TIRC")
        self.assertEqual(doc.assets[0].gst_treatment, "Taxable")

    def test_gst_treatment_is_nil_rated_without_taxes(self):
        doc = create_asset_movement(asset=self.asset)

        self.assertEqual(doc.assets[0].item_tax_template, "GST 18% - _TIRC")
        self.assertEqual(doc.assets[0].gst_treatment, "Nil-Rated")

    def test_set_tax_amount_precisions_for_asset_movement(self):
        """Direct regression test: get_field("items") on Asset Movement used to
        return None, crashing with AttributeError on `.options`."""
        details = ItemGSTDetails()
        details.set_tax_amount_precisions("Asset Movement")
        self.assertIn("cgst_amount", details.precision)

    # Validations

    def test_plain_asset_movement_saves(self):
        """No addresses, no taxes: GST validations must not fire for internal movements."""
        doc = create_asset_movement(
            asset=self.asset,
            bill_from_address=None,
            bill_to_address=None,
        )
        self.assertEqual(doc.total_taxes, 0)

    def test_missing_bill_from_address(self):
        doc = create_asset_movement(
            asset=self.asset,
            bill_from_address=None,
            do_not_save=True,
        )

        self.assertRaisesRegex(
            frappe.ValidationError,
            re.compile(r"(to ensure Company GSTIN is fetched in the transaction.$)"),
            doc.insert,
        )

    def test_same_bill_from_and_bill_to_gstin_allowed(self):
        """The company moving its own asset between locations may share a GSTIN
        between Bill From and Bill To; unlike Stock Entry / Subcontracting, this
        must not be rejected."""
        doc = create_asset_movement(
            assets=[{"asset": self.asset, "taxable_value": 10000}],
            bill_to_address="_Test Indian Registered Company-Billing",
            do_not_save=True,
        )
        _append_output_taxes(doc, ["CGST", "SGST"], rate=9)
        doc.insert()

        self.assertEqual(doc.total_taxes, 1800)

    def test_for_unregistered_company(self):
        asset = get_test_asset(TEST_ASSET_UNREGISTERED)
        doc = create_asset_movement(
            asset=asset,
            company="_Test Indian Unregistered Company",
            bill_from_address="_Test Indian Unregistered Company-Billing",
            bill_to_address="_Test Unregistered Supplier-Billing",
        )
        self.assertEqual(doc.total_taxes, 0.0)

    # Settings

    @change_settings("GST Settings", {"enable_e_waybill_from_asset_movement": 0})
    def test_taxes_cleared_when_disabled(self):
        doc = create_asset_movement(
            assets=[{"asset": self.asset, "taxable_value": 10000}],
            do_not_save=True,
        )
        _append_output_taxes(doc, ["CGST", "SGST"], rate=9)
        doc.insert()

        self.assertEqual(doc.taxes, [])
        self.assertEqual(doc.taxes_and_charges, "")

        # Totals are cleared along with the taxes, not left over from validate
        self.assertEqual(doc.total_taxes, 0)
        self.assertEqual(doc.base_grand_total, 10000)

        doc.reload()
        self.assertEqual(doc.total_taxes, 0)
        self.assertEqual(doc.base_grand_total, 10000)
