"""Words specialists use for the same thing, places families name instead of the country, and topics.

Used by search to expand a question and to tag notes. Small on purpose: every line is a real way of asking, not a
fix for one test question. Extend it from the gap list (questions the brain could not answer)."""
from __future__ import annotations

import re

# destination aliases: places and spellings families use (soft boost, never a filter)
ALIASES = {
    "indonesia": ["bali", "lombok", "java", "gili", "ubud", "indonesie", "indonesië"],
    "thailand": ["tailand", "phuket", "krabi", "koh samui", "bangkok", "chiang mai"],
    "vietnam": ["saigon", "hanoi", "halong", "hoi an", "viëtnam"],
    "japan": ["tokio", "tokyo", "kyoto", "osaka"],
    "sri-lanka": ["ceylon", "colombo", "kandy"],
    "south-africa": ["zuid afrika", "zuid-afrika", "kaapstad", "kaap", "kruger", "south africa"],
    "tanzania": ["zanzibar", "serengeti", "kilimanjaro", "ngorongoro"],
    "costa-rica": ["costa rica", "arenal", "tortuguero"],
}

# topics: a note and a question about the same topic get a small boost
TOPICS = {
    "season": r"reistijd|seizoen|droog|regen|moesson|weer\b|klimaat|maand|wanneer|best time|season|rainy|dry",
    "lodging": r"hotel|slapen|overnacht|verblijf|accommodat|lodge|resort|ryokan|guesthouse|bungalow|camp\b",
    "entry": r"inreis|visum|visa\b|paspoort|papieren|documenten|reisdocument|entry|passport",
    "changes": r"wijzig|omboek|verzet|verschuiv|annuleer|annulering|cancel|change",
    "payment": r"betaal|betaling|aanbetaling|restbedrag|restant|vooraf|deposit|payment",
    "insurance": r"verzeker|insurance",
    "partner": r"partner|regelt|transfers?|gids|excursie|vaste partij|agent",
    "kids_small": r"baby|peuter|kleuter|jonge kinderen|kleine kinderen|toddler",
    "teens": r"tiener|puber|teen|tieners",
    "kids": r"kind|kids|gezin|familie|family|children",
    "nature": r"jungle|regenwoud|natuur|wildlife|dieren|safari|nationaal park|grot",
}

# words that mean the same thing for search (added to the question, never replacing it)
SYNONYMS = {
    "omboeken": "wijzigen wijziging", "verzetten": "wijzigen", "kids": "kinderen", "slapen": "hotels",
    "overnachten": "hotels", "droog": "reistijd", "restbedrag": "restant betaling", "papieren": "inreisregels",
    "visum": "inreisregels", "documenten": "inreisregels", "vaste partij": "lokale partner", "jungle": "regenwoud natuur",
}


def destination_in(text: str) -> str | None:
    from ..synth.world import DESTINATIONS
    t = text.lower()
    for key, d in DESTINATIONS.items():
        if d["nl"].lower() in t or d["name"].lower() in t or key.replace("-", " ") in t:
            return key
    for key, words in ALIASES.items():
        if any(re.search(rf"\b{re.escape(w)}\b", t) for w in words):
            return key
    return None


def topics(text: str) -> set[str]:
    t = text.lower()
    return {k for k, rx in TOPICS.items() if re.search(rx, t)}


def expand(query: str) -> str:
    t = query.lower()
    extra = [v for k, v in SYNONYMS.items() if k in t]
    return query + (" " + " ".join(extra) if extra else "")
