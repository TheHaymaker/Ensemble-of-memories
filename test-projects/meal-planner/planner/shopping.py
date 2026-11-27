"""Add up the ingredients of a week's plan."""
from collections import defaultdict


def shopping_list(plan):
    """plan: [(date, {"name": ..., "ingredients": [(qty, unit, item), ...]})]"""
    totals = defaultdict(float)
    for _, recipe in plan:
        for qty, unit, item in recipe["ingredients"]:
            totals[(item, unit)] += qty
    return [(qty, unit, item) for (item, unit), qty in sorted(totals.items())]
