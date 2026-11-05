# Gemma 4 31B, hosted (Google AI Studio free tier): model check

Run 42031090860, 5 November 2026, GitHub runner calling `gemma-4-31b-it` through Google's OpenAI compatible API.
Same check as the CPU runs, with a bigger sample: 60 mails and 10 proposals. Synthetic data.

## Compared with Gemma 4 e4b on a CPU (run 2)

| Check | e4b on CPU (run 2) | 31B hosted |
|---|---|---|
| Triage category, clean / hard / English | 100% / 86% / 100% | 100% / 100% / 100% |
| Destination, clean / hard / English | 50% / 100% / 100% | 100% / 100% / 100% |
| Proposals passing the checks | 4 of 4 | 8 of 8 written (2 of 10 not written: provider errors) |
| Complaint replies promising money | 0 | 0 |
| Partner offers read from PDF | 3 of 3 | 3 of 3 |
| Seconds per mail | 112 | 37 |
| Seconds per proposal | 489 | 50 |
| Calls that failed | 0 of 46 | 25 of 84 (provider: "internal error", "high demand", rate limit) |

## What this says

- **Understanding: as good as it gets on this sample.** Every mail that got an answer was put in the right category
  with the right destination, including the hard and English ones.
- **Writing: the best so far.** Right greeting, amounts as "€ 8.510", the proper closing, the complaint reply ends
  with when they hear from us. It even left out whale watching for an August trip, which is out of season.
- **Three things to polish, fixed after this run:** one proposal repeated a stop (Halong Bay twice) and no check
  caught it, so a repeated line is now flagged; "dit checken we nog" appeared after several lines instead of once
  next to the price; and a complaint reply promised an answer "binnen drie werkdagen", a number nobody gave it.
- **The free tier is not reliable enough to judge uptime:** almost a third of the calls failed on Google's side.
  The brain now waits and retries a busy hosted model twice (3 s, then 9 s) before moving on. In the pilot the
  model runs in Travelnauts' own Azure environment, so this number says nothing about the pilot.
- **Speed: about 3 to 10 times faster than the CPU,** on a busy free tier. A dedicated GPU will be faster still.

## Next

Run e4b and the 26B A4B (the faster mixture of experts) on a GPU in Azure, which is what the pilot will use,
and compare cost and speed with this quality.

---

# Model check: openai:gemma-4-31b-it (small) / openai:gemma-4-31b-it (large)

A sample of the bench (hosted at generativelanguage.googleapis.com). Synthetic data. Compare with the stand-in in docs/test-reports.

| Check | Result |
|---|---|
| Triage, clean mail (18) | category 100.0%, destination 100.0% |
| Triage, hard mail (12) | category 100.0%, destination 100.0% |
| Triage, english mail (9) | category 100.0%, destination 100.0% |
| Triage failures | 21 |
| Seconds per mail | 36.6 |
| Proposals written | 8 of 10, 0 flagged by the checks, 49.5 s each |
| Complaint replies | 1 of 3, money promises: 0 |
| Partner offers in PDF read right | 3 of 3 |
| Model calls | 84 to the model, 25 failed, 0 fell back to the stand-in |
| Speed | 2.6 tokens per second |


## Errors

