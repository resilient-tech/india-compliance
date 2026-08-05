import frappe
from erpnext.controllers.accounts_controller import get_taxes_and_charges
from frappe.tests import IntegrationTestCase, change_settings
from frappe.utils import now_datetime

from india_compliance.exceptions import NotApplicableError
from india_compliance.gst_india.overrides.test_transaction import create_cess_accounts
from india_compliance.gst_india.utils import load_doc
from india_compliance.gst_india.utils.e_waybill import EWaybillData, update_transaction

# Fixtures for all of these are declared in india_compliance/tests/test_records.json
TEST_FIXED_ASSET_ITEM = "_Test Asset Movement Fixed Asset"
TEST_LOCATION = "_Test Asset Movement Location"
TEST_TARGET_LOCATION = "_Test Asset Movement Target Location"
TEST_ASSET = "_Test Asset Movement Asset"
TEST_ASSET_VALUE = 100000


def get_test_asset(asset_name=TEST_ASSET):
    """Assets are auto-named, so look up the fixture by asset_name instead."""
    return frappe.db.get_value("Asset", {"asset_name": asset_name, "docstatus": 1}, "name")


COMPANY_ADDRESS = "_Test Indian Registered Company-Billing"
COMPANY_PARTY_ADDRESS = "_Test Registered Supplier-Billing"

# Shared with TestEWaybill.test_e_waybill_for_asset_movement so both stay in sync.
_ASSET_MOVEMENT_TEST_VALUES = frappe.get_file_json(
    frappe.get_app_path("india_compliance", "gst_india", "data", "test_e_waybill.json")
)["asset_movement"]["values"]

TRANSPORTER_DETAILS = {
    key: _ASSET_MOVEMENT_TEST_VALUES[key]
    for key in ("mode_of_transport", "vehicle_no", "gst_vehicle_type", "distance")
}


