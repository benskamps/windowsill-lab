#!/usr/bin/env python3
"""Generate the Band Survey artifact. Fonts inlined; no external requests."""
import base64, pathlib

F = pathlib.Path('/home/benslinuxbox/projects/brokenbranchdevwebsite/fonts')
b64 = lambda n: base64.b64encode((F / n).read_bytes()).decode()
FR_N, FR_I, JB_N = b64('fraunces-normal-latin.woff2'), b64('fraunces-italic-latin.woff2'), b64('jetbrainsmono-normal-latin.woff2')

STATIONS = [
    ("fpsacha/zomboid-control-panel", "449 commits &middot; MIT &middot; B42.18", 7, 92, "rival", "ahead of us"),
    ("Danixu docker image", "352&#9733; &middot; the de-facto standard", 19, 84, "rival", "interop, don't compete"),
    ("trongio manager", "Laravel + Postgres + Redis", 30, 58, "rival", "different scope"),
    ("LinuxGSM pzserver", "4,889&#9733; &middot; process lifecycle only", 40, 36, "thin", "no mod smarts"),
    ("Pterodactyl / Pelican egg", "egg store archived 2024-05-14", 50, 13, "dead", "frozen pre-B42"),
    ("~15 commercial hosts", "GPORTAL &middot; Nitrado &middot; Apex &hellip;", 61, 28, "thin", "twin-list unsolved"),
    ("BisectHosting &ldquo;Biko&rdquo;", "2026-07-06 &middot; panel Q&amp;A only", 71, 16, "thin", "the market's only AI"),
]

RECEIPTS = [
    ("wardend selftest", "1132 passed / 2 failed", "1222 passed / 0 failed", ""),
    ("pytest tests/", "0 collected &mdash; green by vacancy", "7 collected &middot; 1 true-positive red", "warn"),
    ("hunted candidates", "116 found, 70 adjudicated", "116 adjudicated &middot; 56 fixed", ""),
    ("lore hard-control fabrication", "18 %", "0 %", ""),
    ("held-out retrieval hit@4", "0.167", "0.833", ""),
    ("30d/120-bucket history query", "1200 ms &middot; budget 750", "239 ms", ""),
    ("Airwaves test harness", "90 assertions", "122 assertions", ""),
    ("files hardcoding this box", "60", "48 &mdash; only 18 real source", ""),
    ("ORGANS.md Warden flags open", "3", "0", ""),
]

SHIPPED = [
    ("the config contract", "lib/wardenpaths.py",
     "25 keys, precedence <em>env &gt; conf &gt; autodetect &gt; default</em>. Four keys actually autodetect &mdash; "
     "<code>pz_user</code>, <code>pz_home</code>, <code>world_name</code>, <code>pz_game</code> &mdash; and six more derive "
     "from those. That is where the <code>servertest</code> assumption finally died: <code>live_ini</code>, "
     "<code>admin_db</code>, <code>players_db</code> and the rest are now built from the world name rather than spelled "
     "out. When autodetect can't tell, it says UNKNOWN instead of guessing something plausible."),
    ("the preflight", "bin/warden-doctor",
     "Answers one question for a stranger: <em>will Warden work here, and if not, what exactly do I fix?</em> It reports "
     "every key with its <em>source</em>, not just its value, then checks filesystem, runtime, reachability and each "
     "optional subsystem with what is lost without it. It cannot crash on an unconfigured box &mdash; it reports. It also "
     "proves the zero-dependency claim rather than asserting it: <em>49 python files scanned, 0 third-party imports.</em>"),
    ("the layout bug", "mods/Bearings &middot; mods/KI5StabilizerB16Patch",
     "Both kept all their content inside a <code>42.13/</code> folder with <strong>no <code>common/</code> directory</strong> "
     "&mdash; which B42 requires before a mod is detected at all. That is the likeliest reason both have sat in "
     "<code>Mods=</code> doing nothing since July. Restructured to the layout the two working mods use; content verified "
     "byte-identical by md5 against the pre-move git objects. Whether it makes them load is unproven until a restart &mdash; "
     "a claim about a mod loader is only settled by the loader."),
    ("the silent revert", "mods/Airwaves",
     "The only way to configure the published mod was editing <code>AirwavesConfig.lua</code> <em>inside the mod "
     "directory</em> &mdash; which Steam overwrites on every Workshop update. Any operator who changed the frequency "
     "would have lost it, with no error, at an arbitrary later time. Configuration now lives outside the mod dir where "
     "Steam can't reach it. The new <code>isServer()</code> guard deliberately fails <em>open</em>, because this repo's own "
     "Clawboid testkit still lists isServer() reliability as unresolved &mdash; it can add a reason to stay quiet on a "
     "client, never a reason the live station goes silent."),
]

