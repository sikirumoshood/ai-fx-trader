from __future__ import annotations

import logging

from config.settings import RESEND_API_KEY, RESEND_FROM_EMAIL

log = logging.getLogger(__name__)


async def send_signal_email(signal, to_email: str) -> None:
    if not RESEND_API_KEY:
        log.warning("Resend not configured — skipping email alert")
        return

    import resend
    resend.api_key = RESEND_API_KEY

    direction  = signal.direction
    order_type = getattr(signal, "order_type", "MARKET")
    is_limit   = order_type == "LIMIT"
    color      = "#16a34a" if direction == "BUY" else "#dc2626"
    arrow      = "▲" if direction == "BUY" else "▼"
    label      = f"{direction} LIMIT ORDER" if is_limit else f"{direction} Signal"

    decimals  = 2 if "JPY" in signal.pair or "XAU" in signal.pair else 5
    ps        = 0.01 if "JPY" in signal.pair else (0.10 if "XAU" in signal.pair else 0.0001)
    pip_sl    = round(abs(signal.entry - signal.stop_loss) / ps, 1)
    pip_tp    = round(abs(signal.take_profit - signal.entry) / ps, 1)

    limit_row = f"""
          <tr><td style="padding:6px 0;color:#9ca3af">Order Type</td>
              <td style="padding:6px 0;text-align:right;font-weight:600;color:#f59e0b">LIMIT — awaiting fill</td></tr>
    """ if is_limit else ""

    html = f"""
    <div style="font-family:sans-serif;max-width:480px;margin:auto;border:1px solid #e5e7eb;border-radius:8px;overflow:hidden">
      <div style="background:{color};padding:16px 20px">
        <h2 style="margin:0;color:#fff;font-size:18px">{arrow} {label} — {signal.pair} {signal.timeframe}</h2>
      </div>
      <div style="padding:20px;background:#111827;color:#f9fafb">
        <table style="width:100%;border-collapse:collapse;font-size:14px">
          {limit_row}
          <tr><td style="padding:6px 0;color:#9ca3af">{"Limit Price" if is_limit else "Entry"}</td>
              <td style="padding:6px 0;text-align:right;font-weight:600">{signal.entry:.{decimals}f}</td></tr>
          <tr><td style="padding:6px 0;color:#9ca3af">Stop Loss</td>
              <td style="padding:6px 0;text-align:right;color:#dc2626;font-weight:600">{signal.stop_loss:.{decimals}f} &nbsp;(-{pip_sl} pips)</td></tr>
          <tr><td style="padding:6px 0;color:#9ca3af">Take Profit</td>
              <td style="padding:6px 0;text-align:right;color:#16a34a;font-weight:600">{signal.take_profit:.{decimals}f} &nbsp;(+{pip_tp} pips)</td></tr>
          <tr><td style="padding:6px 0;color:#9ca3af">Risk:Reward</td>
              <td style="padding:6px 0;text-align:right;font-weight:600">1:{signal.risk_reward}</td></tr>
          <tr><td style="padding:6px 0;color:#9ca3af">Confidence</td>
              <td style="padding:6px 0;text-align:right;font-weight:600">{signal.confidence:.0%}</td></tr>
        </table>
        <p style="margin:16px 0 0;font-size:12px;color:#6b7280;font-style:italic">{signal.reason}</p>
      </div>
    </div>
    """

    try:
        resend.Emails.send({
            "from":    RESEND_FROM_EMAIL,
            "to":      [to_email],
            "subject": f"{arrow} {label} {signal.pair} {signal.timeframe} — AI FX",
            "html":    html,
        })
        log.info("Email alert sent to %s for %s %s", to_email, signal.pair, direction)
    except Exception as exc:
        log.error("Email alert failed: %s", exc)
