# Gemma 4 (e4b) on a CPU-only runner: first model check

Run 41918493904, 4 November 2026, GitHub runner (4 CPUs, 16 GB, no GPU), `brain modelcheck`, synthetic data.
Before the fixes listed at the bottom.

## Compared with the stand-in model on the same sample

| Check | Gemma 4 e4b | Stand-in |
|---|---|---|
| Triage category, clean mail | 100% | 100% |
| Triage category, hard mail | **100%** | 57% |
| Triage category, English mail | **100%** | 25% |
| Destination | 50% clean and hard, 100% English | 100% clean, 50% hard, 0% English |
| Failures, fallbacks | 0 of 46 calls | n/a |
| Proposals passing the checks (price, hotels, health) | 4 of 4 | 4 of 4 |
| Complaint replies promising money | 0 of 3 | 0 of 3 |
| Partner offers read from PDF | 3 of 3 | 3 of 3 |
| Speed on CPU | 105 s per mail, 452 s per proposal, 6 tokens/s | instant |

## What this says

- **Understanding mail: very good.** Every hard and English mail was put in the right category, where the stand-in's
  Dutch rules fail. Structured output worked on every call: no format failures, no fallback needed.
- **Safety held.** Prices exactly from the calculation, no invented hotels, no money promised in complaints.
- **Writing: good Dutch, follows the structure, needs polish.** It uses the route, the activities and the season.
  Weak points: no greeting with the family's name; "Laat je weten" instead of "Laat ons weten"; prices written as
  "€8510.0"; complaint replies addressed "Beste Eva en Kok" (a surname as a first name) and borrowing "rustig tempo"
  from the house style where it makes no sense.
- **Destination 50%:** most likely the model answers with the name ("Sri Lanka") where the brain expects its key.
- **Speed: not usable on CPU.** A GPU (Azure) or a hosted endpoint is needed; expect tens of times faster.

## Fixed after this run (to be confirmed by the next run)

- Triage translates a destination name into the brain's key (via the same aliases as search), never guessing.
- House style: open with "Beste" and the first name, amounts as "€ 8.510", "Laat ons weten wat jullie ervan vinden",
  "rustig tempo" only for itineraries and never in complaint replies; the first name is passed to the model separately.

---

# Model check: ollama:gemma4:e4b (small) / ollama:gemma4:e4b (large)

A sample of the bench on CPU only. Synthetic data. Compare with the stand-in in docs/test-reports.

| Check | Result |
|---|---|
| Triage, clean mail (15) | category 100.0%, destination 50.0% |
| Triage, hard mail (7) | category 100.0%, destination 50.0% |
| Triage, english mail (8) | category 100.0%, destination 100.0% |
| Triage failures | 0 |
| Seconds per mail (CPU) | 105.3 |
| Proposals written | 4 of 4, 0 flagged by the checks, 452.0 s each |
| Complaint replies | 3 of 3, money promises: 0 |
| Partner offers in PDF read right | 3 of 3 |
| Model calls | 46 to the model, 0 failed, 0 fell back to the stand-in |
| Speed | 6.0 tokens per second |


## Proposal r008 (calculated price 8510.0 euro)
Checks: no problems

```
Wat leuk dat jullie aan Sri Lanka denken! Ik heb een route op maat gemaakt voor jullie met de 3-jarige.

Dit is een voorstel met een rustig tempo.

Negombo (1 nacht): Jullie slapen in Lagoon Edge Hotel. Een aanrader is de Vismarkt in de ochtend. Dit checken we nog.
Sigiriya (5 nachten): Jullie slapen in Sigiriya Jungle Lodge. Jullie kunnen de Leeuwenrots beklimmen en een Jeep safari Minneriya maken.
Ella (5 nachten): Jullie slapen in Ella Tea Estate Cottage. Jullie kunnen de treinrit door de theeplantages maken en Little Adams Peak bezoeken.
Yala (4 nachten): Jullie slapen in Yala Safari Tents. Een safari in Yala staat op het programma.
Mirissa (7 nachten): Jullie slapen in Mirissa Palm Beach Resort. Jullie kunnen walvissen spotten (december tot april) en surfles voor kinderen nemen.

De beste reistijd voor het zuiden en westen is december tot en met april.

De indicatie voor deze reis is €8510.0. We checken nog de prijs van het Lagoon Edge Hotel.

Laat je weten wat je ervan vindt. We kunnen de route samen aanpassen.

Hartelijke groet,
Tessa Boer
```

