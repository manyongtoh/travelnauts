// Dutch and English. The screens are written in English; with Dutch on, every text a person sees is swapped through
// this dictionary as it appears (a MutationObserver), so new screens only need new lines here. '#' stands for a
// number. Customer content (mails, drafts) is never touched: it sits in <pre> and <textarea>, or carries data-raw.
// The choice is remembered per person in this browser.
const NL = {
  // frame and sign-in
  "Company brain": "Bedrijfsbrein", "switch": "wissel", "SANDBOX · MADE-UP DATA · NOTHING IS SENT": "SANDBOX · VERZONNEN GEGEVENS · ER WORDT NIETS VERSTUURD",
  "Synthetic data": "Synthetische data", "Specialist view": "Specialistenscherm", "Team lead view": "Teamleiderscherm", "Back office view": "Backofficescherm",
  "Maintenance": "Beheer", "User management": "Gebruikersbeheer", "Specialist view →": "Specialistenscherm →", "Team lead view →": "Teamleiderscherm →",
  "Back office view →": "Backofficescherm →", "Maintenance →": "Beheer →", "User management →": "Gebruikersbeheer →",
  "specialist": "specialist", "back office": "backoffice", "team lead": "teamleider", "product and content": "product en content", "admin": "beheer",
  "Not for your role": "Niet voor jouw rol", "cannot open this screen.": "kan dit scherm niet openen.", "Sign in as someone else": "Log in als iemand anders",
  "Travelnauts pilot · synthetic stage": "Travelnauts pilot · synthetische fase", "Pilot · synthetic stage": "Pilot · synthetische fase",
  "Pick who you are. In the pilot this is your Microsoft sign-in with a second factor (Entra ID); what you can see and do follows your role.":
    "Kies wie je bent. In de pilot is dit je Microsoft-login met een tweede factor (Entra ID); wat je ziet en mag hangt af van je rol.",
  "Sales specialists": "Reisspecialisten", "Own requests and drafts, knowledge, approve and send own drafts": "Eigen aanvragen en concepten, kennis, eigen concepten goedkeuren en versturen",
  "Partner requests, offers, Galileo, supplier watch": "Partneraanvragen, offertes, Galileo, leveranciersbewaking", "Team leads": "Teamleiders",
  "Team view and metrics, reassign, approve knowledge and exceptions": "Teamoverzicht en cijfers, herverdelen, kennis en uitzonderingen goedkeuren",
  "Write and approve knowledge": "Kennis schrijven en goedkeuren", "Admin (Myt)": "Beheer (Myt)",
  "Maintenance, users, budgets; no customer content by default": "Beheer, gebruikers, budgetten; standaard geen klantinhoud",
  "Signed in with Microsoft as": "Ingelogd met Microsoft als", "Continue": "Verder",
  "Good morning": "Goedemorgen", "Good afternoon": "Goedemiddag", "Good evening": "Goedenavond",
  "Copied. Paste it into TravelSpirit.": "Gekopieerd. Plak het in TravelSpirit.", "Select and copy the text": "Selecteer en kopieer de tekst",
  "Cannot open this file": "Dit bestand kan niet worden geopend",
  // specialist
  "Specialist dashboard": "Specialistendashboard", "Today": "Vandaag", "All my trips": "Al mijn reizen", "Ask the brain": "Vraag het brein", "Log": "Logboek",
  "waiting for you": "wachten op jou", "proposals sent": "voorstellen verstuurd", "new mails for triage": "nieuwe mails om te sorteren",
  "Waiting for you": "Wacht op jou", "Draft ready": "Concept klaar", "New request": "Nieuwe aanvraag", "Change requested": "Wijziging gevraagd",
  "Proposal sent": "Voorstel verstuurd", "Booked": "Geboekt", "Lost": "Verloren", "New": "Nieuw",
  "Incoming email": "Binnengekomen mail", "From": "Van", "Subject": "Onderwerp", "Received": "Ontvangen", "Triage tags": "Kenmerken",
  "Normal priority": "Normale prioriteit", "High priority": "Hoge prioriteit", "Low priority": "Lage prioriteit",
  "# days": "# dagen", "# night": "# nacht", "# nights": "# nachten", "# adult": "# volwassene", "# adults": "# volwassenen", "# child": "# kind", "# children": "# kinderen",
  "Calculation · # persons": "Calculatie · # personen", "Total for the family": "Totaal voor het gezin", "Total": "Totaal", "Margin": "Marge",
  "· margin € # · show lines": "· marge € # · toon regels", "Draft travel proposal": "Concept reisvoorstel", "Draft itinerary · # stops": "Conceptroute · # stops",
  "Edit freely. Your changes are measured to improve the brain.": "Pas gerust aan. Je wijzigingen worden gemeten om het brein te verbeteren.",
  "Edit freely before sending": "Pas gerust aan voor verzenden", "draft": "concept", "Sources": "Bronnen", "Availability:": "Beschikbaarheid:",
  "Owner": "Eigenaar", "review by": "herzien voor", "past review date, check first": "herzieningsdatum verstreken, eerst controleren",
  "Approve and send": "Goedkeuren en versturen", "Copy for TravelSpirit": "Kopieer voor TravelSpirit", "Discard": "Weggooien", "New version": "Nieuwe versie",
  "Quieter and cheaper versions": "Rustigere en voordeligere versies", "Suggest extras": "Extra's voorstellen", "Galileo commands": "Galileo-commando's",
  "Ask partners for availability": "Partners om beschikbaarheid vragen", "Call notes": "Belnotities", "Turn into a note": "Maak er een notitie van",
  "Agents prepare, you decide. Nothing goes to the family or a partner without your click.": "Agents bereiden voor, jij beslist. Niets gaat naar het gezin of een partner zonder jouw klik.",
  "Rough notes of the call: wishes, changes, questions, next steps": "Ruwe notities van het gesprek: wensen, wijzigingen, vragen, vervolgstappen",
  "# trips": "# reizen", "Everything assigned to you, newest first.": "Alles wat aan jou is toegewezen, nieuwste eerst.",
  "Knowledge desk": "Kennisbalie", "Ask": "Vraag",
  "Answers come only from approved knowledge, with sources. If the brain does not know, it says so and the question goes on your team's gap list.":
    "Antwoorden komen alleen uit goedgekeurde kennis, met bronnen. Weet het brein het niet, dan zegt het dat en komt de vraag op de hiatenlijst van je team.",
  "Audit log": "Auditlog", "What the agents did": "Wat de agents deden", "Every run, with the model, the sources used and how long it took.": "Elke run, met het model, de gebruikte bronnen en hoe lang het duurde.",
  "Every run, with the sources used and how long it took.": "Elke run, met de gebruikte bronnen en hoe lang het duurde.",
  "Time (UTC)": "Tijd (UTC)", "Agent": "Agent", "Result": "Resultaat",
  "Approved and marked as sent": "Goedgekeurd en gemarkeerd als verstuurd", "Approved. In the sandbox nothing is actually sent.": "Goedgekeurd. In de sandbox wordt niets echt verstuurd.",
  "Discarded. That is feedback for the brain too.": "Weggegooid. Ook dat is feedback voor het brein.", "Call note saved, wishes updated": "Belnotitie opgeslagen, wensen bijgewerkt",
  "Change request": "Wijzigingsverzoek", "Changed proposal ready to check": "Gewijzigd voorstel klaar om te controleren", "Current proposal": "Huidig voorstel",
  "Let the agent apply the change": "Laat de agent de wijziging verwerken", "Write travel proposal": "Reisvoorstel schrijven", "Draft follow-ups": "Opvolgmails opstellen",
  "Process new mail to fill your list.": "Verwerk nieuwe mail om je lijst te vullen.", "Nothing needs you": "Niets wacht op jou", "All done": "Alles klaar",
  "Versions": "Versies", "Suggested extras": "Voorgestelde extra's", "Nothing that fits yet": "Nog niets dat past", "Severity": "Ernst", "About": "Over",
  "travelling now": "nu op reis", "not travelling": "niet op reis", "Internal actions": "Interne acties", "Documents": "Documenten", "Roadbook (PDF)": "Reisboek (pdf)",
  "Voucher": "Voucher", "Suggestions": "Suggesties", "Next-trip idea": "Idee voor een volgende reis", "Next-trip ideas": "Ideeën voor een volgende reis",
  "Make roadbook and vouchers": "Reisboek en vouchers maken", "Draft mail": "Conceptmail", "Family": "Familie", "persons": "personen", "stops": "stops",
  "Availability still to be confirmed.": "Beschikbaarheid nog te bevestigen.", "partners confirmed": "partners bevestigd", "partners not asked yet.": "partners nog niet gevraagd.",
  "Sending adds: availability still to be confirmed.": "Bij verzenden komt erbij: beschikbaarheid nog te bevestigen.",
  "not available: choose an alternative": "niet beschikbaar: kies een alternatief", "price expired": "prijs verlopen",
  // automatic send
  "Send automatically from now on?": "Voortaan automatisch versturen?",
  "Sends in # s": "Verstuurt over # s", "Stop": "Stop", "Stopped. It waits for you.": "Gestopt. Het wacht op jou.", "Sent automatically": "Automatisch verstuurd",
  "Yes, send automatically": "Ja, automatisch versturen", "No, keep asking": "Nee, blijf vragen", "Automatic send": "Automatisch versturen",
  "Switch off": "Uitzetten", "Automatic send switched off": "Automatisch versturen uitgezet", "Fine, you keep approving them": "Prima, je blijft ze zelf goedkeuren", "Not sent:": "Niet verstuurd:", "follow-ups": "opvolgmails", "extras offers": "aanbod extra's", "partner reminders": "herinneringen aan partners", "on": "aan", "off": "uit",
  // team lead
  "Team lead": "Teamleider", "Overview": "Overzicht", "Complaints": "Klachten", "Value": "Waarde", "Insight": "Inzicht", "Knowledge": "Kennis", "Knowledge gaps": "Kennishiaten",
  "open requests": "open aanvragen", "proposals drafted": "voorstellen opgesteld", "approved": "goedgekeurd", "follow-ups": "opvolgmails", "knowledge gaps": "kennishiaten",
  "Figures are per team, never per person. They are here to share work fairly and to see where the brain needs help, not to judge anyone.":
    "Cijfers zijn per team, nooit per persoon. Ze zijn er om werk eerlijk te verdelen en te zien waar het brein hulp nodig heeft, niet om iemand te beoordelen.",
  "Team": "Team", "All": "Alle", "Asia": "Azië", "Africa": "Afrika", "Americas": "Amerika", "Team Asia": "Team Azië", "Team Africa": "Team Afrika", "Team Americas": "Team Amerika",
  "Share edited": "Aandeel aangepast", "of approved proposals, lower is better": "van goedgekeurde voorstellen, lager is beter", "Mail to first draft": "Van mail tot eerste concept",
  "# min": "# min", "agent time, not the specialist's": "tijd van de agent, niet van de specialist", "Agent runs, # h": "Agentruns, # u", "all logged with sources": "alles gelogd met bronnen",
  "Requests by status": "Aanvragen per status", "All teams, synthetic data": "Alle teams, synthetische data", "Inbox": "Inbox",
  "Mail in the (fake) TravelSpirit inbox, all teams": "Mail in de (nep) TravelSpirit-inbox, alle teams", "Triaged": "Gesorteerd", "Needs attention": "Vraagt aandacht",
  "What the agents flagged for a person": "Wat de agents voor een mens markeerden", "asked #×": "# keer gevraagd", "#×": "# keer",
  "Knowledge waiting for approval": "Kennis die wacht op goedkeuring", "Approve": "Goedkeuren", "Reject": "Afwijzen", "Past review date": "Herzieningsdatum verstreken",
  "review was due #-#-#, answers using it are flagged": "herziening was nodig op #-#-#, antwoorden die het gebruiken worden gemarkeerd",
  "# open · # handled": "# open · # afgehandeld", "Draft reply": "Conceptantwoord", "No open complaints": "Geen open klachten",
  "The complaint agent sorts each complaint and drafts a careful reply. It never promises money: refunds, compensation and discounts are your decision. High priority replies need your approval.":
    "De klachtenagent sorteert elke klacht en schrijft een zorgvuldig antwoord. Hij belooft nooit geld: terugbetaling, compensatie en korting zijn jouw beslissing. Antwoorden met hoge prioriteit hebben jouw goedkeuring nodig.",
  "medium priority": "gemiddelde prioriteit", "high priority": "hoge prioriteit", "low priority": "lage prioriteit", "no trip found": "geen reis gevonden",
  "Mail from an unknown address": "Mail van een onbekend adres", "Link to family…": "Koppel aan familie…", "Other family (id)…": "Andere familie (id)…",
  "remember this address": "onthoud dit adres", "Family id from TravelSpirit": "Familie-id uit TravelSpirit",
  "Which family wrote this? Never linked by the brain itself: the reply would go to this address.": "Welke familie schreef dit? Het brein koppelt dit nooit zelf: het antwoord zou naar dit adres gaan.",
  "Requests without an owner": "Aanvragen zonder eigenaar", "The specialist on these trips has left. Reassign them today.": "De specialist van deze reizen is vertrokken. Verdeel ze vandaag opnieuw.",
  "Reassign to…": "Herverdelen naar…", "Reassigned (logged)": "Herverdeeld (gelogd)", "Stuck requests": "Vastgelopen aanvragen",
  // value
  "What the brain is worth": "Wat het brein oplevert", "Period": "Periode",
  "Counted from what happened in the last # days. Hours saved is an estimate: drafts sent, times the minutes a person used to spend, minus what was rewritten.":
    "Geteld uit wat er de afgelopen # dagen gebeurde. Bespaarde uren zijn een schatting: verstuurde concepten, maal de minuten die iemand er vroeger aan kwijt was, min wat werd herschreven.",
  "The baseline is an assumption until Travelnauts measures it with the pilot group. Change it below; every figure updates.":
    "De nulmeting is een aanname tot Travelnauts die meet met de pilotgroep. Pas haar hieronder aan; alle cijfers rekenen mee.",
  "Hours saved (est.)": "Bespaarde uren (schatting)", "First proposal ready": "Eerste voorstel klaar", "# h": "# u", "was # h": "was # u", "Sent unchanged": "Ongewijzigd verstuurd",
  "rewritten #%": "herschreven #%", "rewritten –%": "herschreven –%", "Done unprompted": "Uit zichzelf gedaan", "drafts nobody asked for": "concepten waar niemand om vroeg",
  "Partner answered": "Partner antwoordde", "median # days": "mediaan # dagen", "median – days": "mediaan – dagen", "of # proposals sent": "van # verstuurde voorstellen",
  "Work": "Werk", "Drafted": "Opgesteld", "Sent": "Verstuurd", "Unchanged": "Ongewijzigd", "Minutes each": "Minuten per stuk",
  "Proposals": "Voorstellen", "Changes": "Wijzigingen", "Follow-ups": "Opvolgmails", "Partner chases": "Herinneringen aan partners", "Extras offers": "Aanbod extra's",
  "Roadbooks": "Reisboeken", "Answers": "Antwoorden", "Complaint replies": "Antwoorden op klachten", "Alternatives": "Alternatieven", "Next trip ideas": "Ideeën volgende reis",
  "Trip alerts": "Reiswaarschuwingen", "Hours to first proposal today": "Uren tot eerste voorstel nu", "Baseline measured": "Nulmeting gemeten", "Save baseline": "Nulmeting opslaan",
  "Download CSV": "Download CSV", "Baseline saved": "Nulmeting opgeslagen", "Nothing drafted in this period.": "Niets opgesteld in deze periode.",
  "Also: # invoices checked, # follow-ups withdrawn because the family wrote first, # knowledge gaps answered, # learned notes waiting for review, # suspicious mails held.":
    "Verder: # facturen gecontroleerd, # opvolgmails ingetrokken omdat het gezin eerst schreef, # kennishiaten beantwoord, # geleerde notities wachten op beoordeling, # verdachte mails tegengehouden.",
  // insight, knowledge, gaps
  "No report yet": "Nog geen rapport", "The insight agents run nightly and hourly.": "De inzichtagents draaien elke nacht en elk uur.", "Run them now": "Nu uitvoeren",
  "Insight refreshed": "Inzicht vernieuwd", "Customer insight": "Klantinzicht", "Top wishes": "Meest gevraagde wensen", "Former guests": "Oud-reizigers",
  "Totals per team: what families ask for, and where requests get stuck. Nothing per person.": "Totalen per team: waar gezinnen om vragen en waar aanvragen vastlopen. Niets per persoon.",
  "# items": "# items", "Agents only use approved knowledge. Each item has an owner and a review date.": "Agents gebruiken alleen goedgekeurde kennis. Elk item heeft een eigenaar en een herzieningsdatum.",
  "Show": "Toon", "Waiting for approval": "Wacht op goedkeuring", "Approved": "Goedgekeurd", "Item": "Item", "Review by": "Herzien voor", "Status": "Status", "waiting": "wacht",
  "No items match this filter.": "Geen items voor dit filter.", "Approved. Agents can use it now.": "Goedgekeurd. Agents kunnen het nu gebruiken.", "Rejected": "Afgewezen",
  "# open": "# open", "Question": "Vraag", "Why": "Waarom", "Asked": "Gevraagd", "weak source": "zwakke bron", "no answer": "geen antwoord", "No open gaps": "Geen open hiaten",
  "Questions the brain could not answer well, answers built on outdated knowledge, and drafts that specialists rewrote heavily. This tells the team what to write down next.":
    "Vragen die het brein niet goed kon beantwoorden, antwoorden op verouderde kennis en concepten die specialisten flink herschreven. Zo weet het team wat het als volgende moet opschrijven.",
  "Ask the brain something it does not know on the specialist screen to see one appear.": "Vraag het brein op het specialistenscherm iets wat het niet weet om er een te zien verschijnen.",
  "Added to the knowledge gap list of Team": "Toegevoegd aan de hiatenlijst van team", "Knowledge gap · weak source": "Kennishiaat · zwakke bron",
  // back office
  "Back office": "Backoffice", "Partner requests": "Partneraanvragen", "Mails to check": "Mails om te controleren", "Compare offers": "Offertes vergelijken", "Invoices": "Facturen",
  "Booking files": "Boekingsdossiers", "Supplier watch": "Leveranciersbewaking", "Partners": "Partners", "Partner desk agent": "Partneragent",
  "The agent writes, chases and compares. You approve and choose. Nothing goes to a partner without your click.": "De agent schrijft, herinnert en vergelijkt. Jij keurt goed en kiest. Niets gaat naar een partner zonder jouw klik.",
  "Open requests": "Open aanvragen", "across # trips": "over # reizen", "Waiting for your approval": "Wacht op jouw goedkeuring", "requests and reminders": "aanvragen en herinneringen",
  "Awaiting partner reply": "Wacht op antwoord partner", "sent by mail": "per mail verstuurd", "Overdue": "Te laat", "no reply after # days": "geen antwoord na # dagen",
  "Offers ready": "Offertes klaar", "compare and choose": "vergelijk en kies", "Avg partner reply": "Gem. antwoordtijd partner", "synthetic partners": "synthetische partners",
  "Draft reminders (#)": "Herinneringen opstellen (#)", "Simulate partner replies": "Simuleer antwoorden van partners", "To approve": "Goed te keuren",
  "Agent drafted, needs your click": "Door de agent opgesteld, wacht op jouw klik", "Room availability and price": "Kamerbeschikbaarheid en prijs", "Transfers and excursions": "Transfers en excursies",
  "Email · English": "E-mail · Engels", "Email · Dutch": "E-mail · Nederlands", "Let the agent draft the request": "Laat de agent de aanvraag opstellen", "Sent, waiting": "Verstuurd, wacht",
  "Reminder after # days without a reply": "Herinnering na # dagen zonder antwoord", "Agent chases after # days": "Agent herinnert na # dagen", "# d": "# d",
  "Overdue, draft a reminder": "Te laat, stel een herinnering op", "Chased": "Herinnerd", "Reminder sent": "Herinnering verstuurd",
  "Reminder sent; flagged if still silent": "Herinnering verstuurd; gemarkeerd als het stil blijft", "Answer needs reading": "Antwoord moet gelezen worden",
  "Question, alternative or 'we come back to you'": "Vraag, alternatief of 'we komen erop terug'", "Reply in, offer ready": "Antwoord binnen, offerte klaar",
  "Compare and choose": "Vergelijk en kies", "Declined": "Afgewezen", "Partner said no": "Partner zei nee", "# drafts": "# concepten",
  "Requests and reminders the partner desk wrote. Partners see a booking reference, never the family's name.": "Aanvragen en herinneringen die de partneragent schreef. Partners zien een boekingsreferentie, nooit de naam van het gezin.",
  "Nothing to check": "Niets te controleren", "New partner mails appear here.": "Nieuwe partnermails verschijnen hier.", "# trips with offers": "# reizen met offertes",
  "Ranked by availability, then price, then how reliable the partner has been.": "Gerangschikt op beschikbaarheid, dan prijs, dan hoe betrouwbaar de partner was.",
  "Partner": "Partner", "Offer": "Offerte", "Price": "Prijs", "Reliable": "Betrouwbaar", "Available": "Beschikbaar", "Not available": "Niet beschikbaar",
  "Not available, find another": "Niet beschikbaar, zoek een ander", "After choosing, book in TravelSpirit yourself. The agent never books.": "Boek na het kiezen zelf in TravelSpirit. De agent boekt nooit.",
  "No offers yet. Simulate partner replies on the board.": "Nog geen offertes. Simuleer antwoorden van partners op het bord.",
  "# invoices": "# facturen", "The invoice matcher compares each supplier invoice with the offer we accepted. Paying stays your decision.": "De factuurcontrole vergelijkt elke leveranciersfactuur met de offerte die we accepteerden. Betalen blijft jouw beslissing.",
  "Supplier": "Leverancier", "Invoice": "Factuur", "Invoiced": "Gefactureerd", "Agreed": "Afgesproken", "Note": "Notitie", "Matches": "Klopt", "Handled": "Afgehandeld",
  "Cannot place": "Niet te plaatsen", "Differs": "Wijkt af", "Duplicate": "Dubbel", "Check": "Controleren", "No invoices yet": "Nog geen facturen",
  "Invoices arrive by mail and are picked up after triage.": "Facturen komen per mail binnen en worden na het sorteren opgepakt.",
  "How was this resolved? (for example: credit note asked, not paid twice)": "Hoe is dit opgelost? (bijvoorbeeld: creditnota gevraagd, niet dubbel betaald)",
  "Marked as handled (logged)": "Gemarkeerd als afgehandeld (gelogd)", "Not run yet": "Nog niet uitgevoerd",
  "Every booked trip checked daily: partners confirmed, approved offer, flights, payment, insurance, passports, roadbook.": "Elke geboekte reis dagelijks gecontroleerd: partners bevestigd, offerte goedgekeurd, vluchten, betaling, verzekering, paspoorten, reisboek.",
  "Check now": "Nu controleren", "Booking files checked": "Boekingsdossiers gecontroleerd", "Trip": "Reis", "Destination": "Bestemming", "Departs": "Vertrek", "Missing": "Ontbreekt",
  "No booked trips": "Geen geboekte reizen", "complete": "compleet", "Daily check of partner prices, validity and response times. Nothing is changed automatically.": "Dagelijkse controle van partnerprijzen, geldigheid en antwoordtijden. Er wordt niets automatisch gewijzigd.",
  "Run the check now": "Controle nu uitvoeren", "Supplier watch done": "Leveranciersbewaking klaar", "What": "Wat", "Detail": "Detail", "No findings": "Geen bevindingen",
  "# partners": "# partners", "Slowest first. The partner desk chases these sooner.": "Traagste eerst. De partneragent herinnert deze eerder.", "Kind": "Soort",
  "Days to reply": "Dagen tot antwoord", "hotel": "hotel", "local agent": "lokale agent", "transfer": "transfer", "Partner mail to match": "Partnermail om te koppelen",
  "Read the reply:": "Lees het antwoord:", "Applied": "Verwerkt", "Matched; the agent reads it now (logged)": "Gekoppeld; de agent leest het nu (gelogd)",
  "Still silent after a reminder: phone them or choose another": "Nog steeds stil na een herinnering: bel ze of kies een ander",
  "Request drafted, check it before sending": "Aanvraag opgesteld, controleer voor verzenden", "reminders drafted, check them before sending": "herinneringen opgesteld, controleer voor verzenden",
  "Unknown sender": "Onbekende afzender", "to send": "te versturen", "Breakfast included": "Ontbijt inbegrepen", "Family room available": "Familiekamer beschikbaar",
  // maintenance
  "Health": "Gezondheid", "Agents": "Agents", "Queue": "Wachtrij", "Evals": "Evaluaties", "Audit chain": "Auditketen", "Tool server": "Toolserver",
  "Admin · no customer content": "Beheer · geen klantinhoud", "No open alerts": "Geen open meldingen", "The morning check runs every # minutes.": "De controle draait elke # minuten.",
  "agent runs, # h": "agentruns, # u", "errors": "fouten", "failed": "mislukt", "intact": "intact", "audit chain": "auditketen",
  "This screen shows no customer content. Opening a mail is a break-glass action and is written to the audit chain.": "Dit scherm toont geen klantinhoud. Een mail openen is een noodtoegang en wordt in de auditketen vastgelegd.",
  "Connections": "Koppelingen", "Every outside system, through its own connector": "Elk extern systeem, via een eigen koppeling", "fake": "nep",
  "Model budget": "Modelbudget", "Daily cap for this environment; agents stop when it is reached": "Daglimiet voor deze omgeving; agents stoppen als die bereikt is",
  "Spent today": "Vandaag besteed", "Cap": "Limiet", "Set cap": "Limiet instellen", "Budget cap set (logged)": "Budgetlimiet ingesteld (gelogd)", "Tools": "Tools",
  "Run the scheduler now": "Planner nu uitvoeren", "Last # hours": "Laatste # uur", "Pause an agent: its jobs wait in the queue until you resume it. Every pause is logged.": "Pauzeer een agent: zijn taken wachten in de wachtrij tot je hem hervat. Elke pauze wordt gelogd.",
  "Runs": "Runs", "Errors": "Fouten", "Avg ms": "Gem. ms", "Pause": "Pauzeren", "Resume": "Hervatten", "Work queue": "Werkwachtrij", "Failed jobs": "Mislukte taken", "Job": "Taak",
  "Error": "Fout", "No failed jobs": "Geen mislukte taken", "Stuck for more than an hour": "Langer dan een uur vast", "Nothing stuck": "Niets vast", "Retry": "Opnieuw", "Retry all failed": "Alle mislukte opnieuw",
  "Queued again": "Opnieuw in de wachtrij", "All gates pass. A change that drops below a gate is blocked in CI.": "Alle drempels gehaald. Een wijziging die onder een drempel zakt, wordt in CI tegengehouden.",
  "Gate": "Drempel", "Limit": "Grens", "Hard mails (not gated: the yardstick for a real model)": "Moeilijke mails (geen drempel: de maatstaf voor een echt model)",
  "Triage category #% · change requests understood #% · knowledge answered #%": "Sorteercategorie #% · wijzigingsverzoeken begrepen #% · kennis beantwoord #%",
  "# entries · head #": "# regels · kop #", "Actor": "Door", "Action": "Actie", "Object": "Object", "Hash": "Hash", "# tools": "# tools",
  "The single door to TravelSpirit, the calculation, knowledge and outside data. Each agent only has the tools it needs. Also published over MCP.": "De enige deur naar TravelSpirit, de calculatie, kennis en externe data. Elke agent heeft alleen de tools die hij nodig heeft. Ook gepubliceerd via MCP.",
  "Tool": "Tool", "Access": "Toegang", "read": "lezen", "text": "tekst", "No eval report yet": "Nog geen evaluatierapport", "Models": "Modellen", "Knowledge index": "Kennisindex",
  "Flight data": "Vluchtgegevens", "stand-in": "vervanger", "flight number and date only": "alleen vluchtnummer en datum", "Refresh now": "Nu vernieuwen", "Run": "Uitvoeren",
  "# calls in # h · # denied · # errors · # from cache": "# aanroepen in # u · # geweigerd · # fouten · # uit cache", "# calls, # failed, # escalated, # fallbacks": "# aanroepen, # mislukt, # geëscaleerd, # terugvallers",
  // users
  "Users": "Gebruikers", "Invite": "Uitnodigen", "Roles follow Entra ID app roles": "Rollen volgen de app-rollen in Entra ID", "# people · next access review #-#-#": "# mensen · volgende toegangscontrole #-#-#",
  "Change a role or remove access the day someone leaves. Every change is written to the audit chain. Nobody here sees performance per person.": "Wijzig een rol of trek toegang in op de dag dat iemand vertrekt. Elke wijziging komt in de auditketen. Niemand ziet hier prestaties per persoon.",
  "Name": "Naam", "Email": "E-mail", "Role": "Rol", "Last active": "Laatst actief", "Sales specialist": "Reisspecialist", "Product and content": "Product en content", "Admin": "Beheer",
  "Remove access": "Toegang intrekken", "never": "nooit", "New colleague": "Nieuwe collega", "In Azure this sends an Entra ID invitation with the chosen app role.": "In Azure stuurt dit een Entra ID-uitnodiging met de gekozen app-rol.",
  "Work email": "Werkmail", "None": "Geen", "Invited (logged)": "Uitgenodigd (gelogd)", "Role changed (logged)": "Rol gewijzigd (gelogd)", "Saved and logged": "Opgeslagen en gelogd",
  // partner portal (local agents see it in English; the specialist side follows this switch)
  "Partner portal": "Partnerportaal", "Portal link": "Portaallink", "Copy portal link": "Kopieer portaallink", "Portal link copied": "Portaallink gekopieerd",
  "Asking hotel": "Vraagt hotel", "Confirmed": "Bevestigd", "Alternative offered": "Alternatief aangeboden", "Accept alternative": "Alternatief accepteren", "Valid until": "Geldig tot",
  "Line": "Regel", "Thread": "Gesprek", "Round #": "Ronde #", "Answered in the portal": "Beantwoord in het portaal",
  // duplicates
  "Duplicate records": "Dubbele records", "Merge": "Samenvoegen", "Keep apart": "Apart houden", "Evidence": "Bewijs", "Merged (logged)": "Samengevoegd (gelogd)",
  // agent names in logs
  "triage": "sorteren", "proposal writer": "voorstelschrijver", "partner desk": "partneragent", "knowledge desk": "kennisbalie", "invoice matcher": "factuurcontrole",
  "complaints": "klachten", "alternatives": "alternatieven", "extras": "extra's", "roadbook": "reisboek", "change": "wijziging", "team insight": "teaminzicht", "next trip": "volgende reis",
  "call notes": "belnotities", "booking check": "boekingscontrole", "answered": "beantwoord", "answered #": "beantwoord #", "gap": "hiaat", "Model": "Model", "Language": "Taal", "queued,": "in wachtrij,", "queued": "in wachtrij",
};
// Whole-text patterns that carry names or dates.
const NL_RULES = [
  [/^Good (morning|afternoon|evening), (.+)$/, (m, p, n) => ({morning: "Goedemorgen", afternoon: "Goedemiddag", evening: "Goedenavond"})[p] + ", " + n],
  [/^Family (.+?)( · .+)?$/, (m, n, rest) => "Familie " + n + (rest || "")],
  [/^Owner (.+) · review by (.+)$/, (m, o, d) => `Eigenaar ${o} · herzien voor ${d}`],
  [/^Automatic send on for (.+)$/, (m, x) => "Automatisch versturen aan voor " + (NL[x] || x)],
  [/^Automatic send: (.*)$/, (m, x) => "Automatisch versturen: " + x],
  [/^You sent the last (\d+) (.+?) without changing a word\. Send them automatically from now on\? Each one waits (\d+) seconds on screen with a Stop button first, and every check still applies\.$/,
    (m, n, k, s) => `Je hebt de laatste ${n} ${NL[k] || k} verstuurd zonder een woord te veranderen. Voortaan automatisch versturen? Elk bericht staat eerst ${s} seconden op je scherm met een Stop-knop, en alle controles blijven gelden.`],
  [/^Not sent: (.+)$/, (m, x) => "Niet verstuurd: " + x],
  [/^Model: (.+)$/, (m, x) => "Model: " + x],
  [/^Minutes per (.+) today$/, (m, x) => `Minuten per ${(NL[x] || x).toLowerCase()} nu`],
];

