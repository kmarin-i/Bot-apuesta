#!/usr/bin/env python3
"""
Result Agent - Verifica resultados de partidos automáticamente.
Se dispara cuando un partido debería haber terminado.
Scrapes Betexplorer para obtener resultado real.
"""

import re
import sqlite3
import time
from datetime import datetime, timedelta
from urllib.request import Request, urlopen

import sys
sys.path.insert(0, '/opt/data/proyectos/apuestas-agent')

from shared.models import AgentEvent, EventType
from shared.blackboard import Blackboard

DB_PATH = "/opt/data/proyectos/apuestas-agent/data/matches.db"
BETEXPLORER_BASE = "https://www.betexplorer.com"

class ResultAgent:
    """
    Agente especializado en verificar resultados de partidos.
    """
    
    def __init__(self, agent_id: str = "result_agent"):
        self.agent_id = agent_id
        self.blackboard = Blackboard()
        
        # Suscribirse a alertas de partidos
        self.blackboard.subscribe(EventType.PICK_ALERTED.value, self.agent_id, self.on_alert_sent)
    
    def fetch(self, url: str) -> str:
        """Fetch con manejo de errores."""
        try:
            req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urlopen(req, timeout=15) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except Exception as e:
            print(f"[{self.agent_id}] Error fetching {url}: {e}")
            return ""
    
    def scrape_result(self, home: str, away: str, liga: str) -> dict:
        """Scrapea resultado de un partido específico."""
        url = f"{BETEXPLORER_BASE}/football/{liga}/"
        html = self.fetch(url)
        
        if not html:
            return {"found": False}
        
        # Buscar el partido
        team_score_pat = re.compile(
            r'<span><strong>([^<]+)</strong></span> - <span>([^<]+)</span></a></td>\s*'
            r'<td class="h-text-center"><a[^>]*>\s*(\d+):(\d+)\s*</a></td>',
            re.DOTALL
        )
        
        matches = team_score_pat.findall(html)
        
        for match_home, match_away, score_home, score_away in matches:
            # Fuzzy match - normalizar nombres
            if (self._normalize(home) in self._normalize(match_home) or
                self._normalize(match_home) in self._normalize(home)) and \
               (self._normalize(away) in self._normalize(match_away) or
                self._normalize(match_away) in self._normalize(away)):
                
                hs, as_ = int(score_home), int(score_away)
                result = "HOME" if hs > as_ else ("DRAW" if hs == as_ else "AWAY")
                
                return {
                    "found": True,
                    "home": match_home.strip(),
                    "away": match_away.strip(),
                    "home_score": hs,
                    "away_score": as_,
                    "result": result,
                    "scraped_at": datetime.now().isoformat()
                }
        
        return {"found": False}
    
    def _normalize(self, name: str) -> str:
        """Normaliza nombre de equipo para matching."""
        # Minuscules, quitar acentos, short words
        import unicodedata
        name = name.lower()
        # Quitar acentos
        name = ''.join(c for c in unicodedata.normalize('NFD', name)
                      if unicodedata.category(c) != 'Mn')
        # Quitar "club", "fc", etc
        for word in ['club', 'fc', 'sc', 'cf', ' Atlético', 'Atl.']:
            name = name.replace(word, '')
        return name.strip()
    
    def determine_pick_result(self, pick_data: dict, match_result: dict) -> str:
        """
        Determina si un pick ganó o perdió.
        DC_1X = Local gana o empata → WIN si result in [HOME, DRAW]
        DC_X2 = Empata o visitante → WIN si result in [DRAW, AWAY]
        DC_12 = No empata → WIN si result in [HOME, AWAY]
        """
        if not match_result.get('found'):
            return "PENDING"
        
        result = match_result.get('result', '')
        pick_type = pick_data.get('best_dc', '')
        
        if pick_type == "DC_1X":
            return "WIN" if result in ["HOME", "DRAW"] else "LOSS"
        elif pick_type == "DC_X2":
            return "WIN" if result in ["DRAW", "AWAY"] else "LOSS"
        elif pick_type == "DC_12":
            return "WIN" if result in ["HOME", "AWAY"] else "LOSS"
        else:
            return "UNKNOWN"
    
    def on_alert_sent(self, event: AgentEvent):
        """Callback cuando se envió una alerta - programar verificación."""
        # Extraer datos del pick
        payload = event.payload
        pick_data = payload.get('pick_data', {})
        
        # Guardar en DB de picks pendientes
        liga = pick_data.get('liga', '')
        home = pick_data.get('home', '')
        away = pick_data.get('away', '')
        match_time_str = pick_data.get('match_time', '')
        
        # Por ahora, marcar como programado para verificar en 3 horas
        # En producción, calcular basado en match_time + buffer
        self.schedule_result_check(liga, home, away, payload, event.id)
    
    def schedule_result_check(self, liga: str, home: str, away: str, 
                             pick_data: dict, event_id: str):
        """Programa verificación de resultado."""
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        c.execute('''CREATE TABLE IF NOT EXISTS pending_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT,
            liga TEXT,
            home TEXT,
            away TEXT,
            best_dc TEXT,
            best_odds REAL,
            expected_roi REAL,
            alert_time TEXT,
            check_after TEXT,
            checked INTEGER DEFAULT 0,
            result TEXT,
            scraped_at TEXT
        )''')
        
        # Programar verificación para 3 horas después (para demos)
        # En producción: match_time + 2 hours
        check_after = datetime.now() + timedelta(hours=3)
        
        c.execute('''INSERT OR REPLACE INTO pending_results
            (event_id, liga, home, away, best_dc, best_odds, expected_roi, alert_time, check_after, checked)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0)''',
            (event_id, liga, home, away, 
             pick_data.get('best_dc', ''),
             pick_data.get('best_odds', 0),
             pick_data.get('expected_roi', 0),
             datetime.now().isoformat(),
             check_after.isoformat()))
        
        conn.commit()
        conn.close()
        
        print(f"[{self.agent_id}] Scheduled result check for {home} vs {away} at {check_after}")
    
    def check_pending_results(self):
        """Verifica resultados pendientes que ya deben estar listos."""
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # Ensure table exists
        c.execute('''CREATE TABLE IF NOT EXISTS pending_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT,
            liga TEXT,
            home TEXT,
            away TEXT,
            best_dc TEXT,
            best_odds REAL,
            expected_roi REAL,
            alert_time TEXT,
            check_after TEXT,
            checked INTEGER DEFAULT 0,
            result TEXT,
            scraped_at TEXT
        )''')
        
        now = datetime.now().isoformat()
        
        pending = c.execute('''SELECT * FROM pending_results 
            WHERE checked = 0 AND check_after <= ?''', (now,)).fetchall()
        
        print(f"[{self.agent_id}] Checking {len(pending)} pending results...")
        
        results_updated = 0
        for row in pending:
            _, event_id, liga, home, away, best_dc, best_odds, expected_roi, alert_time, check_after, checked, result, scraped_at = row
            
            # Scrape resultado
            match_result = self.scrape_result(home, away, liga)
            
            if match_result.get('found'):
                # Determinar si el pick ganó
                pick_data = {
                    'best_dc': best_dc,
                    'home': home,
                    'away': away
                }
                pick_result = self.determine_pick_result(pick_data, match_result)
                
                # Calcular profit - usar stake real del pick (default $50)
                stake = pick_data.get('stake', 50.0)
                if pick_result == "WIN":
                    profit = best_odds * stake - stake
                else:
                    profit = -stake
                
                # Actualizar pending
                c.execute('''UPDATE pending_results 
                    SET checked=1, result=?, scraped_at=? 
                    WHERE id=?''', 
                    (pick_result, match_result['scraped_at'], _))
                
                # Publicar evento de resultado
                result_event = AgentEvent(
                    id="",
                    event_type=EventType.PICK_RESULT.value,
                    publisher=self.agent_id,
                    payload={
                        'event_id': event_id,
                        'liga': liga,
                        'home': home,
                        'away': away,
                        'best_dc': best_dc,
                        'best_odds': best_odds,
                        'home_score': match_result['home_score'],
                        'away_score': match_result['away_score'],
                        'result': match_result['result'],
                        'pick_result': pick_result,
                        'profit': profit,
                        'scraped_at': match_result['scraped_at']
                    },
                    timestamp=datetime.now().isoformat(),
                    confidence=1.0 if match_result.get('found') else 0.5,
                    references=[event_id]
                )
                self.blackboard.publish(result_event)
                
                print(f"[{self.agent_id}] {home} vs {away} -> {match_result['result']} (pick: {pick_result}, profit: ${profit})")
                results_updated += 1
            else:
                # No se encontró resultado todavía - re-programar
                new_check = datetime.now() + timedelta(hours=1)
                c.execute('UPDATE pending_results SET check_after=? WHERE id=?', 
                         (new_check.isoformat(), _))
            
            time.sleep(1)  # Rate limit
        
        conn.commit()
        conn.close()
        
        print(f"[{self.agent_id}] Updated {results_updated} results")
        return results_updated
    
    def run(self):
        """Ejecuta verificación de resultados pendientes."""
        self.check_pending_results()


if __name__ == "__main__":
    agent = ResultAgent()
    agent.run()