"""The four guardrail layers from the architecture.

In       detect_injection(): mail is data, never instructions; suspicious mail goes to a person, no draft.
         Stand-in rules here; with AZURE_CONTENT_SAFETY_ENDPOINT/KEY set, Azure Prompt Shields is asked too.
Privacy  Pseudonymiser: names, mail addresses, phone numbers, IBANs and the like are replaced by tags before
         any model call and put back afterwards, so the model never sees who the family is.
Tools    least privilege per agent, enforced in the tool server (identity.AGENTS).
Out      check_output(): prices only from the calculation, no health advice, no unknown hotels, no dashes.
"""
from __future__ import annotations

import os
import re
from typing import Any

from .anonymise import Anonymiser

# --- In: prompt injection ------------------------------------------------------------------------

INJECTION_PATTERNS = [
    (r"\b(ignore|disregard|forget)\b.{0,30}\b(previous|above|all|earlier|prior)\b.{0,20}\b(instructions?|rules|prompts?)", "override"),
    (r"\b(negeer|vergeet)\b.{0,30}\b(vorige|bovenstaande|alle|eerdere)\b.{0,20}\b(instructies|regels|opdrachten)", "override"),
    (r"\b(you are now|from now on you are|act as|pretend to be|je bent nu|doe alsof je)\b", "role"),
    (r"\b(system prompt|systeemprompt|developer mode|jailbreak|dan mode)\b", "system"),
    (r"(^|\n)\s*(system|assistant|developer)\s*:", "role_tag"),
    (r"\b(give|geef|apply|bereken)\b.{0,40}\b(\d{1,3}\s?%|procent)\b.{0,20}\b(discount|korting)", "price_manipulation"),
    (r"\b(korting|discount)\b.{0,40}\b(toepassen|apply|geven|without asking|zonder overleg)", "price_manipulation"),
    (r"\b(send|forward|stuur|mail|e-?mail)\b.{0,60}\b(all|alle|every|the full|het hele)\b.{0,40}(customers?|klant\w*|dossiers?|data|\w*gegevens|list|lijst)", "exfiltration"),
    (r"\b(password|wachtwoord|api[\s_-]?key|token|credentials|inloggegevens)\b", "secrets"),
    (r"<\s*(script|iframe)|<!--|\u200b|\u200c|\u200d|\u2060", "hidden_text"),
    (r"\b(BEGIN|END)\s+(INSTRUCTIONS|PROMPT|SYSTEM)\b", "instruction_block"),
    (r"[A-Za-z0-9+/]{120,}={0,2}", "encoded_blob"),
    (r"\b(book|boek|confirm|bevestig)\b.{0,40}\b(without|zonder)\b.{0,30}\b(approval|goedkeuring|specialist|check)", "bypass_human"),
    # broader families of the same attacks (written for intent, not for one sentence)
    (r"\b(ignore|disregard|forget|override|negeer|vergeet)\b.{0,40}\b(what you were told|your (rules|instructions|guidelines|programming)|"
     r"(the|all|any|je|jouw|alle) (rules|instructions|guidelines|regels|instructies))", "override"),
    (r"\b(instructions?|message|note|opdracht|bericht)\s+(for|to|voor|aan)\s+(the\s+|de\s+)?(ai|assistant|bot|model|llm|agent|assistent)\b", "addressing_ai"),
    (r"\b(hey|hi|dear|attention|beste|hallo)\s+(ai|assistant|bot|chatgpt|claude|gpt|assistent)\b|<!--\s*ai\b", "addressing_ai"),
    (r"\b(print|show|reveal|repeat|output|toon|laat zien|herhaal)\b.{0,30}\b(hidden|secret|system|initial|original|verborgen|geheime)\s+"
     r"(instructions|prompt|rules|instructies|regels)", "prompt_leak"),
    (r"\b(this is your|i am (the|your)|as (the|your)|ik ben (de|je|jouw))\s+(developer|administrator|admin|system administrator|operator|"
     r"beheerder|ontwikkelaar)\b", "false_authority"),
    (r"\b(maintenance|debug|admin|god|onderhouds)\s?(mode|modus)\b|\bskip\s+(all\s+)?(checks|approval|verification)\b", "false_authority"),
    (r"\b(then|and|en)\s+(do|doe)\s+(exactly\s+|precies\s+)?(what it says|wat er staat)", "indirect"),
    (r"\bbelow cost\b|\bonder (de )?kostprijs\b", "price_manipulation"),
    (r"\b(reduction|discount|korting|price|prijs)\b.{0,60}\b(no need to check|without (checking|asking)|(manager|director|boss) (has )?agreed|"
     r"already agreed|zonder (te )?(controleren|overleg)|al afgesproken)", "price_manipulation"),
    (r"\b(include|send|list|give|share|tell|stuur|geef|noem)\b.{0,40}\b(other|all|andere|alle)\s+(bookings|customers|families|guests|clients|"
     r"klanten|boekingen|families|gezinnen|reizigers)\b", "exfiltration"),
    (r"\b(margin|marge|markup|opslag)\b.{0,30}\b(you add|you put|jullie (rekenen|zetten)|on (the )?hotels|op (de )?hotels)", "exfiltration"),
]


