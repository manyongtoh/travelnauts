# brain-core

The company brain platform of Myt B.V. Proprietary: see [LICENSE](LICENSE). Clients plug in through a tenant
pack in their own repo; the core ships one invented sample tenant, Wolkenwaai Reizen, and contains no client
names or data (CI checks this).

A working version of the company brain from the proposal and the tech architecture, running on
**made-up data only**: the tool server (also over MCP), a job queue and scheduler, the model
router with budgets, guardrails, the knowledge vault, sign-in by role, a hash-chained audit log, traces,
nineteen agents (including alternatives, complaints, next-trip and extras advisors, call notes, invoice matching,
roadbooks and vouchers as PDF, and booking file checks),
evals that gate CI, and five screens (specialist, team lead, back office, maintenance, user management).
See [docs/architecture-coverage.md](docs/architecture-coverage.md) for what is built, what is a stand-in
and what still needs Azure, [docs/operations.md](docs/operations.md) for how it scales and what keeps it robust, [docs/runbook.md](docs/runbook.md)
for daily checks and incidents (a template; each client repo keeps its filled-in copy), and
[docs/test-reports](docs/test-reports/README.md) for the latest results.

Nothing here is client data. Families, partners, hotels, prices and staff are invented.
Agents only ever write drafts; a person approves every mail before it goes out.

## Tenants

A tenant pack is a client's own repo: `tenant.toml` (validated at start-up: domains, booking reference prefix,
Galileo remark, autonomy ceiling, margins), `house.md` (the first prompt layer) and optional agent prompt
overrides. It registers itself under the `brain.tenants` entry point; `BRAIN_TENANT` picks one when several are
installed. The core's own sample is `brain/sample_tenant/` (Wolkenwaai Reizen, invented).

- Every table has a `tenant_id`; every query is scoped to the current tenant, and on Postgres row-level
  security enforces the same (connect as a role that is not a superuser). See `tests/test_tenancy.py`.
- The core talks to a client's systems only through two contracts in `brain/connectors.py`: `SystemOfRecord`
  and `Channel`. TravelSpirit is the first adapter (`brain/travelspirit/`).
- Every draft and job has an autonomy level, default 1 (a person approves). See `brain/autonomy.py`.
- `python scripts/check_client_names.py` fails when the core names a client (hashed list in `.client-denylist`).

## Run it

```bash
pip install -e ".[dev]"
brain seed            # build the synthetic database and knowledge vault (data/)
brain worker --once   # run the scheduler and the queue once (triage, follow-ups, insight, ...)
brain serve           # open http://127.0.0.1:8000 and pick who you are
pytest -q             # 185 tests (BRAIN_TEST_DATABASE_URL=postgresql+psycopg://... for Postgres)
brain bench --gate    # evals; fails when a gate from the architecture is not met
brain mcp             # the tool server over MCP, as BRAIN_MCP_AGENT
brain envcheck        # check the test, pilot or live configuration
brain migrate         # database migrations (pilot and live)
brain worker --drain  # scaled workers: work the queue until it is empty
brain loadtest        # many mails, several workers at once (use Postgres)
brain simulate        # two weeks of daily operation with incidents
brain check           # open alerts;  brain verify: counts, audit chain, schema
python scripts/journey.py             # one family, first mail to next trip
python scripts/journey_backoffice.py  # the back office day for one trip
brain modelcheck      # a sample of the bench for a real model on slow hardware
```

With Gemma 4 instead of the stand-in model, see [docs/gemma.md](docs/gemma.md): on your own machine, or without
installing anything through the `gemma` workflow on GitHub (`brain modelcheck`, a sample of the bench). With the full stack (Postgres and Ollama):

```bash
docker compose up -d
docker compose exec ollama ollama pull gemma4
BRAIN_MODEL=ollama:gemma4 docker compose up -d app
```

## How the brain learns

Nothing it learns is used before a person approves it.

| From | What the brain does | Who approves |
|---|---|---|
| What specialists keep adding or removing (3 drafts, 2 people, 30 days) | proposes a house rule; approved rules go into the prompts | team lead |
| Proposals booked or turned down | keeps them as examples, without names (same anonymiser as real data); booked and alike ones first | automatic, anonymised |
| A family question it could not answer | gives the specialist a blank to fill in; the answer becomes a proposed knowledge note | team lead |
| Children's ages | keeps birth years, so ages count up; a next-trip idea years later thinks of today's ages | automatic |
| Earlier trips and complaints | shown to agents as the family's history ("nice to plan with you again"; take extra care) | automatic |
| Who knows a destination | routes requests to that specialist unless they have 3 or more requests more than the least busy colleague | automatic |
| What partners actually do | measures reply time, reply rate, invoice accuracy and complaints; swaps a weak hotel in a draft route | automatic, shown on the board |
| How specialists ask | search knows places (Bali is Indonesia), synonyms (omboeken is wijzigen) and topics | automatic |

## Two model modes

| `BRAIN_MODEL` | What it does |
|---|---|
| `sandbox` (default) | A stand-in model that follows simple rules and templates. No network, same answer every time. Good for testing the flow, the screens and the safety rules. **It says nothing about how good the writing is.** |
| `ollama:gemma4` | Gemma 4 through Ollama, the pilot's choice. Same agents, same checks, real writing. |
| `openai:<model>` | Any OpenAI compatible endpoint (for example Azure AI Foundry) at `BRAIN_MODEL_BASE_URL`. |

## What is in it

