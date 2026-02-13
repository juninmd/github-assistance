#!/bin/bash
# Linting and type checking script
# Usage: ./scripts/lint.sh

set -e

echo "🔍 Running linter (ruff)..."
uv run ruff check src tests

echo ""
echo "✅ Linting passed!"

echo ""
echo "🔍 Running type checker (pyright)..."
uv run pyright

echo ""
echo "✅ Type checking passed!"

echo ""
echo "✅ All checks passed!"
