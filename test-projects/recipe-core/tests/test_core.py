import sys, os, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from recipe_core.parse import parse_line
from recipe_core.scale import scale
from recipe_core.units import convert


class Core(unittest.TestCase):
    def test_parse_mixed_number(self):
        i = parse_line("1 1/2 cups flour")
        self.assertEqual((i.qty, i.unit, i.name), (1.5, "cup", "flour"))

    def test_parse_no_unit(self):
        self.assertEqual(parse_line("2 eggs").unit, None)

    def test_convert_volume(self):
        self.assertAlmostEqual(convert(1, "tbsp", "tsp"), 3.0, places=1)

    def test_scale(self):
        self.assertAlmostEqual(scale([parse_line("1 cup milk")], 2)[0].qty, 2.0)


if __name__ == "__main__":
    unittest.main()
