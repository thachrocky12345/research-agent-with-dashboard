# regime-risk program

Pasted from docs/RESEARCH_SPRINT_regime_risk.md sections 0, 2, and 3 on 2026-10-29.
These rules are pre-registered. Do not edit them after results exist.
Immutable experiment laws are in laws.md. This file is the sprint protocol.

## 0. Decisions carried in from the review

| Component | Decision |
|---|---|
| SMC / DeMark / VSA / EMA34 as trading strategies | **STOP.** 864 + 576 + 288 + 216 configs and a 206-experiment combination search; nothing held up out of sample. |
| Adding indicators, optimizing win rate, LLM chart reading, buying GEX history now | **STOP.** |
| Backtester cost model, ARK conventions, stockdb `research` schema, Research tab | **KEEP.** |
| One final diagnostic on the existing signals (information vs. monetization) | **DO ONCE** (Week 1), then close the question for good. |
| Daily forward-risk prediction with calibrated probabilities | **CONTINUE, gated.** |
| Risk-gated exposure as the economic test ("when not to trade") | **CONTINUE, gated.** |
| Event-driven research (earnings) | **DEFERRED** to a later sprint. stockdb has no point-in-time earnings data; estimate the data cost first. |

**One reframing.** "Predict the market regime" becomes "predict forward risk" with supervised,
scoreable targets (section 2). An unsupervised regime label cannot be scored out of sample, so
regime models (HMM) enter only as an optional *feature* in T3.4, never as the target.

**The trap to avoid.** Most "risk predictability" is volatility clustering. The GEX check already
showed an apparent edge that was implied volatility restated. So every model here must beat a
**vol-only baseline (B1)**, not just an unconditional one. Passing the gate means the features
carry information beyond trailing vol and VIX.

---

## 2. Pre-registration (write before Week 2; never change after)

### 2.1 Time splits (daily work)

| Split | Dates | Who may look |
|---|---|---|
| Development | 2000-01-03 → 2018-12-31 (core features); 2014-03-10 → 2018-12-31 (ETF features) | Grok, freely. Model and feature-set choices happen here. |
| Validation | 2019-01-02 → 2021-12-31 | Scored by expanding-window walk-forward (refit each January on all data before). Gates G2/G3 read these numbers. Each model is scored here **once**. |
| Final holdout | 2022-01-03 → 2024-09-27 | **Human only, once** (T4.1). Scripts refuse these dates without `HUMAN=1`. |

Intraday Tier A work keeps the existing ARK split: train cells for selection, holdout cells for
confirmation of ≤3 pre-registered combinations.

### 2.2 Targets (SPY primary, QQQ as a second check), all measured from close t

| Name | Definition | Type |
|---|---|---|
| `T_down` | 1 if the close-to-close return over the next 5 trading days < −2% | classification |
| `T_volexp` | 1 if realized vol over the next 5 days (√Σ daily log-return², annualized) > trailing 60-day median of that 5-day RV series | classification |
| `T_rv` | log of next-5-day realized vol | regression |

Five days: long enough to act on with exposure changes, short enough for ~4,700 development
observations on SPY.

### 2.3 Baselines every model must be compared to

| Id | Baseline | For |
|---|---|---|
| B0 | Rolling 3-year base rate (classification); trailing 20-day RV (regression) | sanity |
| **B1** | Logistic / ridge on `[log RV20, log VIX, RV5/RV20]` only, same walk-forward | **the gate** |
| HAR | HAR-RV regression on RV1, RV5, RV22 | `T_rv` gate |
| BH | Buy-and-hold SPY | economic |
| DMA | Long when close > 200-day MA, else cash | economic |
| VT | Vol targeting: exposure = min(1, 0.15 / RV20) | economic, reported |

### 2.4 Metrics

- Classification: Brier, log loss, AUC, expected calibration error (10 bins), and
  **Brier skill score vs B1**: `BSS = 1 − Brier_model / Brier_B1`.
