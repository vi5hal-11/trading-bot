"""Real-time zone and trade invalidation checks."""
from datetime import datetime, timezone
from typing import Optional
from ifvg.models import IFVGZone, TradeState
from ifvg.ifvg_scanner import is_ifvg_expired, is_ifvg_invalidated


def check_zone_validity(
    ifvg: IFVGZone,
    candle_close: float,
    now: Optional[datetime] = None,
) -> Optional[str]:
    """Check all invalidation conditions for an IFVG zone.

    Returns a reason string if invalid, None if zone is still valid.
    Checks are ordered: expiry → body-close invalidation.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    if is_ifvg_expired(ifvg, now):
        return "EXPIRED"

    if is_ifvg_invalidated(ifvg, candle_close):
        return "BODY_CLOSE_THROUGH"

    return None


def check_pending_trade_validity(
    trade: TradeState,
    ifvg: IFVGZone,
    candle_close: float,
    now: Optional[datetime] = None,
) -> Optional[str]:
    """Check whether a pending trade (PENDING_A or PENDING_B) should be cancelled.

    Returns cancellation reason string if the trade should be cancelled, None if still valid.
    """
    if trade.status not in ("PENDING_A", "PENDING_B"):
        return None

    zone_reason = check_zone_validity(ifvg, candle_close, now)
    if zone_reason:
        return zone_reason

    return None


def should_cancel_entry(
    trade: TradeState,
    ifvg: IFVGZone,
    candle_close: float,
    now: Optional[datetime] = None,
) -> tuple[bool, str]:
    """Top-level check: should a pending entry be cancelled?

    Returns (should_cancel: bool, reason: str).
    """
    reason = check_pending_trade_validity(trade, ifvg, candle_close, now)
    if reason:
        return True, reason
    return False, ""
