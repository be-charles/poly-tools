# Polymarket RTDS Crypto 15-Minute Window Logger

A Python script that connects to Polymarket's Real-Time Data Socket (RTDS) and logs data for 15-minute window crypto prediction markets.

## Features

✅ **Real-time Market Tracking**: Monitors BTC, ETH, XRP, and SOL 15-minute window markets
✅ **Automatic Market Detection**: Discovers new markets as they're created
✅ **CSV Logging**: Logs all data in CSV format for easy analysis
✅ **Crypto Price Tracking**: Records real-time crypto prices from Binance
✅ **Price-to-Beat Tracking**: Automatically tracks the baseline price for each window
✅ **Manual Price Override**: Set the first price-to-beat manually if needed
✅ **Local Filtering**: Uses local filtering instead of server-side (more reliable)
✅ **Auto-reconnect**: Automatically reconnects if connection is lost

## Installation

```bash
# Install dependencies
pip install -r requirements.txt

# Create configuration file
cp .env.example .env
```

## Configuration

The script uses a `.env` file for configuration. Copy `.env.example` to `.env` and customize:

```bash
cp .env.example .env
```

### Available Settings

**Price-to-Beat Settings** (most important):
```env
BTC_PRICE_TO_BEAT=95000.00
ETH_PRICE_TO_BEAT=3500.00
XRP_PRICE_TO_BEAT=0.65
SOL_PRICE_TO_BEAT=195.00
```

**General Settings**:
```env
CSV_FILENAME=polymarket_crypto_15m_log.csv
LOG_LEVEL=INFO
```

**WebSocket Settings**:
```env
WS_ENDPOINT=wss://ws-live-data.polymarket.com
PING_INTERVAL=5
```

**Market Settings**:
```env
SUPPORTED_SYMBOLS=btc,eth,xrp,sol
```

See `.env.example` for all available configuration options and detailed descriptions.

## Usage

### Basic Usage

Run the script to start logging all 15-minute crypto markets:

```bash
python polymarket_rtds_logger.py
```

The script will load configuration from `.env` automatically.

### Setting Manual Price-to-Beat

**Method 1: Using .env file (recommended)**

Edit your `.env` file:
```env
BTC_PRICE_TO_BEAT=95000.00
ETH_PRICE_TO_BEAT=3500.00
SOL_PRICE_TO_BEAT=195.00
```

Then run:
```bash
python polymarket_rtds_logger.py
```

**Method 2: Command-line arguments (overrides .env)**

```bash
# Set price-to-beat for specific coins
python polymarket_rtds_logger.py --price-to-beat "BTC:95000,ETH:3500,SOL:195"

# Or set for just one
python polymarket_rtds_logger.py --price-to-beat "BTC:95000"
```

### Debug Mode

**Method 1: Using .env file**
```env
LOG_LEVEL=DEBUG
```

**Method 2: Command-line argument (overrides .env)**
```bash
python polymarket_rtds_logger.py --debug
```

## How It Works

### Market Slug Format

The script detects 15-minute window markets by their slug format:

```
{symbol}-updown-15m-{timestamp}
```

Examples:
- `btc-updown-15m-1763013600`
- `eth-updown-15m-1763014200`
- `xrp-updown-15m-1763014800`
- `sol-updown-15m-1763015400`

### Data Flow

1. **Connection**: Connects to `wss://ws-live-data.polymarket.com`
2. **Subscription**: Subscribes to:
   - `activity/trades` - Market trade activity
   - `crypto_prices/update` - Real-time crypto prices from Binance
   - `clob_market/price_change` - Market price changes
3. **Discovery**: Queries Gamma API to find existing 15-minute markets
4. **Monitoring**:
   - Watches for new markets matching the pattern
   - Tracks Yes/No prices for each market
   - Records crypto prices at each update
   - Calculates price-to-beat (first crypto price in window)
5. **Logging**: Writes all data to CSV file

### CSV Output Format

The script creates `polymarket_crypto_15m_log.csv` with the following columns:

| Column | Description |
|--------|-------------|
| `timestamp` | When the data was logged |
| `symbol` | Crypto symbol (BTC, ETH, XRP, SOL) |
| `market_slug` | Full market slug |
| `window_start` | 15-minute window start time |
| `yes_price` | Current "Yes" (UP) price |
| `no_price` | Current "No" (DOWN) price |
| `crypto_price` | Current crypto price |
| `price_to_beat` | Baseline price for this window |
| `outcome` | Final outcome (UP/DOWN) once market closes |

