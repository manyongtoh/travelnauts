# Running the brain on Gemma 4

The sandbox runs on a stand-in model by default. To see real writing and to run test #1 (the quality bench on the
real model), run Gemma 4 locally with Ollama. Synthetic data only, so nothing leaves your machine.

## 1. Install Ollama

| Machine | How |
|---|---|
| Mac | Download the app from ollama.com, or `brew install --cask ollama-app`, then open it |
| Windows | Download the app from ollama.com |
| Linux | `curl -fsSL https://ollama.com/install.sh \| sh` |

Check: `ollama --version`. Ollama answers on `http://localhost:11434`; if it does not, open the app or run `ollama serve`.

## 2. Pull Gemma 4

| Model | Download | Fits | Use it for |
|---|---|---|---|
| `gemma4` (= `gemma4:e4b`) | about 10 GB | 16 GB laptop, Apple Silicon | the small tier: triage, reading replies and invoices |
| `gemma4:26b` | about 18 GB | 32 GB Mac or 24 GB GPU | the large tier: proposals, complaints, escalations |
| `gemma4:31b` | about 20 GB | 32 GB or more | the best quality, slowest |

```bash
ollama pull gemma4
ollama pull gemma4:26b        # if your machine has the memory
ollama run gemma4 "Zeg hallo in één zin."   # quick check
```

## 3. Point the brain at it

```bash
cd travelnauts
pip install -e ".[dev]"
export BRAIN_MODEL_BASE_URL=http://localhost:11434/v1
export BRAIN_MODEL_SMALL=ollama:gemma4
export BRAIN_MODEL_LARGE=ollama:gemma4:26b     # or ollama:gemma4 on a 16 GB machine
export BRAIN_MODEL_FALLBACK=sandbox            # if Gemma fails, the stand-in keeps the flow going
brain seed
brain serve                                    # http://127.0.0.1:8000, the drafts are now written by Gemma
```

With Docker instead: `docker compose up -d`, then `docker compose exec ollama ollama pull gemma4`, then
`BRAIN_MODEL=ollama:gemma4 docker compose up -d app`.

## 4. Run test #1: the quality bench

```bash
brain bench --gate             # takes longer than with the stand-in: every mail goes through Gemma
```

The report lands in `data/bench/report.md`. Compare it with the stand-in run in `docs/test-reports`. Look at:

- **triage_clean / triage_hard / triage_english**: category and field accuracy. The English set is only meaningful
  on a real model.
- **proposals**: unsafe activities must stay 0; the price check must stay 100%.
- **complaints**: money promises must stay 0.
- **avg_ms**: seconds per mail on your machine (Azure will differ).

Then try `scripts/journey.py` and `scripts/journey_backoffice.py`: the whole flow with real writing.

## If something goes wrong

| Problem | Fix |
|---|---|
| Connection refused | Ollama is not running: open the app or `ollama serve` |
| Model not found | `ollama list` and use that exact name |
| Very slow | Use `gemma4` (e4b) for both tiers; close other heavy apps |
| Answers do not fit the expected format | Note which agent; if it keeps happening, the agents can switch to native JSON output (one setting in Pydantic AI) |

For the pilot, where Gemma runs (an Azure GPU, a hosted endpoint) is open question Q26.
