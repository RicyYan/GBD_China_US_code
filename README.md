# GBD China US analysis code

Core scripts for the China-US neurological burden analysis. 

## Scripts

- `01_analyze_neurological_asr_changes.py`: summarizes 1990-2023 changes in age-standardized rates.
- `02_calculate_age_standardized_rates.py`: calculates rates for all supplied measures using pooled global population weights for 1990-2023, normalized within each age band. These are custom weights, not published GBD world standard weights.
- `03_run_three_factor_decomposition.R`: decomposes changes into aging, population growth, and epidemiological effects.
- `05_plot_risk_factor_daly.py`: plots risk-attributable neurological DALY rates.
- `06_prepare_projection_calibration.py`: calibrates GBD forecasts to the 2023 estimates.

Python packages: `numpy`, `pandas`, `matplotlib`, and `openpyxl`. Script 03 uses base R only.

