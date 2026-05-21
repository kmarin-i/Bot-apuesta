#!/usr/bin/env python3
"""
Alerter Agent - Envía alertas por Telegram, prioriza por value y ROI.
Solo envía las mejores oportunidades según análisis del Analyzer.
"""

import sqlite3
from datetime import datetime
from typing import List, Dict, Optional

import sys
sys.path.insert(0, '/opt/data/proyectos/apuestas-agent')

from shared.models import AgentEvent, EventType
from shared.blackboard import Blackboard

DB_PATH = "/opt/data/proyectos/apuestas-agent/data/matches.db"

class AlerterAgent:
    """
    Agente especializado en enviar alertas.
    Solo envía picks que pasaron el filtro del Analyzer.
    """
    
    def __init__(self, agent_id: str = "alerter_agent"):
        self.agent_id = agent_id
        self.blackboard = Blackboard()
        self.telegram_chat_id = "7931331993"  # Ketzel's Telegram
        
        # Suscribirse a picks evaluados
        self.blackboard.subscribe(EventType.PICK_EVALUATED.value, self.agent_id, self.on_pick_evaluated)
    
    def format_telegram_message(self, evaluation: Dict) -> str:
        """Formatea mensaje para Telegram con emojis."""
        pick_data = evaluation.get('pick_data', {})
        liga = pick_data.get('liga', '').split('/')[-1].upper()
        home = pick_data.get('home', '')
        away = pick_data.get('away', '')
        
        best_dc = evaluation.get('best_dc', '')
        best_odds = evaluation.get('best_odds', 0)
        value_score = evaluation.get('value_score', 0)
        expected_roi = evaluation.get('expected_roi', 0)
        recommendation = evaluation.get('recommendation', '')
        confidence = evaluation.get('confidence', 0)
        
        # Emojis
        dc_emoji = {"DC_1X": "🏠", "DC_X2": "✖️", "DC_12": "🏟️"}
        emoji = dc_emoji.get(best_dc, "⚽")
        
        conf_emoji = "🟢" if confidence >= 1.1 else ("🟡" if confidence >= 1.05 else "🔴")
        
        msg = f"""{emoji} *DOBLE OPORTUNIDAD*
━━━━━━━━━━━━━━━
🏆 *{liga}*
{home} vs {away}
━━━━━━━━━━━━━━━
📌 Tipo: *{best_dc}* @ *{best_odds:.2f}*
📊 Value: {conf_emoji} {value_score:.3f} ({value_score-1:.1%})
📈 ROI esperado: *{expected_roi:.1f}%*
🔗 Confianza: *{confidence:.2f}*
━━━━━━━━━━━━━━━"""
        
        if recommendation == "STRONG_BET":
            msg += "\n🔥 *APUESTA FUERTE*"
        elif recommendation == "BET":
            msg += "\n✅ *BUENA APUESTA*"
        
        return msg
    
    def calculate_stake(self, odds: float, bankroll: float = 1000, target_roi: float = 50) -> float:
        """
        Calcula stake óptimo basado en Kelly Criterion simplificado.
        """
        # Kelly fraction = edge / odds
        # edge = value_score - 1
        edge = max(0, (1 / odds) - (1 - 1/odds))  # simplified
        
        # Usar fracción de Kelly (25% del full Kelly)
        kelly_fraction = 0.25 * edge
        
        # Stake como % del bankroll
        stake = bankroll * kelly_fraction
        
        # Bounds
        stake = max(5, min(stake, bankroll * 0.1))  # Min $5, max 10% del bankroll
        
        return round(stake, 2)
    
    def on_pick_evaluated(self, event: AgentEvent):
        """Callback cuando se evalúa un pick."""
        payload = event.payload
        recommendation = payload.get('recommendation', '')
        
        # Solo alertar picks recomendados
        if recommendation not in ['BET', 'STRONG_BET']:
            return
        
        # Verificar que no sea un duplicado reciente
        recent_events = self.blackboard.get_events(EventType.PICK_ALERTED.value, limit=10)
        for recent in recent_events:
            recent_payload = recent.payload
            if (recent_payload.get('pick_data', {}).get('home') == payload.get('pick_data', {}).get('home') and
                recent_payload.get('pick_data', {}).get('away') == payload.get('pick_data', {}).get('away') and
                recent_payload.get('best_dc') == payload.get('best_dc')):
                print(f"[{self.agent_id}] Duplicate pick, skipping: {payload.get('pick_data', {}).get('home')}")
                return
        
        # Formatear mensaje
        message = self.format_telegram_message(payload)
        
        # Calcular stake sugerido
        best_odds = payload.get('best_odds', 0)
        stake = self.calculate_stake(best_odds)
        
        message += f"\n💰 *Stake sugerido: ${stake:.2f}*"
        
        # Aquí iría el envío real a Telegram
        # Por ahora solo publicamos el evento
        print(f"[{self.agent_id}] Alert prepared:")
        print(message)
        
        # Publicar evento de alerta enviada
        alert_event = AgentEvent(
            id="",
            event_type=EventType.PICK_ALERTED.value,
            publisher=self.agent_id,
            payload={
                **payload,
                'telegram_message': message,
                'stake_suggested': stake,
                'chat_id': self.telegram_chat_id
            },
            timestamp=datetime.now().isoformat(),
            confidence=event.confidence,
            references=[event.id]
        )
        self.blackboard.publish(alert_event)
        
        # Actualizar performance
        self.blackboard.update_agent_performance(
            self.agent_id, "alerter", "alert_sent",
            success=True, response_time=0.5
        )
    
    def send_scheduled_alerts(self):
        """Envía alertas programadas basadas en eventos pendientes."""
        # Obtener últimos picks evaluados que no fueron alertados
        evaluated_events = self.blackboard.get_events(EventType.PICK_EVALUATED.value, limit=20)
        alerted_events = self.blackboard.get_events(EventType.PICK_ALERTED.value, limit=50)
        
        alerted_ids = {e.get('references', [''])[0] for e in alerted_events}
        
        for event in evaluated_events:
            payload = event.payload
            if payload.get('recommendation') in ['BET', 'STRONG_BET']:
                if event.id not in alerted_ids:
                    # Este pick no fue alertado aún
                    self.on_pick_evaluated(event)
    
    def get_tipster_roi_report(self) -> str:
        """Genera reporte de ROI por tipster para enviar a Telegram."""
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        tipsters = c.execute('''
            SELECT tp.handle, 
                   COUNT(*) as total,
                   SUM(CASE WHEN tp.result='WIN' THEN 1 ELSE 0 END) as wins,
                   SUM(CASE WHEN tp.result='LOSS' THEN 1 ELSE 0 END) as losses,
                   SUM(tp.profit) as profit
            FROM tipster_picks tp
            WHERE tp.result_checked = 1
            GROUP BY tp.handle
            HAVING COUNT(*) >= 3
            ORDER BY profit DESC
        ''').fetchall()
        
        conn.close()
        
        if not tipsters:
            return "📊 *Reporte ROI Tipsters*\n\nNo hay suficiente data aún."
        
        msg = "📊 *REPORTE ROI TIPSTERS*\n━━━━━━━━━━━━━━━\n\n"
        
        for handle, total, wins, losses, profit in tipsters:
            win_rate = wins / total * 100 if total > 0 else 0
            roi = (profit or 0) / (total * 50) * 100
            
            emoji = "🟢" if roi >= 15 else ("🟡" if roi >= 0 else "🔴")
            
            msg += f"{emoji} @{handle}\n"
            msg += f"   Picks: {total} ({wins}W-{losses}L)\n"
            msg += f"   Win rate: {win_rate:.0f}%\n"
            msg += f"   Profit: ${profit:.2f} (ROI: {roi:.1f}%)\n\n"
        
        return msg
    
    def check_low_roi_tipsters(self, threshold: float = -5.0) -> List[str]:
        """Alertar sobre tipsters con ROI bajo."""
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        tipsters = c.execute('''
            SELECT tp.tipster_handle, 
                   COUNT(*) as total,
                   SUM(tp.profit) as profit
            FROM tipster_picks tp
            WHERE tp.result_checked = 1
            GROUP BY tp.tipster_handle
            HAVING COUNT(*) >= 5
        ''').fetchall()
        
        conn.close()
        
        alerts = []
        for handle, total, profit in tipsters:
            roi = (profit or 0) / (total * 50) * 100
            if roi < threshold:
                alerts.append(f"⚠️ @{handle}: ROI {roi:.1f}% ({total} picks)")
        
        return alerts


if __name__ == "__main__":
    agent = AlerterAgent()
    
    # Enviar reporte de ROI
    report = agent.get_tipster_roi_report()
    print(report)
    
    # Check low ROI tipsters
    alerts = agent.check_low_roi_tipsters()
    if alerts:
        print("\n🚨 ROI BAJO:")
        for a in alerts:
            print(a)