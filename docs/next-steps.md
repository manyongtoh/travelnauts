# From sandbox to pilot

The route is synthetic, then anonymised, then live. This sandbox is the synthetic stage, and it is tested as far
as synthetic data allows (see [test-reports](test-reports/README.md)). What remains needs Travelnauts.

The working lists are in [lists](lists): **open questions** (33, with who answers and by when) and **tests and
next steps** (with status and results). They are the source of truth; this page is the short version.

## Needed from Travelnauts

| What | Replaces | Where it plugs in |
|---|---|---|
| TravelSpirit API documentation and a test account (read API now, two-way from January 2027) | the fake TravelSpirit | `brain/travelspirit/client.py` |
| Where mail is read (TravelSpirit Mail or Exchange), with attachments | mail from the fake | the mail connector |
| 30 to 50 anonymised booked proposals and about 20 partner mails | synthetic examples | `brain/synth` loader |
| The Excel calculation template and margin rules | sandbox margins | `brain/pricing.py` |
| The Galileo commands the team uses | placeholder formats | `brain/agents/galileo.py` |
| Booking terms, payment terms, house style | placeholder policy notes | knowledge items |
| Team setup and knowledge owners | synthetic teams | teams, employees |
| Answers to the flow questions (Q1 to Q11) | sandbox defaults | settings; Q1 and Q4 are built both ways |
| Azure subscription and Entra registrations | local runs | `infra/`, deploy workflow |

## Next, in order

1. **Agree:** contract, success measure, inventory questionnaire, interviews with specialists and back office.
2. **Gemma 4 on the bench** (can start now): see [gemma.md](gemma.md).
3. **Real TravelSpirit adapter** with contract tests on the test account.
4. **Anonymised data:** run the anonymiser on 200 real mails with a person checking; sender matching, sign-off
   names, partner replies and invoices on real mail.
5. **Azure test environment:** deploy, sign-in, alerts to real people, backup drill on point-in-time restore,
   Prompt Shields on the held-out injection set.
6. **Before the pilot:** processing agreement and DPIA, baseline measurement, pilot group onboarding.
7. **Pilot** on anonymised data, read only, weekly review of edit share, gaps and alerts.
8. **Before live:** outside penetration test, go or no-go against agreed criteria.
