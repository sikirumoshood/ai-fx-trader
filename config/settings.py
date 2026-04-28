import os
from dotenv import load_dotenv

load_dotenv()

# ── MT5 ──────────────────────────────────────────────────────────────────────
MT5_LOGIN    = int(os.getenv("MT5_LOGIN", "0"))
MT5_PASSWORD = os.getenv("MT5_PASSWORD", "")
MT5_SERVER   = os.getenv("MT5_SERVER", "")
MT5_PATH     = os.getenv("MT5_PATH", "")          # path to terminal64.exe (Windows only)
MT5_HOST         = os.getenv("MT5_HOST", "localhost")  # mt5linux RPyC host (Docker)
MT5_PORT         = int(os.getenv("MT5_PORT", "8001"))  # mt5linux RPyC port (Docker)
MT5_BRIDGE_FILES = os.path.expanduser(os.getenv(
    "MT5_BRIDGE_FILES",
    "~/Library/Application Support/net.metaquotes.wine.metatrader5"
    "/drive_c/users/user/AppData/Roaming/MetaQuotes/Terminal/Common/Files",
))  # Shared folder between MT5 EA and Python (FILE_COMMON in MQL5)

# ── Kronos model ─────────────────────────────────────────────────────────────
MODEL_NAME      = os.getenv("MODEL_NAME", "kronos")          # kronos | moirai | tft
KRONOS_TOKENIZER = os.getenv("KRONOS_TOKENIZER", "NeoQuasar/Kronos-Tokenizer-base")
KRONOS_MODEL     = os.getenv("KRONOS_MODEL",     "NeoQuasar/Kronos-base")
KRONOS_DEVICE    = os.getenv("KRONOS_DEVICE",    "cpu")      # cpu | cuda:0
KRONOS_CONTEXT     = int(os.getenv("KRONOS_CONTEXT",   "512"))   # max context candles
KRONOS_PRED_LEN    = int(os.getenv("KRONOS_PRED_LEN",   "5"))     # candles to predict ahead
KRONOS_TEMPERATURE = float(os.getenv("KRONOS_TEMPERATURE", "1.0"))  # lower = more deterministic
KRONOS_SAMPLES     = int(os.getenv("KRONOS_SAMPLES",    "1"))     # samples averaged per call

# ── Signal defaults ───────────────────────────────────────────────────────────
DEFAULT_TIMEFRAME      = os.getenv("DEFAULT_TIMEFRAME", "H1")
DEFAULT_MIN_PIPS       = float(os.getenv("DEFAULT_MIN_PIPS", "15"))
DEFAULT_STOP_LOSS_PIPS = float(os.getenv("DEFAULT_STOP_LOSS_PIPS", "20"))
DEFAULT_RISK_REWARD    = float(os.getenv("DEFAULT_RISK_REWARD", "2.0"))
DEFAULT_RISK_PERCENT   = float(os.getenv("DEFAULT_RISK_PERCENT", "1.0"))
DEFAULT_MAX_SPREAD     = float(os.getenv("DEFAULT_MAX_SPREAD", "3.0"))   # pips
SIGNAL_EXPIRY_SECONDS  = int(os.getenv("SIGNAL_EXPIRY_SECONDS", "300"))  # 5 minutes
CONFIDENCE_THRESHOLD   = float(os.getenv("CONFIDENCE_THRESHOLD", "0.62"))

# ── Trading sessions (UTC) ────────────────────────────────────────────────────
SESSION_FILTERS = {
    "SYDNEY":  {"start": "21:00", "end": "06:00"},
    "TOKYO":   {"start": "00:00", "end": "09:00"},
    "LONDON":  {"start": "07:00", "end": "16:00"},
    "NEW_YORK":{"start": "12:00", "end": "21:00"},
}
ACTIVE_SESSIONS = os.getenv("ACTIVE_SESSIONS", "LONDON,NEW_YORK").split(",")

# ── News / FinBERT ────────────────────────────────────────────────────────────
FINBERT_MODEL         = os.getenv("FINBERT_MODEL", "ProsusAI/finbert")
NEWS_BLACKOUT_MINUTES = int(os.getenv("NEWS_BLACKOUT_MINUTES", "30"))

# ── Telegram ─────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")

# ── API ───────────────────────────────────────────────────────────────────────
FX_API_KEY  = os.getenv("FX_API_KEY", "change-me")
API_HOST    = os.getenv("API_HOST", "0.0.0.0")
API_PORT    = int(os.getenv("API_PORT", "8022"))
API_DEBUG   = os.getenv("API_DEBUG", "false").lower() == "true"
SCHEDULE_LOG_PATH = os.getenv("SCHEDULE_LOG_PATH", "logs/schedule-execution.log")

# ── Database ──────────────────────────────────────────────────────────────────
DATABASE_URL      = os.getenv("DATABASE_URL", "postgresql+asyncpg://fx:fx@localhost:5432/fxtrader")
DATABASE_URL_SYNC = os.getenv("DATABASE_URL_SYNC", "postgresql://fx:fx@localhost:5432/fxtrader")

# ── Supported pairs ───────────────────────────────────────────────────────────
SUPPORTED_PAIRS = [
    # Majors
    "EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD", "NZDUSD",
    # Minors
    "EURGBP", "EURJPY", "EURCHF", "EURCAD", "EURAUD", "EURNZD",
    "GBPJPY", "GBPCHF", "GBPCAD", "GBPAUD", "GBPNZD",
    "AUDJPY", "AUDCHF", "AUDCAD", "AUDNZD",
    "CADJPY", "CADCHF", "NZDJPY", "NZDCHF", "CHFJPY",
    # Exotics
    "USDZAR", "USDMXN", "USDNOK", "USDSEK", "USDDKK",
    "USDSGD", "USDHKD", "USDTRY",
]

# ── Pip sizes per pair ────────────────────────────────────────────────────────
# JPY pairs: 1 pip = 0.01; all others: 1 pip = 0.0001
def pip_size(pair: str) -> float:
    return 0.01 if "JPY" in pair else 0.0001
