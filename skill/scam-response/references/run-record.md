# Run record: ledger, resume, states and recovery

## Ledger

LEDGER.md is written only by appending. One line per checkpoint (steps 3 to 10 and 12). Each line carries: delegations with step, expert, action, state, counts and failures; consent and answers in the person's words; writes with approval state; the results needed to resume; and the SHA-256 of the ledger before that line, from the file expert's hash action. An edit between checkpoints breaks the chain, and the replay names the line.

Without Yes 1 nothing is on disk until Yes 2. The ledger lines are held in chat and appended in order after Yes 2, each with the hash of the file before that append. A stopped run repeats only read steps.

## Resume

Resume starts at the first step without a `completed` line, also between visits. The read steps before it are sent again to rebuild their results (reads repeat; writes, consent and the person's earlier answers are not repeated), and their counts must equal the ledger's counts for those steps; a difference is shown as a gap. Consent is shown again. Within one run no file is read twice. New statements after a finished run start a new run number in the same folder; copied exhibits are found by their hash; there is no update mode.

## Missing statements

A missing or failed month is named on START-HERE and GAPS-AND-NEXT with where to download it. The run carries on and writes the pages for what was read; the payments of that month are added when it is read (resume at step 7).

## States

| State | What the run does |
|---|---|
| `completed` | Uses the real result; empty is "none found"; never widens unasked |
| `failed` | Logs step, source and error; continues steps that do not need it |
| `cancelled` | Stops dependent steps; reports reads and writes |
| `waiting_user` | Relays the expert's question word for word |
| `waiting_approval` | Names the write; repeats it only after the person confirms; a decline keeps nothing |

## Recovery

| Failure | Result |
|---|---|
| Source failed | "not read"; unlinked payments fall to "ask the holder"; its steps go to GAPS-AND-NEXT |
| First pass failed | stop list says "not finished" |
| Recording failed | "listen and quote by hand" |
| Statement failed | a gap |
| reconcile failed | the assistant compares, marked so |
| writing failed | plain frame from the payments page |
| Write or save-text failed | one retry, then the page stays in chat |
