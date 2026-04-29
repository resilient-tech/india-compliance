# Copyright (c) 2019, Frappe Technologies Pvt. Ltd. and Contributors
# See license.txt

import json

import frappe
from frappe.tests import IntegrationTestCase, change_settings
from frappe.utils import get_month, getdate

from india_compliance.gst_india.doctype.bill_of_entry.bill_of_entry import (
    make_bill_of_entry,
)
from india_compliance.gst_india.doctype.gstr_3b_report.gstr_3b_report import (
    GSTR3BExcelExporter,
)
from india_compliance.gst_india.overrides.test_transaction import create_cess_accounts
from india_compliance.gst_india.report.gstr_3b_details.gstr_3b_details import (
    GSTR3B_Inward_Nil_Exempt,
)
from india_compliance.gst_india.utils import get_gst_accounts_by_type
from india_compliance.gst_india.utils.tests import (
    create_purchase_invoice,
    create_sales_invoice,
    create_transaction,
)


class TestGSTR3BReport(IntegrationTestCase):
    def setUp(self):
        frappe.set_user("Administrator")
        filters = {"company": "_Test Indian Registered Company"}

        self.maxDiff = None
        for doctype in (
            "Sales Invoice",
            "Purchase Invoice",
            "Payment Entry",
            "Bill of Entry",
            "GSTR 3B Report",
            "Journal Entry",
            "Bill of Entry",
        ):
            frappe.db.delete(doctype, filters=filters)

    @classmethod
    def tearDownClass(cls):
        frappe.db.rollback()

    def get_report_output(self):
        today = getdate()
        frappe.db.delete(
            "GSTR 3B Report",
            filters={
                "company": "_Test Indian Registered Company",
                "company_gstin": "24AAQCA8719H1ZC",
                "year": today.year,
                "month_or_quarter": get_month(today),
            },
        )

        report = frappe.get_doc(
            {
                "doctype": "GSTR 3B Report",
                "company": "_Test Indian Registered Company",
                "company_gstin": "24AAQCA8719H1ZC",
                "year": today.year,
                "month_or_quarter": get_month(today),
            }
        ).insert()

        return json.loads(report.json_output)

    @change_settings("GST Settings", {"enable_overseas_transactions": 1})
    def test_gstr_3b_report(self):
        gst_settings = frappe.get_cached_doc("GST Settings")
        gst_settings.round_off_gst_values = 0
        gst_settings.save()

        create_sales_invoices()
        create_purchase_invoices()
        create_itc_reclaim_journal_entry()

        today = getdate()
        ret_period = f"{today.month:02}{today.year}"

        report = frappe.get_doc(
            {
                "doctype": "GSTR 3B Report",
                "company": "_Test Indian Registered Company",
                "company_gstin": "24AAQCA8719H1ZC",
                "year": today.year,
                "month_or_quarter": get_month(today),
            }
        ).insert()

        output = json.loads(report.json_output)

        self.assertDictEqual(
            output,
            {
                "gstin": "24AAQCA8719H1ZC",
                "ret_period": ret_period,
                # 3.1
                "sup_details": {
                    "isup_rev": {
                        "camt": 9.0,
                        "csamt": 0.0,
                        "iamt": 0.0,
                        "samt": 9.0,
                        "txval": 100.0,
                    },
                    "osup_det": {
                        "camt": 18.0,
                        "csamt": 0.0,
                        "iamt": 73.98,
                        "samt": 18.0,
                        "txval": 732.0,
                    },
                    "osup_nil_exmp": {"txval": 250.0},
                    "osup_nongst": {"txval": 222.0},
                    "osup_zero": {"csamt": 0.0, "iamt": 99.9, "txval": 999.0},
                },
                # 3.1.1
                "eco_dtls": {
                    "eco_sup": {
                        "txval": 0.0,
                        "iamt": 0.0,
                        "camt": 0.0,
                        "samt": 0.0,
                        "csamt": 0.0,
                    },
                    "eco_reg_sup": {"txval": 100.0},
                },
                # 3.2
                "inter_sup": {
                    "comp_details": [{"iamt": 18.0, "pos": "29", "txval": 100.0}],
                    "uin_details": [{"iamt": 36.0, "pos": "29", "txval": 200.0}],
                    "unreg_details": [{"iamt": 19.98, "pos": "06", "txval": 111.0}],
                },
                # 4
                "itc_elg": {
                    "itc_avl": [
                        {
                            "camt": 0.0,
                            "csamt": 0.0,
                            "iamt": 0.0,
                            "samt": 0.0,
                            "ty": "IMPG",
                        },
                        {
                            "camt": 0.0,
                            "csamt": 0.0,
                            "iamt": 0.0,
                            "samt": 0.0,
                            "ty": "IMPS",
                        },
                        {
                            "camt": 9.0,
                            "csamt": 0.0,
                            "iamt": 0.0,
                            "samt": 9.0,
                            "ty": "ISRC",
                        },
                        {
                            "camt": 0.0,
                            "csamt": 0.0,
                            "iamt": 0.0,
                            "samt": 0.0,
                            "ty": "ISD",
                        },
                        {
                            "camt": 40.5,
                            "csamt": 0.0,
                            "iamt": 0.0,
                            "samt": 40.5,
                            "ty": "OTH",
                        },
                    ],
                    "itc_inelg": [
                        {
                            "camt": 9.0,
                            "csamt": 0.0,
                            "iamt": 0.0,
                            "samt": 9.0,
                            "ty": "RUL",
                        },
                        {
                            "camt": 0.0,
                            "csamt": 0.0,
                            "iamt": 36.0,
                            "samt": 0.0,
                            "ty": "OTH",
                        },
                    ],
                    "itc_net": {"camt": 40.5, "csamt": 0.0, "iamt": 0.0, "samt": 40.5},
                    "itc_rev": [
                        {
                            "camt": 9.0,
                            "csamt": 0.0,
                            "iamt": 0.0,
                            "samt": 9.0,
                            "ty": "RUL",
                        },
                        {
                            "camt": 0.0,
                            "csamt": 0.0,
                            "iamt": 0.0,
                            "samt": 0.0,
                            "ty": "OTH",
                        },
                    ],
                },
                # 5
                "inward_sup": {
                    "isup_details": [
                        {"inter": 100.0, "intra": 100.0, "ty": "GST"},
                        {"inter": 300.0, "intra": 200.0, "ty": "NONGST"},
                    ]
                },
            },
        )

        exporter = GSTR3BExcelExporter(output)
        exporter.generate_excel()

    def test_gst_rounding(self):
        gst_settings = frappe.get_cached_doc("GST Settings")
        gst_settings.round_off_gst_values = 1
        gst_settings.save()

        si = create_sales_invoice(
            rate=216,
            is_in_state=True,
            do_not_submit=True,
        )

        # Check for 39 instead of 38.88
        self.assertEqual(si.taxes[0].base_tax_amount_after_discount_amount, 19)

        gst_settings.round_off_gst_values = 1
        gst_settings.save()

    @change_settings(
        "GST Settings",
        {"enable_overseas_transactions": 1, "round_off_gst_values": 0},
    )
    def test_bill_of_entry_impg_itc_in_gstr3b(self):
        """
        A submitted Bill of Entry should contribute IGST to IMPG (Import Of Goods)
        in GSTR-3B table 4A (ITC Available) and table 4C (Net ITC).

        An ineligible BOE (is_ineligible_for_itc=1 on the item) is duplicated:
        once into itc_avl IMPG and once into itc_rev RUL, so its net ITC is zero
        — verifying the is_itc_reversed_for_boe() code path.

        Setup:
          BOE-1 (eligible):
            PI rate=100, customs_duty=100, assessable=200, IGST @18% = 36
          BOE-2 (ineligible):
            PI rate=100, no customs duty, assessable=100, IGST @18% = 18
        """
        pi = create_purchase_invoice(supplier="_Test Foreign Supplier", update_stock=1)
        boe = make_bill_of_entry(pi.name)
        boe.items[0].customs_duty = 100
        boe.bill_of_entry_no = frappe.generate_hash(length=5)
        boe.bill_of_entry_date = getdate()
        boe.save()
        boe.submit()

        # Second BOE — item marked ineligible: appears in both itc_avl and itc_rev
        pi2 = create_purchase_invoice(supplier="_Test Foreign Supplier", update_stock=1, rate=100)
        boe2 = make_bill_of_entry(pi2.name)
        boe2.items[0].is_ineligible_for_itc = 1
        boe2.bill_of_entry_no = frappe.generate_hash(length=5)
        boe2.bill_of_entry_date = getdate()
        boe2.save()
        boe2.submit()

        today = getdate()
        report = frappe.get_doc(
            {
                "doctype": "GSTR 3B Report",
                "company": "_Test Indian Registered Company",
                "company_gstin": "24AAQCA8719H1ZC",
                "year": today.year,
                "month_or_quarter": get_month(today),
            }
        ).insert()

        output = json.loads(report.json_output)

        # Table 4A — IMPG: 36 (eligible BOE) + 18 (ineligible BOE avl copy)
        impg = next(d for d in output["itc_elg"]["itc_avl"] if d["ty"] == "IMPG")
        self.assertEqual(impg["iamt"], 54.0)
        self.assertEqual(impg["camt"], 0.0)
        self.assertEqual(impg["samt"], 0.0)
        self.assertEqual(impg["csamt"], 0.0)

        # Table 4B — itc_rev RUL: 18 from ineligible BOE reversal copy
        rul_rev = next(d for d in output["itc_elg"]["itc_rev"] if d["ty"] == "RUL")
        self.assertEqual(rul_rev["iamt"], 18.0)

        # Table 4C — Net ITC: 36 (eligible BOE); ineligible BOE avl+rev cancels to 0
        net_itc = output["itc_elg"]["itc_net"]
        self.assertEqual(net_itc["iamt"], 36.0)

    def test_itc_reversal_journal_entry_is_included_in_gstr_3b(self):
        journal_entry = create_itc_reversal_journal_entry()

        self.assertEqual(journal_entry.accounts[1].gst_tax_type, "cgst")
        self.assertEqual(journal_entry.accounts[2].gst_tax_type, "sgst")

        today = getdate()

        report = frappe.get_doc(
            {
                "doctype": "GSTR 3B Report",
                "company": "_Test Indian Registered Company",
                "company_gstin": "24AAQCA8719H1ZC",
                "year": today.year,
                "month_or_quarter": get_month(today),
            }
        ).insert()

        output = json.loads(report.json_output)
        self.assertEqual(output["itc_elg"]["itc_rev"][0]["camt"], 9.0)
        self.assertEqual(output["itc_elg"]["itc_rev"][0]["samt"], 9.0)
        self.assertEqual(output["itc_elg"]["itc_net"]["camt"], -9.0)
        self.assertEqual(output["itc_elg"]["itc_net"]["samt"], -9.0)

    @change_settings("GST Settings", {"enable_overseas_transactions": 1})
    def test_inward_nil_non_gst_report_includes_sez_services(self):
        pi = create_purchase_invoice(
            supplier="_Test Registered Supplier",
            do_not_save=1,
            do_not_submit=1,
            item_code="_Test Service Item",
        )
        pi.gst_category = "SEZ"
        pi.insert()
        pi.submit()

        today = getdate()

        report = GSTR3B_Inward_Nil_Exempt(
            {
                "company": "_Test Indian Registered Company",
                "company_gstin": "24AAQCA8719H1ZC",
                "year": today.year,
                "month_or_quarter": get_month(today),
            }
        )

        rows = report.get_inward_nil_exempt()
        self.assertIn(pi.name, [row.voucher_no for row in rows])

    @change_settings("GST Settings", {"enable_overseas_transactions": 1})
    def test_inward_nil_non_gst_report_excludes_overseas_import_services(self):
        pi = create_purchase_invoice(
            supplier="_Test Foreign Supplier",
            do_not_save=1,
            do_not_submit=1,
            item_code="_Test Service Item",
        )
        pi.insert()
        pi.submit()

        self.assertEqual(pi.itc_classification, "Import Of Service")

        today = getdate()

        report = GSTR3B_Inward_Nil_Exempt(
            {
                "company": "_Test Indian Registered Company",
                "company_gstin": "24AAQCA8719H1ZC",
                "year": today.year,
                "month_or_quarter": get_month(today),
            }
        )

        rows = report.get_inward_nil_exempt()
        self.assertNotIn(pi.name, [row.voucher_no for row in rows])

    @change_settings("GST Settings", {"enable_overseas_transactions": 1})
    def test_gstr_3b_report_includes_boe_in_import_of_goods(self):
        pi = create_purchase_invoice(supplier="_Test Foreign Supplier", update_stock=1)

        boe = make_bill_of_entry(pi.name)
        boe.items[0].customs_duty = 100
        boe.bill_of_entry_no = "BOE-001"
        boe.bill_of_entry_date = getdate()
        boe.save()
        boe.submit()

        today = getdate()

        report = frappe.get_doc(
            {
                "doctype": "GSTR 3B Report",
                "company": "_Test Indian Registered Company",
                "company_gstin": "24AAQCA8719H1ZC",
                "year": today.year,
                "month_or_quarter": get_month(today),
            }
        ).insert()

        output = json.loads(report.json_output)
        itc_available = {row["ty"]: row for row in output.get("itc_elg", {}).get("itc_avl", [])}

        self.assertEqual(itc_available["IMPG"].get("iamt"), 36.0)
        self.assertEqual(itc_available["IMPG"].get("csamt"), 0.0)

    @change_settings("GST Settings", {"enable_overseas_transactions": 1})
    def test_gstr_3b_report_includes_boe_cess_non_advol_in_csamt(self):
        pi = create_purchase_invoice(supplier="_Test Foreign Supplier", update_stock=1)

        boe = make_bill_of_entry(pi.name)
        boe.items[0].customs_duty = 100
        boe.bill_of_entry_no = "BOE-002"
        boe.bill_of_entry_date = getdate()

        create_cess_accounts()
        gst_accounts = get_gst_accounts_by_type(boe.company, "Input")
        boe.append(
            "taxes",
            {
                "charge_type": "On Item Quantity",
                "account_head": gst_accounts.cess_non_advol_account,
                "rate": 20,
                "cost_center": "Main - _TIRC",
                "item_wise_tax_rates": {},
            },
        )

        boe.save()
        boe.submit()

        today = getdate()

        report = frappe.get_doc(
            {
                "doctype": "GSTR 3B Report",
                "company": "_Test Indian Registered Company",
                "company_gstin": "24AAQCA8719H1ZC",
                "year": today.year,
                "month_or_quarter": get_month(today),
            }
        ).insert()

        output = json.loads(report.json_output)
        itc_available = {row["ty"]: row for row in output.get("itc_elg", {}).get("itc_avl", [])}

        self.assertEqual(itc_available["IMPG"].get("iamt"), 36.0)
        self.assertEqual(itc_available["IMPG"].get("csamt"), 20.0)

    @change_settings("GST Settings", {"enable_overseas_transactions": 1})
    def test_itc_from_pi_when_boe_not_applicable(self):
        """When is_boe_applicable=0, ITC should be reported from Purchase Invoice directly"""
        # Use SEZ registered supplier: has GSTIN + itc_classification = Import Of Goods
        # GST taxes on PI → is_boe_applicable auto-set to 0 (no BOE needed)
        pi = create_purchase_invoice(
            supplier="_Test Registered Supplier",
            update_stock=1,
            is_out_state=True,
            do_not_save=1,
            do_not_submit=1,
        )
        pi.gst_category = "SEZ"
        pi.insert()
        pi.submit()

        expected_iamt = sum((item.igst_amount or 0) for item in pi.items)
        self.assertGreater(expected_iamt, 0)

        today = getdate()

        report = frappe.get_doc(
            {
                "doctype": "GSTR 3B Report",
                "company": "_Test Indian Registered Company",
                "company_gstin": "24AAQCA8719H1ZC",
                "year": today.year,
                "month_or_quarter": get_month(today),
            }
        ).insert()

        output = json.loads(report.json_output)
        itc_available = {row["ty"]: row for row in output.get("itc_elg", {}).get("itc_avl", [])}

        # ITC should be reported from Purchase Invoice
        self.assertEqual(itc_available["IMPG"].get("iamt"), expected_iamt)
        self.assertEqual(itc_available["IMPG"].get("csamt"), 0.0)

    @change_settings("GST Settings", {"enable_overseas_transactions": 1})
    def test_itc_from_boe_when_boe_applicable(self):
        """When is_boe_applicable=1, ITC should come from BOE, not from Purchase Invoice"""
        pi = create_purchase_invoice(supplier="_Test Foreign Supplier", update_stock=1)
        # PI auto-defaults is_boe_applicable=1 (no GST charged)
        self.assertEqual(pi.is_boe_applicable, 1)

        boe = make_bill_of_entry(pi.name)
        boe.items[0].customs_duty = 100
        boe.bill_of_entry_no = "BOE-004"
        boe.bill_of_entry_date = getdate()
        boe.save()
        boe.submit()

        today = getdate()

        report = frappe.get_doc(
            {
                "doctype": "GSTR 3B Report",
                "company": "_Test Indian Registered Company",
                "company_gstin": "24AAQCA8719H1ZC",
                "year": today.year,
                "month_or_quarter": get_month(today),
            }
        ).insert()

        output = json.loads(report.json_output)
        itc_available = {row["ty"]: row for row in output.get("itc_elg", {}).get("itc_avl", [])}

        # ITC should come from BOE (customs duty 100 * 36% = 36)
        self.assertEqual(itc_available["IMPG"].get("iamt"), 36.0)
        self.assertEqual(itc_available["IMPG"].get("csamt"), 0.0)

    def test_eco_rc_to_composition_not_double_reported_in_section_3_2(self):
        """
        An eco-operator RC invoice to a Registered Composition customer (inter-state)
        must appear in eco_reg_sup (table 3.1.1) but must NOT be reported again in
        comp_details (section 3.2).
        """
        create_sales_invoice(
            customer="_Test Registered Composition Customer",
            is_reverse_charge=True,
            ecommerce_gstin="29AABCF8078M1C8",
            is_out_state_rcm=True,
        )

        today = getdate()
        report = frappe.get_doc(
            {
                "doctype": "GSTR 3B Report",
                "company": "_Test Indian Registered Company",
                "company_gstin": "24AAQCA8719H1ZC",
                "year": today.year,
                "month_or_quarter": get_month(today),
            }
        ).insert()

        output = json.loads(report.json_output)

        # Taxable value must appear in eco_reg_sup (table 3.1.1)
        self.assertEqual(output["eco_dtls"]["eco_reg_sup"]["txval"], 100.0)

        # Must NOT be double-reported in section 3.2 comp_details
        self.assertEqual(output["inter_sup"]["comp_details"], [])

    def test_reverse_charge_sales_invoice(self):
        create_sales_invoice(
            customer="_Test Registered Customer",
            is_reverse_charge=True,
            item_code="_Test Trading Goods 1",
            rate=121,
            is_in_state_rcm=True,
        )

        output = self.get_report_output()

        self.assertEqual(output["sup_details"]["osup_det"]["txval"], 121.0)
        self.assertEqual(output["sup_details"]["osup_det"]["iamt"], 0.0)
        self.assertEqual(output["sup_details"]["osup_det"]["camt"], 0.0)
        self.assertEqual(output["sup_details"]["osup_det"]["samt"], 0.0)
        self.assertEqual(output["sup_details"]["osup_det"]["csamt"], 0.0)

    def test_inward_reverse_charge_purchase_invoice_updates_isup_rev(self):
        create_purchase_invoice(
            is_in_state_rcm=True,
            supplier="_Test Unregistered Supplier",
            is_reverse_charge=True,
            rate=100,
        )

        output = self.get_report_output()

        self.assertEqual(output["sup_details"]["isup_rev"]["txval"], 100.0)
        self.assertEqual(output["sup_details"]["isup_rev"]["iamt"], 0.0)
        self.assertEqual(output["sup_details"]["isup_rev"]["camt"], 9.0)
        self.assertEqual(output["sup_details"]["isup_rev"]["samt"], 9.0)
        self.assertEqual(output["sup_details"]["isup_rev"]["csamt"], 0.0)

    def test_taxable_sales_invoice(self):
        create_sales_invoice(customer="_Test Registered Customer", is_in_state=True)

        output = self.get_report_output()

        self.assertEqual(output["sup_details"]["osup_det"]["txval"], 100.0)
        self.assertEqual(output["sup_details"]["osup_det"]["camt"], 9.0)
        self.assertEqual(output["sup_details"]["osup_det"]["samt"], 9.0)
        self.assertEqual(output["sup_details"]["osup_det"]["iamt"], 0.0)

    @change_settings("GST Settings", {"enable_overseas_transactions": 1})
    def test_zero_rated_sales_invoice(self):
        create_sales_invoice(
            customer_address="_Test Registered Customer-Billing-1",
            is_export_with_gst=True,
            is_out_state=True,
            rate=555,
        )

        output = self.get_report_output()

        self.assertEqual(output["sup_details"]["osup_zero"]["txval"], 555.0)
        self.assertEqual(output["sup_details"]["osup_zero"]["iamt"], 99.9)
        self.assertEqual(output["sup_details"]["osup_zero"]["csamt"], 0.0)

    def test_nil_rated_sales_invoice(self):
        create_sales_invoice(item_tax_template="Nil-Rated - _TIRC")

        output = self.get_report_output()

        self.assertEqual(output["sup_details"]["osup_nil_exmp"]["txval"], 100.0)

    def test_exempted_sales_invoice(self):
        create_sales_invoice(gst_treatment="Exempted", rate=150)

        output = self.get_report_output()

        self.assertEqual(output["sup_details"]["osup_nil_exmp"]["txval"], 150.0)

        create_sales_invoice(item_code="_Test Non GST Item", rate=222)

        output = self.get_report_output()

        self.assertEqual(output["sup_details"]["osup_nongst"]["txval"], 222.0)

    def test_sales_ecommerce_9_5(self):
        create_sales_invoice(
            customer="_Test Registered Customer",
            is_reverse_charge=True,
            item_code="_Test Trading Goods 1",
            rate=100,
            ecommerce_gstin="29AABCF8078M1C8",
            is_in_state_rcm=True,
        )

        output = self.get_report_output()

        self.assertEqual(output["eco_dtls"]["eco_reg_sup"]["txval"], 100.0)

    def test_payment_entry_advance(self):
        create_advance_payment_entry()

        today = getdate()
        report = frappe.get_doc(
            {
                "doctype": "GSTR 3B Report",
                "company": "_Test Indian Registered Company",
                "company_gstin": "24AAQCA8719H1ZC",
                "year": today.year,
                "month_or_quarter": get_month(today),
            }
        ).insert()

        output = json.loads(report.json_output)

        self.assertEqual(output["sup_details"]["osup_det"]["txval"], 500.0)
        self.assertEqual(output["sup_details"]["osup_det"]["iamt"], 0.0)
        self.assertEqual(output["sup_details"]["osup_det"]["camt"], 45.0)
        self.assertEqual(output["sup_details"]["osup_det"]["samt"], 45.0)
        self.assertEqual(output["sup_details"]["osup_det"]["csamt"], 0.0)

    def test_payment_entry_adjustment(self):
        payment_doc = create_advance_payment_entry()
        create_sales_invoice_against_advance(payment_doc)

        today = getdate()
        report = frappe.get_doc(
            {
                "doctype": "GSTR 3B Report",
                "company": "_Test Indian Registered Company",
                "company_gstin": "24AAQCA8719H1ZC",
                "year": today.year,
                "month_or_quarter": get_month(today),
            }
        ).insert()

        output = json.loads(report.json_output)

        self.assertEqual(output["sup_details"]["osup_det"]["txval"], 500.0)
        self.assertEqual(output["sup_details"]["osup_det"]["iamt"], 0.0)
        self.assertEqual(output["sup_details"]["osup_det"]["camt"], 45.0)
        self.assertEqual(output["sup_details"]["osup_det"]["samt"], 45.0)
        self.assertEqual(output["sup_details"]["osup_det"]["csamt"], 0.0)

    def test_inter_state_advance_payment_entry(self):
        create_advance_payment_entry(
            customer_address="_Test Registered Customer-Billing-1",
            place_of_supply="29-Karnataka",
            is_in_state=0,
            is_out_state=1,
        )

        output = self.get_report_output()

        self.assertEqual(output["sup_details"]["osup_det"]["txval"], 500.0)
        self.assertEqual(output["sup_details"]["osup_det"]["iamt"], 90.0)
        self.assertEqual(output["sup_details"]["osup_det"]["camt"], 0.0)
        self.assertEqual(output["sup_details"]["osup_det"]["samt"], 0.0)


