"""
CHAMPION Fairway (886) vs Greens Grade (892): same professional turf nutrition category,
two intensity tiers. The engine surfaces both together with readable tags (no score splitting).
"""

from __future__ import annotations

from .goal_layer import effective_goal_weights
from .types import ScoredProduct, UserInput

CHAMPION_FAIRWAY_ID = "886"
CHAMPION_GREENS_ID = "892"

# Pair block only when Champion SKUs are competitive vs the catalog — not on every lawn_context hit.
# Problems / symptom mode: allow mid-pack rank (turf fertilisers often trail bundles on raw score).
CHAMPION_RELATIVE_TO_TOP = 0.54
CHAMPION_MAX_RANK = 28  # 0-based; best Champion within first 29 products
# Goals + lawn UI but no goal tickboxes yet — stricter so the pair is not “always on”.
CHAMPION_MAX_RANK_GOALS_LAWN_NO_WEIGHTS = 14
CHAMPION_GOAL_MATCH_MIN_FRAC_OF_MAX = 0.76  # goals+lawn+effective weights: vs catalog max goal_match


def lawn_context(user: UserInput) -> bool:
    if user.use_case in ("garden_beds", "pots", "indoor_plants") or user.goal_vertical == "garden":
        return False
    if user.use_case == "lawn" or user.goal_vertical == "lawn":
        return True
    if float(user.problems.get("patchy_lawn", 0.0)) > 0:
        return True
    return False


def champion_turf_pair_warranted(user: UserInput, scored_sorted: list[ScoredProduct]) -> bool:
    """
    True when CHAMPION Fairway / Greens deserve the educational pair in the response.

    - Goals + lawn + effective goal weights: weighted CSV `goal_match` must be near the catalog
      best for the user's selections (not merely “lawn scenario”).
    - Otherwise (problems mode, or goals without usable weights): total score vs leader and rank.
    """
    if not lawn_context(user) or not scored_sorted:
        return False
    by_id = {sp.product.id: sp for sp in scored_sorted}
    s886 = by_id.get(CHAMPION_FAIRWAY_ID)
    s892 = by_id.get(CHAMPION_GREENS_ID)
    if s886 is None or s892 is None:
        return False

    best_sp = s886 if s886.score >= s892.score else s892
    best_score = best_sp.score
    top_score = scored_sorted[0].score
    rank = next(i for i, sp in enumerate(scored_sorted) if sp.product.id == best_sp.product.id)

    egw = effective_goal_weights(user)
    if user.recommendation_mode == "goals" and user.goal_vertical == "lawn" and egw:
        gms = [float(sp.breakdown.get("goal_match", 0.0)) for sp in scored_sorted]
        max_gm = max(gms) if gms else 0.0
        gm_ch = max(
            float(s886.breakdown.get("goal_match", 0.0)),
            float(s892.breakdown.get("goal_match", 0.0)),
        )
        if max_gm <= 0:
            return False
        return gm_ch >= CHAMPION_GOAL_MATCH_MIN_FRAC_OF_MAX * max_gm

    goals_lawn_no_weights = (
        user.recommendation_mode == "goals"
        and user.goal_vertical == "lawn"
        and not egw
    )
    # No ratio shortcut here — otherwise mid-ranked Champion still passes via score ratio alone.
    if goals_lawn_no_weights:
        return rank <= CHAMPION_MAX_RANK_GOALS_LAWN_NO_WEIGHTS

    if top_score > 0 and best_score >= CHAMPION_RELATIVE_TO_TOP * top_score:
        return True
    if rank <= CHAMPION_MAX_RANK:
        return True
    return False


# Copy for API / UI (single source of truth for tags)
FAIRWAY_TAG = "general_lawn_sports"
FAIRWAY_LABEL = "General lawn, council & sports turf"
FAIRWAY_BLURB = (
    "Best default for most home lawns, verges, parks, sports ovals, and medium‑maintenance turf "
    "where you want strong colour, density, and resilience without ultra‑low mowing or elite surface precision."
)

GREENS_TAG = "elite_fine_turf"
GREENS_LABEL = "Elite fine turf & precision surfaces"
GREENS_BLURB = (
    "For very low cut, cylinder‑mown, or high‑input programs where surface quality is critical — "
    "e.g. golf greens, bowling greens, elite fairway‑style management. Higher intensity than typical backyard lawns."
)
