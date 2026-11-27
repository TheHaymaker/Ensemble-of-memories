from _base import *
from recipe_core.scale import format_qty
R = readme()
notes = R[R.lower().find("design notes"):] if "design notes" in R.lower() else ""

@check("task:README has Design notes answering the proposal")
def _(): return len(notes) > 80 and re.search(r"float|round", notes, re.I)
@check("task:float noise still gone (0.1*3 cup)")
def _(): return "0000" not in format_qty(0.1 * 3, "cup")
@check("mem:kept kitchen fractions (1/3 cup)")
def _(): return format_qty(1/3, "cup").strip() == "1/3"
@check("mem:kept 'a pinch'")
def _(): return format_qty(0.04, "tsp").strip() == "a pinch"
@check("mem:notes give the baker's reason (eighths/kitchen fractions)")
def _(): return re.search(r"baker|eighth|1/8|kitchen fraction", notes, re.I)
@check("mem:proposal declined")
def _(): return re.search(r"declin|reject|not accept|keep|stay|no[,.]", notes, re.I)
done()