def create_sales_invoices():
    create_sales_invoice(is_in_state=True)
    create_sales_invoice(
        customer="_Test Registered Composition Customer",
        is_out_state=True,
    )
    create_sales_invoice(
        customer="_Test Unregistered Customer",
        is_in_state=True,
    )
    # Unregistered Out of state
    create_sales_invoice(
        customer="_Test Unregistered Customer",
        is_out_state=True,
        place_of_supply="06-Haryana",
        rate=111,
    )
    # Same Item Nil-Rated
    create_sales_invoice(item_tax_template="Nil-Rated - _TIRC")
    # Non Gst item
    create_sales_invoice(item_code="_Test Non GST Item", rate=222)
    # Zero Rated
    create_sales_invoice(
        customer_address="_Test Registered Customer-Billing-1",
        is_export_with_gst=False,
        rate=444,
    )
    create_sales_invoice(
        customer_address="_Test Registered Customer-Billing-1",
        is_export_with_gst=True,
        is_out_state=True,
        rate=555,
    )
    # E-commerce reverse charge
    create_sales_invoice(
        customer="_Test Registered Customer",
        is_reverse_charge=True,
        item_code="_Test Trading Goods 1",
        rate=100,
        ecommerce_gstin="29AABCF8078M1C8",
        is_in_state_rcm=True,
    )
    # Reverse Charge Sales
    create_sales_invoice(
        customer="_Test Registered Customer",
        is_reverse_charge=True,
        item_code="_Test Trading Goods 1",
        rate=121,
        is_in_state_rcm=True,
    )
    # Exempted item (same section as Nil-Rated: osup_nil_exmp)
    create_sales_invoice(gst_treatment="Exempted", rate=150)
    # UIN Holders inter-state → osup_det (txval+200, iamt+36) and uin_details (pos=29)
    create_sales_invoice(
        customer_address="_Test Registered Customer-Billing-4",
        is_out_state=True,
        rate=200,
    )


