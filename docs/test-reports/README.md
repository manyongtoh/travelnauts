# Test report: daily operation and security

Date: 4 November 2026. Sandbox with synthetic data and the stand-in model. Every test below runs again in CI on
each change, so this report can be reproduced with the commands at the bottom.

## Summary

| Area | Result |
|---|---|
| Test suite on SQLite | 174 passed |
| Test suite on Postgres 16 | 173 passed, 1 skipped (a SQLite-only schema test) |
| Quality bench (`brain bench --gate`) | all 11 limits met |
| Security tests | 17 passed (16 API tests, 1 browser test on 7 screens) |
| Dependency scan (pip-audit) | no known vulnerabilities |
| Code scan (bandit, medium and high) | no findings |
| Two weeks of simulated operation on Postgres, with 6 incidents | 0 failed jobs, 0 lost or doubled mails, audit chain ok every day |
| One family's whole journey, first mail to next trip | every hand-off happens without anyone remembering a step |
| The back office day for one trip, with partner mail written like real mail | replies read and matched, chasing only the silent, invoices checked |
| Alerts during the two weeks | the right alert on each incident that needs a person, none on incidents that heal themselves, none on quiet days |
| Backup and restore drill | passed: counts and audit chain identical, newest migration runs on the restored data |
| Load test, 8 workers | 1,613 mails, none handled twice, none left |

## What the tests found, and what was fixed

Forty-one problems surfaced. All are fixed and each now has a test, so they cannot come back unnoticed.

| # | Found by | Problem | Fix |
|---|---|---|---|
| 1 | Security tests | Browser security headers were missing (clickjacking, sniffing, referrer leaks). | Strict headers on every answer; API answers are never cached. |
| 2 | Security tests | The API documentation pages were open in every environment. | Only in the test environment. |
| 3 | Security tests | An instruction hidden inside a partner's PDF was not checked; only the mail text was. | Attachment text is scanned too; an unreadable attachment is flagged for a person. |
| 4 | Security tests on Postgres | A NUL character in an address or form gave a server error (SQLite accepted it, Postgres does not). | Refused at the door with a clear message. |
| 5 | Dependency scan | The PDF library had known vulnerabilities. | Upgraded to a fixed version. |
| 6 | Simulation | On Postgres the scheduler could not claim its turn, so nightly jobs did not start. | Fixed the comparison; test added that the scheduler runs again after its interval. |
| 7 | Simulation | When the daily model budget ran out, jobs failed for good. | They now wait 15 minutes and try again, without using up their retries. |
| 8 | Simulation | Open requests of someone who left had no owner and nobody was told. | Admin sees the count when deactivating; team leads get a reassign list. |
| 9 | Simulation | Editing an approved knowledge note took it offline for agents until re-approval. | Agents keep the approved text; the edit waits for approval as a change. |
| 11 | Alert simulation | A daily budget of 0 did not count as reached, so the budget alert stayed silent. | A cap of 0 now counts as reached. |
| 12 | Alert simulation | "Agent failing often" fired during the model outage and the budget stop, repeating the real cause. | Budget waits and pauses are not counted; with a model alert open it is not raised. |
| 13 | Code scan | The alert webhook would accept any address scheme, such as file:. | Only https (and local http for tests). |
| 14 | Journey | Real mail carries an address, not a family. Nothing matched it, so a first enquiry created no request, and changes and complaints from real mail were never linked. | Senders are matched to families by address; a first enquiry opens a new relation, named from the sign-off, for the specialist to check. |
| 15 | Journey | A new request waited until the specialist asked for a proposal. | The proposal is drafted right after triage. |
| 16 | Journey | A proposal for a family without a known name crashed. | A neutral greeting when no name is known. |
| 17 | Journey | A "have you decided?" follow-up stayed ready to send after the family booked or wrote back. | It is withdrawn, and approving it is blocked. |
| 18 | Journey | After booking nothing happened by itself: extras and roadbook waited for someone to remember. | Extras right after booking; the roadbook three weeks out, once partners confirmed. |
| 19 | Journey | Flight rows with other field names crashed the flight watch and the roadbook. | Common field names are read; incomplete rows are reported by the booking check. |
| 20 | Journey | A complaint was linked to any booked trip of the family. | To the trip that started most recently. |
| 21 | Journey | Families who had travelled never got a next-trip idea, and in pilot and live the job did nothing at all. | Two months after coming home, at most once a year, on real data too. |
| 22 | Parallel workers on Postgres | Two workers caching the same tool answer at once undid one agent run. | The cache write is a single upsert. |
| 23 | Simulation | On its first run the booking check drafted extras and roadbooks for every booked trip, including trips long past. | Only trips still to come; extras only while more than three weeks remain. |
| 24 | Sign-off names | On real-looking mail the name rule got 25 of 89 right and 12 wrong; on replies it named the family after our own specialist from the quoted history. | Quoted history, footers and company signatures are read like a person would; 89 of 89 right, 0 wrong; on 24 unseen cases 16 right and 0 wrong before tuning. |
| 25 | Addresses | One address shared by two families was matched to whichever came first. | Never guessed: a person picks, with suggestions. |
| 26 | Addresses | A second parent or a new address could not be linked, so their mail waited for ever. | Team lead list with suggested families; one click links the mail and remembers the address. |
| 27 | Hostile model | A follow-up, extras or next-trip mail promising money, inventing a price or saying "booked" could be approved by a specialist. | Every customer mail is checked: prices from the calculation, money only with the team lead, no "booked" unless it is. |
| 28 | TravelSpirit faults | Every job failed for good after about 6 minutes of TravelSpirit being down. | Jobs wait up to 12 hours without using retries; it is not hammered; alert after an hour. |
| 29 | TravelSpirit faults | Failed and refused tool calls disappeared from the log when the work was undone. | They are written back after the rollback. |
| 30 | Availability | A proposal could go out while every partner was still checking, without saying so. | One setting: add "onder voorbehoud", or wait for all; a partner that said no always stops it. |
| 31 | Back office journey | Real partner mail carries an address, not a partner: no partner reply was ever read. | Partners matched by address, or by their own domain when only one partner uses it. |
| 32 | Back office journey | A partner reply without our reference was taken for a family question. | Mail from a known partner is always a partner reply. |
| 33 | Back office journey | A reply that could not be matched to a request was marked done and never seen again. | It waits on the board under "Partner mail to match". |
| 34 | Back office journey | "We will come back to you" counted as available, and the board showed it as "not available". | It is "Answer needs reading"; one click decides. |
| 35 | Back office journey | Partners that had answered were chased anyway. | Fixed by 31: only silent partners are chased. |
| 36 | Back office journey | A partner's "no" left the specialist with nothing. | Alternatives are drafted for the specialist straight away. |
| 37 | Back office journey | A partner silent after a reminder was never flagged. | Flagged on the board and in the booking file: phone them or choose another. |
| 38 | Back office journey | "EUR 1.240" was read as 1.24 euro, and the price check turned "1.240,50" into 124,050. | One euro reader for the whole brain; invoice amounts are cross-checked against the mail itself. |
| 39 | Back office journey | The same invoice sent twice was not caught. | Same number, or same partner, trip and amount: "Duplicate", resolving it needs a reason. |
| 40 | Back office journey | With several partners on a trip, an invoice could be checked against another partner's offer; an invoice for a trip that is not booked was not flagged. | Only a sure match; "Trip not booked" when it is not. |
| 41 | Back office journey | A hotel that said no kept the booking file incomplete, even after another hotel was chosen. | Only partners on the latest route count. |
| 10 | Backup drill | `brain migrate` failed on a database that was built without migrations. | It now adopts such a database only if it matches the code exactly, and otherwise stops without changing anything. |

