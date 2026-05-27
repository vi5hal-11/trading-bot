package main

import (
	"context"
	"log/slog"
	"strings"
	"sync"
	"time"
)

type ManagedPosition struct {
	Symbol     string
	Side       string
	EntryPrice float64
	Quantity   float64
	StopLoss   float64
	TakeProfit float64
	OrderId    string
	OpenedAt   time.Time
	Strategy   string
}

type OrderManager struct {
	client    *BlofinClient
	positions map[string]*ManagedPosition // keyed by symbol
	mu        sync.RWMutex
}

func NewOrderManager(client *BlofinClient) *OrderManager {
	return &OrderManager{
		client:    client,
		positions: make(map[string]*ManagedPosition),
	}
}

func (m *OrderManager) OpenPosition(ctx context.Context, order Order) error {
	m.mu.Lock()
	defer m.mu.Unlock()

	if _, exists := m.positions[order.Symbol]; exists {
		slog.Warn("position already open, skipping", "symbol", order.Symbol)
		return nil
	}

	result, err := m.client.PlaceOrder(ctx, order.Symbol, order.Side, order.Quantity, order.EntryPrice, order.StopLoss)
	if err != nil {
		return err
	}

	m.positions[order.Symbol] = &ManagedPosition{
		Symbol:     order.Symbol,
		Side:       order.Side,
		EntryPrice: order.EntryPrice,
		Quantity:   order.Quantity,
		StopLoss:   order.StopLoss,
		TakeProfit: order.TakeProfit,
		OrderId:    result.OrderId,
		OpenedAt:   time.Now(),
		Strategy:   order.Strategy,
	}

	slog.Info("position opened",
		"symbol", order.Symbol,
		"side", order.Side,
		"qty", order.Quantity,
		"entry", order.EntryPrice,
		"sl", order.StopLoss,
		"tp", order.TakeProfit,
		"order_id", result.OrderId,
		"strategy", order.Strategy,
	)
	return nil
}

func (m *OrderManager) PollPositions(ctx context.Context) error {
	livePositions, err := m.client.GetPositions(ctx)
	if err != nil {
		return err
	}

	// Build set of currently open instIds on exchange
	openOnExchange := make(map[string]bool)
	for _, p := range livePositions {
		if p.Pos != 0 {
			openOnExchange[p.InstId] = true
		}
	}

	m.mu.Lock()
	defer m.mu.Unlock()

	for symbol, pos := range m.positions {
		instId := blofinSymbol(symbol)
		if !openOnExchange[instId] {
			slog.Info("position closed on exchange",
				"symbol", symbol,
				"side", pos.Side,
				"entry", pos.EntryPrice,
				"duration", time.Since(pos.OpenedAt).Round(time.Second),
				"strategy", pos.Strategy,
			)
			delete(m.positions, symbol)
		}
	}
	return nil
}

func (m *OrderManager) ClosePosition(ctx context.Context, symbol, reason string) error {
	m.mu.Lock()
	pos, exists := m.positions[symbol]
	if !exists {
		m.mu.Unlock()
		return nil
	}
	m.mu.Unlock()

	// Flip side to close
	closeSide := "SELL"
	if strings.ToUpper(pos.Side) == "SELL" {
		closeSide = "BUY"
	}

	_, err := m.client.PlaceOrder(ctx, symbol, closeSide, pos.Quantity, 0, 0)
	if err != nil {
		return err
	}

	m.mu.Lock()
	delete(m.positions, symbol)
	m.mu.Unlock()

	slog.Info("position closed manually",
		"symbol", symbol,
		"reason", reason,
		"duration", time.Since(pos.OpenedAt).Round(time.Second),
	)
	return nil
}

func (m *OrderManager) EmergencyCloseAll(ctx context.Context) {
	m.mu.RLock()
	symbols := make([]string, 0, len(m.positions))
	for s := range m.positions {
		symbols = append(symbols, s)
	}
	m.mu.RUnlock()

	for _, symbol := range symbols {
		if err := m.ClosePosition(ctx, symbol, "emergency"); err != nil {
			slog.Error("emergency close failed", "symbol", symbol, "err", err)
		}
	}
}

func (m *OrderManager) RunPoller(ctx context.Context) {
	ticker := time.NewTicker(30 * time.Second)
	defer ticker.Stop()

	for {
		select {
		case <-ticker.C:
			if err := m.PollPositions(ctx); err != nil {
				slog.Warn("position poll error", "err", err)
			}
		case <-ctx.Done():
			return
		}
	}
}