- Regression: QLIKE and MSE on log RV; **skill vs HAR** = `1 − QLIKE_model / QLIKE_HAR`.
- Economic (exposure strategies): CAGR, daily Sharpe annualized, max drawdown, turnover, time in
  market, **after 2 bps per side** on notional changed (SPY/QQQ are that liquid).

### 2.5 Gates (pass/fail written in `events.log` and `reports/GATE_Gn.md`)

| Gate | When | Pass condition | On fail |
|---|---|---|---|
| **G1** | end of Week 1 | Tier A controls behave (cheat signal ≫ 0, random ≈ 0). Feature causality test passes. Benchmarks table exists. Separately: a signal/horizon combo is "alive" only if its excess return exceeds 2× round-trip cost on train **and** keeps its sign with a CI excluding 0 on holdout. | Infrastructure gate: fix, don't proceed. Signals: closed for good if none alive. |
| **G2** | end of Week 2 | At least one of `T_down` / `T_volexp` has BSS vs B1 ≥ 0.05, or `T_rv` has QLIKE skill vs HAR ≥ 5%, on the validation years, and positive in ≥ 2 of the 3 years. | **Stop the sprint.** Write the null report. Keep the infrastructure. |
| **G3** | end of Week 3 | With one of the three fixed exposure mappings (T3.2), validation-years max drawdown < BH **and** Sharpe ≥ BH, after costs. Report VT alongside. | **Stop the sprint.** |
| **G4** | end of Week 4 | Same as G3 on the final holdout, run once by the human. Also survives: features lagged +1 day, costs ×2. | **Stop.** |

If a gate passes, the next step is a forward paper-track (daily predictions written to stockdb,
scored monthly), **not capital**.

Thresholds are set now. Changing one after seeing a result is overfitting the gate.

---

## 3. Rules for every task (paste this block before any G card)

```
You are working in /Users/thachbui/Documents/ultimate-stock-ai/research-agent-with-dashboard/experiments/regime-risk/
Python: /Users/thachbui/Documents/ultimate-stock-ai/backend/venv/bin/python
Plan: /Users/thachbui/Documents/ultimate-stock-ai/docs/RESEARCH_SPRINT_regime_risk.md (sections 1-2 are facts and pre-registered rules; read them first)

Data access
- Daily bars: from app.lib.stockdb_source import get_daily_bars, list_daily_symbols (table names are lowercase: stock_data.spy).
  Copy the backend import preamble from ../indicator-combo/evaluate.py lines 23-37 (sys.path insert + app.services stub). Use adjclose for returns.
- Intraday bars and signal pools: read-only from ../indicator-combo/data/cells/ and ../indicator-combo/data/pools/.
- NEVER query market.stock_* tables. NEVER write to any database except stockdb schema "research". NEVER touch 192.168.1.195.
- Pull one symbol at a time with a short sleep; cache raw pulls under data/raw/ so a rerun never hits the DB.

Causality and splits
- A feature at date t uses only data dated <= t. A target at date t starts at t+1. Ship a truncation test with every feature.
- Never load dates after 2021-12-31 unless the script is run with HUMAN=1 by the human. Assert it.
- Choose models / feature sets / parameters on the development split only. Score the validation split once per choice.
- Use only the parameter grids written in the task card. A new idea goes into journal.md as a hypothesis; do not run it.

Deliverables, every task
- One script in the folder, one report in reports/<task>.md: a table, at most 5 bullets, and a "What I am unsure about" line.
- Append rows to results.tsv (tab-separated; header: task  run_id  split  target  model  feature_set  metric  value  baseline  skill  n  note). Never edit old rows.
- Print the acceptance test output and paste it at the end of the report.
- Hand back: files created, report path, results.tsv rows added, acceptance output, anything that failed.

Hygiene
- Do not edit anything under ../indicator-combo/. Do not edit files listed in config/manifest.json after T1.5 locks them.
- Kill anything that runs longer than 10 minutes; make it cheaper and note it.
- No claims without the number next to them. If a result looks too good, say so and look for a leak first.
```

---
