"""Build an order from a shopping list."""
from .catalog import CATALOG


def build_order(shopping_list, catalog=CATALOG):
    """shopping_list: [(qty, unit, item)] -> [(item, pack, count)]"""
    order = []
    for qty, unit, item in shopping_list:
        packs = catalog.get(item)
        if not packs:
            continue
        size, punit, price = packs[0]
        order.append((item, (size, punit, price), max(1, round(qty / size))))
    return order


def total(order):
    return sum(price * count for _, (_, _, price), count in order)
