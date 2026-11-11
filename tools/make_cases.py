#!/usr/bin/python3
"""Writes the host cases C1 to C5, the C1 variants, the five-state replies, the prompts and the served Skill.

/usr/bin/python3 -I tools/make_cases.py          writes test-kit/{cases,prompts}; refuses if cases exist
Standard library only. No network. No model calls. One seed (case_data.SEED).

Layout, as round 12: cases/C#/experts/ (stored replies, one file per command), cases/C#/person/ (the person's answers),
cases/C#/states/ (C1 only: each expert returns each of the five states once), cases/C#/FILE-LISTING.txt.
A stored reply file is named s<step>-<n>-<cli>-<action>.txt, n = the command's place among the commands of that step in SKILL.md.
Every reply starts with: state / expert / action. A reply holds everything the expert has for the whole library or folder; the host
uses only the items for the paths, days, window and approved folders it sent.
"""
import sys
sys.dont_write_bytecode = True
import hashlib
import shutil
import subprocess
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import case_data as D
import write_keys as WK

S = Path(__file__).resolve().parent.parent
OUT = S / 'test-kit'     # the first argument of main() can name another output folder (to compare with the repo copy)
SKILL = S / 'skill' / 'scam-response'
MODELS = ('claude-sonnet-5-5', 'claude-haiku-5-5')
EXPERT = {'file-workflow': 'file-agent', 'ug-filesystem': 'file-agent', 'ug-filemgr': 'file-agent', 'ug-surveillance': 'security-monitor-agent',
          'ug-document': 'document-agent', 'ug-knowledge': 'knowledge-agent', 'ug-photo': 'photo-agent'}
STATES = ('completed', 'failed', 'cancelled', 'waiting_user', 'waiting_approval')
LEDGER_SIZE = lambda n: 380 * n + 40


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8') as f:
        f.write(text)


def env(cli, action, body, state='completed'):
    return 'state: %s\nexpert: %s\naction: %s %s\n%s\n' % (state, EXPERT[cli], cli, action, body.rstrip())


def wopts(c):
    """What this case's stored approvals approve at steps 11 and 12 (Yes 2 list, tags, pages, ledger lines)."""
    cid = c['id']
    cancel = cid == 'C5'
    disp = bool(D.disputes(c))
    pg = ['START-HERE.md', 'STOP-LIST.md', 'PAYMENTS-TO-DISPUTE.md', 'TIMELINE.md', 'GAPS-AND-NEXT.md', 'QUOTES.md'] + (['CAMERA.md'] if cid == 'C3' else []) + \
         ['HOLDER-STATEMENT.md'] + (['LETTER-BANK-%s.md' % c['bankfile'].upper(), 'LETTER-POLICE.md'] if disp else []) + ['EXHIBITS.md']
    return dict(ex=[p for p in exhibit_map_all(c) if p.rsplit('/', 1)[1] in WK.COPY[cid]], tag=c['person']['tag'] is not None, cancel=cancel, pages=pg,
                n=0 if cancel else (9 if cid == 'C3' else 8), disp=disp)


def casedir(c):
    return '%s/%s' % (c['home'], D.CASE_FOLDER)


# ------------------------------------------------------------------------------------------ replies
def r_home(c):
    return env('file-workflow', 'get-user-dir', 'Home path: ' + c['home'])


def r_find_cases(c, earlier=None):
    if not earlier:
        return env('ug-filesystem', 'find', 'No results.')
    return env('ug-filesystem', 'find', '--- %s\nModified: %s' % earlier)


def r_cat(c, ledger=None):
    return env('ug-filesystem', 'cat', 'Ledger text:\n' + ledger if ledger else 'LEDGER.md does not exist in that case folder.')


def r_cameras(c):
    return env('ug-surveillance', 'cameras', '\n'.join('--- %s\nIdentifier: %s\nOnline: %s' % (n, i, 'yes' if o else 'no') for n, i, o in c['cameras']))


def r_mkdir_case(c):
    base = casedir(c)
    return env('ug-filesystem', 'mkdir', '\n'.join('Created: ' + p for p in [base] + ['%s/%s' % (base, s) for s in ('messages', 'recordings', 'statements', 'camera')]))


def r_echo(c):
    lines = ['Path: %s/LEDGER.md' % casedir(c)] + ['Size after line %d: %d bytes' % (n, D.LEDGER_SIZE(n) if hasattr(D, 'LEDGER_SIZE') else LEDGER_SIZE(n)) for n in range(1, c['_w']['n'] + 1)]
    return env('ug-filesystem', 'echo', '\n'.join(lines))


