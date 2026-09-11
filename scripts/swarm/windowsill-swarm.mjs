export const meta = {
  name: 'windowsill-swarm',
  description: 'Exhaustive haiku sweep over windowsill-lab: the public page, the explainer rooms, 34k lines of instrument code, and the A05 representation gap',
  phases: [
    { title: 'Recon', detail: 'map the page, the rooms, the code, the ledger' },
    { title: 'Hunt', detail: 'file x lens finders across everything', model: 'haiku' },
    { title: 'Verify', detail: '2 adversarial refuters per finding', model: 'haiku' },
    { title: 'Repair', detail: 'one writer per file, disjoint', model: 'haiku' },
    { title: 'A05', detail: 'the representation gap Ben actually asked about' },
    { title: 'Gate', detail: 'measure, including that the public page still stands' },
  ],
}

const L = '/home/benslinuxbox/projects/windowsill-lab'

const RAILS = [
  'REPO: ' + L + '  (windowsill-lab — a real scientific instrument with a LIVE PUBLIC WEBSITE.',
  'Python, ~34,400 lines across 72 files, 69 test files. Two machines run a physics/astronomy',
  'curriculum on a schedule; results are published free for anyone to check.)',
  '',
  '=== THE THREE RAILS THAT MATTER MOST HERE ===',
  '',
  '1. NEVER FABRICATE A MEASUREMENT. This instrument publishes scientific results to the public',
  '   under an explicit promise that nulls are kept and nothing is overclaimed. Inventing a number,',
  '   a target count, a candidate, a lead, a p-value, or a "result_plain" string that is not DERIVED',
  '   FROM A COMMITTED RECEIPT is the single worst thing you could do in this repo — worse than any',
  '   bug you might fix. If a value is not in the receipts, it is UNKNOWN and you say so.',
  '',
  '2. web/index.html IS THE LIVE PUBLIC PAGE, byte-identical to what https://www.brokenbranch.dev/',
  '   windowsill/ serves right now (296,522 bytes, verified). A broken edit there breaks a public',
  '   site. It is also the CANONICAL source — the copy in ~/projects/brokenbranchdevwebsite/',
  '   windowsill/ is a stale mirror, 111 KB behind; never treat that mirror as the source of truth.',
  '',
  '3. THIS IS A SHARED CLONE. A Windows sibling session ("win") works the same repo and pushes to',
  '   the same main. NEVER force-push, never rewrite history, never resolve a conflict by discarding',
  '   the other side. Do not push at all — commits stay local for Ben to review.',
  '',
  '=== HARD RAILS ===',
  '- NEVER run git commit/push/checkout/reset/stash/clean/restore/rebase. (A conflicted `git stash',
  '  pop` is what left pot.json unparseable on this box today — do not add another.)',
  '- NEVER run the campaign, a hunt, or anything that dispatches a slot or writes a receipt:',
  '  no `lab hunt`, no a05/a01 run scripts, no scheduler. The real hunt timer fires at 15:02 today',
  '  and must not be raced.',
  '- DO NOT MODIFY, and treat as read-only evidence: pot.json · reports/hunts/**  · reports/*.html ·',
  '  reports/receipts/** · release/** · web/*.test.mjs snapshots of published output.',
  '  These are committed receipts. They are the instrument\'s memory.',
  '- NEVER touch anything outside ' + L + '. In particular never ~/.openclaw/workspace/ember-home,',
  '  never /home/pzserver, never the brokenbranchdevwebsite mirror.',
  '- NEVER publish, deploy, post, or upload anything anywhere. NO network mutations.',
  '- No sudo. No package installs. Match the project\'s existing dependency posture; add none.',
  '',
  '=== HOW TO RUN THE TESTS (get this right or your verification is meaningless) ===',
  'A bare `python3 -m pytest tests/` FAILS with 62 collection errors — "No module named lab" — because',
  'the package is not installed into the ambient interpreter. That is NOT a bug you have found; it is',
  'the wrong invocation. Use:',
  '      cd ' + L + ' && PYTHONPATH=src python3 -m pytest tests/ -q',
  'Six modules additionally need `torch` (a real optional GPU dependency) and will error without it —',
  'also expected, also not your finding.',
  'THE SUITE IS SLOW (minutes — it runs real physics). Do NOT run the whole suite repeatedly. Run the',
  'targeted subset for what you touched, e.g. PYTHONPATH=src python3 -m pytest tests/test_stories.py -q',
  'The final gate agent runs the full suite once.',
  '',
  '=== GROUND TRUTH measured 2026-08-17, trust over any doc ===',
  '- The A05 exoplanet hunt is live and is the only track producing human-review items:',
  '  3,730 targets searched · 51 above threshold · 3 leads awaiting Ben',
  '  (TIC 234518605 + TIC 272357134 from win\'s sector 2; TIC 49558810 from this box\'s sector 3,',
  '   found 2026-08-16 and previously unreported).',
  '- Explainer rooms exist for a01, a03, a04, k01 and 47 m-track runs. A05 HAS NO ROOM — the one',
  '  track with leads in the air is the one a visitor cannot walk into.',
  '- src/lab/stories.py has a rich, well-written "A05" entry (short_label "Pricing false alarms")',
  '  but its `result_plain` is None.',
  '- CONFIRMED COPY BUG ON THE LIVE PAGE, in the shelf hero: it renders',
  '     "A run reproduced its target, an run returned a null, a run refused its own measurement"',
  '  — the counts are MISSING and "an run" is ungrammatical. Template interpolation is failing in',
  '  production. Find the cause; it is a real defect a visitor sees today.',
  '- The site mirror commits ("chore(mirror): pull lab pages from windowsill-lab@...") lag the',
  '  canonical page, and `git fetch` on the mirror repo fails with a GitHub auth error.',
  '',
  '=== WHY THIS ROUND EXISTS, in Ben\'s words ===',
  '"100 haiku agents would likely find a ton of bugs and opportunities we\'ve never seen because',
  'we\'ve not been exhaustive." He is right: six real findings surfaced in ten minutes of manual',
  'poking, including the production copy bug above. Be exhaustive where a human skimmed.',
].join('\n')

