# Calculation helper

A first calculation for a trip, from a supplier's hotel rate sheet, in the layout specialists already use for a
dossier. The specialist checks and adjusts; nothing is booked or sent.

    brain calc trip.json --rates data/rates/hotels.xlsx --out trip.xlsx

`trip.json` holds the family, the start date, the stops (city, hotel, nights, optionally a room), transfers and
excursions (per person or per group, in the sheet's currency or another), and flights from the booking system's
quote. The format is in `brain/calc/trip.py`. Set `BRAIN_RATES` to skip `--rates`.

## What it does, per night

1. Only the contracts that apply to the client's market (`Settings.market`, default Europe): worldwide contracts
   that do not exclude it, or contracts that name it. Contracts for other markets are skipped.
2. The rate for that date and that day of the week (some hotels charge more on Friday and Saturday).
3. The room split: one family room first (`one_room_first`), parents and children apart, or two mixed rooms only
   when one room does not fit or does not exist. A room must take the party according to its "Max pax" text.
4. The cheapest correct way to price a room: every rate that covers the adults (DBL, TPL, a family or quad rate) is
   tried, with beds for the children beyond it: the first child shares a bed (often free), further children get a
   child's extra bed, and an adult's extra bed only when there is no child's one (and that is noted). A room that
   needs a bed the sheet has no price for is not an option.
5. Mandatory supplements on that date (peak season, gala dinners), per room or per person.
6. The cheapest contract over the whole stay; a promotion is used when cheapest and always flagged.

Then transfers, excursions and flights; everything converted to euro; a suggested price per adult and per child at
the target margin (hotels shared equally over everyone, the rest per person).

## What it is unsure of

The workbook has a sheet **Controleren** that lists every point to check, for example:

- the exchange rate (until the client's currency sheet is connected), the target margin, and from what age a child
  counts as an adult; all three are inputs on the CALC sheet, and the totals follow when they change
- minimum nights not met, children in a room of their own, an adult's extra bed for a child
- hotels or nights without a price, which show as 0 with a yellow mark
- a rate sheet older than a year for the travel date

## The workbook

- **CALC**: settings (yellow, with their source), the arrangement prices (blue: inputs, the margin follows), the
  margin calculation, the hotels per night with the contract as a comment, transfers and excursions, flights
- **Alternatieven**: the three cheapest other hotels per city that fit the family for the same nights
- **Controleren**: the checks, with a column to tick

## Not yet

- the client's currency sheet as the source of the exchange rate
- other suppliers' layouts (one reader per layout)
- writing the result back into the dossier spreadsheet or TravelSpirit
