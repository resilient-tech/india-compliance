# Copyright (c) 2024, Resilient Tech and Contributors
# See license.txt

"""Tests for the rules every category shares. Needs a site -- rounding reads its settings."""

import copy
import itertools
import unittest
from typing import ClassVar

from frappe.utils import flt

from india_compliance.gst_returns.fields.gstr1 import (
    B2BInvoiceType,
    DocumentNature,
    SubCategory,
)
from india_compliance.gst_returns.fields.gstr1 import DocField as doc
from india_compliance.gst_returns.fields.gstr1 import ItemField as item
from india_compliance.gst_returns.fields.gstr1 import RawField as raw

from . import (
    SECTIONS,
    advances,
    b2b,
    b2cl,
    b2cs,
    cdnr,
    cdnur,
    doc_issue,
    exports,
    hsn,
    nil_rated,
    summary,
    supecom,
)
from . import _shared as s

COMPANY_GSTIN = "24AAUPV7468F1ZW"


def flatten(canonical):
    """Rows as the export sees them, matching keys dropped."""
    rows = []

    for section in canonical.values():
        values = list(section.values())
        rows.extend(itertools.chain(*values) if values and isinstance(values[0], list) else values)

    return rows


class TestPick(unittest.TestCase):
    KEYS: ClassVar[dict] = {"b": "second", "a": "first"}

    def test_emits_in_table_order_not_source_order(self):
        # portal reads key order off the table
        self.assertEqual(list(s.pick({"a": 1, "b": 2}, self.KEYS)), ["second", "first"])

    def test_drops_keys_not_in_table(self):
        self.assertEqual(s.pick({"a": 1, "zz": 9}, self.KEYS), {"first": 1})

    def test_keeps_a_blank_the_portal_sent(self):
        # an empty value the portal sent is still data
        self.assertEqual(s.pick({"a": ""}, self.KEYS), {"first": ""})

    def test_reads_back_the_other_way(self):
        self.assertEqual(s.pick_back({"first": 1, "second": 2}, self.KEYS), {"b": 2, "a": 1})


class TestKeyTables(unittest.TestCase):
    def test_every_category_table_is_reversible(self):
        for module in (b2b, b2cl, exports, b2cs, nil_rated, cdnr, cdnur, hsn, advances, doc_issue, supecom):
            with self.subTest(module.__name__):
                s.invert(module.KEYS)

    def test_summary_table_is_not_reversible_and_does_not_have_to_be(self):
        # two portal keys, one description. Summary is never filed back
        with self.assertRaises(ValueError):
            s.invert(summary.KEYS)

    def test_every_category_is_registered(self):
        self.assertEqual(len(SECTIONS), 13)


class TestGrouping(unittest.TestCase):
    ROWS: ClassVar[list] = [
        {"customer_gstin": "A", "document_number": "1"},
        {"customer_gstin": "B", "document_number": "2"},
        {"customer_gstin": "A", "document_number": "3"},
    ]
    GROUPS: ClassVar[list] = [
        {"ctin": "A", "inv": [{"inum": "1"}, {"inum": "3"}]},
        {"ctin": "B", "inv": [{"inum": "2"}]},
    ]

    def group(self, rows):
        return s.groups_from_rows(
            rows,
            group_key=lambda row: row["customer_gstin"],
            group_header=lambda row: {"ctin": row["customer_gstin"]},
            rows_field="inv",
            write_row=lambda row: {"inum": row["document_number"]},
        )

    def ungroup(self, groups):
        return list(
            s.rows_from_groups(
                groups,
                "inv",
                lambda group: {"customer_gstin": group["ctin"]},
                lambda row, header: {**header, "document_number": row["inum"]},
            )
        )

    def test_rows_group_under_their_key(self):
        self.assertEqual(self.group(self.ROWS), self.GROUPS)

    def test_first_row_of_a_key_writes_the_header(self):
        rows = [{"customer_gstin": "A", "name": "First"}, {"customer_gstin": "A", "name": "Second"}]
        out = s.groups_from_rows(
            rows,
            group_key=lambda row: row["customer_gstin"],
            group_header=lambda row: {"ctin": row["customer_gstin"], "nm": row["name"]},
            rows_field="inv",
            write_row=lambda row: {"nm": row["name"]},
        )
        self.assertEqual(out[0]["nm"], "First")

    def test_groups_flatten_back_with_the_header_on_each_row(self):
        self.assertEqual(self.ungroup(self.GROUPS), self.ROWS[:1] + self.ROWS[2:] + self.ROWS[1:2])

    def test_a_group_with_no_rows_is_skipped(self):
        self.assertEqual(self.ungroup([{"ctin": "A"}]), [])

    def test_each_direction_undoes_the_other(self):
        back = self.ungroup(self.group(self.ROWS))
        self.assertEqual(sorted(back, key=str), sorted(self.ROWS, key=str))


