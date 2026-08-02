from __future__ import annotations

import logging
import httpx

from config.settings import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

log = logging.getLogger(__name__)

_BASE = "https://api.telegram.org/bot{token}/sendMessage"


async def send_signal_alert(signal) -> None:
    """Send a trade signal alert to the configured Telegram chat."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        log.warning("Telegram not configured — skipping alert")
        return

    direction = signal.direction
    emoji = "🟢" if direction == "BUY" else "🔴"

    pip_sl  = round(abs(signal.entry - signal.stop_loss) / (0.01 if "JPY" in signal.pair else 0.0001), 1)
    pip_tp  = round(abs(signal.take_profit - signal.entry) / (0.01 if "JPY" in signal.pair else 0.0001), 1)
    news    = f"\nNews:       <b>{signal.news_bias}</b>" if signal.news_bias and signal.news_bias != "NEUTRAL" else ""

    text = (
        f"{emoji} <b>{direction} Signal — {signal.pair} {signal.timeframe}</b>\n"
        f"\n"
        f"Entry:      <b>{signal.entry}</b>\n"
        f"SL:         <b>{signal.stop_loss}</b>  (-{pip_sl} pips)\n"
        f"TP:         <b>{signal.take_profit}</b>  (+{pip_tp} pips)\n"
        f"RR:         <b>1:{signal.risk_reward}</b>\n"
        f"Confidence: <b>{signal.confidence:.0%}</b>"
        f"{news}\n"
        f"\n"
        f"<i>{signal.reason}</i>"
    )

    await _send(text)


async def send_backtest_alert(run_id: str, result: dict) -> None:
    """Send a backtest completion summary to the configured Telegram chat."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return

    total_pips = result.get("total_return", 0)
    pip_emoji  = "📈" if total_pips >= 0 else "📉"
    pip_str    = f"+{total_pips:.1f}" if total_pips > 0 else f"{total_pips:.1f}"

    text = (
        f"{pip_emoji} <b>Backtest Complete</b>\n"
        f"\n"
        f"Traded:        <b>{result.get('traded', 0)}</b> / {result.get('total_signals', 0)} signals\n"
        f"Win Rate:      <b>{result.get('win_rate', 0) * 100:.1f}%</b>\n"
        f"Total Pips:    <b>{pip_str}</b>\n"
        f"Profit Factor: <b>{result.get('profit_factor', 0):.2f}</b>\n"
        f"Max Drawdown:  <b>{result.get('max_drawdown', 0):.1f} pips</b>\n"
        f"Sharpe Ratio:  <b>{result.get('sharpe_ratio', 0):.2f}</b>\n"
        f"\n"
        f"<code>{run_id}</code>"
    )

    await _send(text)


async def _send(text: str) -> None:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                _BASE.format(token=TELEGRAM_BOT_TOKEN),
                json={
                    "chat_id":    TELEGRAM_CHAT_ID,
                    "text":       text,
                    "parse_mode": "HTML",
                },
            )
            resp.raise_for_status()
    except Exception:
        log.exception("Telegram alert failed")
