import frappe
from frappe.tests.utils import FrappeTestCase, change_settings
from frappe.utils import flt, getdate
from erpnext.accounts.doctype.sales_invoice.sales_invoice import make_sales_return

from india_compliance.gst_india.overrides.company import create_default_company_account
from india_compliance.gst_india.utils import get_full_gst_uom
from india_compliance.gst_india.utils.gstr_1 import (
    GSTR1_B2B_InvoiceType,
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


class TestGSTR1BooksData(FrappeTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

    def setUp(self):
        super().setUp()
        frappe.db.rollback()

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
                        self.assertDictEq(row, actual.get(k, [])[i])

            self.assertEqual(v, actual.get(k))

    def test_b2b_regular_transaction(self):
        setup_cess_account()
        si = create_sales_invoice(
            customer="_Test Registered Customer",
            is_in_state=True,
            do_not_submit=True,
            items=[
                {
                    "item_code": "_Test Trading Goods 1",
                    "qty": 1.0,
                    "rate": 100.0,
                }
            ],
        )
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
                "document_type": GSTR1_B2B_InvoiceType.R.value,
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
        setup_cess_account()
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
                "document_type": GSTR1_B2B_InvoiceType.R.value,
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

    @change_settings("System Settings", {"currency_precision": 3})
    def test_b2b_rounding_adjustment(self):
        def create_invoice():
            si = create_sales_invoice(
                customer="_Test Registered Customer",
                is_in_state=True,
                do_not_submit=True,
            )

            random_hsn_codes = ["55885588", "55998899", "55779966", "55667788"]
            for i in range(1, 7):
                append_item(
                    si,
                    data=frappe._dict(
                        gst_hsn_code=random_hsn_codes[i % 4], qty=1.0, rate=1.003
                    ),
                )

            si.save()
            si.submit()

        for _ in range(11):
            create_invoice()

        _class = GSTR1BooksData(filters=FILTERS)
        data = _class.prepare_mapped_data()
        self.assertDictEq(
            {
                "rounding_difference": {
                    "total_taxable_value": -0.022,
                    "total_igst_amount": 0.0,
                    "total_cgst_amount": 0.022,
                    "total_sgst_amount": 0.022,
                    "total_cess_amount": 0.0,
                }
            },
            data["rounding_difference"],
        )

        # Check if HSN Summary is same as Invoice Summary
        for key in _class.DATA_TO_ITEM_FIELD_MAPPING:
            invoice_total = 0
            for row in data[GSTR1_SubCategory.B2B_REGULAR.value].values():
                invoice_total += row.get(key, 0.0)

            hsn_total = 0
            for row in data[GSTR1_SubCategory.HSN_B2B.value].values():
                hsn_total += row.get(key, 0.0)

            self.assertEqual(flt(hsn_total, 2), flt(invoice_total, 2))

    @change_settings("System Settings", {"currency_precision": 3})
    def test_b2c_rounding_adjustment(self):
        def create_invoice():
            si = create_sales_invoice(
                customer="_Test Unregistered Customer",
                is_in_state=True,
                do_not_submit=True,
            )

            random_hsn_codes = ["55885588", "55998899", "55779966", "55667788"]
            for i in range(1, 7):
                append_item(
                    si,
                    data=frappe._dict(
                        gst_hsn_code=random_hsn_codes[i % 4], qty=1.0, rate=1.003
                    ),
                )

            si.save()
            si.submit()

        for _ in range(11):
            create_invoice()

        _class = GSTR1BooksData(filters=FILTERS)
        data = _class.prepare_mapped_data()
        self.assertDictEq(
            {
                "rounding_difference": {
                    "total_taxable_value": -0.022,
                    "total_igst_amount": 0.0,
                    "total_cgst_amount": 0.022,
                    "total_sgst_amount": 0.022,
                    "total_cess_amount": 0.0,
                }
            },
            data["rounding_difference"],
        )

        # Check if HSN Summary is same as Invoice Summary
        for key in _class.DATA_TO_ITEM_FIELD_MAPPING:
            invoice_total = 0
            for invoices in data[GSTR1_SubCategory.B2CS.value].values():
                for row in invoices:
                    invoice_total += row.get(key, 0.0)

            hsn_total = 0
            for row in data[GSTR1_SubCategory.HSN_B2C.value].values():
                hsn_total += row.get(key, 0.0)

            self.assertEqual(flt(hsn_total, 2), flt(invoice_total, 2))

    @change_settings("System Settings", {"currency_precision": 3})
    def test_nil_exempt_rounding_adjustment(self):
        def create_invoice():
            si = create_sales_invoice(
                customer="_Test Unregistered Customer",
                is_in_state=True,
                do_not_submit=True,
                item_code="_Test Nil Rated Item",
            )

            random_hsn_codes = ["55885588", "55998899", "55779966", "55667788"]

            for i in range(1, 7):
                append_item(
                    si,
                    data=frappe._dict(
                        item_code="_Test Nil Rated Item",
                        gst_hsn_code=random_hsn_codes[i % 4],
                        qty=1.0,
                        rate=1.003,
                    ),
                )

            si.save()
            si.submit()

        for _ in range(11):
            create_invoice()

        _class = GSTR1BooksData(filters=FILTERS)
        data = _class.prepare_mapped_data()
        self.assertDictEq(
            {
                "rounding_difference": {
                    "total_taxable_value": -0.022,
                }
            },
            data["rounding_difference"],
        )

        # Check if HSN Summary is same as Invoice Summary
        for key in _class.DATA_TO_ITEM_FIELD_MAPPING:
            invoice_total = 0
            for invoices in data[GSTR1_SubCategory.NIL_EXEMPT.value].values():
                for row in invoices:
                    invoice_total += row.get(key, 0.0)

            hsn_total = 0
            for row in data[GSTR1_SubCategory.HSN_B2C.value].values():
                hsn_total += row.get(key, 0.0)

            self.assertEqual(flt(hsn_total, 2), flt(invoice_total, 2))

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
                "document_type": GSTR1_B2B_InvoiceType.R.value,
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
        si = create_sales_invoice(
            customer="_Test Registered Customer",
            customer_address="_Test Registered Customer-Billing-1",
        )

        data = GSTR1BooksData(filters=FILTERS).prepare_mapped_data()
        self.assertDictEq(
            {
                "transaction_type": "Invoice",
                "document_value": 100.0,
                "reverse_charge": "N",
                "document_type": GSTR1_B2B_InvoiceType.SEWOP.value,
                "total_taxable_value": 100.0,
                "total_igst_amount": 0.0,
                "total_cgst_amount": 0.0,
                "total_sgst_amount": 0.0,
                "total_cess_amount": 0.0,
                "items": [
                    {
                        "taxable_value": 100.0,
                        "igst_amount": 0.0,
                        "cgst_amount": 0.0,
                        "sgst_amount": 0.0,
                        "cess_amount": 0.0,
                        "tax_rate": 0.0,
                    }
                ],
            },
            data[GSTR1_SubCategory.SEZWOP.value][si.name],
        )

    @change_settings("GST Settings", {"enable_overseas_transactions": 1})
    def test_sez_with_tax(self):
        si = create_sales_invoice(
            customer="_Test Registered Customer",
            customer_address="_Test Registered Customer-Billing-1",
            is_out_state=True,
            is_export_with_gst=True,
        )

        data = GSTR1BooksData(filters=FILTERS).prepare_mapped_data()
        self.assertDictEq(
            {
                "transaction_type": "Invoice",
                "document_value": 118.0,
                "reverse_charge": "N",
                "document_type": GSTR1_B2B_InvoiceType.SEWP.value,
                "total_taxable_value": 100.0,
                "total_igst_amount": 18.0,
                "total_cgst_amount": 0.0,
                "total_sgst_amount": 0.0,
                "total_cess_amount": 0.0,
                "items": [
                    {
                        "taxable_value": 100.0,
                        "igst_amount": 18.0,
                        "cgst_amount": 0.0,
                        "sgst_amount": 0.0,
                        "cess_amount": 0.0,
                        "tax_rate": 18.0,
                    }
                ],
            },
            data[GSTR1_SubCategory.SEZWP.value][si.name],
        )

    @change_settings("GST Settings", {"enable_overseas_transactions": 1})
    def test_deemed_export_transaction(self):
        si = create_sales_invoice(
            customer="_Test Registered Customer",
            customer_address="_Test Registered Customer-Billing-2",
            is_in_state=True,
        )

        data = GSTR1BooksData(filters=FILTERS).prepare_mapped_data()

        self.assertDictEq(
            {
                "transaction_type": "Invoice",
                "document_value": 118.0,
                "reverse_charge": "N",
                "document_type": GSTR1_B2B_InvoiceType.DE.value,
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
            data[GSTR1_SubCategory.DE.value][si.name],
        )

    @change_settings("GST Settings", {"enable_overseas_transactions": 1})
    def test_export_without_tax(self):
        si = create_sales_invoice(
            customer="_Test Foreign Customer",
            customer_address="_Test Foreign Customer-Billing",
        )

        data = GSTR1BooksData(filters=FILTERS).prepare_mapped_data()
        self.assertDictEq(
            {
                "transaction_type": "Invoice",
                "document_value": 100.0,
                "reverse_charge": "N",
                "document_type": "WOPAY",
                "total_taxable_value": 100.0,
                "total_igst_amount": 0.0,
                "total_cgst_amount": 0.0,
                "total_sgst_amount": 0.0,
                "total_cess_amount": 0.0,
                "items": [
                    {
                        "taxable_value": 100.0,
                        "igst_amount": 0.0,
                        "cgst_amount": 0.0,
                        "sgst_amount": 0.0,
                        "cess_amount": 0.0,
                        "tax_rate": 0.0,
                    }
                ],
            },
            data[GSTR1_SubCategory.EXPWOP.value][si.name],
        )

    @change_settings("GST Settings", {"enable_overseas_transactions": 1})
    def test_export_with_tax(self):
        si = create_sales_invoice(
            customer="_Test Foreign Customer",
            customer_address="_Test Foreign Customer-Billing",
            is_out_state=True,
            is_export_with_gst=True,
        )
        # TODO: Update port details

        data = GSTR1BooksData(filters=FILTERS).prepare_mapped_data()
        self.assertDictEq(
            {
                "transaction_type": "Invoice",
                "document_value": 118.0,
                "reverse_charge": "N",
                "document_type": "WPAY",
                "total_taxable_value": 100.0,
                "total_igst_amount": 18.0,
                "total_cgst_amount": 0.0,
                "total_sgst_amount": 0.0,
                "total_cess_amount": 0.0,
                "items": [
                    {
                        "taxable_value": 100.0,
                        "igst_amount": 18.0,
                        "cgst_amount": 0.0,
                        "sgst_amount": 0.0,
                        "cess_amount": 0.0,
                        "tax_rate": 18.0,
                    }
                ],
            },
            data[GSTR1_SubCategory.EXPWP.value][si.name],
        )

    def test_b2cl_transaction(self):
        # Unregistered + Interstate + POS + Value > 1 L
        si = create_sales_invoice(
            customer="_Test Unregistered Customer",
            place_of_supply="27-Maharashtra",
            do_no_save=True,
            is_out_state=True,
            rate=100000.0,
        )

        data = GSTR1BooksData(filters=FILTERS).prepare_mapped_data()
        self.assertDictEq(
            {
                "transaction_type": "Invoice",
                "document_value": 118000.0,
                "reverse_charge": "N",
                "document_type": None,
                "total_taxable_value": 100000.0,
                "total_igst_amount": 18000.0,
                "total_cgst_amount": 0.0,
                "total_sgst_amount": 0.0,
                "total_cess_amount": 0.0,
                "items": [
                    {
                        "taxable_value": 100000.0,
                        "igst_amount": 18000.0,
                        "cgst_amount": 0.0,
                        "sgst_amount": 0.0,
                        "cess_amount": 0.0,
                        "tax_rate": 18.0,
                    }
                ],
            },
            data[GSTR1_SubCategory.B2CL.value][si.name],
        )

    def test_cdnr_transaction(self):
        # Create B2B and CN from SI
        si = create_sales_invoice(
            customer="_Test Registered Customer",
            is_in_state=True,
        )

        cn = make_sales_return(si.name).save()
        cn.submit()

        data = GSTR1BooksData(filters=FILTERS).prepare_mapped_data()
        self.assertDictEq(
            {
                "transaction_type": "Credit Note",
                "document_value": -118.0,
                "reverse_charge": "N",
                "document_type": GSTR1_B2B_InvoiceType.R.value,
                "total_taxable_value": -100.0,
                "total_igst_amount": 0.0,
                "total_cgst_amount": -9.0,
                "total_sgst_amount": -9.0,
                "total_cess_amount": 0.0,
                "items": [
                    {
                        "taxable_value": -100.0,
                        "igst_amount": 0.0,
                        "cgst_amount": -9.0,
                        "sgst_amount": -9.0,
                        "cess_amount": 0.0,
                        "tax_rate": 18.0,
                    }
                ],
            },
            data[GSTR1_SubCategory.CDNR.value][cn.name],
        )

        self.assertDictEq(
            {
                "transaction_type": "Invoice",
                "document_value": 118.0,
                "reverse_charge": "N",
                "document_type": GSTR1_B2B_InvoiceType.R.value,
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
            data[GSTR1_SubCategory.B2B_REGULAR.value][si.name],
        )

    @change_settings("GST Settings", {"enable_overseas_transactions": 1})
    def test_cdnur_transaction(self):
        # Create Export and CN from SI
        si = create_sales_invoice(
            customer="_Test Foreign Customer",
            customer_address="_Test Foreign Customer-Billing",
            is_out_state=True,
            is_export_with_gst=True,
        )

        cn = make_sales_return(si.name).save()
        cn.submit()

        data = GSTR1BooksData(filters=FILTERS).prepare_mapped_data()
        self.assertDictEq(
            {
                "transaction_type": "Credit Note",
                "document_value": -118.0,
                "place_of_supply": "96-Other Countries",
                "reverse_charge": "N",
                "document_type": "EXPWP",
                "total_taxable_value": -100.0,
                "total_igst_amount": -18.0,
                "total_cgst_amount": 0.0,
                "total_sgst_amount": 0.0,
                "total_cess_amount": 0.0,
                "items": [
                    {
                        "taxable_value": -100.0,
                        "igst_amount": -18.0,
                        "cgst_amount": 0.0,
                        "sgst_amount": 0.0,
                        "cess_amount": 0.0,
                        "tax_rate": 18.0,
                    }
                ],
            },
            data[GSTR1_SubCategory.CDNUR.value][cn.name],
        )

    def test_nil_exempt_transaction(self):
        # Create B2B (CGST) and B2C (IGST) Invoice
        b2b_si = create_sales_invoice(
            customer="_Test Registered Customer",
            item_code="_Test Nil Rated Item",
            is_in_state=True,
        )

        b2c_si = create_sales_invoice(
            customer="_Test Unregistered Customer",
            item_code="_Test Nil Rated Item",
            is_in_state=True,
        )

        data = GSTR1BooksData(filters=FILTERS).prepare_mapped_data()
        self.assertDictEq(
            {
                "transaction_type": "Invoice",
                "document_value": 100.0,
                "reverse_charge": "N",
                "document_number": b2b_si.name,
                "document_type": "Intra-State supplies to registered persons",
                "total_taxable_value": 100.0,
                "nil_rated_amount": 100.0,
                "exempted_amount": 0.0,
                "non_gst_amount": 0.0,
            },
            data[GSTR1_SubCategory.NIL_EXEMPT.value][
                "Intra-State supplies to registered persons"
            ][0],
        )

        self.assertDictEq(
            {
                "transaction_type": "Invoice",
                "document_value": 100.0,
                "reverse_charge": "N",
                "document_number": b2c_si.name,
                "document_type": "Intra-State supplies to unregistered persons",
                "total_taxable_value": 100.0,
                "nil_rated_amount": 100.0,
                "exempted_amount": 0.0,
                "non_gst_amount": 0.0,
            },
            data[GSTR1_SubCategory.NIL_EXEMPT.value][
                "Intra-State supplies to unregistered persons"
            ][0],
        )

    def test_b2cs_transaction(self):
        # 3-4 transactions with different POS
        place_of_supplies = {
            "27-Maharashtra": {
                "is_in_state": False,
                "is_out_state": True,
                "igst_rate": 18.0,
            },
            "24-Gujarat": {
                "is_in_state": True,
                "is_out_state": False,
                "cgst_rate": 9.0,
                "sgst_rate": 9.0,
            },
            "33-Tamil Nadu": {
                "is_in_state": False,
                "is_out_state": True,
                "igst_rate": 18.0,
            },
            "29-Karnataka": {
                "is_in_state": False,
                "is_out_state": True,
                "igst_rate": 18.0,
            },
        }

        si_s = []
        for pos, details in place_of_supplies.items():
            si_s.append(
                create_sales_invoice(
                    customer="_Test Unregistered Customer",
                    place_of_supply=pos,
                    is_in_state=details["is_in_state"],
                    is_out_state=details["is_out_state"],
                )
            )

        data = GSTR1BooksData(filters=FILTERS).prepare_mapped_data()

        for si in si_s:
            igst_rate = (
                place_of_supplies[si.place_of_supply].get("igst_rate", 0.0)
                / 100
                * si.total
            )
            cgst_rate = (
                place_of_supplies[si.place_of_supply].get("cgst_rate", 0.0)
                / 100
                * si.total
            )
            sgst_rate = (
                place_of_supplies[si.place_of_supply].get("sgst_rate", 0.0)
                / 100
                * si.total
            )
            self.assertDictEq(
                {
                    "document_value": 118.0,
                    "document_number": si.name,
                    "document_type": "OE",
                    "transaction_type": "Invoice",
                    "place_of_supply": si.place_of_supply,
                    "tax_rate": 18.0,
                    "total_taxable_value": 100.0,
                    "total_igst_amount": igst_rate,
                    "total_cgst_amount": cgst_rate,
                    "total_sgst_amount": sgst_rate,
                    "total_cess_amount": 0.0,
                },
                data[GSTR1_SubCategory.B2CS.value][f"{si.place_of_supply} - 18.0"][0],
            )

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
        si = create_sales_invoice(
            customer="_Test Registered Customer",
            is_in_state=True,
            items=[
                {
                    "item_code": "_Test Nil Rated Item",
                    "qty": 1.0,
                    "rate": 100.0,
                },
                {
                    "item_code": "_Test Trading Goods 1",
                    "qty": 1.0,
                    "rate": 100.0,
                },
            ],
        )

        data = GSTR1BooksData(filters=FILTERS).prepare_mapped_data()

        self.assertDictEq(
            {
                "transaction_type": "Invoice",
                "document_value": 218.0,
                "place_of_supply": "24-Gujarat",
                "reverse_charge": "N",
                "document_type": GSTR1_B2B_InvoiceType.R.value,
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
                    },
                ],
            },
            data[GSTR1_SubCategory.B2B_REGULAR.value][si.name],
        )

        self.assertDictEq(
            {
                "transaction_type": "Invoice",
                "document_value": 218.0,
                "reverse_charge": "N",
                "document_number": si.name,
                "document_type": "Intra-State supplies to registered persons",
                "total_taxable_value": 100.0,
                "nil_rated_amount": 100.0,
                "exempted_amount": 0.0,
                "non_gst_amount": 0.0,
            },
            data[GSTR1_SubCategory.NIL_EXEMPT.value][
                "Intra-State supplies to registered persons"
            ][0],
        )

    def test_hsn_summary_with_bifurcation(self):
        si = create_sales_invoice(
            customer="_Test Registered Customer",
            is_in_state=True,
            gst_hsn_code="55885588",
        )

        item = si.items[0]

        data = GSTR1BooksData(filters=FILTERS).prepare_mapped_data()
        uom = get_full_gst_uom(item.uom)
        key = f"{item.gst_hsn_code} - {uom} - {18.0}"

        self.assertDictEq(
            {
                "hsn_code": item.gst_hsn_code,
                "uom": uom,
                "quantity": 1.0,
                "tax_rate": 18.0,
                "total_taxable_value": 100.0,
                "total_igst_amount": 0.0,
                "total_cgst_amount": 9.0,
                "total_sgst_amount": 9.0,
                "total_cess_amount": 0.0,
                "document_value": 118.0,
                "document_type": "HSN Summary - B2B",
            },
            data[GSTR1_SubCategory.HSN_B2B.value][key],
        )

    def test_hsn_summary_without_bifurcation(self):
        # create 2023-2024 fiscal year
        fiscal_year = frappe.new_doc("Fiscal Year")
        fiscal_year.update(
            {
                "year_start_date": "2025-04-01",
                "year_end_date": "2026-03-31",
                "year": "2025-2026",
            }
        ).insert(ignore_if_duplicate=True)

        items = [
            {
                "item_code": "_Test Trading Goods 1",
                "qty": 1.0,
                "rate": 100.0,
                "gst_hsn_code": "55885588",
                "uom": "Nos",
            },
            {
                "item_code": "_Test Nil Rated Item",
                "qty": 1.0,
                "rate": 100.0,
                "gst_hsn_code": "55998899",
                "uom": "Nos",
            },
        ]

        # TODO: Service Item with Others as UOM

        si = create_sales_invoice(
            customer="_Test Registered Customer",
            is_in_state=True,
            items=items,
            posting_date=getdate("2025-04-01"),
            set_posting_time=1,
        )

        filters = frappe._dict(
            {
                **FILTERS,
                "year": 2025,
                "month_or_quarter": "April",
                "from_date": getdate("2025-04-01"),
                "to_date": getdate("2025-04-30"),
            }
        )
        data = GSTR1BooksData(filters=filters).prepare_mapped_data()
        item = si.items[0]
        uom = get_full_gst_uom(item.uom)
        key = f"{item.gst_hsn_code} - {uom} - {18.0}"

        self.assertDictEq(
            {
                "hsn_code": item.gst_hsn_code,
                "uom": uom,
                "quantity": 1.0,
                "tax_rate": 18.0,
                "total_taxable_value": 100.0,
                "total_igst_amount": 0.0,
                "total_cgst_amount": 9.0,
                "total_sgst_amount": 9.0,
                "total_cess_amount": 0.0,
                "document_value": 118.0,
            },
            data[GSTR1_SubCategory.HSN.value][key],
        )

        item = si.items[1]
        uom = get_full_gst_uom(item.uom)
        key = f"{item.gst_hsn_code} - {uom} - {0.0}"

        self.assertDictEq(
            {
                "hsn_code": item.gst_hsn_code,
                "uom": uom,
                "quantity": 1.0,
                "tax_rate": 0.0,
                "total_taxable_value": 100.0,
                "total_igst_amount": 0.0,
                "total_cgst_amount": 0.0,
                "total_sgst_amount": 0.0,
                "total_cess_amount": 0.0,
                "document_value": 100.0,
            },
            data[GSTR1_SubCategory.HSN.value][key],
        )


def setup_cess_account(company="_Test Indian Registered Company"):
    # create cess account
    create_default_company_account(company, "Output Tax CESS", "Duties and Taxes")
    account = frappe.db.get_value(
        "Account",
        {"account_name": "Output Tax CESS", "company": company, "is_group": 0},
    )

    try:
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

    except frappe.ValidationError:
        pass

    return account
