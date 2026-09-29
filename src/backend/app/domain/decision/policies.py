import math
import re
from collections import Counter

from app.domain.geo.models import Point
from app.domain.places.models import Place
from app.domain.preferences.models import Preferences

WEIGHTS = dict(
    preference_match=0.28,
    walking_cost=0.22,
    budget_match=0.18,
    rating_quality=0.14,
    availability_confidence=0.06,
    novelty=0.05,
    data_completeness=0.07,
)


def distance(a: Point, b: Point) -> int:
    lat1, lat2 = math.radians(a.latitude), math.radians(b.latitude)
    dlat, dlon = lat2 - lat1, math.radians(b.longitude - a.longitude)
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return round(6371000 * 2 * math.asin(min(1, math.sqrt(h))))


def eligible(
    places: list[Place], pref: Preferences, excluded: list[str], routes: bool = False
) -> tuple[list[Place], dict[str, int]]:
    kept: list[Place] = []
    counts: Counter[str] = Counter()
    for p in places:
        reason = None
        if p.id in excluded:
            reason = "excludedPlace"
        elif p.straight_line_distance_meters > pref.radius_meters:
            reason = "radius"
        elif set(p.cuisine_types) & set(pref.excluded_cuisines):
            reason = "cuisine"
        elif pref.open_now_preferred and p.business_status == "closed":
            reason = "closed"
        elif (
            p.average_cost is not None
            and pref.budget_per_person.max is not None
            and p.average_cost > pref.budget_per_person.max
        ):
            reason = "budget"
        elif routes and (
            p.route is None or p.route.duration_seconds > pref.max_walking_minutes * 60
        ):
            reason = "walkingLimit"
        if reason:
            counts[reason] += 1
        else:
            warnings = []
            if p.average_cost is None:
                warnings.append("人均暂无数据，无法确认符合预算")
            if p.business_status == "unknown":
                warnings.append("营业状态未知，出发前请确认")
            if p.rating is None:
                warnings.append("评分暂无数据")
            kept.append(p.model_copy(update={"warnings": warnings}))
    return kept, dict(counts)


def score_places(
    places: list[Place],
    pref: Preferences,
    action: str = "",
    recent: list[str] | None = None,
    old_cuisines: list[str] | None = None,
) -> list[Place]:
    weights = WEIGHTS.copy()
    boost = {
        "closer": "walking_cost",
        "cheaper": "budget_match",
        "higherRated": "rating_quality",
    }.get(action)
    if boost:
        weights[boost] *= 2
    norm = sum(weights.values())
    result = []
    for p in places:
        budget = pref.budget_per_person
        match = (
            100.0
            if not pref.preferred_cuisines or set(p.cuisine_types) & set(pref.preferred_cuisines)
            else 30.0
        )
        if action == "differentCuisine" and set(p.cuisine_types) & set(old_cuisines or []):
            match *= 0.3
        budget_score = 40.0
        if p.average_cost is not None:
            budget_score = 100.0
            if budget.min and p.average_cost < budget.min:
                budget_score = max(50, 100 * float(p.average_cost / budget.min))
            if action == "cheaper":
                ceiling = float(budget.max or 100)
                budget_score = max(0, 100 * (1 - float(p.average_cost) / max(ceiling, 1)))
        walking = (
            max(0, 100 * (1 - p.route.duration_seconds / (pref.max_walking_minutes * 60)))
            if p.route
            else max(0, 100 * (1 - p.straight_line_distance_meters / pref.radius_meters))
        )
        sub = dict(
            preference_match=float(match),
            walking_cost=walking,
            budget_match=budget_score,
            rating_quality=p.rating * 20 if p.rating is not None else 40,
            availability_confidence={"open": 100, "unknown": 40, "closed": 0}[p.business_status],
            novelty=30 if p.id in (recent or []) else 100,
            data_completeness=100
            * sum(
                [
                    p.rating is not None,
                    p.average_cost is not None,
                    p.business_status != "unknown",
                    p.route is not None,
                ]
            )
            / 4,
        )
        total = round(sum(sub[k] * weights[k] / norm for k in sub), 2)
        result.append(
            p.model_copy(update={"score": total, "score_breakdown": {**sub, "total": total}})
        )
    return sorted(
        result,
        key=lambda p: (
            -p.score,
            p.route is None,
            -p.score_breakdown["data_completeness"],
            -(p.rating or 0),
            p.route.duration_seconds if p.route else 999999,
            p.id,
        ),
    )


def diverse(places: list[Place]) -> list[Place]:
    selected: list[Place] = []
    remaining = places.copy()
    while remaining and len(selected) < 3:

        def priority(p: Place) -> float:
            brand = re.split(r"[（(]", p.name)[0]
            same_brand = any(re.split(r"[（(]", s.name)[0] == brand for s in selected)
            same_cuisine = any(set(p.cuisine_types) & set(s.cuisine_types) for s in selected)
            return places.index(p) + 8 * same_brand + 3 * same_cuisine

        chosen = min(remaining, key=priority)
        selected.append(chosen)
        remaining.remove(chosen)
    return selected
