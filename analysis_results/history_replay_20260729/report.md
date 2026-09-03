# Coal history replay evaluation

- Period: 2025-10-21 through 2026-07-24
- Latest actual: 2026-07-28
- Common realized points: 65646

## Point accuracy

```
                     scope        n old_mape new_mape mape_improvement_pct old_mae new_mae new_better_pct
       all_common_realized 65646.00     8.20     7.14                12.91   54.58   48.94          53.28
                        h1  1278.00     0.78     0.45                42.01    5.14    3.03          56.57
                      h1_5  6432.00     1.74     1.44                17.04   11.58    9.62          52.25
                     h1_20 24870.00     4.97     4.30                13.34   32.94   28.71          52.89
                     h1_60 65646.00     8.20     7.14                12.91   54.58   48.94          53.28
   recent_since_2026-07-14   378.00     4.45     1.42                68.20   32.55   10.34          85.19
recent_h1_since_2026-07-14    54.00     1.74     0.75                56.75   12.66    5.33          81.48
```

## Per-index accuracy (first 20 horizons)

```
      data_type       n old_mape new_mape mape_improvement_pct old_direction_accuracy new_direction_accuracy
CCI3800outinfer 4145.00     4.71     4.58                 2.90                  59.46                  51.66
   CCI4500infer 4145.00     6.00     4.52                24.68                  59.42                  49.72
CCI4700outinfer 4145.00     4.10     3.98                 2.77                  61.26                  51.32
   CCI5000infer 4145.00     4.80     4.06                15.42                  67.43                  49.64
   CCI5500infer 4145.00     3.73     3.74                -0.26                  70.84                  50.27
CCI5500outinfer 4145.00     6.46     4.95                23.46                  44.27                  64.19
```

## Slope direction

```
horizon       n old_slope_direction_accuracy new_slope_direction_accuracy old_mean_correlation new_mean_correlation
   5.00 1230.00                        59.87                        41.31                 0.20                -0.12
  20.00  960.00                        54.37                        41.25                 0.10                -0.13
```

## Interpretation warning

The replay uses a current checkpoint for historical inference dates. It therefore measures retrospective fit and database replacement quality, not a leakage-free live backtest.