const FINDINGS = {
  type: 'object',
  properties: {
    findings: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          file: { type: 'string' },
          line: { type: 'integer' },
          severity: { type: 'string', enum: ['high', 'medium', 'low'] },
          kind: { type: 'string', enum: ['bug', 'honesty', 'copy', 'a11y', 'perf', 'deadcode', 'opportunity'] },
          title: { type: 'string' },
          detail: { type: 'string' },
          failure_scenario: { type: 'string', description: 'concrete inputs/state -> the wrong outcome a real person would see' },
          fix_sketch: { type: 'string' },
        },
        required: ['file', 'line', 'severity', 'kind', 'title', 'detail', 'failure_scenario', 'fix_sketch'],
      },
    },
  },
  required: ['findings'],
}

const VERDICT = {
  type: 'object',
  properties: { refuted: { type: 'boolean' }, reason: { type: 'string' } },
  required: ['refuted', 'reason'],
}

const WORK = {
  type: 'object',
  properties: {
    done: { type: 'boolean' }, summary: { type: 'string' },
    files_touched: { type: 'array', items: { type: 'string' } },
    receipts: { type: 'array', items: { type: 'string' } },
    blocked: { type: 'string' },
    followups: { type: 'array', items: { type: 'string' } },
  },
  required: ['done', 'summary', 'files_touched', 'receipts', 'blocked', 'followups'],
}

// ------------------------------- RECON -------------------------------
phase('Recon')

