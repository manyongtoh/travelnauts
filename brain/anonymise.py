"""Anonymiser: the gate between TravelSpirit and the brain for the anonymised stage.

What it removes from free text: email addresses, phone numbers, IBANs, BSNs, passport and ID
numbers, Dutch postcodes and street addresses, birth dates, and person names (the names known
from the relation record, plus names found after greetings, sign-offs and family words).

What it keeps, because the agents need it: destinations, months, trip length, ages of the children,
budgets, wishes, and partner and hotel names (businesses, not people).

It fails closed: after scrubbing, the detectors run again over the result. If anything that looks
personal is left, the record is refused, not passed on. A refused record needs a person to look at it.

Replacements are one way (no key is kept), so the brain cannot turn [NAAM_1] back into a name.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

# --- Detectors ---------------------------------------------------------------------------------

EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
URL_WITH_PERSON = re.compile(r"https?://\S*(?:facebook|instagram|linkedin)\.\S+", re.I)
PHONE = re.compile(r"(?<![\w-])(?:(?:\+|00)\d{1,3}[\s.-]?)?(?:\(0\)[\s.-]?)?\d(?:[\s.-]?\d){7,11}(?!\d)")
IBAN = re.compile(r"\b[A-Z]{2}\d{2}[\s]?(?:[A-Z0-9]{4}[\s]?){2,7}[A-Z0-9]{1,4}\b")
POSTCODE = re.compile(r"\b[1-9]\d{3}\s?(?!SA|SD|SS)[A-Z]{2}\b")
STREET = re.compile(r"\b[A-Z][a-zA-Z'.-]+(?:\s[A-Z][a-zA-Z'.-]+)?(?:straat|laan|weg|plein|gracht|kade|dijk|singel|steeg|hof|park|plantsoen|dreef)\s\d+[a-zA-Z]?\b")
BIRTH = re.compile(r"\b(?:geboren(?:\sop)?|geboortedatum|geb\.|date of birth|dob|born(?:\son)?)[:\s]+\d{1,2}[-/.\s](?:\d{1,2}|[a-z]+)[-/.\s]\d{2,4}\b", re.I)
DATE_FULL = re.compile(r"\b\d{1,2}[-/.]\d{1,2}[-/.](?:19|20)\d{2}\b")
PASSPORT_CTX = re.compile(r"\b(?:paspoort(?:nummer)?|passport(?:\snumber|\sno\.?)?|id[-\s]?kaart|documentnummer|identiteitskaart)[:\s#]*((?=[A-Za-z0-9]*\d)[A-Za-z0-9]{6,10})\b", re.I)
PASSPORT_NL = re.compile(r"\b[A-NP-Z]{2}[A-NP-Z0-9]{6}\d\b")
LONG_DIGITS = re.compile(r"\b\d{9}\b")

# Words that are never names, even when capitalised after a greeting.
NOT_NAMES = {"travelnauts", "team", "allemaal", "heer", "mevrouw", "mevr", "dhr", "familie", "gezin", "allen", "beste",
             "hallo", "hoi", "hi", "hey", "dear", "regards", "groet", "groeten", "thanks", "bedankt", "dank", "met",
             "vriendelijke", "hartelijke", "liefs", "kind", "best", "cheers", "alvast", "namens", "and", "en",
             "goedemiddag", "goedemorgen", "goedenavond", "travelnauts,", "mensen", "sorry"}
GREETING = re.compile(r"(?:^|\n)[ \t]*(?i:beste|hallo|hoi|hi|hey|dear|lieve)[ ]+((?:[A-Z][a-zé'-]+)(?:[ ](?:van|de|der|den|ter|ten)?[ ]?[A-Z][a-zé'-]+){0,2})")
SIGNOFF = re.compile(r"(?i:groet(?:en|jes)?|regards|thanks|bedankt|liefs|cheers|dank je wel)[,!.]?[ \t]*(?:\n|,)?[ \t]*((?:[A-Z][a-zé'-]+)(?:[ ](?:van|de|der|den|ter|ten)?[ ]?[A-Z][a-zé'-]+){0,3})")
FAMILY_WORD = re.compile(r"\b(?i:mijn|onze|our|my) (?i:man|vrouw|partner|zoon|dochter|zoontje|dochtertje|husband|wife|son|daughter|kinderen|kids)[ ,]+(?:heet |is |called )?([A-Z][a-zé'-]+(?:(?:, | en | and )[A-Z][a-zé'-]+)*)")
SIGNATURE_NAME = re.compile(r"(?:^|\n)[ \t]*([A-Z][a-zé'-]+[ ](?:(?:van|de|der|den|ter|ten)[ ])*[A-Z][a-zé'-]+)[ \t]*(?=\n|$)")

TRAVEL_WORDS: set[str] = set()


def _travel_words() -> set[str]:
    """Places, hotels and partners that may look like names but must stay."""
    if not TRAVEL_WORDS:
        from .synth.world import DESTINATIONS
        for d in DESTINATIONS.values():
            TRAVEL_WORDS.update(w.lower() for w in re.findall(r"[A-Za-z]+", d["name"] + " " + d["nl"]))
            TRAVEL_WORDS.update(w.lower() for w in re.findall(r"[A-Za-z]+", d["partner"][0]))
            for stop, _, hotels, _ in d["stops"]:
                TRAVEL_WORDS.update(w.lower() for w in re.findall(r"[A-Za-z]+", stop + " " + " ".join(hotels)))
    return TRAVEL_WORDS


@dataclass
class Finding:
    kind: str
    value: str


@dataclass
class Result:
    text: str
    findings: list[Finding] = field(default_factory=list)
    residual: list[Finding] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.residual

    def summary(self) -> dict:
        kinds: dict[str, int] = {}
        for f in self.findings:
            kinds[f.kind] = kinds.get(f.kind, 0) + 1
        return {"ok": self.ok, "removed": kinds, "residual": [f.kind for f in self.residual]}


class Refused(Exception):
    def __init__(self, result: Result):
        super().__init__(f"Anonymiser refused the record: {[f.kind for f in result.residual]}")
        self.result = result


FREEMAIL = {"gmail.com", "hotmail.com", "outlook.com", "live.nl", "live.com", "icloud.com", "me.com", "ziggo.nl",
            "kpnmail.nl", "xs4all.nl", "yahoo.com", "planet.nl", "home.nl", "hotmail.nl", "telfort.nl", "example.org"}
TAG = re.compile(r"\[[A-Z]+_\d+\]")


def suspicious(text: str, known_names: list[str] | None = None) -> list[Finding]:
    """A second, cruder check on the scrubbed text. Anything here means: a person must look."""
    t = TAG.sub(" ", text)
    out = []
    if "@" in t or re.search(r"\((?:at|apestaart)\)|\[at\]", t, re.I):
        out.append(Finding("EMAIL_LIKE", "@"))
    for m in re.finditer(r"\d(?:[\s./-]?\d){8,}", t):
        out.append(Finding("NUMBER_LIKE", m.group(0)))
    for m in re.finditer(r"\b(?=(?:[A-Za-z]*\d){2})(?=(?:\d*[A-Za-z]){2})[A-Za-z0-9]{8,14}\b", t):
        out.append(Finding("CODE_LIKE", m.group(0)))
    for n in known_names or []:
        for part in [n] + n.split():
            if len(part) > 2 and part.lower() not in ("van", "der", "den") and re.search(rf"(?<!\w){re.escape(part)}(?!\w)", t, re.I):
                out.append(Finding("NAME_LEFT", part))
    return out


def _iban_valid(s: str) -> bool:
    s = s.replace(" ", "").upper()
    if not 15 <= len(s) <= 34:
        return False
    n = "".join(str(int(c, 36)) for c in s[4:] + s[:4])
    return int(n) % 97 == 1


def _bsn_valid(s: str) -> bool:
    d = [int(c) for c in s]
    return len(d) == 9 and (sum(w * x for w, x in zip(range(9, 1, -1), d[:8])) - d[8]) % 11 == 0


def _names_in(text: str) -> list[str]:
    tw = _travel_words()
    out = []
    for rx in (GREETING, SIGNOFF, FAMILY_WORD, SIGNATURE_NAME):
        for m in rx.finditer(text):
            for part in re.split(r", | en | and ", m.group(1)):
                words = [w for w in part.split() if w.lower() not in ("van", "de", "der", "den", "ter", "ten")]
                if not words or any(w.lower().strip(",.") in NOT_NAMES or w.lower() in tw for w in words):
                    continue
                out.append(part.strip())
    return out


class Anonymiser:
    def __init__(self) -> None:
        self.counters: dict[str, int] = {}
        self.seen: dict[str, str] = {}

    def _tag(self, kind: str, value: str) -> str:
        key = f"{kind}:{value.lower()}"
        if key not in self.seen:
            self.counters[kind] = self.counters.get(kind, 0) + 1
            self.seen[key] = f"[{kind}_{self.counters[kind]}]"
        return self.seen[key]

    def detect(self, text: str, known_names: list[str] | None = None) -> list[Finding]:
        found: list[Finding] = []
        for kind, rx in (("EMAIL", EMAIL), ("URL", URL_WITH_PERSON), ("IBAN", IBAN), ("ADRES", STREET),
                         ("POSTCODE", POSTCODE), ("GEBOORTEDATUM", BIRTH), ("DATUM", DATE_FULL)):
            for m in rx.finditer(text):
                if kind == "IBAN" and not _iban_valid(m.group(0)):
                    continue
                found.append(Finding(kind, m.group(0)))
        for m in PASSPORT_CTX.finditer(text):
            found.append(Finding("DOCUMENT", m.group(1)))
        for m in PASSPORT_NL.finditer(text):
            if any(ch.isdigit() for ch in m.group(0)[:8]):
                found.append(Finding("DOCUMENT", m.group(0)))
        for m in LONG_DIGITS.finditer(text):
            if _bsn_valid(m.group(0)):
                found.append(Finding("BSN", m.group(0)))
        for m in PHONE.finditer(text):
            digits = re.sub(r"\D", "", m.group(0))
            if 9 <= len(digits) <= 13:
                found.append(Finding("TELEFOON", m.group(0).strip()))
        names = set(_names_in(text))
        for n in known_names or []:
            if n and len(n) > 1:
                names.add(n)
                names.update(p for p in n.split() if len(p) > 2 and p.lower() not in ("van", "der", "den"))
        for n in sorted(names, key=len, reverse=True):
            if re.search(rf"(?<!\w){re.escape(n)}(?!\w)", text):
                found.append(Finding("NAAM", n))
        return found

    def scrub(self, text: str, known_names: list[str] | None = None, strict: bool = True) -> Result:
        res = Result(text)
        findings = self.detect(text, known_names)
        # Longest values first so "Femke Meijer" goes before "Femke".
        for f in sorted(findings, key=lambda f: len(f.value), reverse=True):
            tag = self._tag(f.kind, f.value)
            res.text = re.sub(rf"(?<!\w){re.escape(f.value)}(?!\w)", tag, res.text)
        res.findings = findings
        res.residual = [f for f in self.detect(res.text, known_names) if not TAG.fullmatch(f.value)]
        res.residual += suspicious(res.text, known_names)
        if strict and not res.ok:
            raise Refused(res)
        return res


def anonymise_mail(mail: dict, relation: dict | None = None, strict: bool = True) -> tuple[dict, dict]:
    """Return an anonymised copy of a TravelSpirit mail and a report. Raises Refused when unsure."""
    known = []
    if relation:
        known += [relation.get("contact_name", ""), relation.get("surname", "")]
        known += relation.get("other_names", [])
    a = Anonymiser()
    body = a.scrub(mail.get("body", ""), known, strict)
    subject = a.scrub(mail.get("subject", ""), known, strict)
    out = {k: v for k, v in mail.items() if k not in ("sender", "body", "subject")}
    domain = (mail.get("sender") or "").rsplit("@", 1)[-1].lower()
    out |= {"sender": "[EMAIL_AFZENDER]", "sender_domain": "freemail" if domain in FREEMAIL or not domain else domain,
            "subject": subject.text, "body": body.text}
    return out, {"body": body.summary(), "subject": subject.summary()}


def anonymise_relation(rel: dict, ref: str) -> dict:
    """Keep what the agents need (party, ages, past destinations), drop who they are."""
    return {"id": ref, "surname": f"Gezin {ref[-3:].upper()}", "contact_name": f"Gezin {ref[-3:].upper()}",
            "email": None, "adults": rel.get("adults"), "child_ages": rel.get("child_ages", []),
            "city": None, "past_destinations": rel.get("past_destinations", []), "notes": ""}
