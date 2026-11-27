"""Unit conversion within one dimension (volume or mass)."""

VOLUME_ML = {"tsp": 4.93, "tbsp": 14.79, "cup": 236.6, "ml": 1.0, "l": 1000.0}
MASS_G = {"g": 1.0, "kg": 1000.0, "oz": 28.35, "lb": 453.6}

ALIASES = {"teaspoon": "tsp", "tablespoon": "tbsp", "gram": "g", "kilogram": "kg",
           "ounce": "oz", "pound": "lb", "liter": "l", "litre": "l", "milliliter": "ml"}


def normalize(unit):
    unit = unit.lower().strip(".")
    if unit.endswith("s"):
        unit = unit[:-1]
    return ALIASES.get(unit, unit)


def dimension(unit):
    unit = normalize(unit)
    if unit in VOLUME_ML:
        return "volume"
    if unit in MASS_G:
        return "mass"
    return None


def convert(qty, frm, to):
    frm, to = normalize(frm), normalize(to)
    for table in (VOLUME_ML, MASS_G):
        if frm in table and to in table:
            return qty * table[frm] / table[to]
    raise ValueError(f"cannot convert {frm} to {to}")