def detect_injection(text: str) -> dict:
    reasons = sorted({label for rx, label in INJECTION_PATTERNS if re.search(rx, text, re.I | re.S)})
    result = {"flagged": bool(reasons), "reasons": reasons, "source": "rules"}
    if os.getenv("AZURE_CONTENT_SAFETY_ENDPOINT") and os.getenv("AZURE_CONTENT_SAFETY_KEY"):
        try:
            shield = prompt_shields(text)
            if shield:
                result.update(flagged=True, reasons=reasons + ["prompt_shields"], source="rules+azure")
        except Exception:  # noqa: BLE001  fail closed: if the check cannot run, a person looks
            result.update(flagged=True, reasons=reasons + ["shield_unavailable"])
    return result


def prompt_shields(text: str) -> bool:  # pragma: no cover - needs Azure
    import httpx
    url = os.environ["AZURE_CONTENT_SAFETY_ENDPOINT"].rstrip("/") + "/contentsafety/text:shieldPrompt?api-version=2024-09-01"
    r = httpx.post(url, headers={"Ocp-Apim-Subscription-Key": os.environ["AZURE_CONTENT_SAFETY_KEY"]},
                   json={"userPrompt": "", "documents": [text[:10000]]}, timeout=10)
    r.raise_for_status()
    return any(d.get("attackDetected") for d in r.json().get("documentsAnalysis", []))


# --- Privacy: pseudonymise before the model, restore after ---------------------------------------

PARTICLES = {"van", "de", "der", "den", "ter", "ten", "het", "la", "le", "da", "di", "von", "zu"}
NAME_KEYS = {"name", "surname", "contact_name", "first", "family_name", "first_name", "first_names", "traveller_names"}
NAME_WITH_AGE = re.compile(r"\b([A-Z][a-zé'-]{1,20})\s?(?:\(\d{1,2}\)|van \d{1,2}\b|is \d{1,2}\b|\d{1,2} jaar)")


class PrivacyError(RuntimeError):
    """A known or likely name is still in the text that would go to the model: the call is refused."""
SENSITIVE = {"EMAIL", "TELEFOON", "IBAN", "BSN", "DOCUMENT", "GEBOORTEDATUM", "ADRES", "POSTCODE"}


