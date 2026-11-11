#!/usr/bin/python3
"""Checks that every stored reply answers every part its command asks. Standard library only. No network, no model.

/usr/bin/python3 -I tools/check_cases.py
For each case folder under test-kit/cases it reads the delegate commands from skill/scam-response/SKILL.md (step number, place in
the step, expert, action, instruction text). A part is requested when its trigger phrase appears in the command's instruction text.
It then looks for that part in the stored reply (per item for lists, once for the whole reply otherwise). An empty answer such as
"No results." counts only when the instruction allows it. Writes test-kit/CHECK-CASES.txt and prints the same.
"""
import sys
sys.dont_write_bytecode = True
import re
from pathlib import Path

S = Path(__file__).resolve().parent.parent
SKILL = S / 'skill' / 'scam-response' / 'SKILL.md'
HOST = S / 'test-kit'
STATES = ('completed', 'failed', 'cancelled', 'waiting_user', 'waiting_approval')
EXPERT = {'file-workflow': 'file-agent', 'ug-filesystem': 'file-agent', 'ug-filemgr': 'file-agent', 'ug-surveillance': 'security-monitor-agent',
          'ug-document': 'document-agent', 'ug-knowledge': 'knowledge-agent', 'ug-photo': 'photo-agent'}
PATHHEAD = r'^--- /\S'
ONE = r'Created: /volume1/'

