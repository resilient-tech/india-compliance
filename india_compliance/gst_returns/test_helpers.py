# Copyright (c) 2024, Resilient Tech and Contributors
# See license.txt

"""Pure self-tests for helpers. Site-less. round2 expectations = frappe.flt(x, 2)."""

import unittest
from collections import Counter
from datetime import date, datetime

from .helpers import format_date, parse_date, round2, split


class TestSplit(unittest.TestCase):
    """Sharing out a settled total.

    The pieces must add back to it, and each must be a share of the weight it came from. Adding up
    is the weaker half: a hundred pieces of 0.01 and one of -0.49 also add to 0.50, and it is not
    an allocation. So the shape gets asserted, not just the total.
    """

    def assert_shares(self, pieces, weights, total):
        """Every piece is its own weight, rounded -- not someone else's rounding.

        The total is compared rounded, because that is how every reader adds these up: past a
        million, three exact-paisa pieces still sum to 0.010000000009 in float.
        """
        self.assertEqual(round2(sum(pieces)), total)
        for piece in pieces:
            self.assertEqual(piece, round2(piece), f"not a settled amount: {pieces}")

        for piece, weight in zip(pieces, weights, strict=True):
            self.assertLessEqual(abs(piece - weight), 0.01, f"{weights} -> {pieces}")

            if weight > 0:
                self.assertGreaterEqual(piece, 0.0, f"{weights} -> {pieces}")
            elif weight < 0:
                self.assertLessEqual(piece, 0.0, f"{weights} -> {pieces}")
            else:
                self.assertEqual(piece, 0.0, f"{weights} -> {pieces}")

    def test_pieces_add_back_to_the_total(self):
        self.assertEqual(sum(split(10.00, [3.333, 3.333, 3.334])), 10.00)

    def test_no_piece_carries_everyone_elses_rounding(self):
        # the defect this replaces put the whole leftover on one row
        pieces = split(10.00, [3.333, 3.333, 3.334])
        self.assertEqual(pieces, [3.33, 3.34, 3.33])
        for piece, weight in zip(pieces, [3.333, 3.333, 3.334], strict=True):
            self.assertLess(abs(piece - weight), 0.01)

    def test_one_piece_takes_the_whole_total(self):
        self.assertEqual(split(20.01, [20.01]), [20.01])

    def test_credit_notes_share_out_a_negative_total(self):
        pieces = split(-10.00, [-3.333, -3.333, -3.334])
        self.assertEqual(sum(pieces), -10.00)
        self.assertTrue(all(p < 0 for p in pieces))

    def test_a_zero_weight_gets_nothing_and_the_total_still_holds(self):
        pieces = split(10.00, [5.00, 0.0, 5.00])
        self.assertEqual(pieces[1], 0.0)
        self.assertEqual(sum(pieces), 10.00)

    def test_nothing_to_share_gives_nothing(self):
        self.assertEqual(split(0.0, [0.0, 0.0]), [0.0, 0.0])

    def test_total_is_honoured_even_when_it_disagrees_with_the_weights(self):
        # the total is the settled figure; the weights only decide proportions
        self.assertEqual(sum(split(10.01, [3.333, 3.333, 3.334])), 10.01)

    def test_many_pieces_do_not_accumulate_drift(self):
        """Half the rows take a paisa, half take nothing -- that is what 0.005 each comes to.

        Rounding every weight on its own gives 100 x 0.01 = 1.00, twice the total. Putting the
        excess back on one row gives 99 x 0.01 and a -0.49. Both add to 0.50, so the total alone
        would accept either; the distribution is what tells them apart.
        """
        weights = [0.005] * 100
        pieces = split(0.50, weights)

        self.assertEqual(Counter(pieces), Counter({0.01: 50, 0.0: 50}))
        self.assert_shares(pieces, weights, 0.50)

    def test_credit_note_pieces_keep_their_shape_too(self):
        weights = [-0.005] * 100
        pieces = split(-0.50, weights)

        self.assertEqual(Counter(pieces), Counter({-0.01: 50, 0.0: 50}))
        self.assert_shares(pieces, weights, -0.50)

    def test_no_piece_strays_from_the_weight_it_came_from(self):
        """Whatever the mix -- signs, magnitudes, empties -- a piece is a share of its own weight."""
        for weights in (
            [3.333, 3.333, 3.334],
            [0.001, 0.004, 100.005, -100.005],
            [33.335, -1000000.005, 33.335, 0.0],
            [1000000.005, 0.005, -1000000.005],
            [0.0, 0.005, 0.0],
            [100.0, -100.0],
        ):
            total = round2(sum(weights))
            self.assert_shares(split(total, weights), weights, total)

    def test_weights_that_cancel_out_keep_their_own_amounts(self):
        self.assertEqual(split(0.0, [100.0, -100.0]), [100.0, -100.0])

    def test_a_total_next_to_nothing_does_not_inflate_the_pieces(self):
        self.assertEqual(split(0.01, [1000.005, -1000.0]), [1000.01, -1000.0])

    def test_an_empty_weight_never_gets_a_piece(self):
        """The remainder goes on the last real weight, not merely the last one.

        `total` is summed one way and the running total another, so they can land a paisa apart.
        Whoever takes the remainder absorbs that, and it must not be a line with nothing on it.
        """
        weights = [33.335, -1000000.005, 33.335, 0.0]
        pieces = split(-999933.33, weights)

        self.assertEqual(sum(pieces), -999933.33)
        for piece, weight in zip(pieces, weights, strict=True):
            if not weight:
                self.assertEqual(piece, 0.0)

    def test_nothing_anywhere_gives_nothing_anywhere(self):
        self.assertEqual(split(0.0, []), [])
        self.assertEqual(split(0.0, [0.0, 0.0, 0.0]), [0.0, 0.0, 0.0])