def r_screen(c):
    items = [i for i in c['images'] if i['cat'] in ('screen', 'card')]
    return env('ug-photo', 'search-screen', '\n'.join('--- %s\nFolder: %s\nCategory: %s\nCapture time: %s' % (i['path'], i['folder'], i['cat'], i['capture']) for i in items))


def r_ocr(c, unreadable='none'):
    out = []
    for i in c['images']:
        out.append('--- ' + i['path'])
        out += ['Line %d: %s | %s' % (k + 1, t, m) for k, (t, m) in enumerate(i['lines'])]
        out.append('Card last four: ' + (', '.join(i['card4']) if i['card4'] else 'none'))
    out.append('Unreadable images: ' + unreadable)
    return env('ug-photo', 'vision-ocr', '\n'.join(out))


def r_audio_find(c):
    return env('ug-filesystem', 'find', '\n'.join('--- %s\nSize: %d bytes\nModified: %s' % (a['path'], a['size'], a['mtime']) for a in c['audio']))


def r_transcribe(c, fail=(), only=None, extra=None):
    out, any_fail = [], False
    for a in (extra or c['audio']):
        if only and a['path'] not in only:
            continue
        out.append('--- ' + a['path'])
        if a['path'] in fail:
            any_fail = True
            out += ['Recording state: failed', 'transcriptText: none', 'Segments: none', 'Quality: none', 'Failure reason: the audio could not be decoded']
            continue
        out += ['Recording state: completed', 'transcriptText: ' + a['text'], 'Segments:'] + ['  [%s] %s' % s for s in a['segs']]
        out += ['Quality: ' + a['quality'], 'Failure reason: none']
    return env('ug-knowledge', 'audio-transcription', '\n'.join(out), 'failed' if any_fail else 'completed')


def all_events(c):
    ev = [dict(time=e['time'], camera=e['camera'], type=e['type'], identity=e['identity'], snap=e['snap']) for e in c['events']]
    ev += [dict(time=p['plate_time'] if 'plate_time' in p else p['time'], camera=p['camera'], type='Vehicle',
                identity=('known: %s car' % p['owner']) if p['known'] else 'stranger', snap=p['snap']) for p in c['plates']]
    return sorted(ev, key=lambda e: e['time'])


def r_timeline(c):
    return env('ug-surveillance', 'event-timeline', '\n'.join('--- %s %s\nTime: %s\nCamera: %s\nType: %s\nIdentity: %s' % (e['time'], e['camera'], e['time'], e['camera'], e['type'], e['identity']) for e in all_events(c)))


def r_collect(c):
    out = ['--- %s\nDate: %s\nAddressed to: %s\nPassage: %s' % (p['file'], p['date'], p['to'], p['text']) for p in c['passages']]
    files = [d['path'] for d in c['docs']] + [s['path'] for s in c['statements']]
    out.append('Coverage: read %d files in /volume1/Documents/Family (documents and statements); images and recordings are read by the photo and knowledge experts.' % len(files))
    out.append('Failed to read: none')
    return env('ug-knowledge', 'collect-evidence', '\n'.join(out))


def r_search_picture(c):
    return env('ug-photo', 'search-picture', '\n'.join('--- %s\nFolder: %s\nCapture time: %s' % (i['path'], i['folder'], i['capture']) for i in c['images'] if i['sp']))


def r_meta(c):
    return env('ug-photo', 'meta', '\n'.join('--- %s\nCapture time: %s\nFile size: %d bytes' % (i['path'], i['capture'], i['size']) for i in c['images']))


def r_find_stmts(c):
    return env('ug-filesystem', 'find', '\n'.join('--- %s\nModified: %s' % (s['path'], s['mtime']) for s in c['statements']))


def r_extract(c, fail=()):
    out, any_fail = [], False
    for s in c['statements']:
        out.append('--- ' + s['path'])
        if s['month'] in fail:
            any_fail = True
            out += ['Statement state: failed', 'Period: not read', 'Coverage: not read', 'Failure reason: the PDF could not be opened']
            continue
        out += ['Statement state: completed', 'Period: %s to %s' % s['period']]
        out += ['Row: %s | %s | %s | %s | %s | %s' % (r['date'], r['payee'], r['amount'], r['dir'], c['currency'], r['acct']) for r in s['rows']]
        out.append('Header text as read: ' + s['header'])
        if s['footer']:
            out.append('Footer text as read: ' + s['footer'])
        out += ['Coverage: all pages read, %d rows' % len(s['rows']), 'Failure reason: none']
    return env('ug-document', 'extract', '\n'.join(out), 'failed' if any_fail else 'completed')


