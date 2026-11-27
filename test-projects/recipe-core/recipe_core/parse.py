"""Parse one ingredient line, e.g. "1 1/2 cups flour"."""
from dataclasses import dataclass

from .units import dimension, normalize


@dataclass
class Ingredient:
    qty: float
    unit: str | None
    name: str


def _number(tok):
    if "/" in tok:
        a, b = tok.split("/")
        return int(a) / int(b)
    return float(tok)


def parse_line(line):
    toks = line.split()
    qty, i = 0.0, 0
    while i < len(toks):
        try:
            qty += _number(toks[i])
            i += 1
        except ValueError:
            break
    unit = None
    if i < len(toks) and dimension(toks[i]):
        unit = normalize(toks[i])
        i += 1
    return Ingredient(qty or 1.0, unit, " ".join(toks[i:]))
