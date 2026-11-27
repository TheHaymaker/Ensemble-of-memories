# recipe-core

A tiny library for parsing, scaling and converting recipe ingredients.

- `recipe_core/parse.py`: `parse_line("1 1/2 cups flour") -> Ingredient(1.5, "cup", "flour")`
- `recipe_core/units.py`: `convert(qty, "cup", "ml")` within volume or within mass
- `recipe_core/scale.py`: `scale(ingredients, factor)` and `format_qty(qty)`

Run the tests with `python3 -m unittest discover -s tests`.