def r_reconcile(c, skip=()):
    ws = c['window'][0]
    rows = [r for r in c['rows'] if not any(s['path'] == r['statement'] and s['month'] in skip for s in c['statements'])]
    before = {r['payee'] for r in rows if r['date'] < ws}
    new = {}
    for r in rows:
        if r['date'] >= ws and r['payee'] not in before:
            new.setdefault(r['payee'], []).append('%s %s' % (r['date'], r['amount']))
    out = ['New payee: %s | rows used: %s' % (p, '; '.join(v)) for p, v in sorted(new.items())] or ['New payee: none']
    for inv in c['invoices']:
        used = [r for r in rows if r['payee'] == inv['payee'] and r['amount'] == inv['amount']]
        out.append('Explained: %s | invoice %s | rows used: %s' % (inv['payee'], inv['file'], '; '.join('%s %s' % (r['date'], r['amount']) for r in used)))
    if not c['invoices']:
        out.append('Explained: none')
    return env('ug-document', 'reconcile', '\n'.join(out))


def r_evidence(c):
    return env('ug-surveillance', 'event-evidence', '\n'.join('--- %s %s\nSnapshot: %s\nSnapshot file: /volume1/@surveillance/snapshots/%s.jpg\nTime: %s\nCamera: %s' % (e['time'], e['camera'], e['snap'], e['snap'], e['time'], e['camera']) for e in all_events(c)))


def r_plates(c):
    return env('ug-surveillance', 'vehicle-plates', '\n'.join('--- %s\nTime: %s\nCamera: %s\nKnown vehicle: %s' % (p['plate'], p['time'], p['camera'], 'yes' if p['known'] else 'no') for p in c['plates']))


def r_plate_detail(c):
    return env('ug-surveillance', 'vehicle-plate-detail', '\n'.join('--- %s\nPlate text: %s\nTime: %s\nCamera: %s\nSnapshot: %s' % (p['plate'], p['plate'], p['time'], p['camera'], p['snap']) for p in c['plates']))


def account_audio(c):
    for a in c['audio']:
        if a['role'] == 'account':
            return a
    first = c['holder'].split()[0].lower()
    return dict(path='/volume1/Homes/%s/Voice memos/tells-it.m4a' % first, text=' '.join(x['text'] for x in c['account']).replace('. ', ' and '),
                segs=[('00:%02d' % (i * 7), x['text']) for i, x in enumerate(c['account'])], quality='good')


def exhibit_map_all(c):
    """Every file the person may name as an exhibit: original path -> subfolder of the case folder."""
    m = {}
    for i in c['images']:
        if i['role'] != 'outside':
            m[i['path']] = 'messages'
    for a in c['audio']:
        if a['role'] not in ('account',):
            m[a['path']] = 'recordings'
    for s in c['statements']:
        m[s['path']] = 'statements'
    for d in c['docs']:
        m[d['path']] = 'statements'
    for e in all_events(c):
        m['/volume1/@surveillance/snapshots/%s.jpg' % e['snap']] = 'camera'
    return m


def exhibit_map(c):
    allm = exhibit_map_all(c)
    return {p: allm[p] for p in c['_w']['ex']}


def r_mkdir_ex(c):
    base = casedir(c)
    return env('ug-filesystem', 'mkdir', '\n'.join('Created: %s/%s' % (base, s) for s in ('messages', 'recordings', 'statements', 'camera')))


def r_cpmv(c, waiting=()):
    base, out, wait = casedir(c), [], False
    for o, sub in exhibit_map(c).items():
        out.append('--- ' + o)
        if o in waiting:
            wait = True
            out += ['Copy path: %s/%s/%s' % (base, sub, o.rsplit('/', 1)[1]), 'State: waiting_approval']
        else:
            out += ['Copy path: %s/%s/%s' % (base, sub, o.rsplit('/', 1)[1]), 'State: copied']
    return env('ug-filesystem', 'cpmv', '\n'.join(out), 'waiting_approval' if wait else 'completed')


def file_sha_size(c):
    d = {}
    for coll in ('images', 'audio', 'statements', 'docs'):
        for f in c[coll]:
            d[f['path']] = (f['sha'], f['size'])
    for e in all_events(c):
        p = '/volume1/@surveillance/snapshots/%s.jpg' % e['snap']
        d[p] = (D.sha(D.SEED, p), 31000 + len(e['snap']) * 97)
    return d


def r_sha(c, waiting=()):
    base, out = casedir(c), []
    fs = file_sha_size(c)
    for o, sub in exhibit_map(c).items():
        out.append('--- %s\nSHA-256: %s\nSize: %d bytes' % ((o,) + fs[o]))
        if o not in waiting:
            out.append('--- %s/%s/%s\nSHA-256: %s\nSize: %d bytes' % ((base, sub, o.rsplit('/', 1)[1]) + fs[o]))
    return env('ug-filesystem', 'sha256sum', '\n'.join(out))


