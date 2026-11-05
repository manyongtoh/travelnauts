# Gemma 4 (e4b) on a CPU-only runner: second model check

Run 41989264677, 5 November 2026, same runner and sample as [the first run](gemma4-e4b-cpu.md), after the prompt
and triage fixes in commit 1ad6ef8.

## What changed since run 1

| Point from run 1 | Run 1 | Run 2 |
|---|---|---|
| Greeting with the first name | missing | fixed: "Beste Marieke", "Beste Noor", "Beste Olivier" |
| Complaint addressed "Beste Eva en Kok" | wrong | fixed: "Beste Eva", "Beste Hanna" |
| "Laat je weten" | wrong | fixed: "Laat ons weten wat jullie ervan vinden" |
| Amounts | "€8510.0" | fixed: "€ 8.510", "€ 15.420", "€ 5.790" |
| "rustig tempo" in complaints | yes | fixed: only in itineraries |
| Triage category, hard mail | 100% | 86% (one change request read as a question) |
| Destination, hard mail | 50% | **100%** |
| Destination, clean mail | 50% | 50% (unchanged) |
| Destination, English mail | 100% | 100% |
| Safety: prices, hotels, money promises | all held | all held |
| Speed on CPU | 105 s per mail, 452 s per proposal | 112 s per mail, 489 s per proposal |

## New things this run showed, fixed straight after

- **Complaint replies ended with "Laat ons weten wat jullie ervan vinden"**, the proposal closing, which reads
  oddly after an apology. The house style now keeps that line for proposals; a complaint says when they hear from us.
- **A proposal told the family two hotel prices "zijn verlopen"** (expired): an internal detail. The house style now
  says "nog niet bevestigd" and never mentions expired prices to a family.
- **Destination still empty on half the clean mail.** When the model leaves it empty and the mail names exactly
  one of our destinations (or a place we know, like Bali), triage now fills it; two or none stays empty. With the
  stand-in this lifts hard mail from 33% to 39% and English from 18% to 36%. The model check now lists every missed
  destination, so the next run shows which mails these are.
- **The change request read as a question** is the case the deterministic net from the specialist day catches when
  the mail names a stop of the family's proposal (fixed earlier today, not in this run).

## Verdict

The writing fixes all landed: greeting, amounts, closing and tone now read like Travelnauts. Understanding stays
strong and every safety check held. Speed on CPU is still far too slow: a GPU or a hosted endpoint remains the
next step (docs/gemma.md).

---

# Model check: ollama:gemma4:e4b (small) / ollama:gemma4:e4b (large)

A sample of the bench on CPU only. Synthetic data. Compare with the stand-in in docs/test-reports.

| Check | Result |
|---|---|
| Triage, clean mail (15) | category 100.0%, destination 50.0% |
| Triage, hard mail (7) | category 85.7%, destination 100.0% |
| Triage, english mail (8) | category 100.0%, destination 100.0% |
| Triage failures | 0 |
| Seconds per mail (CPU) | 111.5 |
| Proposals written | 4 of 4, 0 flagged by the checks, 489.4 s each |
| Complaint replies | 3 of 3, money promises: 0 |
| Partner offers in PDF read right | 3 of 3 |
| Model calls | 46 to the model, 0 failed, 0 fell back to the stand-in |
| Speed | 5.6 tokens per second |

Misclassified (hard): change -> question (1)

## Proposal r008 (calculated price 8510.0 euro)
Checks: no problems

```
Beste Marieke,

Wat een mooie keuze, Sri Lanka! Ik heb een route gemaakt met een rustig tempo, perfect voor jullie met de 3-jarige.

Negombo (1 nacht): Jullie slapen in Lagoon Edge Hotel. Een aanrader is de Vismarkt in de ochtend.

Sigiriya (5 nachten): Jullie verblijven in Sigiriya Jungle Lodge. Jullie kunnen de Leeuwenrots beklimmen en een Jeep safari Minneriya maken.

Ella (5 nachten): Jullie slapen in Ella Tea Estate Cottage. Een aanrader is de treinrit door de theeplantages en Little Adams Peak.

Yala (4 nachten): Jullie verblijven in Yala Safari Tents. Hier is een safari in Yala gepland.

Mirissa (7 nachten): Jullie zijn in Mirissa Palm Beach Resort. Jullie kunnen walvissen spotten (december tot april) en surfles voor kinderen nemen.

Wat het weer betreft: in augustus is het aan de zuidwestkust regenseizoen.

De indicatie voor deze reis is € 8.510. We checken nog de prijs van het Lagoon Edge Hotel.

We kunnen de route samen op maat aanpassen. Laat ons weten wat jullie ervan vinden.

Hartelijke groet,
Tessa Boer
```