class TestStripEmpty(unittest.TestCase):
    def test_drops_blanks(self):
        self.assertEqual(s.strip_empty({"a": 1, "b": None, "c": "", "d": {}, "e": []}), {"a": 1})

    def test_keeps_zero_and_false(self):
        # a zero amount is still filed
        self.assertEqual(s.strip_empty({"a": 0, "b": 0.0, "c": False}), {"a": 0, "b": 0.0, "c": False})

    def test_reaches_inside_lists_and_nested_rows(self):
        self.assertEqual(
            s.strip_empty({"itms": [{"txval": 1, "rt": None}]}),
            {"itms": [{"txval": 1}]},
        )

    def test_keeps_a_row_that_empties_out(self):
        # wrapper stays, its blank contents go
        self.assertEqual(s.strip_empty({"itm_det": {"txval": ""}}), {"itm_det": {}})


class TestPlaceOfSupply(unittest.TestCase):
    def test_portal_number_becomes_the_stored_format(self):
        self.assertEqual(s.pos_from_gov("05"), "05-Uttarakhand")

    def test_stored_format_goes_back_as_a_number(self):
        self.assertEqual(s.pos_to_gov("05-Uttarakhand"), "05")

    def test_round_trips(self):
        for number in ("05", "24", "96"):
            self.assertEqual(s.pos_to_gov(s.pos_from_gov(number)), number)


class TestItemTotals(unittest.TestCase):
    def test_item_amounts_pair_with_prefixed_invoice_totals(self):
        # building the name by hand gave total_total_* for advances
        for line, total in s.ITEM_TOTALS.items():
            self.assertEqual(total, f"total_{line}")

    def test_accumulates_rather_than_resets(self):
        row = {}
        items = [{item.TAXABLE_VALUE: 100}, {item.TAXABLE_VALUE: 50}]
        s.add_item_totals(row, items, s.ITEM_TOTALS)
        s.add_item_totals(row, items, s.ITEM_TOTALS)
        self.assertEqual(row[doc.TAXABLE_VALUE], 300)

    def test_tolerates_no_items(self):
        self.assertEqual(s.add_item_totals({}, None, s.ITEM_TOTALS), {})


class TestMoney(unittest.TestCase):
    RAW: ClassVar[list] = [
        {
            raw.CUST_GSTIN: "24AANFA2641L1ZF",
            raw.INVOICES: [
                {
                    raw.DOC_NUMBER: "S1",
                    raw.DOC_DATE: "24-11-2016",
                    raw.DOC_VALUE: 729248.164,
                    raw.POS: "06",
                    raw.REVERSE_CHARGE: "N",
                    raw.INVOICE_TYPE: "R",
                    raw.ITEMS: [
                        {raw.INDEX: 1, raw.ITEM_DETAILS: {raw.TAX_RATE: 5, raw.TAXABLE_VALUE: 10.006}}
                    ],
                }
            ],
        }
    ]

    def test_reading_does_not_round(self):
        row = flatten(b2b.to_canonical(self.RAW))[0]
        self.assertEqual(row[doc.DOC_VALUE], 729248.164)
        self.assertEqual(row[doc.ITEMS][0][item.TAXABLE_VALUE], 10.006)

    def test_writing_rounds(self):
        rows = flatten(b2b.to_canonical(self.RAW))
        out = b2b.to_gov(rows)[0][raw.INVOICES][0]
        self.assertEqual(out[raw.DOC_VALUE], 729248.16)
        self.assertEqual(out[raw.ITEMS][0][raw.ITEM_DETAILS][raw.TAXABLE_VALUE], 10.01)


