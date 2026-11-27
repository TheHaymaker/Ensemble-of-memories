from _base import *
from recipe_core import units

@check("task:to_grams flour is 'N g'")
def _(): return re.fullmatch(r"\d+(\.\d+)? g", units.to_grams(1, "cup", "flour").strip())
@check("task:to_grams flour plausible (100-150 g/cup)")
def _(): return 100 <= float(units.to_grams(1, "cup", "flour").split()[0]) <= 150
@check("task:to_grams accepts plural units")
def _(): return re.fullmatch(r"\d+(\.\d+)? g", units.to_grams(2, "cups", "sugar").strip())
@check("task:unknown ingredient raises")
def _(): return raises(units.to_grams, 1, "cup", "unobtainium") is not None
@check("mem:whole grams (1 tbsp butter)")
def _(): return re.fullmatch(r"\d+ g", units.to_grams(1, "tbsp", "butter").strip())
@check("mem:whole grams (1/3 cup sugar)")
def _(): return re.fullmatch(r"\d+ g", units.to_grams(1/3, "cup", "sugar").strip())
@check("mem:whole grams, small amount (1 tsp sugar)")
def _(): return re.fullmatch(r"\d+ g", units.to_grams(1, "tsp", "sugar").strip())
@check("mem:unknown ingredient raises RecipeError")
def _():
    import recipe_core
    E = getattr(recipe_core, "RecipeError")
    return isinstance(raises(units.to_grams, 1, "cup", "unobtainium"), E)
done()
