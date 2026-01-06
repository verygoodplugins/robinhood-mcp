#!/usr/bin/env bash
# Smoke test: verify the MCP server can be imported and instantiated
set -euo pipefail

echo "Testing robinhood-mcp module import and server creation..."

# Test 1: Verify the module can be imported
python -c "from robinhood_mcp import server; print('✓ Module import successful')"

# Test 2: Verify the MCP server object can be created
python -c "from robinhood_mcp.server import mcp; print(f'✓ Server created: {mcp.name}')"

# Test 3: Verify the entry point exists
if command -v robinhood-mcp &>/dev/null; then
  echo "✓ Entry point 'robinhood-mcp' found"
else
  # Entry point might not be in PATH in CI, check with pip
  pip show robinhood-mcp &>/dev/null && echo "✓ Package installed" || {
    echo "✗ Package not installed"
    exit 1
  }
fi

echo "Smoke test passed!"