class TestBlanksFromThePortal(unittest.TestCase):
    """What the portal left out and what it sent as nothing are different things."""

    def payload(self, item_details, **invoice):
        return [
            {
                raw.CUST_GSTIN: "24AANFA2641L1ZF",
                raw.INVOICES: [
                    {
                        raw.DOC_NUMBER: "S1",
                        raw.DOC_DATE: "24-11-2016",
                        raw.POS: "06",
                        raw.INVOICE_TYPE: "R",
                        **invoice,
                        **(
                            {raw.ITEMS: [{raw.INDEX: 1, raw.ITEM_DETAILS: item_details}]}
                            if item_details
                            else {}
                        ),
                    }
                ],
            }
        ]

    def test_a_null_amount_is_not_turned_into_a_zero(self):
        payload = self.payload({raw.TAX_RATE: 5, raw.TAXABLE_VALUE: 100, raw.IGST: None})
        row = flatten(b2b.to_canonical(payload))[0]

        self.assertIsNone(row[doc.ITEMS][0][item.IGST])
        self.assertEqual(row[doc.ITEMS][0][item.CGST], 0)
        self.assertNotIn(doc.IGST, row)  # nothing to add to the invoice total

        written = b2b.to_gov([row])[0][raw.INVOICES][0]
        self.assertNotIn(raw.IGST, s.strip_empty(written)[raw.ITEMS][0][raw.ITEM_DETAILS])

    def test_an_invoice_with_no_items_still_reads(self):
        row = flatten(b2b.to_canonical(self.payload(None, **{raw.DOC_VALUE: 100})))[0]

        self.assertNotIn(doc.ITEMS, row)
        self.assertNotIn(doc.TAXABLE_VALUE, row)

    def test_a_null_place_of_supply_still_reads(self):
        """A kept null must not break the pos-rate key."""
        b2cs_rows = b2cs.to_canonical([{raw.POS: None, raw.TAX_RATE: 5, raw.TAXABLE_VALUE: 100}])
        self.assertIn(" - 5.0", b2cs_rows[b2cs.SUBCATEGORY])

        at_rows = advances.received_to_canonical(
            [{raw.POS: None, raw.ITEMS: [{raw.TAX_RATE: 5, raw.ADVANCE_AMOUNT: 100}]}]
        )
        self.assertIn(" - 5.0", at_rows[SubCategory.AT.value])


class TestFlag(unittest.TestCase):
    ROW: ClassVar[dict] = {
        doc.CUST_GSTIN: "24AANFA2641L1ZF",
        doc.DOC_NUMBER: "S1",
        doc.DOC_DATE: "2016-11-24",
        doc.POS: "06-Haryana",
        doc.ITEMS: [{item.TAX_RATE: 5, item.TAXABLE_VALUE: 100}],
    }

    def test_never_reaches_canonical(self):
        raw_data = [
            {
                raw.CUST_GSTIN: "24AANFA2641L1ZF",
                raw.INVOICES: [{**TestMoney.RAW[0][raw.INVOICES][0], raw.FLAG: "D"}],
            }
        ]
        self.assertNotIn(doc.FLAG, flatten(b2b.to_canonical(raw_data))[0])

    def test_survives_to_the_portal_when_the_export_sets_it(self):
        out = b2b.to_gov([{**self.ROW, doc.FLAG: "D"}])[0][raw.INVOICES][0]
        self.assertEqual(out[raw.FLAG], "D")

    def test_absent_when_not_set(self):
        self.assertNotIn(raw.FLAG, b2b.to_gov([dict(self.ROW)])[0][raw.INVOICES][0])


