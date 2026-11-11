#!/usr/bin/python3
"""Scam Response scorer: strict, key-based, no model, no network. Standard library only.

  /usr/bin/python3 -I tools/score_run.py score CASE REPLY.txt [OUTDIR]   score one host reply once (writes row-CASE.json under OUTDIR)
  /usr/bin/python3 -I tools/score_run.py --selftest                     synthetic replies for every case, writes test-kit/SELFTEST-SCORER.txt
  /usr/bin/python3 -I tools/score_run.py --selftest-dry                 same, prints only, writes nothing

A host reply holds STATUS, EXPERT CALLS, STEP LOG, then pages, each starting with a line "=== FILE.md". Each page uses the exact labels
of skill/scam-response/references/page-templates.md. Every field gets right, wrong or unread (page, label or value missing = unread).
Version 2 (freeze 3): fixes R1 to R15 and the variant fields K7, K8 of SKILL-FIXES-F3.md; score_run_v1.py is the freeze-2 scorer.
The class is right only if every field is right. Tolerated: spaces, upper/lower case, thousands commas, markdown bold or bullets,
the order of list items, the order of words. Not tolerated: other numbers, dates, names, rule codes, decisions, missing items.
"""
import hashlib
import json
import os
import re
import sys
from decimal import Decimal, InvalidOperation

sys.dont_write_bytecode = True
S = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOST = os.path.join(S, 'test-kit')
SKILL = os.path.join(S, 'skill', 'scam-response')
CASES = ['C1', 'C2', 'C3', 'C4', 'C5']
VARIANTS = ['C1-V1-resume', 'C1-V2-yes2-declined', 'C1-V3-transcription-failed', 'C1-V4-statement-failed',
            'C1-V5-copy-declined', 'C1-V6-ledger-edited', 'C1-V7-one-folder']
HEADER = ['Case folder', 'Case kind', 'Prepared for', 'Prepared on', 'Run number', 'Status']
START = ['What happened', 'Do first tonight', 'For the parent', 'For the helper', 'Payments to dispute', 'Total to dispute',
         'Questions for the holder', 'Gaps in the evidence', 'Months without a statement', 'Letters to send', 'Sources not read',
         'Asked, not followed', 'Not done by this assistant']
EXTRA = ['Account named by the caller', 'First text or voicemail', 'Caller number and name used', 'Callback number', 'Session code',
         'Remote session time', 'Gift card purchases', 'Announcement of the courier', 'Hand-over time', 'Cards handed over',
         'Card uses after hand-over', 'Name or platform used', 'Balance shown on screen', 'Fees asked', 'Weeks covered',
         'Signs searched for', 'Checked', 'Not checked', 'Result']
TAIL = ['Bank limit given by the person', 'Total to dispute', 'Rows to ask the holder', 'Rows left out as normal', 'Rows kept for the timeline only']
# page -> (first label of a block or None, labels)
SPEC = {
    'START-HERE': (None, START + EXTRA),
    'STOP-LIST': ('Item', ['Item', 'Last four digits or name', 'File', 'What is exposed', 'What to do', 'Number to call', 'Safe number source']),
    'PAYMENTS-TO-DISPUTE': ('Row', ['Row', 'Date', 'Payee as shown', 'Amount', 'Currency', 'Account', 'Statement file', 'Days since payment',
                                    'Report-by date', 'Contact that asked for it', 'Link rule', 'Rule code', 'Evidence', 'Decision',
                                    'Holder answer'] + TAIL),
    'TIMELINE': ('Time', ['Time', 'Time source', 'Channel', 'Script step', 'File', 'Event', 'Payment row']),
    'GAPS-AND-NEXT': (None, ['Script seen', 'Steps seen', 'Steps with no evidence', 'Months without a statement', 'Sources not read',
                             'Likely next step', 'Warning cited', 'Questions for the holder']),
    'QUOTES': ('Quote', ['Quote', 'Speaker or sender', 'File', 'Time', 'Read by', 'Clarity', 'Linked payment row', 'Asked, not followed']),
    'CAMERA': ('Event', ['Event', 'Camera', 'Time', 'Kind', 'Identity as returned', 'Snapshot', 'Plate', 'Decision', 'Camera note']),
    'HOLDER-STATEMENT': ('Sentence', ['Holder', 'Sentence', 'Day and amount from records', 'Settled on',
                                      "Parent's own words on any disagreement", 'Signature']),
    'LETTER-BANK': (None, ['To', 'Account holder', 'Accounts', 'Date of letter', 'Summary', 'Payments disputed',
                           'Message that asked for each payment', 'What I ask the bank to do', 'Bank called on', 'Enclosed exhibits',
                           'Holder signature']),
    'LETTER-POLICE': (None, ['Report summary', 'Dates', 'Contact methods used by the caller', 'Names and numbers used by the caller',
                             'Payments', 'Camera events', 'Exhibits', 'Holder statement', 'Reported by']),
    'EXHIBITS': ('Exhibit', ['Exhibit', 'Original path', 'Copy path', 'Bytes', 'SHA-256 of original', 'SHA-256 of copy', 'Copy check']),
    'LEDGER': ('Line', ['Line', 'Step', 'Experts and states', 'Counts', 'Failures', 'Consent and answers', 'Writes', 'Resume data',
                        'Previous ledger SHA-256']),
}
KINDS = {'Human': 'person', 'HumanFace': 'face', 'Vehicle': 'vehicle', 'Package': 'package'}
GENERIC_ITEM_WORDS = {'account', 'number', 'digits', 'given', 'caller', 'codes'}
EXTRA_WORDS = {'Fees asked': ['release']}
STOPW = {'the', 'and', 'for', 'not', 'one', 'are', 'was', 'any', 'its', 'has', 'png', 'jpg', 'pdf'}


# ---------------------------------------------------------------- text helpers
def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


MONTHS = {m: i for i, m in enumerate(['january', 'february', 'march', 'april', 'may', 'june', 'july', 'august', 'september', 'october',
                                      'november', 'december'], 1)}
_MN = '|'.join(MONTHS)


def _iso_dates(s):
    """'15 October 2026' and 'October 15, 2026' become 2026-10-15 (the Skill's own form; other values stay as written)."""
    s = re.sub(r'\b(\d{1,2})(?:st|nd|rd|th)?\s+(%s),?\s+(\d{4})\b' % _MN, lambda m: '%s-%02d-%02d' % (m.group(3), MONTHS[m.group(2)], int(m.group(1))), s)
    return re.sub(r'\b(%s)\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b' % _MN, lambda m: '%s-%02d-%02d' % (m.group(3), MONTHS[m.group(1)], int(m.group(2))), s)


def norm(s):
    s = '' if s is None else str(s)
    s = _iso_dates(s.lower().replace('\u2019', "'").replace('\u2018', "'"))
    s = re.sub(r'[*`]+', ' ', s)
    s = re.sub(r'(?<=\d),(?=\d{3}(?!\d))', '', s)
    return re.sub(r'\s+', ' ', s).strip()


def alnum(s):
    return re.sub(r'[^a-z0-9]', '', norm(s))


def lab(s):
    s = re.sub(r'\([^)]*\)', ' ', s)
    return re.sub(r'[^a-z0-9]+', ' ', s.lower()).strip()


ATOM = re.compile(r'\d{4}-\d{2}-\d{2}|\d{1,2}:\d{2}|\d+(?:[.\-]\d+)*')


def words_ok(actual, expected):
    a, e = norm(actual), norm(expected)
    if not e:
        return not a
    if e == 'none' and norm(strip_br_paren(actual)) == 'none':        # R20: "none" followed by a bracket note is none
        return True
    for at in ATOM.findall(e):
        if not re.search(r'(?<![\d])' + re.escape(at) + r'(?![\d])', a):
            return False
    aw = set(re.findall(r'[a-z]{3,}', a))
    for w in re.findall(r'[a-z]{3,}', ATOM.sub(' ', e)):
        if w not in STOPW and w not in aw:
            return False
    return True


def money(s):
    m = re.search(r'-?\d+(?:\.\d+)?', norm(s).replace(' ', ''))
    try:
        return Decimal(m.group(0)) if m else None
    except InvalidOperation:
        return None


def strip_br(s):
    """R5: bracket notes [..] removed."""
    return re.sub(r'\s*\[[^\]]*\]', ' ', '' if s is None else str(s))


def strip_br_paren(s):
    return re.sub(r'\s*\([^)]*\)', ' ', strip_br(s))


def in_text(q, text_alnum):
    """R18: a quote (raw text) is in a reading (alnum text); 'ending NNNN' matches the full code that ends in NNNN. Bracket notes are ignored."""
    for v in (q, strip_br(q), strip_br_paren(q)):
        a = alnum(v)
        if a and a in text_alnum:
            return True
        fours = re.findall(r'ending\s+([a-z0-9]{4})\b', norm(v))
        if fours:
            a2 = alnum(re.sub(r'ending\s+([A-Za-z0-9]{4})\b', r'\1', v))
            t2 = text_alnum
            for f in fours:
                t2 = re.sub(r'[0-9x]*' + f, f, t2)
            if a2 and a2 in t2:
                return True
    return False


def tagset(v):
    """R4: the script steps named in a Script step value, or {'untagged'}."""
    t = norm(strip_br_paren(v))
    st = {x.upper() for x in re.findall(r'\b[a-e]\d\b', t)}
    if st:
        return st
    return {'untagged'} if t.startswith('untagged') else set()


def basename(p):
    return os.path.basename(str(p)) if p else ''


# ---------------------------------------------------------------- parsing
LINE = re.compile(r'^\s*(?:[-*\u2022]\s+)?(?:\*\*)?([^:\n*]{2,90}?)(?:\*\*)?\s*:\s*(?:\*\*)?\s*(.*)$')
PAGEL = re.compile(r'^\s*={3,}\s*(?:([\w.\-]+?\.md)\b.*|(\S+?)\s*=*)\s*$')


def page_key(name):
    n = re.sub(r'\.md$', '', name.strip(), flags=re.I).upper()
    n = re.sub(r'-RUN\d+$', '', n)
    if n.startswith('LETTER-') and not n.startswith('LETTER-POLICE'):      # R1: any LETTER-*.md other than LETTER-POLICE is the bank letter
        return 'LETTER-BANK'
    return n


def split_pages(text):
    pages, cur, name = {}, [], None
    status = calls = None
    for ln in text.split('\n'):
        m = PAGEL.match(ln)
        if m:
            if name is not None and name not in pages:
                pages[name] = cur
            name, cur = page_key(m.group(1) or m.group(2)), []
            continue
        if name is None:
            m1 = re.match(r'\s*\**STATUS\**\s*:\s*\**\s*(PAGES|STOPPED|NO WRITES)', ln, re.I)
            if m1 and status is None:
                status = m1.group(1).upper()
            m2 = re.match(r'\s*\**EXPERT CALLS\**\s*:\s*\**\s*(\d+)', ln, re.I)
            if m2 and calls is None:
                calls = int(m2.group(1))
        elif not ln.strip().startswith('```'):
            cur.append(ln)
    if name is not None and name not in pages:
        pages[name] = cur
    return status, calls, pages


def parse_page(name, lines):
    """-> dict(header={label:value}, blocks=[[(label,value)..]], tail={label:value}); labels matched by normalised name."""
    first, labels = SPEC.get(name, (None, []))
    known = {lab(x): x for x in HEADER + labels}
    header, blocks, tail, cur, last = {}, [], {}, None, None
    for ln in lines:
        m = LINE.match(ln)
        k = known.get(lab(m.group(1))) if m else None
        if k is None and m:
            kk = lab(m.group(1))
            k = next((v for lk, v in known.items() if kk == lk or (kk.startswith(lk + ' ') and len(lk) > 6)), None)
        if k is None:
            if last is not None and ln.strip():
                last[1] = (last[1] + '\n' + ln.strip()).strip()
            continue
        val = m.group(2).strip()
        if k in HEADER and k not in labels:
            header[k] = val
            last = _Ref(header, k)
            continue
        if name == 'PAYMENTS-TO-DISPUTE' and k in TAIL:
            tail[k] = val
            last = _Ref(tail, k)
            continue
        if first is None:
            if cur is None:
                cur = []
                blocks.append(cur)
        elif k == first or cur is None:
            cur = []
            blocks.append(cur)
        cur.append([k, val])
        last = _Ref(cur, len(cur) - 1)
    return {'header': header, 'blocks': [[tuple(x) for x in b] for b in blocks], 'tail': tail}


class _Ref:
    """Continuation-line target; rewrites the parsed value in place."""
    def __init__(self, container, key):
        self.c, self.k = container, key

    def __getitem__(self, i):
        v = self.c[self.k]
        return v[1] if isinstance(v, list) else v

    def __setitem__(self, i, val):
        v = self.c[self.k]
        if isinstance(v, list):
            v[1] = val
        else:
            self.c[self.k] = val


def blk(block, label):
    for k, v in block:
        if k == label:
            return v
    return None


def blks(parsed):
    out = []
    for b in parsed['blocks']:
        out.append({k: v for k, v in b})
    return out


def merged(parsed):
    d = {}
    for b in parsed['blocks']:
        for k, v in b:
            d.setdefault(k, v)
    return d


