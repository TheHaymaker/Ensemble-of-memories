import sys, os, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from grocery.order import build_order, total


class Order(unittest.TestCase):
    def test_one_pack(self):
        o = build_order([(1, "l", "milk")])
        self.assertEqual(o[0][2], 1)

    def test_total(self):
        self.assertAlmostEqual(total(build_order([(1, "l", "milk")])), 1.19)


if __name__ == "__main__":
    unittest.main()
