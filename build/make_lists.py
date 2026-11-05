"""Builds the two Travelnauts working lists as Excel files."""
from openpyxl import Workbook
from openpyxl.formatting.rule import FormulaRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

FONT = "Arial"
NAVY = "1F2E44"
SAND = "F4EDE1"
INPUT = "FFF7D6"  # light yellow: cells to fill in
thin = Side(style="thin", color="D9CFBF")
BORDER = Border(left=thin, right=thin, top=thin, bottom=thin)


def header(ws, row, cols):
    for i, (name, width) in enumerate(cols, 1):
        c = ws.cell(row=row, column=i, value=name)
        c.font = Font(name=FONT, bold=True, color="FFFFFF", size=10)
        c.fill = PatternFill("solid", fgColor=NAVY)
        c.alignment = Alignment(vertical="center", wrap_text=True)
        c.border = BORDER
        ws.column_dimensions[get_column_letter(i)].width = width
    ws.row_dimensions[row].height = 30


def body(ws, first, rows, input_cols=()):
    for r, values in enumerate(rows, first):
        for col, v in enumerate(values, 1):
            c = ws.cell(row=r, column=col, value=v)
            c.font = Font(name=FONT, size=10)
            c.alignment = Alignment(vertical="top", wrap_text=True)
            c.border = BORDER
            if col in input_cols:
                c.fill = PatternFill("solid", fgColor=INPUT)


def title(ws, text, sub):
    ws["A1"] = text
    ws["A1"].font = Font(name=FONT, bold=True, size=14, color=NAVY)
    ws["A2"] = sub
    ws["A2"].font = Font(name=FONT, size=10, italic=True, color="555555")


def dropdown(ws, col, first, last, options):
    dv = DataValidation(type="list", formula1='"' + ",".join(options) + '"', allow_blank=True)
    ws.add_data_validation(dv)
    dv.add(f"{col}{first}:{col}{last}")


def done_grey(ws, status_col, first, last, ncols, done_values):
    rng = f"A{first}:{get_column_letter(ncols)}{last}"
    cond = "OR(" + ",".join(f'${status_col}{first}="{v}"' for v in done_values) + ")"
    ws.conditional_formatting.add(rng, FormulaRule(formula=[cond], font=Font(name=FONT, color="9A9A9A")))


def summary(wb, src, status_col, prio_col, who_col, statuses, prios, whos, last, sheet_title):
    ws = wb.create_sheet("Summary", 0)
    title(ws, sheet_title, "Counts update by themselves as you fill in the list.")
    ws.column_dimensions["A"].width = 34
    for c in "BCDE":
        ws.column_dimensions[c].width = 14
    r = 4
    ref = f"'{src}'"

    def block(label, col, values, start):
        ws.cell(row=start, column=1, value=label).font = Font(name=FONT, bold=True, color=NAVY)
        ws.cell(row=start, column=2, value="Count").font = Font(name=FONT, bold=True, color=NAVY)
        for i, v in enumerate(values, start + 1):
            ws.cell(row=i, column=1, value=v).font = Font(name=FONT, size=10)
            c = ws.cell(row=i, column=2, value=f'=COUNTIF({ref}!${col}$5:${col}${last},A{i})')
            c.font = Font(name=FONT, size=10)
        t = start + len(values) + 1
        ws.cell(row=t, column=1, value="Total").font = Font(name=FONT, bold=True, size=10)
        ws.cell(row=t, column=2, value=f"=SUM(B{start + 1}:B{t - 1})").font = Font(name=FONT, bold=True, size=10)
        return t + 2

    r = block("By status", status_col, statuses, r)
    if prios:
        r = block("By priority", prio_col, prios, r)
    if whos:
        r = block("By needed by", who_col, whos, r)
    return ws


# ---------------------------------------------------------------- open questions
Q_COLS = [("#", 5), ("Topic", 16), ("Question", 52), ("Why it matters, what it blocks", 46), ("Sandbox does now", 34),
          ("Who can answer", 20), ("Needed by", 16), ("Priority", 10), ("Status", 12), ("Answer", 40), ("Date answered", 13)]