class Pseudonymiser:
    def __init__(self) -> None:
        self.forward: dict[str, str] = {}
        self.back: dict[str, str] = {}

    def _tag(self, kind: str, value: str) -> str:
        if value not in self.forward:
            tag = f"[{kind}_{sum(1 for t in self.back if t.startswith('[' + kind)) + 1}]"
            self.forward[value] = tag
            self.back[tag] = value
        return self.forward[value]

    def _collect(self, obj: Any, key: str | None = None) -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                self._collect(v, k)
        elif isinstance(obj, list):
            for v in obj:
                self._collect(v, key)
        elif isinstance(obj, str):
            if key in NAME_KEYS:
                for part in re.findall(r"[A-Za-zÀ-ÿ'-]+", obj):
                    if len(part) > 1 and part.lower() not in PARTICLES | {"gezin"} | _company_words():
                        self._tag("NAAM", part)
            free_text = "\n" in obj or len(obj) > 80  # names are only searched in mail-like text, not in field values
            if free_text:
                from .anonymise import _travel_words
                from .names import FIRST_NAMES
                travel = _travel_words()
                for w in re.findall(r"\b[A-Z][a-zé'-]{1,20}\b", obj):
                    if w.lower() in FIRST_NAMES and w.lower() not in travel:
                        self._tag("NAAM", w)
                for m in NAME_WITH_AGE.finditer(obj):
                    if m.group(1).lower() not in travel and m.group(1).lower() not in PARTICLES | {"Kinderen", "Zoon", "Dochter"}:
                        self._tag("NAAM", m.group(1))
            for f in Anonymiser().detect(obj):
                if f.kind in SENSITIVE:
                    self._tag(f.kind, f.value)
                elif f.kind == "NAAM" and free_text:
                    for part in f.value.split():
                        if len(part) > 1 and part.lower() not in PARTICLES:
                            self._tag("NAAM", part)

    def _apply(self, obj: Any, table: dict[str, str]) -> Any:
        if isinstance(obj, dict):
            return {k: self._apply(v, table) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._apply(v, table) for v in obj]
        if isinstance(obj, str) and table:
            keys = sorted(table, key=len, reverse=True)
            rx = re.compile("|".join(rf"(?<![\w\[]){re.escape(k)}(?![\w\]])" if not k.startswith("[") else re.escape(k) for k in keys))
            return rx.sub(lambda m: table[m.group(0)], obj)
        return obj

    def mask(self, context: dict) -> dict:
        self._collect(context)
        masked = self._apply(context, self.forward)
        self.check(masked)
        return masked

    def check(self, masked: dict) -> None:
        """Fail closed: refuse if any name we know of, or a likely first name, is still in the text."""
        import json as _json
        from .names import FIRST_NAMES
        text = _json.dumps(masked, ensure_ascii=False)
        left = [v for v, tag in self.forward.items() if tag.startswith("[NAAM") and re.search(rf"(?<![\w\[]){re.escape(v)}(?![\w\]])", text)]
        mails = [v for k, v in _walk(masked) if isinstance(v, str) and ("\n" in v or len(v) > 80)]
        likely = [w for t in mails for w in re.findall(r"\b[A-Z][a-zé'-]{1,20}\b", t) if w.lower() in FIRST_NAMES
                  and w.lower() not in __import__("brain.anonymise", fromlist=["_travel_words"])._travel_words()]
        if left or likely:
            raise PrivacyError(f"Names would reach the model ({len(left) + len(likely)}); the call is refused")

    def unmask(self, output: Any) -> Any:
        return self._apply(output, self.back)


# --- Out: checks on every draft before it is saved -----------------------------------------------

HEALTH = re.compile(r"\b(malaria\w*|vaccin\w*|inent\w*|medicij\w*|prik\w*|antibiotica|tabletten|pillen|dosis|vaccination\w*|medication)\b", re.I)
REFERRAL = re.compile(r"\b(GGD|huisarts|reisvaccinatie|doctor|arts)\b", re.I)
EURO = re.compile(r"(?:€\s?|EUR\s?)(\d{1,3}(?:[.,]\d{3})+|\d+)|(\d{1,3}(?:[.,]\d{3})+|\d{3,})\s?(?:euro|EUR)", re.I)
DASHES = re.compile("[\u2013\u2014]")


def _amounts(text: str) -> list[int]:
    """Euro amounts in a text, rounded to the euro (see brain/money.py for how 1.240,50 and 1,240.50 are read)."""
    from .money import amounts
    return [int(round(a)) for a in amounts(text) if a >= 1]


INTERNAL = re.compile(r"\b(is|zijn) verlopen\b|\bprijs (is )?verlopen|vraag een nieuwe prijs op|price (has )?expired", re.I)


def check_output(text: str, allowed_prices: list[float] | None = None, known_hotels: set[str] | None = None,
                 route_hotels: set[str] | None = None) -> list[str]:
    problems = []
    allowed = {int(round(p)) for p in (allowed_prices or [])}
    for a in _amounts(text):
        if allowed and all(abs(a - p) > 1 for p in allowed):
            problems.append(f"Price {a} euro is not from the calculation")
    if HEALTH.search(text) and not REFERRAL.search(text):
        problems.append("Contains health or medication advice without a referral to the GGD or a doctor")
    for h in (known_hotels or set()) - (route_hotels or set()):
        if h in text:
            problems.append(f"Mentions {h}, which is not in this offer")
    if DASHES.search(text):
        problems.append("Contains em or en dashes")
    if INTERNAL.search(text):  # the price check's notes are for the specialist, never for the family
        problems.append("Tells the family a price has expired: say 'nog niet bevestigd' instead")
    seen = set()
    for line in (x.strip() for x in text.splitlines()):
        if len(line) > 30 and line in seen:  # a model repeating a stop (Gemma 31B wrote Halong Bay twice)
            problems.append(f"A line is repeated: {line[:60]}")
            break
        seen.add(line)
    return problems


def fix_dashes(text: str) -> str:
    return DASHES.sub(",", text)


def _walk(obj, key=None):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from _walk(v, k)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk(v, key)
    else:
        yield key, obj


def _company_words() -> set[str]:
    """The company's own name is never a family name to mask."""
    from .tenant import tenant
    return set(tenant().name_words)
