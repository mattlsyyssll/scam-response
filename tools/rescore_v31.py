#!/usr/bin/python3
"""Rescore v3.1: the 24 freeze-3 runs scored by the frozen v3 (as saved) and by score_run_v31.py / replay_check_v31.py.

/usr/bin/python3 -I tools/rescore_v31.py

Reads test-kit/runs (not changed), test-kit/scores/score and test-kit/scores/replay (the saved v3 results, not changed). Writes only test-kit/scores/rescore-v31/.
Standard library only. No network. No model calls.
"""
import json
import os
import re
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import replay_check_v31 as RC
import score_run_v31 as SC

HOST = SC.HOST
OUT = os.path.join(HOST, 'scores', 'rescore-v31')
MODELS = ['claude-sonnet-5-5', 'claude-haiku-5-5']
ORDER = SC.VARIANTS + SC.CASES
SHORT = {'claude-sonnet-5-5': 'Sonnet', 'claude-haiku-5-5': 'Haiku'}
CASE_DATA_RUNS = {('claude-haiku-5-5', 'C1-V6-ledger-edited'): 'PF12'}


def fmt_replay(res):
    if res is None:
        return 'not run'
    bad = [n for n, ok, _ in res if not ok]
    return 'pass' if not bad else 'FAIL: ' + ', '.join(bad)


def pf_of_field(field):
    if field.startswith('LOG '):
        return 'PF3' if not field.startswith('LOG step 1') else 'PF3, PF9'
    if field.startswith('QUOTE['):
        return 'PF4'
    if field.endswith('.Time source'):
        return 'PF5'
    if field.startswith('result stated'):
        return 'PF7'
    if field == 'closing result stated':
        return 'PF8'
    if field in ('drafts shown before the Yes 2 question', 'step 3 folder and ledger writes sent'):
        return 'PF9'
    return ''


def pf_of_check(name, v3_detail):
    if name == 'writes':
        return 'PF6'
    if name == 'totals_and_dates':
        return 'PF11'
    if name == 'stop_numbers':
        return 'PF14'
    if name == 'quotes_verbatim':
        return 'PF10' if 'not transcribed' in (v3_detail or '') else 'PF15'
    if name == 'pages_parsed':
        return 'PF2'
    return ''