B4P, ANON, LIVE, PILOT = "Before pilot start", "Anonymised stage", "Before live", "During pilot"
QS = [
    # process and flows
    ("Flow", "Should a proposal go out \"subject to availability\" while partners are still checking, or wait until partners confirm?",
     "Decides whether the brain warns or blocks when a specialist sends a proposal with open partner requests.",
     "Both options built, one setting: 'warn' (default) adds 'onder voorbehoud' while partners check; 'block' waits for all. A partner that said no always stops it.",
     "Inge, sales specialists", B4P, "High"),
    ("Flow", "Who creates a new customer in TravelSpirit when a first enquiry arrives? In live, may the brain create it through the two-way API?",
     "The brain opens a new relation from the mail and names it from the sign-off; it still has to exist in TravelSpirit.",
     "Opens the relation in the brain, marked for the specialist to check.", "Inge, in-house developer", B4P, "High"),
    ("Flow", "Can TravelSpirit send a signal when a trip is booked (webhook or event), or only be read on a schedule?",
     "With a signal, follow-ups are withdrawn and extras drafted within the hour instead of the next day.",
     "Reads bookings at the daily booking check.", "In-house developer, TravelSpirit", ANON, "Medium"),
    ("Flow", "A change or complaint from an address we do not know: who links it to the right family?",
     "Without a link the mail waits. Options: the specialist on duty, or the team lead's list.",
     "Built: listed for the team lead with suggested families (same surname, booking number); one click links it and remembers the address. Specialists may link too.",
     "Inge, team leads", B4P, "Medium"),
    ("Flow", "After how many days of silence should a follow-up be drafted? Once, or a second time later?",
     "Too early feels pushy, too late loses bookings.", "5 days after the proposal, once.", "Sales specialists", B4P, "Medium"),
    ("Flow", "After how many days should a partner be chased, and how often?",
     "Speed of availability answers.", "3 days after the request.", "Back office", B4P, "Medium"),
    ("Flow", "When should extras be offered, and who sends them?",
     "Extras right after booking can help revenue; too many mails annoy families.",
     "Right after booking, while more than 3 weeks remain; the specialist approves.", "Sales specialists", B4P, "Low"),
    ("Flow", "When is the roadbook with vouchers made and sent, and by whom?",
     "Sets the trigger and which screen it lands in.", "3 weeks before departure, once all partners confirmed; back office.",
     "Back office", B4P, "Medium"),
    ("Flow", "May we send next-trip ideas to former customers? Is there marketing consent, or a soft opt-in?",
     "Privacy law: commercial mail needs consent or an existing-customer soft opt-in with an easy way out.",
     "Drafts an idea 2 months after return, at most once a year; nothing is sent without approval.", "Inge, privacy contact", B4P, "High"),
    ("Flow", "Complaints: who approves replies, and what may be offered (refund, voucher, nothing without the team lead)?",
     "The brain blocks any money promise unless a team lead approves; the rule should match Travelnauts' policy.",
     "Only a team lead can approve a reply that mentions money.", "Inge, team leads", B4P, "High"),
    ("Flow", "Which knowledge notes may be approved by whom (destination knowledge, policies, house style)?",
     "Every note has an owner; unapproved notes are never used by agents.", "Content role approves; synthetic owners.",
     "Inge", ANON, "Medium"),
    # data and systems
    ("Systems", "TravelSpirit API documentation and a test account. Is January 2027 still the date for the two-way API?",
     "Replaces the fake TravelSpirit; the date decides when drafts can be written into the Visual Tour Builder.",
     "Fake TravelSpirit with synthetic data.", "In-house developer, TravelSpirit", ANON, "High"),
    ("Systems", "Where does the brain read mail: TravelSpirit Mail through the API, or the Exchange mailbox? Are attachments included?",
     "Decides the mail connector and how partner PDFs and invoices arrive.", "Mail comes from the fake TravelSpirit.",
     "In-house developer", ANON, "High"),
    ("Systems", "What do flight rows look like in TravelSpirit (field names, one row per leg)?",
     "The flight watch and roadbook read them; the brain now accepts the common names.", "Reads number and date under several names.",
     "In-house developer", ANON, "Low"),
    ("Systems", "Which n8n workflows from the freelancers still run, and which should the brain replace or leave alone?",
     "Avoids two systems sending the same mail.", "Inventory tool exists (brain n8n).", "Inge, in-house developer", ANON, "Medium"),
    ("Systems", "The Excel calculation template and the margin rules.", "Proposal prices must match how Travelnauts calculates.",
     "Sandbox margins.", "Inge, sales specialists", ANON, "High"),
    ("Systems", "Which Galileo commands does the team actually use?", "The brain writes commands; only allowed ones are produced.",
     "Placeholder command formats.", "Sales specialists", ANON, "Medium"),
    ("Data", "30 to 50 anonymised booked proposals and about 20 partner mails as examples.",
     "Teaches tone and structure, and gives a realistic test set.", "80 synthetic proposals.", "Inge", ANON, "High"),
    ("Data", "Current booking terms, payment terms and house style notes.", "Agents quote terms; wrong terms are a real risk.",
     "Placeholder policy notes.", "Inge", ANON, "High"),
    ("Data", "Team setup: which destinations per team, who is in which team, who owns which knowledge.",
     "Routing of requests and access rights.", "Synthetic teams (Asia, Africa, Americas).", "Inge", ANON, "High"),
    # azure, security, operations
    ("Azure", "Which Azure subscription and resource groups, and who is the owner at Travelnauts?",
     "Needed to deploy the test environment.", "Templates ready, CI compiles them.", "Travelnauts IT", B4P, "High"),
    ("Azure", "Entra ID: who registers the two apps, and which groups map to the roles (specialist, back office, team lead, content, admin)?",
     "Sign-in and role checks in pilot and live.", "Sign-in by picking a person (test only).", "Travelnauts IT", B4P, "High"),
    ("Operations", "Who receives alert mails, and which Teams channel gets the alerts?", "Someone must hear about a critical alert at night or on Sunday.",
     "Alerts built; recipients not set.", "Inge, Travelnauts IT", B4P, "High"),
    ("Operations", "Contacts for the runbook: administrator at Myt, privacy contact, TravelSpirit administrator, Azure owner.",
     "Incident procedures name who to call.", "Table empty in docs/runbook.md.", "Inge", B4P, "Medium"),
    ("Operations", "Monthly Azure budget and the daily model budget per environment.", "Hard stop for spend; alerts at 80% and 100%.",
     "EUR 150 test, 300 pilot, 600 live per month; EUR 5 a day for models.", "Jonas, Inge", B4P, "Medium"),
    ("Models", "Where does Gemma 4 run: an Azure GPU, a hosted endpoint, or another provider? Any data residency requirement (EU only)?",
     "Cost, speed and the processing agreement depend on it.", "Stand-in model.", "Jonas, Travelnauts IT", ANON, "High"),
    ("Privacy", "Log retention: are 30 days for prompts, tool calls and runs right? The audit trail is kept longer.",
     "Must match the processing agreement and the DPIA.", "30 days (setting BRAIN_RETENTION_DAYS).", "Privacy contact", B4P, "Medium"),
    ("Privacy", "Who leads the DPIA at Travelnauts, and who does the outside penetration test (and when)?",
     "Both are needed before customer data and customer channels.", "Not started.", "Inge, privacy contact", LIVE, "High"),
    # pilot organisation
    ("Pilot", "Who is in the pilot group (specialists and back office colleagues), and from which date?",
     "Accounts, training and the measurement baseline.", "Synthetic people.", "Inge", B4P, "High"),
    ("Pilot", "Who measures the baseline (minutes per request, time to first proposal) before the pilot starts?",
     "Without a baseline the gain, and the success fee, cannot be shown.", "The brain records edit share and timings from day one.",
     "Inge, Toh", B4P, "High"),
    ("Pilot", "What exactly counts for the success fee: which measure, measured how, over which period?",
     "No cure no pay needs a measure both sides accept in advance.", "Not defined in the sandbox.", "Jonas, Toh", B4P, "High"),
    ("Pilot", "Role of the in-house developer: access to the repository, reviews, backup for Myt?", "Continuity and knowledge transfer.",
     "Repository is private to Myt.", "Inge, Toh", B4P, "Medium"),
    ("Pilot", "When does Travelnauts' own administrator (beheerder) start?", "Hand-over of the runbook and daily checks.",
     "Myt is administrator.", "Inge", LIVE, "Medium"),
]

