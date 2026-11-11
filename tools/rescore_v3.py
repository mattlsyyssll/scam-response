#!/usr/bin/python3
"""Re-score the 24 saved runs with the frozen v3 scorer and replay check and compare with the saved v3 results.

  /usr/bin/python3 -I tools/rescore_v3.py

Prints one line per run (class and replay result) and the totals. Writes nothing. The 'reads' replay check needs a model transcript; the
transcripts are not in this kit, so that one check is not re-run (the saved results hold it as passed for every run that has pages).
Standard library only. No network. No model calls.
"""
import json
import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import replay_check as RC
import score_run as SC

MODELS = ['claude-sonnet-5-5', 'claude-haiku-5-5']
ORDER = SC.VARIANTS + SC.CASES


def main():
    same_class = same_replay = total = right = 0
    for m in MODELS:
        for case in ORDER:
            rp = os.path.join(SC.HOST, 'runs', m, case + '.reply.txt')
            row = SC.score_reply(case, rp)
            saved = json.load(open(os.path.join(SC.HOST, 'scores', 'score', m, 'row-%s.json' % case)))
            text = open(rp, encoding='utf-8', errors='replace').read()
            _, _, pages = SC.split_pages(text)
            sp = os.path.join(SC.HOST, 'scores', 'replay', m, case + '.json')
            saved_rep = json.load(open(sp)) if os.path.exists(sp) else None
            rep = RC.run_checks(case, pages, text, None) if saved_rep is not None else None
            ok_rep = 'none' if rep is None else ('pass' if all(o for _, o, _ in rep) else 'FAIL')
            ok_saved = 'none' if saved_rep is None else ('pass' if all(o for _, o, _ in saved_rep) else 'FAIL')
            total += 1
            right += row['class'] == 'right'
            same_class += row['class'] == saved['class'] and (row['right'], row['wrong'], row['unread']) == (saved['right'], saved['wrong'], saved['unread'])
            same_replay += ok_rep == ok_saved
            print('%-20s %-28s class %-6s (%d/%d/%d)  replay %-4s  saved: class %-6s replay %s' % (m, case, row['class'], row['right'], row['wrong'], row['unread'], ok_rep, saved['class'], ok_saved))
    print('RESCORE3 runs %d; class right %d; same class and counts as saved %d/%d; same replay result as saved %d/%d' % (total, right, same_class, total, same_replay, total))
    return 0 if same_class == total and same_replay == total else 1


if __name__ == '__main__':
    sys.exit(main())