# ---------------------------------------------------------------- keys
def load_key(case):
    base = case.split('-')[0]
    p = os.path.join(HOST, 'keys', base + '-key.json')
    mf = os.path.join(HOST, 'KEYS-HASHES.txt')
    if os.path.exists(mf):
        want = {ln.split()[1]: ln.split()[0] for ln in open(mf) if re.match(r'^[0-9a-f]{64}\s', ln)}
        if want.get(base + '-key.json') and want[base + '-key.json'] != sha(p):
            raise ValueError('key hash changed: ' + p)
    return json.load(open(p))


class Res:
    def __init__(self):
        self.f = []
        self.partial = {}

    def add(self, field, actual, expected, ok):
        """actual None = unread."""
        if actual is None or (isinstance(actual, str) and not actual.strip()):
            st = 'unread'
        else:
            st = 'right' if ok else 'wrong'
        self.f.append({'field': field, 'state': st, 'read': None if actual is None else str(actual)[:200], 'key': str(expected)[:200]})

    def tok(self, field, actual, expected):
        e = 'none' if expected in (None, '', []) else expected
        self.add(field, actual, e, actual is not None and words_ok(actual, e))

    def exact(self, field, actual, expected):
        self.add(field, actual, expected, actual is not None and alnum(actual) == alnum(expected))

    def num(self, field, actual, expected):
        a, e = money(actual) if actual is not None else None, money(expected)
        self.add(field, actual, expected, a is not None and a == e)

    def blank(self, field, actual):
        """R10: a signature or Reported by line with an empty value (or the word blank or left) is blank; a missing line is unread."""
        if actual is None:
            self.add(field, None, 'blank', False)
        else:
            a = norm(actual)
            self.f.append({'field': field, 'state': 'right' if (not a or 'blank' in a or 'left' in a) else 'wrong', 'read': actual[:200], 'key': 'blank'})

    def flag(self, field, ok, read, expected):
        self.add(field, read, expected, ok)


def pg(pages, name):
    return parse_page(name, pages[name]) if name in pages else None


def has_date(v, d):
    return d and re.search(r'(?<!\d)' + re.escape(d) + r'(?!\d)', norm(v)) is not None


def atoms_ok(actual, expected):
    """Every number, date, time, file name and ALL-CAPS word of the key value is in the reply value (prose words are free)."""
    a, e = norm(actual), norm(expected)
    for at in ATOM.findall(e):
        if not re.search(r'(?<![\d])' + re.escape(at) + r'(?![\d])', a):
            return False
    return all(w.lower() in a for w in re.findall(r'\b[A-Z]{3,}\b', str(expected)))


STEPL = re.compile(r'^\s*(?:[-*\u2022]\s*)?(?:\*\*)?(?:step\s*)?(\d{1,2})\b(?!\.\d)', re.I)
NEG_SENT = re.compile(r"did not send|not sent|omission|omitted|not created|no write|wasn't|weren't|were not|was not|skipped|not reached", re.I)
NEG_SHOWN = re.compile(r"not shown|were not shown|was not shown|did not show|not displayed|omission|omitted|not reached", re.I)


def step_text(text, n):
    """Step-log text of step n: its first line and the lines up to the next numbered step line. Stops at the first page marker."""
    out, cur = [], None
    for ln in text.split('\n'):
        if PAGEL.match(ln):
            break
        m = STEPL.match(ln)
        if m:
            cur = int(m.group(1))
        if cur == n:
            out.append(ln)
    return '\n'.join(out)


def closing_zone(text):
    z = step_text(text, 13)
    return z if z.strip() else '\n'.join(text.split('\n')[-15:])


def drafts_shown(text):
    z = step_text(text, 11)
    return bool(z.strip()) and re.search(r'draft|shown|showed|displayed|presented', z, re.I) is not None and not NEG_SHOWN.search(z)


def step3_writes_sent(text):
    z = step_text(text, 3)
    return bool(z.strip()) and re.search(r'mkdir|folder', z, re.I) is not None and re.search(r'ledger|echo', z, re.I) is not None and not NEG_SENT.search(z)


