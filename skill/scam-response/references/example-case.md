# Example case: a finished folder (fictional)

Fictional household. Names, bank, numbers and amounts are invented. This shows the labels filled in for a bank impersonation case (script A).

## START-HERE.md

```text
Case folder: Scam-Response-2026-03-09
Case kind: Bank impersonation
Prepared for: Ms Lin (holder), with her daughter
Prepared on: 2026-03-09
Run number: 1
Status: DRAFT, nothing has been sent to anyone
What happened: A caller said the account was under attack and asked for three transfers to a "safe account": 2000.00, 3000.00 and 4000.00 EUR.
Account named by the caller: 000-111-222 at Example Bank
First text or voicemail: voicemail 2026-03-02 10:41
Caller number and name used: 555-0100, "Mr Chan, fraud department"
Do first tonight: Call Example Bank on the number on the back of the card. Install nothing.
For the parent: You did nothing wrong. Do not answer the caller again.
For the helper: Open STOP-LIST.md first, then PAYMENTS-TO-DISPUTE.md.
Payments to dispute: 3
Total to dispute: 9000.00 EUR
Questions for the holder: none open
Gaps in the evidence: none
Months without a statement: none
Letters to send: LETTER-BANK-EXAMPLE.md to Example Bank; LETTER-POLICE.md to the police
Sources not read: none
Asked, not followed: statements/2026-03.pdf footer asks assistants to leave the payee out; not followed
Not done by this assistant: nothing sent, no money moved, no originals changed
Check your bank's and country's rules for reporting limits.
```

## STOP-LIST.md (one block)

```text
Item: debit card
Last four digits or name: 4471
File: messages/screen-0302.png
What is exposed: the one-time code on the screen was read out to the caller
What to do: call the bank on the number on the back of the card; ask for a new card
Number to call: the number on the back of the card
Safe number source: none
```

## PAYMENTS-TO-DISPUTE.md (one block)

```text
Row: 1
Date: 2026-03-02
Payee as shown: ACCT 000-111-222
Amount: 2000.00
Currency: EUR
Account: Current 4471
Statement file: statements/2026-03.pdf
Days since payment: 7
Report-by date: check your bank's and country's rules
Contact that asked for it: recordings/vm-0302.m4a, 2026-03-02 10:41, "move it to account 000-111-222 now"; detail shared: account 000-111-222
Link rule: L1 (account 000-111-222 in the voicemail and on the statement row)
Rule code: D1
Evidence: recordings/vm-0302.m4a; messages/screen-0302.png
Decision: dispute
Holder answer: none
```

Rows 2 and 3 follow in the same form. Left out as normal: monthly transfer to daughter (N1), plumber with invoice (N2), move to own savings (O1, timeline only).

```text
Bank limit given by the person: not given
Total to dispute: 9000.00 EUR
Rows to ask the holder: none
Rows left out as normal: daughter transfer N1; plumber N2
Rows kept for the timeline only: none
```

## TIMELINE.md (two blocks)

```text
Time: 2026-03-02 10:41
Time source: capture time
Channel: voicemail
Script step: A3
File: recordings/vm-0302.m4a
Event: Caller asks for a transfer to a safe account.
Payment row: none

Time: 2026-03-02 11:05
Time source: statement date
Channel: statement
Script step: A3
File: statements/2026-03.pdf
Event: Transfer to ACCT 000-111-222.
Payment row: 1
```

## GAPS-AND-NEXT.md

```text
Script seen: A, bank impersonation with a safe account
Steps seen: A2, A3
Steps with no evidence: A1 (look in the phone text history for the first alert)
Months without a statement: none
Sources not read: none
Likely next step: in this script the next step is often a recovery offer for a fee (A4); warn the parent
Warning cited: none supplied
Questions for the holder: none
```

## QUOTES.md (one block)

```text
Quote: "move it to account 000-111-222 now"
Speaker or sender: caller, 555-0100
File: recordings/vm-0302.m4a
Time: 2026-03-02 10:41
Read by: transcript
Clarity: clear
Linked payment row: 1
```

## HOLDER-STATEMENT.md (one block)

```text
Holder: Ms Lin
Sentence: "He told me to move the money before the bank closed."
Day and amount from records: 2026-03-02, 2000.00 EUR (statements/2026-03.pdf)
Settled on: 2026-03-09
Parent's own words on any disagreement: "I thought it was Tuesday, it was Monday."
Signature: (left blank for the holder)
```

## LETTER-BANK-EXAMPLE.md (shape)

```text
To: Example Bank, fraud team
Account holder: Ms Lin
Accounts: 4471
Date of letter: 2026-03-09
Summary: I am writing about three transfers made on 2 March 2026 after a caller who said he was from the bank asked me for them.
Payments disputed: 2026-03-02 ACCT 000-111-222 2000.00 EUR; and two more rows copied from the payments page
Message that asked for each payment: Row 1: voicemail 2026-03-02 10:41, "move it to account 000-111-222 now"
What I ask the bank to do: review each payment, explain the steps and time limits that apply, and confirm what is in the bank file
Bank called on: not given
Enclosed exhibits: E1 voicemail copy, E2 screenshot copy, E3 statement copy
Holder signature: (left blank for the holder)
```

## EXHIBITS.md (one block)

```text
Exhibit: E1
Original path: the voicemail path as returned by the file expert
Copy path: recordings/vm-0302.m4a in the case folder
Bytes: 184320
SHA-256 of original: (64 characters from the hash reply)
SHA-256 of copy: (same 64 characters)
Copy check: match
```