- triage m0085: RuntimeError: All models failed for triage: status_code: 500, model_name: gemma-4-31b-it, body: [{'error': {'code': 500, 'message': 'Internal error encountered.', 'status': '
- triage m0105: RuntimeError: All models failed for triage: status_code: 500, model_name: gemma-4-31b-it, body: [{'error': {'code': 500, 'message': 'Internal error encountered.', 'status': '
- triage m0082: RuntimeError: All models failed for triage: status_code: 500, model_name: gemma-4-31b-it, body: [{'error': {'code': 500, 'message': 'Internal error encountered.', 'status': '
- triage m0086: RuntimeError: All models failed for triage: status_code: 503, model_name: gemma-4-31b-it, body: [{'error': {'code': 503, 'message': 'This model is currently experiencing high
- triage m0056: RuntimeError: All models failed for triage: status_code: 500, model_name: gemma-4-31b-it, body: [{'error': {'code': 500, 'message': 'Internal error encountered.', 'status': '
- triage m0107: RuntimeError: All models failed for triage: status_code: 500, model_name: gemma-4-31b-it, body: [{'error': {'code': 500, 'message': 'Internal error encountered.', 'status': '
- triage m0067: RuntimeError: All models failed for triage: status_code: 500, model_name: gemma-4-31b-it, body: [{'error': {'code': 500, 'message': 'Internal error encountered.', 'status': '
- triage m0083: RuntimeError: All models failed for triage: status_code: 500, model_name: gemma-4-31b-it, body: [{'error': {'code': 500, 'message': 'Internal error encountered.', 'status': '
- triage m0101: RuntimeError: All models failed for triage: status_code: 500, model_name: gemma-4-31b-it, body: [{'error': {'code': 500, 'message': 'Internal error encountered.', 'status': '
- triage m0088: RuntimeError: All models failed for triage: status_code: 500, model_name: gemma-4-31b-it, body: [{'error': {'code': 500, 'message': 'Internal error encountered.', 'status': '
- triage m0021: RuntimeError: All models failed for triage: status_code: 503, model_name: gemma-4-31b-it, body: [{'error': {'code': 503, 'message': 'This model is currently experiencing high
- triage m0077: RuntimeError: All models failed for triage: status_code: 500, model_name: gemma-4-31b-it, body: [{'error': {'code': 500, 'message': 'Internal error encountered.', 'status': '
- triage m0110: RuntimeError: All models failed for triage: status_code: 503, model_name: gemma-4-31b-it, body: [{'error': {'code': 503, 'message': 'This model is currently experiencing high
- triage m0143: RuntimeError: All models failed for triage: status_code: 503, model_name: gemma-4-31b-it, body: [{'error': {'code': 503, 'message': 'This model is currently experiencing high
- triage m0133: RuntimeError: All models failed for triage: status_code: 500, model_name: gemma-4-31b-it, body: [{'error': {'code': 500, 'message': 'Internal error encountered.', 'status': '

## Proposal r008 (calculated price 8510.0 euro)
Checks: no problems

```
Beste Daan,

Wat een heerlijk vooruitzicht om met het kind van 3 jaar naar Sri Lanka te gaan!

Ik heb een route op maat gemaakt met een rustig tempo.

Negombo (1 nacht): jullie slapen in Lagoon Edge Hotel. Een aanrader: de vismarkt in de ochtend.
Sigiriya (5 nachten): jullie slapen in Sigiriya Jungle Lodge. Een aanrader: de leeuwenrots beklimmen en een jeep safari in Minneriya.
Ella (5 nachten): jullie slapen in Ella Tea Estate Cottage. Een aanrader: de treinrit door de theeplantages en Little Adams Peak.
Yala (4 nachten): jullie slapen in Yala Safari Tents. Een aanrader: een safari in Yala.
Mirissa (7 nachten): jullie slapen in Mirissa Palm Beach Resort. Een aanrader: surfles voor kinderen.

In augustus is het vaak regenachtig aan de zuidwestkust, dit checken we nog.

De indicatie voor de prijs is € 8.510. We checken nog enkele details.

Laat ons weten wat jullie ervan vinden.

Hartelijke groet,
Tessa Boer
```

## Proposal r017 (calculated price 6870.0 euro)
Checks: no problems

```
Beste Lotte,

Wat een mooi plan: Japan met het kind van 4 jaar.

Tokio (4 nachten): jullie slapen in Asakusa Family Ryokan. Leuk om te doen is het Ghibli museum (vooraf reserveren) en het Teamlab digitaal museum.

Osaka (12 nachten): jullie slapen in Osaka Bay Family Hotel. Hier kunnen jullie het Aquarium Kaiyukan bezoeken en streetfood proberen in Dotonbori.

Het is september, dus tyfoons kunnen voorkomen. Dit checken we nog.

De prijs is een indicatie van € 6.870.

Laat ons weten wat jullie ervan vinden.

Hartelijke groet,
Bram Hofman
```

## Proposal r018 (calculated price 10080.0 euro)
Checks: no problems

```
Beste Wouter,

Wat een heerlijk vooruitzicht om met de kinderen van 4 en 11 naar Vietnam te gaan!

Hanoi (3 nachten): jullie slapen in Old Quarter Lantern Hotel. Een aanrader: streetfood tour op de fiets en het waterpoppentheater. Dit checken we nog.
Ninh Binh (3 nachten): jullie slapen in Tam Coc Rice Field Homestay. Een aanrader: bootje door Trang An en fietsen langs de rijstvelden.
Halong Bay (3 nachten): jullie slapen in Bai Tu Long Family Junk. Een aanrader: kajakken in de baai en een grotbezoek.
Halong Bay (3 nachten): jullie slapen in Bai Tu Long Family Junk. Een aanrader: kajakken in de baai en een grotbezoek.
Hoi An (6 nachten): jullie slapen in Hoi An Garden Villas. Een aanrader: lantaarns maken en een kookles met marktbezoek.
Ho Chi Minhstad (4 nachten): jullie slapen in Saigon Courtyard Hotel. Een aanrader: mekong delta dagtocht.

De beste reistijd is maart tot en met mei en september tot en met november.

De prijs is een indicatie van € 10.080.

Laat ons weten wat jullie ervan vinden.

Hartelijke groet,
Niels Dijkstra
```

## Complaint reply to m0085

```
Beste Eva,

Bedankt voor jullie bericht. Het spijt ons dat jullie niet tevreden zijn over het hotel. De kamer was volgens jullie vies en klein.

We gaan dit uitzoeken met onze partner ter plaatse. Jullie horen binnen drie werkdagen van ons.

Hartelijke groet,

Travelnauts
```