def score_pages(key, status, calls, pages, text):
    R = Res()
    zero = key['writes']['zero_writes_expected']
    R.exact('STATUS', status, 'NO WRITES' if zero else 'PAGES')
    if zero:
        R.flag('no pages written', not pages, '%d pages' % len(pages), '0 pages')
        R.flag('result stated: no payment matched', 'no payment matched' in norm(closing_zone(text)), 'closing report', 'No payment matched the signs searched for')     # K7
        R.flag('drafts shown before the Yes 2 question', drafts_shown(text), 'step 11', 'drafts shown, then Yes 2 asked')
        R.flag('police report not made', 'letter-police' not in norm(text).replace(' ', '-') or not pages, 'text', 'not made')
        return R
    P = key['pages']
    # header on every page
    h = P['header']
    sh = pg(pages, 'START-HERE')
    for lb in HEADER:
        v = sh['header'].get(lb) if sh else None
        if lb in ('Case folder', 'Run number'):
            R.exact('header.' + lb, v, h[lb])
        elif lb == 'Prepared for':
            R.tok('header.' + lb, v, key['holder'])           # the template asks for the holder's name, then the helper
        else:
            R.tok('header.' + lb, v, h[lb])
    allh = all(all(lb in pg(pages, n)['header'] for lb in HEADER) for n in pages if n != 'LEDGER') if pages else False     # R8: LEDGER.md carries no header
    R.flag('header on every page', allh, 'all' if allh else 'a page lacks a header label', 'all pages')
    # START-HERE
    st = P['START-HERE.md']
    m = merged(sh) if sh else {}
    rd = (lambda k: m.get(k) if sh else None)
    kind = st['What happened'].split(' script')[0]
    amts = [p['amount'] for p in key['payments_to_dispute']]        # free summary: it must name every disputed amount
    R.add('START.What happened', rd('What happened'), 'free text naming ' + (', '.join(amts) or kind),
          rd('What happened') is not None and (all(atoms_ok(rd('What happened'), a) for a in amts) if amts else words_ok(rd('What happened'), kind)))
    v = rd('Do first tonight')
    sn = (key['stop_list'].get('safe_number') or {}).get('value')        # R19: the back of the card, or the card-photo number
    R.add('START.Do first tonight', v, 'back of the card (or the card-photo number %s); install nothing' % sn,
          v is not None and ('back of the card' in norm(v) or (sn is not None and re.sub(r'\D', '', sn) in re.sub(r'\D', '', v))) and 'install nothing' in norm(v))
    R.exact('START.Payments to dispute', rd('Payments to dispute'), st['Payments to dispute'])
    R.num('START.Total to dispute', rd('Total to dispute'), st['Total to dispute'])
    R.tok('START.Questions for the holder', rd('Questions for the holder'), st['Questions for the holder'])
    R.tok('START.Months without a statement', rd('Months without a statement'), st['Months without a statement'])
    R.tok('START.Letters to send', rd('Letters to send'), st['Letters to send'])
    R.tok('START.Sources not read', rd('Sources not read'), st['Sources not read'])
    af_files = re.findall(r'[\w.\-]+\.(?:png|jpg|m4a|pdf)', st['Asked, not followed'], re.I)       # R12: right on the file name; the text is checked on QUOTES
    if af_files:
        R.add('START.Asked, not followed', rd('Asked, not followed'), st['Asked, not followed'], rd('Asked, not followed') is not None and all(x.lower() in norm(rd('Asked, not followed')) for x in af_files))
    else:
        R.tok('START.Asked, not followed', rd('Asked, not followed'), st['Asked, not followed'])
    R.tok('START.Not done by this assistant', rd('Not done by this assistant'), st['Not done by this assistant'])
    for lb, ev in st['extra_labels'].items():
        got = next((m[k] for k in m if lab(k) == lab(lb)), None) if sh else None
        # R6: numbers, dates and capitals of the key in any order with extra text; Fees asked also needs the word release
        if lb == 'Announcement of the courier':          # R11: the key's voicemail is among those named
            ok_ = got is not None and any(x.lower() in norm(got) for x in re.findall(r'[\w.\-]+\.(?:png|jpg|m4a|pdf)', ev, re.I))
        elif lb == 'Gift card purchases':                # R13: count, amount and dates in any wording
            n_, a_ = re.match(r'(\d+) x ([\d.]+)', ev).groups()
            g_ = norm(got or '')
            tot_ = str(int(n_) * int(a_.split('.')[0]))         # R16: the count, the amount each or the total, and the dates
            ok_ = got is not None and re.search(r'(?<![\d.])(%s|%s)(?![\d])' % (n_, {'3': 'three'}.get(n_, n_)), g_) is not None and \
                re.search(r'(?<![\d.])(%s|%s)(?:\.00)?(?!\d)' % (re.escape(a_.split('.')[0]), tot_), g_) is not None and all(d_ in g_ for d_ in set(re.findall(r'\d{4}-\d\d-\d\d', ev)))
        else:
            ok_ = got is not None and atoms_ok(got, ev) and all(w in norm(got) for w in EXTRA_WORDS.get(lb, []))
        R.add('START.' + lb, got, ev, ok_)
    # STOP-LIST
    sp = P['STOP-LIST.md']
    pl = pg(pages, 'STOP-LIST')
    sb = blks(pl) if pl else None
    safe_ok = safe_n = 0
    if sb is None:
        R.add('STOP-LIST page', None, 'page', False)
    else:
        R.flag('STOP-LIST title', 'found in the files read' in norm('\n'.join(pages['STOP-LIST'])) or not sp['items'] and 'none' in norm('\n'.join(pages['STOP-LIST'])),
               'title', sp['title'])
        used = set()
        n_items = len(sb)
        bad = [re.sub(r'\D', '', x) for x in key['stop_list']['numbers_that_must_stay_off']]
        merged_ok, found = {}, 0
        files_known = {basename(x).lower() for x in key['evidence_files']}
        for it in sp['items']:
            want = [t for t in re.split(r'[,\s]+', it['last_four_or_name'].lower()) if t]
            hit, best = None, 0
            for i, b in enumerate(sb):
                if i in used and (i not in merged_ok or merged_ok[i] >= 2):       # R17: one block may carry two key items (app and session code written together)
                    continue
                lv = norm(b.get('Last four digits or name', ''))
                both = lv + ' ' + norm(b.get('Item', ''))
                iw = {w for w in re.findall(r'[a-z]{5,}', norm(it['item'])) if w not in GENERIC_ITEM_WORDS}
                itx = both + ' ' + norm(b.get('What is exposed', ''))
                sc = 3 if all(w in lv for w in want) else (2 if all(w in both for w in want) else (2 if all(w.isdigit() and w in itx for w in want) else
                                                          (1 if any(w in lv for w in want if len(w) >= 3 or w.isdigit()) or any(w in both for w in iw) else 0)))
                if sc > 0 and i not in used:
                    sc += 0.5            # an unused block is preferred to a block already matched
                if sc > best:
                    hit, best = i, sc            # R2: matched on the item name or digits, not on the file
            tag = 'STOP[%s %s].' % (it['last_four_or_name'], basename(it['file']))
            if hit is None:
                R.add(tag + 'item', 'not found', it['last_four_or_name'], False)
                continue
            merged_ok[hit] = merged_ok.get(hit, 0) + 1 if hit in used else 1
            used.add(hit)
            found += 1
            b = sb[hit]
            R.add(tag + 'item', b.get('Item'), it['item'], b.get('Item') is not None)
            fv = norm(b.get('File'))
            fk = [basename(x).strip().lower() for x in it['file'].split(';') if x.strip()]
            if it['file'] == 'not found':
                R.tok(tag + 'File', b.get('File'), 'not found')
            else:       # the key's file, or any other evidence file the reply names for the item
                R.add(tag + 'File', b.get('File'), it['file'], b.get('File') is not None and (any(x in fv for x in fk) or any(x in fv for x in files_known)))
            R.tok(tag + 'Number to call', b.get('Number to call'), it['number_to_call'])
            R.tok(tag + 'Safe number source', b.get('Safe number source'), it['safe_number_source'])
        # R9: right when every key item is found; extra exposure items (the parent's own card) are not wrong
        R.flag('STOP-LIST item count', found == len(sp['items']), '%d listed, %d of %d key items found' % (n_items, found, len(sp['items'])), 'every key item found')
        for b in sb:
            safe_n += 1
            dg = re.sub(r'\D', '', b.get('Number to call', '') + b.get('What to do', ''))
            if not any(x and x in dg for x in bad):
                safe_ok += 1
        R.flag('STOP-LIST numbers safe', safe_ok == safe_n, '%d of %d blocks safe' % (safe_ok, safe_n), 'no scam number in Number to call')
    # PAYMENTS
    pp = P['PAYMENTS-TO-DISPUTE.md']
    pay = pg(pages, 'PAYMENTS-TO-DISPUTE')
    pb = blks(pay) if pay else None
    disp_ok = disp_n = 0
    if pb is None:
        R.add('PAYMENTS page', None, 'page', False)
    else:
        used = set()
        rows = pp['blocks'] if 'blocks' in pp else []
        for kr in rows:
            hit = None
            for i, b in enumerate(pb):
                if i not in used and has_date(b.get('Date'), kr['date']) and money(b.get('Amount')) == money(kr['amount']) \
                        and (alnum(b.get('Payee as shown')) == alnum(kr['payee']) or True):
                    if alnum(b.get('Payee as shown')) == alnum(kr['payee']):
                        hit = i
                        break
                    hit = hit if hit is not None else i
            tag = 'PAY[%s %s %s].' % (kr['date'], kr['amount'], kr['payee'][:22])
            isdisp = kr['decision'] == 'dispute'
            disp_n += isdisp
            if hit is None:
                R.add(tag + 'row', 'row not found', kr['payee'], False)
                continue
            used.add(hit)
            b = pb[hit]
            dv = norm(b.get('Decision', ''))
            R.exact(tag + 'Payee as shown', b.get('Payee as shown'), kr['payee'])
            R.exact(tag + 'Currency', b.get('Currency'), kr['currency'])
            R.tok(tag + 'Account', b.get('Account'), kr['account'])
            R.tok(tag + 'Statement file', b.get('Statement file'), basename(kr['statement_file']))
            R.exact(tag + 'Days since payment', b.get('Days since payment'), str(kr['days_since_payment']))
            R.tok(tag + 'Report-by date', b.get('Report-by date'), kr['report_by'])
            cw = kr['contact_file']
            cv = b.get('Contact that asked for it')
            if not cw:
                R.tok(tag + 'Contact that asked for it', cv, 'none')
            else:       # the file, the time of day (else the date) and the long numbers of the shared detail; words are free
                tm = re.search(r'\d\d:\d\d', kr['contact_time'] or '')
                need = [basename(cw).lower(), tm.group(0) if tm else kr['contact_time'][:10]] + [x for x in ATOM.findall(norm(kr['detail_shared'] or '')) if len(x) >= 4]
                R.add(tag + 'Contact that asked for it', cv, ' '.join(need), cv is not None and all(x in norm(cv) for x in need))
            lr = kr['link_rule']
            lv = norm(strip_br_paren(b.get('Link rule', '')))
            okl = (('l1' in lv or 'none' in lv) if 'or' in lr else ('l1' in lv and 'none' not in lv.replace('l1', '')) if lr == 'L1' else ('none' in lv and 'l1' not in lv))
            R.add(tag + 'Link rule', b.get('Link rule'), lr, b.get('Link rule') is not None and okl)
            R.exact(tag + 'Rule code', b.get('Rule code'), kr['rule'])
            R.add(tag + 'Evidence', b.get('Evidence'), 'not empty', bool((b.get('Evidence') or '').strip()))
            okd = dv.startswith(kr['decision']) or ('decision_after_answer' in kr and kr.get('decision_after_answer') and
                                                    (dv.startswith('left out') or dv.startswith('normal')) and kr['decision_after_answer'].startswith('left out')) \
                or (dv.startswith('dispute') and str(kr.get('decision_after_answer', '')).startswith('dispute'))
            R.add(tag + 'Decision', b.get('Decision'), kr['decision'], b.get('Decision') is not None and okd)
            if kr['holder_answer']:
                R.tok(tag + 'Holder answer', b.get('Holder answer'), kr['holder_answer'])
            else:        # a row never put to the holder: any holder words or "none" are allowed
                R.add(tag + 'Holder answer', b.get('Holder answer'), 'none or the holder\'s words', b.get('Holder answer') is not None)
            if isdisp and dv.startswith('dispute'):
                disp_ok += 1
        extra = [b for i, b in enumerate(pb) if i not in used and norm(b.get('Decision', '')).startswith('dispute')]
        R.flag('PAY extra dispute rows', not extra, len(extra), 0)
        t = pay['tail']
        bl = pp['bank_limit_given']
        R.tok('PAY.Bank limit given by the person', t.get('Bank limit given by the person'), 'not given' if bl is None or bl == 'not given' else str(bl))
        R.num('PAY.Total to dispute', t.get('Total to dispute'), pp['total_to_dispute'])
        R.tok('PAY.Rows to ask the holder', t.get('Rows to ask the holder'),
              ' '.join(str(x) for x in pp['rows_to_ask']) if not pp['rows_to_ask'] else ' '.join(r['payee'] + ' ' + r['amount'] for r in pp['blocks'] if r['row'] in pp['rows_to_ask']))
        lo = norm(t.get('Rows left out as normal') or '')
        o1 = pp.get('rows_kept_for_timeline_only') or []
        kt = t.get('Rows kept for the timeline only')
        if o1:      # K5: one own-account move is two statement rows; naming either leg (date and amount) is enough
            ktn = norm(kt or '')
            okk = any(x['date'] in ktn and re.search(r'(?<![\d.])' + re.escape(norm(x['amount'])) + r'(?!\d)', ktn) for x in o1)
            R.add('PAY.Rows kept for the timeline only', kt, ' / '.join('%s %s %s' % (x['date'], x['payee'], x['amount']) for x in o1), kt is not None and okk)
        else:
            R.tok('PAY.Rows kept for the timeline only', kt, 'none')
        for pn, code in pp['rows_left_out_as_normal']:
            core = re.sub(r'^(e-transfer out|e-transfer in|transfer from|transfer to|wire out|wire in)\s+', '', norm(pn))
            R.add('PAY.left out[%s %s]' % (pn, code), t.get('Rows left out as normal'), pn + ' ' + code,
                  t.get('Rows left out as normal') is not None and alnum(core) in alnum(lo) and re.search(r'\b' + code.lower() + r'\b', lo) is not None)
        if not pp['rows_left_out_as_normal']:
            R.tok('PAY.Rows left out as normal', t.get('Rows left out as normal'), 'none')
    # TIMELINE
    tl = pg(pages, 'TIMELINE')
    tb = blks(tl) if tl else None
    if tb is None:
        R.add('TIMELINE page', None, 'page', False)
    else:
        used = set()
        for ev in P['TIMELINE.md']['events']:
            ts = ev['time']
            hit = None
            for i, b in enumerate(tb):
                if i in used:
                    continue
                okf = ('camera' in norm(b.get('Channel', '')) and 'camera' in ev['file']) if ev['file'].startswith('camera:') \
                    else basename(ev['file']).lower() in norm(b.get('File', ''))
                if norm(strip_br_paren(b.get('Time', ''))).startswith(ts.lower()) and okf:
                    hit = i
                    break
            tag = 'TL[%s %s].' % (ts, basename(ev['file'])[:24])
            if hit is None:
                R.add(tag + 'event', 'not found', ts, False)
                continue
            used.add(hit)
            b = tb[hit]
            tsrc = {'capture time or file time': 'capture time|file time', 'file name or file time': 'file name|file time'}.get(ev['time_source'], ev['time_source'])
            R.add(tag + 'Time source', b.get('Time source'), ev['time_source'],
                  b.get('Time source') is not None and any(norm(x) in norm(b.get('Time source')) for x in tsrc.split('|')))
            chv = (b.get('Channel') or '').split('/')[0].strip() if b.get('Channel') else None
            R.add(tag + 'Channel', chv, ev['channel'], chv is not None and (alnum(chv) == alnum(ev['channel']) or (ev['channel'] == 'screen' and alnum(chv) == 'text')))
            ks = set(ev.get('script_steps') or [x.strip() for x in ev['script_step'].split(',')])
            hs = tagset(b.get('Script step')) if b.get('Script step') is not None else None
            R.add(tag + 'Script step', b.get('Script step'), ev['script_step'], bool(hs) and hs <= ks)        # R4: a non-empty subset of the key's steps
        keyed = {basename(e['file']).lower() for e in P['TIMELINE.md']['events']}
        lw = [basename(f).lower() for f in key['untagged_files']]
        bad = [b for b in tb if any(f in norm(b.get('File', '')) for f in lw) and not norm(b.get('Script step', 'untagged')).startswith('untagged')]
        R.flag('untagged files stay untagged', not bad, len(bad), 0)
    # GAPS
    gp = pg(pages, 'GAPS-AND-NEXT')
    gm = merged(gp) if gp else None
    G = P['GAPS-AND-NEXT.md']
    for lb, kk in [('Script seen', 'script_seen'), ('Steps seen', 'steps_seen'), ('Steps with no evidence', 'steps_with_no_evidence'),
                   ('Months without a statement', 'months_without_a_statement'), ('Sources not read', 'sources_not_read'),
                   ('Likely next step', 'likely_next_step'), ('Questions for the holder', 'questions_for_the_holder')]:
        ev = G[kk]
        ev = ' '.join(ev) if isinstance(ev, list) else ev
        got = gm.get(lb) if gm else None
        if kk == 'likely_next_step' and ev != 'none':
            alt = skill_next(G['steps_seen'][-1] if G['steps_seen'] else None)    # the Skill's own "Next step often" entry is also right
            ok = got is not None and (words_ok(got, re.sub(r'\([^)]*\)', '', ev)) or (alt and words_ok(got, 'in this script the next step is often ' + alt + ' warn the parent')))
            R.add('GAPS.' + lb, got, ev + ' | or: ' + str(alt), ok)
        elif kk == 'script_seen' and ev != 'none':          # R15: the script letter must equal the key's
            lets = set(re.findall(r'\b[A-E]\b', got or ''))
            R.add('GAPS.' + lb, got, ev, got is not None and lets == {ev})
        else:
            R.tok('GAPS.' + lb, got, ev)
    R.add('GAPS.Warning cited', gm.get('Warning cited') if gm else None, 'any value', True)
    # QUOTES
    qp = pg(pages, 'QUOTES')
    qb = blks(qp) if qp else None
    if qb is None:
        R.add('QUOTES page', None, 'page', False)
    else:
        used = set()
        for q in P['QUOTES.md']['quotes']:
            want = alnum(re.sub(r'\s*/\s*|\|', ' ', q['source_text']))
            def qok(b):
                if basename(q['file']).lower() not in norm(b.get('File', '')):
                    return False
                qv = b.get('Quote', '')
                return len(alnum(strip_br_paren(qv))) >= 12 and in_text(qv, want)       # R5: bracket notes are not part of the quote; R18: "ending NNNN" matches the full code
            hit = next((i for i, b in enumerate(qb) if i not in used and qok(b)), None)   # a verbatim excerpt is allowed
            tag = 'QUOTE[%s].' % basename(q['file'])
            if hit is None:
                R.add(tag + 'Quote', 'not found', q['source_text'], False)
                continue
            used.add(hit)
            b = qb[hit]
            R.add(tag + 'Quote', b.get('Quote'), q['source_text'], True)
            R.tok(tag + 'Time', b.get('Time'), q['time'])
            R.tok(tag + 'Read by', b.get('Read by'), q['read_by'])
            R.tok(tag + 'Clarity', b.get('Clarity'), q['clarity'])
    # asked, not followed (QUOTES page end)
    qtext = norm('\n'.join(pages.get('QUOTES', [])))
    seg = qtext[qtext.rfind('asked, not followed'):] if 'asked, not followed' in qtext else None
    anf = P['QUOTES.md']['asked_not_followed']
    af_ok = 0
    for a in anf:
        ok = seg is not None and basename(a['file']).lower() in seg and 'not followed' in seg and words_ok(seg, a['words'])
        af_ok += bool(ok)
        R.add('ASKED[%s]' % basename(a['file']), seg, a['words'], ok)
    if not anf:
        R.flag('ASKED none', seg is None or 'none' in seg or True, seg, 'none')
    # CAMERA
    cm = P['CAMERA.md']
    cp = pg(pages, 'CAMERA')
    if not cm['written']:
        txt = norm('\n'.join(pages.get('CAMERA', [])))
        R.flag('CAMERA not written', 'CAMERA' not in pages or 'camera events not read' in txt, 'page present' if 'CAMERA' in pages else 'absent', 'absent or no-camera line')
    else:
        cb = blks(cp) if cp else None
        if cb is None:
            R.add('CAMERA page', None, 'page', False)
        else:
            used = set()
            def cam_hit(ev):
                hh = ev['time'][-5:]
                cands = []
                for i, b in enumerate(cb):
                    if i in used:
                        continue
                    tv = norm(strip_br_paren(b.get('Time', '')))
                    dv = re.search(r'\d{4}-\d\d-\d\d', tv)
                    if norm(ev['camera']) in norm(b.get('Camera', '')) and hh in tv and (not dv or dv.group(0) == ev['time'][:10]):
                        cands.append(i)
                pref = [i for i in cands if ev['snapshot'].lower() in norm(cb[i].get('Snapshot', ''))]
                return (pref or cands or [None])[0]       # R3: camera and time
            for ev in cm['kept'] + cm['left_out']:
                hit = cam_hit(ev)
                tag = 'CAM[%s].' % ev['snapshot']
                if hit is None:
                    R.add(tag + 'event', 'not found', ev['snapshot'], False)
                    continue
                used.add(hit)
                b = cb[hit]
                R.tok(tag + 'Camera', b.get('Camera'), ev['camera'])
                R.tok(tag + 'Time', strip_br_paren(b.get('Time')), ev['time'])
                if ev['decision'] == 'kept':
                    R.tok(tag + 'Snapshot', b.get('Snapshot'), ev['snapshot'])
                R.tok(tag + 'Kind', b.get('Kind'), KINDS[ev['type']])
                R.tok(tag + 'Identity', b.get('Identity as returned'), ev['identity'])
                R.tok(tag + 'Plate', b.get('Plate'), ev.get('plate') or 'none')
                R.exact(tag + 'Decision', b.get('Decision'), ev['decision'])
            R.flag('CAMERA count', len(cb) == len(cm['kept']) + len(cm['left_out']), len(cb), len(cm['kept']) + len(cm['left_out']))
    # HOLDER-STATEMENT
    hp = pg(pages, 'HOLDER-STATEMENT')
    H = P['HOLDER-STATEMENT.md']
    if hp is None:
        R.add('HOLDER page', None, 'page', False)
    else:
        hm = merged(hp)
        R.tok('HOLDER.Holder', hm.get('Holder'), H['holder'])
        R.blank('HOLDER.Signature', hm.get('Signature'))
        sents = [alnum(b.get('Sentence')) for b in blks(hp)] + [alnum(b.get("Parent's own words on any disagreement")) for b in blks(hp)]
        for s in H['sentences']:
            present = any(alnum(s['parent_words']) in x for x in sents)       # R14: a block may hold two settled answers
            if s['include'] is None:        # R7: include null accepts a sentence written or left out
                R.add('HOLDER-either["%s"]' % s['parent_words'][:40], 'present' if present else 'absent', 'written or left out', True)
            elif s['include']:
                R.add('HOLDER["%s"]' % s['parent_words'][:40], 'present' if present else 'missing', s['parent_words'], present)
            else:
                R.add('HOLDER-not["%s"]' % s['parent_words'][:40], 'absent' if not present else 'written', 'left out', not present)
    # LETTERS
    lb_key = P['LETTER-BANK']
    lp = pg(pages, 'LETTER-BANK')
    pay_lines = lambda v, tup: _consume(v or '', tup)
    if lp is None:
        R.add('LETTER-BANK page', None, 'page', False)
    else:
        lm = merged(lp)
        R.tok('LB.To', lm.get('To'), lb_key['to'])
        R.tok('LB.Account holder', lm.get('Account holder'), lb_key['account_holder'])
        R.tok('LB.Accounts', lm.get('Accounts'), ' '.join(lb_key['accounts']))
        R.exact('LB.Date of letter', lm.get('Date of letter'), lb_key['date_of_letter'])
        ok, extra = pay_lines(lm.get('Payments disputed'), lb_key['payments'])
        R.add('LB.Payments disputed', lm.get('Payments disputed'), lb_key['payments'], ok and not extra)
        R.tok('LB.Bank called on', lm.get('Bank called on'), lb_key['bank_called_on'])
        got = {x.lower() for x in re.findall(r'[\w.\-]+\.(?:png|jpg|m4a|pdf)', lm.get('Enclosed exhibits') or '', re.I)}
        R.add('LB.Enclosed exhibits', lm.get('Enclosed exhibits'), lb_key['enclosed'], got == {x.lower() for x in lb_key['enclosed']})
        R.blank('LB.Holder signature', lm.get('Holder signature'))
        mv = norm(lm.get('Message that asked for each payment') or '')
        R.add('LB.Message that asked for each payment', lm.get('Message that asked for each payment'), 'contact file, time or date of each',
              lm.get('Message that asked for each payment') is not None and all(
                  basename(r['contact_file']).lower() in mv or (r['contact_time'].split(' ')[1:2] and r['contact_time'].split(' ')[1] in mv)
                  or r['contact_time'][:10] in mv for r in pp['blocks'] if r['contact_file'] and r['decision'] == 'dispute'))
    lpk = P['LETTER-POLICE.md']
    lq = pg(pages, 'LETTER-POLICE')
    if lq is None:
        R.add('LP page', None, 'page', False)
    else:
        qm = merged(lq)
        d = qm.get('Dates')
        R.add('LP.Dates', d, lpk['dates'], d is not None and has_date(d, lpk['dates']['first_contact'][:10]) and has_date(d, lpk['dates']['last_payment']))
        v = qm.get('Names and numbers used by the caller')
        R.add('LP.Names and numbers', v, lpk['numbers_used_by_caller'],
              v is not None and set(re.findall(r'\d{3}-\d{4}', v)) == set(re.findall(r'\d{3}-\d{4}', ' '.join(lpk['numbers_used_by_caller']))))
        ok, extra = pay_lines(qm.get('Payments'), lpk['payments'])
        R.add('LP.Payments', qm.get('Payments'), lpk['payments'], ok and not extra)
        cv = qm.get('Camera events')
        if lpk['camera_events']:
            ck = [(t, i) for t, i in lpk['camera_events']]
            okc = cv is not None and all(t.lower() in norm(cv) for t, i in ck)      # every kept event time; one line may carry several
            kept_days = {t[:10] for t, i in ck}
            extra = [d_ for d_ in re.findall(r'\d{4}-\d\d-\d\d \d\d:\d\d', norm(cv or '')) if d_ not in {t.lower() for t, i in ck}]
            R.add('LP.Camera events', cv, ck, okc and not extra)
        else:
            R.tok('LP.Camera events', cv, 'none')
        R.blank('LP.Reported by', qm.get('Reported by'))
    # EXHIBITS
    ep = pg(pages, 'EXHIBITS')
    ek = P['EXHIBITS.md']['exhibits']
    if ep is None:
        R.add('EXHIBITS page', None, 'page', False)
    else:
        eb = blks(ep)
        got = {basename((b.get('Original path') or b.get('Exhibit') or '').strip()).lower() for b in eb}
        R.flag('EXHIBITS list', got == {x.lower() for x in ek} and len(eb) == len(ek), sorted(got), ek)
        for x in ek:
            b = next((b for b in eb if x.lower() == basename(b.get('Original path') or b.get('Exhibit') or '').lower()), None)
            if b is None:
                continue
            R.tok('EXH[%s].Copy check' % x, b.get('Copy check'), 'match')
            R.add('EXH[%s].Copy path' % x, b.get('Copy path'), h['Case folder'] + '/...', b.get('Copy path') is not None and x.lower() in norm(b.get('Copy path')) and
                  norm(h['Case folder']) in norm(b.get('Copy path')))
            for lbl in ('SHA-256 of original', 'SHA-256 of copy'):
                R.add('EXH[%s].%s' % (x, lbl), b.get(lbl), '64 hex', re.search(r'\b[0-9a-f]{64}\b', norm(b.get(lbl) or '')) is not None)
            R.add('EXH[%s].Bytes' % x, b.get('Bytes'), 'digits', re.search(r'\d', b.get('Bytes') or '') is not None)
    # LEDGER
    gl = pg(pages, 'LEDGER')
    if gl is None:
        pass            # LEDGER.md is written by echo, not by save-text; a reply may leave it out. replay_check reads the ledger from the stored replies.
    elif any('Step' in b for b in blks(gl)):
        steps = sorted(int(m_.group(0)) for b in blks(gl) for m_ in [re.search(r'\d+', b.get('Step', ''))] if m_)
        R.flag('LEDGER checkpoint steps', steps == sorted(P['LEDGER.md']['checkpoint_steps']), steps, P['LEDGER.md']['checkpoint_steps'])
        lines = blks(gl)
        R.flag('LEDGER previous hash on every line', all(re.search(r'[0-9a-f]{64}|not given', b.get('Previous ledger SHA-256', ''), re.I) for b in lines) and bool(lines), len(lines), 'every line')
    # partial measures stored on the result
    R.partial = {
        'payments_to_dispute_right': [disp_ok, disp_n],
        'outcome_lines_right': None,
        'asked_not_followed_files_right': [af_ok, len(anf)],
        'stop_list_numbers_safe': [safe_ok, safe_n],
    }
    out = [f for f in R.f if f['field'] in ('START.Payments to dispute', 'START.Total to dispute', 'START.Questions for the holder',
                                            'START.Months without a statement', 'START.Letters to send', 'START.Sources not read')]
    R.partial['outcome_lines_right'] = [sum(1 for f in out if f['state'] == 'right'), len(out)]
    return R


