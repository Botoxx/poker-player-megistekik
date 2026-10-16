"""7-card hand evaluation and Monte Carlo equity against random opponent hands."""
import random
import time
from collections import Counter

RANK_VALUES = {str(n): n for n in range(2, 11)}
RANK_VALUES.update({"T": 10, "J": 11, "Q": 12, "K": 13, "A": 14})
DECK = [(r, s) for r in range(2, 15) for s in "hdsc"]


def to_tuple(card):
    return RANK_VALUES[str(card["rank"])], card["suit"][0]


def straight_high(ranks):
    """Highest card of the best straight in a set of ranks, or 0."""
    if 14 in ranks:
        ranks = ranks | {1}
    for high in range(14, 4, -1):
        if all(high - i in ranks for i in range(5)):
            return high
    return 0


def evaluate7(cards):
    """Score 5-7 (rank, suit) cards; higher tuples are better hands."""
    suits = Counter(s for _, s in cards)
    flush_suit = next((s for s, n in suits.items() if n >= 5), None)
    if flush_suit:
        flush_ranks = sorted((r for r, s in cards if s == flush_suit), reverse=True)
        high = straight_high(set(flush_ranks))
        if high:
            return (8, high)
    counts = Counter(r for r, _ in cards)
    # Ranks ordered by (count, rank): quads first, then trips, pairs, singles.
    groups = sorted(counts.items(), key=lambda kv: (kv[1], kv[0]), reverse=True)
    if groups[0][1] == 4:
        kicker = max(r for r in counts if r != groups[0][0])
        return (7, groups[0][0], kicker)
    trips = sorted((r for r, n in counts.items() if n == 3), reverse=True)
    pairs = sorted((r for r, n in counts.items() if n == 2), reverse=True)
    if trips and (len(trips) > 1 or pairs):
        return (6, trips[0], max(trips[1:] + pairs))
    if flush_suit:
        return (5,) + tuple(flush_ranks[:5])
    high = straight_high(set(counts))
    if high:
        return (4, high)
    singles = sorted((r for r, n in counts.items() if n == 1), reverse=True)
    if trips:
        return (3, trips[0]) + tuple(singles[:2])
    if len(pairs) >= 2:
        kicker = max(singles + pairs[2:])
        return (2, pairs[0], pairs[1], kicker)
    if pairs:
        return (1, pairs[0]) + tuple(singles[:3])
    return (0,) + tuple(singles[:5])


def max_pair_category(shared):
    """Category the board alone shows with 3-4 cards: 1 if paired, 3 for trips, else 0."""
    top = max(Counter(r for r, _ in shared).values(), default=1)
    return {1: 0, 2: 1, 3: 3, 4: 7}[top]


def improves_board(hand, shared, board_score):
    """True if two hole cards make top pair or better with the current board.

    That means two pair or better that the board alone doesn't show, or a pair at least as
    high as the board's top card (top pair or an overpair).
    """
    score = evaluate7(hand + shared)
    if score[0] <= board_score[0]:
        return False
    return score[0] >= 2 or score[1] >= max(r for r, _ in shared)


def made_hand(hand, shared, board_score):
    """True if the hole cards make a pair or better that the board alone doesn't show."""
    return evaluate7(hand + shared)[0] > board_score[0]


def equity(hole, board, opponents, budget_s=0.15, max_sims=800, rng=random, strong_range=False, range_level=None):
    """Share of pots we win against `opponents` hands. Returns (equity, simulations run).

    range_level narrows the first opponent (the bettor): 0 random, 1 a made hand (pair or better
    with their hole cards), 2 top pair or better. Other opponents get random hands.
    strong_range=True is the old spelling of range_level=2 for every opponent.
    """
    mine = [to_tuple(c) for c in hole]
    shared = [to_tuple(c) for c in board]
    known = set(mine + shared)
    remaining = [c for c in DECK if c not in known]
    need_board = 5 - len(shared)
    draw = 2 * opponents + need_board
    deadline = time.monotonic() + budget_s
    board_score = evaluate7(shared) if len(shared) >= 5 else (max_pair_category(shared),)
    won, sims = 0.0, 0
    while sims < max_sims and time.monotonic() < deadline:
        dealt = rng.sample(remaining, draw)
        if strong_range and len(shared) >= 3 and not all(
                improves_board(dealt[need_board + 2 * i:need_board + 2 * i + 2], shared, board_score)
                for i in range(opponents)):
            continue  # rejected deal: does not count as a simulation
        if range_level and len(shared) >= 3:
            bettor = dealt[need_board:need_board + 2]
            check = improves_board if range_level >= 2 else made_hand
            if not check(bettor, shared, board_score):
                continue
        full_board = shared + dealt[:need_board]
        ours = evaluate7(mine + full_board)
        best_other = max(evaluate7(dealt[need_board + 2 * i:need_board + 2 * i + 2] + full_board)
                         for i in range(opponents))
        if ours > best_other:
            won += 1
        elif ours == best_other:
            won += 0.5
        sims += 1
    return (won / sims if sims else 0.0), sims
