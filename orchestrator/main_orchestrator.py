#!/usr/bin/env python3
"""
Orchestrator - El cerebro central que coordina todos los agentes.
Maneja el flujo de eventos, ajusta weights, detecta anomalías.
"""

import time
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import sys
sys.path.insert(0, '/opt/data/proyectos/apuestas-agent')

from shared.blackboard import Blackboard
from shared.models import AgentEvent, EventType
from agents.scraper_agent import ScraperAgent
from agents.analyzer_agent import AnalyzerAgent
from agents.alerter_agent import AlerterAgent
from agents.result_agent import ResultAgent

DB_PATH = "/opt/data/proyectos/apuestas-agent/data/matches.db"

class Orchestrator:
    """
    Orquetador central del sistema multi-agente.
    Coordina flujo de trabajo, detecta anomalías, ajusta thresholds.
    """
    
    def __init__(self):
        self.blackboard = Blackboard()
        
        # Inicializar agentes
        self.agents = {
            'scraper': ScraperAgent(),
            'analyzer': AnalyzerAgent(),
            'alerter': AlerterAgent(),
            'result': ResultAgent()
        }
        
        # Suscribirse a todos los eventos para monitoreo
        for event_type in [e.value for e in EventType]:
            self.blackboard.subscribe(event_type, 'orchestrator', self.on_any_event)
        
        # Configuración de thresholds
        self.config = {
            'min_value_score': 1.05,
            'max_alerts_per_day': 10,
            'low_roi_threshold': -5.0,
            'high_roi_threshold': 15.0,
            'min_picks_for_stats': 5,
            'scrape_interval_hours': 6,
            'result_check_interval_minutes': 30
        }
        
        print("[Orchestrator] Initialized with agents:", list(self.agents.keys()))
    
    def on_any_event(self, event: AgentEvent):
        """Callback para cualquier evento - monitoreo central."""
        # Log de eventos importantes
        if event.event_type in [EventType.PICK_ALERTED.value, EventType.PICK_RESULT.value]:
            print(f"[Orchestrator] Event: {event.event_type} from {event.publisher} (conf: {event.confidence:.2f})")
        
        # Detectar anomalías
        self._detect_anomalies(event)
    
    def _detect_anomalies(self, event: AgentEvent):
        """Detecta anomalías en el sistema."""
        # Si hay muchos picks evaluados sin alertas, algo puede estar mal
        if event.event_type == EventType.PICK_EVALUATED.value:
            recent_evals = self.blackboard.get_events(EventType.PICK_EVALUATED.value, limit=20)
            recent_alerts = self.blackboard.get_events(EventType.PICK_ALERTED.value, limit=20)
            
            # Si tenemos >10 evaluaciones pero <3 alertas,可能有问题
            if len(recent_evals) > 10 and len(recent_alerts) < 3:
                print("[Orchestrator] ⚠️ Anomaly: Many evaluations, few alerts. Check analyzer thresholds.")
        
        # Si el alerter tiene baja confianza, reducir frecuencia
        perf = self.blackboard.get_agent_performance('alerter_agent')
        if perf and perf.get('confidence', 1.0) < 0.5:
            print("[Orchestrator] ⚠️ Alerter confidence low: {:.1%}. Adjusting...".format(perf['confidence']))
            self._adjust_alerts()
    
    def _adjust_alerts(self):
        """Ajusta parámetros de alertas basándose en performance."""
        # Reducir max_alerts_per_day si el alerter no está performsando bien
        current = self.config['max_alerts_per_day']
        self.config['max_alerts_per_day'] = int(current * 0.8)
        print(f"[Orchestrator] Adjusted max_alerts to {self.config['max_alerts_per_day']}")
    
    def run_scrape_cycle(self):
        """Ejecuta ciclo de scraping completo."""
        print("[Orchestrator] Starting scrape cycle...")
        
        # Ejecutar scraper
        scraper = self.agents['scraper']
        matches = scraper.run_full_scrape()
        
        # Guardar matches en DB principal
        self._save_matches_to_db(matches)
        
        print(f"[Orchestrator] Scrape cycle complete: {len(matches)} matches")
        return matches
    
    def _save_matches_to_db(self, matches: List[dict]):
        """Guarda matches en la DB principal."""
        if not matches:
            return
        
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        for m in matches:
            try:
                c.execute('''INSERT OR IGNORE INTO matches 
                    (liga, home, away, home_score, away_score, result, odds_1, odds_X, odds_2, datetime)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                    (m['liga'], m['home'], m['away'], m['home_score'], m['away_score'],
                     m['result'], m['odds_1'], m['odds_X'], m['odds_2'], m.get('scraped_at', datetime.now().isoformat())))
            except:
                pass
        
        conn.commit()
        conn.close()
    
    def run_analysis_cycle(self):
        """Ejecuta ciclo de análisis para picks pendientes."""
        print("[Orchestrator] Starting analysis cycle...")
        
        analyzer = self.agents['analyzer']
        
        # Obtener matches sin resultado (próximos)
        conn = sqlite3.connect(DB_PATH)
        matches = conn.execute('''
            SELECT liga, home, away, odds_1, odds_X, odds_2 
            FROM matches 
            WHERE result IS NULL 
            LIMIT 20
        ''').fetchall()
        conn.close()
        
        for m in matches:
            pick_data = {
                'liga': m[0],
                'home': m[1],
                'away': m[2],
                'odds_1': m[3],
                'odds_X': m[4],
                'odds_2': m[5]
            }
            result = analyzer.evaluate_pick(pick_data)
            
            # Si es recommended, publicar evento de evaluación
            if result.get('recommendation') in ['BET', 'STRONG_BET']:
                event = AgentEvent(
                    id="",
                    event_type=EventType.PICK_EVALUATED.value,
                    publisher='orchestrator',
                    payload=result,
                    timestamp=datetime.now().isoformat(),
                    confidence=result.get('confidence', 0.5)
                )
                self.blackboard.publish(event)
        
        print(f"[Orchestrator] Analysis cycle complete: {len(matches)} matches analyzed")
    
    def run_alert_cycle(self):
        """Ejecuta ciclo de alertas."""
        print("[Orchestrator] Starting alert cycle...")
        
        alerter = self.agents['alerter']
        
        # Enviar alertas pendientes
        alerter.send_scheduled_alerts()
        
        # Verificar ROI bajo
        low_roi = alerter.check_low_roi_tipsters(self.config['low_roi_threshold'])
        if low_roi:
            print("[Orchestrator] Low ROI tipsters detected:")
            for alert in low_roi:
                print(f"  {alert}")
        
        print("[Orchestrator] Alert cycle complete")
    
    def run_result_check_cycle(self):
        """Ejecuta ciclo de verificación de resultados."""
        print("[Orchestrator] Starting result check cycle...")
        
        result_agent = self.agents['result']
        result_agent.check_pending_results()
        
        print("[Orchestrator] Result check cycle complete")
    
    def run_self_improvement(self):
        """Ejecuta ciclo de auto-mejora del sistema."""
        print("[Orchestrator] Running self-improvement cycle...")
        
        # 1. Recalcular stats de tipsters basándose en resultados recientes
        self._recalculate_tipster_stats()
        
        # 2. Actualizar patrones en el blackboard
        self._update_patterns()
        
        # 3. Ajustar thresholds basándose en performance
        self._adjust_thresholds()
        
        # 4. Reportar stats al blackboard
        self._report_system_stats()
        
        print("[Orchestrator] Self-improvement complete")
    
    def _recalculate_tipster_stats(self):
        """Recalcula stats de tipsters basándose en resultados."""
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # Check if tipster_picks table exists and has data
        try:
            c.execute("SELECT COUNT(*) FROM tipster_picks")
        except sqlite3.OperationalError:
            # Table doesn't exist, nothing to recalculate
            conn.close()
            return
        
        tipsters = c.execute('''
            SELECT tp.tipster_handle, COUNT(*) as total,
                   SUM(CASE WHEN tp.result='WIN' THEN 1 ELSE 0 END) as wins,
                   SUM(tp.profit) as profit
            FROM tipster_picks tp
            WHERE tp.result_checked=1
            GROUP BY tp.tipster_handle
        ''').fetchall()
        
        conn.close()
        
        for handle, total, wins, profit in tipsters:
            if total >= self.config['min_picks_for_stats']:
                win_rate = wins / total if total > 0 else 0
                roi = (profit or 0) / (total * 50) * 100
                
                # Ajustar confianza del tipster en el sistema
                if roi >= self.config['high_roi_threshold']:
                    # Tipster performs bien - aumentar su peso
                    pattern_key = f"tipster:{handle}"
                    patterns = self.blackboard.get_patterns(pattern_type="tipster", pattern_key=pattern_key)
                    if patterns:
                        p = patterns[0]
                        new_weight = min(p.get('weight', 1.0) * 1.1, 2.0)  # Max 2x weight
                        print(f"[Orchestrator] @{handle} high ROI: adjusting weight to {new_weight:.2f}")
                
                elif roi < self.config['low_roi_threshold']:
                    # Tipster con bajo ROI - reducir peso o alertar
                    print(f"[Orchestrator] ⚠️ @{handle} ROI {roi:.1f}% below threshold")
    
    def _update_patterns(self):
        """Actualiza patrones descubiertos con nueva data."""
        # Obtener picks evaluados recientes
        recent_events = self.blackboard.get_events(EventType.PICK_RESULT.value, limit=50)
        
        for event in recent_events:
            payload = event.payload
            tipster = payload.get('tipster_handle', '')
            liga = payload.get('liga', '')
            pick_result = payload.get('pick_result', '')
            
            if not tipster:
                continue
            
            # Actualizar patrón del tipster
            pattern_key = f"tipster:{tipster}"
            existing = self.blackboard.get_patterns(pattern_type="tipster", pattern_key=pattern_key)
            
            if existing:
                p = existing[0]
                new_count = p['observed_count'] + 1
                new_success = p['success_count'] + (1 if pick_result == 'WIN' else 0)
                new_rate = new_success / new_count
                
                self.blackboard.discover_pattern("tipster", pattern_key, "orchestrator", {
                    'observed_count': new_count,
                    'success_count': new_success,
                    'success_rate': new_rate,
                    'confidence': min(new_count / 10, 1.0)
                })
            
            # Actualizar patrón de liga
            if liga:
                pattern_key = f"liga:{liga}"
                existing = self.blackboard.get_patterns(pattern_type="liga", pattern_key=pattern_key)
                
                if existing:
                    p = existing[0]
                    new_count = p['observed_count'] + 1
                    new_success = p['success_count'] + (1 if pick_result == 'WIN' else 0)
                    new_rate = new_success / new_count
                    
                    self.blackboard.discover_pattern("liga", pattern_key, "orchestrator", {
                        'observed_count': new_count,
                        'success_count': new_success,
                        'success_rate': new_rate,
                        'confidence': min(new_count / 10, 1.0)
                    })
    
    def _adjust_thresholds(self):
        """Ajusta thresholds basándose en performance histórica."""
        # Leer eventos de resultados últimos 7 días
        recent_results = self.blackboard.get_events(EventType.PICK_RESULT.value, limit=100)
        
        if len(recent_results) < 10:
            return  # No hay suficiente data
        
        # Calcular win rate general
        wins = sum(1 for e in recent_results if e.payload.get('pick_result') == 'WIN')
        total = len(recent_results)
        win_rate = wins / total if total > 0 else 0
        
        # Si win_rate > 60%, podemos ser más agresivos (bajar threshold)
        if win_rate > 0.6:
            self.config['min_value_score'] = max(1.0, self.config['min_value_score'] - 0.01)
            print(f"[Orchestrator] Win rate high ({win_rate:.1%}), adjusted min_value_score to {self.config['min_value_score']:.3f}")
        
        # Si win_rate < 40%, ser más conservative
        elif win_rate < 0.4:
            self.config['min_value_score'] = min(1.15, self.config['min_value_score'] + 0.01)
            print(f"[Orchestrator] Win rate low ({win_rate:.1%}), adjusted min_value_score to {self.config['min_value_score']:.3f}")
    
    def _report_system_stats(self):
        """Reporta stats del sistema al blackboard."""
        conn = sqlite3.connect(DB_PATH)
        
        # Total de picks en sistema
        total_picks = conn.execute("SELECT COUNT(*) FROM tipster_picks WHERE result_checked=1").fetchone()[0]
        
        # Picks por resultado
        wins = conn.execute("SELECT COUNT(*) FROM tipster_picks WHERE result='WIN' AND result_checked=1").fetchone()[0]
        losses = conn.execute("SELECT COUNT(*) FROM tipster_picks WHERE result='LOSS' AND result_checked=1").fetchone()[0]
        
        conn.close()
        
        overall_win_rate = wins / total_picks if total_picks > 0 else 0
        
        print(f"[Orchestrator] System stats: {total_picks} picks, {wins}W/{losses}L ({overall_win_rate:.1%} win rate)")
        
        # Publicar como evento de sistema
        event = AgentEvent(
            id="",
            event_type=EventType.SYSTEM_ADJUSTMENT.value,
            publisher="orchestrator",
            payload={
                "stats_type": "system_overview",
                "total_picks": total_picks,
                "wins": wins,
                "losses": losses,
                "win_rate": overall_win_rate,
                "config": self.config
            },
            timestamp=datetime.now().isoformat(),
            confidence=overall_win_rate
        )
        self.blackboard.publish(event)
    
    def run_full_cycle(self):
        """Ejecuta un ciclo completo del orquestador."""
        print(f"\n[Orchestrator] === Full Cycle {datetime.now().strftime('%Y-%m-%d %H:%M')} ===")
        
        # 1. Scrapear nuevos datos
        self.run_scrape_cycle()
        
        # 2. Analizar picks
        self.run_analysis_cycle()
        
        # 3. Enviar alertas
        self.run_alert_cycle()
        
        # 4. Verificar resultados pendientes
        self.run_result_check_cycle()
        
        # 5. Auto-mejora
        self.run_self_improvement()
        
        print(f"[Orchestrator] === Cycle Complete ===\n")
    
    def run_continuous(self, interval_minutes: int = 30):
        """Ejecuta el orquestador continuamente."""
        print(f"[Orchestrator] Running continuously every {interval_minutes} minutes...")
        
        while True:
            try:
                self.run_full_cycle()
                time.sleep(interval_minutes * 60)
            except KeyboardInterrupt:
                print("[Orchestrator] Shutting down...")
                break
            except Exception as e:
                print(f"[Orchestrator] Error: {e}")
                time.sleep(60)  # Wait 1 min before retry


if __name__ == "__main__":
    orchestrator = Orchestrator()
    
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--continuous":
        orchestrator.run_continuous()
    else:
        orchestrator.run_full_cycle()