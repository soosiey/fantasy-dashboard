# Calibration scripts

Run these commands from the repository root with the project virtual environment.

## Positional weekly coefficients

```bash
./venv/bin/python3 analysis/calibrate_positional_cv.py \
  --seasons 2024 2025
```

By default, the script uses the most recent half-PPR scoring settings saved in
`data/fantasy_dashboard.sqlite3`. Pass `--scoring-league-id` to load settings
directly from a Sleeper league instead.

## Draft-pick weights

Provide each historical season and its Sleeper league ID:

```bash
./venv/bin/python3 analysis/calibrate_draft_weights.py \
  --league 2024=1130262006908633088 \
  --league 2025=1257419717807722496
```

The draft script evaluates both actual deployed starter points and marginal
points in the optimal draft-only lineup. Historical data is cached outside the
repository under `/tmp/fantasy-dashboard-calibration` by default. Use
`--refresh` to replace cached API responses.

Both scripts write timestamp-independent JSON results beneath
`analysis/results/` unless `--output` specifies another path. Generated result
files are intentionally not committed automatically.

Use `--help` on either script for controls such as bootstrap draws, grid
resolution, cache paths, and output paths.