## Proposal r012 (calculated price 15420.0 euro)
Checks: no problems

```
Wat een mooie reis naar Vietnam voor jullie kinderen van 6, 6 en 13!

Ik heb een voorstel gemaakt met een rustig tempo, zodat jullie de tijd hebben om echt te genieten.

Hanoi (3 nachten): Jullie verblijven in Old Quarter Lantern Hotel. Jullie kunnen een streetfood tour op de fiets maken en het Waterpoppentheater zien.
Ninh Binh (3 nachten): Jullie slapen in Tam Coc Rice Field Homestay. Hier kunnen jullie bootjes door Trang An maken en fietsen langs de rijstvelden.
Halong Bay (3 nachten): Jullie verblijven in Bai Tu Long Family Junk. Jullie kunnen kajakken in de baai en een grot bezoeken.
Hoi An (6 nachten): Jullie verblijven in Hoi An Garden Villas. Jullie kunnen lantaarns maken en een kookles met marktbezoek volgen.
Ho Chi Minhstad (4 nachten): Jullie slapen in Saigon Courtyard Hotel. Een mooie dagtocht naar de Mekong delta staat op het programma.

Voor september is de reistijd in Vietnam goed.

De indicatie voor deze reis is €15.420,-.

Dit is een voorstel dat we samen op maat kunnen aanpassen. Laat je weten wat jullie ervan vinden?

Hartelijke groet,
Lieke Jansen
```

## Proposal r015 (calculated price 5790.0 euro)
Checks: no problems

```
Wat een mooie keuze! Ik heb een voorstel voor jullie reis naar Costa Rica met jullie kind van 2 jaar.

We hebben een route gemaakt met een rustig tempo.

San Jose (1 nacht): Jullie slapen in Escazu Garden Hotel. Een aanrader is een koffietour.
Tortuguero (6 nachten): Jullie verblijven in Tortuguero Canal Lodge. Hier kunnen jullie kanoën door de kanalen en schildpadden kijken.
Manuel Antonio (9 nachten): Jullie slapen in Manuel Antonio Jungle Villas. Jullie kunnen het nationale park bezoeken met een gids en bij de mangroven kajakken.

De beste reistijd voor Costa Rica is van december tot en met april.

De indicatie voor deze reis is € 5790. We checken nog de prijs van de hotels, want die zijn verlopen.

Dit is een indicatie. We kunnen de route op maat samen aanpassen. Laat je weten wat je ervan vindt?

Hartelijke groet,
Joost Haan
```

## Complaint reply to m0085

```
Beste Eva en Kok,

Wat jammer om te horen dat jullie teleurgesteld zijn!

Het spijt ons heel erg dat jullie ervaring met het hotel zo negatief was. Een schone en comfortabele kamer is natuurlijk essentieel.

We gaan dit rustig tempo onderzoeken. We kijken naar de klachten over de hygiëne en de grootte van de kamer.

We nemen zo snel mogelijk contact met jullie op.

Hartelijke groet,
Travelnauts
```

## Complaint reply to m0086

```
Beste Hanna en Koster,

Wat jammer om te horen dat jullie teleurgesteld zijn!

Het spijt ons heel erg dat jullie ervaring met het hotel niet goed was. Een vieze en kleine kamer is absoluut niet wat we willen dat jullie meemaken.

We gaan dit rustig bekijken. We kijken intern naar wat er gebeurd is. We nemen contact met jullie op zodra we meer weten.

Hartelijke groet,
Travelnauts
```