## Proposal r012 (calculated price 15420.0 euro)
Checks: no problems

```
Beste Noor,

Wat een mooie bestemming! Ik heb een voorstel gemaakt voor jullie reis naar Vietnam met de kinderen van 6, 6 en 13.

We hebben een rustig tempo ingepland, zodat jullie de tijd hebben om echt te genieten.

In Hanoi (3 nachten) verblijven jullie in het Old Quarter Lantern Hotel. Jullie kunnen bijvoorbeeld een streetfood tour op de fiets maken of naar het Waterpoppentheater.
In Ninh Binh (3 nachten) zijn jullie in het Tam Coc Rice Field Homestay. Daar kunnen jullie een bootje door Trang An maken en fietsen langs de rijstvelden.
In Halong Bay (3 nachten) verblijven jullie in het Bai Tu Long Family Junk. Jullie kunnen kajakken in de baai en een grot bezoeken.
In Hoi An (6 nachten) zijn jullie in het Hoi An Garden Villas. Jullie kunnen lantaarns maken en een kookles met marktbezoek volgen.
In Ho Chi Minhstad (4 nachten) verblijven jullie in het Saigon Courtyard Hotel. Een leuke activiteit is een Mekong delta dagtocht.

Voor september is dit een goede reistijd voor Vietnam.

De indicatie voor deze reis is € 15.420.

Laat ons weten wat jullie ervan vinden. Dan kunnen we de route samen aanpassen.

Hartelijke groet,
Lieke Jansen
```

## Proposal r015 (calculated price 5790.0 euro)
Checks: no problems

```
Beste Olivier,

Costa Rica is een prachtige bestemming voor jullie met de kinderen van 2 jaar. Ik heb een route gemaakt met een rustig tempo, zodat jullie de natuur echt kunnen ervaren.

Jullie verblijven één nacht in San Jose in het Escazu Garden Hotel. Daar kunnen jullie bijvoorbeeld een koffietour maken.

Daarna gaan jullie naar Tortuguero voor 6 nachten in het Tortuguero Canal Lodge. Hier kunnen jullie kanoën door de kanalen en schildpadden kijken.

Tenslotte volgt een verblijf van 9 nachten in Manuel Antonio Jungle Villas. Jullie kunnen hier een nationaal park met gids bezoeken en kajakken bij de mangroven.

De beste reistijd voor Costa Rica is van december tot en met april.

De indicatie voor deze reis is € 5.790. We checken nog de prijzen van Escazu Garden Hotel en Tortuguero Canal Lodge, want die zijn verlopen.

Laat ons weten wat jullie ervan vinden.

Hartelijke groet,
Joost Haan
```

## Complaint reply to m0085

```
Beste Eva,

Het spijt ons te horen dat jullie teleurgesteld zijn.
We lezen jullie bericht over het hotel.
De kamer was vies en klein. Dat is niet de ervaring die we willen geven.
We gaan dit direct onderzoeken.
We nemen contact met het hotel op.
We laten jullie weten wat we vinden.

Laat ons weten wat jullie ervan vinden.
Hartelijke groet,
Travelnauts
```

## Complaint reply to m0086

```
Beste Hanna,

Het spijt ons te horen dat jullie teleurgesteld zijn over het hotel. De kamer was vies en klein. Dit is niet de ervaring die we willen dat jullie hebben.

Ik ga dit direct met het hotel bespreken. We kijken hoe we dit kunnen oplossen.

Laat ons weten wat jullie ervan vinden.

Hartelijke groet,
Travelnauts
```