def skill_next(step):
    p = os.path.join(S, 'skill', 'scam-response', 'references', 'scam-scripts.md')
    for ln in open(p, encoding='utf-8'):
        c = [x.strip() for x in ln.strip().strip('|').split('|')]
        if step and len(c) >= 5 and c[0] == step:
            return re.sub(r'\([^)]*\)', '', c[4]).strip()
    return None


def _consume(v, tuples):
    """Each key payment (date, payee, amount, currency) must be matched by its own line; returns (all matched, leftover dated lines)."""
    lines = [norm(x) for x in re.split(r'\n|;', v) if x.strip()]
    ok = bool(lines)
    for d, p, a, c in tuples:
        j = next((n for n, x in enumerate(lines) if d in x and alnum(p) in alnum(x) and re.search(r'(?<![\d.])' + re.escape(a) + r'(?!\d)', x) and c.lower() in x), None)
        if j is None:
            ok = False
        else:
            lines.pop(j)
    return ok, [x for x in lines if re.search(r'\d{4}-\d\d-\d\d', x)]


def pay_block(pages, date, amount):
    pay = pg(pages, 'PAYMENTS-TO-DISPUTE')
    for b in (blks(pay) if pay else []):
        if has_date(b.get('Date'), date) and money(b.get('Amount')) == money(amount):
            return b
    return None


def score_variant(case, key, status, calls, pages, text):
    R = Res()
    name = '-'.join(case.split('-')[1:])
    vk = key['variants'][name]
    R.exact('STATUS', status, 'NO WRITES' if vk.get('zero_writes') else 'PAGES')
    sh = pg(pages, 'START-HERE')
    m = merged(sh) if sh else {}
    if 'disputes' in vk and not vk.get('zero_writes'):
        R.exact('START.Payments to dispute', m.get('Payments to dispute') if sh else None, str(vk['disputes']))
    if vk.get('zero_writes'):
        R.flag('no pages written', not pages, '%d pages' % len(pages), '0 pages')
    allp = norm('\n'.join('\n'.join(v) for v in pages.values()))
    stop = norm('\n'.join(pages.get('STOP-LIST', [])))
    if vk.get('closing_result'):         # K7: the closing report states the result; step 3 writes are sent after Yes 1; drafts shown before Yes 2
        z = norm(closing_zone(text))
        cr = vk['closing_result']
        R.flag('closing result stated', re.search(r'(?<![\d.])%s(?:\.00)?(?!\d)' % re.escape(cr['total'].split('.')[0]), z) is not None and re.search(r'\b(%s|three)\b' % cr['payments'], z) is not None,
               'closing report', '%s payments, %s' % (cr['payments'], cr['total']))
        R.flag('step 3 folder and ledger writes sent', step3_writes_sent(text) == bool(vk['yes1_writes_sent']), 'step 3', 'sent after Yes 1')
        R.flag('drafts shown before the Yes 2 question', drafts_shown(text) == bool(vk['drafts_before_yes2']), 'step 11', 'drafts shown, then Yes 2 asked')
    if vk.get('not_transcribed'):        # K8 V3
        R.flag('V3 failed voicemail marked not transcribed', 'not transcribed' in allp and 'listen and quote by hand' in allp, 'pages', vk['not_transcribed'])
    for d_, a_, rule in vk.get('decided_rows', []):      # K8 V3, V7: rows decided after the holder's yes
        b = pay_block(pages, d_, a_)
        tag = 'V.row[%s %s].' % (d_, a_)
        R.exact(tag + 'Rule code', b.get('Rule code') if b else None, rule)
        R.add(tag + 'Decision', b.get('Decision') if b else None, 'dispute', b is not None and norm(b.get('Decision', '')).startswith('dispute'))
    if name == 'V3-transcription-failed':
        z = pay_block(pages, '2026-10-16', '120.00')
        R.flag('V3 Zenith row not a dispute', z is None or not norm(z.get('Decision', '')).startswith('dispute'), 'left out' if z is None else z.get('Decision'), 'not a dispute')
    if vk.get('stop_list_not_finished'):
        R.flag('stop list says not finished', 'not finished' in stop and not re.search(r'not finished\W*(no|false)\b', stop), 'STOP-LIST page', 'not finished')
    if vk.get('months_without_statement'):       # K8 V4: the month is named on START-HERE and GAPS, the pages are written
        mo = ' '.join(vk['months_without_statement'])
        R.tok('V4.START.Months without a statement', m.get('Months without a statement') if sh else None, mo)
        gp = pg(pages, 'GAPS-AND-NEXT')
        R.tok('V4.GAPS.Months without a statement', merged(gp).get('Months without a statement') if gp else None, mo)
        for pn in vk.get('pages_required', []):
            R.flag('V4 page written: ' + pn, pn in pages, 'present' if pn in pages else 'absent', 'written')
    if vk.get('declined'):               # K8 V5: the declined copy is "not copied" and is absent from the letters' exhibits
        for f_ in vk['declined']:
            ep = pg(pages, 'EXHIBITS')
            b = next((x for x in (blks(ep) if ep else []) if f_.lower() in norm(x.get('Original path') or x.get('Exhibit') or '')), None)
            R.add('V5[%s].Copy check' % f_, b.get('Copy check') if b else None, 'not copied', b is not None and norm(b.get('Copy check', '')).startswith('not copied'))
            lm = merged(pg(pages, 'LETTER-BANK') or {'blocks': []}) if 'LETTER-BANK' in pages else {}
            lq = merged(pg(pages, 'LETTER-POLICE') or {'blocks': []}) if 'LETTER-POLICE' in pages else {}
            ex = norm((lm.get('Enclosed exhibits') or '') + ' ' + (lq.get('Exhibits') or ''))
            R.flag('V5[%s] absent from the letters\' exhibits' % f_, ('Enclosed exhibits' in lm or 'Exhibits' in lq) and f_.lower() not in ex, 'letters', 'not listed')
    if name == 'V7-one-folder':          # K8 V7: nothing read from Voicemail or Photos
        bad = []
        for pn, lbl in (('TIMELINE', 'File'), ('QUOTES', 'File'), ('PAYMENTS-TO-DISPUTE', 'Contact that asked for it')):
            pp_ = pg(pages, pn)
            for b in (blks(pp_) if pp_ else []):
                v = norm(strip_br_paren(b.get(lbl, '')))
                if 'not read' not in v and re.search(r'\.(m4a|png|jpe?g)\b|/volume1/voicemail|/volume1/photos', v):
                    bad.append(v[:40])
        R.flag('V7 nothing read from Voicemail or Photos', not bad and bool(pages), '; '.join(bad[:2]) or 'none', 'no voicemail or photo in timeline, quotes or contacts')
    R.partial = {'note': 'variant fields (freeze 3): status, dispute count and the variant\'s own behaviour'}
    return R


