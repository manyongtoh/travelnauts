# Usability and accessibility review

5 November 2026. Every view of every screen, in English and Dutch, checked against WCAG 2.1 AA with axe-core
(`build/a11y.py`), the keyboard path through the specialist screen, the partner portal on a phone, the screens at
1024 and 1280 pixels wide, and the ten usability heuristics (Nielsen). Before this review the role colours and
readability changes of the same day were already in.

## Automated check (WCAG 2.1 AA and best practice)

| Finding | Where | Fixed |
|---|---|---|
| Draft text boxes had no accessible name (critical) | specialist, back office, team lead | each is named after what it holds ("Draft travel proposal") |
| Dropdowns without a name (critical) | team lead reassign, users role | "Reassign to… r008", "Role: Sanne de Vries" |
| Budget field without a label (critical) | maintenance | labelled |
| Grey text on removed users at 2.9:1 contrast (serious) | users | removed users get a tinted row with readable text |
| Content outside landmarks (moderate, 56 views) | all screens | header, nav, main; layout unchanged |
| Heading order skipped a level | portal | fixed |
| Fields and buttons 34 to 39 px high on a phone | portal | at least 44 px to tap |

After the fixes: **0 findings on all 56 views and on the portal.**

## Heuristics

| Heuristic | Finding | What changed |
|---|---|---|
| Visibility of system status | A button gave no sign it was working; a second click could approve twice (the server refused it, with an error) | the button that starts an action is busy until the answer is in |
| Visibility of system status | Error messages vanished after 2.6 seconds, too fast to read a refusal with its reason | messages stay 3 seconds or longer, by length; read out to screen readers |
| Error prevention | Discard, Merge and Remove access acted on the first click, with no way back | they ask once more in place ("Click again to discard"), no pop-up, and disarm after 4 seconds |
| Recognition rather than recall | All screens looked the same; partner statuses were internal words ("unclear") | a colour per role, the role in the tab title, plain statuses |
| Aesthetic and minimalist design | Eight equal buttons under a draft | main actions visible, the rest under More actions |
| Flexibility and efficiency | No way past the menu for keyboard users | a Skip to content link; focus moves to the view you open |
| Consistency | Some Dutch screens still had English words | translated |
| Help users recover from errors | Family without a known name showed as "Family ·" | "New relation, name unknown" |
| Accessibility | Motion for people who turn it off | animations off when the system asks for reduced motion |

Keyboard: every action on the specialist screen can be reached with Tab and shows a visible focus ring.
At 1024 and 1280 pixels no screen scrolls sideways.

## Recommended next, needs people or a decision

1. **Test with five real users** from the pilot group, each doing five tasks (send a first proposal, handle a change,
   answer a question, accept a partner alternative, find why a trip is stuck). Five people find most problems.
2. **Undo after Approve and send**, like the 10 second hold of automatic send: a short window to take a mail back.
3. **Search and filters on All my trips** (family name, destination, status) once real volumes are in.
4. **Keyboard shortcuts** for people who approve all day (next item, approve, discard).
5. **House colours**: if the client has a palette, swap it in one place in the stylesheet.
