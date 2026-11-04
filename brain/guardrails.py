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
    (r"<\s*(script|iframe)|<!--|​|‌|‍|⁠", "hidden_text"),
    (r"\b(BEGIN|END)\s+(INSTRUCTIONS|PROMPT|SYSTEM)\b", "instruction_block"),
    (r"[A-Za-z0-9+/]{120,}={0,2}", "encoded_blob"),
    (r"\b(book|boek|confirm|bevestig)\b.{0,40}\b(without|zonder)\b.{0,30}\b(approval|goedkeuring|specialist|check)", "bypass_human"),
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
NAME_KEYS = {"name", "surname", "contact_name", "first", "family_name", "first_name"}
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
                    if len(part) > 1 and part.lower() not in PARTICLES | {"travelnauts", "gezin"}:
                        self._tag("NAAM", part)
            free_text = "\n" in obj or len(obj) > 80  # names are only searched in mail-like text, not in field values
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
        return self._apply(context, self.forward)

    def unmask(self, output: Any) -> Any:
        return self._apply(output, self.back)


# --- Out: checks on every draft before it is saved -----------------------------------------------

HEALTH = re.compile(r"\b(malaria\w*|vaccin\w*|inent\w*|medicij\w*|prik\w*|antibiotica|tabletten|pillen|dosis|vaccination\w*|medication)\b", re.I)
REFERRAL = re.compile(r"\b(GGD|huisarts|reisvaccinatie|doctor|arts)\b", re.I)
EURO = re.compile(r"(?:€\s?|EUR\s?)(\d{1,3}(?:[.,]\d{3})+|\d+)|(\d{1,3}(?:[.,]\d{3})+|\d{3,})\s?(?:euro|EUR)", re.I)
DASHES = re.compile("[\u2013\u2014]")


def _amounts(text: str) -> list[int]:
    out = []
    for m in EURO.finditer(text):
        raw = (m.group(1) or m.group(2)).replace(".", "").replace(",", "")
        if raw.isdigit():
            out.append(int(raw))
    return out


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
    return problems


def fix_dashes(text: str) -> str:
    return DASHES.sub(",", text)
