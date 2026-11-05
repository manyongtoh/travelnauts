# Gemma 4 on Azure: what it costs

Estimate from 5 November 2026. The working file is [Gemma on Azure cost.xlsx](lists/Gemma%20on%20Azure%20cost.xlsx):
change the grey assumptions (volumes, speeds, prices) and the totals follow. Prices are pay-as-you-go list prices
in USD found that day; the serverless GPU prices come from third-party guidance because Microsoft shows them only in
the pricing calculator. Check both in the Azure calculator before deciding.

| Option | USD a month | What you get |
|---|---|---|
| Small model (e4b), serverless T4, only when used | about 2 | Cheapest; the first mail after a quiet spell waits for the model to load |
| Small model, serverless T4, warm in office hours | about 70 | Answers at once during the day |
| 26B or 31B, serverless A100, only when used | about 13 | The quality of the hosted 31B run, paying only for busy seconds |
| 26B or 31B, serverless A100, warm in office hours | about 515 | Best quality, answers at once in the day |
| Small model, T4 machine always on | about 480 | Simple, pays for every idle night |
| 26B or 31B, A100 machine always on | about 2,680 | Only worth it at much higher volume |

Assumed: 40 mails, 8 proposals and 30 other drafts a working day, 22 working days, a quarter of an hour of model
loading a day. At that volume the GPU is busy well under an hour a day.

## What this means

- **The volume is small, so the bigger model is affordable.** Paying per second for an A100 only when there is work,
  the 26B or 31B costs tens of euros a month, not thousands.
- **Waiting for the model to load hardly matters here.** The brain drafts in the background: the proposal is ready
  before the specialist opens it. Only "Ask the brain" is live, and that can wait a minute on a quiet morning or
  use the small model.
- **Proposed for the pilot:** the 26B (the faster mixture of experts) on a serverless A100 that scales to zero, with
  the small model as the fallback. Measure speed and cost in the Azure test environment in the first week and
  update the workbook with real numbers.
- **Not included:** the app itself (Container Apps, Postgres, storage, monitoring), sized in the infra plan; GPU
  quota requests; staff time.