wb = Workbook()
ws = wb.active
ws.title = "Open questions"
title(ws, "Travelnauts company brain: open questions", "Fill in the yellow columns. Status: Open, Asked, Answered, Parked.")
header(ws, 4, Q_COLS)
rows = [(i, *q[:6], q[6], "Open", None, None) for i, q in enumerate(QS, 1)]
body(ws, 5, rows, input_cols=(9, 10, 11))
last = 4 + len(rows)
for r in range(5, last + 1):
    ws.cell(row=r, column=11).number_format = "dd-mm-yyyy"
ws.freeze_panes = "C5"
ws.auto_filter.ref = f"A4:K{last}"
dropdown(ws, "I", 5, last + 50, ["Open", "Asked", "Answered", "Parked"])
dropdown(ws, "H", 5, last + 50, ["High", "Medium", "Low"])
dropdown(ws, "G", 5, last + 50, [B4P, ANON, PILOT, LIVE])
done_grey(ws, "I", 5, last, len(Q_COLS), ["Answered", "Parked"])
ws.conditional_formatting.add(f"H5:H{last}", FormulaRule(formula=[f'$H5="High"'], font=Font(name=FONT, bold=True, color="B4441F")))
ws.page_setup.orientation = "landscape"
ws.page_setup.fitToWidth = 1
ws.sheet_properties.pageSetUpPr.fitToPage = True
ws.page_setup.fitToHeight = 0
summary(wb, "Open questions", "I", "H", "G", ["Open", "Asked", "Answered", "Parked"], ["High", "Medium", "Low"],
        [B4P, ANON, PILOT, LIVE], last, "Open questions: summary")
