import sys
import traceback
from collections import Counter

RANKS = {str(n): n for n in range(2, 11)}
RANKS.update({"T": 10, "J": 11, "Q": 12, "K": 13, "A": 14})

# Made-hand categories, higher is better.
HIGH_CARD, PAIR, TWO_PAIR, TRIPS, STRAIGHT, FLUSH, FULL_HOUSE, QUADS, STRAIGHT_FLUSH = range(9)


def rank_of(card):
    return RANKS[str(card["rank"])]


def has_straight(ranks):
    unique = set(ranks)
    if 14 in unique:
        unique.add(1)  # ace plays low in A-2-3-4-5
    return any(all(r + i in unique for i in range(5)) for r in range(1, 11))


def hand_category(cards):
    ranks = [rank_of(c) for c in cards]
    suits = Counter(c["suit"] for c in cards)
    counts = sorted(Counter(ranks).values(), reverse=True)

    flush_suit = next((s for s, n in suits.items() if n >= 5), None)
    if flush_suit and has_straight([rank_of(c) for c in cards if c["suit"] == flush_suit]):
        return STRAIGHT_FLUSH
    if counts[0] == 4:
        return QUADS
    if counts[0] == 3 and len(counts) > 1 and counts[1] >= 2:
        return FULL_HOUSE
    if flush_suit:
        return FLUSH
    if has_straight(ranks):
        return STRAIGHT
    if counts[0] == 3:
        return TRIPS
    if counts[0] == 2 and len(counts) > 1 and counts[1] == 2:
        return TWO_PAIR
    if counts[0] == 2:
        return PAIR
    return HIGH_CARD


def preflop_strength(hole):
    """Return 2 for premium, 1 for playable, 0 for trash."""
    a, b = sorted((rank_of(c) for c in hole), reverse=True)
    suited = hole[0]["suit"] == hole[1]["suit"]
    if a == b:
        return 2 if a >= 10 else 1
    if a == 14 and b >= 12:
        return 2
    if b >= 10 or (a == 14 and suited) or (suited and a - b == 1 and b >= 7):
        return 1
    return 0


def is_monster(hole):
    a, b = sorted((rank_of(c) for c in hole), reverse=True)
    return (a == b and a >= 12) or (a == 14 and b == 13)


def shove_range(hole):
    a, b = sorted((rank_of(c) for c in hole), reverse=True)
    suited = hole[0]["suit"] == hole[1]["suit"]
    return a == b or a == 14 or (a == 13 and b >= 10) or (a == 12 and b == 11) or (suited and b >= 10)


def call_shove_range(hole):
    a, b = sorted((rank_of(c) for c in hole), reverse=True)
    return (a == b and a >= 9) or (a == 14 and b >= 12)


def heads_up_range(hole):
    a, b = sorted((rank_of(c) for c in hole), reverse=True)
    return a == b or a >= 13 or (a == 12 and b >= 8)


class Player:
    VERSION = "ultragood_python_playerv0.4.0"

    def betRequest(self, game_state):
        try:
            return self.decide(game_state)
        except Exception:
            traceback.print_exc(file=sys.stderr)
            return 0

    def decide(self, game_state):
        me = game_state["players"][game_state["in_action"]]
        hole = me["hole_cards"]
        board = game_state.get("community_cards", [])
        stack = me["stack"]
        to_call = max(game_state["current_buy_in"] - me["bet"], 0)
        min_raise = to_call + game_state.get("minimum_raise", 0)

        big_blind = 2 * game_state.get("small_blind", 2)
        unraised = game_state["current_buy_in"] <= big_blind

        alive = [p for p in game_state["players"] if p.get("status") != "out"]

        if not board and stack <= 15 * big_blind:
            # Push or fold when short: big blinds are worth too much to bet-then-fold.
            if unraised:
                return stack if shove_range(hole) else 0
            return stack if call_shove_range(hole) else 0

        if not board:
            strength = preflop_strength(hole)
            if len(alive) == 2 and heads_up_range(hole):
                strength = max(strength, 1)
            already_raised = me["bet"] > big_blind
            if strength >= 1 and unraised:
                return min(max(min_raise, 3 * big_blind), stack)
            if strength == 2 and not already_raised:
                return min(max(min_raise, 3 * game_state["current_buy_in"]), stack)
            # Facing a re-raise: only monsters continue for big amounts; never re-raise again.
            if is_monster(hole):
                return min(to_call, stack)
            limit = stack // 5 if strength == 2 else stack // 10
            if strength >= 1 and to_call <= limit:
                return min(to_call, stack)
            return 0

        category = hand_category(hole + board)
        board_category = hand_category(board) if len(board) >= 2 else HIGH_CARD
        pot = game_state.get("pot", 0)
        bet_size = min(max(min_raise, pot // 2), stack)
        # Only count hands where our hole cards add something over the board.
        if category > board_category:
            if category >= TRIPS:
                return bet_size
            if category == TWO_PAIR:
                if to_call == 0:
                    return bet_size
                return min(to_call, stack) if to_call <= stack // 3 else 0
            if category == PAIR:
                top = max(rank_of(c) for c in hole) >= max(rank_of(c) for c in board)
                if top and to_call == 0:
                    return bet_size
                if to_call <= (stack // 5 if top else stack // 20):
                    return min(to_call, stack)
                return 0
        # Continuation bet: we were last to raise before the flop and nobody bet yet.
        if to_call == 0 and len(board) == 3 and preflop_strength(hole) >= 1:
            return bet_size
        return 0

    def showdown(self, game_state):
        pass