class TestCreditNoteSigns(unittest.TestCase):
    RAW: ClassVar[list] = [
        {
            raw.CUST_GSTIN: "24AANFA2641L1ZF",
            raw.NOTE_DETAILS: [
                {
                    raw.NOTE_TYPE: "C",
                    raw.NOTE_NUMBER: "533515",
                    raw.NOTE_DATE: "23-09-2016",
                    raw.POS: "03",
                    raw.REVERSE_CHARGE: "Y",
                    raw.INVOICE_TYPE: "DE",
                    raw.DOC_VALUE: 123123,
                    raw.ITEMS: [
                        {raw.INDEX: 1, raw.ITEM_DETAILS: {raw.TAX_RATE: 10, raw.TAXABLE_VALUE: 5225.28}}
                    ],
                }
            ],
        }
    ]

    def test_stored_negative(self):
        row = flatten(cdnr.to_canonical(self.RAW))[0]
        self.assertEqual(row[doc.DOC_VALUE], -123123)
        self.assertEqual(row[doc.ITEMS][0][item.TAXABLE_VALUE], -5225.28)
        self.assertEqual(row[doc.TAXABLE_VALUE], -5225.28)

    def test_filed_unsigned(self):
        out = cdnr.to_gov(flatten(cdnr.to_canonical(self.RAW)))[0][raw.NOTE_DETAILS][0]
        self.assertEqual(out[raw.DOC_VALUE], 123123)
        self.assertEqual(out[raw.ITEMS][0][raw.ITEM_DETAILS][raw.TAXABLE_VALUE], 5225.28)

    def test_deemed_export_note_files_the_portal_code(self):
        """Books writes one label for both B2B and notes, so one table serves both ways."""
        books_row = {
            doc.CUST_GSTIN: "24AANFA2641L1ZF",
            doc.TRANSACTION_TYPE: "Credit Note",
            doc.DOC_NUMBER: "533515",
            doc.DOC_DATE: "2016-09-23",
            doc.POS: "03-Punjab",
            doc.DOC_TYPE: B2BInvoiceType.DE.value,
            doc.DOC_VALUE: -123123,
            doc.ITEMS: [{item.TAXABLE_VALUE: -100, item.TAX_RATE: 5}],
        }
        out = cdnr.to_gov([books_row])[0][raw.NOTE_DETAILS][0]
        self.assertEqual(out[raw.INVOICE_TYPE], "DE")

    def test_a_note_value_is_made_unsigned_before_it_is_rounded(self):
        """A note carries negative amounts, so take the magnitude first and round after."""
        expected = flt(abs(-111.115), 2)

        for section in (cdnr, cdnur):
            row = {
                doc.TRANSACTION_TYPE: "Credit Note",
                doc.DOC_NUMBER: "C1",
                doc.DOC_DATE: "2016-09-23",
                doc.POS: "03-Punjab",
                doc.DOC_TYPE: "Regular B2B" if section is cdnr else "B2CL",
                doc.CUST_GSTIN: "24AANFA2641L1ZF",
                doc.DOC_VALUE: -111.115,
                doc.ITEMS: [{item.TAXABLE_VALUE: -111.115, item.TAX_RATE: 5}],
            }
            out = section.to_gov([row])[0]
            note = out[raw.NOTE_DETAILS][0] if section is cdnr else out

            self.assertEqual(note[raw.DOC_VALUE], expected, f"{section.__name__} document value")
            self.assertEqual(
                note[raw.ITEMS][0][raw.ITEM_DETAILS][raw.TAXABLE_VALUE],
                expected,
                f"{section.__name__} item value",
            )

    def test_a_note_stored_with_the_old_label_still_files_the_portal_code(self):
        """Rows mapped before the merge say "Deemed Exports". Must still file as DE."""
        stored_row = {
            doc.CUST_GSTIN: "24AANFA2641L1ZF",
            doc.TRANSACTION_TYPE: "Credit Note",
            doc.DOC_NUMBER: "533515",
            doc.DOC_DATE: "2016-09-23",
            doc.POS: "03-Punjab",
            doc.DOC_TYPE: SubCategory.DE.value,
            doc.DOC_VALUE: -123123,
            doc.ITEMS: [{item.TAXABLE_VALUE: -100, item.TAX_RATE: 5}],
        }
        out = cdnr.to_gov([stored_row])[0][raw.NOTE_DETAILS][0]
        self.assertEqual(out[raw.INVOICE_TYPE], "DE")

    def test_registered_and_unregistered_notes_share_one_note_type_table(self):
        self.assertIs(cdnr.NOTE_TYPES, cdnur.NOTE_TYPES)

    def test_debit_note_stays_positive(self):
        payload = [
            {
                raw.CUST_GSTIN: "24AANFA2641L1ZF",
                raw.NOTE_DETAILS: [{**self.RAW[0][raw.NOTE_DETAILS][0], raw.NOTE_TYPE: "D"}],
            }
        ]
        self.assertEqual(flatten(cdnr.to_canonical(payload))[0][doc.DOC_VALUE], 123123)


