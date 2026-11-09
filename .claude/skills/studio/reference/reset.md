# reset: revert to the launch baseline

`/studio reset` returns the built-in style packs and engine design settings to exactly how they shipped — the
**launch baseline** frozen at ship time. Use it when a creator has tweaked things and wants to come home, or is
unsure what they changed.

## Run
```
python product/studio_reset.py            # restore built-in defaults to the launch baseline
python product/studio_reset.py snapshot   # (ship-time only) freeze the current config AS the baseline
```

## Safe by design
- **Keeps the creator's own work:** any custom style pack they built (a pack not in the baseline) is preserved.
- **Backs up first:** the current config is copied to `_pre-reset-backup/<timestamp>/` before anything changes, so a reset is never destructive.
- **Never touches** their brand-kit or caption wordlist — those are theirs. Reset only restores the built-in packs + design settings.

The baseline lives in `product/creative-vault/_launch-baseline/`, re-frozen with `snapshot` at every release so
it always matches the packs that version ships. (Frozen once and never again, it made a reset undo every later
fix to the shipped packs; `product/tests/test_reset_baseline.py` fails when it drifts.)
