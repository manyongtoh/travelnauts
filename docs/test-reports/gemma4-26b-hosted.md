# Gemma 4 26B hosted: the free tier cannot test it

Run 42078373405, 5 November 2026, `gemma-4-26b-a4b-it` on Google AI Studio's free tier, alone on the key,
30 mails and 6 proposals asked, synthetic data. Cancelled after 1 hour 55 minutes without a result.

| | 26B, first run (shared key) | 26B, this run (alone) | 31B, second run (shared key) |
|---|---|---|---|
| Calls answered (HTTP 200) | the rest of 121 | 36 of 81 (44%) | 74 of 83 (89%) |
| Calls failed on Google's side (HTTP 500) | 54 of 121 | 45 of 81 (56%) | 9 of 83 |
| Calls that hung to the 120 second timeout | many | 7 | few |
| Report produced | no, cancelled after 3 hours | no, cancelled after 1 h 55 | yes |

The first call already failed at 17:50, before any load, and failures went on in bursts until the cancel.
Retries (3 and 9 seconds) did not help: a 26B request on the free tier fails more often than it succeeds,
so most mails used up their retries and the check never reached the proposals.

## What this says

- Nothing about 26B's quality. Too few answers came back to score triage or writing.
- The free tier serves 26B far worse than 31B. That is a property of Google's free service, not of the model:
  26B is a mixture-of-experts model with about 4B active parameters, and on a GPU of its own it should be
  faster and cheaper than 31B.
- For the pilot, 31B is the only Gemma 4 model with measured results: 100% category and destination on
  every answered mail, and proposals that pass every check.

## Next step

Test 26B where the pilot would run it: one GPU in the client's own Azure (see the cost estimate in the client
repo), with the same command, so speed and quality are measured without a shared free service in between:

    brain modelcheck --mails 60 --proposals 10 --complaints 3 --replies 4
