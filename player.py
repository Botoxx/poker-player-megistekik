# Strategy is documented in STRATEGY.md, which is authoritative; this file implements it.
import sys
import time
import traceback
from collections import Counter

import storage
from equity import equity, evaluate7, to_tuple

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



def has_open_ended_draw(cards):
    unique = {rank_of(c) for c in cards}
    # Four in a row with room on both ends; A-2-3-4 and J-Q-K-A only fill one way.
    return any(all(r + i in unique for i in range(4)) for r in range(2, 11))


def has_draw(hole, board):
    """True if our hole cards make a flush or open-ended straight draw the board alone doesn't."""
    cards = hole + board
    suits = Counter(c["suit"] for c in cards)
    hole_suits = {c["suit"] for c in hole}
    if any(n == 4 and s in hole_suits for s, n in suits.items()):
        return True
    return has_open_ended_draw(cards) and not has_open_ended_draw(board)


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


def tight_shove_range(hole):
    a, b = sorted((rank_of(c) for c in hole), reverse=True)
    return (a == b and a >= 5) or (a == 14 and b >= 9) or (a == 13 and b == 12)


def wide_call_range(hole):
    """Hands ahead of a ~30% shoving range."""
    a, b = sorted((rank_of(c) for c in hole), reverse=True)
    return (a == b and a >= 6) or (a == 14 and b >= 10) or (a == 13 and b == 12)


def call_shove_range(hole):
    a, b = sorted((rank_of(c) for c in hole), reverse=True)
    return (a == b and a >= 9) or (a == 14 and b >= 12)


def heads_up_range(hole):
    a, b = sorted((rank_of(c) for c in hole), reverse=True)
    return a == b or a >= 13 or (a == 12 and b >= 8)


# Opponent model: game_id -> name -> {"hands": set of rounds seen, "raises": set of rounds raised}.
# Lives in process memory; a restart resets it and the bot plays without reads.
OPPONENTS = {}
MAX_GAMES = 50
OUR_NAME = [None]  # learned from bet requests; the showdown request has no in_action
MIN_HANDS = 8

# Saved across games and restarts: "name|version" -> counts. A new opponent version starts fresh.
def prune_old_versions(profiles):
    """Keep only each opponent's most recently seen version: an old version no longer predicts how it plays.

    Profiles saved before "seen" existed are kept until a version of that opponent is seen again.
    """
    newest = {}
    for key, prof in profiles.items():
        name = key.split("|", 1)[0]
        if "seen" in prof and prof["seen"] > profiles.get(newest.get(name), {}).get("seen", -1):
            newest[name] = key
    for key in [k for k in profiles if k.split("|", 1)[0] in newest and newest[k.split("|", 1)[0]] != k]:
        del profiles[key]
    return profiles


PROFILES = prune_old_versions(storage.load())
ROUNDS = {}  # game_id -> {"last": round seen in bet requests, "done": rounds already added to PROFILES}


def profile_key(p):
    return "%s|%s" % (p["name"], p.get("version", ""))


def commit_round(game_state, rnd):
    """Add one finished hand of this game's per-hand flags to the saved profiles, once."""
    gid = game_state.get("game_id", "?")
    rounds = ROUNDS.setdefault(gid, {"last": None, "done": set()})
    while len(ROUNDS) > MAX_GAMES:
        ROUNDS.pop(next(iter(ROUNDS)))
    if rnd is None or rnd in rounds["done"]:
        return
    rounds["done"].add(rnd)
    game = OPPONENTS.get(gid, {})
    for p in game_state["players"]:
        s = game.get(p["name"])
        if p["name"] == OUR_NAME[0] or not s or rnd not in s["hands"]:
            continue
        prof = PROFILES.setdefault(profile_key(p), {})
        for k in ("hands", "raises", "shoves"):
            prof[k] = prof.get(k, 0) + (1 if rnd in s[k] else 0)
        prof["seen"] = time.time()
    prune_old_versions(PROFILES)
    storage.save_soon(PROFILES)


