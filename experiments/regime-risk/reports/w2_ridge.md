# T2.2 Ridge on realized vol, development only

Alpha is chosen from {0.1, 1, 10}. Skill is `(QLIKE_HAR − QLIKE_model) / |QLIKE_HAR|`. Positive means a lower loss than HAR. The card's ratio `1 − QLIKE_model / QLIKE_HAR` flips that ranking because these QLIKE values are negative.

| run | skill or BSS | loss | n |
|---|---:|---:|---:|
| ridge_rv_T_rv_long_spy | -0.152474 | -2.281882 | 4528 |
| ridge_rv_T_rv_long_qqq | -0.048960 | -2.175591 | 4280 |
| ridge_rv_T_rv_full_spy | -0.834384 | -0.515885 | 755 |
| ridge_rv_T_rv_full_qqq | -1.399152 | 1.025613 | 755 |

- No ridge run beats HAR on pooled development QLIKE. SPY `long` skill is −0.152.
- SPY `long` in 2002 has QLIKE +6.12 and MSE 1.22. That one year pulls the pooled loss up.
- HAR already failed the T1.4 check against trailing 20-day RV. A ridge that also loses to HAR is not a vol-gate candidate.
- `full` ridge is worse still. QQQ `full` QLIKE is positive (1.03).
- These four runs are the only ridge specification in the pre-registered grid. Alpha was not changed after the scores.


`ridge_rv_T_rv_long_spy`

```
year | n | loss | skill | extra
2001 | 248 | -1.154114 | -0.435112 | 1.306318
2002 | 252 | 6.123790 | -4.871695 | 1.221343
2003 | 252 | -2.270480 | -0.172316 | 0.217591
2004 | 252 | -3.322243 | -0.007216 | 0.184984
2005 | 252 | -3.540082 | 0.010668 | 0.145273
2006 | 251 | -3.684149 | -0.000296 | 0.151169
2007 | 251 | -2.549662 | 0.017506 | 0.184249
2008 | 253 | -1.230294 | 0.157243 | 0.236549
2009 | 252 | -1.931800 | 0.028923 | 0.123271
2010 | 252 | -2.436597 | -0.024635 | 0.232231
2011 | 252 | -2.062813 | 0.021044 | 0.168514
2012 | 250 | -3.164898 | 0.043813 | 0.180967
2013 | 252 | -3.339683 | 0.007740 | 0.160078
2014 | 252 | -3.469857 | 0.071535 | 0.188263
2015 | 252 | -2.697497 | 0.050699 | 0.174948
2016 | 252 | -3.402829 | 0.158956 | 0.189160
2017 | 251 | -4.404312 | 0.038551 | 0.272765
2018 | 252 | -2.544696 | 0.118179 | 0.217738
```


`ridge_rv_T_rv_long_qqq`

```
year | n | loss | skill | extra
2002 | 252 | -0.308873 | -0.581136 | 0.198018
2003 | 252 | -0.151549 | -0.913375 | 0.429225
2004 | 252 | -2.359068 | -0.044847 | 0.272199
2005 | 252 | -2.856492 | -0.047416 | 0.307059
2006 | 251 | -2.747938 | 0.012534 | 0.121153
2007 | 251 | -2.414605 | 0.026179 | 0.185720
2008 | 253 | -1.108697 | 0.069419 | 0.160411
2009 | 252 | -1.917902 | -0.007260 | 0.210528
2010 | 252 | -2.371783 | 0.032267 | 0.210720
2011 | 252 | -1.831497 | -0.054945 | 0.201784
2012 | 250 | -2.308700 | -0.138007 | 0.239365
2013 | 252 | -3.115426 | -0.002760 | 0.204572
2014 | 252 | -2.983592 | 0.053756 | 0.183178
2015 | 252 | -2.260210 | -0.002086 | 0.194232
2016 | 252 | -2.842541 | 0.114332 | 0.191746
2017 | 251 | -3.471306 | 0.035322 | 0.239295
2018 | 252 | -1.948520 | 0.039640 | 0.169512
```


`ridge_rv_T_rv_full_spy`

```
year | n | loss | skill | extra
2016 | 252 | -2.323294 | -0.239124 | 1.610715
2017 | 251 | -3.908134 | -0.084553 | 0.834311
2018 | 252 | 4.670311 | -3.304166 | 1.064994
```


`ridge_rv_T_rv_full_qqq`

```
year | n | loss | skill | extra
2016 | 252 | -2.137861 | -0.204612 | 0.384953
2017 | 251 | -2.969956 | -0.135315 | 0.312365
2018 | 252 | 8.168802 | -6.139769 | 1.408798
```

What I am unsure about: the 2002 loss may be an ill-conditioned fit in a high-vol year. The chosen alpha for that window was not printed.
