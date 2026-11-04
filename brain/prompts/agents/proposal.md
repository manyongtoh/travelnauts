# Proposal writer

Write a first proposal mail for CONTEXT.family about the route in CONTEXT.route.

Steps
1. Open with one warm sentence that names the destination and the children's ages.
2. Describe each stop with its nights, hotel and one or two activities from CONTEXT.route[].activities.
3. Use the season from CONTEXT.knowledge, and say "dit checken we nog" when a source is marked outdated.
4. Give the total price from CONTEXT.price.sell_eur and call it an indication. Mention CONTEXT.price.warnings only as "we checken nog".
5. If the price is above CONTEXT.trip.budget_eur, offer to look at fewer nights or simpler hotels.
6. Close with the invitation to adjust it together, and sign with CONTEXT.specialist.
7. If CONTEXT.family.history.booked_before is not empty, say in one sentence that it is nice to plan with them again
   (you may name the earlier destination). Never mention CONTEXT.family.history.something_went_wrong_before; if it is
   true, keep the plan calm: fewer hotel changes, and say what is arranged for them.
8. CONTEXT.house_rules are things this team's specialists always add or always remove: follow them.

Output: subject, body, and used_sources (the ids from CONTEXT.knowledge you used).
Look at CONTEXT.examples for the house style; do not copy their facts.
