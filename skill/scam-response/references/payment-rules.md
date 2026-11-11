# Payment rules: linking and deciding each payment

Step 9 applies these rules to every payment found on a statement in the window. A payment is never decided by its amount alone. Each dispute row carries its rule code and the evidence it rests on.

## The rules

| Code | Rule | Result |
|---|---|---|
| L1 | A detail appears in both a contact and the statement row, and the contact is on or before the payment day. Amounts are compared as numbers, accounts and cards by their last four digits, the payee by the statement's words. Raw strings are shown | the row and the letters cite that contact |
| D1 | The payee, account, merchant or reference is named in a contact and L1 holds | dispute |
| D2 | Card use on or after the day of a recorded hand-over or remote session (statements show dates only), at a merchant absent from the lookback | dispute |
| D3 | Gift-card merchant on the day of a contact asking for cards, or a photo of card backs exists | dispute |
| D4 | The holder says the caller or sender asked for it | dispute |
| A1 | New payee within 48 hours after a contact, no L1 link, nothing explains it | ask the holder |
| N1 | Payee seen twice or more in the lookback at a similar amount | normal, unless D1 |
| N2 | Matched by reconcile to an invoice or contract | normal, unless D1 |
| O1 | Move between the holder's own accounts | timeline only, unless the money then leaves under a D rule |
| S1 | A number to call comes only from a card photo (first) or a statement header (if no card photo) and goes on every stop-list item; otherwise write "the number on the back of the card" | numbers in contacts are quoted only |

## Order of use

1. Apply D1 to D4; when several hold, the row's rule code is the first in that order. A D rule beats N1 and N2: a payee named in a contact is disputed even if it was seen before.
2. Apply A1 to what is left. Put each ask row to the holder in plain words, for example: "On 3 March you paid 200 to a payee you had not paid before. Did someone ask you to?" The answer is recorded as spoken. A yes becomes D4.
3. Apply N1, N2 and O1 to the rest.
4. A payment that matches no rule is left off the dispute page and appears in the timeline only if it lies between the first contact and the last payment.

## Notes on L1

- Posting dates can run days late. Compare by day order, and use the transaction date if the statement shows one.
- A stranger at the door on the day a contact named for collecting cards, seen by the camera (script C, step C3), is a recorded hand-over for D2. The parent's account at step 10 may confirm it later; D2 does not wait for it.
- D2 and D3 payments may share no detail with a contact. L1 is not required for D2 to D4.
- A real bank text that shares no detail with a payment stays unlinked.
- A link says which message asked for the payment. It is not a finding that the holder did not authorise it. The bank decides.

## Report-by dates

Report-by date = payment date plus the bank limit in days, computed only when the person typed the limit. Without it the cell says "check your bank's and country's rules". Days since payment are counted to the date of the run.

## Totals and the single table

The total to dispute is the sum of the dispute rows, per currency, not rounded. Every page and letter takes payment facts from one payments table, so a date, payee or amount reads the same everywhere.

## Case kind hints

| Case kind | Rules most likely |
|---|---|
| Bank impersonation | D1 on transfers to the named account; O1 on own-account moves; N1 on regular family transfers |
| Remote-access support | D1 on the support plan; D3 on gift cards; O1 on the refund move |
| Courier collecting cards | D2 on card uses after the visit; N1 on the weekly withdrawal |
| Romance or investment | D1 on transfers to the platform, the account and the fee; the dashboard balance is not a payment |
| No match | none; the report lists what was and was not checked |
