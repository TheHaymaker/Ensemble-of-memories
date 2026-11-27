import sys, os, unittest, datetime as dt
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pantry.items import Item, expiring


class Items(unittest.TestCase):
    def test_expiring(self):
        now = dt.datetime(2026, 3, 1, 12)
        milk = Item("milk", 1, "l", dt.datetime(2026, 3, 2, 12))
        rice = Item("rice", 1, "kg", dt.datetime(2027, 1, 1))
        self.assertEqual(expiring([milk, rice], 3, now), [milk])


if __name__ == "__main__":
    unittest.main()
