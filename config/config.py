#!/usr/bin/env python3
"""
Configuración centralizada del Betting Agent.
Todos los valores configurables están aquí.
No hardcodear nada en los agentes.
"""

import os

# ============================================================================
# DATABASE PATHS
# ============================================================================
DB_PATH = os.environ.get('BETTING_DB_PATH', '/opt/data/proyectos/apuestas-agent/data/matches.db')
BLACKBOARD_DB = os.environ.get('BLACKBOARD_DB_PATH', '/opt/data/proyectos/apuestas-agent/data/agent_blackboard.db')

# ============================================================================
# TELEGRAM CONFIG
# ============================================================================
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '7931331993')  # Ketzel's Telegram
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')  # @Lucasapuesta_bot token

# ============================================================================
# BETTING CONFIG
# ============================================================================
DEFAULT_STAKE = 50.0  # Stake por defecto en dólares
MIN_STAKE = 5.0  # Stake mínimo
MAX_STAKE_PCT = 0.10  # Máximo 10% del bankroll por apuesta
DEFAULT_BANKROLL = 1000.0  # Bankroll por defecto para cálculo de stakes

# ============================================================================
# VALUE DETECTION THRESHOLDS
# ============================================================================
VALUE_THRESHOLD_STRONG = 1.15  # Value score >= 1.15 = STRONG_BET
VALUE_THRESHOLD_NORMAL = 1.05  # Value score >= 1.05 = BET
ROI_THRESHOLD_STRONG = 10.0  # ROI esperado >= 10% para strong bet
ROI_THRESHOLD_NORMAL = 5.0  # ROI esperado >= 5% para bet normal

# ============================================================================
# KELLY CRITERION
# ============================================================================
KELLY_FRACTION = 0.25  # Usar 25% del Kelly completo (conservador)

# ============================================================================
# TIPSTER THRESHOLDS
# ============================================================================
TIPSTER_MIN_PICKS = 3  # Mínimo de picks para confiar en stats
ROI_THRESHOLD_LOW = -5.0  # ROI bajo - considerar dejar de seguir
ROI_THRESHOLD_VERY_LOW = -15.0  # ROI muy bajo - casi seguro dejar de seguir
WINRATE_THRESHOLD_MIN = 0.40  # Win rate mínimo aceptable (40%)

# ============================================================================
# SCRAPER CONFIG
# ============================================================================
LIGAS = [
    'Copa Libertadores',
    'Copa Sudamericana', 
    'Liga MX',
    'Argentina Primera División',
    'Serie A Brasil',
    'Premier League',
]

SCRAPE_TIMEOUT = 30  # Timeout por request en segundos
SCRAPE_DELAY = 2  # Delay entre requests (rate limit)

# ============================================================================
# RESULT VERIFICATION
# ============================================================================
RESULT_CHECK_HOURS = 3  # Horas después del partido para verificar resultado
AUTO_VERIFY_RESULTS = True  # Auto-verificar resultados pendientes

# ============================================================================
# ORCHESTRATOR
# ============================================================================
ORCHESTRATOR_INTERVAL = 30  # Minutos entre ciclos continuos
ORCHESTRATOR_ENABLED = True  # Habilitar orchestrator contínuo

# ============================================================================
# AGENT PERFORMANCE WEIGHTS
# ============================================================================
# Los pesos determinan cuánto confía el sistema en cada agente
AGENT_WEIGHTS = {
    'scraper_agent': 0.8,  # Confianza en scraping
    'analyzer_agent': 0.9,  # Confianza en análisis
    'alerter_agent': 0.85,  # Confianza en alertas
    'result_agent': 0.9,  # Confianza en verificación de resultados
}

# ============================================================================
# SELF-IMPROVEMENT
# ============================================================================
SELF_IMPROVEMENT_ENABLED = True  # Habilitar auto-mejora
PATTERN_MIN_OBSERVATIONS = 5  # Mínimo de observaciones para guardar patrón
PERFORMANCE_WINDOW = 50  # Número de picks para calcular win rate actual

# ============================================================================
# MARKET LIMITS
# ============================================================================
MIN_ODDS = 1.10  # Odds mínimas aceptables
MAX_ODDS = 15.0  # Odds máximas (más allá es sospechoso)
MAX_VALUE_SCORE = 2.0  # Value score máximo (evitar errores de cálculo)