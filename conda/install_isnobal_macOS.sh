#!/usr/bin/env bash
set -euo pipefail

# ---- configuration ---------------------------------------------------------

DEFAULT_ENV_NAME="isnobal"
ENV_NAME="${1:-$DEFAULT_ENV_NAME}"
ENV_FILE="isnobal_macOS.yaml"
TARGET_SUBDIR="osx-64"

# ---- basic checks ----------------------------------------------------------

if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERROR: $ENV_FILE not found"
  exit 1
fi

if [[ "$(uname)" != "Darwin" ]]; then
  echo "ERROR: This script is intended for macOS only."
  exit 1
fi

# ---- choose solver ---------------------------------------------------------

if command -v mamba >/dev/null 2>&1; then
  CONDA=mamba
elif command -v conda >/dev/null 2>&1; then
  CONDA=conda
else
  echo "ERROR: conda or mamba not found in PATH"
  exit 1
fi

echo "Using solver: $CONDA"
echo "Environment name: $ENV_NAME"

# ---- create environment as osx-64 -----------------------------------------

echo "Creating environment '$ENV_NAME' (platform: $TARGET_SUBDIR)..."

CONDA_SUBDIR="$TARGET_SUBDIR" \
  $CONDA env create \
    --name "$ENV_NAME" \
    --file "$ENV_FILE"

# ---- pin subdir inside the environment ------------------------------------

echo "Pinning environment to $TARGET_SUBDIR..."

$CONDA run -n "$ENV_NAME" \
  conda config --env --set subdir "$TARGET_SUBDIR"

# ---- verify env architecture ----------------------------------------------

echo "Verifying environment '$ENV_NAME' is pinned to $TARGET_SUBDIR..."

# Check conda subdir setting
PINNED_SUBDIR=$($CONDA run -n "$ENV_NAME" conda config --show subdir | grep subdir | awk '{print $2}')

if [[ "$PINNED_SUBDIR" != "$TARGET_SUBDIR" ]]; then
  echo "ERROR: Environment subdir is '$PINNED_SUBDIR', expected '$TARGET_SUBDIR'"
  exit 1
fi

# ---- verify interpretter architecture -------------------------------------

echo "Verifying Python architecture..."

$CONDA run -n "$ENV_NAME" python - <<'EOF'
import platform
arch = platform.machine()
if arch != "x86_64":
    raise SystemExit(
        f"ERROR: Python is running as {arch}, expected x86_64.\n"
        "This environment requires osx-64 binaries."
    )
print("Python architecture:", arch)
EOF

# ---- optional: activation-time safety check --------------------------------

ACTIVATE_DIR="$($CONDA info --base)/envs/$ENV_NAME/etc/conda/activate.d"
mkdir -p "$ACTIVATE_DIR"

cat > "$ACTIVATE_DIR/verify_arch.py" <<'EOF'
import platform
if platform.machine() != "x86_64":
    raise SystemExit(
        "ERROR: This Conda environment requires x86_64 (osx-64) binaries.\n"
        "Rosetta may not be active."
    )
EOF

cat > "$ACTIVATE_DIR/verify_arch.sh" <<'EOF'
python "$CONDA_PREFIX/etc/conda/activate.d/verify_arch.py"
EOF

# ---- done ------------------------------------------------------------------

echo
echo "Environment '$ENV_NAME' installed successfully."
echo "• Platform pinned to: $TARGET_SUBDIR"
echo "• Python running as: x86_64"
echo
echo "Activate with: conda activate $ENV_NAME"