wb.save("build/Travelnauts open questions.xlsx")

# ---------------------------------------------------------------- tests and next steps
T_COLS = [("#", 5), ("Area", 14), ("What to test", 44), ("How", 46), ("Where", 14), ("Pass when", 38),
          ("Depends on", 16), ("Owner", 14), ("Status", 14), ("Result, notes", 36)]
SB, AZ_T, AZ_P, ANON_T = "Sandbox", "Azure test", "Pilot environment", "Anonymised data"
TESTS = [
    ("Model", "Gemma 4 against the stand-in model on the quality bench", "brain bench --gate with BRAIN_MODEL set to Gemma 4; compare per agent",
     SB, "All 11 bench limits met", "Q26 model hosting", "Myt"),
    ("Model", "Cost and speed per request with the real model", "Run the two-week simulation with the real model; read cost per day from Maintenance",
     AZ_T, "Within the daily model budget; first draft within 2 minutes", "Q25, Q26", "Myt"),
    ("Privacy", "Anonymiser on real mails", "200 real mails through brain ingest; a person checks every output", SB,
     "No names, addresses, phone numbers or booking numbers left", "Q18 samples", "Myt, Travelnauts"),
    ("TravelSpirit", "Read API: mails, relations, dossiers, flights", "Contract tests in tests/contract against the test account", AZ_T,
     "All fields mapped; no errors on 500 real records", "Q12, Q13", "Myt, in-house developer"),
    ("TravelSpirit", "TravelSpirit slow or down", "Timeouts and errors injected on the test account; check retries and alerts", AZ_T,
     "No lost mail; jobs wait and recover; alert raised", "Q12", "Myt"),
    ("Flow", "Sender matching on a real mailbox", "Run triage on a month of anonymised mail; count matched, new and unknown senders", ANON_T,
     "Over 95% of known families matched; no mail linked to the wrong family", "Q13", "Myt"),
    ("Flow", "Shared and changing family addresses", "Cases: two parents with different addresses, a shared address, a new address", ANON_T,
     "Linked to the right family or clearly marked for a person", "Q4", "Myt"),
    ("Flow", "Name from the sign-off on real mails", "Compare the extracted name with the relation in TravelSpirit", ANON_T,
     "Right or empty in 95%; never a wrong name", "Q2", "Myt"),
    ("Flow", "Triage on real mail (Dutch and English)", "Anonymised month of mail, labelled by a specialist", ANON_T,
     "Category right in 90%; injection flagged; no mail lost", "Q18", "Myt, specialists"),
    ("Flow", "Proposal quality", "Specialists rate brain drafts against their own, without knowing which is which", PILOT,
     "Average edit share falling week by week; no unsafe activity proposed", "Q16, Q19", "Specialists"),
    ("Flow", "Proposal before availability rule", "Build the chosen rule; replay the journey test", SB, "Rule applied in the journey test", "Q1", "Myt"),
    ("Flow", "Partner replies and PDFs", "20 real partner mails and offers through the partner desk", ANON_T, "Availability and price read right in 90%",
     "Q18", "Myt, back office"),
    ("Flow", "Invoice matching", "Real invoices against bookings", ANON_T, "Status right in 90%; no invoice approved by itself", "Q13", "Myt, back office"),
    ("Flow", "Galileo commands", "Commands for 10 real itineraries checked in a Galileo training environment", PILOT, "All commands valid; only allowed commands",
     "Q17", "Specialists"),
    ("Flow", "Go-live with existing bookings", "First booking check on a copy of real data, as a dry run", ANON_T,
     "Work only for trips still to come; no flood of drafts", "Q12", "Myt"),
    ("Flow", "Whole journey on real-shaped data", "scripts/journey.py adapted to the anonymised data", ANON_T,
     "Every hand-off happens by itself; 0 failed jobs", "Q12, Q13", "Myt"),
    ("Security", "Microsoft sign-in and roles", "Sign in with each pilot role; remove someone in Entra", AZ_T,
     "Right screens per role; a leaver loses access at once", "Q22", "Myt, Travelnauts IT"),
    ("Security", "Outside penetration test", "Independent party tests the pilot environment", AZ_P,
     "No high findings open", "Q28", "Travelnauts"),
    ("Security", "DPIA", "Walk through data flows, retention and risks with the privacy contact", AZ_P, "DPIA signed off", "Q27, Q28", "Travelnauts, Myt"),
    ("Azure", "Deploy from scratch", "Deploy workflow into the test resource group; smoke check", AZ_T, "Release answers /readyz within 5 minutes",
     "Q21", "Myt"),
    ("Azure", "Alerts reach people", "Stop the worker (dead man's switch), break /readyz, cause a failed job", AZ_T,
     "Mail and Teams message arrive within 15 minutes", "Q23", "Myt"),
    ("Azure", "Backup and restore on Azure", "Point-in-time restore to a new server, then scripts/backup_drill.sh", AZ_T,
     "Drill passes; restore time measured and acceptable", "Q21", "Myt"),
    ("Azure", "Scaling under load", "brain loadtest at three times the expected daily mail; watch the drain workers scale", AZ_T,
     "No mail handled twice; queue empty within the hour", "Q21", "Myt"),
    ("Operations", "Retention runs as agreed", "Check after 31 days that old logs are gone and the audit trail is intact", AZ_P,
     "Logs older than agreed are gone; audit chain ok", "Q27", "Myt"),
    ("People", "Screens with the pilot group", "Think-aloud sessions with 3 specialists and 2 back office colleagues", PILOT,
     "Each can do their daily work without help after one session", "Q29", "Toh, pilot group"),
    ("People", "Baseline against pilot", "Minutes per request and time to first proposal, before and during the pilot", PILOT,
     "Agreed gain reached (success fee measure)", "Q30, Q31", "Inge, Toh"),
]
STEPS = [
    ("Agree", "Contract and start date", "Sign the contract (no cure no pay) and agree the success fee measure.", "Now", "Both", "Q31"),
    ("Agree", "Inventory questionnaire", "Systems, workflows, costs and speed today.", "Now", "Travelnauts", ""),
    ("Agree", "Interviews", "3 to 5 sales specialists and 2 back office colleagues: how a request really runs.", "Now", "Myt", ""),
    ("Agree", "Decide the flow questions", "Go through the flow questions (Q1 to Q11) with Inge and two specialists.", "Now", "Both", "Q1 to Q11"),
    ("Build", "Build the agreed flow rules", "Availability rule, follow-up and chase timing, complaint policy, extras and roadbook timing.", "Now", "Myt", "Q1 to Q11"),
    ("Build", "Real TravelSpirit adapter", "Replace the fake TravelSpirit using the read API; contract tests.", "Anonymised stage", "Myt", "Q12, Q13"),
    ("Build", "Load anonymised examples", "Proposals, partner mails, terms and the calculation template.", "Anonymised stage", "Both", "Q16, Q18, Q19"),
    ("Build", "Real model", "Run and tune Gemma 4 on the bench; choose where it runs.", "Anonymised stage", "Myt", "Q26"),
    ("Azure", "Test environment", "Deploy in Travelnauts' subscription; Entra sign-in; alerts to the agreed people.", "Anonymised stage", "Both", "Q21, Q22, Q23"),
    ("Azure", "Backup drill on Azure", "Point-in-time restore drill; fill in the runbook contacts.", "Anonymised stage", "Myt", "Q24"),
    ("Privacy", "Processing agreement and DPIA", "Sign the processing agreement; complete the DPIA.", "Before pilot start", "Both", "Q27, Q28"),
    ("Pilot", "Baseline measurement", "Measure minutes per request before the pilot starts.", "Before pilot start", "Travelnauts", "Q30"),
    ("Pilot", "Onboard the pilot group", "Accounts, a short training, the screens, who to ask.", "Before pilot start", "Myt", "Q29"),
    ("Pilot", "Pilot on anonymised data", "Read only; drafts in the brain; weekly review of edit share, gaps and alerts.", "Pilot", "Both", ""),
    ("Pilot", "Weekly review", "30 minutes with Inge: numbers, problems, knowledge gaps, next changes.", "Pilot", "Both", ""),
    ("Live", "Penetration test", "Outside party tests the pilot environment; fix findings.", "Before live", "Travelnauts", "Q28"),
    ("Live", "Go or no-go", "Against agreed criteria: quality, time saved, no open high findings, DPIA done.", "Before live", "Both", "Q31"),
    ("Live", "Two-way API", "Write drafts into the Visual Tour Builder once the new API is available.", "Live", "Myt", "Q12"),
    ("Live", "Hand-over", "Runbook and daily checks to Travelnauts' administrator; Myt as adviser.", "Live", "Both", "Q33"),
    ("Later", "Phase 2", "Family app and the new website on the same backend.", "Later", "Both", ""),
    ("Repo", "Update docs/next-steps.md", "It still lists Postgres as untested; that is done.", "Now", "Myt", ""),
    ("Model", "Gemma 4 on the bench", "First sample on a GitHub runner (Actions > gemma); full bench on a GPU (docs/gemma.md).", "Now", "Myt", "Q26"),
    ("Azure", "Prompt Shields", "Turn on Azure AI Content Safety in the test environment and score the held-out attacks.", "Anonymised stage", "Myt", "Q21"),
]

