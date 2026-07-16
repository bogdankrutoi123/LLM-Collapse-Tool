#!/usr/bin/env bash
# WSL + Windows drive (/mnt/d/...) breaks Node when node_modules lives on drvfs.
# Install dependencies on the native Linux filesystem and symlink them here.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
DEPS_DIR="${HOME}/thesis-frontend-deps"

mkdir -p "$DEPS_DIR"
cp "$ROOT/package.json" "$ROOT/package-lock.json" "$DEPS_DIR/"
(cd "$DEPS_DIR" && npm install)

rm -rf "$ROOT/node_modules"
ln -sf "$DEPS_DIR/node_modules" "$ROOT/node_modules"

echo "WSL deps ready. Run: npm run dev"