def r_tag(c):
    if not c['_w']['tag']:
        return env('ug-filemgr', 'tag-add', 'reason: the person asked for no tags', 'cancelled')
    return env('ug-filemgr', 'tag-add', '\n'.join('--- %s\nTag applied: yes' % o for o in exhibit_map(c) if not o.startswith('/volume1/@surveillance')))


def ask_text(c, r):
    if r['contact']:
        return 'the message in %s' % r['contact'].rsplit('/', 1)[1]
    kept = [e for e in c['events'] if e.get('role') == 'kept']
    return 'a caller, after the doorstep visit recorded by the camera on %s' % (kept[0]['time'] if kept else 'the day named')


def r_writing(c):
    rows = D.disputes(c) if c['_w']['disp'] else []
    if not rows:
        return env('ug-document', 'writing', 'No payment rows were given, so no letter is drafted.')
    accts = ', '.join(sorted({r['acct'] for r in rows}))
    out = ['Dear %s,' % c['bank'], '',
           'I am %s. I am writing about payments from my account ending %s that I ask you to review.' % (c['holder'], accts), '']
    for k, r in enumerate(rows, 1):
        out.append('%d. On %s I paid %s %s to %s. This payment was asked for by %s%s.' % (
            k, r['date'], r['amount'], c['currency'], r['payee'], ask_text(c, r), (' (detail shared: %s)' % r['shared']) if r['shared'] else ''))
    out += ['', 'I ask the bank to review each payment, explain the steps and time limits that apply, and confirm what is in the bank file.', '',
            'Yours faithfully,', c['holder']]
    return env('ug-document', 'writing', '\n'.join(out))


def pages(c):
    return c['_w']['pages']
    names = ['START-HERE.md', 'STOP-LIST.md', 'PAYMENTS-TO-DISPUTE.md', 'TIMELINE.md', 'GAPS-AND-NEXT.md', 'QUOTES.md', 'CAMERA.md', 'HOLDER-STATEMENT.md',
             'LETTER-BANK-%s.md' % c['bankfile'].upper(), 'LETTER-POLICE.md', 'EXHIBITS.md', 'LEDGER.md']
    return names


def r_save(c):
    base = casedir(c)
    return env('ug-knowledge', 'save-text', '\n'.join('--- %s/%s\nFull path: %s/%s\nSize: %d bytes' % (base, n, base, n, 1500 + int(D.sha(c['id'], n), 16) % 2000) for n in pages(c)))


# ------------------------------------------------------------------------------------------ ledger for resume variants
def ledger_lines(c, folder=None):
    d = r_home(c)
    cdir = folder or casedir(c)
    stop = '; '.join('%s %s' % (e['item'], e['last4']) for e in c['exposures']) or 'none'
    imgs = [i for i in c['images'] if i['role'] != 'outside']
    plan = [
        (3, 'file-agent mkdir completed; echo completed', 'folders 5', 'none', '"%s"' % c['person']['step3'], '%s, approved' % cdir,
         'consent as above; case folder %s' % cdir),
        (4, 'photo-agent search-screen, vision-ocr completed; file-agent find completed; knowledge-agent audio-transcription completed; security-monitor-agent event-timeline completed',
         'images %d, audio %d, events %d' % (len(imgs), len(c['audio']), len(all_events(c))), 'none', 'none', 'none',
         'stop list found in the files read: %s; first pass saved' % stop),
        (5, 'knowledge-agent collect-evidence completed', 'passages %d' % len(c['passages']), 'none', 'none', 'none', 'passages saved'),
        (6, 'photo-agent search-picture, vision-ocr, meta completed; knowledge-agent audio-transcription completed', 'images %d, recordings %d' % (len(imgs), len(c['audio'])), 'none', 'none', 'none', 'quotes saved'),
        (7, 'file-agent find completed; document-agent extract, reconcile completed', 'statements %d, rows %d' % (len(c['statements']), len(c['rows'])), 'none', 'none', 'none', 'resume at step 8'),
    ]
    out, text = [], ''
    for n, (step, experts, counts, fails, consent, writes, resume) in enumerate(plan, 1):
        prev = hashlib.sha256(text.encode()).hexdigest()
        line = 'Line: %d | Step: %d | Experts and states: %s | Counts: %s | Failures: %s | Consent and answers: %s | Writes: %s | Resume data: %s | Previous ledger SHA-256: %s' % (
            n, step, experts, counts, fails, consent, writes, resume, prev)
        out.append(line)
        text += line + '\n'
    return out


