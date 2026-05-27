package main

import (
	"context"
	"encoding/json"
	"log/slog"
	"os"
	"os/signal"
	"syscall"

	"github.com/redis/go-redis/v9"
)

// Order published by Python live_publisher via Redis "orders" channel
type Order struct {
	Symbol     string  `json:"symbol"`      // "BTC/USDT:USDT"
	Side       string  `json:"side"`        // "BUY" | "SELL"
	EntryPrice float64 `json:"entry_price"`
	Quantity   float64 `json:"quantity"`
	StopLoss   float64 `json:"stop_loss"`
	TakeProfit float64 `json:"take_profit"`
	Confidence float64 `json:"confidence"`
	Strategy   string  `json:"strategy"`
}

func main() {
	slog.SetDefault(slog.New(slog.NewJSONHandler(os.Stdout, nil)))

	apiKey := getenv("BLOFIN_API_KEY", "")
	secret := getenv("BLOFIN_SECRET_KEY", "")
	passphrase := getenv("BLOFIN_PASSPHRASE", "")
	redisURL := getenv("REDIS_URL", "redis://localhost:6379/0")

	dryRun := apiKey == "" || secret == ""
	if dryRun {
		slog.Warn("BLOFIN credentials not set — running in dry-run mode (orders logged only)")
	}

	opt, err := redis.ParseURL(redisURL)
	if err != nil {
		slog.Error("invalid REDIS_URL", "err", err)
		os.Exit(1)
	}
	rdb := redis.NewClient(opt)

	client := NewBlofinClient(apiKey, secret, passphrase)
	manager := NewOrderManager(client)

	ctx, cancel := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer cancel()

	// Background goroutine: poll Blofin every 30s for fill status
	go manager.RunPoller(ctx)

	slog.Info("execution service started", "dry_run", dryRun, "redis", redisURL)

	pubsub := rdb.Subscribe(ctx, "orders")
	defer pubsub.Close()

	for {
		select {
		case msg, ok := <-pubsub.Channel():
			if !ok {
				return
			}
			var order Order
			if err := json.Unmarshal([]byte(msg.Payload), &order); err != nil {
				slog.Error("invalid order payload", "err", err, "raw", msg.Payload)
				continue
			}

			balance, balErr := client.GetBalance(ctx)
			if balErr != nil {
				slog.Warn("could not fetch balance, skipping validation", "err", balErr)
				balance = 0
			}

			if err := ValidateOrder(order, balance); err != nil {
				slog.Warn("order rejected", "symbol", order.Symbol, "reason", err.Error())
				continue
			}

			if dryRun {
				slog.Info("dry-run: would place order",
					"symbol", order.Symbol,
					"side", order.Side,
					"qty", order.Quantity,
					"entry", order.EntryPrice,
					"sl", order.StopLoss,
					"tp", order.TakeProfit,
					"confidence", order.Confidence,
					"strategy", order.Strategy,
				)
				continue
			}

			if err := manager.OpenPosition(ctx, order); err != nil {
				slog.Error("order placement failed", "symbol", order.Symbol, "err", err)
			}

		case <-ctx.Done():
			slog.Info("shutting down, closing all positions")
			manager.EmergencyCloseAll(context.Background())
			return
		}
	}
}

func getenv(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}
