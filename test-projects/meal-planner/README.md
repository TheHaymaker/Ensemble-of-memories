# meal-planner

Plans a week of meals and builds the shopping list. It carries a copy of recipe-core's unit code
in `planner/units.py` (vendored, so it has the same quirks until someone fixes them here).

- `planner/week.py`: `plan_week(recipes, start)` gives one recipe per day
- `planner/shopping.py`: `shopping_list(plan)` adds up ingredients across the week

Run the tests with `python3 -m unittest discover -s tests`.
