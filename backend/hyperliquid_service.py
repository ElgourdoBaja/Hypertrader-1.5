import os
import json
import asyncio
import websockets
from typing import List, Dict, Optional, Any
from datetime import datetime, timedelta
from hyperliquid.info import Info
from hyperliquid.exchange import Exchange
from hyperliquid.utils import constants
import random
import uuid
import sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from models import (
    Portfolio, Position, Order, Trade, MarketData, 
    CandlestickData, OrderBook, OrderBookLevel, Account,
    OrderType, OrderSide, OrderStatus, StrategyStatus
)

class HyperliquidService:
    def __init__(self, wallet_address=None, api_key=None, api_secret=None, environment="testnet"):
        # Use provided credentials or get from environment
        self.wallet_address = wallet_address or os.getenv("HYPERLIQUID_WALLET_ADDRESS", "")
        self.api_key = api_key or os.getenv("HYPERLIQUID_API_KEY", "")
        self.api_secret = api_secret or os.getenv("HYPERLIQUID_API_SECRET", "")
        self.environment = environment or os.getenv("HYPERLIQUID_ENV", "testnet")
        
        # Check if we have the required credentials
        self.is_configured = bool(self.wallet_address and self.api_key and self.api_secret)
        
        if self.is_configured:
            try:
                self.base_url = (
                    "https://api.hyperliquid-testnet.xyz" if self.environment == "testnet" 
                    else "https://api.hyperliquid.xyz"
                )
                
                print(f"Hyperliquid service initialized:")
                print(f"- Environment: {self.environment}")
                print(f"- Target Wallet: {self.wallet_address}")
                
                # Initialize Info API (doesn't need private key)
                self.info = Info(self.base_url, skip_ws=True)
                
                # Initialize Exchange for trading (needs private key)
                # Note: We pass the private key, but we'll query using the target wallet address
                from eth_account import Account
                wallet_account = Account.from_key(self.api_secret)
                self.exchange = Exchange(wallet_account, self.base_url)
                
                print(f"- Exchange Wallet (from private key): {self.exchange.wallet.address}")
                print(f"- Target Query Wallet: {self.wallet_address}")
                print(f"- SDK Configured: {self.is_configured}")
                
            except Exception as e:
                print(f"Failed to initialize Hyperliquid SDK: {e}")
                self.is_configured = False
        else:
            print(f"Hyperliquid service not configured. Missing credentials: wallet={bool(self.wallet_address)}, key={bool(self.api_key)}, secret={bool(self.api_secret)}")
            self.info = None
            self.exchange = None
    
    def is_api_configured(self) -> bool:
        return self.is_configured
    
    async def get_portfolio(self) -> Portfolio:
        """Get user portfolio with positions and account value"""
        if not self.is_configured:
            return self._generate_mock_portfolio()
        
        try:
            print("Portfolio: Using real Hyperliquid API data")
            
            # Use the wallet address from settings, not derived from private key
            target_wallet = self.wallet_address
            print(f"Querying portfolio for wallet: {target_wallet}")
            
            # Get user state from Hyperliquid using the target wallet address
            user_state = self.info.user_state(target_wallet)
            
            # Debug: Print the raw user_state response
            print(f"Raw user_state response: {json.dumps(user_state, indent=2)}")
            
            portfolio = Portfolio(
                account_value=float(user_state.get("marginSummary", {}).get("accountValue", 0)),
                available_balance=float(user_state.get("withdrawable", 0)),
                margin_used=float(user_state.get("marginSummary", {}).get("totalMarginUsed", 0)),
                total_pnl=float(user_state.get("marginSummary", {}).get("totalRawUsd", 0))
            )
            
            # Convert positions
            positions = []
            for pos in user_state.get("assetPositions", []):
                if float(pos["position"]["szi"]) != 0:
                    position = Position(
                        coin=pos["position"]["coin"],
                        size=abs(float(pos["position"]["szi"])),
                        entry_price=float(pos["position"]["entryPx"]),
                        current_price=float(pos["position"]["positionValue"]) / abs(float(pos["position"]["szi"])),
                        unrealized_pnl=float(pos["position"]["unrealizedPnl"]),
                        side=OrderSide.BUY if float(pos["position"]["szi"]) > 0 else OrderSide.SELL
                    )
                    positions.append(position)
            
            portfolio.positions = positions
            
            print(f"Portfolio: Account Value ${portfolio.account_value}, Available ${portfolio.available_balance}, Positions: {len(positions)}")
            return portfolio
            
        except Exception as e:
            print(f"Error fetching real portfolio: {e}")
            print("Portfolio: Falling back to mock data")
            return self._generate_mock_portfolio()
    
    async def get_account_info(self) -> Account:
        """Get account information"""
        if not self.is_configured:
            print("Account: Using mock data - API not configured")
            return self._generate_mock_account()
        
        try:
            print("Account: Using real Hyperliquid API data")
            
            # Use the wallet address from settings, not derived from private key
            target_wallet = self.wallet_address
            print(f"Querying account info for wallet: {target_wallet}")
            
            user_state = self.info.user_state(target_wallet)
            
            # Debug: Print the raw user_state response
            print(f"Raw user_state response: {json.dumps(user_state, indent=2)}")
            
            # Get account value from marginSummary
            margin_summary = user_state.get("marginSummary", {})
            account_value = float(margin_summary.get("accountValue", 0))
            withdrawable = float(user_state.get("withdrawable", 0))
            
            # If perpetual account is empty, check spot balances using different API
            spot_balance = 0.0
            try:
                # Try to get spot token balances using the public API
                import requests
                
                spot_response = requests.post(
                    "https://api.hyperliquid.xyz/info",
                    json={"type": "spotClearinghouseState", "user": target_wallet},
                    headers={"Content-Type": "application/json"}
                )
                
                if spot_response.status_code == 200:
                    spot_data = spot_response.json()
                    print(f"Raw spot_clearinghouse response: {json.dumps(spot_data, indent=2)}")
                    
                    if "balances" in spot_data:
                        for balance in spot_data["balances"]:
                            if balance.get("coin") == "USDC":
                                total = float(balance.get("total", 0))
                                hold = float(balance.get("hold", 0))
                                spot_balance = total + hold
                                print(f"Found USDC spot balance: total={total}, hold={hold}, combined={spot_balance}")
                                break
                else:
                    print(f"Spot API response status: {spot_response.status_code}")
                    print(f"Spot API response: {spot_response.text}")
                    
            except Exception as e:
                print(f"Error fetching spot balances via API: {e}")
            
            # Use the higher of perp account value or spot balance
            total_account_value = max(account_value, spot_balance)
            total_withdrawable = max(withdrawable, spot_balance)
            
            account = Account(
                address=target_wallet,
                account_value=total_account_value,
                margin_summary=margin_summary,
                cross_margin_summary=user_state.get("crossMarginSummary", {}),
                withdrawable=total_withdrawable
            )
            
            print(f"Account: Address {account.address[:8]}..., Account Value: ${account.account_value}, Withdrawable: ${account.withdrawable}")
            print(f"Perp Account Value: ${account_value}, Spot Balance: ${spot_balance}")
            return account
            
        except Exception as e:
            print(f"Error fetching real account info: {e}")
            print("Account: Falling back to mock data")
            return self._generate_mock_account()
    
    async def get_market_data(self, coin: str) -> MarketData:
        """Get current market data for a coin from real Hyperliquid API"""
        try:
            # Always fetch real market data from Hyperliquid public API
            import requests
            
            # Get all mids (current prices)
            mids_response = requests.post(
                "https://api.hyperliquid.xyz/info",
                json={"type": "allMids"},
                headers={"Content-Type": "application/json"}
            )
            
            if mids_response.status_code == 200:
                all_mids = mids_response.json()
                
                # Get current price for the coin
                current_price = float(all_mids.get(coin, 0))
                
                if current_price > 0:
                    # Get 24h volume and other data
                    meta_response = requests.post(
                        "https://api.hyperliquid.xyz/info", 
                        json={"type": "meta"},
                        headers={"Content-Type": "application/json"}
                    )
                    
                    # Calculate approximate bid/ask spread (0.1% typical for major pairs)
                    spread = current_price * 0.001
                    bid = current_price - spread
                    ask = current_price + spread
                    
                    # Get 24h stats if available
                    stats_response = requests.post(
                        "https://api.hyperliquid.xyz/info",
                        json={"type": "spotMeta"},
                        headers={"Content-Type": "application/json"}
                    )
                    
                    # For now, we'll use approximate values for volume and change
                    # In a production system, you'd calculate these from historical data
                    volume_24h = current_price * 1000000  # Approximate volume
                    change_24h = 0.0  # Would need historical data to calculate
                    
                    return MarketData(
                        coin=coin,
                        price=current_price,
                        bid=bid,
                        ask=ask,
                        volume_24h=volume_24h,
                        change_24h=change_24h
                    )
            
            # If we can't get real data, return error
            raise Exception(f"Could not fetch real market data for {coin}")
            
        except Exception as e:
            print(f"Error fetching real market data for {coin}: {e}")
            raise Exception(f"Failed to fetch real market data: {str(e)}")
    
    async def get_candlestick_data(self, coin: str, interval: str = "1h", limit: int = 100) -> List[CandlestickData]:
        """Get real candlestick data for a coin from Hyperliquid API"""
        try:
            # Always fetch real candlestick data from Hyperliquid public API
            import requests
            from datetime import datetime, timedelta
            
            # Convert interval to Hyperliquid format
            interval_map = {
                "1m": "1m",
                "5m": "5m", 
                "15m": "15m",
                "1h": "1h",
                "4h": "4h",
                "1d": "1d"
            }
            
            hl_interval = interval_map.get(interval, "1h")
            
            # Get current time and calculate start time
            end_time = int(datetime.utcnow().timestamp() * 1000)
            
            # Calculate interval duration in milliseconds
            interval_ms = {
                "1m": 60 * 1000,
                "5m": 5 * 60 * 1000,
                "15m": 15 * 60 * 1000, 
                "1h": 60 * 60 * 1000,
                "4h": 4 * 60 * 60 * 1000,
                "1d": 24 * 60 * 60 * 1000
            }
            
            start_time = end_time - (limit * interval_ms.get(hl_interval, 60 * 60 * 1000))
            
            candles_response = requests.post(
                "https://api.hyperliquid.xyz/info",
                json={
                    "type": "candleSnapshot",
                    "req": {
                        "coin": coin,
                        "interval": hl_interval,
                        "startTime": start_time,
                        "endTime": end_time
                    }
                },
                headers={"Content-Type": "application/json"}
            )
            
            if candles_response.status_code == 200:
                candles_data = candles_response.json()
                
                candlesticks = []
                for candle in candles_data:
                    # Hyperliquid candle format: [timestamp, open, high, low, close, volume]
                    timestamp = datetime.fromtimestamp(candle["t"] / 1000)
                    
                    candlesticks.append(CandlestickData(
                        coin=coin,
                        timestamp=timestamp,
                        open=float(candle["o"]),
                        high=float(candle["h"]),
                        low=float(candle["l"]),
                        close=float(candle["c"]),
                        volume=float(candle.get("v", 0))
                    ))
                
                return candlesticks[-limit:] if candlesticks else []
            
            raise Exception(f"Could not fetch real candlestick data for {coin}")
            
        except Exception as e:
            print(f"Error fetching real candlestick data for {coin}: {e}")
            # For now, return empty list instead of mock data
            return []
    
    async def get_order_book(self, coin: str) -> OrderBook:
        """Get real order book for a coin from Hyperliquid API"""
        try:
            # Always fetch real order book data from Hyperliquid public API
            import requests
            
            orderbook_response = requests.post(
                "https://api.hyperliquid.xyz/info",
                json={"type": "l2Book", "coin": coin},
                headers={"Content-Type": "application/json"}
            )
            
            if orderbook_response.status_code == 200:
                l2_book = orderbook_response.json()
                
                bids = []
                asks = []
                
                # The levels array has two sub-arrays: [bids, asks]
                levels = l2_book.get("levels", [])
                if len(levels) >= 2:
                    # First array is bids (index 0)
                    for level in levels[0]:
                        price = float(level["px"])
                        size = float(level["sz"])
                        bids.append(OrderBookLevel(price=price, size=size))
                    
                    # Second array is asks (index 1)  
                    for level in levels[1]:
                        price = float(level["px"])
                        size = float(level["sz"])
                        asks.append(OrderBookLevel(price=price, size=size))
                
                # Sort bids (highest first) and asks (lowest first)
                bids.sort(key=lambda x: x.price, reverse=True)
                asks.sort(key=lambda x: x.price)
                
                return OrderBook(coin=coin, bids=bids[:20], asks=asks[:20])  # Limit to top 20 levels
            
            raise Exception(f"Could not fetch real order book for {coin}")
            
        except Exception as e:
            print(f"Error fetching real order book for {coin}: {e}")
            raise Exception(f"Failed to fetch real order book: {str(e)}")
    
    async def place_order(self, coin: str, is_buy: bool, size: float, price: Optional[float] = None, 
                         order_type: OrderType = OrderType.LIMIT, reduce_only: bool = False) -> Order:
        """Place a trading order"""
        if not self.is_configured:
            return self._generate_mock_order(coin, is_buy, size, price, order_type)
        
        try:
            print(f"Placing order: {coin}, buy={is_buy}, size={size}, price={price}, type={order_type}")
            
            # Import the correct OrderType from Hyperliquid SDK
            from hyperliquid.utils.signing import OrderType as HlOrderType
            
            # Convert our OrderType to Hyperliquid OrderType
            if order_type == OrderType.LIMIT:
                hl_order_type = HlOrderType(limit={"tif": "Gtc"})
            else:
                hl_order_type = HlOrderType(market={})
            
            # Use the correct method signature
            response = self.exchange.order(
                name=coin,
                is_buy=is_buy,
                sz=size,
                limit_px=price or 0.0,  # Hyperliquid requires a price even for market orders
                order_type=hl_order_type,
                reduce_only=reduce_only
            )
            
            print(f"Order response: {response}")
            
            if response.get("status") == "ok":
                response_data = response.get("response", {}).get("data", {})
                
                # Handle different response formats
                if "statuses" in response_data:
                    statuses = response_data["statuses"]
                    if len(statuses) > 0:
                        status = statuses[0]
                        
                        if "error" in status:
                            # Order was rejected
                            raise Exception(f"Order rejected: {status['error']}")
                        elif "filled" in status:
                            # Order was filled immediately
                            filled_data = status["filled"]
                            return Order(
                                oid=filled_data.get("oid"),
                                coin=coin,
                                side=OrderSide.BUY if is_buy else OrderSide.SELL,
                                size=size,
                                price=float(filled_data.get("avgPx", price or 0)),
                                order_type=order_type,
                                status=OrderStatus.FILLED,
                                filled_size=float(filled_data.get("totalSz", 0)),
                                remaining_size=0.0,
                                average_fill_price=float(filled_data.get("avgPx", 0)),
                                reduce_only=reduce_only
                            )
                        elif "resting" in status:
                            # Order is resting on the book
                            resting_data = status["resting"]
                            return Order(
                                oid=resting_data.get("oid"),
                                coin=coin,
                                side=OrderSide.BUY if is_buy else OrderSide.SELL,
                                size=size,
                                price=price,
                                order_type=order_type,
                                status=OrderStatus.PENDING,
                                filled_size=0.0,
                                remaining_size=size,
                                reduce_only=reduce_only
                            )
                
                # Fallback for other response formats
                return Order(
                    oid=response_data.get("oid"),
                    coin=coin,
                    side=OrderSide.BUY if is_buy else OrderSide.SELL,
                    size=size,
                    price=price,
                    order_type=order_type,
                    status=OrderStatus.PENDING,
                    remaining_size=size,
                    reduce_only=reduce_only
                )
            else:
                raise Exception(f"Order failed: {response}")
                
        except Exception as e:
            print(f"Error placing order: {e}")
            return self._generate_mock_order(coin, is_buy, size, price, order_type)
    
    async def cancel_order(self, coin: str, oid: int) -> bool:
        """Cancel an order"""
        if not self.is_configured:
            return True  # Mock success
        
        try:
            response = self.exchange.cancel(coin, oid)
            return response.get("status") == "ok"
            
        except Exception as e:
            print(f"Error cancelling order: {e}")
            return False
    
    async def get_open_orders(self) -> List[Order]:
        """Get all open orders"""
        if not self.is_configured:
            return self._generate_mock_orders(5)
        
        try:
            # Use the wallet address from settings
            target_wallet = self.wallet_address
            open_orders = self.info.open_orders(target_wallet)
            
            orders = []
            for order_data in open_orders:
                orders.append(Order(
                    oid=order_data.get("oid"),
                    coin=order_data.get("coin"),
                    side=OrderSide.BUY if order_data.get("side") == "B" else OrderSide.SELL,
                    size=float(order_data.get("sz", 0)),
                    price=float(order_data.get("limitPx", 0)),
                    order_type=OrderType.LIMIT,
                    status=OrderStatus.PENDING,
                    remaining_size=float(order_data.get("sz", 0))
                ))
            
            return orders
            
        except Exception as e:
            print(f"Error fetching open orders: {e}")
            return self._generate_mock_orders(5)
    
    async def get_order_history(self, limit: int = 50) -> List[Order]:
        """Get order history from real Hyperliquid API"""
        if not self.is_configured:
            return self._generate_mock_orders(limit)
        
        try:
            import requests
            
            # Get user fills (trade history) from Hyperliquid
            fills_response = requests.post(
                "https://api.hyperliquid.xyz/info",
                json={"type": "userFills", "user": self.wallet_address},
                headers={"Content-Type": "application/json"}
            )
            
            if fills_response.status_code == 200:
                fills_data = fills_response.json()
                
                orders = []
                for fill in fills_data[:limit]:
                    # Convert Hyperliquid fill to our Order format
                    orders.append(Order(
                        oid=fill.get("oid"),
                        coin=fill.get("coin"),
                        side=OrderSide.BUY if fill.get("side") == "B" else OrderSide.SELL,
                        size=float(fill.get("sz", 0)),
                        price=float(fill.get("px", 0)),
                        order_type=OrderType.LIMIT,  # Most fills are from limit orders
                        status=OrderStatus.FILLED,
                        filled_size=float(fill.get("sz", 0)),
                        remaining_size=0.0,
                        average_fill_price=float(fill.get("px", 0)),
                        created_at=datetime.fromtimestamp(fill.get("time", 0) / 1000),
                        updated_at=datetime.fromtimestamp(fill.get("time", 0) / 1000)
                    ))
                
                print(f"Fetched {len(orders)} fills from order history")
                return orders
            else:
                print(f"Failed to fetch order history: {fills_response.status_code}")
                return self._generate_mock_orders(limit)
            
        except Exception as e:
            print(f"Error fetching order history: {e}")
            return self._generate_mock_orders(limit)
    
    # Mock data generators
    def _generate_mock_portfolio(self) -> Portfolio:
        """Generate mock portfolio data"""
        positions = [
            Position(
                coin="BTC",
                size=0.5,
                entry_price=45000,
                current_price=46500,
                unrealized_pnl=750,
                side=OrderSide.BUY
            ),
            Position(
                coin="ETH",
                size=2.0,
                entry_price=3200,
                current_price=3150,
                unrealized_pnl=-100,
                side=OrderSide.BUY
            )
        ]
        
        return Portfolio(
            account_value=50000,
            available_balance=25000,
            margin_used=20000,
            total_pnl=1250,
            daily_pnl=350,
            positions=positions
        )
    
    def _generate_mock_account(self) -> Account:
        """Generate mock account data"""
        return Account(
            address="0x1234567890abcdef1234567890abcdef12345678",
            account_value=50000,
            margin_summary={
                "accountValue": 50000,
                "totalMarginUsed": 20000,
                "totalPnl": 1250
            },
            withdrawable=25000
        )
    
    def _generate_mock_market_data(self, coin: str) -> MarketData:
        """Generate mock market data"""
        base_prices = {"BTC": 45000, "ETH": 3200, "SOL": 100, "AVAX": 35}
        base_price = base_prices.get(coin, 100)
        
        current_price = base_price * random.uniform(0.95, 1.05)
        
        return MarketData(
            coin=coin,
            price=current_price,
            bid=current_price * 0.999,
            ask=current_price * 1.001,
            volume_24h=random.uniform(100000, 1000000),
            change_24h=random.uniform(-5, 5)
        )
    
    def _generate_mock_candlestick_data(self, coin: str, limit: int) -> List[CandlestickData]:
        """Generate mock candlestick data"""
        base_prices = {"BTC": 45000, "ETH": 3200, "SOL": 100, "AVAX": 35}
        base_price = base_prices.get(coin, 100)
        
        candles = []
        current_time = datetime.utcnow() - timedelta(hours=limit)
        current_price = base_price
        
        for i in range(limit):
            open_price = current_price
            close_price = open_price * random.uniform(0.98, 1.02)
            high_price = max(open_price, close_price) * random.uniform(1.0, 1.01)
            low_price = min(open_price, close_price) * random.uniform(0.99, 1.0)
            
            candles.append(CandlestickData(
                coin=coin,
                timestamp=current_time + timedelta(hours=i),
                open=open_price,
                high=high_price,
                low=low_price,
                close=close_price,
                volume=random.uniform(1000, 10000)
            ))
            
            current_price = close_price
        
        return candles
    
    def _generate_mock_order_book(self, coin: str) -> OrderBook:
        """Generate mock order book"""
        base_prices = {"BTC": 45000, "ETH": 3200, "SOL": 100, "AVAX": 35}
        base_price = base_prices.get(coin, 100)
        
        bids = []
        asks = []
        
        # Generate bids (descending price)
        for i in range(10):
            price = base_price * (1 - (i + 1) * 0.001)
            size = random.uniform(0.1, 5.0)
            bids.append(OrderBookLevel(price=price, size=size))
        
        # Generate asks (ascending price)
        for i in range(10):
            price = base_price * (1 + (i + 1) * 0.001)
            size = random.uniform(0.1, 5.0)
            asks.append(OrderBookLevel(price=price, size=size))
        
        return OrderBook(coin=coin, bids=bids, asks=asks)
    
    def _generate_mock_order(self, coin: str, is_buy: bool, size: float, 
                           price: Optional[float], order_type: OrderType) -> Order:
        """Generate mock order"""
        return Order(
            oid=random.randint(1000000, 9999999),
            coin=coin,
            side=OrderSide.BUY if is_buy else OrderSide.SELL,
            size=size,
            price=price,
            order_type=order_type,
            status=OrderStatus.PENDING,
            remaining_size=size
        )
    
    def _generate_mock_orders(self, count: int) -> List[Order]:
        """Generate mock orders"""
        coins = ["BTC", "ETH", "SOL", "AVAX"]
        orders = []
        
        for _ in range(count):
            coin = random.choice(coins)
            is_buy = random.choice([True, False])
            size = random.uniform(0.1, 2.0)
            price = random.uniform(100, 50000)
            
            orders.append(self._generate_mock_order(
                coin, is_buy, size, price, OrderType.LIMIT
            ))
        
        return orders

# Global service instance
hyperliquid_service = HyperliquidService()