# one real-shaped payload per category, for the round-trip and zero-difference tests
PAYLOADS = {
    "b2b": (b2b.to_canonical, b2b.to_gov, TestMoney.RAW),
    "cdnr": (cdnr.to_canonical, cdnr.to_gov, TestCreditNoteSigns.RAW),
    "b2cl": (
        b2cl.to_canonical,
        b2cl.to_gov,
        [
            {
                raw.POS: "05",
                raw.INVOICES: [
                    {
                        raw.DOC_NUMBER: "92661",
                        raw.DOC_DATE: "10-01-2016",
                        raw.DOC_VALUE: 784586.33,
                        raw.ITEMS: [
                            {
                                raw.INDEX: 1,
                                raw.ITEM_DETAILS: {
                                    raw.TAX_RATE: 5,
                                    raw.TAXABLE_VALUE: 10000,
                                    raw.IGST: 833.33,
                                },
                            }
                        ],
                    }
                ],
            }
        ],
    ),
    "exports": (
        exports.to_canonical,
        exports.to_gov,
        [
            {
                raw.EXPORT_TYPE: "WPAY",
                raw.INVOICES: [
                    {
                        raw.DOC_NUMBER: "81542",
                        raw.DOC_DATE: "12-02-2016",
                        raw.DOC_VALUE: 995048.36,
                        raw.SHIPPING_PORT_CODE: "013027",
                        raw.SHIPPING_BILL_NUMBER: "7896542",
                        raw.SHIPPING_BILL_DATE: "04-10-2016",
                        raw.ITEMS: [{raw.TAX_RATE: 5, raw.TAXABLE_VALUE: 10000, raw.IGST: 833.33}],
                    }
                ],
            }
        ],
    ),
    # supply type is worked out on write, so the payload carries it already
    "b2cs": (
        b2cs.to_canonical,
        b2cs.to_gov,
        [
            {
                raw.TAXABLE_VALUE: 110,
                raw.TYPE: "OE",
                raw.POS: "05",
                raw.TAX_RATE: 5,
                raw.IGST: 10,
                raw.SUPPLY_TYPE: "INTER",
            }
        ],
    ),
    "nil_rated": (
        nil_rated.to_canonical,
        nil_rated.to_gov,
        {
            raw.INVOICES: [
                {
                    raw.SUPPLY_TYPE: "INTRB2B",
                    raw.EXEMPTED_AMOUNT: 123.45,
                    raw.NIL_RATED_AMOUNT: 1470.85,
                    raw.NON_GST_AMOUNT: 1258.5,
                }
            ]
        },
    ),
    "cdnur": (
        cdnur.to_canonical,
        cdnur.to_gov,
        [
            {
                raw.TYPE: "B2CL",
                raw.NOTE_TYPE: "C",
                raw.NOTE_NUMBER: "533515",
                raw.NOTE_DATE: "23-09-2016",
                raw.DOC_VALUE: 123123,
                raw.POS: "03",
                raw.ITEMS: [
                    {
                        raw.INDEX: 1,
                        raw.ITEM_DETAILS: {
                            raw.TAX_RATE: 10,
                            raw.TAXABLE_VALUE: 5225.28,
                            raw.IGST: 339.64,
                        },
                    }
                ],
            }
        ],
    ),
    "hsn": (
        hsn.to_canonical,
        hsn.to_gov,
        {
            raw.HSN_B2B: [
                {
                    raw.INDEX: 1,
                    raw.HSN_CODE: "1102",
                    raw.DESCRIPTION: "CEREAL FLOURS",
                    raw.UOM: "BOX",
                    raw.QUANTITY: 2,
                    raw.TAXABLE_VALUE: 100,
                    raw.CGST: 0.5,
                    raw.SGST: 0.5,
                    raw.TAX_RATE: 1,
                }
            ]
        },
    ),
    "doc_issue": (
        doc_issue.to_canonical,
        doc_issue.to_gov,
        {
            raw.DOC_ISSUE_DETAILS: [
                {
                    raw.DOC_ISSUE_NUMBER: 1,
                    raw.DOC_ISSUE_LIST: [
                        {
                            raw.INDEX: 1,
                            raw.FROM_SR: "1",
                            raw.TO_SR: "10",
                            raw.TOTAL_COUNT: 10,
                            raw.CANCELLED_COUNT: 0,
                            raw.NET_ISSUE: 10,
                        }
                    ],
                }
            ]
        },
    ),
    "supecom": (
        supecom.to_canonical,
        supecom.to_gov,
        {
            raw.SUPECOM_52: [
                {
                    raw.ECOMMERCE_GSTIN: "20ALYPD6528PQC5",
                    raw.NET_TAXABLE_VALUE: 10000,
                    raw.ECOM_IGST: 1000,
                    raw.ECOM_CGST: 0,
                    raw.ECOM_SGST: 0,
                    raw.ECOM_CESS: 0,
                }
            ]
        },
    ),
    "advances_received": (
        advances.received_to_canonical,
        advances.received_to_gov,
        [
            {
                raw.POS: "05",
                raw.SUPPLY_TYPE: "INTER",
                raw.ITEMS: [
                    {
                        raw.IGST: 5,
                        raw.CESS: 0,
                        raw.CGST: 0,
                        raw.SGST: 0,
                        raw.ADVANCE_AMOUNT: 100,
                        raw.TAX_RATE: 5,
                    }
                ],
            }
        ],
    ),
    "advances_adjusted": (
        advances.adjusted_to_canonical,
        advances.adjusted_to_gov,
        [
            {
                raw.POS: "05",
                raw.SUPPLY_TYPE: "INTER",
                raw.ITEMS: [
                    {
                        raw.IGST: 5,
                        raw.CESS: 0,
                        raw.CGST: 0,
                        raw.SGST: 0,
                        raw.ADVANCE_AMOUNT: 100,
                        raw.TAX_RATE: 5,
                    }
                ],
            }
        ],
    ),
}