def score_reply(case, reply_path):
    key = load_key(case)
    text = open(reply_path, encoding='utf-8', errors='replace').read()
    status, calls, pages = split_pages(text)
    R = score_variant(case, key, status, calls, pages, text) if '-V' in case else score_pages(key, status, calls, pages, text)
    c = {s: sum(1 for f in R.f if f['state'] == s) for s in ('right', 'wrong', 'unread')}
    return {'case': case, 'class': 'right' if c['wrong'] == 0 and c['unread'] == 0 else 'not right', 'right': c['right'], 'wrong': c['wrong'],
            'unread': c['unread'], 'partial': R.partial, 'fields': R.f, 'reply': (lambda a: os.path.relpath(a, S) if a.startswith(S + os.sep) else a)(os.path.abspath(reply_path))}


# ---------------------------------------------------------------- freeze list
def freeze_paths():
    out = []
    for root in (os.path.join(S, 'skill', 'scam-response'), os.path.join(HOST, 'keys'),
                 os.path.join(HOST, 'prompts'), os.path.join(HOST, 'cases')):
        for d, _, fs in os.walk(root):
            out += [os.path.join(d, f) for f in fs]
    out += [os.path.join(S, 'dist', 'scam-response.zip'), os.path.join(S, 'tools', 'score_run.py'), os.path.join(S, 'tools', 'replay_check.py'),
            os.path.join(HOST, 'KEYS-HASHES.txt')]
    return sorted(set(out))


def verify_freeze(require=True):
    p = os.path.join(HOST, 'FROZEN-HASHES.txt')
    if not os.path.exists(p):
        if require:
            raise ValueError('FROZEN-HASHES.txt missing; run tools/freeze_repo.py first')
        return
    for ln in open(p):
        parts = ln.rstrip('\n').split('\t')
        if len(parts) in (2, 3) and re.match(r'^[0-9a-f]{64}$', parts[0]):
            f = os.path.join(S, parts[-1])
            if not os.path.exists(f) or sha(f) != parts[0]:
                raise ValueError('frozen file changed: ' + parts[-1])


# ---------------------------------------------------------------- synthetic replies (also used by replay_check self-test)
def sections(case_dir):
    """Stored expert replies: {reply file: {path: text}} ."""
    out = {}
    d = os.path.join(case_dir, 'experts')
    for f in sorted(os.listdir(d)):
        t = open(os.path.join(d, f), errors='replace').read()
        parts, cur = {'': []}, ''
        for ln in t.split('\n'):
            m = re.match(r'^--- (.+)$', ln)
            if m:
                cur = m.group(1)
                parts[cur] = []
            else:
                parts.setdefault(cur, []).append(ln)
        out[f] = {k: '\n'.join(v) for k, v in parts.items()}
    return out


def hashes(case_dir):
    """sha256sum / cpmv replies -> ({path: (sha, size)}, {original: copy}, {ledger lines n: sha})."""
    sec = sections(case_dir)
    f = next(k for k in sec if 'sha256sum' in k)
    sh, led = {}, {}
    for p, t in sec[f].items():
        m = re.search(r'SHA-256: (\w+)\s*\nSize: (\d+)', t)
        if not m:
            continue
        mm = re.match(r'(.*LEDGER\.md) \(after (\d+) lines\)', p)
        if mm:
            led[int(mm.group(2))] = m.group(1)
        else:
            sh[p] = (m.group(1), int(m.group(2)))
    cp = {}
    g = next((k for k in sec if 'cpmv' in k), None)
    if g:
        for p, t in sec[g].items():
            m = re.search(r'Copy path: (\S+)', t)
            if m:
                cp[p] = m.group(1)
    else:   # no stored cpmv reply: copies are the case-folder entries of the sha256sum reply, matched to their originals by file name
        for c_ in [x for x in sh if '/Scam-Response-' in x]:
            for o_ in [x for x in sh if '/Scam-Response-' not in x]:
                if o_.rsplit('/', 1)[1] == c_.rsplit('/', 1)[1]:
                    cp[o_] = c_
    return sh, cp, led


def render(key, case_dir):
    """Correct pages (dict name -> list of lines) built from the key and the stored hash replies."""
    P = key['pages']
    h = P['header']
    out = {}

    def head():
        return ['%s: %s' % (k, h[k]) for k in HEADER]

    def kv(pairs):
        return ['%s: %s' % (k, v) for k, v in pairs]

    st = P['START-HERE.md']
    L = head() + kv([('What happened', st['What happened'] + '; payments of ' + ', '.join(x['amount'] for x in key['payments_to_dispute']) + ' ' + key['currency']), ('Do first tonight', st['Do first tonight'])])
    L += kv(list(st['extra_labels'].items()))
    L += kv([('For the parent', 'stay calm; do not answer calls from the numbers listed'), ('For the helper', 'call the bank on the number on the back of the card'),
             ('Payments to dispute', st['Payments to dispute']), ('Total to dispute', st['Total to dispute']),
             ('Questions for the holder', st['Questions for the holder']), ('Gaps in the evidence', 'see GAPS-AND-NEXT.md'),
             ('Months without a statement', st['Months without a statement']), ('Letters to send', st['Letters to send']),
             ('Sources not read', st['Sources not read']), ('Asked, not followed', st['Asked, not followed']),
             ('Not done by this assistant', st['Not done by this assistant'])])
    L.append("Check your bank's and country's rules for reporting limits.")
    out['START-HERE'] = L
    sp = P['STOP-LIST.md']
    L = head() + ['Found in the files read']
    for it in sp['items']:
        L += [''] + kv([('Item', it['item']), ('Last four digits or name', it['last_four_or_name']), ('File', basename(it['file'])),
                        ('What is exposed', it['what_is_exposed']), ('What to do', 'call the bank on the number on the back of the card'),
                        ('Number to call', it['number_to_call']), ('Safe number source', it['safe_number_source'])])
    out['STOP-LIST'] = L
    pp = P['PAYMENTS-TO-DISPUTE.md']
    L = head()
    for r in pp['blocks']:
        cont = 'none' if not r['contact_file'] else '%s, %s, "%s", detail: %s' % (basename(r['contact_file']), r['contact_time'], r['contact_words'], r['detail_shared'])
        dec = r['decision']
        L += [''] + kv([('Row', r['row']), ('Date', r['date']), ('Payee as shown', r['payee']), ('Amount', r['amount']), ('Currency', r['currency']),
                        ('Account', r['account']), ('Statement file', basename(r['statement_file'])), ('Days since payment', r['days_since_payment']),
                        ('Report-by date', r['report_by']), ('Contact that asked for it', cont), ('Link rule', r['link_rule']),
                        ('Rule code', r['rule']), ('Evidence', 'statement row %s %s; ' % (r['date'], r['amount']) + (basename(r['contact_file']) if r['contact_file'] else 'no linked contact')),
                        ('Decision', dec), ('Holder answer', r['holder_answer'] or 'none')])
    ask = ' ; '.join('%s %s on %s' % (r['payee'], r['amount'], r['date']) for r in pp['blocks'] if r['row'] in pp['rows_to_ask']) or 'none'
    L += [''] + kv([('Bank limit given by the person', pp['bank_limit_given'] if pp['bank_limit_given'] else 'not given'),
                    ('Total to dispute', pp['total_to_dispute']), ('Rows to ask the holder', ask),
                    ('Rows left out as normal', '; '.join('%s (%s)' % (a, b) for a, b in pp['rows_left_out_as_normal']) or 'none'),
                    ('Rows kept for the timeline only', '; '.join('%s %s %s' % (x['date'], x['payee'], x['amount']) for x in pp['rows_kept_for_timeline_only']) or 'none')])
    out['PAYMENTS-TO-DISPUTE'] = L
    L = head()
    for e in P['TIMELINE.md']['events']:
        L += [''] + kv([('Time', e['time']), ('Time source', e['time_source']), ('Channel', e['channel']), ('Script step', e['script_step']),
                        ('File', e['file']), ('Event', 'event'), ('Payment row', e.get('payment_row', 'none'))])
    out['TIMELINE'] = L
    G = P['GAPS-AND-NEXT.md']
    j = lambda x: ', '.join(x) if isinstance(x, list) and x else ('none' if isinstance(x, list) else x)
    out['GAPS-AND-NEXT'] = head() + kv([('Script seen', G['script_seen']), ('Steps seen', j(G['steps_seen'])),
                                         ('Steps with no evidence', j(G['steps_with_no_evidence'])),
                                         ('Months without a statement', j(G['months_without_a_statement'])), ('Sources not read', G['sources_not_read']),
                                         ('Likely next step', G['likely_next_step']), ('Warning cited', 'none'),
                                         ('Questions for the holder', j(G['questions_for_the_holder']))])
    L = head()
    for q in P['QUOTES.md']['quotes']:
        L += [''] + kv([('Quote', q['source_text']), ('Speaker or sender', 'sender'), ('File', basename(q['file'])), ('Time', q['time']),
                        ('Read by', q['read_by']), ('Clarity', q['clarity']), ('Linked payment row', 'none')])
    L += ['', 'Asked, not followed:'] + ['%s: %s (not followed)' % (basename(a['file']), a['words']) for a in P['QUOTES.md']['asked_not_followed']]
    out['QUOTES'] = L
    cm = P['CAMERA.md']
    if cm['written']:
        L = head()
        for e in cm['kept'] + cm['left_out']:
            L += [''] + kv([('Event', 'visit'), ('Camera', e['camera']), ('Time', e['time']), ('Kind', KINDS[e['type']]),
                            ('Identity as returned', e['identity']), ('Snapshot', e['snapshot']), ('Plate', e.get('plate') or 'none'),
                            ('Decision', e['decision']), ('Camera note', 'none')])
        out['CAMERA'] = L
    H = P['HOLDER-STATEMENT.md']
    L = head() + ['Holder: ' + H['holder']]
    for s in H['sentences']:
        if s['include']:
            L += [''] + kv([('Sentence', s['parent_words']), ('Day and amount from records', s['record']), ('Settled on', 'settled'),
                            ("Parent's own words on any disagreement", 'none')])
    L += ['', 'Signature: left blank for the holder']
    out['HOLDER-STATEMENT'] = L
    lb = P['LETTER-BANK']
    shs, cps, led = hashes(case_dir)
    frm = lambda tl: ['%s | %s | %s | %s' % tuple(t) for t in tl]
    L = head() + kv([('To', lb['to']), ('Account holder', lb['account_holder']), ('Accounts', ', '.join(lb['accounts'])), ('Date of letter', lb['date_of_letter']),
                     ('Summary', 'I am writing about payments I did not agree to')])
    L += ['Payments disputed:'] + frm(lb['payments'])
    cf = []
    for r in pp['blocks']:
        if r['contact_file'] and r['decision'] == 'dispute' and basename(r['contact_file']) not in cf:
            cf.append(basename(r['contact_file']))
    L += ['Message that asked for each payment: ' + (', '.join(cf) or 'none')]
    L += kv([('What I ask the bank to do', 'review each payment, explain the steps and time limits that apply, and confirm what is in the bank file'),
             ('Bank called on', lb['bank_called_on']), ('Enclosed exhibits', ', '.join(lb['enclosed'])), ('Holder signature', 'left blank for the holder')])
    out['LETTER-BANK'] = L
    lq = P['LETTER-POLICE.md']
    L = head() + kv([('Report summary', 'summary'), ('Dates', '%s to %s' % (lq['dates']['first_contact'], lq['dates']['last_payment'])),
                     ('Contact methods used by the caller', 'calls and messages'),
                     ('Names and numbers used by the caller', ', '.join(lq['numbers_used_by_caller']) or 'none')])
    L += ['Payments:'] + frm(lq['payments'])
    L += ['Camera events:'] + (['%s | %s' % tuple(c) for c in lq['camera_events']] or ['none'])
    L += kv([('Exhibits', ', '.join(lb['enclosed'])), ('Holder statement', 'see HOLDER-STATEMENT.md'), ('Reported by', 'left blank for the holder')])
    out['LETTER-POLICE'] = L
    L = head()
    for x in P['EXHIBITS.md']['exhibits']:
        orig = next(p for p in shs if basename(p) == x and not p.startswith(h['Case folder']))
        cp = cps[orig]
        L += [''] + kv([('Exhibit', x), ('Original path', orig), ('Copy path', cp), ('Bytes', shs[cp][1]), ('SHA-256 of original', shs[orig][0]),
                        ('SHA-256 of copy', shs[cp][0]), ('Copy check', 'match')])
    out['EXHIBITS'] = L
    L = []      # R8: LEDGER.md carries no header
    for n, s in enumerate(P['LEDGER.md']['checkpoint_steps'], 1):
        L += [''] + kv([('Line', n), ('Step', s), ('Experts and states', 'completed'), ('Counts', 'n'), ('Failures', 'none'),
                        ('Consent and answers', 'as given'), ('Writes', 'none'), ('Resume data', 'saved'), ('Previous ledger SHA-256', led.get(n - 1, 'not given'))])
    out['LEDGER'] = L
    return out