const RECON = [
  ['page', 'web/index.html (296KB, THE LIVE PUBLIC PAGE) plus web/pots.js, web/growth-forms.js and their .test.mjs files. Map: how the page is structured, where its copy lives, how it fetches the feed (pot.json / snapshot.json off GitHub raw), how the shelf hero is built and WHY its counts render empty, how the plant/pots are drawn, what runs client-side.'],
  ['rooms', 'reports/*.html — 53 explainer rooms. Map: what a room contains, what distinguishes a rich room (a01 is 86KB) from a thin one (a04 is 43KB), which tracks have rooms (a01/a03/a04/k01 + 47 m-track), and what a room for A05 would need. Also: who generates them — src/lab/render.py, publish.py, receipt.py, archive.py.'],
  ['instrument', 'src/lab/ — the physics/astronomy core. Map the module map, which modules are load-bearing, where the honesty gates live (the deterministic checker, the amber/green promotion boundary, claim_boundary), and the 6-10 places a careful reviewer looks first.'],
  ['a05', 'The A05 lane specifically: src/lab/a05*.py (a05_hunt, a05_stats, a05_sensitivity), scripts/a05_hunt.py, src/lab/curriculum.py hunt_lane(), src/lab/publish.py hunt_block(). Map exactly how a hunt runs, how a receipt is written, how leads are graded, and how pot["hunt"] is derived. Read reports/hunts/*.json as evidence, never modify them.'],
  ['ledger', 'Data integrity: pot.json (read-only), reports/hunts/**, reports/receipts/**. Map the schemas, and check whether the derived aggregates in pot.json actually reconcile with the receipts they claim to summarise. Report discrepancies as findings; do NOT edit any of these files.'],
  ['copy', 'src/lab/stories.py (the plain-language question/why/result copy for every milestone) plus every user-visible string in web/index.html and src/lab/render.py. Map: which milestones have result_plain filled vs None, and whether any published copy makes a claim the receipts do not support.'],
]

const recon = (await parallel(RECON.map(function (r) {
  return function () {
    return agent(RAILS + '\n\nREAD-ONLY recon. Edit nothing. Run no project code that writes.\n\n' + [
      'MAP THIS AREA: ' + r[1],
      '',
      'Produce a dense factual map for the finders who come after you. Cite file:line throughout.',
      'Name the specific places a real defect is most likely. Max 800 words. Your output is data for',
      'other agents, not prose for a human.',
    ].join('\n'), { label: 'recon:' + r[0], phase: 'Recon', model: 'sonnet' })
  }
}))).filter(Boolean)

const MAP = recon.join('\n\n=====\n\n').slice(0, 55000)
log('recon banked ' + recon.length + '/' + RECON.length)

// ------------------------------- HUNT -------------------------------
phase('Hunt')

const LENSES = {
  crash: 'CRASH & CORRECTNESS — unhandled exceptions on realistic input, None/KeyError/IndexError, off-by-one, inverted condition, wrong default, a function whose contract and callers disagree, float comparison where exactness matters.',
  honesty: 'SCIENTIFIC HONESTY — this is the lens that matters most in this repo. A number presented as measured that is actually assumed, interpolated, defaulted or carried over. An unmeasurable value rendered as 0 instead of unknown. A gate that can pass without the evidence it claims to check. An aggregate that double-counts or silently drops rows. A claim in published copy the receipts do not support. A null quietly not kept.',
  copy: 'PUBLIC COPY — text a visitor reads: broken template interpolation (the shelf hero is a KNOWN case), missing or wrong numbers, grammar that reveals a failed substitution, stale claims, an internal term leaking into lay copy, a promise the page does not keep, inconsistent naming of the same thing.',
  data: 'DATA & SCHEMA — receipt/pot schema drift, a writer and reader disagreeing on a field, a field read that is never written, aggregation that assumes uniqueness it does not have, timezone/UTC handling, sort order that changes results.',
  a11y: 'ACCESSIBILITY & FRONT-END ROBUSTNESS — missing alt text, unlabelled controls, colour used as the only signal, keyboard traps, focus never visible, a fetch with no failure path so the page shows an empty dash forever, layout that breaks narrow, motion with no prefers-reduced-motion.',
  dead: 'DEAD & DRIFTED — code no caller reaches, a config key nothing reads, a documented flag that does not exist, a test asserting removed behaviour, a TODO that was silently completed or silently abandoned, duplicated logic that has since diverged.',
}