def create_purchase_invoices():
    create_purchase_invoice(is_in_state=True)
    create_purchase_invoice(rate=250, qty=1, is_in_state=True)
    create_purchase_invoice(supplier="_Test Registered Composition Supplier")
    create_purchase_invoice(
        is_in_state_rcm=True,
        supplier="_Test Unregistered Supplier",
        is_reverse_charge=True,
    )
    # Intra-state Nil-Rated purchase → inward_sup GST intra
    create_purchase_invoice(item_code="_Test Nil Rated Item", rate=100)
    # Non-GST purchase → inward_sup NONGST intra
    create_purchase_invoice(item_code="_Test Non GST Item", rate=200)
    # PoS ineligible ITC → itc_inelg OTH iamt=36 (18% IGST on 200, PoS≠company state)
    create_purchase_invoice(
        supplier="_Test Registered InterState Supplier",
        is_out_state=True,
        place_of_supply="29-Karnataka",
        rate=200,
        qty=1,
    )
    # Section 17(5) → itc_avl OTH +9/+9 and itc_rev RUL +9/+9 (net zero change)
    pi = create_purchase_invoice(is_in_state=True, rate=100, qty=1, do_not_save=True)
    pi.items[0].is_ineligible_for_itc = 1
    pi.save()
    pi.submit()
    # Inter-state Non-GST purchase → inward_sup NONGST inter=300
    create_purchase_invoice(
        item_code="_Test Non GST Item",
        rate=300,
        supplier="_Test Registered InterState Supplier",
        is_out_state=True,
    )