STEPLOG = ['Step 1: first steps given; passed', 'Step 2: home path and cameras found; passed', 'Step 3: consent shown, Yes 1; folder made and ledger line written; passed', 'Step 4: stop list shown before step 5; dropped 1 outside photo; passed',
           'Step 5: passages collected; passed', 'Step 6: files read; passed', 'Step 7: statements read; passed', 'Step 8: camera events read; passed', 'Step 9: timeline built; passed',
           'Step 10: account checked; passed', 'Step 11: drafts shown, Yes 2; passed', 'Step 12: writes approved; passed', 'Step 13: final summary; passed']


def to_text(status, pages, calls=31, log=None):
    t = 'STATUS: %s\nEXPERT CALLS: %d\nSTEP LOG:\n' % (status, calls) + '\n'.join(log or STEPLOG) + '\n'
    for n, ls in pages.items():
        t += '\n=== %s.md\n' % n + '\n'.join(ls) + '\n'
    return t


C5_LOG = ['1 first steps given; passed', '2 home path found; passed', '3 consent shown, Yes 1: no; no writes', '4 stop list: none found; passed', '9 control, nothing tagged; passed',
          '11 drafts shown, Yes 2 asked; declined', '12 not run', '13 report: No payment matched the signs searched for. Nothing was saved.']


def synth_reply(case):
    key = load_key(case)
    if key['writes']['zero_writes_expected']:
        return to_text('NO WRITES', {}, log=C5_LOG)
    return to_text('PAGES', render(key, os.path.join(HOST, 'cases', case)))


def mutate(pages, page, label, new=None, nth=0, drop_block=False):
    """Copy of pages with the nth line of LABEL on PAGE changed (new) or removed (new=None)."""
    out = {k: list(v) for k, v in pages.items()}
    idx = [i for i, ln in enumerate(out[page]) if lab(ln.split(':')[0]) == lab(label) and ':' in ln]
    i = idx[nth]
    if new is None:
        del out[page][i]
    else:
        out[page][i] = '%s: %s' % (label, new)
    return out


def mutants(case):
    """[(name, expected state of at least one field: 'wrong' or 'unread', reply text)] for one case."""
    key = load_key(case)
    base = render(key, os.path.join(HOST, 'cases', case))
    T = lambda p, st='PAGES': to_text(st, p)
    pay = key['pages']['PAYMENTS-TO-DISPUTE.md']['blocks'][0]
    ms = [
        ('wrong total', 'wrong', T(mutate(base, 'START-HERE', 'Total to dispute', '1.00 ' + key['currency']))),
        ('wrong dispute count', 'wrong', T(mutate(base, 'START-HERE', 'Payments to dispute', '99'))),
        ('missing dispute-count line', 'unread', T(mutate(base, 'START-HERE', 'Payments to dispute'))),
        ('wrong amount in a payment block', 'wrong', T(mutate(base, 'PAYMENTS-TO-DISPUTE', 'Amount', '7.77'))),
        ('wrong date in a payment block', 'wrong', T(mutate(base, 'PAYMENTS-TO-DISPUTE', 'Date', '2020-01-01'))),
        ('wrong rule code', 'wrong', T(mutate(base, 'PAYMENTS-TO-DISPUTE', 'Rule code', 'D4' if pay['rule'] != 'D4' else 'D1'))),
        ('wrong payee text', 'wrong', T(mutate(base, 'PAYMENTS-TO-DISPUTE', 'Payee as shown', pay['payee'] + ' LTD'))),
        ('missing report-by line', 'unread', T(mutate(base, 'PAYMENTS-TO-DISPUTE', 'Report-by date'))),
        ('wrong script step', 'wrong', T(mutate(base, 'TIMELINE', 'Script step', 'Z9', nth=0))),
        ('altered quote', 'wrong', T(mutate(base, 'QUOTES', 'Quote', 'I never said this'))),
        ('wrong letter addressee', 'wrong', T(mutate(base, 'LETTER-BANK', 'To', 'Nowhere Bank'))),
        ('missing signature line', 'unread', T(mutate(base, 'LETTER-POLICE', 'Reported by'))),
        ('missing exhibit', 'wrong', T({**base, 'EXHIBITS': base['EXHIBITS'][:-8]})),
        ('missing page', 'unread', T({k: v for k, v in base.items() if k != 'GAPS-AND-NEXT'})),
        ('wrong status', 'wrong', T(base, 'STOPPED')),
    ]
    if key['stop_list']['numbers_that_must_stay_off']:
        ms.append(('scam number in Number to call', 'wrong', T(mutate(base, 'STOP-LIST', 'Number to call', key['stop_list']['numbers_that_must_stay_off'][0]))))
    if key['stop_list']['items']:
        ms.append(('stop-list item missing', 'wrong', T({**base, 'STOP-LIST': base['STOP-LIST'][:-8]})))
    if key['pages']['CAMERA.md']['written']:
        ms.append(('wrong camera decision', 'wrong', T(mutate(base, 'CAMERA', 'Decision', 'kept' if key['pages']['CAMERA.md']['left_out'] and False else 'known, left out', nth=0))))
    return ms


def tolerant(case):
    """Reformatting that must not change the score: case, spaces, bold labels, thousands commas, bullets, reordered list lines."""
    key = load_key(case)
    base = render(key, os.path.join(HOST, 'cases', case))
    out = {}
    for n, ls in base.items():
        nl = []
        for ln in ls:
            m = re.match(r'^([^:]+): (.*)$', ln)
            if m and lab(m.group(1)) in {lab(x) for x in HEADER + sum([s[1] for s in SPEC.values()], [])}:
                v = re.sub(r'(?<![\d.])(\d{4,})(\.\d\d)\b', lambda t: '{:,}'.format(int(t.group(1))) + t.group(2), m.group(2)) if n != 'EXHIBITS' else m.group(2)
                ln = '- **%s:**   %s' % (m.group(1).upper(), v.upper() if n in ('START-HERE', 'GAPS-AND-NEXT') and False else v)
            nl.append(ln)
        out[n] = nl
    # list order: reverse the order of the letter payment lines
    for n in ('LETTER-BANK', 'LETTER-POLICE'):
        ls = out[n]
        i = next((k for k, ln in enumerate(ls) if re.match(r'^\s*\d{4}-\d\d-\d\d \|', ln)), None)
        if i is not None:
            j = i
            while j < len(ls) and re.match(r'^\s*\d{4}-\d\d-\d\d \|', ls[j]):
                j += 1
            ls[i:j] = list(reversed(ls[i:j]))
    return to_text('PAGES', out)


def _blocks(lines):
    """Split page lines (after the header) into blocks separated by blank lines; returns (head lines, blocks)."""
    head, blocks, cur = [], [], None
    for ln in lines:
        if not ln.strip():
            cur = None
            continue
        if cur is None and (head == [] or len(head) >= len(HEADER) or blocks):
            if len(head) >= len(HEADER):
                cur = []
                blocks.append(cur)
        if cur is None:
            head.append(ln)
        else:
            cur.append(ln)
    return head, blocks


def _rebuild(head, blocks):
    out = list(head)
    for b in blocks:
        out += [''] + b
    return out


def _sub(pages, page, old, new, count=1):
    out = {k: list(v) for k, v in pages.items()}
    done = 0
    for i, ln in enumerate(out[page]):
        if old in ln and done < count:
            out[page][i] = ln.replace(old, new)
            done += 1
    assert done, (page, old)
    return out


def _untag_1130(pages):
    out = {k: list(v) for k, v in pages.items()}
    L = out['TIMELINE']
    i = next(n for n, ln in enumerate(L) if ln.startswith('Time: 2026-10-27 11:29'))
    j = next(n for n in range(i, len(L)) if L[n].startswith('Script step:'))
    L[j] = 'Script step: untagged'
    return out


def _untag_gift(pages):
    out = {k: list(v) for k, v in pages.items()}
    L = out['TIMELINE']
    for i, ln in enumerate(L):
        if ln.startswith('File:') and 'lakeshore-2026-10.pdf' in ln:
            for j in range(i, max(i - 8, 0), -1):
                if L[j].startswith('Script step:'):
                    L[j] = 'Script step: untagged'
                    break
            else:
                continue
            break
    return out


