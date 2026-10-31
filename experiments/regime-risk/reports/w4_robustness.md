# T4.2 Robustness on validation

Frozen model: LightGBM, feature set `full`. Validation only. The block bootstrap resamples 21-day blocks, 1,000 draws, seed 20261029. It does not refit the trees. Holdout dates were not loaded.

## BSS intervals

| symbol | target | bss | ci_low | ci_high | p_positive | n |
|---|---|---:|---:|---:|---:|---:|
| spy | T_down | 0.0048 | -0.1234 | 0.1407 | 0.5400 | 721 |
| spy | T_volexp | 0.4151 | 0.2092 | 0.5829 | 1.0000 | 721 |
| qqq | T_down | 0.0309 | -0.0415 | 0.1040 | 0.7730 | 741 |
| qqq | T_volexp | 0.2478 | 0.0720 | 0.3980 | 0.9960 | 741 |

## Sharpe minus buy-and-hold

| symbol | book | sharpe_diff | ci_low | ci_high | p_nonneg | n |
|---|---|---:|---:|---:|---:|---:|
| spy | binary | -0.1461 | -1.2356 | 0.9585 | 0.3910 | 752 |
| spy | linear | -0.3082 | -1.6582 | 0.9414 | 0.2720 | 752 |
| spy | tercile | -0.3366 | -1.6608 | 0.8298 | 0.2600 | 752 |
| qqq | binary | -0.4903 | -1.0692 | 0.1144 | 0.0620 | 745 |
| qqq | linear | -0.4708 | -1.0565 | 0.1404 | 0.0610 | 745 |
| qqq | tercile | -0.4850 | -1.0161 | 0.1437 | 0.0670 | 745 |

## Costs at 2 bps and 4 bps

| symbol | book | sharpe_2bps | max_dd_2bps | sharpe_4bps | max_dd_4bps | n |
|---|---|---:|---:|---:|---:|---:|
| spy | binary | 0.9407 | -0.1180 | 0.8980 | -0.1185 | 752 |
| spy | linear | 0.7786 | -0.0840 | 0.7170 | -0.0863 | 752 |
| spy | tercile | 0.7502 | -0.0949 | 0.6859 | -0.0969 | 752 |
| spy | BH | 1.0868 | -0.3410 | 1.0865 | -0.3410 | 752 |
| spy | VT | 1.4095 | -0.1646 | 1.4056 | -0.1648 | 752 |
| qqq | binary | 0.9329 | -0.2856 | 0.9127 | -0.2856 | 745 |
| qqq | linear | 0.9524 | -0.2790 | 0.9321 | -0.2790 | 745 |
| qqq | tercile | 0.9382 | -0.2856 | 0.9194 | -0.2856 | 745 |
| qqq | BH | 1.4232 | -0.2856 | 1.4229 | -0.2856 | 745 |
| qqq | VT | 1.5601 | -0.1394 | 1.5546 | -0.1395 | 745 |

## Features lagged one extra day

| symbol | target | bss_lag1 | bss_raw | n |
|---|---|---:|---:|---:|
| spy | T_down | 0.0031 | 0.0048 | 721 |
| spy | T_volexp | 0.3540 | 0.4151 | 721 |
| qqq | T_down | 0.0351 | 0.0309 | 741 |
| qqq | T_volexp | 0.2341 | 0.2478 | 741 |

Lagged `P(T_down)` uses the same three mappings. Cuts come from the lagged model's prior calendar year. `T_down` BSS stays near zero after the lag. The exposure Sharpe moves from below buy-and-hold to above it. That book is not a new selection. The pre-registered mappings stay the unlagged ones.

| symbol | book | sharpe | bh_sharpe | max_dd | bh_max_dd | n |
|---|---|---:|---:|---:|---:|---:|
| spy | binary | 1.4230 | 1.0868 | -0.0884 | -0.3410 | 752 |
| spy | linear | 1.3312 | 1.0868 | -0.0644 | -0.3410 | 752 |
| spy | tercile | 1.2614 | 1.0868 | -0.0618 | -0.3410 | 752 |
| qqq | binary | 1.8172 | 1.4232 | -0.1453 | -0.2856 | 745 |
| qqq | linear | 1.7480 | 1.4232 | -0.1059 | -0.2856 | 745 |
| qqq | tercile | 1.9421 | 1.4232 | -0.1034 | -0.2856 | 745 |

