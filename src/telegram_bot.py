#!/usr/bin/env python3
"""
Telegram Bot para alertas de apuestas.
Recibe picks y los procesa.
"""

import sqlite3
import json
from datetime import datetime
from urllib.request import Request, urlopen

DB_PATH = "/opt/data/proyectos/apuestas-agent/data/matches.db"

def calculate_dc_odds(odds_1, odds_X, odds_2):
    """Calcula odds de Doble Oportunidad (Double Chance)."""
    prob_1 = 1 / odds_1 if odds_1 else 0
    prob_X = 1 / odds_X if odds_X else 0
    prob_2 = 1 / odds_2 if odds_2 else 0
    
    dc_1x_prob = prob_1 + prob_X
    dc_x2_prob = prob_X + prob_2
    dc_12_prob = prob_1 + prob_2
    
    dc_1x_odds = 1 / dc_1x_prob if dc_1x_prob > 0 else None
    dc_x2_odds = 1 / dc_x2_prob if dc_x2_prob > 0 else None
    dc_12_odds = 1 / dc_12_prob if dc_12_prob > 0 else None
    
    return {"1X": dc_1x_odds, "X2": dc_x2_odds, "12": dc_12_odds}

def find_value_bets(threshold=1.05):
    """Encuentra apuestas con value."""
    conn = sqlite3.connect(DB_PATH)
    matches = conn.execute("""
        SELECT id, liga, home, away, odds_1, odds_X, odds_2
        FROM matches
        WHERE has_result = 0 AND odds_1 IS NOT NULL
        LIMIT 20
    """).fetchall()
    conn.close()
    
    value_bets = []
    for m in matches:
        _, liga, home, away, odds_1, odds_X, odds_2 = m
        dc_odds = calculate_dc_odds(odds_1, odds_X, odds_2)
        
        for dc_type, dc_odd in dc_odds.items():
            if dc_odd and dc_odd >= 1.05 and dc_odd <= 1.80:
                value_bets.append({
                    "liga": liga,
                    "home": home,
                    "away": away,
                    "dc_type": dc_type,
                    "dc_odds": dc_odd,
                    "probability": 1 / dc_odd if dc_odd else 0
                })
    
    return value_bets

def format_alert(match):
    """Formatea una alerta para Telegram."""
    dc_emoji = {"1X": "🏠", "X2": "✖️", "12": "🏟️"}
    emoji = dc_emoji.get(match["dc_type"], "⚽")
    
    msg = f"""
{emoji} *DOBLE OPORTUNIDAD*
━━━━━━━━━━━━━━━
🏆 *{match['liga'].split('/')[-1].upper()}*
{match['home']} vs {match['away']}
━━━━━━━━━━━━━━━
📌 Tipo: *{match['dc_type']}*
📊 Odd: *{match['dc_odds']:.2f}*
📈 Probabilidad: *{match['probability']*100:.0f}%*
━━━━━━━━━━━━━━━
"""
    return msg

def main():
    print("=== Buscando value bets ===")
    bets = find_value_bets()
    
    if bets:
        print(f"\nEncontrados {len(bets)} posibles value bets:")
        for b in bets[:5]:
            print(format_alert(b))
    else:
        print("\nNo hay value bets en este momento.")
        print("Esperando proximos partidos...")
    
    return bets

if __name__ == "__main__":
    main()