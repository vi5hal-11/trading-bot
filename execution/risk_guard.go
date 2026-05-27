package main

import "fmt"

const (
	maxRiskPct      = 0.03  // 3% max price risk per trade
	maxPositionPct  = 0.10  // 10% max portfolio allocation
	minConfidence   = 0.10  // reject signals below this confidence
)

func ValidateOrder(order Order, portfolioBalance float64) error {
	if order.EntryPrice <= 0 || order.Quantity <= 0 {
		return fmt.Errorf("invalid order: entry_price=%.4f qty=%.6f", order.EntryPrice, order.Quantity)
	}
	if order.Side != "BUY" && order.Side != "SELL" {
		return fmt.Errorf("invalid side: %q", order.Side)
	}
	if order.Confidence < minConfidence {
		return fmt.Errorf("confidence too low: %.3f < %.3f", order.Confidence, minConfidence)
	}

	priceRisk := order.EntryPrice - order.StopLoss
	if order.Side == "SELL" {
		priceRisk = order.StopLoss - order.EntryPrice
	}
	riskPct := priceRisk / order.EntryPrice
	if riskPct <= 0 {
		return fmt.Errorf("stop-loss on wrong side: entry=%.2f sl=%.2f side=%s", order.EntryPrice, order.StopLoss, order.Side)
	}
	if riskPct > maxRiskPct {
		return fmt.Errorf("risk too high: %.2f%% > %.0f%% max", riskPct*100, maxRiskPct*100)
	}

	posValue := order.EntryPrice * order.Quantity
	if portfolioBalance > 0 && posValue > portfolioBalance*maxPositionPct {
		return fmt.Errorf("position too large: $%.2f > %.0f%% of $%.2f portfolio", posValue, maxPositionPct*100, portfolioBalance)
	}

	return nil
}