wb = Workbook()
ws = wb.active
ws.title = "To test"
title(ws, "Travelnauts company brain: what to test", "Already tested in the sandbox: see docs/test-reports. Fill in the yellow columns.")
header(ws, 4, T_COLS)
RESULTS = {
    5: ("Running", "Sandbox part passed (4 Nov): flaky 30%, timeouts 50%, two hours down. 0 failed jobs, nothing lost or doubled, "
                   "about one try per pass while down, alert after an hour. Fixed: outages failed every job after 6 minutes; "
                   "failed calls vanished from the log. Still to do: the real test account."),
    7: ("Running", "Synthetic part passed (4 Nov): other parent, new address, shared address, colleague forward, +tags and capitals. "
                   "Never linked by itself; team lead links with suggestions and the address is remembered. Still to do: real mailbox."),
    8: ("Running", "Synthetic part passed (4 Nov): 89 of 89 right, then 16 of 24 on unseen cases before tuning (now 24 of 24), "
                   "never a wrong name. Old rule: 25 of 89 right, 12 wrong (named families after our own specialist). Real mail still to do."),
    9: ("Running", "English set of 20 mails and 10 English attacks added to the bench (4 Nov). Masking: 0 names left. Category score waits "
                   "for the real model (#1); the stand-in only reads Dutch."),
    1: ("Running", "CPU runs (4 and 5 Nov, Gemma 4 e4b): triage 100%, safety held, writing fixes confirmed in run 2. Hosted 31B "
                   "(5 Nov, 60 mails): category and destination 100% on clean, hard and English mail, proposals pass every check, "
                   "best writing so far; three polish points fixed after it. Next: e4b and 26B on an Azure GPU. "
                   "Reports: docs/test-reports/gemma4-e4b-cpu*.md and gemma4-31b-hosted.md"),
    2: ("Running", "CPU only: 112 s per mail, 489 s per proposal: not usable. Hosted 31B on a free tier: 37 s per mail, 50 s per "
                   "proposal, but 25 of 84 calls failed on the provider's side (now retried). Cost and speed on an Azure GPU still to measure."),
    11: ("Passed", "Both rules built and tested in the whole journey (4 Nov). Travelnauts picks one (Q1)."),
}
EXTRA = [
    ("Flow", "The specialist's and team lead's day", "scripts/journey_people.py: proposal, change, question, call, urgent mail from the road, unknown address, sick leave, leaver",
     SB, "Everything drafted before they look; urgent first; nothing left with someone who is away", "", "Myt", "Passed",
     "Passed (5 Nov) after 5 fixes, among them: a family stranded at the airport was triaged as a plain question; 'a night less in Bangkok' was not seen as a change."),
    ("Flow", "Automatic send", "10 unchanged approvals, the question, the 10 second countdown, Stop, checks still blocking, switch off",
     SB, "Only low-risk kinds; never early; never twice; a stop leaves it for the person", "", "Myt", "Passed", "Passed (5 Nov), API and browser."),
    ("Flow", "Partner portal with a local agent", "A real local agent answers one request in the portal on a phone, with an alternative and a question",
     AZ_P, "They find it easier than mail; nothing unclear left on our side", "", "Both", "To do",
     "Sandbox part passed (5 Nov): line by line, alternatives in one click, no family data shown, phone width, script in partner text stays text."),
    ("Data", "Duplicate families on the real export", "Run the duplicate list on the anonymised TravelSpirit export; a person checks 30 pairs",
     ANON_T, "Most 'likely' pairs are real doubles; few false alarms", "", "Both", "To do", "Sandbox part passed (5 Nov): planted doubles found, at most 3 false alarms on 60 families."),
    ("Security", "A fully compromised model", "Replace the model by a hostile one: false prices, money promises, 'booking confirmed', other families' names",
     SB, "Nothing sent without approval; model never sees other families; specialist cannot approve promises", "", "Myt", "Passed",
     "Passed (4 Nov) after a fix: follow-up, extras and next-trip mails with promises could be approved before."),
    ("Flow", "The back office day", "scripts/journey_backoffice.py: partner mail as partners write it, chasing, invoices, booking file",
     SB, "Replies read and matched; only silent partners chased; invoices checked; nothing dropped", "", "Myt", "Passed",
     "Passed (4 Nov) after 11 fixes, among them: no partner reply was read on real mail, 'EUR 1.240' read as 1.24, duplicate invoices missed."),
    ("Security", "Prompt Shields on unseen attacks", "Turn on Azure AI Content Safety Prompt Shields; score the 8 held-out English attacks", AZ_T,
     "Most held-out attacks flagged; no look-alikes flagged", "Q21", "Myt", "To do",
     "Rules alone catch 2 of 8 unseen attacks (4 Nov): expected for keyword rules. The hostile model test shows misses cannot do harm."),
]
rows = [(i, *t[:5], t[5], t[6], *(RESULTS.get(i) or ("To do", None))) for i, t in enumerate(TESTS, 1)]
rows += [(len(rows) + k, *e) for k, e in enumerate(EXTRA, 1)]
body(ws, 5, rows, input_cols=(9, 10))
last_t = 4 + len(rows)
ws.freeze_panes = "C5"
ws.auto_filter.ref = f"A4:J{last_t}"
dropdown(ws, "I", 5, last_t + 50, ["To do", "Running", "Passed", "Failed", "Blocked"])
dropdown(ws, "E", 5, last_t + 50, [SB, ANON_T, AZ_T, AZ_P, PILOT])
done_grey(ws, "I", 5, last_t, len(T_COLS), ["Passed"])
ws.conditional_formatting.add(f"I5:I{last_t}", FormulaRule(formula=['$I5="Failed"'], font=Font(name=FONT, bold=True, color="B4441F")))
ws.sheet_properties.pageSetUpPr.fitToPage = True
ws.page_setup.orientation = "landscape"
ws.page_setup.fitToHeight = 0

