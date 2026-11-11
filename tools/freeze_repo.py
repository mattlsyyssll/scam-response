#!/usr/bin/python3
"""Write test-kit/FROZEN-HASHES.txt for this repo copy: the hashes of the files the scorer checks (the Skill folder, the ZIP, the keys and
their manifest, the prompts, the cases, tools/score_run.py and tools/replay_check.py).

  /usr/bin/python3 -I tools/freeze_repo.py          writes the file, replacing the old one
  /usr/bin/python3 -I tools/freeze_repo.py --check  only checks the files against the saved hashes

These are the hashes of the repo copies (paths were rewritten after the original freeze; see FROZEN-HASHES-original.txt). Standard library only.
"""
import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import score_run as SC


def main(argv):
    target = os.path.join(SC.HOST, 'FROZEN-HASHES.txt')
    if '--check' in argv:
        SC.verify_freeze()
        print('freeze check ok: every file matches test-kit/FROZEN-HASHES.txt')
        return 0
    lines = ['Repo copy hashes (paths were rewritten after the original freeze; the original list is FROZEN-HASHES-original.txt).',
             'sha256\tpath (relative to the repo root)']
    for p in SC.freeze_paths():
        lines.append('%s\t%s' % (SC.sha(p), os.path.relpath(p, SC.S).replace(os.sep, '/')))
    with open(target, 'w') as f:
        f.write('\n'.join(lines) + '\n')
    print('Recorded hashes of %d files: test-kit/FROZEN-HASHES.txt' % (len(lines) - 2))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
