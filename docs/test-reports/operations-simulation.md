# Two weeks of simulated operation

Database: postgres. Stand-in model. Clock fast-forwarded.

| Day | Date | Jobs run | Failed (total) | Queue at night | Untriaged | Triaged twice | Drafts waiting | Log rows | Audit chain | Alerts raised | What happened |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Mon 2026-11-09 | 274 | 0 | 0 | 0 | 0 | 14 | 1806 | ok | none |  |
| 2 | Tue 2026-11-10 | 132 | 0 | 0 | 0 | 0 | 2 | 2427 | ok | none |  |
| 3 | Wed 2026-11-11 | 148 | 0 | 0 | 0 | 0 | 11 | 3134 | ok | none | worker died holding 1 jobs at 09:00; jobs still stuck after 5 min: 1; jobs stuck after 20 min: 0 |
| 4 | Thu 2026-11-12 | 124 | 0 | 0 | 0 | 0 | 9 | 3780 | ok | none |  |
| 5 | Fri 2026-11-13 | 181 | 0 | 0 | 0 | 0 | 8 | 4660 | ok | model_errors (warning) | model down 09:00 to 12:00 (fallback for the first hour only); admin retried 0 failed jobs at 12:00; failed jobs with fallback: 0; failed or waiting without fallback: 13 |
| 6 | Sat 2026-11-14 | 23 | 0 | 0 | 0 | 0 | 40 | 4810 | ok | none |  |
| 7 | Sun 2026-11-15 | 13 | 0 | 0 | 0 | 0 | 65 | 4903 | ok | none | database restarted at 11:00; ready after restart: 200 |
| 8 | Mon 2026-11-16 | 134 | 0 | 0 | 0 | 0 | 47 | 3946 | ok | none |  |
| 9 | Tue 2026-11-17 | 153 | 0 | 0 | 0 | 0 | 15 | 4627 | ok | budget (critical) | daily model budget reached at 10:00, raised again at 10:30; jobs waiting for budget: 41; jobs failed on budget: 0 |
| 10 | Wed 2026-11-18 | 119 | 0 | 0 | 0 | 0 | 6 | 4781 | ok | none |  |
| 11 | Thu 2026-11-19 | 129 | 0 | 0 | 0 | 0 | 5 | 4437 | ok | ownerless (warning) | Sanne de Vries left; access removed; reassign list given to admin: 10; open requests of leaver: 1; leaver requests flagged by team insight: 8 |
| 12 | Fri 2026-11-20 | 127 | 0 | 0 | 0 | 0 | 6 | 4553 | ok | none | team lead reassigned 8 of 8 requests |
| 13 | Sat 2026-11-21 | 29 | 0 | 0 | 0 | 0 | 36 | 4218 | ok | none | note beste-reistijd-costa-rica.md (approved) changed in the vault; changed note status after reindex: approved, change waiting: True; changed note findable by agents: True |
| 14 | Sun 2026-11-22 | 4 | 0 | 0 | 0 | 0 | 37 | 4241 | ok | none |  |