ws2 = wb.create_sheet("Next steps")
S_COLS = [("#", 5), ("Area", 12), ("Step", 30), ("What", 56), ("Phase", 18), ("Owner", 14), ("Depends on", 16),
          ("Target date", 13), ("Status", 14), ("Notes", 34)]
title(ws2, "Travelnauts company brain: next steps", "Q numbers refer to the open questions list. Fill in the yellow columns.")
header(ws2, 4, S_COLS)
rows = [(i, s[0], s[1], s[2], s[3], s[4], s[5], None, "Not started", None) for i, s in enumerate(STEPS, 1)]
body(ws2, 5, rows, input_cols=(8, 9, 10))
last_s = 4 + len(rows)
for r in range(5, last_s + 1):
    ws2.cell(row=r, column=8).number_format = "dd-mm-yyyy"
ws2.freeze_panes = "D5"
ws2.auto_filter.ref = f"A4:J{last_s}"
dropdown(ws2, "I", 5, last_s + 50, ["Not started", "In progress", "Done", "Blocked"])
dropdown(ws2, "F", 5, last_s + 50, ["Myt", "Travelnauts", "Both"])
done_grey(ws2, "I", 5, last_s, len(S_COLS), ["Done"])
ws2.sheet_properties.pageSetUpPr.fitToPage = True
ws2.page_setup.orientation = "landscape"
ws2.page_setup.fitToHeight = 0