def create_asset_movement(**data):
    data = frappe._dict(data)
    do_not_save = data.pop("do_not_save", False)
    submit = data.pop("submit", False)
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
        item_data = {
            "asset": row.asset or data.asset,
            "target_location": row.get("target_location", TEST_TARGET_LOCATION),
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

    if submit:
        doc.submit()

    return doc


def _append_output_taxes(doc, accounts, company_abbr="_TIRC", rate=9, charge_type="On Net Total", **kwargs):
    """Unlike the shared `_append_taxes`, defaults to Output accounts, since Asset
    Movement validates as an outward (sales-side) supply."""
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

        frappe.db.set_single_value(
            "GST Settings",
            {
                "enable_api": 1,
                "enable_e_waybill": 1,
                "enable_e_waybill_from_asset_movement": 1,
            },
        )

    def test_taxes_populate_from_template_and_flow_to_asset_rows(self):
        """Simulates fetching a Taxes and Charges Template's rows, for intra- and inter-state."""
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

    def test_asset_details_fetched_into_assets_table(self):
        """Selecting an Asset fetches the Item details needed for the e-Waybill item payload."""
        doc = create_asset_movement(asset=self.asset)
        row = doc.assets[0]

        self.assertEqual(row.item_code, frappe.db.get_value("Asset", self.asset, "item_code"))
        self.assertEqual(row.item_name, frappe.db.get_value("Asset", self.asset, "item_name"))
        self.assertEqual(row.qty, frappe.db.get_value("Asset", self.asset, "asset_quantity"))
        self.assertEqual(row.gst_hsn_code, "847130")
        self.assertEqual(row.uom, "Nos")


class TestAssetMovementEWaybill(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        create_cess_accounts()

        cls.asset = get_test_asset()

        # asserted against the real address GSTINs, so sandbox substitution must be off
        cls._sandbox_mode = frappe.db.get_single_value("GST Settings", "sandbox_mode")

        frappe.db.set_single_value(
            "GST Settings",
            {
                "enable_api": 1,
                "enable_e_waybill": 1,
                "enable_e_waybill_from_asset_movement": 1,
                "sandbox_mode": 0,
            },
        )

    @classmethod
    def tearDownClass(cls):
        frappe.db.set_single_value("GST Settings", "sandbox_mode", cls._sandbox_mode)
        super().tearDownClass()

    def create_asset_movement_for_e_waybill(self, **kwargs):
        """Reloaded through load_doc so the onload aliases the e-Waybill mapper relies on are applied."""
        kwargs.setdefault(
            "assets",
            [{"asset": self.asset, "taxable_value": 10000, "target_location": self.next_location()}],
        )
        kwargs.setdefault("extra_fields", TRANSPORTER_DETAILS)
        taxes = kwargs.pop("taxes", ["CGST", "SGST"])
        rate = kwargs.pop("rate", 9)

        doc = create_asset_movement(do_not_save=True, **kwargs)
        _append_output_taxes(doc, taxes, rate=rate)
        doc.insert()
        doc.submit()

        return load_doc("Asset Movement", doc.name, "submit")

    def test_outward_e_waybill_data(self):
        """Transfer: the company is Bill From, so userGstin must match fromGstin (NIC error 359)."""
        # same GSTIN on both sides, since NIC only allows "For Own Use" when they match
        doc = self.create_asset_movement_for_e_waybill(bill_to_address=COMPANY_ADDRESS)
        update_transaction(doc, frappe._dict(self.sub_supply_values()))

        data = EWaybillData(doc).get_data()

        self.assertEqual(data["supplyType"], "O")
        self.assertEqual(data["subSupplyType"], 5)  # For Own Use
        self.assertEqual(data["docType"], "CHL")
        self.assertEqual(data["docNo"], doc.name)

        self.assertEqual(data["userGstin"], doc.bill_from_gstin)
        self.assertEqual(data["fromGstin"], doc.bill_from_gstin)
        self.assertEqual(data["toGstin"], doc.bill_to_gstin)
        self.assertEqual(data["fromGstin"], data["toGstin"])
        self.assertEqual(data["fromTrdName"], doc.company)
        self.assertEqual(data["transactionType"], 1)

        self.assertEqual(data["totalValue"], 10000)
        self.assertEqual(data["cgstValue"], 900)
        self.assertEqual(data["sgstValue"], 900)
        self.assertEqual(data["igstValue"], 0)
        self.assertEqual(data["mainHsnCode"], "847130")

        self.assertEqual(len(data["itemList"]), 1)
        item = data["itemList"][0]
        self.assertEqual(item["hsnCode"], "847130")
        self.assertEqual(item["qtyUnit"], "NOS")
        self.assertEqual(item["quantity"], 1)
        self.assertEqual(item["taxableAmount"], 10000)
        self.assertEqual(item["cgstRate"], 9)
        self.assertEqual(item["sgstRate"], 9)

    def test_inward_e_waybill_data_for_receipt(self):
        """Receipt: the company is Bill To, so userGstin must match toGstin (NIC error 360)."""
        doc = self.create_asset_movement_for_e_waybill(purpose="Receipt", bill_from_address=COMPANY_ADDRESS)
        update_transaction(doc, frappe._dict(self.sub_supply_values()))

        data = EWaybillData(doc).get_data()

        self.assertEqual(data["supplyType"], "I")
        self.assertEqual(data["subSupplyType"], 5)  # For Own Use

        self.assertEqual(data["userGstin"], doc.bill_to_gstin)
        self.assertEqual(data["toGstin"], doc.bill_to_gstin)
        self.assertEqual(data["fromGstin"], doc.bill_from_gstin)
        self.assertEqual(data["fromGstin"], data["toGstin"])
        self.assertEqual(
            data["userGstin"],
            frappe.db.get_value("Address", COMPANY_ADDRESS, "gstin"),
        )

        # the company name labels Bill To, since the company is the recipient on a Receipt
        self.assertEqual(data["toTrdName"], doc.company)

    def test_receipt_requires_registered_bill_to(self):
        """On a Receipt the company is Bill To, so it cannot be Unregistered."""
        self.assertRaisesRegex(
            frappe.ValidationError,
            "Bill To GSTIN.*mandatory field",
            self.create_asset_movement_for_e_waybill,
            purpose="Receipt",
            bill_to_address="_Test Unregistered Supplier-Billing",
        )

    def test_transaction_type_when_ship_to_differs(self):
        doc = self.create_asset_movement_for_e_waybill(
            ship_to_address="_Test Registered Customer Warehouse-Shipping"
        )
        update_transaction(doc, frappe._dict(self.sub_supply_values()))

        data = EWaybillData(doc).get_data()

        self.assertEqual(data["transactionType"], 2)  # Bill To - Ship To

    def test_e_waybill_not_applicable_when_setting_disabled(self):
        doc = self.create_asset_movement_for_e_waybill()

        with change_settings("GST Settings", {"enable_e_waybill": 0}):
            self.assertRaises(NotApplicableError, EWaybillData, doc)

    @change_settings("GST Settings", {"sandbox_mode": 1})
    def test_sandbox_gstin_substitution(self):
        """REGISTERED_GSTIN must land on whichever side is the company, since userGstin is force-set to it."""
        scenarios = (
            ("Transfer", "Job Work", "fromGstin"),  # differing GSTINs, so "For Own Use" doesn't apply
            ("Receipt", "Job Work Returns", "toGstin"),
        )
        for purpose, sub_supply_type, company_side in scenarios:
            with self.subTest(purpose=purpose):
                doc = self.create_asset_movement_for_e_waybill(purpose=purpose)
                update_transaction(doc, frappe._dict(self.sub_supply_values(sub_supply_type=sub_supply_type)))

                data = EWaybillData(doc).get_data()

                self.assertEqual(data[company_side], data["userGstin"])
                self.assertNotEqual(data["fromGstin"], data["toGstin"])

    def next_location(self):
        """ERPNext rejects a Source and Target Location that are the same."""
        current = frappe.db.get_value("Asset", self.asset, "location")
        return TEST_LOCATION if current == TEST_TARGET_LOCATION else TEST_TARGET_LOCATION

    @staticmethod
    def sub_supply_values(**overrides):
        """The Generate dialog values, as update_transaction receives them."""
        return {**_ASSET_MOVEMENT_TEST_VALUES, **overrides}
