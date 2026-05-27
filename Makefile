# Makefile — common VPS operations for the trading bot
# Usage: make <target>
# Requires: docker compose, bash

.PHONY: start stop restart update logs status ps clean backup help

COMPOSE = docker compose

help:
	@echo ""
	@echo "Trading Bot — VPS Operations"
	@echo ""
	@echo "  make start     Build and start all services"
	@echo "  make stop      Stop all services (data preserved)"
	@echo "  make restart   Restart bot, frontend, nginx only"
	@echo "  make update    Pull latest code and rebuild"
	@echo "  make logs      Follow bot logs (Ctrl-C to exit)"
	@echo "  make status    Show service health and recent log tail"
	@echo "  make ps        Show all container states"
	@echo "  make clean     Remove stopped containers and unused images"
	@echo "  make backup    Dump Postgres to ./backups/"
	@echo ""

start:
	$(COMPOSE) build --parallel
	$(COMPOSE) up -d
	@sleep 5
	$(COMPOSE) ps

stop:
	$(COMPOSE) down

restart:
	$(COMPOSE) up -d --no-deps --build bot frontend nginx

update:
	bash update.sh

logs:
	$(COMPOSE) logs -f bot

status:
	@echo "=== Container status ==="; $(COMPOSE) ps
	@echo ""
	@echo "=== Bot (last 30 lines) ==="; $(COMPOSE) logs --tail=30 bot
	@echo ""
	@echo "=== Health endpoint ===" ; curl -sf http://localhost/health || echo "(not reachable)"

ps:
	$(COMPOSE) ps

clean:
	$(COMPOSE) rm -f
	docker image prune -f

backup:
	@mkdir -p backups
	$(COMPOSE) exec -T postgres pg_dump -U $${DB_USER:-bot_user} trading_bot \
	    > backups/trading_bot_$$(date +%Y%m%d_%H%M%S).sql
	@echo "✓ Backup saved to backups/"
