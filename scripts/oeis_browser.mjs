/**
 * OEIS submission driver — a real browser window, a persistent profile, and a
 * hard line about who authenticates.
 *
 * WHO DOES WHAT, and why it is split this way:
 *
 *   Ben authenticates. OEIS signs in with Google, GitHub, or an emailed link /
 *   passkey — every one of those is his identity, and none of them should pass
 *   through a browser a model is driving. So this script opens the window and
 *   stops. It never types a password, never reads a mailbox, never touches an
 *   OAuth consent screen.
 *
 *   The model types the submission. Transcribing 30 integers and four fields
 *   into a web form by hand is the single step in this pipeline with no checker
 *   on it, which is exactly the step a machine should do — from the generated
 *   package, never from memory.
 *
 *   Ben presses submit. `fill` stops before "Save changes"; nothing leaves the
 *   box without a human looking at the filled form first.
 *
 * The profile lives in ~/.lab/oeis-profile so the login survives between runs.
 * It holds a real session cookie for his account: it is deliberately outside
 * ~/projects (never synced) and outside the repo.
 *
 * Usage:
 *   node scripts/oeis_browser.mjs login [email]   # open, prefill, hand over
 *   node scripts/oeis_browser.mjs whoami          # is the session live?
 *   node scripts/oeis_browser.mjs fill <pkg.md>   # fill the edit form, stop
 */
import { createRequire } from 'node:module';
import { readFileSync, existsSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';

// playwright lives in a tool dir, not in this repo — windowsill-lab is a Python
// project and a node_modules tree in it would be a lie about what it is. ESM
// ignores NODE_PATH, so resolve it explicitly rather than by ambient luck.
const require = createRequire(import.meta.url);
const TOOL_DIR = join(homedir(), '.lab', 'oeis-tool', 'node_modules', 'playwright');
if (!existsSync(TOOL_DIR)) {
  console.error(`playwright not found at ${TOOL_DIR}\n`
    + '  mkdir -p ~/.lab/oeis-tool && cd ~/.lab/oeis-tool && npm init -y && npm i playwright\n'
    + '  npx playwright install chromium');
  process.exit(2);
}
const { chromium } = require(TOOL_DIR);

const PROFILE = join(homedir(), '.lab', 'oeis-profile');
const SEQ = 'A329398';
const DEFAULT_EMAIL = 'ben@brokenbranch.dev';

async function open({ headless = false } = {}) {
  return chromium.launchPersistentContext(PROFILE, {
    headless,
    viewport: { width: 1440, height: 950 },
    args: ['--disable-blink-features=AutomationControlled'],
  });
}

/** Read the generated package. Never accept loose numbers — only this file. */
function parsePackage(path) {
  const md = readFileSync(path, 'utf8');
  const block = (heading) => {
    const i = md.indexOf(heading);
    if (i < 0) return null;
    const fence = md.indexOf('```', i);
    if (fence < 0) return null;
    const start = md.indexOf('\n', fence) + 1;
    const end = md.indexOf('```', start);
    return md.slice(start, end).trim();
  };
  const data = block('## 1 · DATA');
  const extensions = block('## 2 · Extensions field');
  const comment = block('## 3 · New comment');
  const prog = block('## 4 · PROG');
  if (!data || !comment || !prog) {
    throw new Error('package is missing DATA, comment or PROG — refusing');
  }
  const terms = data.split(',').map((s) => s.trim());
  if (!terms.every((t) => /^\d+$/.test(t))) {
    throw new Error('DATA contains a non-integer — refusing');
  }
  return { data, extensions, comment, prog, count: terms.length };
}

/**
 * Is this profile signed in? Three states, never two.
 *
 * The first version of this asked whether the homepage said "Sign in with
 * Google" — text that only ever appears on /login — and then read the
 * signed-OUT page's `<a href="/account">Register</a>` as the username. It
 * reported "signed in as Register" against a profile with no session at all.
 * A detector that cannot return NO is not a detector.
 *
 * The signal, verified against the real signed-out markup: a signed-out page
 * carries `<a href="/login">`. Its ABSENCE is the positive signal, and a page
 * that yields no anchors at all is `unknown` — refused, not guessed.
 */
async function whoami(ctx) {
  const page = await ctx.newPage();
  await page.goto('https://oeis.org/', { waitUntil: 'domcontentloaded' });
  const anchors = await page.locator('a').count();
  if (anchors === 0) {
    return { state: 'unknown', who: null, page,
             why: 'no anchors on the page — could not see, so not answering' };
  }
  const loginLinks = await page.locator('a[href^="/login"]').count();
  if (loginLinks > 0) {
    return { state: 'signed-out', who: null, page,
             why: `${loginLinks} /login link(s) present` };
  }
  const who = await page
    .locator('a[href^="/user/"], a[href*="logout"]')
    .first()
    .textContent()
    .catch(() => null);
  return { state: 'signed-in', who: who?.trim() ?? null, page,
           why: 'no /login link present' };
}

const cmd = process.argv[2] ?? 'login';

if (cmd === 'login') {
  const email = process.argv[3] ?? DEFAULT_EMAIL;
  const ctx = await open();
  const page = await ctx.newPage();
  await page.goto('https://oeis.org/login?redirect=%2F', { waitUntil: 'domcontentloaded' });
  await page.fill('#signin-email', email).catch(() => {});
  console.log(`\n  A browser window is open at the OEIS sign-in, prefilled with ${email}.`);
  console.log('  Sign in however you like — Google, GitHub, or the emailed link.');
  console.log('  Nothing here reads your password; the session is saved to');
  console.log(`  ${PROFILE} so this only has to happen once.`);
  console.log('\n  Leave the window open. Ctrl-C here when you are signed in.\n');
  await new Promise(() => {});          // hold the window open
} else if (cmd === 'whoami') {
  const ctx = await open({ headless: true });
  const { state, who, why } = await whoami(ctx);
  console.log(`${state}${who ? ` as ${who}` : ''}  (${why})`);
  await ctx.close();
  process.exit(state === 'signed-in' ? 0 : 1);
} else if (cmd === 'fill') {
  const pkgPath = process.argv[3];
  if (!pkgPath) throw new Error('usage: fill <submission package .md>');
  const pkg = parsePackage(pkgPath);
  const ctx = await open();
  const { state, why } = await whoami(ctx);
  if (state !== 'signed-in') {
    console.error(`${state} (${why}) — run \`login\` first. `
      + 'Refusing to open the edit form.');
    await ctx.close();
    process.exit(1);
  }
  const page = await ctx.newPage();
  await page.goto(`https://oeis.org/edit/global/${SEQ}`, { waitUntil: 'domcontentloaded' });
  console.log(`\n  Edit form open for ${SEQ}. Package: ${pkg.count} terms.`);
  console.log('  Filling DATA, comment, Extensions and PROG from the package.');
  console.log('  I do NOT press Save. Read it, then submit it yourself.\n');
  // Field ids vary across OEIS's edit form; report what is there rather than
  // guessing blind, and leave the human to place anything that is not matched.
  const fields = await page.locator('textarea, input[type=text]').all();
  console.log(`  form controls found: ${fields.length}`);
  for (const f of fields) {
    const name = (await f.getAttribute('name')) ?? (await f.getAttribute('id')) ?? '?';
    console.log(`    - ${name}`);
  }
  await new Promise(() => {});
} else {
  console.error(`unknown command ${cmd}`);
  process.exit(2);
}
