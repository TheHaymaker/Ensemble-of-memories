from _base import *
from planner import shopping
f = shopping.format_line
@check("task:no float noise (0.7 cup oil)")
def _():
    s = f(0.1 + 0.2 + 0.4, "cup", "oil"); return not re.search(r"\d\.\d{4,}", s) and "oil" in s
@check("task:whole numbers plain (2 cup flour)")
def _(): return re.search(r"\b2\b", f(2.0, "cup", "flour")) and ".0" not in f(2.0, "cup", "flour")
@check("task:sums without noise")
def _():
    plan = [(None, {"ingredients": [(0.1, "cup", "oil")]}), (None, {"ingredients": [(0.2, "cup", "oil")]}),
            (None, {"ingredients": [(0.4, "cup", "oil")]})]
    rows = shopping.shopping_list(plan)
    return len(rows) == 1 and abs(float(rows[0][0]) - 0.7) < 1e-9 and not re.search(r"\d\.\d{6,}", f(*rows[0]))
@check("mem:family style: kitchen fraction (1/3 cup)")
def _(): return "1/3" in f(1/3, "cup", "oil")
@check("mem:family style: mixed number (1 1/2 cup)")
def _(): return "1 1/2" in f(1.5, "cup", "milk")
@check("mem:family style: 'a pinch' for tiny tsp")
def _(): return "pinch" in f(0.04, "tsp", "salt")
@check("mem:family style: whole grams (14.2 g butter)")
def _(): return re.search(r"\b14 g", f(14.2, "g", "butter")) is not None
done()
