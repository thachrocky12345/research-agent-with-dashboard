# T4.3 Decision

Numbers sit beside the written thresholds. Continue or stop is blank. This file is not a capital decision. The holdout was not loaded.

| Gate | Threshold | Number | Written test |
|---|---|---|---|
| G1 controls | Cheat excess CI excludes 0. Random CI includes 0 on at least 90% of cells at every horizon. | Cheat minimum excess 13.71 bps, all h=4 cells exclude 0. Random minimum horizon fraction 0.880. Joint fraction 0.840. | Cheat passes. Random fails. |
| G1 features | Causality on 20 development dates, and a benchmarks table. | All six feature sets pass. Leak check passes. `reports/benchmarks.md` exists. | Passes. |
| G1 signals | A combo is alive only after a pre-registered holdout cell. | `config/tier_a_preregistered.json` has no combo. | No signal is alive. |
| G2 | One of `T_down` or `T_volexp` has validation BSS vs B1 ≥ 0.05, or `T_rv` QLIKE skill vs HAR ≥ 0.05, and the winner is positive in at least 2 of 3 years. | SPY `T_down` BSS 0.004752, positive in 1 of 3 years (2019 0.086, 2020 −0.012, 2021 −0.014). Block interval −0.123 to 0.141. SPY `T_volexp` BSS 0.415123, positive in 3 of 3 years. Block interval 0.209 to 0.583, and 1,000 of 1,000 draws are positive. SPY `T_rv` skill −0.258825. | `T_volexp` meets the numeric test. `T_down` and `T_rv` do not. |
| G3 | One of the three fixed `P(T_down)` mappings has validation max drawdown less severe than buy-and-hold and Sharpe at least as high, after 2 bps. | SPY binary Sharpe 0.941 vs 1.087, max drawdown −0.118 vs −0.341. Linear 0.779 vs 1.087, −0.084 vs −0.341. Tercile 0.750 vs 1.087, −0.095 vs −0.341. Block interval for the binary Sharpe gap is −1.24 to +0.96. Share of draws with Sharpe at least buy-and-hold: 0.39. | Point test is not met. The interval still includes a pass. |
| G4 | The same economic test on the holdout, once, and the validation result still holds with features lagged one day and with costs at 4 bps. | Holdout not run. At 4 bps, SPY binary Sharpe is 0.898 vs buy-and-hold 1.087. Lagged `T_volexp` BSS is 0.354. Lagged `T_down` BSS is 0.003. Lagged exposure Sharpe is higher than buy-and-hold, and that mapping was not pre-registered. | Not scored. |

- Trailing-20-day realized vol is still the vol benchmark. HAR lost that development check, and the validation `T_rv` skill is negative.
- Dev-only isotonic calibration raises SPY validation ECE and Brier for both classification targets (`reports/w3_calibration.md`).
- SPY and QQQ agree on `T_volexp` (correlation 0.870) and disagree on `T_down` (correlation 0.280). QQQ validation BSS is 0.031 for `T_down` and 0.248 for `T_volexp`.
- The sprint text says a failed G3 stops the sprint before the holdout. T4.1 was not run for that reason.
- A pass on any later reading is a paper-track, a daily job writing `p`, exposure, and the realized outcome to stockdb schema `research`, scored monthly for at least three months.

What I am unsure about: the Sharpe-gap interval is wide enough that a single holdout window could land on either side of buy-and-hold. That is the human's call.

Human decision: ________

If the decision is continue, the next card is the one holdout run in T4.1, then the paper-track. T4.4 stays closed until that decision is written down.
