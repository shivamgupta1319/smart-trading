from .intraday.orb_15m import ORB15mStrategy
from .intraday.vwap_supertrend import VWAPSupertrendStrategy
from .intraday.ema_rsi import EMARSIStrategy
from .intraday.macd_zero import MACDZeroStrategy
from .intraday.inside_bar import InsideBarStrategy
from .intraday.vwap_macd_rsi import VWAPMACDRSIStrategy
from .intraday.gap_and_go import GapAndGoStrategy
from .intraday.ema20_pullback import EMA20PullbackStrategy
from .intraday.cpr_breakout import CPRBreakoutStrategy
from .intraday.pdh_pdl_breakout import PDHPDLBreakoutStrategy
from .intraday.bb_mean_reversion_intraday import BBMeanReversionIntradayStrategy
from .swing.sma44_pullback import SMA44PullbackStrategy
from .swing.ema200_macd import EMA200MACDStrategy
from .swing.bb_squeeze import BBSqueezeStrategy
from .swing.rsi_divergence import RSIDivergenceStrategy
from .swing.golden_cross import GoldenCrossStrategy
from .swing.supertrend_ema import SuperTrendEMAStrategy
from .swing.bollinger_mean_reversion import BollingerMeanReversionStrategy
from .swing.macd_stoch_confluence import MacdStochConfluenceStrategy
from .swing.vcp import VCPStrategy
from .swing.episodic_pivot import EpisodicPivotStrategy
from .swing.break_and_retest import BreakAndRetestStrategy
from .swing.ema_10_50_cross import EMA1050CrossStrategy
from .swing.dma_20_pullback import DMA20PullbackStrategy
from .swing.fibonacci_golden_zone import FibonacciGoldenZoneStrategy
from .swing.mtf_alignment import MTFAlignmentStrategy
from .swing.channel_oscillation import ChannelOscillationStrategy
from .swing.volume_climax import VolumeClimaxStrategy

STRATEGY_REGISTRY = {
    "15m_ORB": ORB15mStrategy(),
    "VWAP_Supertrend": VWAPSupertrendStrategy(),
    "VWAP_MACD_RSI": VWAPMACDRSIStrategy(),
    "EMA_RSI": EMARSIStrategy(),
    "MACD_Zero": MACDZeroStrategy(),
    "Inside_Bar": InsideBarStrategy(),
    "Gap_And_Go": GapAndGoStrategy(),
    "EMA20_Pullback": EMA20PullbackStrategy(),
    "CPR_Breakout": CPRBreakoutStrategy(),
    "PDH_PDL_Breakout": PDHPDLBreakoutStrategy(),
    "BB_Mean_Reversion_Intraday": BBMeanReversionIntradayStrategy(),
    "SMA44_Pullback": SMA44PullbackStrategy(),
    "EMA200_MACD": EMA200MACDStrategy(),
    "BB_Squeeze": BBSqueezeStrategy(),
    "RSI_Divergence": RSIDivergenceStrategy(),
    "Golden_Cross": GoldenCrossStrategy(),
    "SuperTrend_EMA": SuperTrendEMAStrategy(),
    "Bollinger_Mean_Reversion": BollingerMeanReversionStrategy(),
    "MACD_Stoch_Confluence": MacdStochConfluenceStrategy(),
    "VCP": VCPStrategy(),
    "Episodic_Pivot": EpisodicPivotStrategy(),
    "Break_And_Retest": BreakAndRetestStrategy(),
    "EMA_10_50_Cross": EMA1050CrossStrategy(),
    "DMA20_Pullback": DMA20PullbackStrategy(),
    "Fibonacci_Golden_Zone": FibonacciGoldenZoneStrategy(),
    "MTF_Alignment": MTFAlignmentStrategy(),
    "Channel_Oscillation": ChannelOscillationStrategy(),
    "Volume_Climax": VolumeClimaxStrategy(),
}

STRATEGY_TIMEFRAMES = {
    "15m_ORB": "15m",
    "VWAP_Supertrend": "15m",
    "VWAP_MACD_RSI": "15m",
    "EMA_RSI": "5m",
    "MACD_Zero": "15m",
    "Inside_Bar": "15m",
    "Gap_And_Go": "5m",
    "EMA20_Pullback": "5m",
    "CPR_Breakout": "5m",
    "PDH_PDL_Breakout": "5m",
    "BB_Mean_Reversion_Intraday": "15m",
    "SMA44_Pullback": "1D",
    "EMA200_MACD": "1D",
    "BB_Squeeze": "1D",
    "RSI_Divergence": "1D",
    "Golden_Cross": "1D",
    "SuperTrend_EMA": "1D",
    "Bollinger_Mean_Reversion": "1D",
    "MACD_Stoch_Confluence": "1D",
    "VCP": "1D",
    "Episodic_Pivot": "1D",
    "Break_And_Retest": "1D",
    "EMA_10_50_Cross": "1D",
    "DMA20_Pullback": "1D",
    "Fibonacci_Golden_Zone": "1D",
    "MTF_Alignment": "1D",
    "Channel_Oscillation": "1D",
    "Volume_Climax": "1D",
}

# Hold duration classification for trade journal
# INTRADAY: Exit same day by 15:15 IST
# SHORT_SWING: 2-5 trading days
# MID_SWING: 1-4 weeks
# LONG_POSITIONAL: 1-6 months
STRATEGY_HOLD_DURATIONS = {
    "15m_ORB": "INTRADAY",
    "VWAP_Supertrend": "INTRADAY",
    "VWAP_MACD_RSI": "INTRADAY",
    "EMA_RSI": "INTRADAY",
    "MACD_Zero": "INTRADAY",
    "Inside_Bar": "INTRADAY",
    "Gap_And_Go": "INTRADAY",
    "EMA20_Pullback": "INTRADAY",
    "CPR_Breakout": "INTRADAY",
    "PDH_PDL_Breakout": "INTRADAY",
    "BB_Mean_Reversion_Intraday": "INTRADAY",
    "SMA44_Pullback": "SHORT_SWING",
    "EMA200_MACD": "SHORT_SWING",
    "SuperTrend_EMA": "SHORT_SWING",
    "DMA20_Pullback": "SHORT_SWING",
    "Break_And_Retest": "SHORT_SWING",
    "BB_Squeeze": "MID_SWING",
    "RSI_Divergence": "MID_SWING",
    "Bollinger_Mean_Reversion": "MID_SWING",
    "MACD_Stoch_Confluence": "MID_SWING",
    "VCP": "MID_SWING",
    "Episodic_Pivot": "MID_SWING",
    "Fibonacci_Golden_Zone": "MID_SWING",
    "Channel_Oscillation": "MID_SWING",
    "Volume_Climax": "MID_SWING",
    "Golden_Cross": "LONG_POSITIONAL",
    "EMA_10_50_Cross": "LONG_POSITIONAL",
    "MTF_Alignment": "LONG_POSITIONAL",
}