| Part | Where | What it does |
|---|---|---|
| Synthetic world | `brain/synth/` | 8 destinations, 3 teams, 29 staff, 200 families, 57 partners, 182 price lines, 80 past proposals, 70 knowledge items, 30 trips in progress, 104 regular mails and 35 hard mails, all with ground truth |
| Fake TravelSpirit | `brain/travelspirit/` | Read API in the shape we expect, plus draft reisplans. The real API plugs in here. |
| Company brain | `brain/knowledge/` | Only approved knowledge is used; every item has an owner and a review date; unanswered questions, weak sources and heavily rewritten drafts go on the gap list |
| Price calculation | `brain/pricing.py` | The Excel calculation as code: cost lines, margin per kind, expired prices flagged |
| Triage | `brain/agents/triage.py` | Classifies mail, extracts trip details, routes to team and least busy specialist |
| Proposal writer | `brain/agents/proposal.py` | Route from similar past proposals, age safe activities, prices, approved facts, house voice, draft reisplan |
| Follow-up | `brain/agents/followup.py` | Friendly reminder when a proposal has had no reply for 5 days |
| Partner desk | `brain/agents/partner_desk.py` | Availability requests to the local agent and every hotel, reminders after 3 days, offer comparison |
| Galileo helper | `brain/agents/galileo.py` | Writes the Galileo commands with an explanation; never runs, ends or tickets |
| Knowledge desk | `brain/agents/knowledge_desk.py` | Answers with sources, or says it does not know and records a gap |
| Change agent | `brain/agents/change.py` | Links a change request to the right trip, applies what it safely can (nights, skipping a stop), recalculates, drafts the reply; dates, transport and anything unclear go to the specialist |
| Anonymiser | `brain/anonymise.py` | Removes names, mail addresses, phone numbers, IBANs, BSNs, passport numbers, addresses and birth dates; keeps destinations, months, ages and budgets; a second check refuses the record if anything personal may be left |
| Ingest | `brain/ingest.py`, `brain ingest export.jsonl` | Loads a TravelSpirit export through the anonymiser (anonymised stage only); refused records are reported by id, never by content |
| Audit log | `agent_runs` table | Every run: agent, model, sources, result, time |
| Screens | `brain/api/static/` | Specialist, team lead (team figures only, never per person), back office board; Dutch or English per person (EN/NL in the top bar) |
| Value page | `brain/value.py`, Team lead > Value | Time to first proposal against the baseline, share sent unchanged, work done unprompted, partner reply times, booked share, estimated hours saved. The baseline is editable and labelled an assumption until measured. CSV export. |
| Automatic send | `brain/autosend.py` | After 10 unchanged approvals in a row of a low-risk kind (follow-ups, extras offers, partner requests and reminders) the brain asks whether it may send them itself. If yes, each one shows 10 seconds with a Stop button, then goes out with every check. Proposals, changes, answers, complaints and money stay manual. |
| Partner portal | `brain/portal.py`, `/portal/<link>` | Local agents answer line by line without an account: status, price, valid-until date, alternatives, a thread and PDF upload. The back office accepts an alternative in one click. No family names. |
| Duplicate families | `brain/duplicates.py`, Team lead > Duplicates | Likely doubles with the evidence; a person merges or keeps apart; a merge plan for the TravelSpirit administrator. |

## Safety rules built in

- `BRAIN_DATA_STAGE=live` refuses to start. Live needs the go-live approval from the client's management.
- In the synthetic stage the app refuses to run if any row is not marked synthetic.
- Agents cannot write final records in TravelSpirit, only drafts (`BRAIN_TRAVELSPIRIT_WRITE=drafts|off`).
- Partner mails carry a booking reference, never the family's name.
- Activities below the minimum age of the youngest child are never proposed.
- Citations are checked: an agent can only cite sources it was actually given.

## Test bench (stand-in model, seed 42)

`brain bench` runs every agent over the inbox and checks it against the ground truth. GitHub runs the
tests and the bench on every push and shows the report on the run page.

| Check | Regular mails | Hard mails |
|---|---|---|
| Anonymiser: mails passed, names left behind | 139 of 139 passed, 0 names left | (included) |
| Triage: right category | 100% of 104 | 29% of 35 |
| Triage: destination, days, month, ages, budget | 100% each | 7% to 60% |
| Change requests linked and understood | 10 of 10 | 0 of 5 |
| Knowledge desk: answered with the right source | 8 of 8 | 0 of 3 |
| Knowledge desk: unknown questions became gaps | 6 of 6 | 2 of 2 |
| Proposals: approved source, route fits, no unsafe activities | 72 of 72 | |
| Galileo: commands outside the allowed formats | 0 of 115 | |

The stand-in model's rules were written against the regular mails, so those scores show that the plumbing
and the safety rules work. The hard mails (English, numbers in words, "meivakantie", "15k", Bali instead of
Indonesia, partner replies, out of office) were kept apart on purpose: the rules fail on them, which is the
point. They are the yardstick for Gemma. The knowledge desk misses on hard questions partly because search is
still keyword based; search by meaning is the next step there.

## What is a placeholder until a client provides it

Each client repo lists what it still has to provide. In short: TravelSpirit API documentation and test access,
anonymised example proposals and partner mails, the Excel calculation template, the Galileo command
list, and the real booking terms. Everything that stands in for these is marked as a placeholder.

## Ownership

Built and owned by Myt B.V. Client-specific content and data stay in the client's own repo and database, as set
out in each client's agreement.
