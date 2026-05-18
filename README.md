[![Jupyter Book Badge](https://jupyterbook.org/badge.svg)](https://jbae11.github.io/openmc_activator/)

[![CI testing](https://github.com/jbae11/openmc_activator/actions/workflows/ci.yml/badge.svg)](https://github.com/jbae11/openmc_activator/actions/workflows/ci.yml)

# openmc_activator

Standalone OpenMC activation workflow for comparing OpenMC activation results with the IAEA CoNDERC FNS benchmark FISPACT-II results.

The main entry points are:

- `openmc_activator.py`: helper class for standalone neutron-source activation with OpenMC.
- `compare.py`: script that runs selected FNS benchmark cases and compares OpenMC contact dose rate against FISPACT-II gamma dose rate.
- `overview.html`: tracked root dashboard for browsing generated element and material results.
- `clean_results.sh`: removes generated result files while preserving nuclear data and benchmark inputs.

## Installation

The recommended setup builds OpenMC from the `develop` branch, downloads the TENDL-2017 nuclear data used by the benchmark, and configures `OPENMC_CROSS_SECTIONS` in a conda environment:

```bash
cd scripts
./build_conda_activator_cdr.sh
```

After the script completes, activate the environment:

```bash
conda activate openmc-activator-cdr
```

The setup script installs the Python packages needed by this repository, including `pypact`, `plotly`, `pymatviz`, `notebook`, `ipykernel`, and `jupytext`.

## Usage

Run all available FNS benchmark cases:

```bash
python compare.py
```

Run a small deterministic random subset:

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

Combine filters before random selection:

```bash
python compare.py --materials Fe Al Ni --random-select 2 --random-seed 42
```

## Notebook-Style Usage

`compare.py` is a Jupytext percent-format script. You can open it in Jupyter-compatible editors, or run it from a notebook with:

```python
%run compare.py --random-select 1 --random-seed 1
```

If you run cells directly inside the script, set `NOTEBOOK_ARGS` near the top of `compare.py`, for example:

```python
NOTEBOOK_ARGS = ["--random-select", "1", "--random-seed", "1"]
```

Leave it as `None` for normal command-line use.

## Outputs

The script writes:

- `results/html/<material>_<experiment>.html`: interactive per-case comparison plots.
- `results/html/periodic_table.html`: Plotly periodic-table overview for element results when element cases are present.
- `results/manifest.json` and `results/manifest.js`: generated result indexes used by the dashboard.
- `openmc_result_dict.json`, `fispact_result_dict.json`, `exp_data_dict.json`: raw result dictionaries for programmatic inspection.

Open `overview.html` in a browser to browse the current manifest-backed results. The dashboard starts on an overview page with:

- a clickable periodic table for element results;
- material tiles for non-element materials such as steels and alloys;
- experiment lists for each selected element or material;
- embedded per-experiment comparison plots.

If `./clean_results.sh` was just run, the dashboard remains available but shows an empty state.

Subset runs overwrite the result JSON and manifest files with only the selected cases. Old generated HTML files can remain on disk until cleaned, but the dashboard follows `results/manifest.js`.

To remove generated results while preserving `run_artifacts/` nuclear data and extracted `fns/` benchmark inputs:

```bash
./clean_results.sh
```

## Notes

The FISPACT-II comparison value is the total gamma dose rate from each `TENDL-2017_<experiment>.out` summary table. The OpenMC value is computed with `Material.get_photon_contact_dose_rate(dose_quantity="absorbed-air")`.
