# robinhood-mcp

A read-only MCP server for Robinhood portfolio research. Wraps [robin_stocks](https://github.com/jmfernandes/robin_stocks).

> **Research Tool Only** - This server provides read-only access for portfolio analysis and stock research. No trading functionality is exposed.

> **Unofficial** - This uses an unofficial API. Use at your own risk. See [robin_stocks disclaimer](https://github.com/jmfernandes/robin_stocks#disclaimer).

## Installation

```bash
pip install robinhood-mcp
```

Or with uvx:
```bash
uvx robinhood-mcp
```

## Configuration

Set environment variables:
```bash
export ROBINHOOD_USERNAME="your_email"
export ROBINHOOD_PASSWORD="your_password"
export ROBINHOOD_TOTP_SECRET="your_2fa_secret"  # Optional, for 2FA
```

### Getting your TOTP Secret

If you have 2FA enabled on Robinhood:

1. When setting up 2FA, Robinhood shows a QR code
2. Most authenticator apps let you view the secret key
3. The secret is a base32-encoded string (e.g., `JBSWY3DPEHPK3PXP`)
4. Set this as `ROBINHOOD_TOTP_SECRET`

### Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "robinhood": {
      "command": "uvx",
      "args": ["robinhood-mcp"],
      "env": {
        "ROBINHOOD_USERNAME": "your_email",
        "ROBINHOOD_PASSWORD": "your_password",
        "ROBINHOOD_TOTP_SECRET": "your_2fa_secret"
      }
    }
  }
}
```

### Claude Code

```bash
claude mcp add robinhood -- uvx robinhood-mcp
```

Then set environment variables in your shell or `.env` file.

## Available Tools

| Tool | Description |
|------|-------------|
| `robinhood_get_portfolio` | Get portfolio value, equity, and performance metrics |
| `robinhood_get_positions` | Get all current stock positions with P&L |
| `robinhood_get_watchlist` | Get stocks in a watchlist |
| `robinhood_get_quote` | Get real-time quote for a stock |
| `robinhood_get_fundamentals` | Get P/E ratio, market cap, dividend yield |
| `robinhood_get_historicals` | Get historical price data (OHLCV) |
| `robinhood_get_news` | Get recent news articles for a stock |
| `robinhood_get_earnings` | Get earnings dates and estimates |
| `robinhood_get_ratings` | Get analyst buy/hold/sell ratings |
| `robinhood_get_dividends` | Get dividend payment history |
| `robinhood_get_options_positions` | Get current options positions |
| `robinhood_search_symbols` | Search for stock symbols |

## Example Usage

Once configured, you can ask Claude:

- "What's my current portfolio value?"
- "Show me my positions and their performance"
- "Get the fundamentals for AAPL"
- "What's the historical data for TSLA over the past year?"
- "Show me analyst ratings for NVDA"

## Development

```bash
# Clone the repo
git clone https://github.com/verygoodplugins/robinhood-mcp.git
cd robinhood-mcp

# Install with dev dependencies
pip install -e ".[dev]"

# Run linting
ruff check .
ruff format --check .

# Run tests
pytest

# Run the server locally
robinhood-mcp
```

## Security Notes

- Credentials are only used locally to authenticate with Robinhood
- Session tokens are stored in `~/.tokens/robinhood.pickle` by robin_stocks
- Never commit your `.env` file
- Consider using a dedicated Robinhood account for API access

## License

MIT

## Disclaimer

This tool is for educational and research purposes only. It uses unofficial APIs that may break at any time. The authors are not responsible for any account restrictions or financial losses.

**Not affiliated with Robinhood Markets, Inc.**

## Links

- [Very Good Plugins](https://verygoodplugins.com/?utm_source=github)
- [robin_stocks Documentation](https://robin-stocks.readthedocs.io/)
- [MCP Protocol](https://modelcontextprotocol.io/)
