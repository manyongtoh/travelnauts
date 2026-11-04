# Two weeks of simulated operation

Database: postgres. Stand-in model. Clock fast-forwarded.

| Day | Date | Jobs run | Failed (total) | Queue at night | Untriaged | Triaged twice | Drafts waiting | Log rows | Audit chain | Alerts raised | What happened |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Mon 2026-11-09 | 276 | 0 | 0 | 0 | 0 | 14 | 1810 | ok | none |  |
| 2 | Tue 2026-11-10 | 133 | 0 | 0 | 0 | 0 | 3 | 2438 | ok | none |  |
| 3 | Wed 2026-11-11 | 149 | 0 | 0 | 0 | 0 | 12 | 3154 | ok | none | worker died holding 1 jobs at 09:00; jobs still stuck after 5 min: 1; jobs stuck after 20 min: 0 |
| 4 | Thu 2026-11-12 | 383 | 0 | 0 | 0 | 0 | 18 | 3938 | ok | travelspirit (warning) | TravelSpirit down 09:30 to 12:00; jobs failed while travelspirit down: 0; jobs waiting for travelspirit: 2; travelspirit alert: critical |
| 5 | Fri 2026-11-13 | 179 | 0 | 0 | 0 | 0 | 12 | 4781 | ok | model_errors (warning) | model down 09:00 to 12:00 (fallback for the first hour only); admin retried 0 failed jobs at 12:00; failed jobs with fallback: 0; failed or waiting without fallback: 24 |
| 6 | Sat 2026-11-14 | 32 | 0 | 0 | 0 | 0 | 51 | 4975 | ok | none |  |
| 7 | Sun 2026-11-15 | 13 | 0 | 0 | 0 | 0 | 71 | 5053 | ok | none | database restarted at 11:00; ready after restart: 200 |
| 8 | Mon 2026-11-16 | 91 | 0 | 0 | 0 | 0 | 16 | 5619 | ok | none |  |
| 9 | Tue 2026-11-17 | 225 | 0 | 0 | 0 | 0 | 32 | 4305 | ok | budget (critical) | daily model budget reached at 10:00, raised again at 10:30; jobs waiting for budget: 73; jobs failed on budget: 0 |
| 10 | Wed 2026-11-18 | 152 | 0 | 0 | 0 | 0 | 27 | 4512 | ok | none |  |
| 11 | Thu 2026-11-19 | 138 | 0 | 0 | 0 | 0 | 21 | 5123 | ok | ownerless (warning) | Sanne de Vries left; access removed; reassign list given to admin: 9; open requests of leaver: 0; leaver requests flagged by team insight: 7 |
| 12 | Fri 2026-11-20 | 157 | 0 | 0 | 0 | 0 | 22 | 4724 | ok | none | team lead reassigned 7 of 7 requests |
| 13 | Sat 2026-11-21 | 25 | 0 | 0 | 0 | 0 | 54 | 4521 | ok | none | note beste-reistijd-costa-rica.md (approved) changed in the vault; changed note status after reindex: approved, change waiting: True; changed note findable by agents: True |
| 14 | Sun 2026-11-22 | 4 | 0 | 0 | 0 | 0 | 55 | 4546 | ok | none |  |
