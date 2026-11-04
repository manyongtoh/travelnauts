# Travelnauts company brain: sandbox

A working first version of the company brain from the proposal, running on **made-up data only**.
It has the six pilot agents, the knowledge rules (approval, owner, review date, gap list), a fake
TravelSpirit, the price calculation and the three screens (specialist, team lead, back office).

Nothing here is Travelnauts data. Families, partners, hotels, prices and staff are invented.
Agents only ever write drafts; a person approves every mail before it goes out.

## Run it

```bash
pip install -e ".[dev]"
brain seed            # build the synthetic database (data/brain.db)
brain serve           # open http://127.0.0.1:8000
pytest -q             # 26 tests
brain bench           # test bench report in data/bench/
```

With the full stack (Postgres and Ollama with Gemma):

```bash
docker compose up -d
docker compose exec ollama ollama pull gemma4
BRAIN_MODEL=ollama:gemma4 docker compose up -d app
```

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
| Screens | `brain/api/static/` | Specialist, team lead (team figures only, never per person), back office board |

## Safety rules built in

- `BRAIN_DATA_STAGE=live` refuses to start. Live needs the go-live approval from Inge and Jonas.
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

## What is a placeholder until Travelnauts provides it

See [docs/next-steps.md](docs/next-steps.md). In short: TravelSpirit API documentation and test access,
anonymised example proposals and partner mails, the Excel calculation template, the Galileo command
list, and the real booking terms. Everything that stands in for these is marked as a placeholder.

## Ownership

Built by Myt B.V. The generic parts (agent framework, knowledge rules, test bench, screens) are Myt's
and reusable; Travelnauts specific content and data stay with Travelnauts, as set out in the contract.