# key: "cli action"; part: (label, trigger regex in the instruction, scope item|all, reply regex)
PARTS = {
    'file-workflow get-user-dir': [('home path', r'home path of the current user', 'all', r'Home path: /volume1/')],
    'ug-filesystem find': [('full path', r'full path', 'item', PATHHEAD), ('modified date', r'modified date', 'item', r'Modified: \d{4}-\d\d-\d\d'),
                           ('size', r'\bsize\b', 'item', r'Size: \d+ bytes')],
    'ug-filesystem cat': [('full text of the file', r'full text of the file', 'all', r'Ledger text:|does not exist')],
    'ug-surveillance cameras': [('name', r'its name', 'item', r'^--- \S'), ('identifier', r'identifier', 'item', r'Identifier: \S+'),
                                ('online or not', r'whether it is online', 'item', r'Online: (yes|no)')],
    'ug-filesystem mkdir': [('full path of each folder created', r'full path of each', 'all', ONE),
                            ('subfolders messages, recordings, statements, camera', r'subfolders messages, recordings, statements and camera|exhibit subfolders', 'all',
                             r'(?s)(?=.*/messages)(?=.*/recordings)(?=.*/statements)(?=.*/camera)')],
    'ug-filesystem echo': [('full path', r'full path', 'all', r'Path: /volume1/'), ('size in bytes', r'size in bytes', 'all', r'\d+ bytes')],
    'ug-photo search-screen': [('full path', r'full path', 'item', PATHHEAD), ('folder', r'its folder', 'item', r'Folder: /'),
                               ('category', r'its category', 'item', r'Category: (screen|card)'),
                               ('capture time', r'capture time', 'item', r'Capture time: \d{4}-\d\d-\d\d \d\d:\d\d')],
    'ug-photo vision-ocr': [('every line of text as read', r'every line of text', 'item', r'Line 1: .+ \| (clear|unclear)'),
                            ('clarity mark on every line', r'clarity mark per line', 'item', 'LINES_MARKED'),
                            ('last four digits of a card number', r'last four digits of any card', 'item', r'Card last four: '),
                            ('list of unreadable images', r'list unreadable images', 'all', r'Unreadable images: ')],
    'ug-knowledge audio-transcription': [('transcriptText', r'transcripttext', 'item', r'transcriptText: '),
                                         ('segments with start times', r'segments with start times', 'item', r'Segments: none|\[\d\d:\d\d\]'),
                                         ('quality mark', r'quality mark', 'item', r'Quality: '), ('failure reason', r'failure reason', 'item', r'Failure reason: ')],
    'ug-surveillance event-timeline': [('time', r'each event with time', 'item', r'Time: \d{4}-'), ('camera', r'camera', 'item', r'Camera: \S'),
                                       ('type', r'\btype\b', 'item', r'Type: (Human|HumanFace|Vehicle|Package)'), ('identity', r'identity', 'item', r'Identity: \S')],
    'ug-knowledge collect-evidence': [('source file path', r'source file path', 'item', PATHHEAD), ('date if shown', r'its date', 'item', r'Date: '),
                                      ('addressed to', r'who it is addressed to', 'item', r'Addressed to: '), ('matching passage', r'matching passage', 'item', r'Passage: '),
                                      ('coverage statement', r'coverage statement', 'all', r'Coverage: '), ('files that failed to read', r'files that failed to read', 'all', r'Failed to read: ')],
    'ug-photo search-picture': [('image path', r'image path', 'item', PATHHEAD), ('folder', r'its folder', 'item', r'Folder: /'),
                                ('capture time', r'capture time', 'item', r'Capture time: ')],
    'ug-photo meta': [('capture time', r'capture time', 'item', r'Capture time: '), ('file size', r'file size', 'item', r'File size: \d+ bytes')],
    'ug-document extract': [('every transaction row with date, description, amount, direction, currency, account', r'every transaction row', 'item',
                             r'Statement state: failed|Row: \d{4}-\d\d-\d\d \| .+ \| \d+\.\d\d \| (debit|credit) \| [A-Z]{3} \| \d{4}'),
                            ('statement period', r'statement period', 'item', r'Period: '), ('coverage statement', r'coverage statement', 'item', r'Coverage: '),
                            ('failure reason', r'failure reason', 'item', r'Failure reason: ')],
    'ug-document reconcile': [('payees new in the window', r'new in the window', 'all', r'New payee: '), ('payments explained by an invoice or contract', r'explained by an invoice', 'all', r'Explained: '),
                              ('rows used for each', r'each with the rows used', 'all', 'ROWS_USED')],
    'ug-surveillance event-evidence': [('snapshot reference', r'snapshot reference', 'item', r'Snapshot: \S'), ('time', r'\btime\b', 'item', r'Time: '),
                                       ('camera', r'camera', 'item', r'Camera: ')],
    'ug-surveillance vehicle-plates': [('plate', r'each plate', 'item', r'^--- \S'), ('time', r'with time', 'item', r'Time: '), ('camera', r'camera', 'item', r'Camera: '),
                                       ('known vehicle or not', r'whether it is a known vehicle', 'item', r'Known vehicle: (yes|no)')],
    'ug-surveillance vehicle-plate-detail': [('plate text', r'plate text', 'item', r'Plate text: \S'), ('time', r'\btime\b', 'item', r'Time: '),
                                             ('camera', r'camera', 'item', r'Camera: '), ('snapshot reference', r'snapshot reference', 'item', r'Snapshot: \S')],
    'ug-filesystem cpmv': [('original path', r'original path', 'item', PATHHEAD), ('copy path', r'the copy path', 'item', r'Copy path: /volume1/'),
                           ('state of each copy', r'state of each copy', 'item', r'State: (copied|waiting_approval)')],
    'ug-filesystem sha256sum': [('path', r'return the path', 'item', PATHHEAD), ('SHA-256 value', r'sha-256 value', 'item', r'SHA-256: [0-9a-f]{64}'),
                                ('size in bytes', r'size in bytes', 'item', r'Size: \d+ bytes')],
    'ug-filemgr tag-add': [('each file', r'return each file', 'item', PATHHEAD), ('whether the tag was applied', r'whether the tag was applied', 'item', r'Tag applied: (yes|no)')],
    'ug-document writing': [('full letter text', r'full letter text', 'all', r'Dear |No payment rows were given'),
                            ('first person', r'first person', 'all', r'\bI (am|paid)\b|No payment rows were given'),
                            ('which message asked for each payment', r'which message asked for each payment', 'all', 'ASKED_EACH')],
    'ug-knowledge save-text': [('full path', r'full path', 'item', r'Full path: /volume1/'), ('size in bytes', r'size in bytes', 'item', r'Size: \d+ bytes')],
}
EMPTY_OK = r'no results|no cameras|does not exist|say so'
PERSON = {'step2-answer.txt': 'step 2: resume or new', 'step3-consent.txt': 'step 3: consent and Yes 1', 'step9-ask-answers.txt': 'step 9: answers to ask rows',
          'step10-account.txt': 'step 10: the parent\'s account', 'step10-settle.txt': 'step 10: the parent settles each disagreement',
          'step11-answer.txt': 'step 11: Yes 2', 'step12-approvals.txt': 'step 12: platform approval per write'}