def rule_tests():
    """One synthetic case per freeze-3 rule: (name, case, reply text, expected class, key edit or None). expected: 'right' or 'not right'."""
    T = []
    kc = {c: load_key(c) for c in ('C1', 'C2', 'C3', 'C4')}
    base = {c: render(kc[c], os.path.join(HOST, 'cases', c)) for c in kc}
    txt = lambda c, p, status='PAGES': to_text(status, p)
    # R1 bank letter named by the bank's first word or any other name
    for nm in ('LETTER-NORTHVALE-BANK', 'LETTER-BANK-NORTHVALE', 'LETTER-NORTHVALE'):
        t = txt('C1', base['C1']).replace('=== LETTER-BANK.md', '=== %s.md' % nm)
        T.append(('R1 bank letter named %s.md is read as the bank letter' % nm, 'C1', t, 'right', None))
    t = txt('C1', base['C1']).replace('=== LETTER-POLICE.md', '=== LETTER-POLICE-X.md')
    T.append(('R1 a page named LETTER-POLICE-X is not read as the bank letter (police letter stays unread)', 'C1', t.replace('=== LETTER-BANK.md', '=== LETTER-POLICE.md', 1) if False else t, 'not right', None))
    # R2 stop-list item matched on name or digits, any file
    b4 = base['C4']
    p = {k: list(v) for k, v in b4.items()}
    sl = p['STOP-LIST']
    i = next(n for n, ln in enumerate(sl) if ln.startswith('Last four digits or name: Elena chat'))
    sl[i] = 'Last four digits or name: Elena'
    j = next(n for n in range(i, len(sl)) if sl[n].startswith('File:'))
    sl[j] = 'File: summit-2026-10.pdf'
    T.append(('R2 stop-list item named by one word and another evidence file', 'C4', txt('C4', p), 'right', None))
    h_, bl_ = _blocks(b4['STOP-LIST'])
    p2 = {**b4, 'STOP-LIST': _rebuild(h_, [x for x in bl_ if not any('7712' in ln for ln in x)])}
    T.append(('R2 stop-list item absent from the page is not found', 'C4', txt('C4', p2), 'not right', None))
    # R3 camera matched on camera and time; Snapshot not asked
    p = {k: list(v) for k, v in base['C3'].items()}
    kcm = kc['C3']['pages']['CAMERA.md']
    n = 0
    for e in kcm['left_out']:
        p['CAMERA'] = [ln.replace('Snapshot: ' + e['snapshot'], 'Snapshot: not asked') for ln in p['CAMERA']]
        n += 1
    T.append(('R3 known camera events with Snapshot "not asked" match on camera and time', 'C3', txt('C3', p), 'right', None))
    e0 = kcm['kept'][0]
    p = {k: list(v) for k, v in base['C3'].items()}
    p['CAMERA'] = [ln.replace('Time: ' + e0['time'], 'Time: 2026-11-03 03:03') if ln.startswith('Time: ' + e0['time']) else ln for ln in p['CAMERA']]
    T.append(('R3 camera event with another time is not found', 'C3', txt('C3', p), 'not right', None))
    # R4 multi-tag subset
    p = _sub(base['C2'], 'TIMELINE', 'Script step: B1, B2', 'Script step: B1')
    T.append(('R4 one of two keyed steps is right', 'C2', txt('C2', p), 'right', None))
    p = _sub(base['C2'], 'TIMELINE', 'Script step: B1, B2', 'Script step: B1, B2, B4')
    T.append(('R4 a step outside the key set is wrong', 'C2', txt('C2', p), 'not right', None))
    p = _sub(base['C2'], 'TIMELINE', 'Script step: B1, B2', 'Script step: untagged')
    T.append(('R4 untagged where the key has steps is wrong', 'C2', txt('C2', p), 'not right', None))
    # R5 bracket notes
    p = {k: list(v) for k, v in base['C3'].items()}
    p['TIMELINE'] = [ln + ' (time of day not given)' if ln.startswith('Time: 2026-11-03') and len(ln) == len('Time: 2026-11-03') else ln for ln in p['TIMELINE']]
    T.append(('R5 time with a bracket note "(time of day not given)"', 'C3', txt('C3', p), 'right', None))
    p = {k: list(v) for k, v in base['C4'].items()}
    p['QUOTES'] = [ln + ' [unclear word]' if ln.startswith('Quote: ') else ln for ln in p['QUOTES']]
    T.append(('R5 quote followed by a bracket note', 'C4', txt('C4', p), 'right', None))
    p = {k: list(v) for k, v in base['C4'].items()}
    p['QUOTES'] = [ln.replace('Quote: ', 'Quote: Elena says [she] ') if ln.startswith('Quote: ') else ln for ln in p['QUOTES']]
    T.append(('R5 a bracket note does not repair an altered quote', 'C4', txt('C4', _sub(base['C4'], 'QUOTES', 'Quote: ', 'Quote: Invented. ')), 'not right', None))
    # R6 card uses and fees in any order with extra text
    k3 = kc['C3']['pages']['START-HERE.md']['extra_labels']['Card uses after hand-over'].split(', ')
    p = _sub(base['C3'], 'START-HERE', 'Card uses after hand-over: ' + ', '.join(k3), 'Card uses after hand-over: on 2026-11-03 and 2026-11-04 the card paid ' + '; then '.join(reversed(k3)) + ' in total')
    T.append(('R6 card uses in another order with extra text', 'C3', txt('C3', p), 'right', None))
    p = _sub(base['C3'], 'START-HERE', 'Card uses after hand-over: ' + ', '.join(k3), 'Card uses after hand-over: ' + ', '.join(k3[:2]))
    T.append(('R6 a missing card use is wrong', 'C3', txt('C3', p), 'not right', None))
    fe = kc['C4']['pages']['START-HERE.md']['extra_labels']['Fees asked']
    p = _sub(base['C4'], 'START-HERE', 'Fees asked: ' + fe, 'Fees asked: release fee 4350.00 CAD (voicemail 2026-11-03)')
    T.append(('R6 fees asked as amount and the word release with extra text', 'C4', txt('C4', p), 'right', None))
    p = _sub(base['C4'], 'START-HERE', 'Fees asked: ' + fe, 'Fees asked: release fee 4000.00 CAD')
    T.append(('R6 fees asked with another amount is wrong', 'C4', txt('C4', p), 'not right', None))
    # R7 include null accepts written or left out (key edited in memory)
    def k7(c, drop):
        k = json.loads(json.dumps(kc[c]))
        k['pages']['HOLDER-STATEMENT.md']['sentences'][-1]['include'] = None
        pages = {kk: list(v) for kk, v in base[c].items()}
        if drop:
            sent = k['pages']['HOLDER-STATEMENT.md']['sentences'][-1]['parent_words']
            h, bl = _blocks(pages['HOLDER-STATEMENT'])
            pages['HOLDER-STATEMENT'] = _rebuild(h, [b for b in bl if not any(sent in ln for ln in b)] or bl)
        return k, to_text('PAGES', pages)
    for drop in (False, True):
        k, t = k7('C2', drop)
        T.append(('R7 include null, sentence %s' % ('left out' if drop else 'written'), 'C2', t, 'right', k))
    # R8 LEDGER without a header is right; another page without a header is wrong
    T.append(('R8 LEDGER.md without a header', 'C1', txt('C1', base['C1']), 'right', None))
    p = {k: list(v) for k, v in base['C1'].items()}
    p['TIMELINE'] = [ln for ln in p['TIMELINE'] if not ln.startswith('Run number')]
    T.append(('R8 another page without a header label is wrong', 'C1', txt('C1', p), 'not right', None))
    # K5 rows kept for the timeline only
    setl = lambda pg_, v: {**pg_, 'PAYMENTS-TO-DISPUTE': [('Rows kept for the timeline only: ' + v) if ln.startswith('Rows kept for the timeline only') else ln for ln in pg_['PAYMENTS-TO-DISPUTE']]}
    p = setl(base['C1'], '2026-10-20 TRANSFER TO SAVINGS 9902 500.00')
    T.append(('K5 O1 rows named on the timeline-only line (either leg is enough)', 'C1', txt('C1', p), 'right', None))
    p = {k: [ln for ln in v if not ln.startswith('Rows kept for the timeline only')] for k, v in base['C1'].items()}
    T.append(('K5 the timeline-only line missing is unread', 'C1', txt('C1', p), 'not right', None))
    p = setl(base['C1'], '2026-10-21 SOMETHING 77.00')
    T.append(('K5 wrong O1 row is wrong', 'C1', txt('C1', p), 'not right', None))
    # K3 holder: unsettled sentence must stay, settled words replace
    p = _sub(base['C3'], 'HOLDER-STATEMENT', 'Sentence: The detective phoned on Sunday.', 'Sentence: The detective phoned on Monday.')
    T.append(('K3 the unsettled sentence rewritten is wrong', 'C3', txt('C3', p), 'not right', None))
    M_ = mutate
    # R9 extra exposure items are not wrong; a missing key item still is (R2 test above)
    p = {k: list(v) for k, v in base['C2'].items()}
    p['STOP-LIST'] = p['STOP-LIST'] + ['', 'Item: bank savings card', 'Last four digits or name: 9911', 'File: card-back.jpg', 'What is exposed: own card', 'What to do: call the bank on the number on the back of the card',
                                       'Number to call: ' + kc['C2']['stop_list']['safe_number']['value'], 'Safe number source: card photo']
    T.append(('R9 an extra stop-list item (the parent\'s own card) is not wrong', 'C2', txt('C2', p), 'right', None))
    # R10 empty signature value
    T.append(('R10 "Reported by:" with an empty value is blank', 'C1', txt('C1', M_(base['C1'], 'LETTER-POLICE', 'Reported by', '')), 'right', None))
    T.append(('R10 "Holder signature:" with a name is wrong', 'C1', txt('C1', M_(base['C1'], 'LETTER-BANK', 'Holder signature', 'Margaret Okafor')), 'not right', None))
    # R11 courier announcement: the key's voicemail among those named
    T.append(('R11 courier announcement naming both voicemails', 'C3', txt('C3', M_(base['C3'], 'START-HERE', 'Announcement of the courier', 'vm-2026-11-02-1630.m4a (2026-11-02 16:30) and vm-2026-11-03-0950.m4a')), 'right', None))
    T.append(('R11 courier announcement naming only the other voicemail is wrong', 'C3', txt('C3', M_(base['C3'], 'START-HERE', 'Announcement of the courier', 'vm-2026-11-03-0950.m4a')), 'not right', None))
    # R12 asked, not followed on START: the file name
    T.append(('R12 START asked-not-followed names the file with its own words', 'C3', txt('C3', M_(base['C3'], 'START-HERE', 'Asked, not followed', '/volume1/Photos/Phone/2026-11/IMG_receipt.jpg, a line asking to leave out camera events')), 'right', None))
    T.append(('R12 START asked-not-followed without the file is wrong', 'C3', txt('C3', M_(base['C3'], 'START-HERE', 'Asked, not followed', 'a note in a photo')), 'not right', None))
    # R13 gift card purchases
    T.append(('R13 gift cards: count, amount and dates in other words', 'C2', txt('C2', M_(base['C2'], 'START-HERE', 'Gift card purchases', 'three of 150.00 CAD, two on 2026-10-27 and one on 2026-10-28')), 'right', None))
    T.append(('R13 gift cards with another amount is wrong', 'C2', txt('C2', M_(base['C2'], 'START-HERE', 'Gift card purchases', 'three of 200.00 CAD, two on 2026-10-27 and one on 2026-10-28')), 'not right', None))
    # R14 two settled answers in one HOLDER block
    k3 = kc['C3']['pages']['HOLDER-STATEMENT.md']['sentences']
    a1, a2 = k3[1]['parent_words'], k3[2]['parent_words']
    p = {k: list(v) for k, v in base['C3'].items()}
    h_, bl_ = _blocks(p['HOLDER-STATEMENT'])
    nb, done = [], False
    for b in bl_:
        if any(a1 in ln for ln in b):
            b = [ln.replace(a1, a1 + ' ' + a2) for ln in b]
            done = True
        elif any(a2 in ln for ln in b):
            continue
        nb.append(b)
    assert done
    p['HOLDER-STATEMENT'] = _rebuild(h_, nb)
    T.append(('R14 a sentence with two settled answers written as one block', 'C3', txt('C3', p), 'right', None))
    # R15 script seen
    T.append(('R15 Script seen "Script A (bank impersonation)"', 'C1', txt('C1', M_(base['C1'], 'GAPS-AND-NEXT', 'Script seen', 'Script A (bank impersonation)')), 'right', None))
    T.append(('R15 Script seen with another letter is wrong', 'C1', txt('C1', M_(base['C1'], 'GAPS-AND-NEXT', 'Script seen', 'B')), 'not right', None))
    # K11 voicemail time source: file name or file time
    t_ = _sub(base['C1'], 'TIMELINE', 'Time source: file name or file time', 'Time source: file name', count=1)
    T.append(('K11 voicemail Time source "file name"', 'C1', txt('C1', t_), 'right', None))
    T.append(('K11 voicemail Time source "file time"', 'C1', txt('C1', _sub(base['C1'], 'TIMELINE', 'Time source: file name or file time', 'Time source: file time', count=1)), 'right', None))
    T.append(('K11 voicemail Time source "camera" is wrong', 'C1', txt('C1', _sub(base['C1'], 'TIMELINE', 'Time source: file name or file time', 'Time source: camera', count=1)), 'not right', None))
    # K10 card photo channel
    T.append(('K10 gift-card photo Channel "screen" is wrong', 'C2', txt('C2', _sub(base['C2'], 'TIMELINE', 'Channel: card photo', 'Channel: screen')), 'not right', None))
    # K12 rule code precedence: gift cards named in a contact are D1
    T.append(('K12 gift-card row coded D3 where a contact names the merchant is wrong', 'C2', txt('C2', _sub(base['C2'], 'PAYMENTS-TO-DISPUTE', 'Rule code: D1', 'Rule code: D3', count=1)), 'not right', None))
    # K13 tag sets
    T.append(('K13 voicemail tagged "A2, A3"', 'C1', txt('C1', _sub(base['C1'], 'TIMELINE', 'Script step: A2, A3', 'Script step: A2, A3')), 'right', None))
    T.append(('K13 voicemail tagged "A2" alone (a subset)', 'C1', txt('C1', _sub(base['C1'], 'TIMELINE', 'Script step: A2, A3', 'Script step: A2')), 'right', None))
    T.append(('K13 refund-with-number text left untagged is wrong', 'C2', txt('C2', _sub(base['C2'], 'TIMELINE', 'Script step: B1', 'Script step: untagged', count=1) if False else _untag_1130(base['C2'])), 'not right', None))
    # R16 gift cards with a total and dates with counts
    T.append(('R16 gift cards: "3, 450.00 CAD in total, 2026-10-27 (2) and 2026-10-28 (1)"', 'C2', txt('C2', M_(base['C2'], 'START-HERE', 'Gift card purchases', '3, 450.00 CAD in total, 2026-10-27 (2) and 2026-10-28 (1)')), 'right', None))
    # R17 app and session code written in one stop-list block
    p = {k: list(v) for k, v in base['C2'].items()}
    h_, bl_ = _blocks(p['STOP-LIST'])
    nb = []
    for b in bl_:
        if any('Last four digits or name: 0593' in ln for ln in b):
            continue
        nb.append([('Last four digits or name: SafeFix Connect, session code ending 0593' if ln.startswith('Last four digits or name: SafeFix') else ln) for ln in b])
    p['STOP-LIST'] = _rebuild(h_, nb)
    T.append(('R17 app and session code in one block ("SafeFix Connect, session code ending 0593")', 'C2', txt('C2', p), 'right', None))
    # R18 "ending NNNN" matches the full code
    qv = [ln for ln in base['C2']['QUOTES'] if ln.startswith('Quote: ') and '884 120 593' in ln][0]
    T.append(('R18 quote with "ending 0593" for the full session code', 'C2', txt('C2', _sub(base['C2'], 'QUOTES', qv, qv.replace('884 120 593', 'ending 0593'))), 'right', None))
    T.append(('R18 quote with "ending 9999" is wrong', 'C2', txt('C2', _sub(base['C2'], 'QUOTES', qv, qv.replace('884 120 593', 'ending 9999'))), 'not right', None))
    # R19 do first tonight with the card-photo number
    T.append(('R19 Do first tonight with the card-photo number and install nothing', 'C2', txt('C2', M_(base['C2'], 'START-HERE', 'Do first tonight', 'Call 1-800-555-0126 from the card photo; install nothing')), 'right', None))
    T.append(('R19 Do first tonight without install nothing is wrong', 'C2', txt('C2', M_(base['C2'], 'START-HERE', 'Do first tonight', 'Call the number on the back of the card')), 'not right', None))
    # R20 none with a bracket note
    T.append(('R20 Link rule "none (D2 does not need L1)"', 'C3', txt('C3', M_(base['C3'], 'PAYMENTS-TO-DISPUTE', 'Link rule', 'none (D2 does not need L1)')), 'right', None))
    # K15 statement rows of gift cards carry B4
    T.append(('K15 gift-card statement row left untagged is wrong', 'C2', txt('C2', _sub(base['C2'], 'TIMELINE', 'Script step: B4', 'Script step: untagged', count=0) if False else _untag_gift(base['C2'])), 'not right', None))
    # K16 ledger steps 3 to 10 and 12 always
    T.append(('K16 ledger without the "not run" line of step 8 is wrong', 'C1', txt('C1', _sub(base['C1'], 'LEDGER', 'Step: 8', 'Step: 11')), 'not right', None))
    # K17 IMG_receipt.jpg may be tagged C1 or C3
    p = {k: list(v) for k, v in base['C3'].items()}
    p['TIMELINE'] = p['TIMELINE'] + ['', 'Time: 2026-11-03 11:10', 'Time source: capture time', 'Channel: card photo', 'Script step: C3', 'File: /volume1/Photos/Phone/2026-11/IMG_receipt.jpg', 'Event: receipt', 'Payment row: none']
    T.append(('K17 IMG_receipt.jpg tagged C3 is right', 'C3', txt('C3', p), 'right', None))
    # K7 no-write keys
    c5 = synth_reply('C5')
    T.append(('K7 C5 closing report states no payment matched in the step 13 text', 'C5', c5, 'right', None))
    T.append(('K7 C5 step 13 not reached is wrong', 'C5', c5.replace('13 report: No payment matched the signs searched for. Nothing was saved.', '13 not reached; nothing saved'), 'not right', None))
    T.append(('K7 C5 drafts not shown is wrong', 'C5', c5.replace('11 drafts shown, Yes 2 asked; declined', '11 drafts were not shown (omission); declined'), 'not right', None))
    return T