Two code scan warnings (a fixed temporary folder in the simulation, a table name in a query) were low risk in
context but were fixed rather than suppressed.

## Security tests

Every test signs in as a real role from the synthetic team and tries something it should not be able to do.

| Test | What it proves |
|---|---|
| every API route needs sign-in | No address answers without a signed-in user, checked for every route automatically. |
| unknown or removed users are refused | A user who left loses access at once. |
| specialists cannot reach each other's trips | Changing a request number in the address gives 403, not someone else's customer. |
| team leads stay in their team | A team lead for Asia cannot see Latin America. |
| roles cannot do each other's work | Back office cannot approve customer mail, specialists cannot approve partner mail, only content approves knowledge, nobody but the admin reaches the admin screens. |
| privilege escalation is blocked | Nobody can make themselves admin or create an admin. |
| knowledge is filtered by role | A note on margins is visible to back office, not to specialists. |
| admin needs break-glass for content | The administrator can run the system but must give a logged reason to read customer mail. |
| hostile input does not break or leak | SQL injection, path tricks, NUL characters and script tags are harmless. |
| file download cannot escape the folder | Roadbook and voucher downloads cannot reach other files. |
| big requests and floods are refused | Over 1 MB is refused; over 30 actions a minute per user is refused for that minute. |
| errors do not leak internals | A failing agent gives a plain message: no stack trace, path or password from the error. |
| security headers and no cross-site access | Headers present; other websites cannot call the API. |
| API docs are closed outside test | No documentation pages in pilot or live. |
| Entra rejects forged and expired tokens | Forged signature, expired, "alg none" and wrong-audience tokens are all refused. |
| injection hidden in a partner PDF is caught | The mail is flagged and no draft is made from it. |
| no script runs from stored text (browser) | Script payloads in family names, mails and knowledge notes stay text on all 7 screens. |

## Daily operation

Two simulated weeks on Postgres: 25 family mails a day plus partner replies, staff working twice a day, the
scheduler every hour and the night jobs at 02:00. One incident on six of the days. Full table:
[operations-simulation.md](operations-simulation.md).