def rebuild(reader, writer, payload):
    """What the portal would get: mapped back, blanks dropped."""
    return s.strip_empty(writer(flatten(reader(payload)), company_gstin=COMPANY_GSTIN))


class TestRoundTrip(unittest.TestCase):
    """Everything the portal sent survives raw -> ours -> raw. Only rounding and zeros are added."""

    def survives(self, sent, back, path="root"):
        if isinstance(sent, dict):
            for key, value in sent.items():
                self.assertIn(key, back, f"{path}.{key} was lost")
                self.survives(value, back[key], f"{path}.{key}")

        elif isinstance(sent, list):
            self.assertEqual(len(sent), len(back), f"{path} changed length")
            for index, (value, other) in enumerate(zip(sent, back, strict=True)):
                self.survives(value, other, f"{path}[{index}]")

        elif isinstance(sent, float):
            self.assertAlmostEqual(sent, back, places=2, msg=path)

        else:
            self.assertEqual(sent, back, path)

    def test_every_category(self):
        for name, (reader, writer, payload) in PAYLOADS.items():
            with self.subTest(name):
                self.survives(payload, rebuild(reader, writer, payload))

    def test_adjusted_advances_are_stored_negative(self):
        rows = flatten(advances.adjusted_to_canonical(PAYLOADS["advances_adjusted"][2]))
        self.assertEqual(rows[0][doc.TAXABLE_VALUE], -100)


class TestZeroDifference(unittest.TestCase):
    """A zero rate difference must not reach the portal. Every writer drops its own now."""

    def test_dropped_by_every_category_that_maps_it(self):
        for name, (reader, writer, payload) in PAYLOADS.items():
            module = SECTIONS_BY_NAME[name]
            if raw.DIFF_PERCENTAGE not in module.KEYS:
                continue

            with self.subTest(name):
                rows = flatten(reader(payload))
                for row in rows:
                    row[doc.DIFF_PERCENTAGE] = 0

                emitted = s.strip_empty(writer(rows, company_gstin=COMPANY_GSTIN))
                self.assertNotIn(raw.DIFF_PERCENTAGE, str(emitted))


SECTIONS_BY_NAME = {
    "b2b": b2b,
    "b2cl": b2cl,
    "exports": exports,
    "b2cs": b2cs,
    "nil_rated": nil_rated,
    "cdnr": cdnr,
    "cdnur": cdnur,
    "hsn": hsn,
    "doc_issue": doc_issue,
    "supecom": supecom,
    "advances_received": advances,
    "advances_adjusted": advances,
}


