import os
import json
from datetime import datetime, timedelta
import requests
import time
import logging
import numpy as np
from typing import Optional, Dict, List, Tuple
import hashlib
import hmac

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('trading_bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


class TradingBot:
    """
    Cryptocurrency Trading Bot with technical analysis and automated trading
    Supports multiple exchanges and trading strategies
    """
    
    # Binance API endpoints
    BINANCE_API_URL = "https://api.binance.com/api/v3"
    BINANCE_WS_URL = "wss://stream.binance.com:9443/ws"
    
    def __init__(self, api_key: str, api_secret: str, trading_pair: str = "BTCUSDT",
                 strategy: str = "ma_crossover", initial_balance: float = 1000):
        """
        Initialize Trading Bot
        
        Args:
            api_key: Exchange API key
            api_secret: Exchange API secret
            trading_pair: Trading pair (e.g., BTCUSDT)
            strategy: Trading strategy to use
            initial_balance: Initial account balance for backtesting
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.trading_pair = trading_pair
        self.strategy = strategy
        self.initial_balance = initial_balance
        
        # Trading state
        self.position = None
        self.entry_price = None
        self.entry_time = None
        self.current_balance = initial_balance
        self.trade_history = []
        self.price_history = []
        
        # Technical analysis parameters
        self.short_window = 20  # Short MA period
        self.long_window = 50   # Long MA period
        self.rsi_period = 14
        self.rsi_upper = 70
        self.rsi_lower = 30
        
        # Risk management
        self.stop_loss_pct = 2.0
        self.take_profit_pct = 5.0
        self.max_position_size = 0.1  # Max 10% of balance per trade
        
        logger.info(f"Trading Bot initialized - Pair: {trading_pair}, Strategy: {strategy}")
    
    def get_current_price(self) -> Optional[float]:
        """
        Fetch current price from Binance API
        
        Returns:
            Current price or None if error
        """
        try:
            endpoint = f"{self.BINANCE_API_URL}/ticker/price"
            params = {"symbol": self.trading_pair}
            
            response = requests.get(endpoint, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            price = float(data['price'])
            logger.debug(f"Current {self.trading_pair} price: ${price}")
            return price
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching current price: {e}")
            return None
    
    def get_historical_prices(self, interval: str = "1h", limit: int = 100) -> List[float]:
        """
        Fetch historical price data from Binance
        
        Args:
            interval: Candlestick interval (1m, 5m, 1h, 1d, etc.)
            limit: Number of candles to fetch
            
        Returns:
            List of closing prices
        """
        try:
            endpoint = f"{self.BINANCE_API_URL}/klines"
            params = {
                "symbol": self.trading_pair,
                "interval": interval,
                "limit": limit
            }
            
            response = requests.get(endpoint, params=params, timeout=10)
            response.raise_for_status()
            
            klines = response.json()
            prices = [float(kline[4]) for kline in klines]  # Close price is index 4
            logger.debug(f"Fetched {len(prices)} historical prices")
            return prices
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching historical prices: {e}")
            return []
    
    def calculate_sma(self, prices: List[float], period: int) -> List[float]:
        """
        Calculate Simple Moving Average
        
        Args:
            prices: List of prices
            period: MA period
            
        Returns:
            List of SMA values
        """
        if len(prices) < period:
            return []
        return [np.mean(prices[i:i+period]) for i in range(len(prices)-period+1)]
    
    def calculate_rsi(self, prices: List[float], period: int = 14) -> Optional[float]:
        """
        Calculate Relative Strength Index
        
        Args:
            prices: List of prices
            period: RSI period
            
        Returns:
            RSI value (0-100) or None
        """
        if len(prices) < period + 1:
            return None
        
        deltas = np.diff(prices)
        seed = deltas[:period+1]
        
        up = seed[seed >= 0].sum() / period
        down = -seed[seed < 0].sum() / period
        
        rs = up / down if down != 0 else 0
        rsi = 100 - 100 / (1 + rs)
        
        return rsi
    
    def calculate_macd(self, prices: List[float]) -> Dict[str, Optional[float]]:
        """
        Calculate MACD (Moving Average Convergence Divergence)
        
        Args:
            prices: List of prices
            
        Returns:
            Dictionary with MACD, Signal, and Histogram
        """
        if len(prices) < 26:
            return {"macd": None, "signal": None, "histogram": None}
        
        ema12 = self._calculate_ema(prices, 12)
        ema26 = self._calculate_ema(prices, 26)
        
        if ema12 is None or ema26 is None:
            return {"macd": None, "signal": None, "histogram": None}
        
        macd = ema12 - ema26
        signal = self._calculate_ema([macd], 9)
        signal = signal if signal is not None else macd
        histogram = macd - signal
        
        return {
            "macd": macd,
            "signal": signal,
            "histogram": histogram
        }
    
    def _calculate_ema(self, prices: List[float], period: int) -> Optional[float]:
        """Calculate Exponential Moving Average"""
        if len(prices) < period:
            return None
        
        multiplier = 2 / (period + 1)
        ema = np.mean(prices[:period])
        
        for price in prices[period:]:
            ema = price * multiplier + ema * (1 - multiplier)
        
        return ema
    
    def calculate_indicators(self, prices: List[float]) -> Dict:
        """
        Calculate all technical indicators
        
        Args:
            prices: List of closing prices
            
        Returns:
            Dictionary with all indicators
        """
        if len(prices) < self.long_window:
            logger.warning("Not enough price data for indicators")
            return {}
        
        sma_short = self.calculate_sma(prices, self.short_window)
        sma_long = self.calculate_sma(prices, self.long_window)
        rsi = self.calculate_rsi(prices, self.rsi_period)
        macd_data = self.calculate_macd(prices)
        
        indicators = {
            "sma_short": sma_short[-1] if sma_short else None,
            "sma_long": sma_long[-1] if sma_long else None,
            "rsi": rsi,
            "macd": macd_data,
            "current_price": prices[-1]
        }
        
        logger.debug(f"Indicators - SMA20: {indicators['sma_short']:.2f}, "
                    f"SMA50: {indicators['sma_long']:.2f}, RSI: {indicators['rsi']:.2f}")
        
        return indicators
    
    def generate_signal(self, indicators: Dict) -> str:
        """
        Generate trading signal based on indicators
        
        Args:
            indicators: Dictionary with calculated indicators
            
        Returns:
            Signal: 'BUY', 'SELL', or 'HOLD'
        """
        if not indicators or any(v is None for v in indicators.values() if v != indicators.get('macd')):
            return 'HOLD'
        
        sma_short = indicators.get('sma_short')
        sma_long = indicators.get('sma_long')
        rsi = indicators.get('rsi')
        macd_data = indicators.get('macd', {})
        
        signal = 'HOLD'
        
        if self.strategy == 'ma_crossover':
            # Golden Cross: Short MA crosses above Long MA (bullish)
            if sma_short and sma_long and sma_short > sma_long and not self.position:
                signal = 'BUY'
            # Death Cross: Short MA crosses below Long MA (bearish)
            elif sma_short and sma_long and sma_short < sma_long and self.position == 'LONG':
                signal = 'SELL'
        
        elif self.strategy == 'rsi':
            # RSI below 30: Oversold (potential buy)
            if rsi and rsi < self.rsi_lower and not self.position:
                signal = 'BUY'
            # RSI above 70: Overbought (potential sell)
            elif rsi and rsi > self.rsi_upper and self.position == 'LONG':
                signal = 'SELL'
        
        elif self.strategy == 'macd':
            # MACD histogram positive and increasing (bullish)
            if (macd_data.get('histogram') is not None and macd_data.get('histogram') > 0 
                and macd_data.get('macd') and macd_data.get('signal') and 
                macd_data.get('macd') > macd_data.get('signal') and not self.position):
                signal = 'BUY'
            # MACD histogram negative and decreasing (bearish)
            elif (macd_data.get('histogram') is not None and macd_data.get('histogram') < 0 
                  and self.position == 'LONG'):
                signal = 'SELL'
        
        elif self.strategy == 'combined':
            # Combined strategy: All indicators align
            sma_bullish = sma_short and sma_long and sma_short > sma_long
            rsi_bullish = rsi and rsi < self.rsi_lower
            macd_bullish = (macd_data.get('histogram') is not None and 
                           macd_data.get('histogram') > 0)
            
            if sma_bullish and rsi_bullish and macd_bullish and not self.position:
                signal = 'BUY'
            elif not sma_bullish and self.position == 'LONG':
                signal = 'SELL'
        
        logger.info(f"Signal generated: {signal}")
        return signal
    
    def _generate_signature(self, query_string: str) -> str:
        """Generate HMAC SHA256 signature for Binance API"""
        return hmac.new(
            self.api_secret.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
    
    def execute_trade(self, signal: str, current_price: float) -> bool:
        """
        Execute trade based on signal
        
        Args:
            signal: Trading signal (BUY, SELL, HOLD)
            current_price: Current market price
            
        Returns:
            True if trade executed, False otherwise
        """
        if signal == 'HOLD':
            return False
        
        try:
            if signal == 'BUY' and not self.position:
                return self._execute_buy(current_price)
            elif signal == 'SELL' and self.position == 'LONG':
                return self._execute_sell(current_price)
            
            # Check stop loss and take profit
            if self.position == 'LONG' and self.entry_price:
                price_change_pct = ((current_price - self.entry_price) / self.entry_price) * 100
                
                if price_change_pct <= -self.stop_loss_pct:
                    logger.warning(f"Stop loss triggered: {price_change_pct:.2f}%")
                    return self._execute_sell(current_price)
                elif price_change_pct >= self.take_profit_pct:
                    logger.info(f"Take profit triggered: {price_change_pct:.2f}%")
                    return self._execute_sell(current_price)
            
            return False
        except Exception as e:
            logger.error(f"Error executing trade: {e}")
            return False
    
    def _execute_buy(self, price: float) -> bool:
        """Execute buy order"""
        try:
            # Calculate position size
            trade_amount = self.current_balance * self.max_position_size
            quantity = trade_amount / price
            
            logger.info(f"BUY Signal - Price: ${price:.2f}, Quantity: {quantity:.8f}")
            
            # In real trading, this would place an actual order
            # For now, we simulate it
            self.position = 'LONG'
            self.entry_price = price
            self.entry_time = datetime.now()
            self.current_balance -= trade_amount
            
            trade_record = {
                'type': 'BUY',
                'price': price,
                'quantity': quantity,
                'amount': trade_amount,
                'timestamp': self.entry_time.isoformat(),
                'balance_after': self.current_balance
            }
            self.trade_history.append(trade_record)
            logger.info(f"Buy executed at ${price:.2f}")
            return True
        except Exception as e:
            logger.error(f"Error executing buy: {e}")
            return False
    
    def _execute_sell(self, price: float) -> bool:
        """Execute sell order"""
        try:
            if not self.entry_price:
                return False
            
            trade_amount = self.current_balance + (self.current_balance / 
                          (self.current_balance / (self.max_position_size)))
            profit_loss = (price - self.entry_price) * (trade_amount / self.entry_price)
            profit_loss_pct = (profit_loss / (self.initial_balance * self.max_position_size)) * 100
            
            logger.info(f"SELL Signal - Price: ${price:.2f}, P&L: ${profit_loss:.2f} ({profit_loss_pct:.2f}%)")
            
            # Update balance
            self.current_balance += trade_amount + profit_loss
            
            trade_record = {
                'type': 'SELL',
                'price': price,
                'entry_price': self.entry_price,
                'profit_loss': profit_loss,
                'profit_loss_pct': profit_loss_pct,
                'timestamp': datetime.now().isoformat(),
                'balance_after': self.current_balance,
                'duration': (datetime.now() - self.entry_time).total_seconds() / 60  # minutes
            }
            self.trade_history.append(trade_record)
            
            # Reset position
            self.position = None
            self.entry_price = None
            self.entry_time = None
            
            logger.info(f"Sell executed at ${price:.2f}, P&L: ${profit_loss:.2f}")
            return True
        except Exception as e:
            logger.error(f"Error executing sell: {e}")
            return False
    
    def get_account_balance(self) -> Optional[Dict]:
        """Fetch account balance from exchange"""
        try:
            # This would connect to the real API
            # For now, return simulated data
            return {
                'total': self.current_balance,
                'available': self.current_balance,
                'in_order': 0
            }
        except Exception as e:
            logger.error(f"Error fetching account balance: {e}")
            return None
    
    def get_performance_stats(self) -> Dict:
        """Calculate bot performance statistics"""
        if not self.trade_history:
            return {
                'total_trades': 0,
                'winning_trades': 0,
                'losing_trades': 0,
                'win_rate': 0,
                'total_profit_loss': 0,
                'total_profit_loss_pct': 0,
                'avg_profit_per_trade': 0
            }
        
        sell_trades = [t for t in self.trade_history if t['type'] == 'SELL']
        winning = [t for t in sell_trades if t['profit_loss'] > 0]
        losing = [t for t in sell_trades if t['profit_loss'] <= 0]
        
        total_pl = sum(t.get('profit_loss', 0) for t in sell_trades)
        win_rate = (len(winning) / len(sell_trades) * 100) if sell_trades else 0
        
        return {
            'total_trades': len(self.trade_history),
            'buy_trades': len([t for t in self.trade_history if t['type'] == 'BUY']),
            'sell_trades': len(sell_trades),
            'winning_trades': len(winning),
            'losing_trades': len(losing),
            'win_rate': win_rate,
            'total_profit_loss': total_pl,
            'total_profit_loss_pct': (total_pl / self.initial_balance) * 100,
            'avg_profit_per_trade': total_pl / len(sell_trades) if sell_trades else 0,
            'current_balance': self.current_balance
        }
    
    def print_performance_report(self):
        """Print detailed performance report"""
        stats = self.get_performance_stats()
        logger.info("=" * 60)
        logger.info("TRADING BOT PERFORMANCE REPORT")
        logger.info("=" * 60)
        logger.info(f"Total Trades: {stats['total_trades']}")
        logger.info(f"Buy Orders: {stats['buy_trades']} | Sell Orders: {stats['sell_trades']}")
        logger.info(f"Winning Trades: {stats['winning_trades']} | Losing Trades: {stats['losing_trades']}")
        logger.info(f"Win Rate: {stats['win_rate']:.2f}%")
        logger.info(f"Total P&L: ${stats['total_profit_loss']:.2f} ({stats['total_profit_loss_pct']:.2f}%)")
        logger.info(f"Avg Profit/Trade: ${stats['avg_profit_per_trade']:.2f}")
        logger.info(f"Current Balance: ${stats['current_balance']:.2f}")
        logger.info("=" * 60)
    
    def run(self, interval: int = 60, historical_interval: str = "1h"):
        """
        Main bot loop
        
        Args:
            interval: Seconds between checks
            historical_interval: Candlestick interval for analysis
        """
        logger.info(f"Starting Trading Bot - Interval: {interval}s, Strategy: {self.strategy}")
        
        try:
            while True:
                # Fetch price data
                prices = self.get_historical_prices(interval=historical_interval, limit=100)
                if not prices:
                    logger.warning("Failed to fetch prices, retrying...")
                    time.sleep(interval)
                    continue
                
                current_price = prices[-1]
                
                # Calculate indicators and generate signal
                indicators = self.calculate_indicators(prices)
                signal = self.generate_signal(indicators)
                
                # Execute trade
                self.execute_trade(signal, current_price)
                
                # Log current state
                logger.info(f"Position: {self.position or 'NONE'} | "
                           f"Balance: ${self.current_balance:.2f} | "
                           f"Price: ${current_price:.2f}")
                
                time.sleep(interval)
        except KeyboardInterrupt:
            logger.info("Bot stopped by user")
            self.print_performance_report()
        except Exception as e:
            logger.error(f"Fatal error in main loop: {e}")
            self.print_performance_report()


def main():
    """Main entry point"""
    api_key = os.getenv("BINANCE_API_KEY", "your_api_key")
    api_secret = os.getenv("BINANCE_API_SECRET", "your_api_secret")
    
    # Initialize bot
    bot = TradingBot(
        api_key=api_key,
        api_secret=api_secret,
        trading_pair="BTCUSDT",
        strategy="ma_crossover",  # Options: 'ma_crossover', 'rsi', 'macd', 'combined'
        initial_balance=1000
    )
    
    # Run the bot
    bot.run(interval=60, historical_interval="1h")


if __name__ == "__main__":
    main()
