# Test report: daily operation and security

Date: 4 November 2026. Sandbox with synthetic data and the stand-in model. Every test below runs again in CI on
each change, so this report can be reproduced with the commands at the bottom.

## Summary

| Area | Result |
|---|---|
| Test suite on SQLite | 116 passed |
| Test suite on Postgres 16 | 115 passed, 1 skipped (a SQLite-only schema test) |
| Quality bench (`brain bench --gate`) | all 11 limits met |
| Security tests | 17 passed (16 API tests, 1 browser test on 7 screens) |
| Dependency scan (pip-audit) | no known vulnerabilities |
| Code scan (bandit, medium and high) | no findings |
| Two weeks of simulated operation on Postgres, with 6 incidents | 0 failed jobs, 0 lost or doubled mails, audit chain ok every day |
| Backup and restore drill | passed: counts and audit chain identical, newest migration runs on the restored data |
| Load test, 8 workers | 1,613 mails, none handled twice, none left |

## What the tests found, and what was fixed

Ten problems surfaced. All are fixed and each now has a test, so they cannot come back unnoticed.

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

| Day | Incident | Outcome |
|---|---|---|
| 3 | A worker dies holding a job | Picked up by another worker within 20 minutes. |
| 5 | The model is down for three hours | With the fallback: 0 failures. Without: 13 jobs waited, all done after retry. |
| 7 | The database restarts | Ready again straight away; nothing half saved. |
| 9 | The daily model budget runs out | 39 jobs waited, 0 failed, all done when the budget was raised. |
| 11 | A specialist leaves | Access gone at once; 11 requests listed to reassign. |
| 13 | An approved note is edited | Agents keep the approved text; the edit waits for approval. |

Across all 14 days: 0 failed jobs, the queue empty every night, no mail left untriaged or triaged twice, the
audit chain intact every day, and the log size stable at about 3,500 rows with 7-day retention.

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

- **The real model.** All of this ran with the stand-in model. Quality and cost with the real model are measured
  in the first pilot week with the same bench.
- **Real Azure.** Point-in-time restore, failover, Entra sign-in and KEDA scaling are configured but only
  testable in Travelnauts' subscription. Repeat the backup drill there before live.
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
