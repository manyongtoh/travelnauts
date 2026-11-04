"""Realistic mail endings and the name a person would read from them: (body, contact name, surname).

An empty name means a person would not be sure either; the extractor must then give nothing rather than guess.
Written for test #8 (name from the sign-off). Mixed Dutch and English, phone footers, replies with history,
company signatures, couples, families, and endings that are not names at all.
"""
import random

REQ = "Wij willen in de zomer met de kinderen naar Costa Rica. Kunnen jullie een voorstel maken?"
QUOTE = ("\n\nOp 3 nov. 2026 om 10:12 schreef Sanne de Vries | Travelnauts <sanne@travelnauts.example>:\n"
         "> Beste familie,\n> Hierbij ons voorstel.\n> Hartelijke groet,\n> Sanne de Vries\n")
QUOTE_EN = ("\n\nOn Tue, 3 Nov 2026 at 10:12, Sanne de Vries <sanne@travelnauts.example> wrote:\n"
            "> Dear family,\n> Kind regards,\n> Sanne de Vries\n")
FWD_OUTLOOK = ("\n\n-----Oorspronkelijk bericht-----\nVan: Sanne de Vries <sanne@travelnauts.example>\n"
               "Verzonden: dinsdag 3 november 2026 10:12\nOnderwerp: Voorstel\n\nBeste familie,\nGroet, Sanne de Vries")

PEOPLE = [("Marieke Visser", "Visser"), ("Jan van der Berg", "van der Berg"), ("Anne-Marie Dijkstra", "Dijkstra"),
          ("Zoë Bakker", "Bakker"), ("Mohamed El Amrani", "El Amrani"), ("Sarah Thompson", "Thompson"),
          ("Pieter de Jong", "de Jong"), ("Fatima Yilmaz", "Yilmaz"), ("Joëlle van 't Hof", "van 't Hof"),
          ("Sjoerd ter Horst", "ter Horst"), ("Esther van den Broek", "van den Broek"), ("Tom Jansen", "Jansen")]
GREETINGS = ["Groet,", "Groeten,", "Groetjes,", "Met vriendelijke groet,", "Vriendelijke groeten,", "Hartelijke groet,",
             "Met hartelijke groet,", "Mvg,", "M.v.g.", "Gr.", "Liefs,", "Kind regards,", "Best regards,", "Regards,",
             "Best,", "Cheers,", "Alvast bedankt!", "Dank je wel,", "Tot snel,", "Thanks,"]
FOOTERS = ["", "\n\nVerstuurd vanaf mijn iPhone", "\n\nSent from my Samsung Galaxy", "\n\nGet Outlook for iOS",
           "\n\nVerzonden met de Mail-app"]


def cases() -> list[tuple[str, str, str]]:
    rng = random.Random(8)
    out = []
    # 1. a person signs off, in all common ways, with or without a phone footer or quoted history
    for i, (name, sur) in enumerate(PEOPLE * 5):
        g = GREETINGS[i % len(GREETINGS)]
        sep = rng.choice([" ", "\n", "\n\n"])
        tail = rng.choice(FOOTERS) + (rng.choice(["", QUOTE, QUOTE_EN, FWD_OUTLOOK]) if i % 3 == 0 else "")
        out.append((f"{REQ}\n\n{g}{sep}{name}{tail}", name, sur))
    # 2. company signature under the name
    out += [
        (f"{REQ}\n\nMet vriendelijke groet,\n\nJan de Boer\nSenior adviseur | Acme BV\nT 06 12345678\nwww.acme.example",
         "Jan de Boer", "de Boer"),
        (f"{REQ}\n\nKind regards,\nOlivia Brown\nHead of Finance\nM +44 7700 900123", "Olivia Brown", "Brown"),
        (f"{REQ}\n\n--\nMarieke Visser\n06 12345678", "Marieke Visser", "Visser"),
        (f"{REQ}\n\nGroet,\nEmma 😊", "Emma", ""),
        (f"{REQ}\n\nGroeten, Bas Mulder (06 23456789)", "Bas Mulder", "Mulder"),
        (f"{REQ}\n\nGroet,\nJ. de Vries", "J. de Vries", "de Vries"),
        (f"{REQ}\n\nGroet,\nMARIEKE VISSER", "Marieke Visser", "Visser"),
        (f"{REQ}\n\ngroetjes, marieke", "Marieke", ""),
    ]
    # 3. couples and families
    out += [
        (f"{REQ}\n\nLiefs, Anouk en Pieter", "Anouk en Pieter", ""),
        (f"{REQ}\n\nGroeten,\nMarieke en Johan Visser", "Marieke en Johan Visser", "Visser"),
        (f"{REQ}\n\nGroet, Daan & Iris de Wit", "Daan & Iris de Wit", "de Wit"),
        (f"{REQ}\n\nGroeten, familie Jansen", "", "Jansen"),
        (f"{REQ}\n\nGroeten,\nFam. van der Meer", "", "van der Meer"),
        (f"{REQ}\n\nGroeten, de familie Bos", "", "Bos"),
        (f"{REQ}\n\nKind regards,\nThe Smith family", "", "Smith"),
    ]
    # 4. endings that are not a name: nothing is better than a guess
    out += [
        (f"{REQ}\n\nGroeten uit Utrecht!", "", ""),
        (f"{REQ}\n\nGroet,\nTeam Marketing", "", ""),
        (f"{REQ}\n\nLiefs, ons hele gezin", "", ""),
        (f"{REQ}\n\nBedankt!", "", ""),
        (f"{REQ}\n\nGroetjes,\nPapa en mama", "", ""),
        (f"{REQ}\n\nGroet,\nReisgezelschap De Zonnebloem", "", ""),
        (f"{REQ}\n\nMet vriendelijke groet,\nAcme Holding BV", "", ""),
        (f"{REQ}\n\nGroeten,\nWij", "", ""),
        (f"{REQ}", "", ""),
        (f"{REQ}\n\nGroet, X", "", ""),
        (f"{REQ}\n\nBest,\nThe team at Acme Travel", "", ""),
        (f"{REQ}\n\nCheers!", "", ""),
        (f"{REQ}{QUOTE}", "", ""),  # only the quoted history is signed: that is our specialist, not the family
        (f"{REQ}\n\nGroeten,\nSanne\nTravelnauts", "", ""),  # our own signature in a forward
    ]
    return out


