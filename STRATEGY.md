# Strategy overview

This is the authoritative description of how the bot decides. The code in `player.py`
implements exactly what is written here; when in doubt, this document wins.

## Design principles

- **Low variance.** We are playing for a podium finish across many short games, so we
  avoid big coin-flip pots and prefer to fold marginal spots. Survival ranks above
  stealing thin edges.
- **No per-opponent modelling in the hot path.** We treat every opponent identically.
  Opponent-specific branches exist in the source but are gated behind a sample count we
  almost never reach inside a single 90–130 hand game, so in practice they do not fire.
  Tuning against our name is not worth it.
- **Slow to adapt.** The showdown profiler needs **20+ observed showdowns** against a
  given player before it changes any threshold. Within one game it effectively never
  flips, so early-game reads do not move us.

## Preflop

- Tight-aggressive. We open only the top tiers: pairs 66+, A-T+, K-J+, Q-J, suited
  broadways. Everything else folds, including from the button.
- Open size is a flat 3 big blinds. We do not size-tell.
- **Facing a 3-bet or any re-raise, we continue only with AA/KK/QQ/AK.** Everything else
  folds, every time, regardless of price or position.
- Short-stacked (≤ 15 bb) we push/fold a standard Nash-ish chart. We shove rarely
  (target shove frequency 8–12%) to keep our all-ins credible.

## Postflop

- We estimate equity, then compare it to pot odds. Call when equity beats the price,
  fold otherwise.
- **We assume every bet is a value bet.** A bettor is credited with top pair or better,
  so we need roughly **60% equity to continue against any bet, and two pair or better to
  continue against a bet of 0.6 pot or larger.** We fold one pair to big bets as a rule.
- **We do not bluff and we do not stab.** If it is checked to us without a strong made
  hand, we check behind. We only put chips in with genuine value.
- We never float and never raise as a semi-bluff.

## What we are bad at (known, accepted)

- We over-fold to aggression. A bot that bets big and often will take a lot of small pots
  from us uncontested; we accept that as the price of low variance.
- We do not punish bluffers inside a single game, because the profiler adapts too slowly.
