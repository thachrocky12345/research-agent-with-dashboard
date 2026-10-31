# Tier A train

## 15 highest excess / CI width

| source | hash | type | dir | h | n | excess bps | CI lo | CI hi | ratio | hit | hit base | frac cells + | cost bps |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| vsa | cell | ND2 | bearish | 2 | 3895 | 2.95 | 1.70 | 4.37 | 1.10 | 0.497 | 0.460 | 0.84 | 9.15 |
| vsa | cell | ND | bearish | 2 | 3895 | 2.91 | 1.48 | 4.35 | 1.01 | 0.497 | 0.460 | 0.84 | 9.15 |
| vsa | cell | UT2 | bearish | 130 | 1978 | 29.96 | 7.83 | 52.62 | 0.67 | 0.405 | 0.383 | 0.76 | 5.42 |
| smc | b5882b27b24c | SMC_CHOCH_BEAR | bearish | 4 | 2029 | 4.42 | 1.20 | 8.05 | 0.65 | 0.461 | 0.461 | 0.64 | 4.80 |
| vsa | cell | ND | bearish | 8 | 3893 | 5.54 | 0.57 | 10.30 | 0.57 | 0.482 | 0.456 | 0.80 | 9.16 |
| vsa | cell | ND2 | bearish | 8 | 3893 | 5.39 | 0.48 | 10.00 | 0.57 | 0.482 | 0.457 | 0.80 | 9.16 |
| vsa | cell | UT | bearish | 130 | 16174 | 14.65 | 0.94 | 28.30 | 0.54 | 0.390 | 0.379 | 0.80 | 4.71 |
| smc | b5882b27b24c | SMC_BOS_BULL | bullish | 2 | 1915 | 2.12 | 0.12 | 4.18 | 0.52 | 0.488 | 0.503 | 0.64 | 4.38 |
| vsa | cell | LVT | bullish | 4 | 963 | 5.54 | 0.66 | 11.36 | 0.52 | 0.521 | 0.493 | 0.72 | 9.16 |
| smc | 814fe66acb91 | SMC_BOS_BULL | bullish | 2 | 1618 | 2.19 | -0.01 | 4.42 | 0.50 | 0.484 | 0.501 | 0.68 | 4.67 |
| vsa | cell | SO | bullish | 130 | 12848 | 17.27 | -0.09 | 36.22 | 0.48 | 0.629 | 0.612 | 0.80 | 5.39 |
| demark | ed66babbccd0 | DEMARK_BUY | bullish | 130 | 3564 | 19.18 | -1.78 | 39.37 | 0.47 | 0.612 | 0.609 | 0.80 | 7.64 |
| vsa | cell | UT2 | bearish | 78 | 1998 | 16.65 | -0.95 | 35.23 | 0.46 | 0.426 | 0.408 | 0.64 | 5.42 |
| smc | b5882b27b24c | SMC_CHOCH_BEAR | bearish | 8 | 2027 | 4.03 | -0.66 | 8.45 | 0.44 | 0.455 | 0.456 | 0.64 | 4.80 |
| vsa | cell | ND | bearish | 4 | 3894 | 2.04 | -0.42 | 4.28 | 0.43 | 0.484 | 0.463 | 0.64 | 9.16 |

## 5 lowest excess / CI width

| source | hash | type | dir | h | n | excess bps | CI lo | CI hi | ratio | hit | hit base | frac cells + | cost bps |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| smc | b5882b27b24c | SMC_BOS_BEAR | bearish | 130 | 1351 | -37.65 | -63.78 | -10.25 | -0.70 | 0.346 | 0.382 | 0.24 | 5.25 |
| smc | 87355a6ff467 | SMC_BOS_BEAR | bearish | 130 | 976 | -39.97 | -70.09 | -10.15 | -0.67 | 0.345 | 0.383 | 0.24 | 5.29 |
| smc | b5882b27b24c | SMC_BOS_BEAR | bearish | 8 | 1383 | -6.92 | -12.24 | -1.21 | -0.63 | 0.444 | 0.459 | 0.32 | 5.20 |
| smc | b5882b27b24c | SMC_BOS_BEAR | bearish | 26 | 1374 | -14.37 | -27.25 | -2.59 | -0.58 | 0.414 | 0.442 | 0.20 | 5.21 |
| vsa | cell | TC | bullish | 8 | 26725 | -2.09 | -3.86 | -0.20 | -0.57 | 0.520 | 0.531 | 0.32 | 5.14 |

- Train-cell Tier A, 204 combos (source, hash, signal type, direction, horizon), 76.0s. This is a ranking for reading, not a selection.
- 22 of 204 combos have a 95% CI that excludes 0. Pure chance at 5% would be about 10.2.
- Excess is signal mean minus matched-random mean, in bps of the underlying. Cost bps is the mean of 2 * $0.01 / close at the signal bar (slippage line from the card, not the 2 bps economic cost).
- A combo is not marked alive here. Alive requires the cost test on train and a holdout CI, and the holdout list is still empty.
- Hashes are the pool directories that contain all 55 cells. VSA uses hash `cell` because those signals are stored on the cell.

What I am unsure about: several pool hashes for the same source are different generator settings, so the same signal type can appear more than once. Overlapping horizons share days; the day-block bootstrap is the dependence control, and it does not remove the multiple-comparison problem in this table.
