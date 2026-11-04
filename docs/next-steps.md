# From sandbox to pilot

The proposal's route is synthetic, then anonymised, then live. This sandbox is the synthetic stage.

## Needed from Travelnauts for the anonymised stage

| What | Replaces | Where it plugs in |
|---|---|---|
| TravelSpirit API documentation and a test account (read API now, two-way API from January 2027) | `FakeTravelSpirit` | `brain/travelspirit/client.py`, `RealTravelSpirit` |
| 30 to 50 anonymised proposals that were booked, plus 20 partner mails | the 80 synthetic past proposals | `brain/synth` loader for anonymised data |
| The Excel calculation template | margins in `pricing.py` (sandbox assumptions) | `brain/pricing.py` |
| The Galileo commands the team actually uses | the placeholder formats | `brain/agents/galileo.py`, `ALLOWED` |
| Current booking terms, payment terms and house style notes | `k-policy-*`, `k-voice` | knowledge items, approved by the owner |
| Team setup: which destinations per team, who owns which knowledge | `brain/synth/world.py` | teams, employees |

## To build next

1. **Gemma run.** Run the bench with `BRAIN_MODEL=ollama:gemma4`, compare with the stand-in, tune the
   instructions. If Gemma on Ollama struggles with tool based structured output, switch the agents to
   native JSON output (one setting in Pydantic AI).
2. **Postgres and vector search.** The tables are written for Postgres too (docker compose), but not yet
   tested against a Postgres server. Then replace the
   TF-IDF search in `knowledge/store.py` with embeddings in pgvector behind the same `search()`.
3. **Anonymiser: built.** `brain ingest` loads a TravelSpirit export through it. Before the first real
   export, test it on a sample of 200 real mails with a person checking the output, and extend the
   patterns for anything it misses.
4. **Measurement.** Baseline the minutes per request with the pilot group before go-live, then compare.
   The edit share per draft and the gap list are already recorded.
5. **Azure.** Container on Azure, Entra ID login for the screens, secrets in Key Vault, logs to the
   existing Azure tenant. Pentest and DPIA before customer channels.
