# Bot-apuesta — Agente de Apuestas Deportivas

## Objetivo
Agente autónomo que sigue tipsters en X, analiza odds, detecta **value bets** y alerta por Telegram.

**Regla de oro:** ganar dinero, no solo informar.

---

## Arquitectura

```
X (tipsters)          →  Scraping de picks públicos
The Odds API           →  Líneas de bookmakers
n8n (VPS)              →  Orquestación y scheduling
AI Agent (VPS)         →  Análisis de patrones + decisión
Telegram (@Lucasapuesta_bot) → Alertas de value bets
PostgreSQL (VPS)       →  Storage: picks, odds, resultados, P&L
```

---

## Estructura del proyecto

```
Bot-apuesta/
├── src/                  # Código principal
│   ├── __init__.py
│   ├── scraper_x.py      # Scraping de X (tipsters)
│   ├── odds_client.py    # Cliente The Odds API
│   ├── value_finder.py   # Detecta value bets
│   ├── analyzer.py       # Analiza patrones de tipsters
│   └── telegram_bot.py   # Envío de alertas
├── n8n/                  # Workflows de n8n
├── data/                 # Datos (SQLite/Postgres)
├── config/               # Configuración (API keys, etc.)
├── scripts/              # Scripts utilitarios
└── tests/
```

---

## Pendientes

- [ ] The Odds API key → theoddsapi.com (CRÍTICO)
- [ ] Auth X en navegador VPS → scraping de tipsters
- [ ] Definir deporte: NBA / NFL / Fútbol
- [ ] Configurar PostgreSQL en VPS

---

## Stack

- Python 3.13
- n8n (VPS, Docker)
- PostgreSQL / SQLite
- Telegram Bot API
- The Odds API v5