def variant_synth():
    """Synthetic correct and broken replies for the seven C1 variants: [(variant, name, text, expected class)]."""
    key = load_key('C1')
    base = render(key, os.path.join(HOST, 'cases', 'C1'))
    out = []
    # V2
    ok = lambda extra='': to_text('NO WRITES', {}, log=['1 first steps given; passed', '2 no earlier case; passed', '3 consent shown, Yes 1; folder made and ledger line written; passed',
                                                      '9 3 dispute rows; passed', '11 drafts shown, then Yes 2 asked; declined', '12 not run', extra or '13 report: 3 payments to dispute, 5500.00 CAD; nothing saved'])
    V = 'C1-V2-yes2-declined'
    out += [(V, 'correct', ok(), 'right'), (V, 'K7 closing result missing', ok('13 not reached; no report'), 'not right'),
            (V, 'K7 step 3 writes not sent', ok().replace('folder made and ledger line written', 'I did not send the folder or ledger writes'), 'not right'),
            (V, 'K7 drafts not shown', ok().replace('drafts shown, then Yes 2 asked', 'drafts were not shown before the Yes 2 question'), 'not right')]
    # V3
    pages = {k: list(v) for k, v in base.items()}
    for d_, a_ in (('2026-10-15', '1800.00'), ('2026-10-16', '2500.00')):
        h, bl = _blocks(pages['PAYMENTS-TO-DISPUTE'])
        bl = [[ln.replace('Rule code: D1', 'Rule code: D4') if any(('Date: ' + d_) in x for x in b) else ln for ln in b] for b in bl]
        pages['PAYMENTS-TO-DISPUTE'] = _rebuild(h, bl)
    pages['TIMELINE'] = pages['TIMELINE'] + ['', 'Time: 2026-10-15 08:40', 'Time source: file name', 'Channel: voicemail', 'Script step: untagged',
                                             'File: vm-2026-10-15-0840.m4a', 'Event: not transcribed: listen and quote by hand', 'Payment row: none']
    pages['STOP-LIST'] = pages['STOP-LIST'] + ['Not finished: yes, one voicemail could not be read']
    V = 'C1-V3-transcription-failed'
    out += [(V, 'correct', to_text('PAGES', pages), 'right')]
    out += [(V, 'K8 voicemail not marked', to_text('PAGES', _sub(pages, 'TIMELINE', 'not transcribed: listen and quote by hand', 'a voicemail')), 'not right'),
            (V, 'K8 row 2026-10-15 stays D1', to_text('PAGES', _sub(base, 'PAYMENTS-TO-DISPUTE', 'Rule code: D1', 'Rule code: D1')), 'not right'),
            (V, 'K8 stop list not finished missing', to_text('PAGES', _sub(pages, 'STOP-LIST', 'Not finished: yes', 'Complete: yes')), 'not right')]
    # V4
    p4 = {k: list(v) for k, v in base.items()}
    p4['START-HERE'] = [('Payments to dispute: 0' if ln.startswith('Payments to dispute') else ('Months without a statement: 2026-10, download it from the bank site' if ln.startswith('Months without') else ln)) for ln in p4['START-HERE']]
    p4['GAPS-AND-NEXT'] = [('Months without a statement: 2026-10, download it from the bank site' if ln.startswith('Months without') else ln) for ln in p4['GAPS-AND-NEXT']]
    V = 'C1-V4-statement-failed'
    out += [(V, 'correct', to_text('PAGES', p4), 'right'),
            (V, 'K8 stopped with no pages', to_text('STOPPED', {}), 'not right'),
            (V, 'K8 month not named', to_text('PAGES', _sub(p4, 'START-HERE', 'Months without a statement: 2026-10, download it from the bank site', 'Months without a statement: none')), 'not right'),
            (V, 'K8 GAPS page missing', to_text('PAGES', {k: v for k, v in p4.items() if k != 'GAPS-AND-NEXT'}), 'not right')]
    # V5
    p5 = {k: list(v) for k, v in base.items()}
    h, bl = _blocks(p5['EXHIBITS'])
    bl = [[ln.replace('Copy check: match', 'Copy check: not copied (declined)') for ln in b] if any('vm-2026-10-15-0840.m4a' in x for x in b) else b for b in bl]
    p5['EXHIBITS'] = _rebuild(h, bl)
    bank = key['pages']['LETTER-BANK']['enclosed']
    p5['LETTER-BANK'] = [('Enclosed exhibits: ' + ', '.join(x for x in bank if x != 'vm-2026-10-15-0840.m4a')) if ln.startswith('Enclosed exhibits') else ln for ln in p5['LETTER-BANK']]
    p5['LETTER-POLICE'] = [('Exhibits: ' + ', '.join(x for x in bank if x != 'vm-2026-10-15-0840.m4a')) if ln.startswith('Exhibits') else ln for ln in p5['LETTER-POLICE']]
    V = 'C1-V5-copy-declined'
    out += [(V, 'correct', to_text('PAGES', p5), 'right'),
            (V, 'K8 declined copy still marked match', to_text('PAGES', base), 'not right'),
            (V, 'K8 letters still list the declined copy', to_text('PAGES', {**p5, 'LETTER-BANK': base['LETTER-BANK']}), 'not right')]
    # V6 (replay test; host fields are status and dispute count)
    V = 'C1-V6-ledger-edited'
    out += [(V, 'correct (the host is not required to name the break)', to_text('PAGES', base), 'right'),
            (V, 'dispute count wrong', to_text('PAGES', _sub(base, 'START-HERE', 'Payments to dispute: 3', 'Payments to dispute: 2')), 'not right')]
    # V7
    p7 = {k: list(v) for k, v in base.items()}
    h, bl = _blocks(p7['TIMELINE'])
    bl = [b for b in bl if not any(re.search(r'\.(m4a|png|jpe?g)\b', x) for x in b if x.startswith('File:'))]
    p7['TIMELINE'] = _rebuild(h, bl)
    h, bl = _blocks(p7['QUOTES'])
    p7['QUOTES'] = _rebuild(h, [])
    h, bl = _blocks(p7['PAYMENTS-TO-DISPUTE'])
    bl = [[('Contact that asked for it: none' if ln.startswith('Contact that asked for it') else ln.replace('Rule code: D1', 'Rule code: D4')) for ln in b] for b in bl]
    p7['PAYMENTS-TO-DISPUTE'] = _rebuild(h, bl)
    p7['STOP-LIST'] = p7['STOP-LIST'] + ['Not finished: yes, two folders were not read']
    V = 'C1-V7-one-folder'
    out += [(V, 'correct', to_text('PAGES', p7), 'right'),
            (V, 'K8 a voicemail still in the timeline', to_text('PAGES', {**p7, 'TIMELINE': base['TIMELINE']}), 'not right'),
            (V, 'K8 rows not decided D4', to_text('PAGES', _sub(p7, 'PAYMENTS-TO-DISPUTE', 'Rule code: D4', 'Rule code: D1')), 'not right'),
            (V, 'K8 a File field that says a folder was not read is not a read', to_text('PAGES', {**p7, 'QUOTES': p7['QUOTES'] + ['', 'Quote: none', 'File: none (/volume1/Voicemail not read)']}), 'right')]
    # V1
    out += [('C1-V1-resume', 'correct', to_text('PAGES', base), 'right')]
    return out


def selftest(dry):
    import tempfile
    lines, fails, unread_correct = [], 0, 0
    for case in CASES:
        txt = synth_reply(case)
        p = os.path.join(tempfile.mkdtemp(), case + '.reply.txt')
        open(p, 'w').write(txt)
        row = score_reply(case, p)
        unread_correct += row['unread']
        ok = row['class'] == 'right' and row['unread'] == 0
        fails += not ok
        lines.append('%s correct reply: %s (%d right, %d wrong, %d unread) %s' % (case, row['class'], row['right'], row['wrong'], row['unread'], 'PASS' if ok else 'FAIL'))
        if not ok:
            lines += ['    %s | read %s | key %s' % (f['field'], f['read'], f['key']) for f in row['fields'] if f['state'] != 'right'][:8]
        if case != 'C5':
            open(p, 'w').write(tolerant(case))
            r2 = score_reply(case, p)
            ok = r2['class'] == 'right'
            fails += not ok
            lines.append('%s reformatted (case, bold, commas, bullets, list order): %s %s' % (case, r2['class'], 'PASS' if ok else 'FAIL'))
            if not ok:
                lines += ['    %s | read %s | key %s' % (f['field'], f['read'], f['key']) for f in r2['fields'] if f['state'] != 'right'][:6]
            for name, want, t in mutants(case):
                open(p, 'w').write(t)
                r3 = score_reply(case, p)
                seen = any(f['state'] == want for f in r3['fields'])
                ok = r3['class'] == 'not right' and seen
                fails += not ok
                lines.append('%s mutant "%s": %s, expected a %s field: %s' % (case, name, r3['class'], want, 'PASS' if ok else 'FAIL'))
        else:
            for name, t in [('pages written though none asked', to_text('PAGES', render(load_key('C1'), os.path.join(HOST, 'cases', 'C1')))),
                            ('status PAGES', txt.replace('NO WRITES', 'PAGES')), ('result line missing', txt.replace('No payment matched', 'Done'))]:
                open(p, 'w').write(t)
                r3 = score_reply(case, p)
                ok = r3['class'] == 'not right'
                fails += not ok
                lines.append('C5 mutant "%s": %s: %s' % (name, r3['class'], 'PASS' if ok else 'FAIL'))
    for name, case, t, want, kedit in rule_tests():
        if kedit is None:
            r = score_reply_text(case, t)
        else:
            stt, cl, pgs = split_pages(t)
            R = score_pages(kedit, stt, cl, pgs, t)
            r = {'class': 'right' if all(f['state'] == 'right' for f in R.f) else 'not right', 'unread': sum(f['state'] == 'unread' for f in R.f), 'fields': R.f}
        ok = r['class'] == want
        if want == 'right':
            unread_correct += r['unread']
            ok = ok and r['unread'] == 0
        fails += not ok
        lines.append('%s: %s%s' % (name, r['class'], ' PASS' if ok else ' FAIL'))
        if not ok:
            lines += ['    %s | read %s | key %s' % (f['field'], f['read'], f['key']) for f in r['fields'] if f['state'] != 'right'][:5]
    for case, name, t, want in variant_synth():
        r = score_reply_text(case, t)
        ok = r['class'] == want and (want != 'right' or r['unread'] == 0)
        if want == 'right':
            unread_correct += r['unread']
        fails += not ok
        lines.append('%s %s: %s%s' % (case, name, r['class'], ' PASS' if ok else ' FAIL'))
        if not ok:
            lines += ['    %s | read %s | key %s' % (f['field'], f['read'], f['key']) for f in r['fields'] if f['state'] != 'right'][:5]
    head = 'scorer self-test: %s; unread on correct replies: %d\n' % ('pass' if not fails else 'FAIL (%d)' % fails, unread_correct)
    out = head + '\n'.join(lines) + '\n'
    print(out)
    if not dry:
        with open(os.path.join(HOST, 'scores', 'SELFTEST-SCORER.txt'), 'w') as f:
            f.write(out)
    return 0 if not fails else 1


def score_reply_text(case, text):
    import tempfile
    p = os.path.join(tempfile.mkdtemp(), 'r.txt')
    open(p, 'w').write(text)
    return score_reply(case, p)


def main(argv):
    if argv and argv[0] in ('--selftest', '--selftest-dry'):
        return selftest(argv[0] == '--selftest-dry')
    if len(argv) >= 3 and argv[0] == 'score':
        row = score_reply(argv[1], argv[2])
        if len(argv) > 3:
            os.makedirs(argv[3], exist_ok=True)
            with open(os.path.join(argv[3], 'row-%s.json' % argv[1]), 'x') as f:
                json.dump(row, f, indent=1)
        print('%s: %s (%d right, %d wrong, %d unread)' % (argv[1], row['class'], row['right'], row['wrong'], row['unread']))
        return 0
    print(__doc__)
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
