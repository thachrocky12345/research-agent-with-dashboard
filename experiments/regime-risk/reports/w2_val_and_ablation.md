# T2.4 One validation score, then one ablation

The development rule picks, for each target, the single SPY cell with the highest skill. Each choice is scored once on validation. `T_rv` skill is QLIKE skill versus HAR. On the same 721 rows, skill versus trailing `log_rv20` is −0.332027.

| Target | Choice | Dev skill | Val skill | 2019 | 2020 | 2021 | n |
|---|---|---:|---:|---:|---:|---:|---:|
| T_down | lgbm, full | −0.040146 | 0.004752 | 0.085966 | −0.012150 | −0.013510 | 721 |
| T_volexp | lgbm, full | 0.203396 | 0.415123 | 0.317521 | 0.640769 | 0.066101 | 721 |
| T_rv | lgbm, full | 0.097473 | −0.258825 | 0.056031 | −2.526693 | 0.124118 | 721 |

Ablation drops one group and rescores the same two validation fits. Delta is versus the untouched validation BSS. These fits were not used to change the choice.

| Group dropped | T_volexp BSS | delta | T_down BSS | delta |
|---|---:|---:|---:|---:|
| vol | 0.367 | −0.048 | 0.003 | −0.001 |
| credit | 0.401 | −0.015 | 0.012 | +0.007 |
| rates | 0.417 | +0.002 | 0.020 | +0.016 |
| breadth | 0.392 | −0.023 | −0.004 | −0.009 |
| sector / relative | 0.413 | −0.002 | 0.020 | +0.015 |
| trend / drawdown | 0.410 | −0.005 | 0.006 | +0.002 |
| liquidity | 0.416 | +0.001 | 0.006 | +0.002 |

- `T_down` validation BSS is 0.004752 and positive in one of three years. That is below 0.05. AUC on the same rows is 0.597835.
- `T_volexp` validation BSS is 0.415123, AUC 0.824455, positive in all three years. Positive rate is 0.4327. In 2020 the B1 Brier is 0.416870 and the model Brier is 0.149753, so part of that year's 0.640769 skill is the linear baseline collapsing.
- `T_rv` validation skill versus HAR is −0.258825. Skill versus trailing `log_rv20` on the same rows is −0.332027. 2020 skill versus HAR is −2.526693. Two years are positive and the pooled score misses 5%.
- Dropping the vol group leaves `T_volexp` BSS at 0.367. No single group removes it. The development `long` alternative, BSS 0.138497 on 4,528 rows, was not scored on validation.
- The written G2 test is met by `T_volexp` alone. `reports/GATE_G2.md` is not written. The holdout was not loaded. A pass would be a paper-track, not capital.

What I am unsure about: the `full` model was chosen on 755 development rows (2016–2018), and the validation BSS of 0.415123 had no second look allowed.

Acceptance output for the `T_rv` validation run, the one that was still missing:

```
qlike_skill_vs_har: -0.258825
qlike: -1.638734
mse: 0.304740
n: 721
year	n	qlike	skill	mse
2019	232	-3.318471	0.056031	0.131462
2020	253	1.276668	-2.526693	0.547781
2021	236	-3.112878	0.124118	0.214533
```