def stats_for(game_state, p):
    """Counts for an opponent: the saved profile once it has seen more hands than this game, else this game's."""
    s = OPPONENTS.get(game_state.get("game_id", "?"), {}).get(p["name"])
    local = {}
    if s:
        local = {k: len(s.get(k, ())) for k in ("hands", "raises", "shoves")}
        local.update(big_showdowns=s.get("big_showdowns", 0), weak_showdowns=s.get("weak_showdowns", 0))
    saved = PROFILES.get(profile_key(p), {})
    return saved if saved.get("hands", 0) >= local.get("hands", 0) and saved else local


def observe(game_state):
    game = OPPONENTS.setdefault(game_state.get("game_id", "?"), {})
    while len(OPPONENTS) > MAX_GAMES:
        OPPONENTS.pop(next(iter(OPPONENTS)))
    rnd = game_state.get("round")
    big_blind = 2 * game_state.get("small_blind", 1)
    OUR_NAME[0] = game_state["players"][game_state["in_action"]]["name"]
    # A new round means the last one is over, even if no showdown request arrived for it.
    last = ROUNDS.get(game_state.get("game_id", "?"), {}).get("last")
    if last is not None and last != rnd:
        commit_round(game_state, last)
    ROUNDS.setdefault(game_state.get("game_id", "?"), {"last": None, "done": set()})["last"] = rnd
    # Largest bet each opponent made this hand on any street; the showdown state has bets reset to 0.
    for i, p in enumerate(game_state["players"]):
        if i != game_state["in_action"] and p.get("status") != "out":
            s = game.setdefault(p["name"], {"hands": set(), "raises": set(), "shoves": set()})
            bets = s.setdefault("max_bet", {})
            bets[rnd] = max(bets.get(rnd, 0), p.get("bet", 0))
            for old in [r for r in bets if r != rnd and r != rnd - 1]:
                del bets[old]
    if game_state.get("community_cards"):
        return
    for i, p in enumerate(game_state["players"]):
        if i == game_state["in_action"] or p.get("status") == "out":
            continue
        s = game.setdefault(p["name"], {"hands": set(), "raises": set(), "shoves": set()})
        s["hands"].add(rnd)
        if p.get("bet", 0) > big_blind:
            s["raises"].add(rnd)
        if p.get("bet", 0) > 0 and p.get("stack", 1) == 0:
            s["shoves"].add(rnd)


def raiser_style(game_state):
    """Return "shover", "loose", "tight" or None for the opponent holding the current highest bet."""
    me = game_state["in_action"]
    top = max((p for i, p in enumerate(game_state["players"]) if i != me),
              key=lambda p: p.get("bet", 0), default=None)
    s = stats_for(game_state, top) if top else {}
    if s.get("hands", 0) < MIN_HANDS:
        return None
    if s.get("shoves", 0) / s["hands"] >= 0.15:
        return "shover"
    freq = s.get("raises", 0) / s["hands"]
    return "loose" if freq >= 0.35 else "tight" if freq < 0.12 else None


def hu_open_range(hole):
    """About 70% of hands: what to raise heads-up when nobody has raised."""
    a, b = sorted((rank_of(c) for c in hole), reverse=True)
    return a == b or a >= 10 or hole[0]["suit"] == hole[1]["suit"] or a - b <= 2


def hu_call_shove_range(hole):
    a, b = sorted((rank_of(c) for c in hole), reverse=True)
    return a == b or a == 14 or (a == 13 and b >= 10)


def shover_alive(game_state):
    """True if an opponent still in the game shoves preflop in at least 15% of hands we saw."""
    me = game_state["in_action"]
    for i, p in enumerate(game_state["players"]):
        if i == me or p.get("status") == "out":
            continue
        s = stats_for(game_state, p)
        if s.get("hands", 0) < MIN_HANDS:
            continue
        if s.get("shoves", 0) / s["hands"] >= 0.15:
            return True
    return False