def create_advance_payment_entry(do_not_submit=False, **kwargs):
    payment_doc = create_transaction(
        **{
            "doctype": "Payment Entry",
            "payment_type": "Receive",
            "mode_of_payment": "Cash",
            "company_address": "_Test Indian Registered Company-Billing",
            "party_type": "Customer",
            "party": "_Test Registered Customer",
            "customer_address": "_Test Registered Customer-Billing",
            "paid_to": "Cash - _TIRC",
            "paid_amount": 500,
            "is_in_state": 1,
            "do_not_save": True,
            **kwargs,
        }
    )

    payment_doc.setup_party_account_field()
    payment_doc.set_missing_values()
    payment_doc.set_exchange_rate()
    payment_doc.received_amount = payment_doc.paid_amount / payment_doc.target_exchange_rate
    payment_doc.save()

    if not do_not_submit:
        payment_doc.submit()

    return payment_doc


def create_sales_invoice_against_advance(payment_doc):
    invoice_doc = create_transaction(
        doctype="Sales Invoice",
        customer="_Test Registered Customer",
        is_in_state=1,
        do_not_submit=True,
    )

    invoice_doc.set_advances()
    for row in invoice_doc.advances:
        row.allocated_amount = invoice_doc.net_total if row.reference_name == payment_doc.name else 0

    invoice_doc.submit()
    return invoice_doc