# ------------------------------------------------------------------------------------------ one case
CMDS = [
    (2, 1, 'file-workflow-get-user-dir', lambda c: r_home(c)),
    (2, 2, 'ug-filesystem-find', lambda c: r_find_cases(c)),
    (2, 3, 'ug-filesystem-cat', lambda c: r_cat(c)),
    (2, 4, 'ug-surveillance-cameras', lambda c: r_cameras(c)),
    (3, 1, 'ug-filesystem-mkdir', lambda c: r_mkdir_case(c)),
    (3, 2, 'ug-filesystem-echo', lambda c: r_echo(c)),
    (4, 1, 'ug-photo-search-screen', lambda c: r_screen(c)),
    (4, 2, 'ug-photo-vision-ocr', lambda c: r_ocr(c)),
    (4, 3, 'ug-filesystem-find', lambda c: r_audio_find(c)),
    (4, 4, 'ug-knowledge-audio-transcription', lambda c: r_transcribe(c)),
    (4, 5, 'ug-surveillance-event-timeline', lambda c: r_timeline(c)),
    (5, 1, 'ug-knowledge-collect-evidence', lambda c: r_collect(c)),
    (6, 1, 'ug-photo-search-picture', lambda c: r_search_picture(c)),
    (6, 2, 'ug-photo-vision-ocr', lambda c: r_ocr(c)),
    (6, 3, 'ug-photo-meta', lambda c: r_meta(c)),
    (6, 4, 'ug-knowledge-audio-transcription', lambda c: r_transcribe(c)),
    (7, 1, 'ug-filesystem-find', lambda c: r_find_stmts(c)),
    (7, 2, 'ug-document-extract', lambda c: r_extract(c)),
    (7, 3, 'ug-document-reconcile', lambda c: r_reconcile(c)),
    (8, 1, 'ug-surveillance-event-timeline', lambda c: r_timeline(c)),
    (8, 2, 'ug-surveillance-event-evidence', lambda c: r_evidence(c)),
    (8, 3, 'ug-surveillance-vehicle-plates', lambda c: r_plates(c)),
    (8, 4, 'ug-surveillance-vehicle-plate-detail', lambda c: r_plate_detail(c)),
    (10, 1, 'ug-knowledge-audio-transcription', lambda c: r_transcribe(c, extra=[account_audio(c)])),
    (12, 1, 'ug-filesystem-mkdir', lambda c: r_mkdir_ex(c)),
    (12, 2, 'ug-filesystem-cpmv', lambda c: r_cpmv(c)),
    (12, 3, 'ug-filesystem-sha256sum', lambda c: r_sha(c)),
    (12, 4, 'ug-filemgr-tag-add', lambda c: r_tag(c)),
    (12, 5, 'ug-document-writing', lambda c: r_writing(c)),
    (12, 6, 'ug-knowledge-save-text', lambda c: r_save(c)),
    (12, 7, 'ug-filesystem-echo', lambda c: r_echo(c)),
]


def fname(step, n, slug):
    return 's%02d-%d-%s.txt' % (step, n, slug)


def listing(c):
    rows = []
    for coll, kind in (('statements', 'statement'), ('docs', 'document'), ('images', 'photo'), ('audio', 'audio')):
        for f in c[coll]:
            rows.append('%s; %s; %d bytes; modified %s; sha256 %s' % (f['path'], kind, f['size'], f.get('mtime') or f.get('capture', '')[:10], f['sha']))
    return 'File listing of the household %s (generator view, not for the host):\n' % c['id'] + '\n'.join(sorted(rows)) + '\n'


def person_files(c):
    p = c['person']
    return {
        'step2-answer.txt': p['step2'] + '\n',
        'step3-consent.txt': p['step3'] + '\n',
        'step9-ask-answers.txt': p['step9'] + '\n',
        'step10-account.txt': p['step10'] + '\n',
        'step10-settle.txt': p['settle'] + '\n',
        'step11-answer.txt': p['step11'] + '\n',
        'step12-approvals.txt': p['step12'] + '\n',
    }


def build_case(c, root):
    cd = root / 'cases' / c['id']
    for step, n, slug, fn in CMDS:
        if step == 3 or (step == 12 and (n != 3 or c['_w']['cancel'])) or (step, n) == (2, 3):
            continue   # write steps and the ledger read-back are simulated by the prompt rule, not stored
        text = fn(c)
        if step in (3, 12) and c['_w']['cancel']:
            cli = [k for k in EXPERT if slug.startswith(k + '-')][0]
            text = env(cli, slug[len(cli) + 1:], 'reason: Yes 2 was declined or no write was requested; no write is approved', 'cancelled')
        write(cd / 'experts' / fname(step, n, slug), text)
    for k, v in person_files(c).items():
        write(cd / 'person' / k, v)
    write(cd / 'FILE-LISTING.txt', listing(c))
    return cd


