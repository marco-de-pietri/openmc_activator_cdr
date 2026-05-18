# Install

Clone the repository and enter it:

```bash
git clone git@github.com:jbae11/openmc_activator.git
cd openmc_activator
```

The recommended setup uses the project conda installer. It builds OpenMC from the `develop` branch, downloads the TENDL-2017 nuclear data used by the benchmark, installs the Python dependencies, and configures `OPENMC_CROSS_SECTIONS` inside the conda environment.

```bash
cd scripts
./build_conda_activator_cdr.sh
```

After the script completes, activate the environment:

```bash
conda activate openmc-activator-cdr
```

Return to the repository root before running comparisons:

```bash
cd ..
python compare.py --random-select 1 --random-seed 1
```
