# Gemma 4 31B hosted, second run (with the fixes from the first)

Run 42048278929, 5 November 2026, `gemma-4-31b-it` on Google AI Studio's free tier, 60 mails and 10 proposals,
synthetic data. It ran at the same time as a 26B run on the same key.

| Check | First 31B run | This run |
|---|---|---|
| Triage category, clean / hard / English | 100% / 100% / 100% | 100% / 100% / 100% (53 answered) |
| Destination | 100% everywhere | 100% everywhere |
| Proposals passing every check | 8 of 8 written (10 asked) | 9 of 9 written (10 asked) |
| Calls failed on Google's side | 25 of 84 | 9 of 83 (busy provider now retried) |
| Repeated stop in a proposal | once (Halong Bay twice) | none in 9 proposals; a repeat is now flagged |
| Complaint reply promising a number of days | "binnen drie werkdagen" | none: "We komen hier zo snel mogelijk op terug" |
| "Dit checken we nog" after lines | several | still after some lines, next to notes past their review date |
| Seconds per mail / per proposal | 37 / 50 | 74 / 90 (retries, and a shared key) |

## What this says

- The fixes held: no invented promises, no repeated stops, the right closing.
- "Dit checken we nog" now sits where the knowledge is past its review date (typhoons in September, a street food
  tour). That is partly right. On real notes, with real review dates, it should appear far less; check again then.
- The free tier stays unreliable and slow when shared. It says nothing about the pilot, where Gemma runs in
  Travelnauts' own Azure.

---

# Model check: openai:gemma-4-31b-it (small) / openai:gemma-4-31b-it (large)

A sample of the bench (hosted at generativelanguage.googleapis.com). Synthetic data. Compare with the stand-in in docs/test-reports.

| Check | Result |
|---|---|
| Triage, clean mail (25) | category 100.0%, destination 100.0% |
| Triage, hard mail (15) | category 100.0%, destination 100.0% |
| Triage, english mail (13) | category 100.0%, destination 100.0% |
| Triage failures | 7 |
| Seconds per mail | 73.5 |
| Proposals written | 9 of 10, 0 flagged by the checks, 90.1 s each |
| Complaint replies | 2 of 3, money promises: 0 |
| Partner offers in PDF read right | 3 of 3 |
| Model calls | 83 to the model, 9 failed, 0 fell back to the stand-in |
| Speed | 1.5 tokens per second |


## Errors

- triage m0085: RuntimeError: All models failed for triage: status_code: 500, model_name: gemma-4-31b-it, body: [{'error': {'code': 500, 'message': 'Internal error encountered.', 'status': '
- triage m0056: RuntimeError: All models failed for triage: status_code: 500, model_name: gemma-4-31b-it, body: [{'error': {'code': 500, 'message': 'Internal error encountered.', 'status': '
- triage m0087: RuntimeError: All models failed for triage: status_code: 503, model_name: gemma-4-31b-it, body: [{'error': {'code': 503, 'message': 'This model is currently experiencing high
- triage m0089: RuntimeError: All models failed for triage: status_code: 503, model_name: gemma-4-31b-it, body: [{'error': {'code': 503, 'message': 'This model is currently experiencing high
- triage m0088: RuntimeError: All models failed for triage: status_code: 500, model_name: gemma-4-31b-it, body: [{'error': {'code': 500, 'message': 'Internal error encountered.', 'status': '
- triage m0159: RuntimeError: All models failed for triage: status_code: 500, model_name: gemma-4-31b-it, body: [{'error': {'code': 500, 'message': 'Internal error encountered.', 'status': '
- triage m0148: RuntimeError: All models failed for triage: status_code: 500, model_name: gemma-4-31b-it, body: [{'error': {'code': 500, 'message': 'Internal error encountered.', 'status': '
- proposal r008: RuntimeError: All models failed for proposal: status_code: 500, model_name: gemma-4-31b-it, body: [{'error': {'code': 500, 'message': 'Internal error encountered.', 'status':
- complaint m0086: RuntimeError: All models failed for complaint_reply: status_code: 500, model_name: gemma-4-31b-it, body: [{'error': {'code': 500, 'message': 'Internal error encountered.', 's

## Proposal r012 (calculated price 15420.0 euro)
Checks: no problems

```
Beste Noor,

Wat een heerlijk vooruitzicht om met de kinderen van 6, 6 en 13 naar Vietnam te gaan!

Hanoi (3 nachten): jullie slapen in Old Quarter Lantern Hotel. Een aanrader: streetfood tour op de fiets en het waterpoppentheater. Dit checken we nog.

Ninh Binh (3 nachten): jullie slapen in Tam Coc Rice Field Homestay. Een aanrader: bootje door Trang An en fietsen langs de rijstvelden.

Halong Bay (3 nachten): jullie slapen in Bai Tu Long Family Junk. Een aanrader: kajakken in de baai en een grotbezoek.

Hoi An (6 nachten): jullie slapen in Hoi An Garden Villas. Een aanrader: lantaarns maken en een kookles met marktbezoek.

Ho Chi Minhstad (4 nachten): jullie slapen in Saigon Courtyard Hotel. Een aanrader: mekong delta dagtocht.

September is een goede reistijd voor Vietnam.

De indicatie voor de prijs is € 15.420.

Laat ons weten wat jullie ervan vinden. We kunnen de route samen aanpassen.

Hartelijke groet,

Lieke Jansen
```

## Proposal r015 (calculated price 5790.0 euro)
Checks: no problems

```
Beste Olivier,

Wat een heerlijk vooruitzicht om met het kind van 2 jaar naar Costa Rica te gaan!

Jullie slapen 1 nacht in San Jose in het Escazu Garden Hotel, waar jullie een koffietour kunnen doen.
In Tortuguero verblijven jullie 6 nachten in de Tortuguero Canal Lodge en gaan kanoen door de kanalen.
In Manuel Antonio slapen jullie 9 nachten in de Manuel Antonio Jungle Villas en bezoeken jullie het nationaal park met gids.

De beste reistijd is december tot en met april.

De indicatie voor de prijs is € 5.790, we checken nog.

Laat ons weten wat jullie ervan vinden.

Hartelijke groet,
Joost Haan
```

## Proposal r017 (calculated price 6870.0 euro)
Checks: no problems

```
Beste Lotte,

Wat een mooi plan om met het kind van 4 naar Japan te gaan!

Tokio (4 nachten): jullie slapen in Asakusa Family Ryokan. Leuk om te bezoeken is het Ghibli museum (vooraf reserveren) en het Teamlab digitaal museum.

Osaka (12 nachten): jullie slapen in Osaka Bay Family Hotel. Hier kunnen jullie het Aquarium Kaiyukan bezoeken en streetfood proberen in Dotonbori.

Het is september, dus tyfoons kunnen voorkomen. Dit checken we nog.

De indicatie voor de prijs is € 6.870.

Laat ons weten wat jullie ervan vinden.

Hartelijke groet,
Bram Hofman
```

## Complaint reply to m0085

```
Beste Eva,

Bedankt voor jullie bericht. Het spijt ons dat jullie niet tevreden waren over het hotel. We vinden het vervelend dat de kamer vies en klein was.

We gaan dit uitzoeken met onze partner ter plaatse. We komen hier zo snel mogelijk op terug.

Hartelijke groet,

Travelnauts
```

## Complaint reply to m0087

```
Beste Vera,

Bedankt voor jullie bericht. Het spijt ons dat jullie niet tevreden waren over de hotelkamer. We gaan dit uitzoeken met onze partner ter plaatse.

We komen hier zo snel mogelijk op terug.

Hartelijke groet,

Travelnauts
```