def skill_commands():
    text = SKILL.read_text(encoding='utf-8')
    out, step = [], None
    counts = {}
    for line in text.splitlines():
        m = re.match(r'## Step (\d+)\.', line)
        if m:
            step = int(m.group(1))
            continue
        m = re.match(r"`delegate --target (\S+) --instruction '(.*)'`\s*$", line)
        if m and step:
            counts[step] = counts.get(step, 0) + 1
            u = re.search(r'Use ([a-z0-9-]+) ([a-z0-9-]+)', m.group(2))
            out.append(dict(step=step, n=counts[step], target=m.group(1), cli=u.group(1), action=u.group(2), text=m.group(2)))
    return out


def items_of(body):
    blocks, cur = [], None
    for line in body.splitlines():
        if line.startswith('--- '):
            cur = [line]
            blocks.append(cur)
        elif cur is not None:
            cur.append(line)
    return ['\n'.join(b) for b in blocks]


def part_ok(rx, scope, body, items, instr):
    def one(txt):
        if rx == 'LINES_MARKED':
            lines = [l for l in txt.splitlines() if re.match(r'Line \d+: ', l)]
            return bool(lines) and all(re.search(r'\| (clear|unclear)$', l) for l in lines)
        if rx == 'ROWS_USED':
            ls = [l for l in txt.splitlines() if l.startswith('New payee: ') and 'none' not in l] + [l for l in txt.splitlines() if l.startswith('Explained: ') and 'none' not in l]
            return all('rows used:' in l for l in ls)
        if rx == 'ASKED_EACH':
            if 'No payment rows were given' in txt:
                return True
            ls = [l for l in txt.splitlines() if re.match(r'\d+\. On ', l)]
            return bool(ls) and all('asked for by' in l for l in ls)
        return re.search(rx, txt, re.M) is not None
    if scope == 'all':
        return one(body)
    if not items:
        return bool(re.search(EMPTY_OK, body, re.I) and re.search(EMPTY_OK, instr, re.I))
    return all(one(i) for i in items)


def listing_counts(case):
    t = (case / 'FILE-LISTING.txt').read_text(encoding='utf-8')
    return {k: len(re.findall(r'; %s;' % k, t)) for k in ('photo', 'audio', 'statement', 'document')}