const PY = [
  'src/lab/a05_hunt.py', 'src/lab/a05_stats.py', 'src/lab/a05_sensitivity.py', 'src/lab/a01.py',
  'src/lab/publish.py', 'src/lab/render.py', 'src/lab/receipt.py', 'src/lab/curriculum.py',
  'src/lab/stories.py', 'src/lab/archive.py', 'src/lab/setup.py',
]

const TARGETS = []
// the public page and its JS get every lens — it is the surface a stranger touches
for (const l of ['copy', 'a11y', 'crash', 'honesty', 'dead']) TARGETS.push(['web/index.html', l])
for (const l of ['crash', 'a11y', 'dead']) TARGETS.push(['web/pots.js + web/growth-forms.js', l])
// the A05 lane gets the honesty and data lenses twice over
for (const f of ['src/lab/a05_hunt.py', 'src/lab/a05_stats.py', 'src/lab/a05_sensitivity.py'])
  for (const l of ['honesty', 'crash', 'data']) TARGETS.push([f, l])
// the rest of the named modules
for (const f of PY.slice(3)) for (const l of ['crash', 'honesty', 'data', 'dead']) TARGETS.push([f, l])
// the wider tree, swept in slices so nothing is unread
TARGETS.push(['src/lab/ — every module NOT named in another target, slice A (alphabetical first third)', 'crash'])
TARGETS.push(['src/lab/ — every module NOT named in another target, slice B (middle third)', 'crash'])
TARGETS.push(['src/lab/ — every module NOT named in another target, slice C (final third)', 'crash'])
TARGETS.push(['src/lab/ — the same three slices again', 'honesty'])
TARGETS.push(['scripts/ — every script', 'crash'])
TARGETS.push(['scripts/ — every script', 'honesty'])
TARGETS.push(['tests/ — do the tests actually assert what they claim? find tests that cannot fail, tests asserting removed behaviour, and behaviour with no test at all', 'dead'])
TARGETS.push(['reports/*.html — the 53 explainer rooms: broken rooms, missing assets, dead links, rooms whose copy contradicts their own receipt', 'copy'])
TARGETS.push(['reports/*.html — the rooms, read-only', 'a11y'])
TARGETS.push(['src/lab/stories.py — every milestone entry', 'copy'])
TARGETS.push(['src/lab/stories.py + src/lab/publish.py — does published copy ever outrun its receipts?', 'honesty'])

log('hunting ' + TARGETS.length + ' file-by-lens pairs')