| Day | Incident | Outcome | Alert raised |
|---|---|---|---|
| 3 | A worker dies holding a job | Picked up by another worker within 20 minutes. | none: it healed itself |
| 5 | The model is down for three hours | With the fallback: 0 failures. Without: jobs waited, all done after retry. | model errors (warning) |
| 7 | The database restarts | Ready again straight away; nothing half saved. | none from the brain; Azure watches /readyz |
| 9 | The daily model budget runs out | 42 jobs waited, 0 failed, all done when the budget was raised. | budget (critical) |
| 11 | A specialist leaves | Access gone at once; 12 requests listed to reassign. | requests without an owner (warning) |
| 12 | The team lead reassigns them | 12 of 12 reassigned. | the alert clears |
| 13 | An approved note is edited | Agents keep the approved text; the edit waits for approval. | none: nothing is wrong |

Across all 14 days: 0 failed jobs, the queue empty every night, no mail left untriaged or triaged twice, the
audit chain intact every day, and the log size stable at about 3,500 rows with 7-day retention.

## Security: a successful injection, or a model gone wrong

Detection rules catch all 30 attacks they were written for and none of the 8 innocent look-alikes, but only 2 of
8 attacks written afterwards. That is expected of rules. What protects Travelnauts is that a successful attack
can do nothing. `tests/security/test_hostile_model.py` swaps the model for a hostile one and shows:

| Guarantee | Result |
|---|---|
| The model only sees the family it works on | holds: no other family's name or address in anything it was shown |
| The model cannot call tools | holds: code calls the tools; the model only returns text and fields |
| Nothing is sent without a person approving | holds |
| A specialist cannot approve invented prices, money promises or "your booking is confirmed" | holds, after fix 27 |

Next layer: Azure AI Content Safety Prompt Shields, in the Azure test environment.

## One family's journey

`scripts/journey.py` (and `tests/test_journey.py`) follows one new family through the API, as each role would:

| When | Who | What happens |
|---|---|---|
| Mon 08:00 | family | first mail from an unknown address |
| Mon 08:00 | brain | new relation opened, named from the sign-off; request created and assigned; proposal drafted |
| Mon 09:00 | specialist | finds the proposal ready; asks partners for availability |
| Mon 10:00 | back office | approves the partner mails |
| Tue | specialist | sends the proposal |
| a week later | brain | drafts a follow-up after silence |
| booking | brain | withdraws the follow-up; drafts extras |
| 3 weeks out | brain | drafts the roadbook and vouchers once partners confirmed; watches the flight |
| after the trip | family, team lead | complaint from the same address reaches the team lead, linked to the trip |
| 4 months later | brain | next-trip idea |

## The back office day

`scripts/journey_backoffice.py` (and `tests/test_journey_backoffice.py`) follows one trip through the back office,
with partner mail written the way partners write: from reservations@ or info@, with or without our reference.

| When | What happens |
|---|---|
| Monday | specialist asks partners; back office approves the five request mails |
| Tuesday | a confirmation with "EUR 1.240" (read as 1,240 euro), a "fully booked" without reference (matched to the only open request of that hotel, alternatives drafted for the specialist), a "we will come back to you" (needs reading) |
| a week later | reminders only to the two silent partners |
| two weeks later | still silent after the reminder: flagged on the board and in the booking file |
| invoices | the confirmed partner's invoice matches; the same invoice again is a duplicate; the silent partner's invoice cannot be placed |

## Backup and restore

`scripts/backup_drill.sh` on the database after the two weeks:

```
1. verify source
2. backup                503K
3. restore to a new database
4. verify copy
5. compare               tables: 22, rows: 6821, differences: none
                         audit chain: 497 entries, ok: True, same head as source: True
6. newest migration      down one migration and up again: ok; schema matches the code
drill passed
```

Then one row in the audit log of the restored copy was changed by hand. `brain verify` reported "audit chain
broken at entry 201" and exited with an error, so tampering with a backup or the live database is detected.

## What this does not cover yet

- **The real model.** All of this ran with the stand-in model. A first Gemma 4 run (e4b, CPU only) is under way
  on a GitHub runner; its report will be added here as gemma4-e4b-cpu.md. Quality and cost with the real model are measured
  in the first pilot week with the same bench.
- **Real Azure.** Point-in-time restore, failover, Entra sign-in, KEDA scaling and the Azure Monitor alerts are
  configured but only testable in Travelnauts' subscription. CI compiles the templates on every change. Repeat the backup drill there before live.
- **An outside penetration test.** These tests check what we thought of. Before live, have an independent party
  test the pilot environment.
- **Real TravelSpirit.** Its behaviour under errors and load is simulated, not measured.
- **Real volumes.** The restore took seconds on 6,821 rows. Measure it on the pilot database.

## Reproduce

```
pytest -q                                              # all tests, SQLite
BRAIN_TEST_DATABASE_URL=postgresql+psycopg://... pytest -q   # all tests, Postgres
brain bench --gate
brain simulate --days 14                               # on Postgres
scripts/backup_drill.sh postgresql://...
pip-audit -r req.txt && bandit -q -r brain -ll
```

The daily and incident procedures are in [../runbook.md](../runbook.md).