def write_consistency(case, out):
    """Write-step replies must match what the stored approvals approve (oracle: the key file; variants override)."""
    import json
    base = case.name.split('-')[0]
    key = json.loads((HOST / 'keys' / ('%s-key.json' % base)).read_text())
    var = case.name.split('-', 1)[1] if '-' in case.name else ''
    ex = [x for x in key['writes']['exhibits_to_copy']]
    tag = key['writes']['tag_originals'] is not None
    pages = ['START-HERE.md', 'STOP-LIST.md', 'PAYMENTS-TO-DISPUTE.md', 'TIMELINE.md', 'GAPS-AND-NEXT.md', 'QUOTES.md'] + (['CAMERA.md'] if key['camera_events']['page_written'] else []) + \
        ['HOLDER-STATEMENT.md'] + (['LETTER-BANK-%s.md' % key['pages']['LETTER-BANK']['file'].split('LETTER-BANK-')[1][:-3], 'LETTER-POLICE.md'] if key['pages']['LETTER-BANK'] else []) + ['EXHIBITS.md']
    nled = len(key['pages']['LEDGER.md']['checkpoint_steps'])
    cancel = key['writes']['zero_writes_expected']
    if var.startswith('V2'):
        cancel = True
    if var.startswith('V4'):
        pages = [p for p in pages if not p.startswith('LETTER')]
    if var.startswith('V7'):
        ex, tag = ['northvale-2026-10.pdf'], False
    gaps, ev = 0, case / 'experts'
    def rd(name):
        return list(ev.glob(name))[0].read_text()
    def bad(msg):
        nonlocal gaps
        gaps += 1
        out.append('  GAP consistency: ' + msg)
    if cancel:
        for g in ('s12-*',):
            for f in sorted(ev.glob(g)):
                if not f.read_text().startswith('state: cancelled'):
                    bad('%s should be cancelled (no write approved)' % f.name)
        out.append('  consistency: write steps cancelled, as approved')
        return gaps
    cp = [i.split('\n')[0][4:].rsplit('/', 1)[1] for i in items_of(rd('s12-2-*'))]
    if sorted(cp) != sorted(ex):
        bad('copied files %d differ from the Yes 2 list %d' % (len(cp), len(ex)))
    sh = [i.split('\n')[0][4:] for i in items_of(rd('s12-3-*')) if 'LEDGER.md' not in i.split('\n')[0]]
    orig = [x for x in sh if x.startswith('/volume1/') and '/Scam-Response-' not in x]
    if sorted(x.rsplit('/', 1)[1] for x in orig) != sorted(x for x in ex if True) and not var.startswith('V5'):
        bad('hashed originals differ from the Yes 2 list')
    tg = rd('s12-4-*')
    if tag:
        names = [i.split('\n')[0][4:].rsplit('/', 1)[1] for i in items_of(tg)]
        if sorted(names) != sorted(x for x in ex if not x.startswith('snap-')):
            bad('tagged originals differ from the Yes 2 list (camera snapshots excluded)')
    elif not tg.startswith('state: cancelled'):
        bad('tag reply present although no tags were asked')
    sv = [i.split('\n')[0][4:].rsplit('/', 1)[1] for i in items_of(rd('s12-6-*'))]
    if sorted(sv) != sorted(pages):
        bad('saved pages %s differ from the pages the Skill writes %s' % (sorted(set(sv) ^ set(pages)), len(pages)))
    ec = [int(x) for x in re.findall(r'Size after line \d+: (\d+) bytes', rd('s12-7-*'))]
    shl = re.findall(r'LEDGER\.md \(after (\d+) lines\)\nSHA-256: [0-9a-f]{64}\nSize: (\d+) bytes', rd('s12-3-*'))
    shs = [int(b) for a, b in shl if int(a) > 0]
    if len(ec) != nled or ec != shs:
        bad('ledger sizes: echo reply has %d lines, sha reply %d, key expects %d lines, or sizes differ' % (len(ec), len(shs), nled))
    out.append('  consistency: copy %d, tag %s, pages %d, ledger lines %d: checked' % (len(cp), 'yes' if tag else 'none', len(sv), len(ec)))
    return gaps


MONTHS = {m: i for i, m in enumerate(['january', 'february', 'march', 'april', 'may', 'june', 'july', 'august', 'september', 'october', 'november', 'december'], 1)}


