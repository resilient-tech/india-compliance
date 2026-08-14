import frappe
from erpnext.controllers.accounts_controller import get_taxes_and_charges
from frappe.desk.form.load import run_onload
from frappe.tests import IntegrationTestCase
from frappe.utils import now_datetime

from india_compliance.gst_india.overrides.test_transaction import create_cess_accounts
from india_compliance.gst_india.overrides.transaction import get_gst_details
from india_compliance.gst_india.utils import get_place_of_supply

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
UNREGISTERED_ADDRESS = "_Test Unregistered Customer-1-Billing"


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

    def test_taxable_value_always_follows_the_asset(self):
        doc = create_asset_movement(asset=self.asset)
        self.assertEqual(doc.assets[0].taxable_value, TEST_ASSET_VALUE)

        # refetched on every save, so it cannot drift from the Asset
        doc = create_asset_movement(assets=[{"asset": self.asset, "taxable_value": 4200}])
        self.assertEqual(doc.assets[0].taxable_value, TEST_ASSET_VALUE)

    def test_item_tax_template_is_resolved_from_the_item(self):
        """The Asset carries no template of its own, so it comes off the Item, exactly as
        it does for a Stock Entry mapped from a Subcontracting Order."""
        doc = create_asset_movement(asset=self.asset)
        self.assertEqual(doc.assets[0].item_tax_template, "GST 18% - _TIRC")

        # a template chosen on the row is never overwritten
        doc = create_asset_movement(assets=[{"asset": self.asset, "item_tax_template": "GST 12% - _TIRC"}])
        self.assertEqual(doc.assets[0].item_tax_template, "GST 12% - _TIRC")

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
        # the Asset is not even looked up when GST is not in play
        self.assertEqual(doc.assets[0].taxable_value, 0)

    def test_taxes_populate_from_template_and_flow_to_asset_rows(self):
        """Simulates fetching a Taxes and Charges Template's rows, for intra- and inter-state,
        along with the Item details the e-Waybill item payload needs from the Asset."""
        scenarios = (
            (
                "In-State",
                COMPANY_PARTY_ADDRESS,
                "Output GST In-state - _TIRC",
                {"cgst_amount": 9000, "sgst_amount": 9000, "igst_amount": 0},
            ),
            (
                "Out-State",
                "_Test Registered Supplier-Billing-3",  # Karnataka (29)
                "Output GST Out-state - _TIRC",
                {"cgst_amount": 0, "sgst_amount": 0, "igst_amount": 18000},
            ),
        )

        for tax_category, bill_to_address, taxes_and_charges, expected in scenarios:
            with self.subTest(tax_category=tax_category):
                doc = create_asset_movement(
                    assets=[
                        {
                            "asset": self.asset,
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

                self.assertEqual(doc.total_taxes, 18000)
                self.assertEqual(doc.base_grand_total, TEST_ASSET_VALUE + 18000)

                row = doc.assets[0]
                for fieldname, value in expected.items():
                    self.assertEqual(row.get(fieldname), value)

                # selecting an Asset fetches its Item details into the row
                self.assertEqual(row.item_code, frappe.db.get_value("Asset", self.asset, "item_code"))
                self.assertEqual(row.item_name, frappe.db.get_value("Asset", self.asset, "item_name"))
                self.assertEqual(row.gst_hsn_code, "847130")
                self.assertEqual(row.qty, 1)
                self.assertEqual(row.uom, "Nos")

    def test_inward_movement_bills_the_company(self):
        """On a Receipt the company is billed to rather than from, and the e-Waybill is
        still generated under the company's GSTIN. Nothing else exercises inward."""
        company_gstin = frappe.db.get_value("Address", COMPANY_ADDRESS, "gstin")
        party_gstin = frappe.db.get_value("Address", COMPANY_PARTY_ADDRESS, "gstin")

        for purpose, bill_from, bill_to in (
            ("Transfer", company_gstin, party_gstin),
            ("Receipt", party_gstin, company_gstin),
        ):
            with self.subTest(purpose=purpose):
                doc = create_asset_movement(asset=self.asset, purpose=purpose)
                run_onload(doc)

                self.assertEqual(doc.bill_from_gstin, bill_from)
                self.assertEqual(doc.bill_to_gstin, bill_to)

                # whichever side it sits on, the company generates the e-Waybill
                self.assertEqual(doc.company_gstin, company_gstin)
                self.assertEqual(doc.supplier_gstin, party_gstin)
                self.assertEqual(doc.place_of_supply, "24-Gujarat")

    def test_gst_details_for_asset_movement(self):
        """Drive the whitelisted entry point the client uses, rather than planting taxes."""
        gst_details = get_gst_details(
            party_details=frappe._dict(
                doctype="Asset Movement",
                purpose="Transfer",
                bill_from_address=COMPANY_ADDRESS,
                bill_to_address=COMPANY_PARTY_ADDRESS,
                bill_from_gstin=frappe.db.get_value("Address", COMPANY_ADDRESS, "gstin"),
                bill_to_gstin=frappe.db.get_value("Address", COMPANY_PARTY_ADDRESS, "gstin"),
            ),
            doctype="Asset Movement",
            company="_Test Indian Registered Company",
            update_place_of_supply=True,
        )

        self.assertEqual(gst_details.get("place_of_supply"), "24-Gujarat")
        # Asset Movement charges Output GST, so it must resolve a *Sales* template
        self.assertTrue(gst_details.get("taxes_and_charges", "").startswith("Output GST"))

    def test_place_of_supply_falls_back_to_unregistered_bill_to_address(self):
        """A URP consignee has no GSTIN, so the state comes off its address instead."""
        party_details = frappe._dict(
            doctype="Asset Movement",
            bill_from_gstin=frappe.db.get_value("Address", COMPANY_ADDRESS, "gstin"),
            bill_to_gstin=None,
            bill_to_address=UNREGISTERED_ADDRESS,
        )

        expected = "{}-{}".format(
            *frappe.db.get_value("Address", UNREGISTERED_ADDRESS, ("gst_state_number", "gst_state"))
        )
        self.assertEqual(get_place_of_supply(party_details, "Asset Movement"), expected)
