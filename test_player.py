import unittest

from player import Player, hand_category, preflop_strength, PAIR, TWO_PAIR, STRAIGHT, FLUSH, FULL_HOUSE


def c(spec):
    rank, suit = spec[:-1], {"h": "hearts", "d": "diamonds", "s": "spades", "c": "clubs"}[spec[-1]]
    return {"rank": rank, "suit": suit}


def state(hole, board=(), current_buy_in=20, my_bet=10, stack=1000, minimum_raise=20, pot=30, others=3):
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
        ] + [{"name": f"extra{i}", "stack": 1000, "bet": 0, "status": "active"} for i in range(others - 1)],
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

    def test_equity_folds_air_to_pot_bet(self):
        gs = state(["7c", "2d"], board=["8s", "Ah", "8h"], current_buy_in=700, my_bet=100, stack=600, pot=1300)
        self.assertEqual(Player().betRequest(gs), 0)

    def test_equity_raises_full_house(self):
        gs = state(["Ac", "As"], board=["8s", "Ah", "8d"], current_buy_in=200, my_bet=100, stack=900, pot=500)
        self.assertGreater(Player().betRequest(gs), 100)

    def test_equity_calls_nut_flush_draw_at_good_price(self):
        gs = state(["Ah", "7h"], board=["2h", "9h", "Kc"], current_buy_in=120, my_bet=100, stack=900, pot=400, others=1)
        self.assertEqual(Player().betRequest(gs), 20)

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

    def test_calls_frequent_shover_with_pocket_sevens(self):
        import player
        player.OPPONENTS.clear()
        for rnd in range(10):  # "other" shoves every hand
            gs = state(["7h", "2d"], current_buy_in=1000)
            gs.update(game_id="s", round=rnd)
            gs["players"][0].update(bet=1000, stack=0)
            Player().betRequest(gs)
        gs = state(["7c", "7d"], current_buy_in=1000, my_bet=60, stack=940)
        gs.update(game_id="s", round=11)
        gs["players"][0].update(bet=1000, stack=0)
        self.assertEqual(Player().betRequest(gs), 940)

    def test_overpair_calls_with_good_pot_odds(self):
        # KK on Q-6-4 facing 300 into a 1200 pot: 4:1, call even though it is over a fifth of our stack.
        s = state(["Kh", "Kd"], board=["4d", "Qh", "6d"], current_buy_in=300, my_bet=0, stack=1000, pot=1200)
        self.assertEqual(Player().betRequest(s), 300)

    def test_heads_up_opens_weak_suited_hand(self):
        s = state(["7h", "3h"], current_buy_in=20, my_bet=10, others=1)
        self.assertEqual(Player().betRequest(s), 50)

    def test_heads_up_defends_king_rag(self):
        s = state(["Kh", "4d"], current_buy_in=60, my_bet=20, others=1)
        self.assertEqual(Player().betRequest(s), 40)

    def test_no_light_open_when_shover_at_table(self):
        import player
        player.OPPONENTS.clear()
        for rnd in range(10):
            gs = state(["7h", "2d"], current_buy_in=1000)
            gs.update(game_id="sh", round=rnd)
            gs["players"][0].update(bet=1000, stack=0)
            Player().betRequest(gs)
        gs = state(["Jh", "10d"])
        gs.update(game_id="sh", round=11)
        self.assertEqual(Player().betRequest(gs), 0)

    def test_big_reraise_commits_instead_of_raise_fold(self):
        # A-Q facing a raise to 160: 3x would be 480, a third of the stack or more, so don't raise.
        # 700 behind (35 big blinds) is deep: call. 300 behind (15 big blinds... here 20 bb cap): shove.
        self.assertEqual(Player().betRequest(state(["Qh", "As"], current_buy_in=160, my_bet=20, stack=700)), 140)
        self.assertEqual(Player().betRequest(state(["Qh", "As"], current_buy_in=160, my_bet=20, stack=390)), 390)

    def test_second_pair_folds_to_big_bet(self):
        # Round 34 knockout: K-10 on K-6-A-9 facing 420 into 700 with 790 behind.
        gs = state(["Ks", "10s"], board=["Kh", "6s", "Ad", "9s"], current_buy_in=620, my_bet=200,
                   stack=790, pot=700, others=1)
        self.assertEqual(Player().betRequest(gs), 0)

    def test_set_still_calls_big_bet(self):
        gs = state(["6d", "6c"], board=["Kh", "6s", "Ad", "9s"], current_buy_in=620, my_bet=200,
                   stack=790, pot=700, others=1)
        self.assertGreaterEqual(Player().betRequest(gs), 420)

    def k10_spot(self, game_id):
        gs = state(["Ks", "10s"], board=["Kh", "6s", "Ad", "9s"], current_buy_in=620, my_bet=200,
                   stack=790, pot=700, others=1)
        gs.update(game_id=game_id, round=50)
        gs["players"][0]["bet"] = 620
        return gs

    def teach_showdowns(self, game_id, hole, n):
        """Opponent bets 300 (15 big blinds) then shows `hole` on a fixed board, n times."""
        for rnd in range(n):
            gs = state(["7h", "2d"], board=["Qh", "8c", "4d"], current_buy_in=300, my_bet=0, others=1)
            gs.update(game_id=game_id, round=rnd)
            gs["players"][0]["bet"] = 300
            Player().betRequest(gs)
            sd = {"game_id": game_id, "round": rnd, "small_blind": 10,
                  "community_cards": [c(x) for x in ["Qh", "8c", "4d", "2s", "Jc"]],
                  "players": [{"name": "other", "status": "active", "bet": 0, "stack": 0,
                               "hole_cards": [c(x) for x in hole]},
                              {"name": "us", "status": "active", "bet": 0, "stack": 0,
                               "hole_cards": [c("7h"), c("2d")]}]}
            Player().showdown(sd)

    def test_calls_big_bet_from_known_bluffer(self):
        import player
        player.OPPONENTS.clear()
        self.teach_showdowns("bluff", ["6h", "3c"], 2)  # bet big twice with nothing
        self.assertEqual(Player().betRequest(self.k10_spot("bluff")), 420)

    def test_folds_big_bet_from_honest_bettor(self):
        import player
        player.OPPONENTS.clear()
        self.teach_showdowns("honest", ["Qd", "Qs"], 3)  # bet big three times with a set
        self.assertEqual(Player().betRequest(self.k10_spot("honest")), 0)

    def test_ace_high_folds_to_river_bet_on_paired_board(self):
        # Round 22 call-down: A-6 with no pair on J-7-4-10-7 facing 445 into a 900 pot.
        gs = state(["As", "6s"], board=["Jc", "7c", "4h", "10h", "7d"], current_buy_in=845, my_bet=400,
                   stack=600, pot=1245, others=1)
        gs["players"][0]["bet"] = 845
        self.assertEqual(Player().betRequest(gs), 0)

    def test_underpair_folds_to_turn_bet(self):
        # Round 29 call-down: 2-2 on J-4-J-7 facing 120 into a 250 pot.
        gs = state(["2s", "2c"], board=["Jh", "4c", "Js", "7c"], current_buy_in=230, my_bet=110,
                   stack=800, pot=370, others=1)
        gs["players"][0]["bet"] = 230
        self.assertEqual(Player().betRequest(gs), 0)

    def test_deep_ace_queen_calls_instead_of_shoving(self):
        # A-Q with 2,261 behind (big blind 100) facing a raise to 350: call, don't shove 22+ big blinds.
        gs = state(["Qd", "Ac"], current_buy_in=350, my_bet=50, stack=2261)
        gs["small_blind"] = 50
        self.assertEqual(Player().betRequest(gs), 300)

    def test_calls_nontekik_reshove_with_sixes(self):
        gs = state(["6h", "6d"], current_buy_in=400, my_bet=60, stack=900)
        gs["players"][0].update(name="nontekik", bet=400, stack=0)
        self.assertEqual(Player().betRequest(gs), 340)

    def test_folds_tens_to_big_bpex_open(self):
        gs = state(["10h", "10d"], current_buy_in=140, my_bet=0, stack=1000)
        gs["players"][0].update(name="bpex", bet=140)
        self.assertEqual(Player().betRequest(gs), 0)

    def test_bets_into_nontechyk_check_heads_up(self):
        gs = state(["7h", "2d"], board=["Kc", "9s", "4d"], current_buy_in=0, my_bet=0, pot=200, others=1)
        gs["players"][0].update(name="nontechyk", bet=0)
        self.assertEqual(Player().betRequest(gs), 110)

    def test_folds_second_pair_to_honest_half_pot_river_bet(self):
        gs = state(["Ks", "10s"], board=["Kh", "6s", "Ad", "9s", "2c"], current_buy_in=150, my_bet=0,
                   stack=900, pot=450, others=1)
        gs["players"][0].update(name="nontechyk", bet=150)
        self.assertEqual(Player().betRequest(gs), 0)

    def test_min_raises_premium_when_nontekik_alive(self):
        gs = state(["Ah", "Ad"], current_buy_in=20, my_bet=0)
        gs["players"][2]["name"] = "nontekik"
        self.assertEqual(Player().betRequest(gs), 40)

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
