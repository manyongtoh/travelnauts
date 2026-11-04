# Two weeks of simulated operation

Database: postgres. Stand-in model. Clock fast-forwarded.

| Day | Date | Jobs run | Failed (total) | Queue at night | Untriaged | Triaged twice | Drafts waiting | Log rows | Audit chain | What happened |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Mon 2026-11-09 | 167 | 0 | 0 | 0 | 0 | 21 | 994 | ok |  |
| 2 | Tue 2026-11-10 | 91 | 0 | 0 | 0 | 0 | 16 | 1607 | ok |  |
| 3 | Wed 2026-11-11 | 79 | 0 | 0 | 0 | 0 | 12 | 2198 | ok | worker died holding 1 jobs at 09:00; jobs still stuck after 5 min: 1; jobs stuck after 20 min: 0 |
| 4 | Thu 2026-11-12 | 75 | 0 | 0 | 0 | 0 | 17 | 2763 | ok |  |
| 5 | Fri 2026-11-13 | 103 | 0 | 0 | 0 | 0 | 19 | 3427 | ok | model down 09:00 to 12:00 (fallback for the first hour only); admin retried 0 failed jobs at 12:00; failed jobs with fallback: 0; failed or waiting without fallback: 13 |
| 6 | Sat 2026-11-14 | 11 | 0 | 0 | 0 | 0 | 31 | 3476 | ok |  |
| 7 | Sun 2026-11-15 | 11 | 0 | 0 | 0 | 0 | 48 | 3546 | ok | database restarted at 11:00; ready after restart: 200 |
| 8 | Mon 2026-11-16 | 62 | 0 | 0 | 0 | 0 | 25 | 4158 | ok |  |
| 9 | Tue 2026-11-17 | 114 | 0 | 0 | 0 | 0 | 29 | 3604 | ok | daily model budget reached at 10:00, raised again at 10:30; jobs waiting for budget: 39; jobs failed on budget: 0 |
| 10 | Wed 2026-11-18 | 69 | 0 | 0 | 0 | 0 | 29 | 3623 | ok |  |
| 11 | Thu 2026-11-19 | 70 | 0 | 0 | 0 | 0 | 30 | 3692 | ok | Sanne de Vries left; access removed; reassign list given to admin: 11; open requests of leaver: 2; leaver requests flagged by team insight: 8 |
| 12 | Fri 2026-11-20 | 69 | 0 | 0 | 0 | 0 | 26 | 3784 | ok |  |
| 13 | Sat 2026-11-21 | 11 | 0 | 0 | 0 | 0 | 47 | 3508 | ok | note beste-reistijd-costa-rica.md (approved) changed in the vault; changed note status after reindex: approved, change waiting: True; changed note findable by agents: True |
| 14 | Sun 2026-11-22 | 3 | 0 | 0 | 0 | 0 | 47 | 3522 | ok |  |
