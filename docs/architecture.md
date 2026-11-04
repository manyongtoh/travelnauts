# Architecture (sandbox)

```
 TravelSpirit Mail ──► Triage ──► TripRequest ──► Proposal writer ──► Draft ──► Specialist approves
   (fake for now)        │                            │    ▲                      │
                         │                            │    │ approved knowledge   ├─► VTB draft reisplan
                         ▼                            ▼    │ price list           ├─► Partner desk ──► partner mails (back office approves)
                   Knowledge desk ──► answer with   Galileo helper ──► commands    └─► edit share ──► gap list if heavily rewritten
                                     sources, or gap                (specialist runs them)
```

## Principles

- **Code does the lookups, the model writes.** Each agent first gathers its facts in plain code
  (TravelSpirit, knowledge, price list, past proposals). The model only gets that context and returns
  a typed result (Pydantic). This keeps answers traceable and stops the model inventing prices or rules.
- **Drafts only.** Every output is a `Draft`. Approval is a person's action, and the approval records
  how much was changed.
- **Approved knowledge only.** Proposed items are invisible to agents until a specialist or team lead
  approves them. Items past their review date are flagged in answers and on the team lead screen.
- **Everything logged.** `agent_runs` holds agent, model, subject, sources, result and duration for
  each run, including failures.
- **One interface per outside system.** TravelSpirit, the model and search each sit behind one small
  interface, so the fake can be swapped for the real thing without touching the agents.

## Stack

Python 3.11+, Pydantic AI, FastAPI, SQLAlchemy (SQLite in the sandbox, Postgres with pgvector in
docker compose and on Azure), scikit-learn TF-IDF for offline search, Ollama for Gemma 4.
