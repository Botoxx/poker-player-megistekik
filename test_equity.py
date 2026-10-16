import random
import time
import unittest

from equity import equity, evaluate7


def cs(*specs):
    return [(int({"T": 10, "J": 11, "Q": 12, "K": 13, "A": 14}.get(s[:-1], s[:-1])), s[-1]) for s in specs]


def gc(*specs):
    return [{"rank": s[:-1], "suit": {"h": "hearts", "d": "diamonds", "s": "spades", "c": "clubs"}[s[-1]]}
            for s in specs]


class EvaluateTest(unittest.TestCase):
    def test_category_order(self):
        hands = [
            cs("2h", "5d", "9c", "Js", "Kh", "3d", "7c"),    # high card
            cs("2h", "2d", "9c", "Js", "Kh", "3d", "7c"),    # pair
            cs("2h", "2d", "9c", "9s", "Kh", "3d", "7c"),    # two pair
            cs("2h", "2d", "2c", "9s", "Kh", "3d", "7c"),    # trips
            cs("Ah", "2d", "3c", "4s", "5h", "Jd", "Kc"),    # wheel straight
            cs("2h", "5h", "9h", "Jh", "Kh", "3d", "7c"),    # flush
            cs("2h", "2d", "2c", "9s", "9h", "3d", "7c"),    # full house
            cs("2h", "2d", "2c", "2s", "Kh", "3d", "7c"),    # quads
            cs("5h", "6h", "7h", "8h", "9h", "2d", "Kc"),    # straight flush
        ]
        scores = [evaluate7(h) for h in hands]
        self.assertEqual(scores, sorted(scores))
        self.assertEqual([s[0] for s in scores], list(range(9)))

    def test_kicker_decides(self):
        board = cs("Ah", "9d", "5c", "3s", "2h")
        self.assertGreater(evaluate7(board + cs("Ad", "Kc")), evaluate7(board + cs("As", "Qc")))

    def test_board_plays_is_tie(self):
        board = cs("Ah", "Kh", "Qd", "Jc", "10s")
        self.assertEqual(evaluate7(board + cs("2d", "3c")), evaluate7(board + cs("4d", "5c")))


class EquityTest(unittest.TestCase):
    def test_aces_vs_one_random_hand(self):
        e, sims = equity(gc("Ah", "Ad"), [], 1, budget_s=2, max_sims=3000, rng=random.Random(1))
        self.assertAlmostEqual(e, 0.85, delta=0.03)

    def test_budget_is_respected(self):
        start = time.monotonic()
        _, sims = equity(gc("7h", "2d"), gc("Kh", "9c", "4d"), 3, budget_s=0.15, max_sims=10 ** 6)
        self.assertLess(time.monotonic() - start, 0.25)
        self.assertGreater(sims, 100)


if __name__ == "__main__":
    unittest.main()