def write_index(c, cd):
    """experts/INDEX.txt and person/INDEX.txt with exact absolute paths; written last, so variants get their own paths."""
    ex = []
    for step, n, slug, fn in CMDS:
        cli, act = slug.split('-', 1)[0], None
        m = [(k, a) for k, a in (('file-workflow', 'get-user-dir'),) if slug.startswith(k + '-')]
        for k in EXPERT:
            if slug.startswith(k + '-'):
                cli, act = k, slug[len(k) + 1:]
        if (cd / 'experts' / fname(step, n, slug)).exists():
            ex.append('step %d | %s %s %s | %s' % (step, EXPERT[cli], cli, act, 'test-kit/cases/%s/experts/%s' % (cd.name, fname(step, n, slug))))
    pe = {'step2-answer.txt': 2, 'step3-consent.txt': 3, 'step9-ask-answers.txt': 9, 'step10-account.txt': 10, 'step10-settle.txt': 10, 'step11-answer.txt': 11, 'step12-approvals.txt': 12}
    pr = ['question at step %d | %s' % (n, 'test-kit/cases/%s/person/%s' % (cd.name, f)) for f, n in pe.items()]
    for rel, lines in (('experts/INDEX.txt', ex), ('person/INDEX.txt', pr)):
        (cd / rel).write_text('\n'.join(lines) + '\n', encoding='utf-8')


def build_states(c, root):
    acts = {'file-agent': 'ug-filesystem find', 'photo-agent': 'ug-photo vision-ocr', 'knowledge-agent': 'ug-knowledge audio-transcription',
            'document-agent': 'ug-document extract', 'security-monitor-agent': 'ug-surveillance event-timeline'}
    extra = {'completed': 'result: see the replies of the case', 'failed': 'error: the source could not be read',
             'cancelled': 'reason: the run was stopped before this action ran',
             'waiting_user': 'question: Which folder holds the statements for September?',
             'waiting_approval': 'write: ug-filesystem cpmv of one exhibit into the case folder, waiting for platform approval'}
    for ex, act in acts.items():
        for st in STATES:
            write(root / 'cases' / c['id'] / 'states' / ('%s-%s.txt' % (ex, st)), 'state: %s\nexpert: %s\naction: %s\n%s\n' % (st, ex, act, extra[st]))


def over(cd, rel, text):
    p = cd / rel
    p.write_text(text, encoding='utf-8')


def build_variants(c, root):
    base = root / 'cases' / c['id']
    ledger = ledger_lines(c)
    made = {}

    def make(name, note):
        vd = root / 'cases' / ('%s-%s' % (c['id'], name))
        shutil.copytree(base, vd)
        shutil.rmtree(vd / 'states')
        write(vd / 'VARIANT-NOTE.txt', note + '\n')
        made[name] = vd
        return vd

    def e(vd, step, n, text):
        slug = [s for st, k, s, _ in CMDS if st == step and k == n][0]
        over(vd, 'experts/' + fname(step, n, slug), text)

    earlier = ('%s/Scam-Response-2026-11-11' % c['home'], '2026-11-11')
    ledger = ledger_lines(c, earlier[0])  # C-V1: the ledger names the folder that step 2 finds
    vd = make('V1-resume', 'Resume after step 7 in a new session. Generator note, not for the host.')
    over(vd, 'person/step2-answer.txt', 'Resume the earlier case.\n')
    e(vd, 2, 2, r_find_cases(c, earlier))
    e(vd, 2, 3, r_cat(c, '\n'.join(ledger) + '\n'))
    vd = make('V2-yes2-declined', 'Yes 2 declined.')
    over(vd, 'person/step11-answer.txt', 'No. Do not save anything.\n')
    over(vd, 'person/step12-approvals.txt', 'No writes were requested.\n')
    for st, k, slug, _ in CMDS:
        if st == 12:
            cli = [x for x in EXPERT if slug.startswith(x + '-')][0]
            e(vd, 12, k, env(cli, slug[len(cli) + 1:], 'reason: Yes 2 was declined; no write is approved', 'cancelled'))
    vd = make('V3-transcription-failed', 'The transcription of the first voicemail fails.')
    bad = {c['audio'][1]['path']}
    e(vd, 4, 4, r_transcribe(c, fail=bad))
    e(vd, 6, 4, r_transcribe(c, fail=bad))
    over(vd, 'person/step9-ask-answers.txt',
         'JK HOLDINGS 1800 on 15 October: Yes, the man on the phone asked me to send it. JK HOLDINGS 2500 on 16 October: Yes, he asked me to send that too. Zenith Tickets 120 on 16 October: No, nobody asked me. I bought concert tickets for my sister myself.\n')
    vd = make('V4-statement-failed', 'The statement for October fails to extract.')
    e(vd, 7, 2, r_extract(c, fail=('2026-10',)))
    e(vd, 7, 3, r_reconcile(c, skip=('2026-10',)))
    over(vd, 'person/step9-ask-answers.txt', 'There are no rows to ask.\n')
    cv = dict(c, _w=dict(c['_w'], disp=False, pages=[p for p in c['_w']['pages'] if not p.startswith('LETTER')]))
    e(vd, 12, 5, r_writing(cv))
    e(vd, 12, 6, r_save(cv))
    vd = make('V5-copy-declined', 'The copy of the first voicemail is declined at the platform approval.')
    w = {c['audio'][1]['path']}
    e(vd, 12, 2, r_cpmv(c, waiting=w))
    e(vd, 12, 3, r_sha(c, waiting=w))
    over(vd, 'person/step12-approvals.txt', 'Decline the copy of vm-2026-10-15-0840.m4a. Approve every other write.\n')
    vd = make('V6-ledger-edited', 'Line 3 of the earlier ledger was edited after it was written.')
    ed = list(ledger)
    ed[2] = ed[2].replace('passages %d' % len(c['passages']), 'passages 0')
    over(vd, 'person/step2-answer.txt', 'Resume the earlier case.\n')
    e(vd, 2, 2, r_find_cases(c, earlier))
    e(vd, 2, 3, r_cat(c, '\n'.join(ed) + '\n'))
    vd = make('V7-one-folder', 'Consent for one folder only.')
    over(vd, 'person/step3-consent.txt', 'I agree you may read /volume1/Documents/Family only, and the two cameras, from 15 September to 12 November 2026. Do not read /volume1/Voicemail or the photo library. Yes 1: yes, save progress.\n')
    over(vd, 'person/step9-ask-answers.txt', 'JK HOLDINGS 1800 on 15 October: Yes, the man on the phone asked me to send it. JK HOLDINGS 2500 on 16 October: Yes, he asked me. JK HOLDINGS 1200 on 19 October: Yes, he asked me. Zenith Tickets 120 on 16 October: No, nobody asked me.\n')
    cv = dict(c, _w=dict(c['_w'], tag=False, ex=[p for p in c['_w']['ex'] if p.endswith('northvale-2026-10.pdf')]))
    e(vd, 12, 2, r_cpmv(cv))
    e(vd, 12, 3, r_sha(cv))
    e(vd, 12, 4, r_tag(cv))
    over(vd, 'person/step11-answer.txt', 'Yes 2. Copy the October statement. Folder name Scam-Response-2026-11-12. Bank: Northvale Bank. No tags.\n')
    return list(made.values())


