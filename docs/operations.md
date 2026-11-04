# Running at scale, and what keeps it robust

## How it scales

| Part | How it grows | Limit today |
|---|---|---|
| API and screens | Stateless: any number of replicas behind Container Apps, scaled on concurrent requests (2 to 10 in live) | Postgres connections: pool of 10 plus 20 overflow per replica |
| Agents | Work arrives as jobs in Postgres. KEDA starts extra worker replicas when jobs wait (one per 20 queued jobs, up to 10). Each job is claimed with a row lock, so workers never take the same job | Model throughput and budget, not the platform |
| Scheduler | One scheduled job every 5 minutes; safe if two run at once (compare and set on the last run time) | |
| Database | Azure Database for PostgreSQL, indexes on every hot column, paging on lists, 30 days retention on logs | One server; read replicas are the next step if needed |
| Knowledge search | Index per replica in memory, rebuilt when knowledge changes; pgvector or Azure AI Search when the vault grows past a few thousand chunks | |

Load test (`brain loadtest`, stand-in model, local Postgres 16): 8 workers handled 1,613 mails in 44 seconds,
about 2,000 a minute. Every mail was triaged exactly once, no job ran twice, all request numbers were unique,
and 40 approvals by different people at the same moment left the audit chain intact. Travelnauts gets about
300 mails a day. With a real model, the model's response time sets the pace (a few seconds per step), and the
parallel workers are what keep the queue short.

## What keeps it robust

| Risk | What the code does | Test |
|---|---|---|
| A name reaches the model | Names from the dossier, first names in the text and "Name (8)" patterns are masked; if a known name is still there, the model call is refused | `test_children_names_never_reach_the_model`, `test_model_call_refused_if_a_known_name_slips_through` |
| An agent fails halfway | One run is one transaction: on failure everything it wrote is rolled back; only the run record and model costs stay | `test_failed_agent_leaves_nothing_half_done` |
| A job runs twice | Claimed with a guarded update (and `SKIP LOCKED` on Postgres); agents check whether the work was already done | `test_a_job_is_claimed_by_one_worker_only`, `test_jobs_are_safe_to_repeat`, `test_parallel_workers_never_double_process` |
| A worker dies | Jobs carry a 10 minute lease; expired leases go back in the queue | `test_dead_workers_jobs_come_back` |
| Two schedulers | Compare and set on the last run time | `test_two_schedulers_queue_each_job_once` |
| The audit chain forks | Unique link to the previous entry; concurrent writers retry on the new head | `test_audit_chain_cannot_fork`, load test |
| Duplicate request numbers | Atomic counter in the database | `test_request_numbers_stay_unique` |
| The model returns rubbish | Typed output is validated; invalid answers go back to the model twice | `test_garbage_output_is_retried_until_valid` |
| The model hangs or is down | 60 second timeout, fallback model, and a circuit breaker after 5 failures in 5 minutes | `test_timeouts_fall_back_and_a_failing_model_is_skipped` |
| Budget runs away | Daily cap per environment, checked before every call | `test_budget_cap_stops_agents` |
| Too much traffic | 1 MB request limit; 30 agent actions per person per minute (per replica) | |
| Errors shown to users | Unhandled errors become a short message; the details go to the log | |
| Schema changes | Alembic migrations; CI checks they match the models on Postgres | CI `postgres` job |
| SQLite hides bugs | Foreign keys are enforced in SQLite too, and the full test suite runs on Postgres in CI | 95 tests on both |

## Commands

```bash
brain migrate                 # bring the schema up to date (pilot and live)
brain worker --once           # scheduler tick and one pass (the 5 minute job)
brain worker --drain          # work the queue until empty (the scaled workers)
brain loadtest --mails 600 --workers 4
curl /healthz  /readyz        # liveness and readiness probes
```

## Not done yet

- The rate limit is per replica, in memory. With many replicas, move it to Azure API Management or Redis.
- Search by meaning uses local embeddings; with a large vault, move vectors to pgvector or Azure AI Search.
- Microsoft sign-in in the screens is written (MSAL) but needs Travelnauts' Entra app registrations to try.
- Backups and restore drills are Azure settings; write the restore runbook with Travelnauts' administrator.
