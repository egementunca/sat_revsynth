#!/bin/bash
# Install modern SAT solvers for high-performance circuit synthesis
# Based on SAT Competition 2024 results

set -e

INSTALL_DIR="${1:-$HOME/.local/bin}"
mkdir -p "$INSTALL_DIR"

echo "Installing SAT solvers to: $INSTALL_DIR"

# Temporary build directory
BUILD_DIR=$(mktemp -d)
cd "$BUILD_DIR"

# Install kissat (SAT Competition 2024 winner)
echo ">>> Installing kissat..."
git clone --depth 1 https://github.com/arminbiere/kissat.git
cd kissat
./configure
make -j$(nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 4)
cp build/kissat "$INSTALL_DIR/kissat"
cp build/kissat "$INSTALL_DIR/kissat-sc2024"  # Alias for current version
cd ..

# Install CaDiCaL 2.0
echo ">>> Installing CaDiCaL..."
git clone --depth 1 https://github.com/arminbiere/cadical.git
cd cadical
./configure
make -j$(nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 4)
cp build/cadical "$INSTALL_DIR/cadical"
cd ..

# Cleanup
rm -rf "$BUILD_DIR"

echo ""
echo "Installation complete!"
echo "Solvers installed to: $INSTALL_DIR"
echo ""
echo "Make sure $INSTALL_DIR is in your PATH:"
echo "  export PATH=\"\$PATH:$INSTALL_DIR\""
echo ""
echo "Verify installation:"
echo "  kissat --version"
echo "  cadical --version"