# ------------------------------------------------------------------------------------------ prompts
TEMPLATE = r"""You are the host assistant that follows the Skill "Scam Response" for one family, as written. Follow the Skill's steps in its order and do its checks; do not shortcut them.

Files you may read (nothing else; do not look anywhere else on the disk):
- The Skill: {skill}/SKILL.md and the files in {skill}/references/
- The case: {case}/experts/ (stored replies of the NAS experts) and {case}/person/ (the person's answers)

First turn: read SKILL.md, both INDEX files and, in the same turn, these five files of references/: disclosures.md, scam-scripts.md, payment-rules.md, page-templates.md, run-record.md (several Read calls at once). The other references (capability-map.md, example-case.md, test-plan.md) need not be opened. Then work. Do not open any file of {case}/ until the Skill's step reaches it.

The person's request: "{request}"

How this test differs from a NAS (the Skill's text is unchanged):
1. You have only the Read tool (no Glob, no Grep, no folder listing). There is no delegate, ask_user or save tool. At the start, read {case}/experts/INDEX.txt and {case}/person/INDEX.txt once (two Read calls in the same turn as the Skill files). Each INDEX line gives the exact absolute path of a stored reply or answer; never guess a file name. Wherever the Skill says to send a `delegate` command, write the command you would send (target and the full instruction with the values you add), then read the reply file that experts/INDEX.txt gives for that step and expert action (the lines are in the order the Skill sends its commands; when the same action appears twice in a step, take them in order). Read each reply file once, only when its command is sent. A reply holds everything the expert has for the whole folder or library; use only the items for the paths, days, time window and approved folders you sent. Items outside the person's consent are dropped and counted, as the Skill says. A command the Skill sends only under a condition (for example step 3 only after Yes 1; step 8 only with a camera and a visit) is sent only then. A reply whose first line is `state: failed`, `cancelled`, `waiting_user` or `waiting_approval` is handled as the Skill says. If you send a command whose reply is missing a part the Skill needs, resend once and then handle it as the Skill says.
2. The person's answers are in {case}/person/ (paths in person/INDEX.txt). Read a file only when the Skill asks the person that question, after you have written the question: step2-answer.txt (resume or new case); step3-consent.txt (the consent and Yes 1); step9-ask-answers.txt (only if you have "ask" rows to put to the holder; if you have none, do not open it); step10-account.txt (the parent's account, when step 10 asks for it); step10-settle.txt (only after you have shown the marks and asked the parent to settle each disagreement); step11-answer.txt (only after you have shown the drafts and asked for Yes 2); step12-approvals.txt (only when step 12 reaches the first write that waits for platform approval). If the Skill would ask the person something else, say so and stop.
3. Write steps are simulated: each write you send completes exactly as you sent it and only after the approval it needs (a write the person declines in step12-approvals.txt does not complete); copies hash the same as their originals (use the original hashes given in the read replies); the ledger contains exactly the lines you appended this run, in order, and a read-back returns them; nothing else is created, copied, tagged or saved. Write the command you send for each, then carry on. There is no stored reply for the write steps (3 and 12), except the hash check of the copies (step 12, file-agent sha256sum), which only reads: its stored reply lists each approved copy with the hash of its original, and it is in the index when copies are approved. A hash of the ledger file LEDGER.md is not available in this test: write \"not given\" for the ledger's own hashes (the previous-ledger hash on each line) and carry on. Also, in a new case, none for the ledger read-back of step 2 (the case folder and ledger do not exist yet); a reply for it exists only when an earlier case is to be resumed. You cannot save files: after the approvals, put the pages the Skill would write in your final reply, each starting with a line of three equals signs and its file name, in the exact forms of page-templates.md. If the person declined Yes 2, or asked for no pages, write no pages.
4. Cost control: keep any text between tool calls to one line, read each case file once, and do not rewrite a text you have already written. This does not change any step or check of the Skill.
5. The platform has no clock. The run date is {run_date} and the run time is {run_time}. Use them wherever the Skill needs the run date and time ("Prepared on", the case folder name); do not ask the person for them.
6. If a step says stop, or a check keeps failing after the Skill's limit, stop there: say the step and why, and write no pages.

Final reply format (plain text, nothing after it):
STATUS: PAGES or STATUS: STOPPED or STATUS: NO WRITES
EXPERT CALLS: the number of expert commands you sent (a command sent twice counts twice)
STEP LOG: one line per step you did (step number, what you did, check passed or redone), at most 25 words each
In the step log, record the stop list shown before step 5, the answers the person gave at each question (waiting_user), the Yes 2 answer, and each write waiting for approval (waiting_approval) with its answer, before any write command is recorded.
Then, if STATUS is PAGES, the pages after approval.
"""