QUEUE = [
    ("Restart <span class='mono'>public-ember</span>, then re-run the gate", "blocked", "blocked on you",
     "The front door is still serving pre-swarm code &mdash; the process started at 16:52, the file changed at 01:32. "
     "The fabrication fix booked as 18&#8239;% &rarr; 0&#8239;% is on disk and in the selftest, but it is not what a "
     "stranger would actually hit. The battery run is yours because the classifier blocks an agent from running it."),
    ("Run the cable", "you", "your hands",
     "Sustained packet loss, worst single sample 100&#8239;%, on a WiFi-only box hosting public multiplayer. With the "
     "Steam scare resolved as a false alarm, this is now the top real item on the board. Players read packet loss as "
     "rubber-banding and leave without telling you."),
    ("Find one player", "open", "open",
     "Everything else is downstream of this. The research on where small B42 servers actually find people came back "
     "thinnest of all four briefs &mdash; that is the next thing worth a night, and it isn't engineering."),
    ("Decide whether Warden goes out at all", "open", "open",
     "<span class='mono'>docs/POSITIONING.md</span> is written for you to decide from, not to be sold to. It says plainly "
     "where we are behind. The defensible ground is the operator seat &mdash; and that window is narrowing rather than "
     "opening: an NPC-companion project had its first commit three days ago."),
]

stations = "".join(
    f'<div class="st {c}" style="left:{p}%"><div class="bar" style="height:{int(s*1.05)}px"></div>'
    f'<div class="nm">{n}</div><div class="sb">{sb}</div><div class="tag">{t}</div></div>'
    for n, sb, p, s, c, t in STATIONS)
ticks = "".join(f'<div class="tick{" maj" if i % 2 == 0 else ""}" style="left:{i*5}%"></div>' for i in range(21))
receipts = "".join(
    f'<tr><td>{g}</td><td class="n was">{w}</td><td class="n now {k}">{a}</td></tr>'
    for g, w, a, k in RECEIPTS)
shipped = "".join(
    f'<div class="ship"><span class="k">{k}</span><h3>{p}</h3><p>{b}</p></div>'
    for k, p, b in SHIPPED)
queue = "".join(
    f'<li><b>{t} <span class="chip c-{c}">{lbl}</span></b><p>{b}</p></li>'
    for t, c, lbl, b in QUEUE)

