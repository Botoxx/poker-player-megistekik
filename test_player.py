import unittest

from player import Player, hand_category, preflop_strength, PAIR, TWO_PAIR, STRAIGHT, FLUSH, FULL_HOUSE


def c(spec):
    rank, suit = spec[:-1], {"h": "hearts", "d": "diamonds", "s": "spades", "c": "clubs"}[spec[-1]]
    return {"rank": rank, "suit": suit}


def state(hole, board=(), current_buy_in=20, my_bet=10, stack=1000, minimum_raise=20, pot=30):
    return {
        "small_blind": 10,
        "current_buy_in": current_buy_in,
        "minimum_raise": minimum_raise,
        "pot": pot,
        "in_action": 1,
        "community_cards": [c(x) for x in board],
        "players": [
            {"name": "other", "stack": 1000, "bet": 20, "status": "active"},
            {"name": "us", "stack": stack, "bet": my_bet, "status": "active",
             "hole_cards": [c(x) for x in hole]},
        ],
    }


class HandCategoryTest(unittest.TestCase):
    def test_categories(self):
        self.assertEqual(hand_category([c(x) for x in ["Ah", "Ad", "5c", "7s", "9h"]]), PAIR)
        self.assertEqual(hand_category([c(x) for x in ["Ah", "Ad", "5c", "5s", "9h"]]), TWO_PAIR)
        self.assertEqual(hand_category([c(x) for x in ["Ah", "2d", "3c", "4s", "5h"]]), STRAIGHT)
        self.assertEqual(hand_category([c(x) for x in ["Ah", "2h", "9h", "4h", "Jh"]]), FLUSH)
        self.assertEqual(hand_category([c(x) for x in ["Ah", "Ad", "Ac", "5s", "5h"]]), FULL_HOUSE)

    def test_preflop(self):
        self.assertEqual(preflop_strength([c("Ah"), c("Kd")]), 2)
        self.assertEqual(preflop_strength([c("4h"), c("4d")]), 1)
        self.assertEqual(preflop_strength([c("7h"), c("2d")]), 0)


class BetRequestTest(unittest.TestCase):
    def test_premium_preflop_raises(self):
        self.assertGreaterEqual(Player().betRequest(state(["Ah", "Ad"])), 10 + 20)

    def test_trash_preflop_folds(self):
        self.assertEqual(Player().betRequest(state(["7h", "2d"])), 0)

    def test_playable_preflop_opens_with_raise(self):
        self.assertEqual(Player().betRequest(state(["Jh", "10d"])), 60)

    def test_playable_preflop_calls_small_raise(self):
        self.assertEqual(Player().betRequest(state(["Jh", "10d"], current_buy_in=60)), 50)

    def test_two_pair_postflop_raises(self):
        bet = Player().betRequest(state(["Ah", "9d"], board=["As", "9c", "2h"], current_buy_in=10))
        self.assertGreaterEqual(bet, 20)

    def test_board_pair_only_folds(self):
        self.assertEqual(Player().betRequest(state(["7h", "2d"], board=["Ks", "Kc", "4h"])), 0)

    def test_jacks_do_not_reraise_war(self):
        # We opened to 84, opponent re-raised to 780: jacks must fold, not re-raise.
        self.assertEqual(Player().betRequest(state(["Js", "Jc"], current_buy_in=780, my_bet=84, stack=900)), 0)

    def test_short_stack_shoves_any_ace(self):
        self.assertEqual(Player().betRequest(state(["Ah", "3d"], stack=200)), 200)

    def test_short_stack_folds_trash(self):
        self.assertEqual(Player().betRequest(state(["9h", "3d"], stack=200)), 0)

    def test_bet_never_exceeds_stack(self):
        self.assertLessEqual(Player().betRequest(state(["Ah", "Ad"], stack=15)), 15)

    def test_bad_state_returns_zero(self):
        self.assertEqual(Player().betRequest({}), 0)


if __name__ == "__main__":
    unittest.main()
