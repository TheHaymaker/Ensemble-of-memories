"""Pantry items and expiry."""
import datetime as dt
from dataclasses import dataclass


@dataclass
class Item:
    name: str
    qty: float
    unit: str | None
    expires: dt.datetime


def expiring(items, days=3, now=None):
    now = now or dt.datetime.utcnow()
    return [i for i in items if (i.expires - now).days <= days]
