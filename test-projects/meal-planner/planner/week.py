"""One recipe per day for a week."""
import datetime as dt

DAYS = 7


def plan_week(recipes, start=None):
    start = start or dt.date.today()
    return [(start + dt.timedelta(days=d), recipes[d % len(recipes)]) for d in range(DAYS)]
