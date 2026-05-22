from .intraday.orb_15m import ORB15mStrategy
from .intraday.vwap_supertrend import VWAPSupertrendStrategy
from .intraday.ema_rsi import EMARSIStrategy
from .intraday.macd_zero import MACDZeroStrategy
from .intraday.inside_bar import InsideBarStrategy
from .swing.sma44_pullback import SMA44PullbackStrategy
from .swing.ema200_macd import EMA200MACDStrategy
from .swing.bb_squeeze import BBSqueezeStrategy
from .swing.rsi_divergence import RSIDivergenceStrategy
from .swing.golden_cross import GoldenCrossStrategy

STRATEGY_REGISTRY = {
    "15m_ORB": ORB15mStrategy(),
    "VWAP_Supertrend": VWAPSupertrendStrategy(),
    "EMA_RSI": EMARSIStrategy(),
    "MACD_Zero": MACDZeroStrategy(),
    "Inside_Bar": InsideBarStrategy(),
    "SMA44_Pullback": SMA44PullbackStrategy(),
    "EMA200_MACD": EMA200MACDStrategy(),
    "BB_Squeeze": BBSqueezeStrategy(),
    "RSI_Divergence": RSIDivergenceStrategy(),
    "Golden_Cross": GoldenCrossStrategy(),
}

STRATEGY_TIMEFRAMES = {
    "15m_ORB": "15m",
    "VWAP_Supertrend": "15m",
    "EMA_RSI": "5m",
    "MACD_Zero": "15m",
    "Inside_Bar": "15m",
    "SMA44_Pullback": "1D",
    "EMA200_MACD": "1D",
    "BB_Squeeze": "1D",
    "RSI_Divergence": "1D",
    "Golden_Cross": "1D",
}
