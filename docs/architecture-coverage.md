# Architecture v2: what the sandbox covers

Every part of the tech architecture document, where it lives in the code, and its status.

- **Built:** works and is tested here.
- **Stand-in:** same interface, local replacement for an Azure or outside service; switching is configuration.
- **Written, untested:** code or template exists but needs Azure or Travelnauts access to run.
- **Later:** planned for after the pilot, as in the document.

## Platform

| Architecture | Where | Status |
|---|---|---|
| One tool server as the single door, rights per caller, every call logged | `brain/toolserver.py`, `identity.AGENTS` | Built |
| Agents call it through MCP | `brain/mcp_server.py`, `brain mcp` | Built (one MCP server per agent identity) |
| Queue: messages and jobs picked up by agents | `brain/jobs.py`, `brain worker` | Built |
| Scheduled agents (nightly, hourly, daily) | `jobs.SCHEDULE` | Built |
| Pydantic AI, fixed steps in code, typed output | `brain/agents/*` | Built |
| Model gateway: routing by tier, fallback, budgets | `brain/router.py` (LiteLLM in Azure) | Stand-in |
| Escalation to the large model (low confidence, complaint, failed check) | triage, proposal, Galileo | Built |
| Caching: prompt layers fixed, exact cache for lookups, semantic cache for internal questions only | `prompts/`, toolserver cache, `knowledge/store.py` | Built (provider prompt caching needs a real model) |
| Calculation service with versioned price tables, traceable quotes | `brain/pricing.py` (`quote`, `price_version`) | Built |
| TravelSpirit connector with our own contract, adapters per API version, one ID mapping | `travelspirit/client.py`, `adapter_v1.py` | Built on an assumed format; real mapping needs API docs |
| Contract tests on recorded TravelSpirit responses | `tests/contract/` | Built (recordings are placeholders) |
| Drafts only, switch to write into TravelSpirit per environment | `BRAIN_TRAVELSPIRIT_WRITE`, review screen with copy button | Built |
| Galileo: commands only, never executed | `agents/galileo.py`, `galileo.write_commands` tool | Built (placeholder command formats) |
| Flight and train status, number and date only | `travel.flight_status` | Stand-in |

## Agents

| Agent | Status |
|---|---|
| Triage | Built |
| Proposal writer | Built |
| Partner desk: requests, reads replies and PDF offers, chases, compares | Built |
| Supplier watcher | Built |
| Knowledge desk | Built |
| Customer insight | Built |
| Follow-up | Built |
| Galileo helper | Built |
| Team insight | Built |
| Trip monitor | Built (stand-in flight data) |
| Change handling (not in the document, added) | Built |
| Proposal alternatives: quieter and cheaper, priced | Built |
| Complaint handling: severity, actions, careful reply, team lead approves money or high priority | Built |
| Next-trip advisor (weekly, former guests) | Built |
| Extras advisor | Built |
| Call notes into wishes, changes, questions, next steps | Built |
| Invoice matcher: invoice against the accepted offer | Built |
| Roadbook and vouchers as PDF, with a children's page | Built |
| Partner offers in PDF attachments | Built |
| Booking file checks (partners, offer, flights, payment, insurance, passports, roadbook) | Built |

## Knowledge and prompts

| Architecture | Where | Status |
|---|---|---|
| Obsidian vault in git as master | `knowledge/vault.py`, `BRAIN_VAULT` | Built (markdown folder; point it at the real vault) |
| Chunk by heading with source, version, validity, roles | `vault.chunks`, `KnowledgeItem` | Built |
| Vector and keyword search combined, filtered by role | `knowledge/store.py`, `knowledge/embed.py` | Built; local embeddings are a stand-in for an Azure embedding model in pgvector |
| Cite, approve, owner and review date, gaps, trace errors | store, knowledge desk, team lead screen | Built |
| Nightly re-index; changed text needs approval again; old policy archived | `vault.reindex` | Built |
| Three prompt layers, versioned, version stored per model call | `brain/prompts/` | Built |
| 5 to 10 best examples picked by Jorine and a team lead | `examples.search` uses earlier proposals | Stand-in (needs the real examples) |

## Guardrails, privacy, access

| Architecture | Where | Status |
|---|---|---|
| In: mail is data; suspicious mail to a person, no draft | `guardrails.detect_injection`, triage | Built (rules); Azure Prompt Shields written, untested |
| Privacy: mask names, IBAN, passport, BSN before any model call | `guardrails.Pseudonymiser`, `anonymise.py` | Built (Presidio in Azure is optional on top) |
| Anonymisation step between live and pilot | `brain ingest` | Built |
| Tools: least privilege per agent | `identity.AGENTS` | Built |
| Out: structured output, prices only from the calculation, no health advice, unknown hotels flagged | `guardrails.check_output`, approval check | Built |
| Entra ID sign-in, app roles, checked on every request | `identity.verify_entra_token`, `api/app.py` | Built (token check tested with a local key); sandbox picker by default |
| Role table (specialist, back office, team lead, content, admin, agents) | `identity.PERMISSIONS` | Built |
| Admin sees no customer content; break-glass is logged | `/api/admin/break-glass` | Built |
| Separate customer login (Entra External ID) | | Later |

## Observability, evals, operations

| Architecture | Where | Status |
|---|---|---|
| Trace per run: tool calls, model, prompt version, tokens, cost, latency | `agent_runs`, `tool_calls`, `model_calls`, `/api/traces/{id}` | Built; Langfuse export written, untested |
| Audit log append-only and hash-chained, pseudonymous | `brain/auditchain.py` | Built |
| Evals in CI with thresholds that block a change | `evals/bench.py`, `evals/sets.py`, `.github/workflows/ci.yml` | Built |
| 20 injection mails, 20 knowledge questions, price check exact to the euro | `evals/sets.py` | Built |
| 200 labelled triage mails, 30 past requests scored by an LLM judge | | Needs real (anonymised) mails and a real model |
| Feedback per draft: used as is, edited, discarded | `Draft.edit_share`, discard in audit chain | Built |
| Maintenance dashboard: connections, queue, errors, stuck jobs, cost and budget, evals, audit chain; pause agents | `static/maintenance.html` | Built |
| User management: roles, invite, remove access, next access review | `static/users.html` | Built (writes to Entra ID in Azure: not yet) |
| Team metrics for Power BI | `/api/metrics/teams.csv` | Built (CSV); Power BI report itself not built |
| Azure Monitor and alerts to Teams | | Needs Azure |
| Test, pilot and live with their own rules | `brain/environments.py`, `brain envcheck` | Built |
| Infrastructure as code per environment, autoscaling API and KEDA-scaled workers, probes | `infra/main.bicep`, `infra/params/` | Written, untested |
| Postgres, migrations, parallel workers | `migrations/`, `brain migrate`, `jobs.claim` | Built and tested on Postgres 16 (95 tests, load test) |
| Deploy one way up with approval | `.github/workflows/deploy.yml` | Written, untested |
| n8n workflows: export, sort, rebuild | `brain n8n` | Built (inventory and advice) |

## Customer journey

App, web chat, WhatsApp, the living proposal, the Reisboekje and the customer assistant come after the pilot,
on the same tool server. Nothing for them is built yet, apart from the parts they reuse (tool server,
knowledge, guardrails, trip monitor).