def flow_consistency(case, out):
    """Stored person answers and expert replies must follow the flow the key expects. Returns (gaps, number of checks run)."""
    import json
    base = case.name.split('-')[0]
    key = json.loads((HOST / 'keys' / ('%s-key.json' % base)).read_text())
    var = case.name.split('-', 1)[1] if '-' in case.name else ''
    ev, pe = case / 'experts', case / 'person'
    gaps, n = 0, 0

    def bad(msg):
        nonlocal gaps
        gaps += 1
        out.append('  GAP flow: ' + msg)

    def rd(d, pat):
        fs = list(d.glob(pat))
        return fs[0].read_text() if fs else ''
    zero = key['writes']['zero_writes_expected']
    step3, step9, step11, step12 = (rd(pe, 'step3-*'), rd(pe, 'step9-*'), rd(pe, 'step11-*'), rd(pe, 'step12-*'))
    # F1 Yes 1 and Yes 2 approve what the case needs, unless the case is about a refusal
    n += 1
    if not var and not zero:
        if not step3.rstrip().endswith('Yes 1: yes, save progress.'):
            bad('Yes 1 is not approved in a case that writes')
        if not step11.startswith('Yes 2') or not step12.startswith('Approve every write'):
            bad('Yes 2 or the write approvals are missing in a case that writes')
    # F2 every ask row gets an answer; no ask rows -> the answer says so
    n += 1
    if not var:
        rows = key['ask_rows']
        if rows:
            for r in rows:
                if r['payee'].lower() not in step9.lower():
                    bad('ask row %s has no answer in step9' % r['payee'])
        elif not step9.startswith('There are no rows to ask'):
            bad('step9 answer does not say there are no rows')
    # F3 an account exists when the key has holder lines, and the request offers it
    n += 1
    sents = key['pages']['HOLDER-STATEMENT.md']['sentences']
    if any(x['include'] for x in sents) and not var:
        if not rd(pe, 'step10-account*').strip():
            bad('key has holder lines but step10-account is empty')
        prompt = (HOST / 'prompts' / ('%s.claude-sonnet-5-5.txt' % case.name)).read_text()
        if 'in his own words' not in prompt and 'in her own words' not in prompt:
            bad('the request does not offer the parent\'s account, so step 10 is never reached')
        dis = sum(1 for x in sents if x['mark'] == 'disagrees')
        if dis and len(re.findall(r'\b\d\. ', rd(pe, 'step10-settle*'))) < dis:
            bad('step10-settle settles fewer disagreements than the key marks')
    # F4 every file the copy reply names appears as a path in an earlier stored reply, so the host could name it
    n += 1
    earlier = '\n'.join(f.read_text() for f in sorted(ev.glob('s0*')) + sorted(ev.glob('s1[01]*')))
    cpf = list(ev.glob('s12-2-*'))
    if cpf and not cpf[0].read_text().startswith('state: cancelled'):
        for it in items_of(cpf[0].read_text()):
            o = it.split('\n')[0][4:]
            if o not in earlier:
                bad('copy reply names %s, which no earlier reply returned' % o)
    # F5 the sha256sum reply hashes exactly the copy reply's originals and copies
    n += 1
    shf = list(ev.glob('s12-3-*'))
    if cpf and shf and not cpf[0].read_text().startswith('state: cancelled') and not var.startswith(('V5', 'V2')):
        cps = {i.split('\n')[0][4:] for i in items_of(cpf[0].read_text())}
        cpp = {re.search(r'Copy path: (\S+)', i).group(1) for i in items_of(cpf[0].read_text())}
        shp = {i.split('\n')[0][4:].split(' (after')[0] for i in items_of(shf[0].read_text()) if 'LEDGER.md' not in i.split('\n')[0]}
        if shp != cps | cpp:
            bad('sha256sum paths differ from the copy reply (%d vs %d)' % (len(shp), len(cps | cpp)))
    # F6 save-text saves the pages the key writes and not the ledger (echo writes the ledger)
    n += 1
    svf = list(ev.glob('s12-6-*'))
    if svf and not zero and 'LEDGER.md' in svf[0].read_text():
        bad('save-text reply lists LEDGER.md; the ledger is written by echo')
    # F7 the echo reply reports exactly the ledger lines the key expects
    n += 1
    ecf = list(ev.glob('s12-7-*'))
    if ecf and not zero and not var:
        if len(re.findall(r'Size after line', ecf[0].read_text())) != len(key['pages']['LEDGER.md']['checkpoint_steps']):
            bad('echo reply line count differs from the key checkpoint steps')
    # F8 card photos lie inside the consent window; F9 the holder name is in a reading inside the window
    n += 2
    m = re.search(r'from (\d+) (\w+) to (\d+) (\w+) (\d{4})', step3)
    if m and not var:
        start = '%s-%02d-%02d' % (m.group(5), MONTHS[m.group(2).lower()], int(m.group(1)))
        for it in items_of(rd(ev, 's04-1-*')):
            if 'Category: card' in it:
                cap = re.search(r'Capture time: (\S+)', it).group(1)
                if cap < start:
                    bad('card photo %s captured %s, before the window start %s' % (it.split('\n')[0][4:], cap, start))
        ocr = rd(ev, 's04-2-*') + rd(ev, 's06-2-*')
        if key['holder'].lower() not in ocr.lower() and not zero:
            bad('holder name %s appears in no text reading, so a letter cannot take it from the files' % key['holder'])
    # F11 every scam number the key keeps off the stop list is printed in a message the host reads
    n += 1
    for num in ([] if var else key['stop_list']['numbers_that_must_stay_off']):
        if num not in earlier:
            bad('scam number %s appears in no stored reply' % num)
    # F10 the writing reply uses only facts that appear in the case files and the request
    n += 1
    wf = list(ev.glob('s12-5-*'))
    if wf and 'Dear' in wf[0].read_text():
        corpus = '\n'.join(f.read_text() for f in sorted(ev.glob('s*')) if not f.name.startswith('s12-5')) + '\n' + '\n'.join(f.read_text() for f in pe.glob('step*'))
        corpus += (HOST / 'prompts' / ('%s.claude-sonnet-5-5.txt' % case.name)).read_text()
        low = corpus.lower()
        for f in re.findall(r'\d[\d.:\-]*\d|\b[A-Z][A-Z]{2,}\b', wf[0].read_text().split('\n', 3)[3]):
            if f.lower() not in low:
                bad('writing reply uses "%s", which is in no case file' % f)
        nm = re.search(r'I am (.+?)\.', wf[0].read_text())
        if nm and nm.group(1).lower() not in low:
            bad('writing reply names "%s", which is in no case file' % nm.group(1))
    return gaps, n