let LANG = "en";
try { LANG = localStorage.getItem("lang:" + (localStorage.getItem("me") || "")) || localStorage.getItem("lang") || "en"; } catch {}
const NUM = /\d+(?:[.,:]\d+)*/g;
function T(text) {
  if (LANG !== "nl" || !text) return text;
  const lead = text.match(/^\s*/)[0], trail = text.match(/\s*$/)[0], core = text.trim().replace(/\s+/g, " ");
  if (!core) return text;
  let out = NL[core];
  if (out === undefined) {
    const nums = core.match(NUM);
    if (nums) { const t = NL[core.replace(NUM, "#")]; if (t !== undefined) { let i = 0; out = t.replace(/#/g, () => nums[i++] ?? "#"); } }
  }
  if (out === undefined) for (const [re, f] of NL_RULES) { const m = core.match(re); if (m) { out = f(...m); break; } }
  return out === undefined ? text : lead + out + trail;
}
const SKIP = new Set(["SCRIPT", "STYLE", "TEXTAREA", "PRE", "CODE"]);
function translateTree(root) {
  if (LANG !== "nl") return;
  if (root.nodeType === 3) { const p = root.parentElement; if (p && !SKIP.has(p.tagName) && !p.closest("[data-raw]")) { const t = T(root.nodeValue); if (t !== root.nodeValue) root.nodeValue = t; } return; }
  if (root.nodeType !== 1 || root.closest("[data-raw]")) return;
  for (const a of ["placeholder", "title", "aria-label"]) { const v = root.getAttribute(a); if (v) { const t = T(v); if (t !== v) root.setAttribute(a, t); } }
  if (SKIP.has(root.tagName)) return;
  for (const c of root.childNodes) translateTree(c);
}
function setLang(l) {
  try { localStorage.setItem("lang:" + (localStorage.getItem("me") || ""), l); localStorage.setItem("lang", l); } catch {}
  location.reload();
}
document.documentElement.lang = LANG;
if (LANG === "nl") {
  const start = () => {
    translateTree(document.body);
    new MutationObserver(ms => ms.forEach(m => m.type === "characterData" ? translateTree(m.target) : m.type === "attributes" ? translateTree(m.target) : m.addedNodes.forEach(translateTree)))
      .observe(document.body, {childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ["placeholder", "title", "aria-label"]});
  };
  document.body ? start() : document.addEventListener("DOMContentLoaded", start);
  const _prompt = window.prompt.bind(window), _confirm = window.confirm.bind(window);
  window.prompt = (msg, d) => _prompt(T(msg), d);
  window.confirm = msg => _confirm(T(msg));
}