HTML = """<title>The Band Survey</title>
<style>
@font-face{font-family:'Fraunces';src:url(data:font/woff2;base64,__FRN__) format('woff2');font-weight:300 900;font-style:normal;font-display:block}
@font-face{font-family:'Fraunces';src:url(data:font/woff2;base64,__FRI__) format('woff2');font-weight:300 900;font-style:italic;font-display:block}
@font-face{font-family:'JetBrains Mono';src:url(data:font/woff2;base64,__JBN__) format('woff2');font-weight:300 700;font-style:normal;font-display:block}
:root{
 --bark:#1c1510;--bark2:#241b13;--panel:#2b2117;--line:#4a3b28;
 --parchment:#ece1cc;--dim:#b8a98c;--faint:#8a7c66;--ash:#6f6557;
 --ember:#e8833a;--moss:#8aa86b;--slate:#8fa3ad;--clay:#c4744a;--wax:#a84b3a;--brass:#c9a86a;
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bark);color:var(--parchment);
 font-family:'Fraunces',Georgia,'Times New Roman',serif;font-weight:360;font-size:17px;line-height:1.62;
 -webkit-font-smoothing:antialiased}
body::before{content:"";position:fixed;inset:0;pointer-events:none;z-index:99;opacity:.05;
 background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='140' height='140'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.85' numOctaves='3'/%3E%3C/filter%3E%3Crect width='140' height='140' filter='url(%23n)'/%3E%3C/svg%3E")}
.wrap{max-width:1000px;margin:0 auto;padding:0 28px 96px}
.mono{font-family:'JetBrains Mono',ui-monospace,monospace}
.eyebrow{font-family:'JetBrains Mono',ui-monospace,monospace;font-size:10px;letter-spacing:.4em;
 text-transform:uppercase;color:var(--brass)}
header{padding:74px 0 34px;border-bottom:1px solid var(--line);
 background:radial-gradient(120% 150% at 12% -12%,rgba(232,131,58,.12),transparent 62%)}
h1{font-size:clamp(46px,9vw,112px);font-style:italic;font-weight:380;
 font-variation-settings:'opsz' 144;letter-spacing:-.018em;line-height:.96;margin:16px 0 0;text-wrap:balance}
.dek{max-width:62ch;color:var(--dim);font-size:19px;font-style:italic;margin:20px 0 0}
.stamp{display:inline-block;margin-top:26px;padding:5px 12px;border:1px solid var(--wax);color:var(--wax);
 font-family:'JetBrains Mono',ui-monospace,monospace;font-size:9px;letter-spacing:.28em;text-transform:uppercase}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(132px,1fr));gap:1px;
 background:var(--line);border:1px solid var(--line);margin:40px 0 0}
.stat{background:var(--bark2);padding:16px 18px}
.stat b{display:block;font-family:'JetBrains Mono',ui-monospace,monospace;font-size:26px;font-weight:600;
 color:var(--ember);font-variant-numeric:tabular-nums;line-height:1.1}
.stat.zero b{color:var(--wax)}
.stat span{display:block;font-family:'JetBrains Mono',ui-monospace,monospace;font-size:9px;letter-spacing:.15em;
 text-transform:uppercase;color:var(--faint);margin-top:7px}
section{padding:62px 0 0}
h2{font-size:31px;font-style:italic;font-weight:400;margin:0 0 6px;letter-spacing:-.01em;text-wrap:balance}
.sub{color:var(--faint);font-size:15px;font-style:italic;margin:0 0 30px;max-width:66ch}
p{max-width:68ch}
.band{border:1px solid var(--line);background:linear-gradient(180deg,var(--bark2),#1e1710);
 padding:30px 26px 16px;overflow-x:auto}
.dial{position:relative;height:186px;min-width:700px}
.tick{position:absolute;bottom:0;width:1px;background:var(--line);height:8px}
.tick.maj{height:14px;background:#5c4a33}
.st{position:absolute;bottom:22px;transform:translateX(-50%);text-align:center;width:132px}
.bar{width:3px;margin:0 auto;background:var(--slate);border-radius:2px 2px 0 0}
.st.rival .bar{background:var(--clay)}
.st.dead .bar{background:var(--ash);opacity:.6}
.st.ours .bar{background:var(--ember);width:5px;box-shadow:0 0 20px rgba(232,131,58,.6)}
.st .nm{font-family:'JetBrains Mono',ui-monospace,monospace;font-size:8.5px;letter-spacing:.04em;
 color:var(--parchment);margin-top:9px;line-height:1.4}
.st .sb{font-family:'JetBrains Mono',ui-monospace,monospace;font-size:7.5px;color:var(--faint);margin-top:3px;line-height:1.35}
.st .tag{font-family:'JetBrains Mono',ui-monospace,monospace;font-size:7px;letter-spacing:.13em;
 text-transform:uppercase;margin-top:5px;color:var(--clay)}
.st.ours .nm{color:var(--ember)}
.st.ours .tag{color:var(--ember)}
.st.dead .tag,.st.thin .tag{color:var(--faint)}
.deadair{position:absolute;bottom:22px;height:132px;border:1px dashed rgba(138,168,107,.45);
 background:rgba(138,168,107,.05)}
.deadair span{position:absolute;top:10px;left:0;right:0;text-align:center;
 font-family:'JetBrains Mono',ui-monospace,monospace;font-size:8.5px;letter-spacing:.22em;
 text-transform:uppercase;color:var(--moss)}
.scale{display:flex;justify-content:space-between;font-family:'JetBrains Mono',ui-monospace,monospace;
 font-size:8.5px;letter-spacing:.15em;color:var(--faint);text-transform:uppercase;
 border-top:1px solid var(--line);padding-top:10px;margin-top:2px;min-width:700px}
.pull{border-left:2px solid var(--ember);padding:4px 0 4px 22px;margin:28px 0;
 font-style:italic;font-size:21px;max-width:60ch;line-height:1.45}
.note{border:1px solid var(--line);background:var(--panel);padding:20px 22px;margin:26px 0}
.note.warn{border-color:var(--clay)}
.note.good{border-color:var(--moss)}
.note p{margin:0;max-width:none}
.ship{border-top:1px solid var(--line);padding:26px 0}
.ship h3{margin:0;font-weight:400;font-style:normal;
 font-family:'JetBrains Mono',ui-monospace,monospace;font-size:12.5px;letter-spacing:.05em;color:var(--parchment)}
.ship .k{font-family:'JetBrains Mono',ui-monospace,monospace;font-size:9px;letter-spacing:.26em;
 text-transform:uppercase;color:var(--brass);display:block;margin-bottom:9px}
.ship code{font-family:'JetBrains Mono',ui-monospace,monospace;font-size:.85em;color:var(--ember);
 background:rgba(232,131,58,.09);padding:1px 5px}
.ship p{margin:11px 0 0;color:var(--dim)}
.tblwrap{overflow-x:auto}
.tbl{width:100%;border-collapse:collapse;font-size:14px;min-width:520px}
.tbl th{font-family:'JetBrains Mono',ui-monospace,monospace;font-size:9px;letter-spacing:.2em;
 text-transform:uppercase;color:var(--faint);text-align:left;padding:10px 12px;
 border-bottom:1px solid var(--line);font-weight:400}
.tbl td{padding:11px 12px;border-bottom:1px solid rgba(74,59,40,.55);vertical-align:top}
.tbl td.n{font-family:'JetBrains Mono',ui-monospace,monospace;font-size:12px;font-variant-numeric:tabular-nums}
.tbl tr td:first-child{color:var(--dim)}
.was{color:var(--faint)}
.now{color:var(--moss)}
.now.warn{color:var(--clay)}
ol.q{list-style:none;counter-reset:q;padding:0;margin:0}
ol.q li{counter-increment:q;border-top:1px solid var(--line);padding:20px 0 20px 54px;position:relative}
ol.q li::before{content:counter(q,decimal-leading-zero);position:absolute;left:0;top:22px;
 font-family:'JetBrains Mono',ui-monospace,monospace;font-size:12px;color:var(--brass);letter-spacing:.1em}
ol.q b{font-weight:400;font-size:18px;font-style:italic;display:block}
ol.q p{margin:8px 0 0;color:var(--dim);font-size:15px;max-width:66ch}
.chip{display:inline-block;font-family:'JetBrains Mono',ui-monospace,monospace;font-size:7.5px;
 letter-spacing:.18em;text-transform:uppercase;padding:2px 7px;border:1px solid;margin-left:9px;vertical-align:3px;font-style:normal}
.c-you{color:var(--ember);border-color:var(--ember)}
.c-blocked{color:var(--wax);border-color:var(--wax)}
.c-open{color:var(--slate);border-color:var(--slate)}
footer{margin-top:78px;border-top:1px solid var(--line);padding-top:22px;
 font-family:'JetBrains Mono',ui-monospace,monospace;font-size:9px;letter-spacing:.13em;
 text-transform:uppercase;color:var(--faint);line-height:2.1}
@media (max-width:640px){.wrap{padding:0 18px 70px}.dek{font-size:17px}h2{font-size:26px}}
</style>

<div class="wrap">
<header>
 <div class="eyebrow">Broken Branch &middot; Warden &middot; night of 16&ndash;17 August 2026</div>
 <h1>The Band Survey</h1>
 <p class="dek">You asked me to zoom out and see who else was broadcasting. Here is the band, swept honestly
 &mdash; including the stretch where somebody else is already louder than us, and the dead air where nobody
 is transmitting at all.</p>
 <div class="stamp">Private &middot; nothing published, nothing sent</div>
 <div class="stats">
  <div class="stat"><b>370</b><span>agents run</span></div>
  <div class="stat"><b>116</b><span>candidates adjudicated</span></div>
  <div class="stat"><b>56</b><span>defects confirmed &amp; fixed</span></div>
  <div class="stat"><b>1222</b><span>selftest, none failing</span></div>
  <div class="stat zero"><b>0</b><span>players, ever</span></div>
 </div>
</header>

<section>
 <h2>The sweep</h2>
 <p class="sub">Signal height is maturity, not merit &mdash; commits, stars, and whether anyone has touched it
 since B42 went stable on 29 July. Every station here was read from source or vendor documentation, never from
 a README's claims about itself.</p>
 <div class="band">
  <div class="dial">
   __STATIONS__
   <div class="deadair" style="left:80%;right:1%"><span>dead air</span></div>
   <div class="st ours" style="left:89%">
    <div class="bar" style="height:112px"></div>
    <div class="nm">AN LLM IN THE<br>OPERATOR SEAT</div>
    <div class="sb">Minecraft: 4+ shipped<br>Project Zomboid: none</div>
    <div class="tag">unclaimed</div>
   </div>
   __TICKS__
  </div>
  <div class="scale"><span>crowded &mdash; mod &amp; server management</span><span>thinning</span><span>nobody here</span></div>
 </div>
</section>

<section>
 <h2>The part you won't enjoy</h2>
 <p>I had an agent read <span class="mono">fpsacha/zomboid-control-panel</span>'s source directly rather than its
 README, because I was about to spend a night defending the wrong hill. <strong>Their mod manager is better than
 ours.</strong> Everything <span class="mono">pzmod</span> does &mdash; disk-based resolution, B42 versioned
 directories, multi-mod Workshop items &mdash; plus a conflict scanner, <span class="mono">require=</span>-driven
 load-order sorting, map-folder detection, and a graphical picker. 449 commits, pushed three days ago. And
 B42.20 shipped a built-in mod manager of its own on 29 July.</p>
 <div class="pull">&ldquo;Kills the twin-list hell&rdquo; was true when it was written. It isn't now.</div>
 <div class="note good"><p><strong>The same read found something real, though.</strong> Both competitors write the
 live <span class="mono">.ini</span> <em>directly</em> when you add a mod &mdash; no diff, no review, no undo.
 Warden stages, diffs, and waits for a deliberate <span class="mono">--yes</span>, with byte-preserving edits and
 secret redaction enforced by a selftest. Neither has any of that. So the honest pitch is the <em>workflow
 property</em>, not the resolution mechanic: nothing touches your live server without a reviewed diff.</p></div>
 <p>The paid market tells the same story from the other side. Across roughly fifteen commercial hosts the
 twin-list problem is simply <em>unsolved</em> &mdash; Shockbyte, ScalaCube, BisectHosting and Indifferent
 Broccoli are confirmed-manual from their own documentation, and several send customers to free third-party
 tools rather than build it in. Exactly one meaningful AI feature exists in that entire market, and it is a
 panel Q&amp;A chatbot that knows nothing about mods.</p>
</section>

<section>
 <h2>What went in tonight</h2>
 <p class="sub">Four things landed. Two are bugs that had been quietly costing you something for weeks.</p>
 __SHIPPED__
</section>

<section>
 <h2>Receipts</h2>
 <p class="sub">Measured on this box after the work, by me &mdash; not taken from an agent's self-report.</p>
 <div class="tblwrap"><table class="tbl">
  <tr><th>gate</th><th>before</th><th>after</th></tr>
  __RECEIPTS__
 </table></div>
 <div class="note warn"><p><strong>The one red test is correct, and I left it red.</strong> Bumping Airwaves to
 0.3.0 made the drift detector notice the live install is still 0.2.0. That is the detector doing its job.
 Deploying means a restart, which is yours to call rather than an agent's.</p></div>
</section>

<section>
 <h2>The thing no amount of agents can fix</h2>
 <p>The server is up, public, listed on Steam, reachable, with no join blockers. Airwaves is published and healthy
 with three subscribers &mdash; I checked that listing twice tonight, because one scout reported it had been taken
 down. It hadn't. It had read a CSS-hidden template string that sits on every Workshop page and concluded a ban.</p>
 <div class="pull">Not one player has ever connected. Zero, across every log since launch.</div>
 <p>Two nights and 370 agents have made Warden genuinely better &mdash; a shell injection dead, an auth token no
 longer visible in <span class="mono">ps aux</span>, player transcripts no longer world-readable, a silent
 data-contamination bug found hiding behind a performance miss. But every claim about Ember still rests on a room
 nobody has walked into. <span class="mono">ember-radio</span> has now met a real Project Zomboid runtime. It has
 never met a person. That is a distribution problem, and it is the one thing I can't throw compute at.</p>
</section>

<section>
 <h2>Yours to decide</h2>
 <p class="sub">Risk-sorted. Everything above this line is done; everything below needs you.</p>
 <ol class="q">__QUEUE__</ol>
</section>

<footer>
 Measured 2026-08-17 &middot; selftest 1222/0 &middot; pytest 7 collected &middot; 12 commits across two repos &middot; nothing pushed<br>
 Competitive figures read from source and vendor docs, dated; unverified claims left marked unverified<br>
 Self-contained &mdash; typefaces embedded, no external requests &middot; Loam
</footer>
</div>
"""

page = (HTML.replace('__FRN__', FR_N).replace('__FRI__', FR_I).replace('__JBN__', JB_N)
            .replace('__STATIONS__', stations).replace('__TICKS__', ticks)
            .replace('__RECEIPTS__', receipts).replace('__SHIPPED__', shipped)
            .replace('__QUEUE__', queue))

out = pathlib.Path('/home/benslinuxbox/cockpit/band-survey.html')
out.write_text(page, encoding='utf-8')
print(f'wrote {out}  {len(page)/1024:.0f} KB')