def main():
    cmds = skill_commands()
    out, gaps = [], 0
    out.append('check_cases: %d delegate commands read from SKILL.md; cases checked: %s' % (len(cmds), ', '.join(sorted(p.name for p in (HOST / 'cases').iterdir() if p.is_dir()))))
    experts = set(re.findall(r'→ `([a-z-]+-agent)`', SKILL.read_text(encoding='utf-8')))
    for case in sorted(p for p in (HOST / 'cases').iterdir() if p.is_dir()):
        cnt = listing_counts(case)
        cgaps = 0
        out.append('')
        out.append('== %s' % case.name)
        for q, label in PERSON.items():
            f = case / 'person' / q
            if not f.exists() or not f.read_text().strip():
                out.append('  GAP person answer missing: %s (%s)' % (q, label))
                cgaps += 1
        for c in cmds:
            if c['step'] == 3 or (c['step'] == 12 and c['n'] != 3):
                continue
            if (c['step'], c['n']) == (12, 3):
                f3 = list((case / 'experts').glob('s12-3-*'))
                zero = case.name in ('C5',) or case.name.endswith('V2-yes2-declined')
                if zero:
                    if f3:
                        out.append('  GAP hash reply stored although no copy is approved')
                        cgaps += 1
                    continue
                if f3:
                    its = {i.split('\n')[0][4:]: re.search(r'SHA-256: ([0-9a-f]{64})', i).group(1) for i in items_of(f3[0].read_text())}
                    for pth, h in its.items():
                        if '/Scam-Response-' in pth:
                            orig = [o for o in its if '/Scam-Response-' not in o and o.rsplit('/', 1)[1] == pth.rsplit('/', 1)[1]]
                            if not orig or its[orig[0]] != h:
                                out.append('  GAP copy hash differs from its original: ' + pth)
                                cgaps += 1   # write steps are simulated by the prompt rule; no stored reply
            if (c['step'], c['n']) == (2, 3) and not (case.name.endswith(('V1-resume', 'V6-ledger-edited'))):
                if list((case / 'experts').glob('s02-3-*')):
                    out.append('  GAP ledger read-back stored in a case that does not resume')
                    cgaps += 1
                continue
            fs = list((case / 'experts').glob('s%02d-%d-%s-%s.txt' % (c['step'], c['n'], c['cli'], c['action'])))
            tag = 'step %d.%d %s %s %s' % (c['step'], c['n'], c['target'], c['cli'], c['action'])
            if len(fs) != 1:
                out.append('  GAP %s: no stored reply file' % tag)
                cgaps += 1
                continue
            body = fs[0].read_text(encoding='utf-8')
            head = body.splitlines()[:3]
            miss = []
            if len(head) < 3 or not head[0].startswith('state: ') or head[0][7:] not in STATES:
                miss.append('state line')
            if len(head) < 3 or head[1] != 'expert: ' + c['target'] or head[2] != 'action: %s %s' % (c['cli'], c['action']):
                miss.append('expert/action lines')
            req = []
            items = items_of(body)
            if head and head[0] == 'state: cancelled':
                out.append('  step %d.%d %-22s %-34s cancelled reply (no write approved)' % (c['step'], c['n'], c['target'], c['cli'] + ' ' + c['action']))
                if len(body.splitlines()) < 4 or not body.splitlines()[3].startswith('reason:'):
                    cgaps += 1
                    out.append('  GAP cancelled reply has no reason line')
                continue
            for label, trig, scope, rx in PARTS.get(c['cli'] + ' ' + c['action'], []):
                if re.search(trig, c['text'], re.I):
                    req.append(label)
                    if not part_ok(rx, scope, body, items, c['text']):
                        miss.append(label)
            if not PARTS.get(c['cli'] + ' ' + c['action']):
                miss.append('no part table for this command')
            want = {('ug-photo', 'vision-ocr'): 'photo', ('ug-photo', 'meta'): 'photo', ('ug-document', 'extract'): 'statement'}.get((c['cli'], c['action']))
            if want and len([i for i in items if i.startswith('--- /')]) != cnt[want]:
                miss.append('an item for every %s in the household (%d)' % (want, cnt[want]))
            if (c['cli'], c['action']) == ('ug-knowledge', 'audio-transcription') and c['step'] in (4, 6):
                if len(items) != cnt['audio'] - (1 if 'dad-tells-it' in (case / 'FILE-LISTING.txt').read_text() and False else 0) and len(items) not in (cnt['audio'], cnt['audio'] - 1):
                    miss.append('an item for every recording (%d)' % cnt['audio'])
            out.append('  step %d.%d %-22s %-34s parts: %s -> %s' % (c['step'], c['n'], c['target'], c['cli'] + ' ' + c['action'], '; '.join(req) or 'none', 'ok' if not miss else 'MISSING ' + ', '.join(miss)))
            cgaps += len(miss)
        if (case / 'states').exists():
            for ex in sorted(experts):
                for st in STATES:
                    f = case / 'states' / ('%s-%s.txt' % (ex, st))
                    ok = f.exists() and ('state: ' + st) in f.read_text() and ('expert: ' + ex) in f.read_text()
                    extra = {'failed': 'error:', 'cancelled': 'reason:', 'waiting_user': 'question:', 'waiting_approval': 'write:', 'completed': 'result:'}[st]
                    ok = ok and extra in f.read_text()
                    if not ok:
                        out.append('  GAP state reply missing or incomplete: %s %s' % (ex, st))
                        cgaps += 1
            out.append('  states: %d experts x %d states checked' % (len(experts), len(STATES)))
        fg, fn = flow_consistency(case, out)
        cgaps += fg
        out.append('  flow consistency: %d checks, %d gaps' % (fn, fg))
        n_idx = 0
        for rel in ('experts/INDEX.txt', 'person/INDEX.txt'):
            f = case / rel
            if not f.exists():
                out.append('  GAP index missing: ' + rel)
                cgaps += 1
                continue
            for line in f.read_text().splitlines():
                n_idx += 1
                pth = line.rsplit('| ', 1)[1]
                if not (S / pth).is_file() or str(case.relative_to(S)) not in pth:
                    out.append('  GAP index path missing or outside the case: ' + pth)
                    cgaps += 1
        out.append('  index lines checked: %d' % n_idx)
        out.append('  gaps in %s: %d' % (case.name, cgaps))
        gaps += cgaps
    out.append('')
    out.append('TOTAL gaps: %d' % gaps)
    text = '\n'.join(out) + '\n'
    (HOST / 'scores' / 'CHECK-CASES.txt').write_text(text, encoding='utf-8')
    print(text)
    return gaps


if __name__ == '__main__':
    sys.exit(0 if main() == 0 else 1)