### Example CSV Output

```csv
timestamp,symbol,market_slug,window_start,yes_price,no_price,crypto_price,price_to_beat,outcome
2025-11-13T10:15:23.456Z,BTC,btc-updown-15m-1763013600,2025-11-13T10:00:00,0.52,0.48,95123.45,95000.00,
2025-11-13T10:15:45.789Z,ETH,eth-updown-15m-1763013600,2025-11-13T10:00:00,0.48,0.52,3512.34,3500.00,
2025-11-13T10:16:12.345Z,BTC,btc-updown-15m-1763013600,2025-11-13T10:00:00,0.55,0.45,95234.56,95000.00,
```

## API Endpoints

The script uses:
- **RTDS WebSocket**: `wss://ws-live-data.polymarket.com`
- **Gamma Markets API**: `https://gamma-api.polymarket.com/markets`

## Supported Crypto Assets

- **BTC** - Bitcoin
- **ETH** - Ethereum
- **XRP** - Ripple
- **SOL** - Solana

## Local Filtering

The script implements **local filtering** instead of server-side filtering because server-side RTDS filtering can be unreliable. This means:

1. The script subscribes to all trade activity
2. It filters messages locally to only process 15-minute crypto markets
3. More reliable detection of new markets
4. No missed events due to filter issues

## Price-to-Beat Logic

The **price-to-beat** is the baseline crypto price at the start of the 15-minute window. The market predicts whether the crypto will be UP (above) or DOWN (below) this price at the end of the window.

### Automatic Tracking

When a new market is detected, the script:
1. Records the **first crypto price** it sees for that window
2. Uses this as the price-to-beat
3. Logs all subsequent prices relative to this baseline

### Manual Override

If you start the script after a window has begun:
1. The first price seen may not be the actual window start price
2. Set the correct baseline in your `.env` file (recommended):
   ```env
   BTC_PRICE_TO_BEAT=95000.00
   ```
3. Or use `--price-to-beat` command-line argument (overrides .env):
   ```bash
   python polymarket_rtds_logger.py --price-to-beat "BTC:95000"
   ```
4. The script will use your manual price for that symbol

### Configuration Priority

Settings are loaded in the following order (later overrides earlier):
1. Default values in the script
2. `.env` file settings
3. Command-line arguments (highest priority)

## Troubleshooting

### Connection Issues

If you see connection errors, the script will automatically retry every 5 seconds.

### Missing Crypto Prices

The script waits for crypto prices before logging market data. If you don't see logs immediately, wait a few seconds for the first price updates.

### Market Not Detected

If a new market isn't detected:
1. Check that the slug matches the pattern: `{symbol}-updown-15m-{timestamp}`
2. Enable `--debug` mode to see all incoming messages
3. Verify the market is open (not closed)

### Wrong Price-to-Beat

If the price-to-beat seems incorrect:
1. Stop the script
2. Check the actual window start price
3. Update your `.env` file:
   ```env
   BTC_PRICE_TO_BEAT=95000.00
   ```
4. Or restart with `--price-to-beat SYMBOL:PRICE` for a one-time override

## Example Output

```
2025-11-13 10:15:23 - INFO - 🚀 Starting Polymarket RTDS Logger
2025-11-13 10:15:23 - INFO - Tracking: BTC, ETH, XRP, SOL
2025-11-13 10:15:23 - INFO - Logging to: polymarket_crypto_15m_log.csv
2025-11-13 10:15:24 - INFO - ✅ Connected to wss://ws-live-data.polymarket.com
2025-11-13 10:15:24 - INFO - Subscribed to 3 topics
2025-11-13 10:15:25 - INFO - Now tracking market: btc-updown-15m-1763013600
2025-11-13 10:15:26 - INFO - Set price to beat for BTC (window 1763013600): 95000.00
2025-11-13 10:15:27 - INFO - 📊 BTC | Yes: 0.520 No: 0.480 | Price: $95123.45 | Beat: $95000.00
2025-11-13 10:15:45 - INFO - 🔔 Detected new 15m market: eth-updown-15m-1763014200
```

## Notes

- The script runs continuously until stopped with Ctrl+C
- All data is appended to the CSV file (existing data is preserved)
- Markets are tracked until the script is stopped
- Ping messages are sent every 5 seconds to keep the connection alive

## License

This is an independent tool and is not officially affiliated with Polymarket.
