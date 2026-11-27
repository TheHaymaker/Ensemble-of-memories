from _base import *
from recipe_core.units import normalize
from recipe_core.parse import parse_line
@check("task:glasses -> glass")
def _(): return normalize("glasses") == "glass"
@check("task:cups -> cup")
def _(): return normalize("cups") == "cup"
@check("task:tbsps/teaspoons still normalize")
def _(): return normalize("teaspoons") == "tsp"
@check("task:'2 cups flour' still parses")
def _():
    i = parse_line("2 cups flour"); return i.unit == "cup" and i.name == "flour" and float(i.qty) == 2
@check("mem:(control) kitchen fractions intact (1/3 cup)")
def _():
    from recipe_core.scale import format_qty
    return format_qty(1/3, "cup").strip() == "1/3"
done()
