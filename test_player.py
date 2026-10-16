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

    def test_board_pair_plus_our_pair_is_not_two_pair(self):
        # A-Q on A-8-8 facing a big bet: one pair of aces, not two pair, so no big call.
        gs = state(["Qh", "As"], board=["8s", "Ah", "8h"], current_buy_in=400, my_bet=100, stack=600, pot=600)
        self.assertEqual(Player().betRequest(gs), 0)

    def test_calls_wider_against_loose_raiser(self):
        import player
        player.OPPONENTS.clear()
        for rnd in range(10):  # "other" raises to 100 every hand
            gs = state(["7h", "2d"], current_buy_in=100)
            gs.update(game_id="g", round=rnd)
            gs["players"][0]["bet"] = 100
            Player().betRequest(gs)
        gs = state(["Jh", "10d"], current_buy_in=200, my_bet=60)
        gs.update(game_id="g", round=11)
        gs["players"][0]["bet"] = 200
        self.assertEqual(Player().betRequest(gs), 140)
        gs["game_id"] = "fresh"  # no reads in a new game: fold the same spot
        self.assertEqual(Player().betRequest(gs), 0)

    def test_twelve_big_blinds_folds_queen_jack(self):
        self.assertEqual(Player().betRequest(state(["Qd", "Jd"], stack=240)), 0)

    def test_bet_never_exceeds_stack(self):
        self.assertLessEqual(Player().betRequest(state(["Ah", "Ad"], stack=15)), 15)

    def test_flush_draw_calls_when_cheap(self):
        s = state(["Ah", "7h"], board=["2h", "9h", "Kc"], current_buy_in=20, my_bet=0, pot=100)
        self.assertEqual(Player().betRequest(s), 20)

    def test_open_ended_draw_calls_when_cheap(self):
        s = state(["8d", "9c"], board=["10h", "Js", "2c"], current_buy_in=20, my_bet=0, pot=100)
        self.assertEqual(Player().betRequest(s), 20)

    def test_draw_folds_when_too_expensive(self):
        s = state(["Ah", "7h"], board=["2h", "9h", "Kc"], current_buy_in=80, my_bet=0, pot=100)
        self.assertEqual(Player().betRequest(s), 0)

    def test_draw_folds_on_river(self):
        s = state(["Ah", "7h"], board=["2h", "9h", "Kc", "3d", "4s"], current_buy_in=20, my_bet=0, pot=100)
        self.assertEqual(Player().betRequest(s), 0)

    def test_board_flush_draw_without_our_suit_folds(self):
        s = state(["Ac", "7d"], board=["2h", "9h", "Kh", "3h"], current_buy_in=10, my_bet=0, pot=100)
        self.assertEqual(Player().betRequest(s), 0)

    def test_overpair_on_paired_board_calls(self):
        s = state(["Ah", "Ad"], board=["7s", "7c", "2h"], current_buy_in=50, my_bet=0, pot=150)
        self.assertEqual(Player().betRequest(s), 50)

    def test_top_pair_on_paired_board_calls(self):
        s = state(["Kh", "9d"], board=["Ks", "7c", "7h"], current_buy_in=50, my_bet=0, pot=150)
        self.assertEqual(Player().betRequest(s), 50)

    def test_two_real_pairs_on_paired_board_count(self):
        s = state(["Kh", "Qd"], board=["Ks", "Qc", "7h", "7d"], current_buy_in=0, my_bet=0, pot=150)
        self.assertGreater(Player().betRequest(s), 0)

    def test_bottom_pair_with_ace_kicker_is_not_top_pair(self):
        s = state(["Ac", "5d"], board=["Ks", "9c", "5h"], current_buy_in=150, my_bet=0, pot=300)
        self.assertEqual(Player().betRequest(s), 0)

    def test_weak_pair_with_flush_draw_calls(self):
        s = state(["7h", "4h"], board=["Kh", "9h", "4d"], current_buy_in=60, my_bet=0, pot=300)
        self.assertEqual(Player().betRequest(s), 60)

    def test_bad_state_returns_zero(self):
        self.assertEqual(Player().betRequest({}), 0)


if __name__ == "__main__":
    unittest.main()