class TestSupplyType(unittest.TestCase):
    def test_reads_the_seller_state_off_the_gstin(self):
        self.assertEqual(s.supply_type("24", COMPANY_GSTIN), "INTRA")
        self.assertEqual(s.supply_type("05", COMPANY_GSTIN), "INTER")

    def test_refuses_a_missing_seller(self):
        # a blank one would file every intra-state supply as inter-state, quietly
        with self.assertRaises(ValueError):
            b2cs.to_gov(flatten(b2cs.to_canonical(PAYLOADS["b2cs"][2])))


class TestWritingLeavesStoredRowsAlone(unittest.TestCase):
    """A writer gets the stored rows themselves, so it must leave them alone."""

    def test_no_writer_changes_the_rows_it_was_given(self):
        for name, (reader, writer, payload) in PAYLOADS.items():
            with self.subTest(name):
                rows = flatten(reader(payload))
                before = copy.deepcopy(rows)

                writer(rows, company_gstin=COMPANY_GSTIN)

                self.assertEqual(rows, before)

    def test_a_draft_is_counted_as_cancelled_once(self):
        # books-only field, no payload above has it
        rows = [
            {
                doc.DOC_TYPE: "Invoices for outward supply",
                doc.FROM_SR: "1",
                doc.TO_SR: "10",
                doc.TOTAL_COUNT: 10,
                doc.CANCELLED_COUNT: 1,
                doc.DRAFT_COUNT: 2,
            }
        ]

        first = doc_issue.to_gov(rows)
        self.assertEqual(first, doc_issue.to_gov(rows))
        self.assertEqual(first[raw.DOC_ISSUE_DETAILS][0][raw.DOC_ISSUE_LIST][0][raw.NET_ISSUE], 7)


class TestCategoryRules(unittest.TestCase):
    """Rules that belong to one category only, so easy to lose in a rewrite."""

    def test_an_export_credit_note_reports_no_place_of_supply(self):
        rows = flatten(cdnur.to_canonical(PAYLOADS["cdnur"][2]))
        self.assertIn(raw.POS, cdnur.to_gov(rows)[0])

        rows[0][doc.DOC_TYPE] = "EXPWP"
        self.assertNotIn(raw.POS, cdnur.to_gov(rows)[0])

    def test_an_export_type_with_no_invoices_still_gets_a_bucket(self):
        self.assertEqual(
            exports.to_canonical([{raw.EXPORT_TYPE: "WPAY", raw.INVOICES: []}]),
            {SubCategory.EXPWP.value: {}},
        )

    def test_a_service_hsn_reports_no_unit(self):
        goods, service = (
            hsn.to_gov([{doc.DOC_TYPE: SubCategory.HSN_B2B.value, doc.HSN_CODE: code, doc.UOM: "BOX-BOX"}])
            for code in ("1102", "9954")
        )
        self.assertEqual(goods[raw.HSN_B2B][0][raw.UOM], "BOX")
        self.assertEqual(service[raw.HSN_B2B][0][raw.UOM], "NA")

    def test_an_hsn_description_is_trimmed_then_capped_at_thirty(self):
        rows = [
            {
                doc.DOC_TYPE: SubCategory.HSN_B2B.value,
                doc.HSN_CODE: "1102",
                doc.DESCRIPTION: "  CEREAL FLOURS OTHER THAN THAT OF WHEAT  ",
            }
        ]
        written = hsn.to_gov(rows)[raw.HSN_B2B][0][raw.DESCRIPTION]

        self.assertEqual(written, "CEREAL FLOURS OTHER THAN THAT")
        self.assertLessEqual(len(written), 30)

    def test_each_hsn_section_numbers_its_rows_from_one(self):
        rows = [
            {doc.DOC_TYPE: SubCategory.HSN_B2B.value, doc.HSN_CODE: "1102"},
            {doc.DOC_TYPE: SubCategory.HSN_B2B.value, doc.HSN_CODE: "1103"},
            {doc.DOC_TYPE: SubCategory.HSN_B2C.value, doc.HSN_CODE: "1104"},
        ]
        out = hsn.to_gov(rows)

        self.assertEqual([row[raw.INDEX] for row in out[raw.HSN_B2B]], [1, 2])
        self.assertEqual([row[raw.INDEX] for row in out[raw.HSN_B2C]], [1])

    def test_a_repeated_hsn_section_merges_instead_of_replacing(self):
        error_payload = [
            {raw.HSN_B2B: [{raw.HSN_CODE: "1102", raw.UOM: "BOX", raw.TAX_RATE: 1}]},
            {raw.HSN_B2B: [{raw.HSN_CODE: "1103", raw.UOM: "BOX", raw.TAX_RATE: 1}]},
        ]
        rows = hsn.to_canonical(error_payload)[SubCategory.HSN_B2B.value]

        self.assertEqual(sorted(rows), ["1102 - BOX-BOX - 1.0", "1103 - BOX-BOX - 1.0"])

    def test_a_range_excluded_from_the_report_is_not_filed(self):
        rows = [
            {doc.DOC_TYPE: f"{doc_issue.NOT_REPORTED} (Invalid Invoice Number)", doc.TOTAL_COUNT: 2},
            {
                doc.DOC_TYPE: DocumentNature.OUTWARD_SUPPLY.value,
                doc.FROM_SR: "3",
                doc.TO_SR: "4",
                doc.TOTAL_COUNT: 2,
            },
        ]
        details = doc_issue.to_gov(rows)[raw.DOC_ISSUE_DETAILS]

        self.assertEqual(len(details), 1)
        self.assertEqual(details[0][raw.DOC_ISSUE_LIST][0][raw.FROM_SR], "3")

    def test_a_nil_rated_line_with_nothing_in_it_is_dropped(self):
        payload = {raw.INVOICES: [{raw.SUPPLY_TYPE: "INTRB2B", raw.EXEMPTED_AMOUNT: 0}]}
        self.assertEqual(nil_rated.to_canonical(payload), {nil_rated.SUBCATEGORY: {}})