def record_showdown(game_state):
    """Count opponents who put in 10+ big blinds and showed down less than top pair."""
    game = OPPONENTS.get(game_state.get("game_id", "?"), {})
    board = [to_tuple(c) for c in game_state.get("community_cards", [])]
    if len(board) != 5:
        return
    board_score = evaluate7(board)
    top_board = max(r for r, _ in board)
    big_blind = 2 * game_state.get("small_blind", 1)
    rnd = game_state.get("round")
    for p in game_state["players"]:
        s = game.get(p["name"])
        hole = p.get("hole_cards") or []
        if p["name"] == OUR_NAME[0] or p.get("status") != "active" or len(hole) != 2 or not s:
            continue
        if s.get("max_bet", {}).get(rnd, 0) < 10 * big_blind:
            continue
        score = evaluate7([to_tuple(c) for c in hole] + board)
        weak = score <= board_score or (score[0] == 1 and score[1] < top_board) or score[0] == 0
        for counts in (s, PROFILES.setdefault(profile_key(p), {})):
            counts["big_showdowns"] = counts.get("big_showdowns", 0) + 1
            counts["weak_showdowns"] = counts.get("weak_showdowns", 0) + (1 if weak else 0)


def bettor_profile(game_state):
    """Return "bluffer", "honest" or None for the opponent holding the current highest bet."""
    me = game_state["in_action"]
    top = max((p for i, p in enumerate(game_state["players"]) if i != me),
              key=lambda p: p.get("bet", 0), default=None)
    s = stats_for(game_state, top) if top else {}
    big, weak = s.get("big_showdowns", 0), s.get("weak_showdowns", 0)
    if big >= 2 and weak / big >= 0.4:
        return "bluffer"
    if big >= 3 and weak == 0:
        return "honest"
    return None


# Counters read from the opponents' public source (16 Oct). All three value-bet and rarely bluff.
HONEST_BETTORS = {"nontechyk", "nontekik", "bpex"}


def top_bettor(game_state):
    """The opponent holding the highest bet, or None."""
    me = game_state["in_action"]
    return max((p for i, p in enumerate(game_state["players"]) if i != me),
               key=lambda p: p.get("bet", 0), default=None)


def resteal_call_range(hole):
    """nontekik re-shoves its top 30% over our opens; these hands are ahead of that range."""
    a, b = sorted((rank_of(c) for c in hole), reverse=True)
    return (a == b and a >= 6) or (a == 14 and b >= 9) or (a == 13 and b >= 11)


def light_3bet_range(hole):
    """~30% of hands: what we re-raise over nontekik's wide open to make it fold its junk."""
    a, b = sorted((rank_of(c) for c in hole), reverse=True)
    suited = hole[0]["suit"] == hole[1]["suit"]
    if a == b:
        return True  # any pair
    if suited:
        return a == 14 or (a >= 10 and b >= 10) or (a - b == 1 and b >= 4)
    return a >= 12 and b >= 11  # KQo/AQo/AJo/AKo


