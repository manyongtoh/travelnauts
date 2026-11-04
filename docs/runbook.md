# Runbook: daily operation and incidents

For the administrator at Myt (myt-beheer) and, later, Travelnauts' own administrator. Every procedure below was
tested in the sandbox, either in the two-week simulation (`brain simulate`), the backup drill
(`scripts/backup_drill.sh`) or the test suite. The column "Tested in" says where.

## Every working morning (five minutes)

1. Open **Maintenance**. Check four things:
   - Queue at night was empty, and no job is in `failed`.
   - Every agent is green. A paused agent shows who paused it and why.
   - Model spend today is under the daily budget.
   - The audit chain says ok.
2. Open **Team lead > Insight** for each team: the list "Requests without an owner" should be empty.
3. Look at **Team lead > Gaps**: questions the knowledge desk could not answer. Give them to the owner of that
   knowledge, or close them.

The same checks from a terminal: `brain verify` (row counts, audit chain, schema version) and `GET /readyz`.

## Every month

- Run the backup drill against a fresh copy of the live backup: `scripts/backup_drill.sh <database url>`.
  It must end with `drill passed`. File the output in the security folder.
- Review the user list with Travelnauts: anyone who left must be inactive.
- Run `pip-audit` (CI does this on every change, but new vulnerabilities appear in old versions too).

## Incidents

Each incident lists what you see, what the system already does on its own, and what you do.

### The model provider is down or slow
- **You see:** agent runs fail or are slow, the router shows the fallback model in use.
- **The system:** switches to the fallback model; if that also fails, the circuit breaker opens and jobs wait.
  No mail is lost: it stays in the queue.
- **You do:** nothing while the fallback works. If both are down for more than an hour, tell the team leads that
  drafts are delayed. When it is back, **Retry** on each failed job in **Maintenance**.
- **Tested in:** simulation day 5 (0 failures with the fallback; 13 waiting without it, all recovered after retry).

### A worker stops or hangs
- **You see:** jobs with status `running` that are older than ten minutes.
- **The system:** every job has a ten-minute lease. The next worker takes over expired jobs automatically.
- **You do:** nothing, unless it keeps happening. Then look at the worker logs in Azure and restart the
  container app revision.
- **Tested in:** simulation day 3 (1 stuck job, picked up again within 20 minutes); load test with 8 workers
  (1,613 mails, none handled twice).

### The database restarts or fails over
- **You see:** a short burst of errors; `/readyz` answers 503 until the database is back.
- **The system:** Azure takes the container out of rotation while `/readyz` fails. Every agent run is one
  transaction, so nothing is half saved.
- **You do:** check `brain verify` afterwards. It must say ok.
- **Tested in:** simulation day 7 (ready again straight after the restart, audit chain ok).

### The daily model budget is reached
- **You see:** Maintenance shows the budget at 100%; jobs show `waiting for budget`.
- **The system:** stops calling the model and puts jobs back in the queue for 15 minutes, without using up their
  retries. Nothing fails.
- **You do:** decide with the GM whether to raise today's budget (**Maintenance > Model budget**) or let the jobs wait
  until tomorrow. Find out why: a mail loop or an unusual peak.
- **Tested in:** simulation day 9 (39 jobs waited, 0 failed, all done once the budget was raised).

### TravelSpirit is unreachable
- **You see:** tool calls to TravelSpirit fail in the agent log.
- **The system:** the agent run fails cleanly and the job is retried with a longer wait each time. In pilot the
  brain only reads, so nothing is written half way.
- **You do:** check with the TravelSpirit administrator. After it is back, retry failed jobs.

### An agent does something wrong
- **You see:** a specialist or team lead reports drafts that are wrong in the same way.
- **You do:** pause that agent (**Maintenance > Pause**; every pause is logged). Other agents keep working. Add the bad
  case to the test set, fix the prompt or the knowledge, run `brain bench --gate`, then resume it.

### Someone leaves Travelnauts
- **You do:** set the user to inactive in **Users**. Their access stops at once. The screen shows how many
  of their open requests need a new owner; reassign them in **Team lead > Insight**.
- **Tested in:** simulation day 11 (access removed, 11 requests listed to reassign); security tests (inactive
  users are refused everywhere).

### Someone changes an approved knowledge note
- **The system:** agents keep using the approved text. The change waits in **Team lead > Knowledge** as
  "(change)" until the team lead approves it.
- **Tested in:** simulation day 13; test `test_an_edited_note_keeps_its_approved_text_until_the_change_is_approved`.

### The audit chain is broken
- **You see:** Maintenance or `brain verify` says "audit chain broken at entry N".
- **This means:** someone changed or deleted a log row directly in the database. The application cannot do this.
- **You do:** do not repair it. Export the database (pg_dump), note the time, and tell the Travelnauts privacy
  contact and Myt the same day. Compare with the last backup to see what was changed. Treat it as a possible
  data incident.
- **Tested in:** backup drill (a changed row in a restored copy is found at the exact entry); test
  `test_verify_reports_counts_and_catches_a_changed_audit_entry`.

### Suspected data leak
- **You do, within the hour:** pause all agents; switch off the mail connector; save the audit log and the
  agent log. Tell the Travelnauts privacy contact. Under the processing agreement Myt informs Travelnauts without
  undue delay, and Travelnauts decides on reporting to the Autoriteit Persoonsgegevens within 72 hours.
- The audit log shows who opened which customer data and when (including every break-glass use with its reason).

### Restore from backup
1. Azure keeps point-in-time backups (30 days in pilot and live). Restore to a **new** server, never over the old one.
2. Run `brain verify` on the restored database. It must say ok and list the expected row counts.
3. Run `brain migrate`. It brings the schema up to date, or stops without changing anything if the database
   does not match the code.
4. Point the container apps at the new database (one setting), and check `/readyz`.
5. Mail that arrived after the backup moment is fetched again from the mailbox; the brain skips mail it has
   already seen.
- **Tested in:** backup drill on two weeks of simulated data (6,821 rows in 22 tables, counts identical, audit
  chain identical, the newest migration down and up again on the restored data). Restore took seconds at this
  size; at live size, measure it during the first real drill.

## Who to call

Fill in with Travelnauts before the pilot starts.

| Role | Name | How |
|---|---|---|
| Administrator at Myt | | |
| Travelnauts privacy contact | | |
| TravelSpirit administrator | | |
| Azure subscription owner | | |
