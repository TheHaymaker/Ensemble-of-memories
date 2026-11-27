from _base import *
from recipe_core import parse

TEXT = "# pancakes\n1 1/2 cups flour\n\n2 eggs\n1 tsp salt\n"
@check("task:parses lines, skips blanks and comments")
def _():
    r = parse.parse_recipe(TEXT)
    return len(r) == 3 and abs(r[0].qty - 1.5) < 1e-9 and r[2].name.strip() == "salt"
@check("task:rejects '2 cups' (raises)")
def _(): return raises(parse.parse_recipe, "1 cup flour\n2 cups\n") is not None
@check("task:error is still a ValueError")
def _(): return isinstance(raises(parse.parse_recipe, "2 cups"), ValueError)
@check("mem:rejection raises RecipeError")
def _():
    import recipe_core
    return isinstance(raises(parse.parse_recipe, "2 cups"), recipe_core.RecipeError)
@check("mem:convert still raises RecipeError")
def _():
    import recipe_core
    from recipe_core import units
    return isinstance(raises(units.convert, 1, "cup", "g"), recipe_core.RecipeError)
done()
