#!/usr/bin/env python3
"""
Analyzer Agent - Evalúa picks, calcula odds DC, detecta value, actualiza stats.
Es el "cerebro" que decide si un pick vale la pena.
"""

import re
import sqlite3
from datetime import datetime
from typing import List, Optional, Dict

import sys
sys.path.insert(0, '/opt/data/proyectos/apuestas-agent')

from shared.models import AgentEvent, EventType, Pick, Market, Pattern
from shared.blackboard import Blackboard

DB_PATH = "/opt/data/proyectos/apuestas-agent/data/matches.db"

class AnalyzerAgent:
    """
    Agente especializado en análisis de picks.
    Calcula valor, evalúa confianza, detecta patrones.
    """
    
    def __init__(self, agent_id: str = "analyzer_agent"):
        self.agent_id = agent_id
        self.blackboard = Blackboard()
        
        # Suscribirse a eventos relevantes
        self.blackboard.subscribe(EventType.PICK_DETECTED.value, self.agent_id, self.on_pick_detected)
        self.blackboard.subscribe(EventType.PICK_RESULT.value, self.agent_id, self.on_pick_result)
    
    def calculate_dc_odds(self, odds_1: float, odds_X: float, odds_2: float) -> Dict[str, float]:
        """
        Calcula odds de Doble Oportunidad (Double Chance).
        DC_1X = Local gana o empata
        DC_X2 = Empata o visitante
        DC_12 = No empata
        """
        prob_1 = 1 / odds_1 if odds_1 > 0 else 0
        prob_X = 1 / odds_X if odds_X > 0 else 0
        prob_2 = 1 / odds_2 if odds_2 > 0 else 0
        
        # Normalizar probabilidades (pueden sumar más de 1 por vig)
        total_prob = prob_1 + prob_X + prob_2
        prob_1_norm = prob_1 / total_prob
        prob_X_norm = prob_X / total_prob
        prob_2_norm = prob_2 / total_prob
        
        # DC odds usando probabilidades normalizadas
        dc_1x_prob = prob_1_norm + prob_X_norm
        dc_x2_prob = prob_X_norm + prob_2_norm
        dc_12_prob = prob_1_norm + prob_2_norm
        
        dc_1x_odds = 1 / dc_1x_prob if dc_1x_prob > 0 else 0
        dc_x2_odds = 1 / dc_x2_prob if dc_x2_prob > 0 else 0
        dc_12_odds = 1 / dc_12_prob if dc_12_prob > 0 else 0
        
        return {
            "DC_1X": round(dc_1x_odds, 2),
            "DC_X2": round(dc_x2_odds, 2),
            "DC_12": round(dc_12_odds, 2)
        }
    
    def estimate_fair_odds(self, odds_implied: float, historical_rate: float) -> float:
        """
        Estima odds justas basadas en historial.
        Si historical_rate = 0.65 (65% win rate) y odds actuales = 1.40:
        - Probabilidad implícita actual = 1/1.40 = 71.4%
        - Odds justas según historial = 1/0.65 = 1.54
        - Value = 1.54/1.40 = 1.10 (10% value)
        """
        return 1 / historical_rate if historical_rate > 0 else 0
    
    def calculate_value(self, dc_odds: float, historical_success_rate: float) -> Dict:
        """
        Calcula el value de una apuesta.
        Returns: {value_score, expected_roi, recommendation}
        """
        if dc_odds <= 0 or historical_success_rate <= 0:
            return {"value_score": 0, "expected_roi": 0, "recommendation": "SKIP"}
        
        implied_prob = 1 / dc_odds
        if implied_prob <= 0:  # Evitar división por cero
            return {"value_score": 0, "expected_roi": 0, "recommendation": "SKIP"}
        
        value_ratio = historical_success_rate / implied_prob
        
        # Value score: > 1.0 = value, > 1.1 = strong value
        expected_roi = (dc_odds * historical_success_rate - 1) * 100
        
        if value_ratio >= 1.15 and expected_roi >= 10:
            recommendation = "STRONG_BET"  # Apuesta fuerte
        elif value_ratio >= 1.05 and expected_roi >= 5:
            recommendation = "BET"  # Apuesta normal
        elif value_ratio >= 0.95:
            recommendation = "PASS"  # No hay value pero tampoco desventaja
        else:
            recommendation = "SKIP"  # Saltar -负value
        
        # Sanitizar expected_roi: no puede ser absurda (>1000% o <-100%)
        expected_roi = max(-100, min(expected_roi, 1000))
        
        return {
            "value_score": round(value_ratio, 3),
            "expected_roi": round(expected_roi, 2),
            "recommendation": recommendation,
            "implied_prob": round(implied_prob * 100, 1),
            "historical_prob": round(historical_success_rate * 100, 1)
        }
    
    def get_tipster_stats(self, handle: str) -> Dict:
        """Obtiene stats de un tipster desde el blackboard."""
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        stats = c.execute('''
            SELECT 
                COUNT(*) as total_picks,
                SUM(CASE WHEN result='WIN' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN result='LOSS' THEN 1 ELSE 0 END) as losses,
                SUM(CASE WHEN result='VOID' THEN 1 ELSE 0 END) as voids,
                SUM(profit) as total_profit
            FROM tipster_picks
            WHERE tipster_handle=? AND result_checked=1
        ''', (handle,)).fetchone()
        
        conn.close()
        
        total, wins, losses, voids, profit = stats or (0, 0, 0, 0, 0)
        
        if total > 0:
            win_rate = wins / total
            roi = (profit or 0) / (total * 50) * 100
        else:
            win_rate = 0.5  # Default 50% si no hay data
            roi = 0
        
        return {
            "total_picks": total or 0,
            "wins": wins or 0,
            "losses": losses or 0,
            "voids": voids or 0,
            "win_rate": win_rate,
            "roi": roi,
            "total_profit": profit or 0
        }
    
    def get_league_stats(self, liga: str) -> Dict:
        """Obtiene stats históricas de una liga."""
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        stats = c.execute('''
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN result='HOME' THEN 1 ELSE 0 END) as home_wins,
                SUM(CASE WHEN result='DRAW' THEN 1 ELSE 0 END) as draws,
                SUM(CASE WHEN result='AWAY' THEN 1 ELSE 0 END) as away_wins,
                AVG(odds_1) as avg_odds_1,
                AVG(odds_X) as avg_odds_X,
                AVG(odds_2) as avg_odds_2
            FROM matches
            WHERE liga=? AND result IS NOT NULL
        ''', (liga,)).fetchone()
        
        conn.close()
        
        total, home_wins, draws, away_wins = stats[:4] if stats else (0, 0, 0, 0)
        
        if total and total > 0:
            return {
                "total_matches": total,
                "home_win_rate": home_wins / total,
                "draw_rate": draws / total,
                "away_win_rate": away_wins / total,
                "avg_odds_1": stats[4] or 0,
                "avg_odds_X": stats[5] or 0,
                "avg_odds_2": stats[6] or 0
            }
        
        return {"total_matches": 0, "home_win_rate": 0.45, "draw_rate": 0.28, "away_win_rate": 0.27}
    
    def evaluate_pick(self, pick_data: dict) -> Dict:
        """
        Evalúa un pick y decide si vale la pena.
        Retorna evaluación completa con recomendación.
        """
        liga = pick_data.get('liga', '')
        home = pick_data.get('home', '')
        away = pick_data.get('away', '')
        tipster = pick_data.get('tipster_handle', 'betexplorer')
        
        # Obtener stats relevantes
        tipster_stats = self.get_tipster_stats(tipster)
        league_stats = self.get_league_stats(liga)
        
        # Calcular DC odds si tenemos odds 1X2
        odds_1 = pick_data.get('odds_1', 0)
        odds_X = pick_data.get('odds_X', 0)
        odds_2 = pick_data.get('odds_2', 0)
        
        dc_odds = self.calculate_dc_odds(odds_1, odds_X, odds_2)
        
        # Evaluar cada tipo de DC
        evaluations = {}
        for dc_type, dc_odd in dc_odds.items():
            if dc_odd <= 0:
                continue
            
            # Determinar historical rate según tipo de DC
            if dc_type == "DC_1X":
                hist_rate = league_stats.get('home_win_rate', 0.45) + league_stats.get('draw_rate', 0.28)
            elif dc_type == "DC_X2":
                hist_rate = league_stats.get('draw_rate', 0.28) + league_stats.get('away_win_rate', 0.27)
            else:  # DC_12
                hist_rate = league_stats.get('home_win_rate', 0.45) + league_stats.get('away_win_rate', 0.27)
            
            # Ajustar por ROI del tipster (factor entre 0.5 y 1.5 para evitar tasas negativas)
            tipster_factor = max(0.5, min(1 + (tipster_stats.get('roi', 0) / 100), 1.5))
            adjusted_rate = min(max(hist_rate * tipster_factor, 0.01), 0.95)  # Cap 1%-95%
            
            value_eval = self.calculate_value(dc_odd, adjusted_rate)
            
            evaluations[dc_type] = {
                "dc_odds": dc_odd,
                "historical_rate": round(adjusted_rate * 100, 1),
                **value_eval
            }
        
        # Encontrar el mejor DC para esta pareja
        best_dc = max(evaluations.items(), 
                      key=lambda x: x[1].get('value_score', 0), 
                      default=(None, {}))
        
        # Decisión final
        if best_dc[0] and evaluations.get(best_dc[0], {}).get('recommendation') in ["BET", "STRONG_BET"]:
            final_recommendation = evaluations[best_dc[0]]['recommendation']
            confidence = min(evaluations[best_dc[0]]['value_score'], 1.5)
        else:
            final_recommendation = "NO_VALUE"
            confidence = 0.3
            best_dc = (None, {})
        
        return {
            "pick_data": pick_data,
            "dc_evaluations": evaluations,
            "best_dc": best_dc[0],
            "best_odds": evaluations.get(best_dc[0], {}).get('dc_odds', 0),
            "value_score": evaluations.get(best_dc[0], {}).get('value_score', 0),
            "expected_roi": evaluations.get(best_dc[0], {}).get('expected_roi', 0),
            "recommendation": final_recommendation,
            "confidence": confidence,
            "tipster_stats": tipster_stats,
            "league_stats": league_stats,
            "evaluated_at": datetime.now().isoformat()
        }
    
    def on_pick_detected(self, event: AgentEvent):
        """Callback cuando se detecta un pick."""
        evaluation = self.evaluate_pick(event.payload)
        
        # Publicar evento de pick evaluado
        eval_event = AgentEvent(
            id="",
            event_type=EventType.PICK_EVALUATED.value,
            publisher=self.agent_id,
            payload=evaluation,
            timestamp=datetime.now().isoformat(),
            confidence=evaluation.get('confidence', 0.5) * event.confidence,
            references=[event.id]
        )
        self.blackboard.publish(eval_event)
        
        # Descubrir patrones si hay stats suficientes
        if evaluation.get('tipster_stats', {}).get('total_picks', 0) >= 5:
            self._discover_patterns(evaluation)
    
    def _discover_patterns(self, evaluation: Dict):
        """Descubre y registra patrones."""
        tipster = evaluation.get('pick_data', {}).get('tipster_handle', '')
        liga = evaluation.get('pick_data', {}).get('liga', '')
        best_dc = evaluation.get('best_dc', '')
        result = evaluation.get('recommendation', '')
        
        if not tipster or not liga:
            return
        
        # Registrar patrón de tipster
        pattern_key = f"tipster:{tipster}"
        existing = self.blackboard.get_patterns(pattern_type="tipster", pattern_key=pattern_key)
        
        if existing:
            # Actualizar existente
            p = existing[0]
            new_count = p['observed_count'] + 1
            new_success = p['success_count'] + (1 if result in ["BET", "STRONG_BET"] else 0)
            new_rate = new_success / new_count
            new_roi = (p.get('avg_roi', 0) * p['observed_count'] + evaluation.get('expected_roi', 0)) / new_count
            
            self.blackboard.discover_pattern("tipster", pattern_key, self.agent_id, {
                'observed_count': new_count,
                'success_count': new_success,
                'success_rate': new_rate,
                'avg_roi': new_roi,
                'confidence': min(new_count / 10, 1.0)  # Más confianza con más samples
            })
        else:
            # Nuevo patrón
            self.blackboard.discover_pattern("tipster", pattern_key, self.agent_id, {
                'observed_count': 1,
                'success_count': 1 if result in ["BET", "STRONG_BET"] else 0,
                'success_rate': 1.0 if result in ["BET", "STRONG_BET"] else 0.0,
                'avg_roi': evaluation.get('expected_roi', 0),
                'confidence': 0.3  # Baja confianza inicial
            })
    
    def on_pick_result(self, event: AgentEvent):
        """Callback cuando llega resultado de un pick."""
        payload = event.payload
        result = payload.get('result', '')
        tipster = payload.get('tipster_handle', '')
        
        # Actualizar stats del tipster
        if tipster and result in ['WIN', 'LOSS']:
            # El resultado llegó - el analyzer puede recalcular con datos reales
            pass
        
        # Ajustar confianza del agente que publicó el resultado
        if result == 'WIN':
            self.blackboard.adjust_agent_confidence('alerter_agent', 0.05)  # +5% confianza
        else:
            self.blackboard.adjust_agent_confidence('alerter_agent', -0.05)  # -5% confianza
    
    def run_analysis(self, picks: List[dict]) -> List[Dict]:
        """Analiza una lista de picks."""
        results = []
        for pick in picks:
            eval_result = self.evaluate_pick(pick)
            results.append(eval_result)
            
            # Publicar evento de evaluación
            event = AgentEvent(
                id="",
                event_type=EventType.PICK_EVALUATED.value,
                publisher=self.agent_id,
                payload=eval_result,
                timestamp=datetime.now().isoformat(),
                confidence=eval_result.get('confidence', 0.5)
            )
            self.blackboard.publish(event)
        
        return results
    
    def get_recommendations(self, min_value_score: float = 1.05) -> List[Dict]:
        """Obtiene picks recomendados (value bets)."""
        events = self.blackboard.get_events(EventType.PICK_EVALUATED.value, limit=50)
        
        recommendations = []
        for event in events:
            if event.confidence >= min_value_score:
                payload = event.payload
                if payload.get('recommendation') in ['BET', 'STRONG_BET']:
                    recommendations.append({
                        **payload,
                        'event_id': event.id
                    })
        
        # Ordenar por value score
        recommendations.sort(key=lambda x: x.get('value_score', 0), reverse=True)
        
        return recommendations[:10]  # Top 10


if __name__ == "__main__":
    agent = AnalyzerAgent()
    
    # Test con data existente
    conn = sqlite3.connect(DB_PATH)
    matches = conn.execute("SELECT * FROM matches LIMIT 5").fetchall()
    conn.close()
    
    print(f"Analyzing {len(matches)} matches...")
    for m in matches:
        pick_data = {
            'liga': m[1],
            'home': m[2],
            'away': m[3],
            'odds_1': m[7],
            'odds_X': m[8],
            'odds_2': m[9]
        }
        result = agent.evaluate_pick(pick_data)
        print(f"\n{pick_data['home']} vs {pick_data['away']}: {result['recommendation']} (value: {result['value_score']})")
        print(f"  Best DC: {result['best_dc']} @ {result['best_odds']}")
        print(f"  Expected ROI: {result['expected_roi']}%")