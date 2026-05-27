"""Pydantic models for all IFVG inter-module data structures."""
from datetime import datetime
from decimal import Decimal
from typing import Literal, Optional
from pydantic import BaseModel, model_validator


class Bias(BaseModel):
    direction: Literal["BULL", "BEAR", "NONE"]
    timestamp: datetime


class LiquidityPool(BaseModel):
    level: Decimal
    side: Literal["BSL", "SSL"]
    touch_count: int
    formed_at: datetime
    expires_at: datetime


class SweepEvent(BaseModel):
    symbol: str
    candle_timestamp: datetime
    sweep_extreme: Decimal
    pool_level: Decimal
    direction: Literal["BSL_SWEEP", "SSL_SWEEP"]
    extension_pct: float


class DisplacementEvent(BaseModel):
    candle_timestamp: datetime
    atr_ratio: float
    direction: Literal["BULL", "BEAR"]
    body_close: Decimal


class IFVGZone(BaseModel):
    symbol: str
    zone_high: Decimal
    zone_low: Decimal
    ce: Decimal
    direction: Literal["BULL", "BEAR"]
    formed_at: datetime
    expires_at: datetime
    width_pct: float

    @model_validator(mode="after")
    def zone_high_gt_low(self) -> "IFVGZone":
        if self.zone_high <= self.zone_low:
            raise ValueError(f"zone_high ({self.zone_high}) must be > zone_low ({self.zone_low})")
        return self


class ConfluenceScore(BaseModel):
    total: int
    breakdown: dict[str, bool]


class TradeState(BaseModel):
    symbol: str
    entry_price: Decimal
    sl_price: Decimal
    tp1_price: Decimal
    tp2_price: Decimal
    dol_level: Decimal
    position_size: Decimal
    risk_amount: Decimal
    status: Literal["PENDING_A", "PENDING_B", "OPEN", "CLOSED"]
    tp1_hit: bool = False
    entry_mode: Literal["LIMIT", "CONFIRM", "NONE"] = "NONE"
    opened_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    outcome: Optional[str] = None
    pnl_r: Optional[float] = None
    candles_since_entry: int = 0