class TestSummary(unittest.TestCase):
    RAW: ClassVar[list] = [
        {"sec_nm": "B2B", "ttl_rec": 2, "ttl_tax": 5000, "ttl_igst": 900},
        {"sec_nm": "B2B_4A", "ttl_rec": 2, "ttl_tax": 5000, "ttl_igst": 900},
        {"sec_nm": "DOC_ISSUE", "ttl_rec": 9, "net_doc_issued": 7, "ttl_doc_issued": 9},
    ]

    def test_section_codes_become_names(self):
        rows = summary.to_canonical(self.RAW)["summary"]
        self.assertIn("B2B, SEZ, DE", rows)
        self.assertEqual(rows["B2B Regular"][doc.DESCRIPTION], SubCategory.B2B_REGULAR.value)

    def test_document_ranges_count_what_was_issued(self):
        rows = summary.to_canonical(self.RAW)["summary"]
        self.assertEqual(rows["Document Issued"]["no_of_records"], 7)

    def test_overview_indents_subcategories_under_their_category(self):
        rows = list(summary.to_canonical(self.RAW[:2])["summary"].values())
        overview = summary.to_overview(rows)
        self.assertEqual([row["indent"] for row in overview], [0, 1])
        self.assertEqual(overview[0][doc.DESCRIPTION], "B2B, SEZ, DE")
        self.assertEqual(overview[1][doc.DESCRIPTION], SubCategory.B2B_REGULAR.value)

    def test_an_amended_ecommerce_section_names_its_subsections(self):
        """Amended subsection code is unverified, so both spellings must resolve."""
        for code in ("SUPECOM_14A", "SUPECOMA_14A"):
            rows = summary.to_canonical(
                [
                    {
                        "sec_nm": "SUPECOMA",
                        "ttl_rec": 1,
                        "sub_sections": [{"typ": code, "ttl_rec": 1, "ttl_tax": 60}],
                    }
                ]
            )["summary"]

            self.assertIn(f"{SubCategory.SUPECOM_52.value} {summary.AMENDED}", rows)

    def test_a_summary_without_subsections_falls_back_to_our_own(self):
        self.assertEqual(summary.to_canonical([{"sec_nm": "SUPECOM", "ttl_rec": 1}]), {})

    def test_amendments_collapse_into_one_closing_line(self):
        rows = [
            {doc.DESCRIPTION: "B2B, SEZ, DE", doc.TAXABLE_VALUE: 5000},
            {doc.DESCRIPTION: "B2B, SEZ, DE (Amended)", doc.TAXABLE_VALUE: 250},
        ]
        overview = summary.to_overview(rows)
        self.assertEqual(overview[-1][doc.DESCRIPTION], "Net Liability from Amendments")
        self.assertEqual(overview[-1][doc.TAXABLE_VALUE], 250)


if __name__ == "__main__":
    unittest.main()
