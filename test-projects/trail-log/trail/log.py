"""Hikes from GPS points (lat, lon, elevation_m, seconds)."""
import math

R = 6371.0


def _hav(a, b):
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


class Hike:
    def __init__(self, points):
        self.points = points

    def distance_km(self):
        return sum(_hav(a, b) for a, b in zip(self.points, self.points[1:]))

    def distance_miles(self):
        return self.distance_km() * 0.621371

    def elevation_gain_m(self):
        return sum(max(0, b[2] - a[2]) for a, b in zip(self.points, self.points[1:]))

    def pace(self):
        """minutes per km as 'm:ss'"""
        secs = self.points[-1][3] - self.points[0][3]
        per_km = secs / 60 / self.distance_km()
        return f"{int(per_km)}:{int((per_km % 1) * 60)}"