def create_itc_reversal_journal_entry(
    ineligibility_reason="As per rules 42 & 43 of CGST Rules",
):
    journal_entry = frappe.get_doc(
        {
            "doctype": "Journal Entry",
            "company": "_Test Indian Registered Company",
            "company_gstin": "24AAQCA8719H1ZC",
            "posting_date": getdate(),
            "voucher_type": "Reversal Of ITC",
            "ineligibility_reason": ineligibility_reason,
            "accounts": [
                {
                    "account": "GST Expense - _TIRC",
                    "debit_in_account_currency": 18,
                },
                {
                    "account": "Input Tax CGST - _TIRC",
                    "credit_in_account_currency": 9,
                },
                {
                    "account": "Input Tax SGST - _TIRC",
                    "credit_in_account_currency": 9,
                },
            ],
        }
    )
    journal_entry.insert()
    journal_entry.submit()
    return journal_entry


def create_itc_reclaim_journal_entry():
    """
    Create a 'Reclaim of ITC Reversal' Journal Entry.
    In the JE the amounts are the opposite direction to Reversal Of ITC:
    GST Expense is credited and Input Tax accounts are debited.
    """
    journal_entry = frappe.get_doc(
        {
            "doctype": "Journal Entry",
            "company": "_Test Indian Registered Company",
            "company_gstin": "24AAQCA8719H1ZC",
            "posting_date": getdate(),
            "voucher_type": "Reclaim of ITC Reversal",
            "accounts": [
                {
                    "account": "GST Expense - _TIRC",
                    "credit_in_account_currency": 18,
                },
                {
                    "account": "Input Tax CGST - _TIRC",
                    "debit_in_account_currency": 9,
                },
                {
                    "account": "Input Tax SGST - _TIRC",
                    "debit_in_account_currency": 9,
                },
            ],
        }
    )
    journal_entry.insert()
    journal_entry.submit()
    return journal_entry
