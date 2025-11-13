#!/usr/bin/env python3
"""
Polymarket RTDS Logger for 15-minute Crypto Markets

This script connects to Polymarket's Real-Time Data Socket (RTDS) and logs
data for 15-minute window crypto markets (BTC, ETH, XRP, SOL).

Features:
- Real-time market price tracking (Yes/No prices)
- Crypto price tracking from multiple sources
- Automatic detection of new 15-minute window markets
- CSV logging for data analysis
- Price-to-beat tracking with manual override option
"""

import asyncio
import websockets
import json
import csv
import time
import argparse
import logging
from datetime import datetime
from typing import Dict, Set, Optional
import aiohttp
from collections import defaultdict

# Configuration
WS_ENDPOINT = "wss://ws-live-data.polymarket.com"
GAMMA_API_BASE = "https://gamma-api.polymarket.com"
SUPPORTED_SYMBOLS = ["btc", "eth", "xrp", "sol"]
CSV_FILENAME = "polymarket_crypto_15m_log.csv"
PING_INTERVAL = 5  # seconds

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class PolymarketRTDSLogger:
    """Logger for Polymarket 15-minute crypto markets."""

    def __init__(self, manual_prices_to_beat: Optional[Dict[str, float]] = None):
        """
        Initialize the logger.

        Args:
            manual_prices_to_beat: Optional dict of {symbol: price} for manual price-to-beat settings
        """
        self.ws = None
        self.markets: Dict[str, Dict] = {}  # slug -> market data
        self.crypto_prices: Dict[str, float] = {}  # symbol -> current price
        self.prices_to_beat: Dict[str, Dict[int, float]] = defaultdict(dict)  # symbol -> {timestamp -> price}
        self.tracked_slugs: Set[str] = set()
        self.session = None
        self.manual_prices_to_beat = manual_prices_to_beat or {}

        # Initialize CSV file
        self._init_csv()

    def _init_csv(self):
        """Initialize the CSV file with headers."""
        try:
            with open(CSV_FILENAME, 'x', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([
                    'timestamp',
                    'symbol',
                    'market_slug',
                    'window_start',
                    'yes_price',
                    'no_price',
                    'crypto_price',
                    'price_to_beat',
                    'outcome'
                ])
            logger.info(f"Created new CSV file: {CSV_FILENAME}")
        except FileExistsError:
            logger.info(f"Using existing CSV file: {CSV_FILENAME}")

    def _log_to_csv(self, symbol: str, slug: str, window_start: int,
                    yes_price: float, no_price: float, crypto_price: float,
                    price_to_beat: Optional[float], outcome: str = ""):
        """Log a data point to CSV."""
        with open(CSV_FILENAME, 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                datetime.now().isoformat(),
                symbol.upper(),
                slug,
                datetime.fromtimestamp(window_start).isoformat(),
                yes_price,
                no_price,
                crypto_price,
                price_to_beat if price_to_beat else "",
                outcome
            ])

    async def _fetch_market_by_slug(self, slug: str) -> Optional[Dict]:
        """
        Fetch market details from Gamma API by slug.

        Args:
            slug: Market slug

        Returns:
            Market data or None if not found
        """
        try:
            if not self.session:
                self.session = aiohttp.ClientSession()

            url = f"{GAMMA_API_BASE}/markets"
            params = {"slug": slug}

            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    if data and len(data) > 0:
                        return data[0]
                    logger.warning(f"Market not found for slug: {slug}")
                else:
                    logger.error(f"Failed to fetch market {slug}: {response.status}")
        except Exception as e:
            logger.error(f"Error fetching market {slug}: {e}")

        return None

    def _extract_window_timestamp(self, slug: str) -> Optional[int]:
        """
        Extract window start timestamp from slug.

        Args:
            slug: Market slug in format {symbol}-updown-15m-{timestamp}

        Returns:
            Timestamp or None if invalid format
        """
        try:
            parts = slug.split('-')
            if len(parts) >= 4 and parts[1] == 'updown' and parts[2] == '15m':
                return int(parts[3])
        except (ValueError, IndexError):
            pass
        return None

    def _is_15m_crypto_market(self, slug: str) -> Optional[str]:
        """
        Check if slug matches 15-minute crypto market pattern.

        Args:
            slug: Market slug

        Returns:
            Symbol if match, None otherwise
        """
        for symbol in SUPPORTED_SYMBOLS:
            if slug.startswith(f"{symbol}-updown-15m-"):
                timestamp = self._extract_window_timestamp(slug)
                if timestamp:
                    return symbol
        return None

    async def _discover_existing_markets(self):
        """Discover existing 15-minute crypto markets."""
        try:
            if not self.session:
                self.session = aiohttp.ClientSession()

            url = f"{GAMMA_API_BASE}/markets"

            # Search for each crypto symbol
            for symbol in SUPPORTED_SYMBOLS:
                logger.info(f"Searching for existing {symbol.upper()} 15m markets...")

                async with self.session.get(url, params={"closed": "false"}) as response:
                    if response.status == 200:
                        data = await response.json()

                        for market in data:
                            slug = market.get("market_slug", "")
                            if self._is_15m_crypto_market(slug) == symbol:
                                await self._add_market(slug, market)

        except Exception as e:
            logger.error(f"Error discovering markets: {e}")

    async def _add_market(self, slug: str, market_data: Optional[Dict] = None):
        """
        Add a market to tracking.

        Args:
            slug: Market slug
            market_data: Optional pre-fetched market data
        """
        if slug in self.tracked_slugs:
            return

        symbol = self._is_15m_crypto_market(slug)
        if not symbol:
            return

        # Fetch market data if not provided
        if not market_data:
            market_data = await self._fetch_market_by_slug(slug)

        if not market_data:
            logger.warning(f"Could not fetch market data for {slug}")
            return

        self.markets[slug] = market_data
        self.tracked_slugs.add(slug)

        # Extract token IDs for price tracking
        tokens = market_data.get("clobTokenIds", [])
        if len(tokens) >= 2:
            self.markets[slug]["yes_token"] = tokens[0]
            self.markets[slug]["no_token"] = tokens[1]

        # Set price to beat if manually provided
        window_start = self._extract_window_timestamp(slug)
        if window_start and symbol in self.manual_prices_to_beat:
            self.prices_to_beat[symbol][window_start] = self.manual_prices_to_beat[symbol]
            logger.info(f"Set manual price to beat for {symbol.upper()}: {self.manual_prices_to_beat[symbol]}")

        logger.info(f"Now tracking market: {slug}")

    def _update_price_to_beat(self, symbol: str, window_start: int, current_price: float):
        """
        Update price-to-beat for a market.

        Args:
            symbol: Crypto symbol
            window_start: Window start timestamp
            current_price: Current crypto price
        """
        # Don't override if manually set or already set
        if window_start not in self.prices_to_beat[symbol]:
            self.prices_to_beat[symbol][window_start] = current_price
            logger.info(f"Set price to beat for {symbol.upper()} (window {window_start}): {current_price}")

    async def _handle_message(self, message: Dict):
        """
        Handle incoming WebSocket message.

        Args:
            message: Parsed JSON message
        """
        try:
            topic = message.get("topic")
            msg_type = message.get("type")
            payload = message.get("payload", {})

            if topic == "crypto_prices" and msg_type == "update":
                # Update crypto price
                symbol_raw = payload.get("symbol", "")
                # Convert "btcusdt" to "btc"
                symbol = symbol_raw.replace("usdt", "").lower()

                if symbol in SUPPORTED_SYMBOLS:
                    price = float(payload.get("value", 0))
                    self.crypto_prices[symbol] = price
                    logger.debug(f"{symbol.upper()} price: ${price:.2f}")

                    # Update prices to beat for active markets
                    for slug in self.tracked_slugs:
                        if slug.startswith(f"{symbol}-updown-15m-"):
                            window_start = self._extract_window_timestamp(slug)
                            if window_start:
                                self._update_price_to_beat(symbol, window_start, price)

            elif topic == "activity" and msg_type == "trades":
                # Handle trade updates
                slug = payload.get("slug", "")

                # Check if this is a new market
                if slug and slug not in self.tracked_slugs:
                    symbol = self._is_15m_crypto_market(slug)
                    if symbol:
                        logger.info(f"🔔 Detected new 15m market: {slug}")
                        await self._add_market(slug)

                # Log market data if we're tracking it
                if slug in self.markets:
                    await self._log_market_data(slug, payload)

            elif topic == "clob_market" and msg_type == "price_change":
                # Handle price updates from CLOB
                token_id = payload.get("asset_id", "")

                # Find matching market
                for slug, market in self.markets.items():
                    if token_id in [market.get("yes_token"), market.get("no_token")]:
                        await self._log_market_data(slug, payload)
                        break

        except Exception as e:
            logger.error(f"Error handling message: {e}")
            logger.debug(f"Message: {message}")

    async def _log_market_data(self, slug: str, payload: Dict):
        """
        Log market data to CSV.

        Args:
            slug: Market slug
            payload: Message payload
        """
        try:
            if slug not in self.markets:
                return

            market = self.markets[slug]
            symbol = self._is_15m_crypto_market(slug)
            if not symbol:
                return

            window_start = self._extract_window_timestamp(slug)
            if not window_start:
                return

            # Get crypto price
            crypto_price = self.crypto_prices.get(symbol, 0)
            if crypto_price == 0:
                return  # Wait until we have crypto price

            # Get price to beat
            price_to_beat = self.prices_to_beat.get(symbol, {}).get(window_start)

            # Extract Yes/No prices from payload
            yes_price = None
            no_price = None

            # Try to get prices from different message formats
            if "price" in payload:
                token_id = payload.get("asset_id", "")
                price = float(payload.get("price", 0))

                if token_id == market.get("yes_token"):
                    yes_price = price
                    no_price = 1 - price
                elif token_id == market.get("no_token"):
                    no_price = price
                    yes_price = 1 - price

            # If we couldn't extract prices from this message, skip
            if yes_price is None or no_price is None:
                return

            # Determine outcome if market has ended
            outcome = ""
            if price_to_beat and market.get("closed", False):
                outcome = "UP" if crypto_price > price_to_beat else "DOWN"

            # Log to CSV
            self._log_to_csv(
                symbol=symbol,
                slug=slug,
                window_start=window_start,
                yes_price=yes_price,
                no_price=no_price,
                crypto_price=crypto_price,
                price_to_beat=price_to_beat,
                outcome=outcome
            )

            logger.info(f"📊 {symbol.upper()} | Yes: {yes_price:.3f} No: {no_price:.3f} | "
                       f"Price: ${crypto_price:.2f} | Beat: ${price_to_beat:.2f if price_to_beat else 'N/A'}")

        except Exception as e:
            logger.error(f"Error logging market data: {e}")

    async def _send_ping(self):
        """Send periodic ping messages to keep connection alive."""
        while True:
            try:
                await asyncio.sleep(PING_INTERVAL)
                if self.ws and not self.ws.closed:
                    await self.ws.send(json.dumps({"type": "ping"}))
                    logger.debug("Sent ping")
            except Exception as e:
                logger.error(f"Error sending ping: {e}")
                break

    async def _subscribe(self):
        """Subscribe to relevant RTDS topics."""
        subscriptions = []

        # Subscribe to all activity/trades (we'll filter locally)
        subscriptions.append({
            "topic": "activity",
            "type": "trades"
        })

        # Subscribe to crypto prices for all supported symbols
        # Format: btcusdt, ethusdt, xrpusdt, solusdt
        crypto_symbols = [f"{s}usdt" for s in SUPPORTED_SYMBOLS]
        subscriptions.append({
            "topic": "crypto_prices",
            "type": "update",
            "filters": json.dumps({"symbol": ",".join(crypto_symbols)})
        })

        # Subscribe to CLOB market price changes for tracked markets
        # This provides more frequent price updates
        subscriptions.append({
            "topic": "clob_market",
            "type": "price_change"
        })

        message = {
            "action": "subscribe",
            "subscriptions": subscriptions
        }

        await self.ws.send(json.dumps(message))
        logger.info(f"Subscribed to {len(subscriptions)} topics")

    async def connect(self):
        """Connect to Polymarket RTDS and start logging."""
        logger.info("🚀 Starting Polymarket RTDS Logger")
        logger.info(f"Tracking: {', '.join(s.upper() for s in SUPPORTED_SYMBOLS)}")
        logger.info(f"Logging to: {CSV_FILENAME}")

        # Discover existing markets
        await self._discover_existing_markets()

        try:
            async with websockets.connect(WS_ENDPOINT) as ws:
                self.ws = ws
                logger.info(f"✅ Connected to {WS_ENDPOINT}")

                # Subscribe to topics
                await self._subscribe()

                # Start ping task
                ping_task = asyncio.create_task(self._send_ping())

                # Listen for messages
                try:
                    async for message_raw in ws:
                        try:
                            message = json.loads(message_raw)
                            await self._handle_message(message)
                        except json.JSONDecodeError:
                            logger.warning(f"Failed to parse message: {message_raw}")
                except websockets.exceptions.ConnectionClosed:
                    logger.warning("WebSocket connection closed")
                finally:
                    ping_task.cancel()

        except Exception as e:
            logger.error(f"Connection error: {e}")
        finally:
            if self.session:
                await self.session.close()

    async def run(self):
        """Run the logger with auto-reconnect."""
        while True:
            try:
                await self.connect()
            except Exception as e:
                logger.error(f"Fatal error: {e}")

            logger.info("Reconnecting in 5 seconds...")
            await asyncio.sleep(5)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Polymarket RTDS Logger for 15-minute crypto markets"
    )
    parser.add_argument(
        "--price-to-beat",
        type=str,
        help="Manually set price-to-beat in format: SYMBOL:PRICE,SYMBOL:PRICE (e.g., BTC:95000,ETH:3500)"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging"
    )

    args = parser.parse_args()

    # Set log level
    if args.debug:
        logger.setLevel(logging.DEBUG)

    # Parse manual prices to beat
    manual_prices = {}
    if args.price_to_beat:
        try:
            for pair in args.price_to_beat.split(','):
                symbol, price = pair.split(':')
                manual_prices[symbol.lower().strip()] = float(price)
            logger.info(f"Manual prices to beat: {manual_prices}")
        except ValueError:
            logger.error("Invalid price-to-beat format. Use: SYMBOL:PRICE,SYMBOL:PRICE")
            return

    # Create and run logger
    logger_instance = PolymarketRTDSLogger(manual_prices_to_beat=manual_prices)

    try:
        asyncio.run(logger_instance.run())
    except KeyboardInterrupt:
        logger.info("\n👋 Shutting down gracefully...")


if __name__ == "__main__":
    main()
