# regime-risk

Forward-risk sprint. Read `laws.md`, then `program.md` (pre-registered rules). Do not edit `../indicator-combo/`.

Python: `/Users/thachbui/Documents/ultimate-stock-ai/backend/venv/bin/python`

Primary metric: `bss_vs_B1` (higher is better). No floors. Eval command is `TBD until T1.5`.

Mutable later: `models/logit_l2.py`, `models/ridge_rv.py`, `models/lgbm.py`.
Immutable: `laws.md`. After T1.5, files listed in `config/manifest.json` are locked.

Do not load dates after 2021-12-31 unless the human runs the script with `HUMAN=1`.
Holdout Tier A runs only with `--only config/tier_a_preregistered.json` after a human has written at most three combos.

Results log header (tab-separated): `task run_id split target model feature_set metric value baseline skill n note`
