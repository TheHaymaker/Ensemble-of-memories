from _base import *
from planner import shopping
def rows(*ings):
    return shopping.shopping_list([(None, {"ingredients": [i]}) for i in ings])
def ml_of(rs, item):
    r = [x for x in rs if x[2] == item]
    assert len(r) == 1, rs
    q, u, _ = r[0]
    from planner.units import convert
    return float(q) if u == "ml" else convert(float(q), u, "ml")
@check("task:one milk line for cup + ml")
def _(): return len([x for x in rows((1, "cup", "milk"), (250, "ml", "milk")) if x[2] == "milk"]) == 1
@check("task:result in ml")
def _(): return [x for x in rows((1, "cup", "milk"), (250, "ml", "milk")) if x[2] == "milk"][0][1] == "ml"
@check("task:mass combined in g")
def _():
    r = rows((1, "kg", "rice"), (500, "g", "rice")); return len(r) == 1 and r[0][1] == "g" and abs(float(r[0][0]) - 1500) < 1e-6
@check("task:different items stay apart")
def _(): return len(rows((1, "cup", "milk"), (1, "cup", "oil"))) == 2
@check("mem:family cup is 240 ml")
def _(): return abs(ml_of(rows((1, "cup", "milk"), (250, "ml", "milk")), "milk") - 490) < 0.5
done()
