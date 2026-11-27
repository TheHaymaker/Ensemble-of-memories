import sys, os, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from trail.log import Hike

PTS = [(46.0, 7.0, 1000, 0), (46.01, 7.0, 1050, 900), (46.02, 7.0, 1040, 1800)]


class Log(unittest.TestCase):
    def test_distance(self):
        self.assertAlmostEqual(Hike(PTS).distance_km(), 2.22, places=1)

    def test_gain(self):
        self.assertEqual(Hike(PTS).elevation_gain_m(), 50)


if __name__ == "__main__":
    unittest.main()
