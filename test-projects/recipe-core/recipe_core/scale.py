"""Scale a recipe and format quantities for people."""
from .parse import Ingredient


def scale(ingredients, factor):
    return [Ingredient(i.qty * factor, i.unit, i.name) for i in ingredients]


def format_qty(qty):
    return str(qty)