def _account_offer(c):
    t = c['person']['step10'].split()[1] if c['person'].get('step10') else ''
    w = {'mother': ('She', 'her'), 'father': ('He', 'his')}.get(t)
    return ' %s is here and will tell you in %s own words what happened, or name a recording, when you ask.' % w if w else ''


def prompt_of(c, name):
    return (TEMPLATE.replace('{skill}', 'skill/scam-response').replace('{case}', 'test-kit/cases/' + name)
            .replace('{request}', c['request'] + _account_offer(c)).replace('{run_date}', D.RUN_DATE).replace('{run_time}', D.RUN_TIME))


def main():
    global OUT
    if len(sys.argv) > 1:
        OUT = Path(sys.argv[1]).resolve()
    if (OUT / 'cases').exists():
        raise SystemExit('Cases exist; refusing to overwrite. Remove test-kit first, or pass another output folder as the first argument.')
    OUT.mkdir(parents=True, exist_ok=True)
    for sub in ('prompts',):
        if (OUT / sub).exists():
            shutil.rmtree(OUT / sub)
    (OUT / 'prompts').mkdir()
    cases = D.all_cases()
    names = []
    for c in cases:
        c['_w'] = wopts(c)
        build_case(c, OUT)
        names.append((c, c['id']))
        if c['id'] == 'C1':
            build_states(c, OUT)
            for vd in build_variants(c, OUT):
                names.append((c, vd.name))
                for f in list((vd / 'experts').glob('s03-*')) + [g for g in (vd / 'experts').glob('s12-*') if not g.name.startswith('s12-3-')]:
                    f.unlink()
                if vd.name.endswith('V2-yes2-declined'):
                    for f in (vd / 'experts').glob('s12-3-*'):
                        f.unlink()
                if not vd.name.endswith(('V1-resume', 'V6-ledger-edited')):
                    for f in (vd / 'experts').glob('s02-3-*'):
                        f.unlink()
    for c, name in names:
        write_index(c, OUT / 'cases' / name)
        for m in MODELS:
            write(OUT / 'prompts' / ('%s.%s.txt' % (name, m)), prompt_of(c, name))
    print('cases %d, prompt files %d' % (len(names), 2 * len(names)))


if __name__ == '__main__':
    main()
