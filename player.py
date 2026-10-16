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


class Player:
    VERSION = "ultragood_python_playerv0.1.0"

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

        if not board:
            strength = preflop_strength(hole)
            if strength == 2:
                return min(max(min_raise, 4 * game_state.get("small_blind", 10)), stack)
            if strength == 1 and to_call <= stack // 10:
                return min(to_call, stack)
            return 0

        category = hand_category(hole + board)
        board_category = hand_category(board) if len(board) >= 2 else HIGH_CARD
        # Only count hands where our hole cards add something over the board.
        if category > board_category:
            if category >= TWO_PAIR:
                return min(max(min_raise, game_state.get("pot", 0) // 2), stack)
            if category == PAIR and to_call <= stack // 5:
                return min(to_call, stack)
        return 0

    def showdown(self, game_state):
        pass
