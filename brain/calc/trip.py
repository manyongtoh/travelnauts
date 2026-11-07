"""A trip to calculate, as a small JSON file a specialist (or the brain) fills in.

    {"title": "Thailand met kinderen",
     "party": {"adults": 2, "children": [8, 11]},
     "start": "2027-07-02",
     "stops": [{"city": "Bangkok", "hotel": "Riva Surya", "nights": 3}, ...],
     "items": [{"label": "BKK luchthaven - hotel", "on": "2027-07-02", "adult": 770, "child": 770},
               {"label": "Elephant Hills", "kind": "excursion", "adult": 1633, "child": 544, "currency": "AUD"}],
     "flights": [{"label": "KL AMS-BKK v.v.", "adult_eur": 1793, "child_eur": 1435.25, "reference": "optie"}],
     "settings": {"rate_to_eur": 0.0268, "target_margin": 0.23}}
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from .calculate import Flight, Item, Party, Settings, Stop


def _date(v):
    return date.fromisoformat(v) if v else None


def load(path: str | Path) -> dict:
    d = json.loads(Path(path).read_text())
    settings = Settings(**{k: v for k, v in (d.get("settings") or {}).items() if k in Settings.__dataclass_fields__})
    return {
        "title": d.get("title", ""),
        "party": Party(int(d["party"]["adults"]), [int(x) for x in d["party"].get("children", [])]),
        "start": _date(d["start"]),
        "stops": [Stop(x["city"], x["hotel"], int(x["nights"]), x.get("room")) for x in d["stops"]],
        "items": [Item(x["label"], _date(x.get("on")), float(x["adult"]), None if x.get("child") is None else float(x["child"]),
                       bool(x.get("per_group", False)), x.get("kind", "transfer"), x.get("currency")) for x in d.get("items", [])],
        "flights": [Flight(x["label"], float(x["adult_eur"]), None if x.get("child_eur") is None else float(x["child_eur"]),
                           x.get("reference", "")) for x in d.get("flights", [])],
        "settings": settings,
    }
