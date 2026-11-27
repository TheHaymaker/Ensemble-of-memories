import sys, os, unittest, datetime as dt
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from planner.week import plan_week
from planner.shopping import shopping_list

PANCAKES = {"name": "pancakes", "ingredients": [(1, "cup", "milk"), (2, None, "eggs")]}
SOUP = {"name": "soup", "ingredients": [(500, "ml", "stock"), (1, None, "onion")]}


class Planner(unittest.TestCase):
    def test_seven_days(self):
        self.assertEqual(len(plan_week([PANCAKES, SOUP], dt.date(2026, 1, 5))), 7)

    def test_same_unit_adds(self):
        lst = shopping_list([(None, PANCAKES), (None, PANCAKES)])
        self.assertIn((2, "cup", "milk"), lst)


if __name__ == "__main__":
    unittest.main()
