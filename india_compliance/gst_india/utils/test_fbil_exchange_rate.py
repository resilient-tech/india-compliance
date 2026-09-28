# Copyright (c) 2026, Resilient Tech and contributors
# For license information, please see license.txt

from unittest.mock import patch

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import flt

from india_compliance.gst_india.utils.fbil_exchange_rate import (
    fetch_fbil_reference_rates,
    get_fbil_exchange_rate,
    set_fbil_conversion_rate,
    sync_fbil_currency_exchange,
    upsert_currency_exchange,
)

SAMPLE_FBIL_RESPONSE = [
    {
        "processRunDate": "2026-09-21 00:00:00",
        "subProdName": "INR / 1 EUR",
        "displayTime": "2026-09-21 13:00:00",
        "rate": 109.9033,
        "comments": "",
    },
    {
        "processRunDate": "2026-09-21 00:00:00",
        "subProdName": "INR / 1 USD",
        "displayTime": "2026-09-21 13:00:00",
        "rate": 95.7991,
        "comments": "",
    },
    {
        "processRunDate": "2026-09-21 00:00:00",
        "subProdName": "INR / 100 JPY",
        "displayTime": "2026-09-21 13:00:00",
        "rate": 64.14,
        "comments": "",
    },
    {
        "processRunDate": "2026-09-18 00:00:00",
        "subProdName": "INR / 1 EUR",
        "displayTime": "2026-09-18 13:00:00",
        "rate": 109.9885,
        "comments": "",
    },
]

INDIAN_COMPANY = "_Test Indian Registered Company"
FOREIGN_COMPANY = "_Test Foreign Company"


def mock_fbil_response(mock_get, payload=SAMPLE_FBIL_RESPONSE):
    mock_get.return_value.json.return_value = payload
    mock_get.return_value.raise_for_status.return_value = None


class TestFBILExchangeRate(FrappeTestCase):
    def setUp(self):
        self.set_enabled(1)
        frappe.db.delete("Currency Exchange", {"to_currency": "INR", "from_currency": ("in", ("EUR", "USD"))})

    def tearDown(self):
        self.set_enabled(0)

    def set_enabled(self, value):
        frappe.db.set_single_value("GST Settings", "enable_fbil_exchange_rate", value)
        frappe.clear_document_cache("GST Settings", "GST Settings")

    @patch("india_compliance.gst_india.utils.fbil_exchange_rate.requests.get")
    def test_fetch_filters_supported_currencies(self, mock_get):
        mock_fbil_response(mock_get)

        rows = fetch_fbil_reference_rates("2026-09-18", "2026-09-21", currencies=("EUR", "USD"))

        self.assertEqual(
            [(str(r.date), r.currency, r.rate) for r in rows],
            [
                ("2026-09-18", "EUR", 109.9885),
                ("2026-09-21", "EUR", 109.9033),
                ("2026-09-21", "USD", 95.7991),
            ],
        )

        params = mock_get.call_args.kwargs["params"]
        self.assertEqual(params["fromDate"], "2026-09-18")
        self.assertEqual(params["toDate"], "2026-09-21")

    @patch("india_compliance.gst_india.utils.fbil_exchange_rate.requests.get")
    def test_sync_is_idempotent(self, mock_get):
        mock_fbil_response(mock_get)

        result = sync_fbil_currency_exchange(
            currencies=("EUR",), from_date="2026-09-18", to_date="2026-09-21"
        )
        self.assertFalse(result.skipped)
        self.assertEqual((result.created, result.updated, result.unchanged), (2, 0, 0))

        rate = frappe.db.get_value(
            "Currency Exchange",
            {"date": "2026-09-21", "from_currency": "EUR", "to_currency": "INR"},
            "exchange_rate",
        )
        self.assertEqual(flt(rate, 6), 109.9033)

        result = sync_fbil_currency_exchange(
            currencies=("EUR",), from_date="2026-09-18", to_date="2026-09-21"
        )
        self.assertEqual((result.created, result.updated, result.unchanged), (0, 0, 2))

    @patch("india_compliance.gst_india.utils.fbil_exchange_rate.requests.get")
    def test_sync_skipped_when_disabled(self, mock_get):
        self.set_enabled(0)

        result = sync_fbil_currency_exchange()

        self.assertTrue(result.skipped)
        mock_get.assert_not_called()

    def test_get_rate_falls_back_to_previous_business_day(self):
        upsert_currency_exchange("2026-09-18", "EUR", 109.9885)

        rate = get_fbil_exchange_rate("EUR", "2026-09-20", fetch_if_missing=False)
        self.assertEqual(rate, 109.9885)

        self.assertIsNone(get_fbil_exchange_rate("EUR", "2026-09-17", fetch_if_missing=False))
        self.assertEqual(get_fbil_exchange_rate("INR", "2026-09-17", fetch_if_missing=False), 1.0)

    @patch("india_compliance.gst_india.utils.fbil_exchange_rate.requests.get")
    def test_get_rate_fetches_when_missing(self, mock_get):
        mock_fbil_response(mock_get)

        rate = get_fbil_exchange_rate("EUR", "2026-09-22")

        self.assertEqual(rate, 109.9033)
        self.assertTrue(
            frappe.db.exists(
                "Currency Exchange",
                {"date": "2026-09-21", "from_currency": "EUR", "to_currency": "INR"},
            )
        )

    def test_conversion_rate_is_set_from_fbil(self):
        upsert_currency_exchange("2026-09-21", "EUR", 109.9033)

        doc = self.make_invoice(conversion_rate=1.0)
        set_fbil_conversion_rate(doc)

        self.assertEqual(doc.conversion_rate, 109.9033)

    def test_conversion_rate_is_not_changed_when_not_applicable(self):
        upsert_currency_exchange("2026-09-21", "EUR", 109.9033)

        for doc in (
            self.make_invoice(company=FOREIGN_COMPANY),
            self.make_invoice(currency="INR"),
            self.make_invoice(currency="AED"),
            self.make_invoice(is_opening="Yes"),
            self.make_invoice(is_return=1, return_against="SINV-0001"),
        ):
            set_fbil_conversion_rate(doc)
            self.assertEqual(doc.conversion_rate, 80.0, doc)

    def test_conversion_rate_is_not_changed_when_disabled(self):
        upsert_currency_exchange("2026-09-21", "EUR", 109.9033)
        self.set_enabled(0)

        doc = self.make_invoice()
        set_fbil_conversion_rate(doc)

        self.assertEqual(doc.conversion_rate, 80.0)

    @patch("india_compliance.gst_india.utils.fbil_exchange_rate.requests.get")
    def test_throws_when_no_rate_available(self, mock_get):
        mock_fbil_response(mock_get, payload=[])

        self.assertRaisesRegex(
            frappe.ValidationError,
            "No FBIL reference rate is available",
            set_fbil_conversion_rate,
            self.make_invoice(),
        )

    def make_invoice(self, **kwargs):
        doc = frappe._dict(
            doctype="Sales Invoice",
            company=INDIAN_COMPANY,
            currency="EUR",
            posting_date="2026-09-22",
            conversion_rate=80.0,
            is_opening="No",
            is_return=0,
            return_against=None,
        )
        doc.update(kwargs)
        return doc