def held_out() -> list[tuple[str, str, str]]:
    """Written after the extractor was tuned on cases(); scored as they came, to see how it generalises."""
    R = "Is het mogelijk om in de meivakantie naar Japan te gaan met twee kinderen?"
    return [
        (f"{R}\n\nGroetjes van ons allemaal,\nLotte", "Lotte", ""),
        (f"{R}\n\nHartelijke groeten,\nRuud en Ilse Kramer\nAmersfoort", "Ruud en Ilse Kramer", "Kramer"),
        (f"{R}\n\nVriendelijke groet / Kind regards,\n\nNiels Vermeulen\nProduct Owner\n\nDisclaimer: dit bericht is vertrouwelijk.",
         "Niels Vermeulen", "Vermeulen"),
        (f"{R}\n\nmvg\nkarin smit", "Karin Smit", "Smit"),
        (f"{R}\n\nGroet,\nDe Bruijn", "", ""),
        (f"{R}\n\nGroeten,\nfam. de Graaf", "", "de Graaf"),
        (f"{R}\n\nThanks a lot!\nChris & Sam", "Chris & Sam", ""),
        (f"{R}\n\nGr Wouter", "Wouter", ""),
        (f"{R}\n\nGroeten,\n\nEva\n\nOp ma 2 nov. 2026 schreef Travelnauts <info@travelnauts.example>:\n> Bedankt voor je bericht",
         "Eva", ""),
        (f"{R}\n\nLiefs,\nMama", "", ""),
        (f"{R}\n\nMet vriendelijke groet,\n\nIng. P.J. Hendriks", "", ""),
        (f"{R}\n\nGroet,\nHenk-Jan Mol\n+31 6 1234 5678", "Henk-Jan Mol", "Mol"),
        (f"{R}\n\nBest wishes,\nAisha Khan", "Aisha Khan", "Khan"),
        (f"{R}\n\nGroeten,\nNoah (en Emma, Finn en Saar)", "Noah", ""),
        (f"{R}\n\nGroet, Bureau Zuid", "", ""),
        (f"{R}\n\nGroetjes!!\nSophie van Dam xx", "Sophie van Dam", "van Dam"),
        (f"{R}\n\nGroeten,\nJ.", "", ""),
        (f"{R}\n\nVriendelijke groet,\nM. Peters\nnamens de familie Peters", "M. Peters", "Peters"),
        (f"{R}\n\nGroet,\nPeter\n\n________________________________\nVan: Travelnauts\nVerzonden: maandag", "Peter", ""),
        (f"{R}\n\nGroeten,\nTim en Lisa", "Tim en Lisa", ""),
        (f"{R}\n\nHoi! Groetjes, Fleur", "Fleur", ""),
        (f"{R}\n\nGroeten uit Zwolle,\nBram", "Bram", ""),
        (f"{R}\n\nBedankt alvast,\nYara El Idrissi", "Yara El Idrissi", "El Idrissi"),
        (f"{R}\n\nGroet,\nOpa Kees", "", ""),
    ]
