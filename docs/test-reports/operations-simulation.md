# Two weeks of simulated operation

Database: postgres. Stand-in model. Clock fast-forwarded.

| Day | Date | Jobs run | Failed (total) | Queue at night | Untriaged | Triaged twice | Drafts waiting | Log rows | Audit chain | Alerts raised | What happened |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Mon 2026-11-09 | 291 | 0 | 0 | 0 | 0 | 14 | 1846 | ok | none |  |
| 2 | Tue 2026-11-10 | 139 | 0 | 0 | 0 | 0 | 8 | 2493 | ok | none |  |
| 3 | Wed 2026-11-11 | 137 | 0 | 0 | 0 | 0 | 6 | 3148 | ok | none | worker died holding 1 jobs at 09:00; jobs still stuck after 5 min: 1; jobs stuck after 20 min: 0 |
| 4 | Thu 2026-11-12 | 408 | 0 | 0 | 0 | 0 | 20 | 3987 | ok | travelspirit (warning) | TravelSpirit down 09:30 to 12:00; jobs failed while travelspirit down: 0; jobs waiting for travelspirit: 2; travelspirit alert: critical |
| 5 | Fri 2026-11-13 | 203 | 0 | 0 | 0 | 0 | 16 | 4886 | ok | model_errors (warning) | model down 09:00 to 12:00 (fallback for the first hour only); admin retried 0 failed jobs at 12:00; failed jobs with fallback: 0; failed or waiting without fallback: 27 |
| 6 | Sat 2026-11-14 | 32 | 0 | 0 | 0 | 0 | 57 | 5073 | ok | none |  |
| 7 | Sun 2026-11-15 | 17 | 0 | 0 | 0 | 0 | 80 | 5154 | ok | none | database restarted at 11:00; ready after restart: 200 |
| 8 | Mon 2026-11-16 | 139 | 0 | 0 | 0 | 0 | 65 | 4106 | ok | none |  |
| 9 | Tue 2026-11-17 | 144 | 0 | 0 | 0 | 0 | 18 | 4794 | ok | budget (critical) | daily model budget reached at 10:00, raised again at 10:30; jobs waiting for budget: 38; jobs failed on budget: 0 |
| 10 | Wed 2026-11-18 | 144 | 0 | 0 | 0 | 0 | 18 | 4980 | ok | none |  |
| 11 | Thu 2026-11-19 | 144 | 0 | 0 | 0 | 0 | 17 | 5089 | ok | ownerless (warning) | Sanne de Vries left; access removed; reassign list given to admin: 12; open requests of leaver: 0; leaver requests flagged by team insight: 11 |
| 12 | Fri 2026-11-20 | 177 | 0 | 0 | 0 | 0 | 27 | 4591 | ok | none | team lead reassigned 11 of 11 requests |
| 13 | Sat 2026-11-21 | 34 | 0 | 0 | 0 | 0 | 64 | 4373 | ok | none | note beste-reistijd-costa-rica.md (approved) changed in the vault; changed note status after reindex: approved, change waiting: True; changed note findable by agents: True |
| 14 | Sun 2026-11-22 | 4 | 0 | 0 | 0 | 0 | 65 | 4402 | ok | none |  |
