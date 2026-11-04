# Two weeks of simulated operation

Database: postgres. Stand-in model. Clock fast-forwarded.

| Day | Date | Jobs run | Failed (total) | Queue at night | Untriaged | Triaged twice | Drafts waiting | Log rows | Audit chain | Alerts raised | What happened |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Mon 2026-11-09 | 274 | 0 | 0 | 0 | 0 | 14 | 1806 | ok | none |  |
| 2 | Tue 2026-11-10 | 132 | 0 | 0 | 0 | 0 | 2 | 2426 | ok | none |  |
| 3 | Wed 2026-11-11 | 135 | 0 | 0 | 0 | 0 | 4 | 3078 | ok | none | worker died holding 1 jobs at 09:00; jobs still stuck after 5 min: 1; jobs stuck after 20 min: 0 |
| 4 | Thu 2026-11-12 | 459 | 0 | 0 | 0 | 0 | 16 | 3969 | ok | travelspirit (warning) | TravelSpirit down 09:30 to 12:00; jobs failed while travelspirit down: 0; jobs waiting for travelspirit: 2; travelspirit alert: critical |
| 5 | Fri 2026-11-13 | 189 | 0 | 0 | 0 | 0 | 8 | 4829 | ok | model_errors (warning) | model down 09:00 to 12:00 (fallback for the first hour only); admin retried 0 failed jobs at 12:00; failed jobs with fallback: 0; failed or waiting without fallback: 28 |
| 6 | Sat 2026-11-14 | 29 | 0 | 0 | 0 | 0 | 47 | 5015 | ok | none |  |
| 7 | Sun 2026-11-15 | 13 | 0 | 0 | 0 | 0 | 71 | 5105 | ok | none | database restarted at 11:00; ready after restart: 200 |
| 8 | Mon 2026-11-16 | 93 | 0 | 0 | 0 | 0 | 12 | 5680 | ok | none |  |
| 9 | Tue 2026-11-17 | 208 | 0 | 0 | 0 | 0 | 27 | 4248 | ok | budget (critical) | daily model budget reached at 10:00, raised again at 10:30; jobs waiting for budget: 67; jobs failed on budget: 0 |
| 10 | Wed 2026-11-18 | 115 | 0 | 0 | 0 | 0 | 7 | 4356 | ok | none |  |
| 11 | Thu 2026-11-19 | 125 | 0 | 0 | 0 | 0 | 6 | 5068 | ok | ownerless (warning) | Sanne de Vries left; access removed; reassign list given to admin: 11; open requests of leaver: 1; leaver requests flagged by team insight: 10 |
| 12 | Fri 2026-11-20 | 146 | 0 | 0 | 0 | 0 | 10 | 4480 | ok | none | team lead reassigned 10 of 10 requests |
| 13 | Sat 2026-11-21 | 29 | 0 | 0 | 0 | 0 | 45 | 4170 | ok | none | note beste-reistijd-costa-rica.md (approved) changed in the vault; changed note status after reindex: approved, change waiting: True; changed note findable by agents: True |
| 14 | Sun 2026-11-22 | 4 | 0 | 0 | 0 | 0 | 46 | 4193 | ok | none |  |
