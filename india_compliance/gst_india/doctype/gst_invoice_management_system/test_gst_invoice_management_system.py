# Copyright (c) 2024, Resilient Tech and Contributors
# See license.txt

import frappe
from frappe.tests import IntegrationTestCase, change_settings
from frappe.utils import add_to_date

from india_compliance.gst_india.doctype.gst_invoice_management_system import (
    PurchaseInvoice,
    _declared_from_books,
    defer_undeclarable_itc_reduction,
    set_declared_itc,
)
from india_compliance.gst_india.doctype.gst_invoice_management_system.gst_invoice_management_system import (
    IMSReconciler,
    get_data_for_upload,
    get_period_options,
    update_previous_ims_action,
)
from india_compliance.gst_india.doctype.gst_inward_supply.gst_inward_supply import (
    preserve_pending_itc_declaration,
)
from india_compliance.gst_india.doctype.purchase_reconciliation_tool.test_purchase_reconciliation_tool import (
    create_gst_inward_supply,
)
from india_compliance.gst_india.utils.api import create_integration_request
from india_compliance.gst_india.utils.gstr_2.ims import IMSB2B, IMSB2BCN
from india_compliance.gst_india.utils.itc_claim import (
    ITC_CLAIM_PERIOD_DEFERRED,
    update_gstr3b_filing_status,
)
from india_compliance.gst_india.utils.tests import create_purchase_invoice

EXTRA_TEST_RECORD_DEPENDENCIES = []
IGNORE_TEST_RECORD_DEPENDENCIES = []