class Player:
    VERSION = "ultragood_python_playerv0.26.0"

    def betRequest(self, game_state):
        try:
            observe(game_state)
        except Exception:
            traceback.print_exc(file=sys.stderr)
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
        try:
            style = raiser_style(game_state) if not unraised else None
        except Exception:
            style = None

        heads_up = len(alive) == 2
        raiser = top_bettor(game_state) if not board and not unraised else None
        if raiser and raiser["name"] == "nontekik" and raiser.get("stack", 1) == 0 and resteal_call_range(hole):
            return min(to_call, stack)
        if (raiser and raiser["name"] == "bpex" and me["bet"] <= big_blind
                and raiser.get("bet", 0) >= 6 * big_blind and not is_monster(hole)):
            return 0  # bpex opens about 6.5 big blinds only with JJ+ / AKs
        # nontekik v1.1.2 opens 60-70% and folds to re-pressure when deep: 3-bet to take it down.
        if (raiser and raiser["name"] == "nontekik" and me["bet"] <= big_blind
                and big_blind < raiser.get("bet", 0) <= 4 * big_blind
                and stack > 30 * big_blind and raiser.get("stack", 0) > 25 * big_blind
                and (is_monster(hole) or wide_call_range(hole) or light_3bet_range(hole))):
            three_bet = min(3 * raiser["bet"], stack)
            if three_bet <= stack // 4:
                return three_bet
        try:
            shover = shover_alive(game_state)
        except Exception:
            shover = False
        if not board and heads_up:
            # Heads-up the blinds come every hand: folding most hands bleeds the stack.
            if stack <= 15 * big_blind:
                if unraised:
                    return stack if heads_up_range(hole) else 0
                return stack if hu_call_shove_range(hole) or is_monster(hole) else 0
            if unraised and shover:
                # Against a shover, only raise hands that can call the re-shove; limp the rest.
                if wide_call_range(hole) or is_monster(hole):
                    return min(max(min_raise, 5 * big_blind // 2), stack)
                return min(to_call, stack) if heads_up_range(hole) else 0
            if unraised and hu_open_range(hole):
                return min(max(min_raise, 5 * big_blind // 2), stack)
            if is_monster(hole):
                return min(max(min_raise, 3 * game_state["current_buy_in"]), stack) if me["bet"] <= big_blind else min(to_call, stack)
            if heads_up_range(hole) and to_call <= stack // 6:
                return min(to_call, stack)
            if not unraised:
                return 0

        if not board and stack <= 15 * big_blind:
            # Push or fold when short: big blinds are worth too much to bet-then-fold.
            if unraised:
                # Opponents call wide against frequent shovers; only shove wide when desperate.
                in_range = shove_range(hole) if stack <= 10 * big_blind else tight_shove_range(hole)
                return stack if in_range else 0
            # Raising often is not shoving wide: against either, call only with hands ahead of a wide range.
            wide = style in ("loose", "shover") and wide_call_range(hole)
            return stack if call_shove_range(hole) or wide else 0

        if not board:
            strength = preflop_strength(hole)
            if len(alive) == 2 and heads_up_range(hole):
                strength = max(strength, 1)
            already_raised = me["bet"] > big_blind
            if strength >= 1 and unraised:
                if shover and strength < 2 and not wide_call_range(hole):
                    return 0  # opening would just get shoved on and folded
                if strength == 2 and any(q["name"] == "nontekik" for q in alive):
                    return min(min_raise, stack)  # min-raise looks weak to nontekik and draws re-shoves
                return min(max(min_raise, 3 * big_blind), stack)
            if strength == 2 and not already_raised:
                raise_to = max(min_raise, 3 * game_state["current_buy_in"])
                if raise_to < stack // 3:
                    return raise_to
                # Raising a third of our stack and folding to a shove is the worst result.
                # Short enough: commit with a shove. Deep: just call a moderate raise.
                if stack <= 20 * big_blind:
                    return stack
                return min(to_call, stack) if to_call <= stack // 4 else 0
            # Facing a re-raise: only monsters continue for big amounts; never re-raise again.
            if is_monster(hole):
                ranks = sorted((rank_of(c) for c in hole), reverse=True)
                aces_kings = ranks[0] == ranks[1] and ranks[0] >= 13
                # Deep, these opponents re-raise this big only for value (AA/KK/QQ/AK); QQ and A-K
                # are behind that range, so folding beats calling off ~90 big blinds with them.
                if not aces_kings and stack > 25 * big_blind and to_call > 25 * big_blind:
                    return 0
                return min(to_call, stack)
            if style == "shover" and wide_call_range(hole):
                return min(to_call, stack)
            if style == "tight" and to_call > 4 * big_blind:
                return 0
            if style == "loose" and strength >= 1 and to_call <= stack // 4:
                return min(to_call, stack)
            limit = stack // 5 if strength == 2 else stack // 10
            if strength >= 1 and to_call <= limit:
                return min(to_call, stack)
            return 0

        try:
            decision = self.postflop_by_equity(game_state, me, hole, board, stack, to_call, min_raise)
        except Exception:
            traceback.print_exc(file=sys.stderr)
            decision = None
        if decision is not None:
            return decision

        category = hand_category(hole + board)
        board_category = hand_category(board) if len(board) >= 2 else HIGH_CARD
        pot = game_state.get("pot", 0)
        bet_size = min(max(min_raise, pot // 2), stack)
        in_hand = sum(1 for p in game_state["players"] if p.get("status") == "active")
        hole_ranks = [rank_of(c) for c in hole]
        board_ranks = [rank_of(c) for c in board]
        if board_category == PAIR and category == TWO_PAIR:
            # One of the "two pairs" may be on the board, where everyone has it.
            paired = {r for r in hole_ranks if board_ranks.count(r) == 1}
            if len(paired) < 2:
                category, board_category = PAIR, HIGH_CARD
        # Only count hands where our hole cards add something over the board.
        if category > board_category:
            if category >= TRIPS:
                return bet_size
            if category == TWO_PAIR:
                if to_call == 0:
                    return bet_size
                return min(to_call, stack) if to_call <= stack // 3 else 0
            if category == PAIR:
                if hole_ranks[0] == hole_ranks[1]:
                    top = hole_ranks[0] > max(board_ranks)  # overpair
                else:
                    top = max((r for r in hole_ranks if r in board_ranks), default=0) == max(board_ranks)
                if top and to_call == 0 and (len(board) < 5 or bet_size <= stack // 4):
                    return bet_size
                if to_call <= (stack // 5 if top else stack // 20) or (top and to_call * 3 <= pot):
                    return min(to_call, stack)
                # Too expensive for the pair alone; a draw below may still justify a call.
        # Continuation bet: we were last to raise before the flop and nobody bet yet.
        if to_call == 0 and len(board) == 3 and preflop_strength(hole) >= 1 and in_hand <= 2:
            return bet_size
        # Chase draws only before the river and only when the pot pays for it.
        if to_call > 0 and len(board) in (3, 4) and has_draw(hole, board):
            max_call = pot // 3 if len(board) == 3 else pot // 5
            if to_call <= min(max_call, stack // 10):
                return to_call
        return 0

    def postflop_by_equity(self, game_state, me, hole, board, stack, to_call, min_raise):
        """Bet by Monte Carlo win chance against the opponents still in the hand; None to fall back to rules."""
        in_hand = sum(1 for p in game_state["players"] if p.get("status") == "active")
        opponents = max(in_hand - 1, 1)
        pot = game_state.get("pot", 0)
        big_bet = to_call > 0 and to_call >= stack // 4 and to_call >= pot // 2
        try:
            profile = bettor_profile(game_state) if big_bet else None
        except Exception:
            profile = None
        # A bet of a quarter of our stack and half the pot means a made hand, not a random one,
        # unless this bettor has shown down weak hands after betting big before.
        try:
            if to_call > 0 and not big_bet:
                profile = bettor_profile(game_state)
        except Exception:
            profile = None
        # Any bet means the bettor usually holds a made hand; a big bet means top pair or better.
        level = 0 if to_call == 0 else 2 if big_bet else 1
        bettor = top_bettor(game_state) if to_call > 0 else None
        honest = bettor is not None and bettor["name"] in HONEST_BETTORS
        if honest:
            # Their source has no pure bluffs, except bpex's small heads-up flop/turn bets (30% bluffs).
            small_bpex = bettor["name"] == "bpex" and len(board) < 5 and to_call * 5 <= pot * 2
            level = 1 if small_bpex else 2
        if profile == "bluffer":
            level = max(level - 1, 0)
        others = [q for i, q in enumerate(game_state["players"])
                  if i != game_state["in_action"] and q.get("status") == "active"]
        if to_call == 0 and len(others) == 1 and others[0]["name"] == "nontechyk":
            # nontechyk only bets with 0.6+ equity and needs about that much to call a 55% pot bet.
            return min(max(min_raise, 55 * pot // 100), stack)
        win, sims = equity(hole, board, opponents, range_level=level)
        if sims < 100:
            return None
        if to_call == 0:
            if win >= 0.65:
                return min(max(min_raise, 2 * pot // 3), stack)
            if win >= 0.5 and opponents == 1:
                return min(max(min_raise, pot // 2), stack)
            return 0
        # A bettor's range beats a random hand: discount up to 10 points as the bet grows toward the pot.
        win -= 0.10 * min(1.0, to_call / max(pot, 1))
        price = to_call / (pot + to_call)
        floor = {"bluffer": 0.0, "honest": 0.60}.get(profile, 0.60 if honest else 0.55)
        if big_bet and win < floor:
            return 0
        if win >= 0.80:
            return min(max(min_raise, pot), stack)
        if win >= price + 0.03:
            return min(to_call, stack)
        return 0

    def showdown(self, game_state):
        try:
            record_showdown(game_state)
            commit_round(game_state, game_state.get("round"))
        except Exception:
            traceback.print_exc(file=sys.stderr)
