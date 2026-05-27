package main

import (
	"bytes"
	"context"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/google/uuid"
)

const blofinBaseURL = "https://openapi.blofin.com"

type BlofinClient struct {
	apiKey     string
	secret     string
	passphrase string
	httpClient *http.Client
}

func NewBlofinClient(apiKey, secret, passphrase string) *BlofinClient {
	return &BlofinClient{
		apiKey:     apiKey,
		secret:     secret,
		passphrase: passphrase,
		httpClient: &http.Client{Timeout: 10 * time.Second},
	}
}

type OrderResult struct {
	OrderId string `json:"ordId"`
	Code    string `json:"code"`
	Msg     string `json:"msg"`
}

type Position struct {
	InstId    string  `json:"instId"`
	PosSide   string  `json:"posSide"`
	Pos       float64 `json:"pos,string"`
	AvgPx     float64 `json:"avgPx,string"`
	Upl       float64 `json:"upl,string"`
}

// blofinSymbol converts BTC/USDT:USDT → BTC-USDT
func blofinSymbol(symbol string) string {
	base := strings.Split(symbol, ":")[0] // BTC/USDT
	return strings.ReplaceAll(base, "/", "-")
}

func (c *BlofinClient) sign(method, path, body string) map[string]string {
	ts := strconv.FormatInt(time.Now().UnixMilli(), 10)
	nonce := uuid.New().String()

	message := ts + nonce + strings.ToUpper(method) + path + body
	mac := hmac.New(sha256.New, []byte(c.secret))
	mac.Write([]byte(message))
	sig := hex.EncodeToString(mac.Sum(nil))

	return map[string]string{
		"ACCESS-KEY":        c.apiKey,
		"ACCESS-SIGN":       sig,
		"ACCESS-TIMESTAMP":  ts,
		"ACCESS-NONCE":      nonce,
		"ACCESS-PASSPHRASE": c.passphrase,
		"Content-Type":      "application/json",
	}
}

func (c *BlofinClient) doRequest(ctx context.Context, method, path string, body any) ([]byte, error) {
	var bodyStr string
	var bodyReader io.Reader

	if body != nil {
		b, err := json.Marshal(body)
		if err != nil {
			return nil, err
		}
		bodyStr = string(b)
		bodyReader = bytes.NewReader(b)
	}

	req, err := http.NewRequestWithContext(ctx, method, blofinBaseURL+path, bodyReader)
	if err != nil {
		return nil, err
	}

	headers := c.sign(method, path, bodyStr)
	for k, v := range headers {
		req.Header.Set(k, v)
	}

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	data, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, err
	}

	if resp.StatusCode >= 400 {
		return nil, fmt.Errorf("blofin API %d: %s", resp.StatusCode, string(data))
	}
	return data, nil
}

func (c *BlofinClient) PlaceOrder(ctx context.Context, symbol, side string, qty, entryPrice, sl float64) (*OrderResult, error) {
	instId := blofinSymbol(symbol)
	blofinSide := strings.ToLower(side) // "buy" or "sell"

	payload := map[string]any{
		"instId":      instId,
		"marginMode":  "cross",
		"posSide":     "net",
		"side":        blofinSide,
		"ordType":     "market",
		"sz":          fmt.Sprintf("%.4f", qty),
		"slTriggerPx": fmt.Sprintf("%.2f", sl),
		"slOrdPx":     "-1", // market stop
	}

	data, err := c.doRequest(ctx, "POST", "/api/v1/trade/order", payload)
	if err != nil {
		return nil, err
	}

	var wrapper struct {
		Code string        `json:"code"`
		Msg  string        `json:"msg"`
		Data []OrderResult `json:"data"`
	}
	if err := json.Unmarshal(data, &wrapper); err != nil {
		return nil, err
	}
	if wrapper.Code != "0" {
		return nil, fmt.Errorf("blofin order error %s: %s", wrapper.Code, wrapper.Msg)
	}
	if len(wrapper.Data) == 0 {
		return nil, fmt.Errorf("blofin returned empty order data")
	}
	return &wrapper.Data[0], nil
}

func (c *BlofinClient) GetPositions(ctx context.Context) ([]*Position, error) {
	data, err := c.doRequest(ctx, "GET", "/api/v1/account/positions", nil)
	if err != nil {
		return nil, err
	}

	var wrapper struct {
		Code string      `json:"code"`
		Data []*Position `json:"data"`
	}
	if err := json.Unmarshal(data, &wrapper); err != nil {
		return nil, err
	}
	return wrapper.Data, nil
}

func (c *BlofinClient) CancelOrder(ctx context.Context, instId, orderId string) error {
	payload := map[string]string{
		"instId": instId,
		"ordId":  orderId,
	}
	_, err := c.doRequest(ctx, "POST", "/api/v1/trade/cancel-order", payload)
	return err
}

func (c *BlofinClient) GetBalance(ctx context.Context) (float64, error) {
	data, err := c.doRequest(ctx, "GET", "/api/v1/account/balance", nil)
	if err != nil {
		return 0, err
	}

	var wrapper struct {
		Code string `json:"code"`
		Data []struct {
			Details []struct {
				Ccy   string  `json:"ccy"`
				AvailEq float64 `json:"availEq,string"`
			} `json:"details"`
		} `json:"data"`
	}
	if err := json.Unmarshal(data, &wrapper); err != nil {
		return 0, err
	}

	for _, account := range wrapper.Data {
		for _, detail := range account.Details {
			if detail.Ccy == "USDT" {
				return detail.AvailEq, nil
			}
		}
	}
	return 0, fmt.Errorf("USDT balance not found")
}