class TestGSTInvoiceManagementSystem(IntegrationTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.gst_ims = frappe.get_doc(
            {
                "doctype": "GST Invoice Management System",
                "company": "_Test Indian Registered Company",
                "company_gstin": "24AAQCA8719H1ZC",
                "return_period": "122024",
            }
        )

        default_args = {
            "bill_date": "2024-12-11",
            "return_period_2b": "122024",
            "gen_date_2b": "2024-12-11",
        }

        create_gst_inward_supply(
            **default_args, bill_no="BILL-24-00001", previous_ims_action="No Action", action="Pending"
        )
        cls.invoice_name_1 = frappe.get_value("GST Inward Supply", {"bill_no": "BILL-24-00001"})

        create_gst_inward_supply(
            **default_args,
            bill_no="BILL-24-00002",
            previous_ims_action="Rejected",
            action="No Action",
            previous_action="Pending",
        )
        cls.invoice_name_2 = frappe.get_value("GST Inward Supply", {"bill_no": "BILL-24-00002"})

        cls.pinv = create_purchase_invoice(
            **{
                "bill_no": "BILL-24-00001",
                "bill_date": "2024-12-11",
                "items": [
                    {
                        "item_code": "_Test Trading Goods 1",
                        "qty": 1,
                    }
                ],
                "supplier": "_Test Registered Supplier",
                "supplier_gstin": "24AABCR6898M1ZN",
            }
        )

    def test_update_action(self):
        # Reconcile invoice with bill_no "BILL-24-00001"
        IMSReconciler().reconcile(
            frappe._dict(
                {
                    "company": self.gst_ims.company,
                    "company_gstin": self.gst_ims.company_gstin,
                }
            )
        )

        # Test matched invoice
        self.gst_ims.update_action((self.invoice_name_1,), "Rejected")
        ims_action, action, previous_action = frappe.get_all(
            "GST Inward Supply",
            filters={"name": self.invoice_name_1},
            fields=["ims_action", "action", "previous_action"],
            as_list=True,
        )[0]
        self.assertEqual(ims_action, "Rejected")
        self.assertEqual(action, "Pending")
        self.assertEqual(previous_action, "No Action")

        # Test unmatched invoice
        frappe.db.set_value("GST Inward Supply", self.invoice_name_1, "link_name", "")
        self.gst_ims.update_action((self.invoice_name_1,), "Rejected")
        ims_action, action, previous_action = frappe.get_all(
            "GST Inward Supply",
            filters={"name": self.invoice_name_1},
            fields=["ims_action", "action", "previous_action"],
            as_list=True,
        )[0]
        self.assertEqual(ims_action, "Rejected")
        self.assertEqual(action, "Ignore")
        self.assertEqual(previous_action, "Pending")

        # Test invoice with previous IMS Action "Rejected"
        self.gst_ims.update_action((self.invoice_name_2,), "No Action")
        ims_action, action, previous_action = frappe.get_all(
            "GST Inward Supply",
            filters={"name": self.invoice_name_2},
            fields=["ims_action", "action", "previous_action"],
            as_list=True,
        )[0]
        self.assertEqual(ims_action, "No Action")
        self.assertEqual(action, "Pending")
        self.assertEqual(previous_action, "Pending")

    def test_data_for_upload(self):
        # Empty data
        upload_data = get_data_for_upload("24AAQCA8719H1ZC", "save")
        self.assertDictEqual(upload_data, {})

        # Data for save request
        self.gst_ims.update_action((self.invoice_name_1,), "Accepted")

        upload_data = get_data_for_upload("24AAQCA8719H1ZC", "save")
        self.assertEqual("BILL-24-00001", upload_data["b2b"][0]["inum"])

        # Data for reset request
        self.gst_ims.update_action((self.invoice_name_2,), "No Action")

        upload_data = get_data_for_upload("24AAQCA8719H1ZC", "reset")
        self.assertEqual("BILL-24-00002", upload_data["b2b"][0]["inum"])

    def test_declared_from_books(self):
        # CR25787E: snap to supplier within tolerance, else use books capped at document
        document = {"igst": 100, "cgst": 900, "sgst": 900, "cess": 0}

        # books within ₹1 -> trust supplier value
        self.assertEqual(
            _declared_from_books(document, {"igst": 100.5, "cgst": 900, "sgst": 900, "cess": 0}),
            {
                "itc_reduction_required": 1,
                "declared_igst": 100,
                "declared_cgst": 900,
                "declared_sgst": 900,
                "declared_cess": 0,
            },
        )

        # books lower (>₹1) -> books value, sgst mirrors cgst
        self.assertEqual(
            _declared_from_books(document, {"igst": 80, "cgst": 850, "sgst": 850, "cess": 0}),
            {
                "itc_reduction_required": 1,
                "declared_igst": 80,
                "declared_cgst": 850,
                "declared_sgst": 850,
                "declared_cess": 0,
            },
        )

        # books higher -> capped at document
        capped = _declared_from_books(document, {"igst": 500, "cgst": 1000, "sgst": 1000, "cess": 0})
        self.assertEqual(capped["declared_cgst"], 900)

        # no tax -> reduction not required
        zero = _declared_from_books(
            {"igst": 0, "cgst": 0, "sgst": 0, "cess": 0},
            {"igst": 0, "cgst": 0, "sgst": 0, "cess": 0},
        )
        self.assertEqual(zero["itc_reduction_required"], 0)

    def test_gov_format_itc_reduction(self):
        handler = IMSB2BCN(self.gst_ims.company, self.gst_ims.company_gstin)

        # accept -> declared block emitted
        data = handler.convert_data_to_gov_format(self.gov_invoice())
        self.assertEqual(data["itcRedReq"], "Y")
        self.assertEqual(data["declCgst"], 850)
        self.assertEqual(data["declSgst"], 850)

        # govt blocked -> suppressed
        data = handler.convert_data_to_gov_format(self.gov_invoice(is_itc_reduction_blocked=1))
        self.assertNotIn("itcRedReq", data)

        # reject -> no declared block, remarks carried
        data = handler.convert_data_to_gov_format(
            self.gov_invoice(ims_action="Rejected", remarks="not our purchase")
        )
        self.assertNotIn("itcRedReq", data)
        self.assertEqual(data["remarks"], "not our purchase")

        # non-specified record -> never declares
        data = IMSB2B(self.gst_ims.company, self.gst_ims.company_gstin).convert_data_to_gov_format(
            self.gov_invoice()
        )
        self.assertNotIn("itcRedReq", data)

    def test_defer_undeclarable_itc_reduction(self):
        matched = frappe._dict(
            ims_action="Accepted",
            doc_type="Credit Note",
            is_amended=0,
            is_itc_reduction_blocked=0,
            link_doctype="Purchase Invoice",
            link_name="PINV-1",
            bill_no="CN-MATCHED",
        )
        unmatched = frappe._dict(matched, link_doctype=None, link_name=None, bill_no="CN-UNMATCHED")
        blocked = frappe._dict(unmatched, is_itc_reduction_blocked=1, bill_no="CN-BLOCKED")
        b2b = frappe._dict(unmatched, doc_type="Invoice", is_amended=0, bill_no="B2B-UNMATCHED")

        # only the unmatched specified accept is deferred (skipped); the rest are kept
        kept = defer_undeclarable_itc_reduction([matched, unmatched, blocked, b2b])
        self.assertEqual(
            [invoice.bill_no for invoice in kept],
            ["CN-MATCHED", "CN-BLOCKED", "B2B-UNMATCHED"],
        )

    def test_set_declared_itc_on_accept(self):
        cn = create_gst_inward_supply(
            bill_no="CN-IMS-DECL",
            bill_date="2024-12-11",
            classification="CDNR",
            doc_type="Credit Note",
            is_amended=0,
            previous_ims_action="No Action",
            return_period_2b="122024",
            gen_date_2b="2024-12-11",
        )
        self.addCleanup(self.delete_inward_supply, cn.name)

        frappe.db.set_value(
            "GST Inward Supply",
            cn.name,
            {"link_doctype": "Purchase Invoice", "link_name": self.pinv.name},
        )

        # expected declared = linked PI tax reconciled against the credit note's own tax
        document = {head: cn.get(head) or 0 for head in ("igst", "cgst", "sgst", "cess")}
        books = PurchaseInvoice().get_all(names=[self.pinv.name]).get(self.pinv.name) or {}
        expected = _declared_from_books(document, books)

        set_declared_itc((cn.name,), "Accepted")

        cn.reload()
        self.assertEqual(cn.itc_reduction_required, expected["itc_reduction_required"])
        self.assertEqual(cn.declared_cgst, expected["declared_cgst"])
        self.assertEqual(cn.declared_sgst, cn.declared_cgst)  # govt: CGST == SGST

    def test_preserve_pending_itc_declaration(self):
        # re-download keeps the user's un-uploaded declared values; portal flags still refresh
        pending = {"declared_cgst": 10, "itc_reduction_required": 1, "is_itc_reduction_blocked": 0}
        preserve_pending_itc_declaration(
            frappe._dict(ims_action="Accepted", previous_ims_action="No Action"), pending
        )
        self.assertNotIn("declared_cgst", pending)
        self.assertNotIn("itc_reduction_required", pending)
        self.assertIn("is_itc_reduction_blocked", pending)

        # no pending action -> portal's declared values are kept
        refreshed = {"declared_cgst": 10}
        preserve_pending_itc_declaration(
            frappe._dict(ims_action="Accepted", previous_ims_action="Accepted"), refreshed
        )
        self.assertIn("declared_cgst", refreshed)

    def test_update_action_with_declared_overrides(self):
        cn = create_gst_inward_supply(
            bill_no="CN-IMS-OVERRIDE",
            bill_date="2024-12-11",
            classification="CDNR",
            doc_type="Credit Note",
            is_amended=0,
            previous_ims_action="No Action",
            return_period_2b="122024",
            gen_date_2b="2024-12-11",
        )
        self.addCleanup(self.delete_inward_supply, cn.name)
        frappe.db.set_value(
            "GST Inward Supply",
            cn.name,
            {"link_doctype": "Purchase Invoice", "link_name": self.pinv.name},
        )

        # document (supplier) tax is cgst = sgst = 900; override above supplier -> capped
        overrides = {cn.name: {"igst": 0, "cgst": 5000, "sgst": 5000, "cess": 0}}
        self.gst_ims.update_action((cn.name,), "Accepted", declared_overrides=overrides)

        cn.reload()
        self.assertEqual(cn.declared_cgst, 900)  # capped at document
        self.assertEqual(cn.declared_sgst, cn.declared_cgst)  # govt: CGST == SGST
        self.assertEqual(cn.itc_reduction_required, 1)

    def gov_invoice(self, **overrides):
        invoice = frappe._dict(
            {
                "supplier_gstin": "24MAYAS0100J1JD",
                "supply_type": "Regular",
                "supplier_return_form": "R1",
                "sup_return_period": "012023",
                "document_value": 1000,
                "place_of_supply": "07-Delhi",
                "previous_ims_action": "No Action",
                "igst": 0,
                "cgst": 900,
                "sgst": 900,
                "cess": 0,
                "taxable_value": 10000,
                "ims_action": "Accepted",
                "is_itc_reduction_blocked": 0,
                "itc_reduction_required": 1,
                "declared_igst": 0,
                "declared_cgst": 850,
                "declared_sgst": 850,
                "declared_cess": 0,
                "remarks": None,
                "is_remarks_blocked": 0,
            }
        )
        invoice.update(overrides)
        return invoice

    def delete_inward_supply(self, name):
        if frappe.db.exists("GST Inward Supply", name):
            frappe.delete_doc("GST Inward Supply", name, force=True)

    def test_update_previous_ims_action(self):
        self.gst_ims.update_action((self.invoice_name_1,), "Accepted")
        self.gst_ims.update_action((self.invoice_name_2,), "No Action")

        upload_data = get_data_for_upload("24AAQCA8719H1ZC", "save")
        data = {
            "body": {
                "action": "SAVE",
                "data": {
                    "invdata": upload_data,
                },
            },
        }

        create_integration_request(
            data=data,
            reference_doctype="GST Invoice Management System",
            reference_name="GST Invoice Management System",
            request_id="12345",
        )
        error_report = {
            "b2b": [
                {
                    "stin": "24AABCR6898M1ZN",
                    "inv": [{"rtnprd": "122024", "inum": "BILL-24-00002"}],
                }
            ],
        }

        update_previous_ims_action("12345", error_report)

        # Previous IMS Action updated
        self.assertEqual(
            frappe.get_value("GST Inward Supply", self.invoice_name_1, "previous_ims_action"),
            "Accepted",
        )

        # Previous IMS Action not updated
        self.assertEqual(
            frappe.get_value("GST Inward Supply", self.invoice_name_2, "previous_ims_action"),
            "Rejected",
        )

    @change_settings("GST Settings", {"enable_api": 1, "sandbox_mode": 0})
    def test_get_period_options(self):
        periods = self.get_periods()

        # When there are no GSTR 3B return logs
        period_options = get_period_options("_Test Indian Registered Company", "24AAQCA8719H1ZC")
        self.assertListEqual(period_options, periods[:6])

        # When GSTR 3B filed period is more than 6 months
        self.create_gstr_3b_return_log(periods[-1])
        period_options = get_period_options("_Test Indian Registered Company", "24AAQCA8719H1ZC")
        self.assertListEqual(period_options, periods[:-1])

        # When GSTR 3B filed period is less than 6 months
        self.create_gstr_3b_return_log(periods[2])
        period_options = get_period_options("_Test Indian Registered Company", "24AAQCA8719H1ZC")
        self.assertListEqual(period_options, periods[:2])

    def test_auto_reconciliation(self):
        invoice_data = self.gst_ims.autoreconcile_and_get_data().get("invoice_data")

        for data in invoice_data:
            if data._inward_supply.bill_no == "BILL-24-00001":
                self.assertEqual(data._purchase_invoice.name, self.pinv.name)

    def test_get_invoice_details_with_none_purchase_name(self):
        """
        Regression test: IMS detail view sends purchase_name=None for
        rows that are missing in purchase invoices.
        """
        gst_is = create_gst_inward_supply(
            bill_no="IMS-GID-001",
            bill_date="2024-12-12",
            return_period_2b="122024",
            gen_date_2b="2024-12-12",
            previous_ims_action="No Action",
            ims_action="No Action",
        )

        gst_ims = frappe.get_doc(
            {
                "doctype": "GST Invoice Management System",
                "company": "_Test Indian Registered Company",
                "company_gstin": "24AAQCA8719H1ZC",
                "return_period": "122024",
            }
        )

        result = gst_ims.get_invoice_details(
            purchase_name=None,
            inward_supply_name=gst_is.name,
        )

        self.assertEqual(result.inward_supply_name, gst_is.name)
        self.assertEqual(result.match_status, "Missing in PI")
        self.assertIsNone(result.purchase_invoice_name)

    def test_get_invoice_details_with_none_inward_supply_name(self):
        """
        Regression test: detail view can send inward_supply_name=None for
        rows where a purchase invoice exists but no matching inward supply.
        """
        pinv = create_purchase_invoice(
            bill_no="IMS-GID-002",
            bill_date="2024-12-12",
            posting_date="2024-12-12",
            supplier="_Test Registered Supplier",
            supplier_gstin="24AABCR6898M1ZN",
            company="_Test Indian Registered Company",
            company_gstin="24AAQCA8719H1ZC",
            items=[
                {
                    "item_code": "_Test Trading Goods 1",
                    "qty": 1,
                }
            ],
        )

        gst_ims = frappe.get_doc(
            {
                "doctype": "GST Invoice Management System",
                "company": "_Test Indian Registered Company",
                "company_gstin": "24AAQCA8719H1ZC",
                "return_period": "122024",
            }
        )

        result = gst_ims.get_invoice_details(
            purchase_name=pinv.name,
            inward_supply_name=None,
        )

        self.assertEqual(result.purchase_invoice_name, pinv.name)
        self.assertEqual(result.match_status, "Missing in 2A/2B")
        self.assertIsNone(result.inward_supply_name)

    def test_link_documents_with_none_purchase_invoice_name(self):
        """
        Regression test: link_documents should be a no-op when
        purchase_invoice_name is None.
        """
        gst_is = create_gst_inward_supply(
            bill_no="IMS-GID-003",
            bill_date="2024-12-12",
            return_period_2b="122024",
            gen_date_2b="2024-12-12",
            previous_ims_action="No Action",
            ims_action="No Action",
        )

        gst_ims = frappe.get_doc(
            {
                "doctype": "GST Invoice Management System",
                "company": "_Test Indian Registered Company",
                "company_gstin": "24AAQCA8719H1ZC",
                "return_period": "122024",
            }
        )

        result = gst_ims.link_documents(
            purchase_invoice_name=None,
            inward_supply_name=gst_is.name,
            link_doctype="Purchase Invoice",
        )

        self.assertIsNone(frappe.db.get_value("GST Inward Supply", gst_is.name, "link_name"))
        self.assertTrue(any(row.inward_supply_name == gst_is.name for row in result))

    def test_link_documents_with_none_link_doctype(self):
        """
        Regression test: link_documents should be a no-op when
        link_doctype is None.
        """
        pinv = create_purchase_invoice(
            bill_no="IMS-GID-004",
            bill_date="2024-12-12",
            posting_date="2024-12-12",
            supplier="_Test Registered Supplier",
            supplier_gstin="24AABCR6898M1ZN",
            company="_Test Indian Registered Company",
            company_gstin="24AAQCA8719H1ZC",
            items=[
                {
                    "item_code": "_Test Trading Goods 1",
                    "qty": 1,
                }
            ],
        )
        gst_is = create_gst_inward_supply(
            bill_no="IMS-GID-004",
            bill_date="2024-12-12",
            return_period_2b="122024",
            gen_date_2b="2024-12-12",
            previous_ims_action="No Action",
            ims_action="No Action",
        )

        gst_ims = frappe.get_doc(
            {
                "doctype": "GST Invoice Management System",
                "company": "_Test Indian Registered Company",
                "company_gstin": "24AAQCA8719H1ZC",
                "return_period": "122024",
            }
        )

        result = gst_ims.link_documents(
            purchase_invoice_name=pinv.name,
            inward_supply_name=gst_is.name,
            link_doctype=None,
        )

        self.assertIsNone(frappe.db.get_value("GST Inward Supply", gst_is.name, "link_name"))
        self.assertTrue(any(row.inward_supply_name == gst_is.name for row in result))

    def get_periods(self):
        periods = []
        date = add_to_date(None, months=-1)

        for _ in range(10):
            period = date.strftime("%m%Y")

            periods.append(period)
            date = add_to_date(date, months=-1)

        return periods

    def create_gstr_3b_return_log(self, period):
        gstr3b_log = frappe.new_doc("GST Return Log")
        gstr3b_log.return_period = period
        gstr3b_log.company = "_Test Indian Registered Company"
        gstr3b_log.gstin = "24AAQCA8719H1ZC"
        gstr3b_log.return_type = "GSTR3B"
        gstr3b_log.filing_status = "Filed"
        gstr3b_log.insert()

    def test_itc_claim_period_on_ims_action(self):
        """
        Test ITC Claim Period is set correctly based on IMS action.

        Logic:
        - Rejected/Pending → 'Deferred'
        - Accepted → ims_period (period from GST IMS)
        """
        ims_period = "122024"

        frappe.db.set_value(
            "GST Inward Supply",
            self.invoice_name_1,
            {"link_doctype": "Purchase Invoice", "link_name": self.pinv.name},
        )

        # Test Rejected action → Deferred
        self.gst_ims.period = ims_period
        self.gst_ims.update_action((self.invoice_name_1,), "Rejected")
        itc_claim_period = frappe.db.get_value("Purchase Invoice", self.pinv.name, "itc_claim_period")
        self.assertEqual(itc_claim_period, ITC_CLAIM_PERIOD_DEFERRED)

        # Test Accepted action → ims_period
        self.gst_ims.update_action((self.invoice_name_1,), "Accepted")
        itc_claim_period = frappe.db.get_value("Purchase Invoice", self.pinv.name, "itc_claim_period")
        self.assertEqual(itc_claim_period, ims_period)

        # Test Pending action → Deferred
        self.gst_ims.update_action((self.invoice_name_1,), "Pending")
        itc_claim_period = frappe.db.get_value("Purchase Invoice", self.pinv.name, "itc_claim_period")
        self.assertEqual(itc_claim_period, ITC_CLAIM_PERIOD_DEFERRED)

    def test_itc_claim_period_no_change_when_filed(self):
        """
        IMS action should NOT update ITC Claim Period when the
        current period is already filed.

        _calculate_itc_claim_period skips if current period is in
        the filed set.
        """
        ims_period = "122024"

        frappe.db.set_value(
            "GST Inward Supply",
            self.invoice_name_1,
            {"link_doctype": "Purchase Invoice", "link_name": self.pinv.name},
        )

        self.gst_ims.period = ims_period
        self.gst_ims.update_action((self.invoice_name_1,), "Accepted")
        itc_claim_period = frappe.db.get_value("Purchase Invoice", self.pinv.name, "itc_claim_period")
        self.assertEqual(itc_claim_period, ims_period)

        update_gstr3b_filing_status(
            company_gstin="24AAQCA8719H1ZC",
            month_or_quarter="December",
            year=2024,
            status="Filed",
        )

        # IMS Rejected → should NOT change (period is filed)
        self.gst_ims.update_action((self.invoice_name_1,), "Rejected")
        itc_claim_period = frappe.db.get_value("Purchase Invoice", self.pinv.name, "itc_claim_period")
        self.assertEqual(itc_claim_period, ims_period)

        update_gstr3b_filing_status(
            company_gstin="24AAQCA8719H1ZC",
            month_or_quarter="December",
            year=2024,
            status="Not Filed",
        )