sm = wb.create_sheet("Summary", 0)
title(sm, "Tests and next steps: summary", "Counts update by themselves as you fill in the lists.")
sm.column_dimensions["A"].width = 30
sm.column_dimensions["B"].width = 12
r = 4
for label, sheet, col, vals, lst in [("Tests by status", "To test", "I", ["To do", "Running", "Passed", "Failed", "Blocked"], last_t),
                                     ("Tests by where", "To test", "E", [SB, ANON_T, AZ_T, AZ_P, PILOT], last_t),
                                     ("Steps by status", "Next steps", "I", ["Not started", "In progress", "Done", "Blocked"], last_s),
                                     ("Steps by phase", "Next steps", "E", ["Now", "Anonymised stage", "Before pilot start", "Pilot", "Before live", "Live", "Later"], last_s)]:
    sm.cell(row=r, column=1, value=label).font = Font(name=FONT, bold=True, color=NAVY)
    sm.cell(row=r, column=2, value="Count").font = Font(name=FONT, bold=True, color=NAVY)
    for i, v in enumerate(vals, r + 1):
        sm.cell(row=i, column=1, value=v).font = Font(name=FONT, size=10)
        sm.cell(row=i, column=2, value=f"=COUNTIF('{sheet}'!${col}$5:${col}${lst},A{i})").font = Font(name=FONT, size=10)
    t = r + len(vals) + 1
    sm.cell(row=t, column=1, value="Total").font = Font(name=FONT, bold=True, size=10)
    sm.cell(row=t, column=2, value=f"=SUM(B{r + 1}:B{t - 1})").font = Font(name=FONT, bold=True, size=10)
    r = t + 2
wb.save("build/Travelnauts tests and next steps.xlsx")
print(len(QS), len(TESTS), len(STEPS))
