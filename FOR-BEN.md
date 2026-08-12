# For Ben — one thing this branch could not push

## CI never runs two of the three web test suites

`.github/workflows/ci.yml`'s `web` job names one file by hand:

```yaml
      - name: Growth-form registry tests
        run: node --test web/growth-forms.test.mjs
```

So `web/pots.test.mjs` — the whole pot layer's behavioural suite, shipped
2026-08-11 — has never once been run by CI, and neither would
`web/centre-plant.test.mjs` from this branch. Green there does not currently
mean "the web suites pass".

The fix is one line, verified locally (44 tests, all green):

```diff
-      - name: Growth-form registry tests
-        run: node --test web/growth-forms.test.mjs
+      # Every web suite, by glob — naming one file by hand is how web/pots.test.mjs
+      # shipped on 2026-08-11 and was never once run by CI.
+      - name: Web suites (growth forms, pots, the centre plant)
+        run: node --test web/*.test.mjs
```

**Why it is not in the PR:** pushing a `.github/workflows/` edit needs the
`workflow` OAuth scope, which this session's token does not have:

```
! [remote rejected] center-plant-per-track -> center-plant-per-track
  (refusing to allow an OAuth App to create or update workflow
   `.github/workflows/ci.yml` without `workflow` scope)
```

Apply it yourself on the branch (`! ` in a session with your creds), or say the
word and I will re-raise it as its own PR once the scope is there.

**What still gates this branch without it:** the two source guards in
`tests/test_web_growth_forms.py` DO run in CI's fast `pipeline` job, so the
wiring regression (the centre going back to the whole-lab ledger) is caught.
What is *not* gated by CI is the behavioural proof — `benchLadder` actually
producing the bench track's numbers against the committed feed. That runs
locally with `node --test web/*.test.mjs`.