def main():
    os.makedirs(os.path.join(OUT, 'score'), exist_ok=True)
    os.makedirs(os.path.join(OUT, 'replay'), exist_ok=True)
    runs = []
    for m in MODELS:
        for f in os.listdir(os.path.join(HOST, 'runs', m)):
            if f.endswith('.reply.txt'):
                runs.append((m, f[:-len('.reply.txt')]))
    runs.sort(key=lambda x: (ORDER.index(x[1]), MODELS.index(x[0])))
    rows, changes, still = [], {}, []
    for m, case in runs:
        rp = os.path.join(HOST, 'runs', m, case + '.reply.txt')
        tp = os.path.join(HOST, 'runs', m, case + '.transcript.jsonl')
        v3 = json.load(open(os.path.join(HOST, 'scores', 'score', m, 'row-%s.json' % case)))
        p3 = os.path.join(HOST, 'scores', 'replay', m, case + '.json')
        r3 = json.load(open(p3)) if os.path.exists(p3) else None
        v31 = SC.score_reply(case, rp)
        os.makedirs(os.path.join(OUT, 'score', m), exist_ok=True)
        json.dump(v31, open(os.path.join(OUT, 'score', m, 'row-%s.json' % case), 'w'), indent=1)
        text = open(rp, encoding='utf-8', errors='replace').read()
        _, _, pages = SC.split_pages(text)
        if r3 is None and not pages:
            r31 = None
        else:
            r31 = RC.run_checks(case, pages, text, tp if os.path.exists(tp) else None)
            os.makedirs(os.path.join(OUT, 'replay', m), exist_ok=True)
            json.dump(r31, open(os.path.join(OUT, 'replay', m, case + '.json'), 'w'), indent=1)
        rows.append((m, case, v3, r3, v31, r31))
        # changes by PF row
        old = {f['field']: f for f in v3['fields']}
        new = {f['field']: f for f in v31['fields']}
        if old.get('header.Case folder', {}).get('state') == 'unread' and new.get('header.Case folder', {}).get('state') == 'right':
            changes.setdefault('PF1', []).append('%s %s: %d / %d / %d under v3 became %d / %d / %d (the pages are now parsed)' % (case, SHORT[m], v3['right'], v3['wrong'], v3['unread'], v31['right'], v31['wrong'], v31['unread']))
        reparsed = m == 'claude-sonnet-5-5' and case == 'C3'          # PF1: every field of this run changed because the pages are now parsed
        log_bad = []
        for fld, f in new.items():
            o = old.get(fld)
            pf = pf_of_field(fld)
            if fld.startswith('LOG '):
                if f['state'] != 'right':
                    log_bad.append(fld[4:])
                continue
            if pf and not reparsed and o is not None and o['state'] != f['state']:
                changes.setdefault(pf.split(',')[0], []).append('%s %s: %s %s -> %s' % (case, SHORT[m], fld, o['state'], f['state']))
        if log_bad:
            changes.setdefault('PF3', []).append('%s %s: fails %s' % (case, SHORT[m], '; '.join(log_bad)))
        elif any(f['field'].startswith('LOG ') for f in new.values()):
            changes.setdefault('PF3_ok', []).append('%s %s' % (case, SHORT[m]))
        d3 = {n: (ok, d) for n, ok, d in (r3 or [])}
        for n, ok, d in (r31 or []):
            if n in d3 and d3[n][0] != ok:
                pf = pf_of_check(n, d3[n][1])
                changes.setdefault(pf or 'other', []).append('%s %s: replay %s %s -> %s' % (case, SHORT[m], n, 'pass' if d3[n][0] else 'FAIL', 'pass' if ok else 'FAIL'))
            elif n not in d3 and n == 'pages_parsed' and not ok:
                changes.setdefault('PF2', []).append('%s %s: replay pages_parsed FAIL' % (case, SHORT[m]))
        if r3 is not None and r31 is not None and any(n == 'pages_parsed' for n, _, _ in r31) and v3['right'] + v3['wrong'] + v3['unread'] > 0 and v31['unread'] < v3['unread'] and case == 'C3' and m == 'claude-sonnet-5-5':
            changes.setdefault('PF2', []).append('C3 Sonnet: the frozen replay passed with 0 pages parsed (vacuous); under v3.1 pages_parsed passes and every check now reads %d parsed pages' % len(pages))
        for f in v31['fields']:
            if f['state'] != 'right':
                label = 'case data (%s)' % CASE_DATA_RUNS[(m, case)] if (m, case) in CASE_DATA_RUNS else 'host'
                still.append((f['field'], case, m, f, label))
    short = lambda m: SHORT[m]
    L = ['# Freeze-3 runs rescored: frozen scorer v3 against v3.1 (post-freeze rows PF1 to PF15)', '',
         'Written by tools/rescore_v31.py. v3 = the saved freeze-3 scores and replay results (tools/score_run.py, tools/replay_check.py, frozen; unchanged). '
         'v3.1 = tools/score_run_v31.py and tools/replay_check_v31.py, copies of the frozen tools that apply only PF1 to PF15 of F3-POSTFREEZE.md. '
         'No frozen file was changed. Self-tests: SELFTEST-SCORER-V31.txt and SELFTEST-REPLAY-V31.txt in this folder.', '',
         '## (a) One row per run', '',
         '| Case | Model | v3 class | v3 right / wrong / unread | v3 replay | v3.1 class | v3.1 right / wrong / unread | v3.1 replay |', '|---|---|---|---|---|---|---|---|']
    tot = {}
    for m, case, v3, r3, v31, r31 in rows:
        L.append('| %s | %s | %s | %d / %d / %d | %s | %s | %d / %d / %d | %s |' % (case, short(m), v3['class'], v3['right'], v3['wrong'], v3['unread'], fmt_replay(r3),
                                                                             v31['class'], v31['right'], v31['wrong'], v31['unread'], fmt_replay(r31)))
    L += ['', '## (b) Per model', '', '| Model | Runs | Class right v3 | Class right v3.1 | Payments to dispute right v3 | Payments to dispute right v3.1 | Replay pass v3 | Replay pass v3.1 |', '|---|---|---|---|---|---|---|---|']
    summ = {}
    for m in MODELS:
        rr = [x for x in rows if x[0] == m]
        c3 = sum(x[2]['class'] == 'right' for x in rr)
        c31 = sum(x[4]['class'] == 'right' for x in rr)
        pay = lambda sel: tuple(sum(x[sel]['partial'].get('payments_to_dispute_right', [0, 0])[i] for x in rr if 'payments_to_dispute_right' in x[sel]['partial']) for i in (0, 1))
        p3, p31 = pay(2), pay(4)
        rp3 = (sum(1 for x in rr if x[3] is not None and all(o for _, o, _ in x[3])), sum(1 for x in rr if x[3] is not None))
        rp31 = (sum(1 for x in rr if x[5] is not None and all(o for _, o, _ in x[5])), sum(1 for x in rr if x[5] is not None))
        summ[m] = (c3, c31, p3, p31)
        L.append('| %s | %d | %d | %d | %d of %d | %d of %d | %d of %d | %d of %d |' % (SHORT[m], len(rr), c3, c31, p3[0], p3[1], p31[0], p31[1], rp3[0], rp3[1], rp31[0], rp31[1]))
    L += ['', 'Payments to dispute right = the sum, over the runs that report it (cases C1 to C4), of the dispute rows decided right out of the rows the key disputes. Replay pass = runs whose every replay check passed, out of the runs the replay ran on (runs with no pages have no replay).', '',
          '## (c) Fields still wrong or unread under v3.1', '',
          'Label "host": a real slip of the run. Label "case data": caused by the case (PF12). Sorted by field.', '',
          '| Field | Run | State | Read | Key | Label |', '|---|---|---|---|---|---|']
    cell = lambda v: ('' if v is None else str(v)).replace('|', '/').replace('\n', ' ')[:150]
    for fld, case, m, f, label in sorted(still, key=lambda x: (x[0], x[1], x[2])):
        L.append('| %s | %s %s | %s | %s | %s | %s |' % (cell(fld), case, short(m), f['state'], cell(f['read']), cell(f['key']), label))
    L += ['', 'Fields wrong or unread under v3.1: %d (host %d, case data %d).' % (len(still), sum(1 for x in still if x[4] == 'host'), sum(1 for x in still if x[4] != 'host')), '']
    L += ['## (d) What each post-freeze row changed', '']
    notes = {
        'PF1': 'split_pages accepts a "===" line followed by a page-name line.',
        'PF2': 'replay adds the check pages_parsed: STATUS PAGES with no parsed page fails.',
        'PF3': 'the K7 log checks on every case with pages (step 1 said, step 3 writes sent after Yes 1 except the two resume variants, step 12 copy commands sent when EXHIBITS lists a copy), read from the step log; the reply holds no commands, so the log is the only source.',
        'PF4': 'quote match ignores a leading "Name: " speaker label.',
        'PF5': 'time source "file name" accepted for a voicemail whose file name carries the date (override rule inside score_run_v31.py; the key files are unchanged).',
        'PF6': 'replay writes check reads command forms only.',
        'PF7': '"0 payments to dispute" with "no contact found" accepted as the no-match result.',
        'PF8': 'closing result of the declined-Yes-2 variant accepted when each payment amount is listed (or the total with the count).',
        'PF9': 'one log reader: sentence-level, "drafts shown" passes, "not stated / not said / omission" fails only the step it is about; step 1 is also checked in V2 and C5.',
        'PF10': 'replay accepts the Skill failure marker ("not transcribed: listen and quote by hand") in place of a quote.',
        'PF11': 'replay checks report-by dates on dispute rows only.',
        'PF12': 'no scoring change: C1-V6 Haiku is labelled "stopped on case data" (the stored Yes 2 answer names the new folder 2026-11-12, the resumed folder is 2026-11-11).',
        'PF13': 'no scoring change: the field "stop list says not finished" stays strict (C1-V7 Sonnet stays wrong).',
        'PF14': 'replay applies S1 to the card photos the consent allowed.',
        'PF15': 'replay accepts quotes found in the person\'s stored answers.'}
    for k in ['PF%d' % i for i in range(1, 16)]:
        L.append('### %s' % k)
        L.append(notes[k])
        ch = changes.get(k, [])
        if k == 'PF12':
            ch = ['C1-V6-ledger-edited Haiku: stopped at step 12 before any write; label "case data" in section (c) (stopped on case data).']
        if k == 'PF13':
            ch = ['C1-V7-one-folder Sonnet: "stop list says not finished" stays wrong under v3.1 (as written).']
        if k == 'PF3':
            ch = ch + ['no change for the %d runs that pass every log check: %s' % (len(changes.get('PF3_ok', [])), ', '.join(changes.get('PF3_ok', [])))]
        L += ['- ' + x for x in ch] or ['- changed no run']
        L.append('')
    if 'other' in changes:
        L += ['### Other changes (not attributed to one row)'] + ['- ' + x for x in changes['other']] + ['']
    open(os.path.join(OUT, 'RESCORE-V31.md'), 'w').write('\n'.join(L))
    c3 = {m: summ[m][0] for m in MODELS}
    print('RESCORE31 rows %d; v3 class right %d/24; v3.1 class right %d/24; payments right Sonnet %d/%d, Haiku %d/%d' % (
        len(rows), sum(c3.values()), sum(summ[m][1] for m in MODELS), summ['claude-sonnet-5-5'][3][0], summ['claude-sonnet-5-5'][3][1], summ['claude-haiku-5-5'][3][0], summ['claude-haiku-5-5'][3][1]))


if __name__ == '__main__':
    main()
