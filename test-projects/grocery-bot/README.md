# grocery-bot

Turns a shopping list into a store order: picks package sizes and prices the basket.

- `grocery/catalog.py`: a tiny product catalog (pack size, unit, price)
- `grocery/order.py`: `build_order(shopping_list, catalog)` and `total(order)`

Run the tests with `python3 -m unittest discover -s tests`.
