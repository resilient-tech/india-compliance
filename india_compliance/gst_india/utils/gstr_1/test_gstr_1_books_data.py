import frappe
from erpnext.accounts.doctype.sales_invoice.mapper import make_sales_return
from frappe.tests import IntegrationTestCase, change_settings
from frappe.utils import flt, getdate

from india_compliance.gst_india.doctype.gst_return_log.generate_gstr_1 import SummarizeGSTR1
from india_compliance.gst_india.doctype.gstr_1.gstr_1_export import GovExcel
from india_compliance.gst_india.overrides.company import create_default_company_account
from india_compliance.gst_india.utils import get_full_gst_uom
from india_compliance.gst_india.utils.gstr_1 import (
    B2BInvoiceType,
    JsonKey,
    SubCategory,
)
from india_compliance.gst_india.utils.gstr_1 import (
    DocField as doc,
)
from india_compliance.gst_india.utils.gstr_1.gstr_1_books_map import (
    BooksDataMapper,
    GSTR1BooksData,
)
from india_compliance.gst_india.utils.gstr_1.gstr_1_data import GSTR1Invoices
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
                "document_type": B2BInvoiceType.R.value,
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
            data[SubCategory.B2B_REGULAR.value][si.name],
        )

    def test_b2b_regular_transaction_with_gst_inclusive_price(self):
        setup_cess_account()
        si = create_sales_invoice(customer="_Test Registered Customer", do_not_submit=True)
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
                "document_type": B2BInvoiceType.R.value,
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
            data[SubCategory.B2B_REGULAR.value][si.name],
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
                    data=frappe._dict(gst_hsn_code=random_hsn_codes[i % 4], qty=1.0, rate=1.003),
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
            for row in data[SubCategory.B2B_REGULAR.value].values():
                invoice_total += row.get(key, 0.0)

            hsn_total = 0
            for row in data[SubCategory.HSN_B2B.value].values():
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
                    data=frappe._dict(gst_hsn_code=random_hsn_codes[i % 4], qty=1.0, rate=1.003),
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
            for invoices in data[SubCategory.B2CS.value].values():
                for row in invoices:
                    invoice_total += row.get(key, 0.0)

            hsn_total = 0
            for row in data[SubCategory.HSN_B2C.value].values():
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
                    "total_igst_amount": 0.0,
                    "total_cgst_amount": 0.0,
                    "total_sgst_amount": 0.0,
                    "total_cess_amount": 0.0,
                }
            },
            data["rounding_difference"],
        )

        # Check if HSN Summary is same as Invoice Summary
        for key in _class.DATA_TO_ITEM_FIELD_MAPPING:
            invoice_total = 0
            for invoices in data[SubCategory.NIL_EXEMPT.value].values():
                for row in invoices:
                    invoice_total += row.get(key, 0.0)

            hsn_total = 0
            for row in data[SubCategory.HSN_B2C.value].values():
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
                "document_type": B2BInvoiceType.R.value,
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
            data[SubCategory.B2B_REVERSE_CHARGE.value][si.name],
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
                "document_type": B2BInvoiceType.SEWOP.value,
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
            data[SubCategory.SEZWOP.value][si.name],
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
                "document_type": B2BInvoiceType.SEWP.value,
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
            data[SubCategory.SEZWP.value][si.name],
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
                "document_type": B2BInvoiceType.DE.value,
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
            data[SubCategory.DE.value][si.name],
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
            data[SubCategory.EXPWOP.value][si.name],
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
            data[SubCategory.EXPWP.value][si.name],
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
            data[SubCategory.B2CL.value][si.name],
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
                "document_type": B2BInvoiceType.R.value,
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
            data[SubCategory.CDNR.value][cn.name],
        )

        self.assertDictEq(
            {
                "transaction_type": "Invoice",
                "document_value": 118.0,
                "reverse_charge": "N",
                "document_type": B2BInvoiceType.R.value,
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
            data[SubCategory.B2B_REGULAR.value][si.name],
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
            data[SubCategory.CDNUR.value][cn.name],
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
            data[SubCategory.NIL_EXEMPT.value]["Intra-State supplies to registered persons"][0],
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
            data[SubCategory.NIL_EXEMPT.value]["Intra-State supplies to unregistered persons"][0],
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
            igst_rate = place_of_supplies[si.place_of_supply].get("igst_rate", 0.0) / 100 * si.total
            cgst_rate = place_of_supplies[si.place_of_supply].get("cgst_rate", 0.0) / 100 * si.total
            sgst_rate = place_of_supplies[si.place_of_supply].get("sgst_rate", 0.0) / 100 * si.total
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
                data[SubCategory.B2CS.value][f"{si.place_of_supply} - 18.0"][0],
            )

    @change_settings("GST Settings", {"enable_overseas_transactions": 1})
    def test_b2cs_overseas_intra_state_credit_note(self):
        # Foreign customer with an Overseas billing address (no GSTIN), but the supply is
        # delivered within India to a Gujarat shipping address (POS = 24-Gujarat, not
        # "96-Other Countries").this is a B2C intra-state supply
        # NOT exports/CDNUR.
        si = create_sales_invoice(
            customer="_Test Foreign Customer-1",
            customer_address="_Test Foreign Customer-1-Billing",
            shipping_address_name="_Test Foreign Customer-1-Shipping",
            place_of_supply="24-Gujarat",
            is_in_state=True,
        )

        cn = make_sales_return(si.name).save()
        cn.submit()

        data = GSTR1BooksData(filters=FILTERS).prepare_mapped_data()

        b2cs_rows = data[SubCategory.B2CS.value]["24-Gujarat - 18.0"]
        by_doc = {row["document_number"]: row for row in b2cs_rows}

        # Both SI and CN land in B2CS under the same POS + rate key
        self.assertIn(si.name, by_doc)
        self.assertIn(cn.name, by_doc)

        self.assertEqual(
            by_doc[si.name]["total_taxable_value"] + by_doc[cn.name]["total_taxable_value"],
            0.0,
        )

        self.assertNotIn(cn.name, data.get(SubCategory.CDNUR.value, {}))

    def test_cdnur_credit_note_not_double_counted_in_b2cs(self):
        # Inter-state B2C (Unregistered) invoice ABOVE the B2CL threshold (> 1 lakh),
        # then a PARTIAL credit note whose own value is BELOW the threshold.
        # the CN belongs only in CDNUR (Table 9B)
        si = create_sales_invoice(
            customer="_Test Unregistered Customer",
            place_of_supply="27-Maharashtra",  # inter-state vs company GSTIN 24...
            is_out_state=True,
            qty=10,
            rate=20000,  # original invoice value 2,00,000 > 1,00,000
        )

        cn = make_sales_return(si.name)
        cn.items[0].qty = -1  # partial return: CN own value 20,000 < 1,00,000
        cn.save()
        cn.submit()

        data = GSTR1BooksData(filters=FILTERS).prepare_mapped_data()

        # CN must appear in CDNUR
        self.assertIn(cn.name, data.get(SubCategory.CDNUR.value, {}))

        # CN must NOT also appear anywhere in B2CS (any POS + rate list)
        b2cs = data.get(SubCategory.B2CS.value, {})
        b2cs_docs = {row["document_number"] for rows in b2cs.values() for row in rows}
        self.assertNotIn(cn.name, b2cs_docs)

    def test_b2cs_credit_note_below_b2cl_limit_stays_in_b2cs(self):
        si = create_sales_invoice(
            customer="_Test Unregistered Customer",
            place_of_supply="27-Maharashtra",  # inter-state vs company GSTIN 24...
            is_out_state=True,
            qty=1,
            rate=5000,  # original invoice value 5,900 < 1,00,000
        )

        cn = make_sales_return(si.name).save()
        cn.submit()

        data = GSTR1BooksData(filters=FILTERS).prepare_mapped_data()

        # CN lands in B2CS under the POS + rate key, with negative (return) values
        b2cs_rows = data[SubCategory.B2CS.value]["27-Maharashtra - 18.0"]
        cn_row = next(row for row in b2cs_rows if row["document_number"] == cn.name)
        self.assertDictEq(
            {
                "transaction_type": "Credit Note",
                "document_type": "OE",
                "place_of_supply": "27-Maharashtra",
                "total_taxable_value": -5000.0,
                "total_igst_amount": -900.0,
                "tax_rate": 18.0,
            },
            cn_row,
        )

        # CN must NOT leak into CDNUR
        self.assertNotIn(cn.name, data.get(SubCategory.CDNUR.value, {}))

    def test_cdnur_full_value_b2cl_credit_note(self):
        # Full credit note of an inter-state B2C (Unregistered) invoice ABOVE the B2CL
        # threshold.The CN belongs in CDNUR (Table 9B) with type "B2CL".
        si = create_sales_invoice(
            customer="_Test Unregistered Customer",
            place_of_supply="27-Maharashtra",
            is_out_state=True,
            qty=10,
            rate=20000,  # original invoice value 2,00,000 > 1,00,000
        )

        cn = make_sales_return(si.name).save()
        cn.submit()

        data = GSTR1BooksData(filters=FILTERS).prepare_mapped_data()

        self.assertDictEq(
            {
                "transaction_type": "Credit Note",
                "document_number": cn.name,
                "document_type": "B2CL",
                "place_of_supply": "27-Maharashtra",
                "total_taxable_value": -200000.0,
                "total_igst_amount": -36000.0,
                "total_cgst_amount": 0.0,
                "total_sgst_amount": 0.0,
            },
            data[SubCategory.CDNUR.value][cn.name],
        )

        # CN must NOT also appear anywhere in B2CS
        b2cs = data.get(SubCategory.B2CS.value, {})
        b2cs_docs = {row["document_number"] for rows in b2cs.values() for row in rows}
        self.assertNotIn(cn.name, b2cs_docs)

    def test_cdnur_debit_note(self):
        # Debit note (is_debit_note) against an inter-state B2C (Unregistered) invoice ABOVE
        # the B2CL threshold classified under CDNUR (Table 9B) with type "B2CL".
        si = create_sales_invoice(
            customer="_Test Unregistered Customer",
            place_of_supply="27-Maharashtra",
            is_out_state=True,
            qty=10,
            rate=20000,  # original invoice value 2,00,000 > 1,00,000
        )

        dn = make_sales_return(si.name)
        dn.is_return = 0
        dn.is_debit_note = 1
        for item in dn.items:
            item.qty = abs(item.qty)  # debit note: positive quantities
        dn.save()
        dn.submit()

        data = GSTR1BooksData(filters=FILTERS).prepare_mapped_data()

        self.assertDictEq(
            {
                "transaction_type": "Debit Note",
                "document_number": dn.name,
                "document_type": "B2CL",
                "place_of_supply": "27-Maharashtra",
                "total_taxable_value": 200000.0,
                "total_igst_amount": 36000.0,
            },
            data[SubCategory.CDNUR.value][dn.name],
        )

        # DN must NOT appear in B2CS
        b2cs = data.get(SubCategory.B2CS.value, {})
        b2cs_docs = {row["document_number"] for rows in b2cs.values() for row in rows}
        self.assertNotIn(dn.name, b2cs_docs)

    @change_settings("GST Settings", {"enable_overseas_transactions": 1})
    def test_cdnur_export_credit_note_without_tax(self):
        # Credit note of an export invoice WITHOUT payment of tax. The CN belongs
        # in CDNUR (Table 9B) with type "EXPWOP" and zero IGST.
        si = create_sales_invoice(
            customer="_Test Foreign Customer",
            customer_address="_Test Foreign Customer-Billing",
        )

        cn = make_sales_return(si.name).save()
        cn.submit()

        data = GSTR1BooksData(filters=FILTERS).prepare_mapped_data()

        self.assertDictEq(
            {
                "transaction_type": "Credit Note",
                "document_number": cn.name,
                "document_type": "EXPWOP",
                "place_of_supply": "96-Other Countries",
                "total_taxable_value": -100.0,
                "total_igst_amount": 0.0,
            },
            data[SubCategory.CDNUR.value][cn.name],
        )

    def test_ecommerce_invoices_aggregate_under_supecom(self):
        ecommerce_gstin_1 = "20ALYPD6528PQC5"
        ecommerce_gstin_2 = "29AABCF8078M1C8"

        # Two invoices for operator 1 (count is row-based, not invoice-based)
        create_sales_invoice(
            customer="_Test Registered Customer",
            is_in_state=True,
            ecommerce_gstin=ecommerce_gstin_1,
        )
        create_sales_invoice(
            customer="_Test Unregistered Customer",
            place_of_supply="27-Maharashtra",
            is_in_state=False,
            is_out_state=True,
            ecommerce_gstin=ecommerce_gstin_1,
        )

        # One invoice for operator 2
        create_sales_invoice(
            customer="_Test Registered Customer",
            is_in_state=True,
            ecommerce_gstin=ecommerce_gstin_2,
        )

        data = GSTR1BooksData(filters=FILTERS).prepare_mapped_data()

        self.assertIn(SubCategory.SUPECOM_52.value, data)
        supecom_rows = data[SubCategory.SUPECOM_52.value]
        self.assertIn(ecommerce_gstin_1, supecom_rows)
        self.assertIn(ecommerce_gstin_2, supecom_rows)
        self.assertEqual(len(supecom_rows), 2)

        row_1 = supecom_rows[ecommerce_gstin_1]
        row_2 = supecom_rows[ecommerce_gstin_2]

        for row, gstin in ((row_1, ecommerce_gstin_1), (row_2, ecommerce_gstin_2)):
            self.assertEqual(row[doc.DOC_TYPE], SubCategory.SUPECOM_52.value)
            self.assertEqual(row[doc.ECOMMERCE_GSTIN], gstin)
            self.assertIn(doc.ECOMMERCE_OPERATOR_NAME, row)
            self.assertNotIn("no_of_records", row)
            self.assertGreater(row[doc.TAXABLE_VALUE], 0)
            # Frontend summary/detail reads invoice-level total tax fields.
            self.assertIn(doc.IGST, row)
            self.assertIn(doc.CGST, row)
            self.assertIn(doc.SGST, row)

        # Operator 1 has in-state + out-state invoices, so it should have both
        # IGST and CGST/SGST in aggregate.
        self.assertGreater(row_1[doc.IGST], 0)
        self.assertGreater(row_1[doc.CGST], 0)
        self.assertGreater(row_1[doc.SGST], 0)

    @change_settings(
        "GST Settings",
        {
            "enable_reverse_charge_in_sales": 1,
            "enable_sales_through_ecommerce_operators": 1,
        },
    )
    def test_9_5_reported_only_in_supecom(self):
        si = create_sales_invoice(
            customer="_Test Registered Customer",
            is_reverse_charge=True,
            is_in_state=True,
            is_in_state_rcm=True,
            ecommerce_gstin="20ALYPD6528PQC5",
        )

        data = GSTR1BooksData(filters=FILTERS).prepare_mapped_data()

        self.assertIn(SubCategory.SUPECOM_9_5.value, data)
        supecom = data[SubCategory.SUPECOM_9_5.value]
        self.assertIn("20ALYPD6528PQC5", supecom)
        self.assertGreater(supecom["20ALYPD6528PQC5"][doc.TAXABLE_VALUE], 0)

        self.assertNotIn(si.name, data.get(SubCategory.B2B_REVERSE_CHARGE.value, {}))
        for hsn in (
            SubCategory.HSN_B2B.value,
            SubCategory.HSN_B2C.value,
            SubCategory.HSN.value,
        ):
            self.assertNotIn(hsn, data)

        overview = {row["description"]: row for row in GSTR1Invoices(FILTERS).get_overview()}
        self.assertNotIn(si.name, overview[SubCategory.B2B_REVERSE_CHARGE.value]["unique_records"])
        self.assertIn(si.name, overview[SubCategory.SUPECOM_9_5.value]["unique_records"])

    @change_settings("GST Settings", {"enable_sales_through_ecommerce_operators": 1})
    def test_52_reported_in_both_primary_and_supecom(self):
        si = create_sales_invoice(
            customer="_Test Registered Customer",
            is_in_state=True,
            ecommerce_gstin="20ALYPD6528PQC5",
        )

        data = GSTR1BooksData(filters=FILTERS).prepare_mapped_data()

        self.assertIn(si.name, data.get(SubCategory.B2B_REGULAR.value, {}))
        self.assertIn(SubCategory.SUPECOM_52.value, data)
        self.assertIn("20ALYPD6528PQC5", data[SubCategory.SUPECOM_52.value])

    def test_supecom_rounding_at_invoice_level(self):
        """
        Rounding must happen at the invoice level before aggregating across
        invoices for the same operator. Without invoice-level rounding the
        operator total diverges from the sum of per-invoice rounded amounts.
        """
        supply_type = SubCategory.SUPECOM_52.value
        eco_gstin = "20ALYPD6528PQC5"

        def make_item(invoice_no, igst):
            return frappe._dict(
                invoice_no=invoice_no,
                ecommerce_gstin=eco_gstin,
                taxable_value=0,
                igst_amount=igst,
                cgst_amount=0,
                sgst_amount=0,
                total_cess_amount=0,
            )

        grouped_data = {
            supply_type: {
                "INV-ECOM-001": [make_item("INV-ECOM-001", 0.006)],
                "INV-ECOM-002": [make_item("INV-ECOM-002", 0.006)],
            }
        }

        prepared_data = {}
        BooksDataMapper().process_data_for_supecom(grouped_data, prepared_data)

        row = prepared_data[supply_type][eco_gstin]
        # Each invoice rounds to 0.01; two invoices → 0.02
        self.assertEqual(row[doc.IGST], flt(0.01 + 0.01, 2))

    def test_gov_excel_process_data_keeps_supecom_rows(self):
        ecommerce_gstin = "20ALYPD6528PQC5"

        books_data = {
            "aggregate_data": {},
            SubCategory.SUPECOM_52.value: [
                {
                    doc.DOC_TYPE: SubCategory.SUPECOM_52.value,
                    doc.ECOMMERCE_GSTIN: ecommerce_gstin,
                    doc.ECOMMERCE_OPERATOR_NAME: "Test Operator",
                    doc.TAXABLE_VALUE: 100.0,
                    doc.IGST: 18.0,
                    doc.CGST: 0.0,
                    doc.SGST: 0.0,
                    doc.CESS: 0.0,
                }
            ],
        }
        processed = GovExcel().process_data(books_data)

        self.assertIn(JsonKey.SUPECOM.value, processed)
        self.assertTrue(processed[JsonKey.SUPECOM.value])

        supecom_row = processed[JsonKey.SUPECOM.value][0]
        self.assertEqual(supecom_row[doc.ECOMMERCE_GSTIN], ecommerce_gstin)
        self.assertEqual(supecom_row[doc.ECOMMERCE_OPERATOR_NAME], "Test Operator")
        self.assertGreater(supecom_row[doc.TAXABLE_VALUE], 0)

    def test_supecom_excel_headers_include_operator_name(self):
        headers = GovExcel().get_category_headers(JsonKey.SUPECOM.value)

        operator_name_header = next(
            header for header in headers if header.get("label") == "E-Commerce Operator Name"
        )
        self.assertEqual(operator_name_header.get("fieldname"), doc.ECOMMERCE_OPERATOR_NAME)

    def test_supecom_summary_counts_rows(self):
        for subcategory in (
            SubCategory.SUPECOM_52.value,
            SubCategory.SUPECOM_9_5.value,
        ):
            data = {
                subcategory: [
                    {
                        doc.DOC_TYPE: subcategory,
                        doc.ECOMMERCE_GSTIN: "20ALYPD6528PQC5",
                        doc.TAXABLE_VALUE: 100.0,
                        doc.IGST: 18.0,
                        doc.CGST: 0.0,
                        doc.SGST: 0.0,
                        doc.CESS: 0.0,
                    },
                    {
                        doc.DOC_TYPE: subcategory,
                        doc.ECOMMERCE_GSTIN: "29AABCF8078M1C8",
                        doc.TAXABLE_VALUE: 200.0,
                        doc.IGST: 0.0,
                        doc.CGST: 18.0,
                        doc.SGST: 18.0,
                        doc.CESS: 0.0,
                    },
                ]
            }

            summary_row = SummarizeGSTR1().get_subcategory_summary(data)[subcategory]

            self.assertEqual(summary_row["no_of_records"], 2)
            self.assertEqual(summary_row[doc.TAXABLE_VALUE], 300.0)

            if subcategory == SubCategory.SUPECOM_52.value:
                self.assertFalse(summary_row["consider_in_total_taxable_value"])
            else:
                self.assertTrue(summary_row["consider_in_total_taxable_value"])

            self.assertFalse(summary_row["consider_in_total_tax"])

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
                "document_type": B2BInvoiceType.R.value,
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
            data[SubCategory.B2B_REGULAR.value][si.name],
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
            data[SubCategory.NIL_EXEMPT.value]["Intra-State supplies to registered persons"][0],
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
            data[SubCategory.HSN_B2B.value][key],
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
            data[SubCategory.HSN.value][key],
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
            data[SubCategory.HSN.value][key],
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