class TestRound2(unittest.TestCase):
    def test_none_and_zero(self):
        self.assertEqual(round2(None), 0.0)
        self.assertEqual(round2(0), 0.0)
        self.assertEqual(round2(0.0), 0.0)

    def test_epsilon_corrected_halves(self):
        self.assertEqual(round2(2.675), 2.68)
        self.assertEqual(round2(-50.005), -50.0)
        self.assertEqual(round2(10.005), 10.01)
        self.assertEqual(round2(99.995), 100.0)
        self.assertEqual(round2(1234.565), 1234.57)

    def test_plain_values(self):
        self.assertEqual(round2(100), 100.0)
        self.assertEqual(round2(33.333333), 33.33)
        self.assertEqual(round2(0.1 + 0.2), 0.3)


class TestDateHelpers(unittest.TestCase):
    def test_parse_iso_and_custom_fmt(self):
        self.assertEqual(parse_date("2024-03-15"), date(2024, 3, 15))
        self.assertEqual(parse_date("15-03-2024", "%d-%m-%Y"), date(2024, 3, 15))

    def test_parse_empty(self):
        self.assertIsNone(parse_date(None))
        self.assertIsNone(parse_date(""))

    def test_parse_passthrough_date(self):
        self.assertEqual(parse_date(date(2024, 3, 15)), date(2024, 3, 15))

    def test_parse_datetime_drops_time(self):
        parsed = parse_date(datetime(2024, 3, 15, 13, 45, 6))
        self.assertEqual(parsed, date(2024, 3, 15))
        self.assertNotIsInstance(parsed, datetime)

    def test_format_iso_and_custom_fmt(self):
        self.assertEqual(format_date(date(2024, 3, 15)), "2024-03-15")
        self.assertEqual(format_date(date(2024, 3, 15), "%d-%m-%Y"), "15-03-2024")
        self.assertIsNone(format_date(None))

    def test_roundtrip(self):
        self.assertEqual(parse_date(format_date(date(2024, 3, 15))), date(2024, 3, 15))


if __name__ == "__main__":
    unittest.main()
