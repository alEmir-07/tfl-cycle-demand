#!/usr/bin/env bash
# Reproduce the whole project end to end (≈1.5 GB download, ~15 min compute on a laptop).
set -euo pipefail
cd "$(dirname "$0")"
python src/download.py all
cd notebooks
for nb in 01_cleaning 02_eda 03_modelling 04_rebalancing; do
  jupyter nbconvert --to notebook --execute --inplace --ExecutePreprocessor.timeout=3600 "$nb.ipynb"
done
