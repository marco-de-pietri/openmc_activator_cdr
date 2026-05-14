#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# OpenMC Development Environment Setup Script
# -----------------------------------------------------------------------------
# This script:
# 1. Creates a fresh conda environment with required dependencies
# 2. Clones the OpenMC repository (develop branch)
# 3. Downloads and converts TENDL-2017 neutron cross sections locally
# 4. Sets OPENMC_CROSS_SECTIONS only in this conda env
# 5. Builds and installs OpenMC from source into the conda environment
# 6. Installs Python bindings + testing extras
# 7. Verifies the installation
# -----------------------------------------------------------------------------

set -euo pipefail

# ---------------------------
# Configuration
# ---------------------------
ENV_NAME="openmc-activator-cdr" # Name of the conda environment
GH_PROFILE="openmc-dev"
PY_VER="3.14"
PROJECT_DIR_NAME="openmc_activator_cdr"
REQUIRED_RUN_DIR="/$PROJECT_DIR_NAME/scripts"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd -P)"
RUN_ARTIFACTS_DIR="$REPO_ROOT/run_artifacts"
OPENMC_SRC_DIR="$RUN_ARTIFACTS_DIR/openmc"
CURRENT_DIR="$(pwd -P)"

if [[ "$(basename "$CURRENT_DIR")" != "scripts" ]] || [[ "$(basename "$(dirname "$CURRENT_DIR")")" != "$PROJECT_DIR_NAME" ]]; then
  echo "Error: this script must be run from $REQUIRED_RUN_DIR" >&2
  echo "Run: cd $REQUIRED_RUN_DIR && ./$(basename "$0")" >&2
  exit 1
fi

mkdir -p "$RUN_ARTIFACTS_DIR"

# ---------------------------
# Create conda environment
# ---------------------------
echo "Creating conda environment: $ENV_NAME"

conda create -y -n "$ENV_NAME" \
  python="$PY_VER" \
  cmake make git compilers hdf5 pip numba wget curl \
  -c conda-forge

# ---------------------------
# Activate environment
# ---------------------------
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate "$ENV_NAME"

echo "Activated environment: $ENV_NAME"

# ---------------------------
# Clone OpenMC repository
# ---------------------------
echo "Cloning OpenMC (develop branch)"

git clone --recurse-submodules \
  --branch develop \
  "https://github.com/$GH_PROFILE/openmc.git" \
  "$OPENMC_SRC_DIR"

cd "$OPENMC_SRC_DIR"

git checkout develop
git submodule update --init --recursive

# ---------------------------
# Build OpenMC
# ---------------------------
echo "Building OpenMC"

mkdir -p build
cd build

cmake -DCMAKE_INSTALL_PREFIX="$CONDA_PREFIX" -DOPENMC_ENABLE_STRICT_FP=on ..

make -j"$(nproc)"
make install

# ---------------------------
# Install Python bindings
# ---------------------------
cd ..

echo "Installing Python package (editable mode with tests)"

pip install -e '.[test]'
pip install PySide6
pip install openmc-plotter --no-deps
pip install neutronics_material_maker
pip install plotly
pip install git+https://github.com/fispact/pypact

# Reload environment so variables take effect in this shell
conda deactivate
conda activate "$ENV_NAME"


# ---------------------------
# Download nuclear data locally
# ---------------------------

cd "$RUN_ARTIFACTS_DIR"

echo "Running TENDL downloader"

TENDL_RELEASE="2017"
TENDL_HDF5="$RUN_ARTIFACTS_DIR/tendl-${TENDL_RELEASE}-hdf5"
TENDL_ACE="$RUN_ARTIFACTS_DIR/tendl-${TENDL_RELEASE}-ace"
TENDL_XS="$TENDL_HDF5/cross_sections.xml"

python "$SCRIPT_DIR/download-tendl.py" \
  --download \
  --extract \
  --release "$TENDL_RELEASE" \
  --destination "$TENDL_HDF5" \
  --cleanup



# Sanity checks
test -f "$TENDL_XS"
test -d "$TENDL_ACE"

# ---------------------------
# Set conda env-specific variables
# ---------------------------
echo "Setting conda environment variables"

conda env config vars set \
  OPENMC_CROSS_SECTIONS="$TENDL_XS"

# Reload environment so variables take effect in this shell
conda deactivate
conda activate "$ENV_NAME"

echo "OPENMC_CROSS_SECTIONS=$OPENMC_CROSS_SECTIONS"

# ---------------------------
# Verification
# ---------------------------
echo "Verifying installation"

python - <<EOF
import os
from importlib import metadata

import openmc
import numba

try:
    openmc_version = getattr(openmc, "__version__", None) or metadata.version("openmc")
except metadata.PackageNotFoundError:
    openmc_version = "unknown"

print("openmc:", openmc_version)
print("openmc module:", getattr(openmc, "__file__", "unknown"))
print("numba:", numba.__version__)
print("OPENMC_CROSS_SECTIONS:", os.environ.get("OPENMC_CROSS_SECTIONS"))
EOF

echo "OpenMC executable location:"
which openmc

echo "Setup complete!"
