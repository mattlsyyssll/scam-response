#!/usr/bin/python3
"""Write test-kit/RESULTS.md from the saved scores, replay results, reads and models.

  /usr/bin/python3 -I tools/write_results.py

Order: strict count first (class right only if every field is right), then the partial measures and replay results per run, then reads per
run and the model IDs that really ran. Reads only files written by save_run.py. Standard library only.
"""
import glob
import json
import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import score_run as SC

H = SC.HOST


def load(p, default=None):
    return json.load(open(p)) if os.path.exists(p) else default


def frac(x):
    return '%d of %d' % tuple(x) if x else 'n/a'


def main():
    rows = []
    for p in sorted(glob.glob(os.path.join(H, 'scores', 'score', '*', 'row-*.json'))):
        label = os.path.basename(os.path.dirname(p))
        r = load(p)
        rp = load(os.path.join(H, 'scores', 'replay', label, r['case'] + '.json'))
        rows.append((label, r, rp))
    reads, models = load(os.path.join(H, 'scores', 'READS.json'), {}), load(os.path.join(H, 'scores', 'MODELS.json'), {})
    L = ['# Scam Response: host test results', '', 'Written by tools/write_results.py from the saved runs. Standard library only; no model.', '',
         '## Strict count (class right only if every field is right)', '']
    labels = sorted({l for l, _, _ in rows})
    L += ['| Model | Runs scored | Class right | Not right |', '|---|---|---|---|']
    for lb in labels:
        rs = [r for l, r, _ in rows if l == lb]
        ok = sum(1 for r in rs if r['class'] == 'right')
        L.append('| %s | %d | %d | %d |' % (lb, len(rs), ok, len(rs) - ok))
    tot = sum(1 for _, r, _ in rows if r['class'] == 'right')
    L += ['', 'All runs: %d of %d class right.' % (tot, len(rows)), '']
    if not rows:
        L += ['No run saved yet.', '']
    L += ['## Per run: fields, partial measures, replay', '',
          '| Case | Model | Class | Fields right / wrong / unread | Payments to dispute right | Outcome lines right | Asked, not followed files right | Stop-list numbers safe | Replay |',
          '|---|---|---|---|---|---|---|---|---|']
    for lb, r, rp in rows:
        pm = r.get('partial') or {}
        if rp is None:
            rs = 'not run'
        else:
            bad = [n for n, ok, _ in rp if not ok]
            rs = 'pass (%d checks)' % len(rp) if not bad else 'FAIL: ' + ', '.join(bad)
        L.append('| %s | %s | %s | %d / %d / %d | %s | %s | %s | %s | %s |' % (
            r['case'], lb, r['class'], r['right'], r['wrong'], r['unread'], frac(pm.get('payments_to_dispute_right')),
            frac(pm.get('outcome_lines_right')), frac(pm.get('asked_not_followed_files_right')), frac(pm.get('stop_list_numbers_safe')), rs))
    L += ['', '## Wrong or unread fields', '']
    for lb, r, rp in rows:
        bad = [f for f in r['fields'] if f['state'] != 'right']
        if bad:
            L.append('**%s %s**' % (r['case'], lb))
            L += ['- %s: %s (read: %s; key: %s)' % (f['field'], f['state'], f['read'], f['key']) for f in bad[:25]]
            L.append('')
        if rp:
            fl = [(n, d) for n, ok, d in rp if not ok]
            if fl:
                L.append('**%s %s replay failures**' % (r['case'], lb))
                L += ['- %s: %s' % x for x in fl]
                L.append('')
    L += ['## Reads and models per run', '', '| Run | Stored reads (millions) | Model IDs that ran |', '|---|---|---|']
    for k in sorted(set(reads) | set(models)):
        L.append('| %s | %.1f | %s |' % (k, reads.get(k, 0) / 1e6, ', '.join(models.get(k, [])) or 'unknown'))
    L += ['', 'Total reads: %.1fM.' % (sum(reads.values()) / 1e6), '']
    with open(os.path.join(H, 'scores', 'RESULTS.md'), 'w') as f:
        f.write('\n'.join(L))
    print('wrote test-kit/scores/RESULTS.md (%d runs)' % len(rows))


if __name__ == '__main__':
    main()
