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
pytest -q             # 14 tests
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
| Synthetic world | `brain/synth/` | 8 destinations, 3 teams, 29 staff, 200 families, 57 partners, 182 price lines, 80 past proposals, 70 knowledge items, 106 mails with ground truth, 30 trips in progress |
| Fake TravelSpirit | `brain/travelspirit/` | Read API in the shape we expect, plus draft reisplans. The real API plugs in here. |
| Company brain | `brain/knowledge/` | Only approved knowledge is used; every item has an owner and a review date; unanswered questions, weak sources and heavily rewritten drafts go on the gap list |
| Price calculation | `brain/pricing.py` | The Excel calculation as code: cost lines, margin per kind, expired prices flagged |
| Triage | `brain/agents/triage.py` | Classifies mail, extracts trip details, routes to team and least busy specialist |
| Proposal writer | `brain/agents/proposal.py` | Route from similar past proposals, age safe activities, prices, approved facts, house voice, draft reisplan |
| Follow-up | `brain/agents/followup.py` | Friendly reminder when a proposal has had no reply for 5 days |
| Partner desk | `brain/agents/partner_desk.py` | Availability requests to the local agent and every hotel, reminders after 3 days, offer comparison |
| Galileo helper | `brain/agents/galileo.py` | Writes the Galileo commands with an explanation; never runs, ends or tickets |
| Knowledge desk | `brain/agents/knowledge_desk.py` | Answers with sources, or says it does not know and records a gap |
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

| Check | Result |
|---|---|
| Triage: right category / destination / team | 100% / 100% / 100% (106 mails) |
| Triage: days, month, ages, adults, budget extracted | 100% each |
| Proposals: drafted with an approved source, route fits the days | 70 of 70 |
| Proposals: activities too old for the youngest child | 0 |
| Proposals: within budget (where a budget was given) | 95% |
| Knowledge desk: answerable questions answered with the right source | 8 of 8 |
| Knowledge desk: unanswerable questions recorded as gaps | 6 of 6, none answered with false confidence |
| Partner desk: right number of requests per trip | 10 of 10 |
| Galileo: commands outside the allowed formats | 0 of 115 |

Read this with care: the stand-in model was written with the synthetic data in mind, so high scores
show the plumbing and the rules work, not that a language model will score this well. The same
bench is the yardstick when we switch to Gemma.

## What is a placeholder until Travelnauts provides it

See [docs/next-steps.md](docs/next-steps.md). In short: TravelSpirit API documentation and test access,
anonymised example proposals and partner mails, the Excel calculation template, the Galileo command
list, and the real booking terms. Everything that stands in for these is marked as a placeholder.

## Ownership

Built by Myt B.V. The generic parts (agent framework, knowledge rules, test bench, screens) are Myt's
and reusable; Travelnauts specific content and data stay with Travelnauts, as set out in the contract.
