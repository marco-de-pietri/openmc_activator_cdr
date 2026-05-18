# Getting Started

Run `compare.py` to perform the OpenMC simulations and compare them with precalculated FISPACT results from the CoNDERC benchmark data.

Run all cases:

```bash
python compare.py
```

Run a small deterministic subset:

```bash
python compare.py --random-select 1 --random-seed 1
```

Run selected materials:

```bash
python compare.py --materials Fe SS304 SS316
```

Run selected experiment campaigns:

```bash
python compare.py --experiments 2000exp_5min
```

The script writes interactive plots to `results/html/`, generated dashboard metadata to `results/`, and raw JSON summaries to the repository root.

Open the root `overview.html` file in a browser to navigate the generated element and material results.

To remove generated results while preserving nuclear data and extracted benchmark inputs:

```bash
./clean_results.sh
```

Build the Jupyter Book with:

```bash
jupyter-book build .
```