const hunted = (await parallel(TARGETS.map(function (t, i) {
  return function () {
    return agent(RAILS + '\n\nSUBSYSTEM MAP from recon (verify against the real files):\n' + MAP + '\n\n' + [
      'You are finder #' + (i + 1) + '. READ-ONLY: read and grep only. Never edit. Never execute code',
      'that writes a file.',
      '',
      'TARGET: ' + t[0],
      'LENS:   ' + LENSES[t[1]],
      '',
      'Hunt ONLY through your lens — others cover the rest, so do not dilute.',
      '',
      'What counts as a finding:',
      '- a REAL defect on a reachable path, or a concrete opportunity a maintainer would act on',
      '- you can state the inputs/state and the wrong outcome A REAL PERSON WOULD SEE',
      '- cite exact file and line',
      '- if a guard, caller, or default already handles it, it is NOT a finding — check first',
      '- zero findings is a fine answer. Do not invent volume. In this repo especially, a fabricated',
      '  finding about a scientific result is worse than a missed one.',
      '',
      'Return at most 5 findings, most severe first.',
    ].join('\n'), {
      label: 'hunt:' + String(t[0]).replace(/^.*\//, '').slice(0, 22) + ':' + t[1],
      phase: 'Hunt', model: 'haiku', schema: FINDINGS,
    })
  }
}))).filter(Boolean)

let raw = hunted.flatMap(function (h) { return h.findings || [] })
const seen = new Set(); const ded = []
for (const f of raw) {
  const k = f.file + '::' + f.line + '::' + String(f.title || '').toLowerCase().slice(0, 40)
  if (seen.has(k)) continue
  seen.add(k); ded.push(f)
}
const rank = { high: 0, medium: 1, low: 2 }
ded.sort(function (a, b) { return (rank[a.severity] ?? 3) - (rank[b.severity] ?? 3) })
const CAP = 60
const toVerify = ded.slice(0, CAP)
log(raw.length + ' candidates, ' + ded.length + ' deduped, verifying ' + toVerify.length +
    (ded.length > CAP ? ' (' + (ded.length - CAP) + ' lower-severity NOT assessed — record as not-assessed, never as clean)' : ''))

// ------------------------------- VERIFY -------------------------------
phase('Verify')

const judged = (await parallel(toVerify.map(function (f, i) {
  return function () {
    return parallel([
      function () {
        return agent(RAILS + '\n\n' + [
          'You are a SKEPTIC. REFUTE this claim by reading the code. Read-only.',
          '', 'CLAIM: ' + f.title, 'FILE: ' + f.file + ':' + f.line, 'KIND: ' + f.kind,
          'DETAIL: ' + f.detail, 'CLAIMED FAILURE: ' + f.failure_scenario, '',
          'Refute if: the input cannot reach there · a guard/caller/default already handles it ·',
          'the reader misread control flow or data shape · it is intended given the surrounding',
          'contract · the line does not correspond to the described code · it is already fixed.',
          '',
          'For a COPY or HONESTY claim, additionally check it against the actual published artefact',
          'and the actual receipts — several findings in this repo will be about text, and text is',
          'easy to misquote.',
          '',
          'Default to refuted=true when uncertain. Cite the lines that decided it.',
        ].join('\n'), { label: 'ref-a:' + i, phase: 'Verify', model: 'haiku', schema: VERDICT })
      },
      function () {
        return agent(RAILS + '\n\n' + [
          'You are a REPRODUCTION checker. Read-only; run nothing that writes.',
          '', 'CLAIM: ' + f.title, 'FILE: ' + f.file + ':' + f.line,
          'CLAIMED FAILURE: ' + f.failure_scenario, '',
          'Trace the exact path from a real entry point — a scheduled slot, a CLI script, a page load,',
          'a fetch of the published feed — to this line, naming each hop with file:line.',
          'For a claim about the PUBLIC PAGE, the entry point is "a visitor loads',
          'https://www.brokenbranch.dev/windowsill/", and you may read the page source as evidence.',
          '',
          'refuted=true if you cannot name that concrete path, or the trigger never occurs in this',
          'deployment. refuted=false only if you can state it hop by hop.',
        ].join('\n'), { label: 'ref-b:' + i, phase: 'Verify', model: 'haiku', schema: VERDICT })
      },
    ]).then(function (vs) {
      const ok = vs.filter(Boolean)
      return Object.assign({}, f, {
        survives: ok.length > 0 && ok.every(function (v) { return !v.refuted }),
        verdicts: ok.map(function (v) { return (v.refuted ? 'REFUTED: ' : 'STANDS: ') + v.reason }),
      })
    })
  }
}))).filter(Boolean)

const confirmed = judged.filter(function (j) { return j.survives })
const killed = judged.filter(function (j) { return !j.survives })
log('verified: ' + confirmed.length + ' CONFIRMED, ' + killed.length + ' refuted')

// ------------------------------- REPAIR -------------------------------
phase('Repair')

const byFile = {}
for (const f of confirmed) { (byFile[f.file] = byFile[f.file] || []).push(f) }
const groups = Object.keys(byFile).map(function (k) { return [k, byFile[k]] })
log('repair: ' + confirmed.length + ' across ' + groups.length + ' files, one writer each')

const repairs = groups.length === 0 ? [] : (await parallel(groups.map(function (g) {
  const file = g[0], fs = g[1]
  return function () {
    const list = fs.map(function (f, i) {
      return '[' + (i + 1) + '] ' + String(f.severity).toUpperCase() + ' ' + f.kind + ' — ' + f.title +
        '\n    line ' + f.line + ' (may have shifted — find it by behaviour)' +
        '\n    defect: ' + f.detail + '\n    failure: ' + f.failure_scenario +
        '\n    suggested: ' + f.fix_sketch
    }).join('\n\n')
    const isPublic = /web\/index\.html/.test(file)
    return agent(RAILS + '\n\n' + [
      'You are the SOLE writer for exactly one file: ' + file,
      'Other agents edit other files concurrently. Editing outside ' + file + ' corrupts their work.',
      isPublic ? '\n*** THIS IS THE LIVE PUBLIC PAGE. Every edit is surgical. After each change, re-verify\n' +
                 'the document still parses and the byte count moves only as much as your edit explains.\n' +
                 'Do NOT restyle, do NOT refactor, do NOT reflow. Fix the defect and nothing else. ***\n' : '',
      'Fix these ' + fs.length + ' finding(s), each already survived two adversarial reviewers:',
      '', list, '',
      'Method:',
      '1. Read the file and its surroundings first. If on reading a finding is wrong, SKIP it and say why.',
      '2. Minimal surgical change, matching existing style exactly.',
      '3. NEVER invent a measurement to make something look complete. If a value should come from a',
      '   receipt and the receipt does not have it, render it as unknown and say so in notes.',
      '4. Prove it parses: ast.parse for Python; for HTML/JS use python3 html.parser for tag balance',
      '   and `node --check` on extracted script where practical.',
      '5. Run the test suite for what you touched (PYTHONPATH=src python3 -m pytest tests/<targeted>.py -q, or the relevant',
      '   node --test for web/*.test.mjs) and report before/after counts. Do not leave it worse.',
    ].join('\n'), { label: 'fix:' + file.replace(/^.*\//, '').slice(0, 24), phase: 'Repair', model: 'haiku', schema: WORK })
  }
}))).filter(Boolean)

// ------------------------------- A05 -------------------------------
phase('A05')

const a05 = (await parallel([
  function () {
    return agent(RAILS + '\n\n' + [
      'You own ONE file: src/lab/stories.py — and within it, ONLY the "A05" entry.',
      '',
      'A05 is the exoplanet hunt. Its story entry is already well written (short_label "Pricing false',
      'alarms") but `result_plain` is None, while the hunt has in fact produced measured output.',
      '',
      'Fill result_plain — DERIVED FROM THE COMMITTED RECEIPTS ONLY. Read reports/hunts/*.json and',
      'pot.json (read-only) and use lab.publish.hunt_block() to see the authoritative aggregate.',
      'As of today that is 3,730 targets searched · 51 above threshold · 3 leads awaiting human review.',
      'VERIFY those numbers yourself rather than trusting this brief.',
      '',
      'THE COPY BAR, and it is the whole task:',
      '- Plain language for a non-expert. Match the voice of the neighbouring entries exactly.',
      '- It must NOT claim a discovery, a planet, or a detection. The strongest honest verdict this',
      '  instrument produces is "a lead awaiting human review". The existing why_it_matters says so;',
      '  do not contradict it.',
      '- It must state that a human has not yet reviewed the leads. That is the true current state and',
      '  it is more interesting than a fudge.',
      '- Numbers must be the receipts\' numbers. If you cannot verify one, leave it out entirely.',
      '',
      'Write nothing else in the file. Verify with ast.parse and by importing stories and printing the',
      'A05 entry. Put the exact final string in receipts so it can be read.',
    ].join('\n'), { label: 'a05:story-copy', phase: 'A05', model: 'sonnet', schema: WORK })
  },
  function () {
    return agent(RAILS + '\n\n' + [
      'READ-ONLY design study — write NO code and edit NO file. Your deliverable is a report.',
      '',
      'A05 is the only track with leads in the air and the ONLY track with no explainer room:',
      'rooms exist for a01, a03, a04, k01 and 47 m-track runs. A visitor cannot walk into the one',
      'experiment that is genuinely mid-flight.',
      '',
      'Establish, from the code, EXACTLY what it would take to generate an A05 room:',
      '1. Read src/lab/render.py, publish.py, receipt.py, archive.py and work out precisely how a',
      '   room is produced today — what input it needs, what shape, which function is the entry point.',
      '2. Compare a rich room (reports/2026-08-14-a01.html, 86KB) with a thin one',
      '   (reports/2026-08-08-a04.html, 43KB). What does the rich one carry that the thin one lacks?',
      '3. Determine whether the existing A05 hunt receipts already contain what a room needs, or',
      '   whether the receipt schema would have to grow — and if so, exactly which fields.',
      '4. Say what the room would honestly SHOW. A physics room can animate a lattice. An A05 room',
      '   has light curves, a periodogram, a per-target false-alarm probability, and three graded',
      '   leads. Which of those are in the receipts today?',
      '',
      'Deliver: the entry point + call signature, the missing pieces named precisely, an honest',
      'estimate of the work, and the single smallest first step that would produce a real (not',
      'placeholder) A05 room. If the honest answer is "the receipts do not carry enough yet", say',
      'that plainly — it is the most useful possible finding.',
    ].join('\n'), { label: 'a05:room-study', phase: 'A05', model: 'sonnet' })
  },
])).filter(Boolean)

// ------------------------------- GATE -------------------------------
phase('Gate')

const gate = await agent(RAILS + '\n\n' + [
  'FINAL GATE. Measure honestly. Fix nothing. Commit nothing.',
  '',
  '1. cd ' + L + ' && PYTHONPATH=src python3 -m pytest tests/ -q 2>&1 | tail -6   (slow; run ONCE.\n     A bare invocation without PYTHONPATH=src gives 62 bogus collection errors — do not report those.)',
  '2. node --test web/ 2>&1 | tail -8   (or the project\'s own web test command — find it)',
  '3. git -C ' + L + ' status -s   and   git -C ' + L + ' diff --stat',
  '4. ast.parse every changed .py; html.parser tag-balance every changed .html; node --check any',
  '   changed .js',
  '',
  '5. THE PUBLIC PAGE IS THE THING THAT MUST NOT BREAK. Verify explicitly:',
  '   - web/index.html still parses with zero unclosed tags',
  '   - its byte count, and whether the delta is explained by the edits made',
  '   - the shelf-hero counts: do they now render numbers instead of "an run"? Quote the text.',
  '   - fetch https://www.brokenbranch.dev/windowsill/ and confirm PRODUCTION is still the OLD file',
  '     (nothing here deploys; if production changed, something pushed and that is an incident)',
  '',
  '6. CONFIRM NO RECEIPT WAS TOUCHED. `git status` must show NO changes under pot.json,',
  '   reports/hunts/, reports/receipts/, reports/*.html or release/. If any appears, name it FIRST —',
  '   that is the one unacceptable outcome of this round.',
  '',
  '7. Report the A05 result_plain string verbatim, and state whether every number in it is traceable',
  '   to a committed receipt.',
  '',
  'Report measured truth without flattering it. If something is worse, say so first.',
].join('\n'), { label: 'gate', phase: 'Gate', model: 'sonnet', schema: WORK })

return {
  hunted: TARGETS.length, candidates: raw.length, deduped: ded.length,
  verified: toVerify.length, confirmed: confirmed.length, refuted: killed.length,
  notAssessed: Math.max(0, ded.length - CAP),
  confirmedList: confirmed.map(function (c) { return { file: c.file, line: c.line, sev: c.severity, kind: c.kind, title: c.title } }),
  refutedList: killed.map(function (c) { return { file: c.file, title: c.title, why: c.verdicts } }),
  repairs: repairs, a05: a05, gate: gate,
}