## Per-year stability at 2 bps

| symbol | year | book | sharpe | bh_sharpe | max_dd | bh_max_dd | sharpe_ge | dd_less_severe |
|---|---:|---|---:|---:|---:|---:|---:|---:|
| spy | 2019 | binary | 1.1342 | 2.1611 | -0.0690 | -0.0688 | 0 | 0 |
| spy | 2020 | binary | 0.8537 | 0.6153 | -0.1180 | -0.3410 | 1 | 1 |
| spy | 2021 | binary | 0.9774 | 1.8521 | -0.0587 | -0.0542 | 0 | 0 |
| spy | 2019 | linear | 1.3934 | 2.1611 | -0.0660 | -0.0688 | 0 | 1 |
| spy | 2020 | linear | 0.7980 | 0.6153 | -0.0234 | -0.3410 | 1 | 1 |
| spy | 2021 | linear | 0.2454 | 1.8521 | -0.0840 | -0.0542 | 0 | 0 |
| spy | 2019 | tercile | 1.3748 | 2.1611 | -0.0628 | -0.0688 | 0 | 1 |
| spy | 2020 | tercile | 0.9859 | 0.6153 | -0.0473 | -0.3410 | 1 | 1 |
| spy | 2021 | tercile | -0.0394 | 1.8521 | -0.0949 | -0.0542 | 0 | 0 |
| spy | 2019 | VT | 1.9575 | 2.1611 | -0.0687 | -0.0688 | 0 | 1 |
| spy | 2020 | VT | 0.7295 | 0.6153 | -0.1646 | -0.3410 | 1 | 1 |
| spy | 2021 | VT | 1.8151 | 1.8521 | -0.0542 | -0.0542 | 0 | 0 |
| qqq | 2019 | binary | 1.2870 | 2.1739 | -0.1357 | -0.1098 | 0 | 0 |
| qqq | 2020 | binary | 1.2695 | 1.2701 | -0.2856 | -0.2856 | 0 | 0 |
| qqq | 2021 | binary | -1.0457 | 1.4328 | -0.0002 | -0.1085 | 0 | 1 |
| qqq | 2019 | linear | 1.3611 | 2.1739 | -0.1232 | -0.1098 | 0 | 0 |
| qqq | 2020 | linear | 1.2878 | 1.2701 | -0.2790 | -0.2856 | 1 | 1 |
| qqq | 2021 | linear | -1.0457 | 1.4328 | -0.0002 | -0.1085 | 0 | 1 |
| qqq | 2019 | tercile | 1.3654 | 2.1739 | -0.1260 | -0.1098 | 0 | 0 |
| qqq | 2020 | tercile | 1.2695 | 1.2701 | -0.2856 | -0.2856 | 0 | 0 |
| qqq | 2021 | tercile | -1.0457 | 1.4328 | -0.0002 | -0.1085 | 0 | 1 |
| qqq | 2019 | VT | 1.9433 | 2.1739 | -0.0961 | -0.1098 | 0 | 1 |
| qqq | 2020 | VT | 1.5175 | 1.2701 | -0.1394 | -0.2856 | 1 | 1 |
| qqq | 2021 | VT | 1.2783 | 1.4328 | -0.0791 | -0.1085 | 0 | 1 |

## SPY and QQQ probability agreement

| target | corr | n |
|---|---:|---:|
| T_down | 0.2797 | 721 |
| T_volexp | 0.8697 | 721 |

- Intervals are percentiles of the block bootstrap. The trees are not refit inside each draw.
- `p_positive` is the share of draws with BSS above zero. `p_nonneg` is the share with Sharpe at least buy-and-hold.
- `dd_less_severe` is 1 when the stored drawdown is closer to zero than buy-and-hold.
- Lagged BSS is the same walk-forward rule on the previous row's features. `bss_raw` is the unlagged validation BSS.
- Holdout dates were not loaded. This file does not pick a model and does not decide a gate.

What I am unsure about: the bootstrap misses training noise because LightGBM stays fixed inside each draw.
