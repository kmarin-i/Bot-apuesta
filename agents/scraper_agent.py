#!/usr/bin/env python3
"""
Scraper Agent - Detecta picks de fuentes externas y publica en blackboard.
Monitorea X (tipsters), Betexplorer (partidos y odds).
"""

import re
import time
from datetime import datetime, timedelta
from urllib.request import Request, urlopen
from typing import List, Optional

import sys
sys.path.insert(0, '/opt/data/proyectos/apuestas-agent')

from shared.models import AgentEvent, EventType, Pick, Market
from shared.blackboard import Blackboard

BETEXPLORER_BASE = "https://www.betexplorer.com"
LIGAS = [
    "south-america/copa-libertadores",
    "south-america/copa-sudamericana", 
    "mexico/liga-mx",
    "argentina/liga-profesional",
    "brazil/serie-a-betano",
    "england/premier-league",
]

class ScraperAgent:
    """
    Agente especializado en scraping de datos.
    Publica eventos: pick.detected, match.odds, etc.
    """
    
    def __init__(self, agent_id: str = "scraper_agent"):
        self.agent_id = agent_id
        self.blackboard = Blackboard()
        self.user_agent = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/148.0"
        
        # Suscribirse a eventos relevantes
        self.blackboard.subscribe("pick.result", self.agent_id, self.on_result_received)
    
    def fetch(self, url: str) -> str:
        """Fetch con manejo de errores."""
        try:
            req = Request(url, headers={"User-Agent": self.user_agent})
            with urlopen(req, timeout=15) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except Exception as e:
            print(f"[{self.agent_id}] Error fetching {url}: {e}")
            return ""
    
    def scrape_betexplorer_league(self, liga_path: str) -> List[dict]:
        """Scrapea una liga de Betexplorer y publica picks detectados."""
        url = f"{BETEXPLORER_BASE}/football/{liga_path}/"
        html = self.fetch(url)
        
        if not html:
            return []
        
        matches = []
        
        # Pattern para partidos terminados con resultado
        team_score_pat = re.compile(
            r'<span><strong>([^<]+)</strong></span> - <span>([^<]+)</span></a></td>\s*'
            r'<td class="h-text-center"><a[^>]*>\s*(\d+):(\d+)\s*</a></td>',
            re.DOTALL
        )
        
        team_matches = team_score_pat.findall(html)
        
        # Obtener todas las odds
        all_odds = re.findall(r'data-odd="(\d+\.\d+)"', html)
        odds_groups = [all_odds[i:i+3] for i in range(0, len(all_odds), 3)]
        
        for idx, (home, away, home_score, away_score) in enumerate(team_matches):
            if idx >= len(odds_groups):
                break
            
            odds = odds_groups[idx]
            hs, as_ = int(home_score), int(away_score)
            result = "HOME" if hs > as_ else ("DRAW" if hs == as_ else "AWAY")
            
            match_data = {
                "liga": liga_path,
                "home": home.strip(),
                "away": away.strip(),
                "home_score": hs,
                "away_score": as_,
                "result": result,
                "odds_1": float(odds[0]),
                "odds_X": float(odds[1]),
                "odds_2": float(odds[2]),
                "scraped_at": datetime.now().isoformat(),
                "source": "betexplorer"
            }
            
            matches.append(match_data)
            
            # Publicar evento de pick detectado (para partidos con resultado, 
            # esto ayuda al analyzer a calibrar)
            event = AgentEvent(
                id="",
                event_type=EventType.PICK_DETECTED.value,
                publisher=self.agent_id,
                payload=match_data,
                timestamp=datetime.now().isoformat(),
                confidence=0.8,  # Betexplorer es source confiable
                references=[]
            )
            self.blackboard.publish(event)
        
        return matches
    
    def scrape_upcoming_matches(self, liga_path: str) -> List[dict]:
        """Scrapea partidos próximos (sin resultado) de una liga."""
        url = f"{BETEXPLORER_BASE}/football/{liga_path}/"
        html = self.fetch(url)
        
        if not html:
            return []
        
        upcoming = []
        
        # Pattern para partidos sin resultado (próximos)
        upcoming_pat = re.compile(
            r'<span>([^<]+)</span> - <span>([^<]+)</span></a></td>\s*'
            r'<td class="h-text-center">\s*</td>',
            re.DOTALL
        )
        
        upcoming_matches = upcoming_pat.findall(html)
        
        # Obtener odds para estos partidos
        all_odds = re.findall(r'data-odd="(\d+\.\d+)"', html)
        
        # Los primeros N odds son de partidos terminados (ya procesados)
        # El resto son de partidos próximos
        # Necesitamos saber cuántos partidos terminados hay
        
        team_score_pat = re.compile(
            r'<span><strong>([^<]+)</strong></span> - <span>([^<]+)</span></a></td>\s*'
            r'<td class="h-text-center"><a[^>]*>\s*(\d+):(\d+)\s*</a></td>',
            re.DOTALL
        )
        finished_count = len(team_score_pat.findall(html))
        
        # Los odds después de los partidos terminados son de partidos próximos
        upcoming_odds = all_odds[finished_count * 3:]
        odds_groups = [upcoming_odds[i:i+3] for i in range(0, len(upcoming_odds), 3)]
        
        for idx, (home, away) in enumerate(upcoming_matches):
            if idx >= len(odds_groups):
                break
            
            odds = odds_groups[idx]
            
            match_data = {
                "liga": liga_path,
                "home": home.strip(),
                "away": away.strip(),
                "home_score": None,
                "away_score": None,
                "result": None,
                "odds_1": float(odds[0]),
                "odds_X": float(odds[1]),
                "odds_2": float(odds[2]),
                "scraped_at": datetime.now().isoformat(),
                "source": "betexplorer",
                "status": "upcoming"
            }
            
            upcoming.append(match_data)
        
        return upcoming
    
    def on_result_received(self, event: AgentEvent):
        """Callback cuando llega resultado de un pick."""
        # El scraper puede actualizar su accuracy basado en resultados
        # Por ahora solo loggea
        payload = event.payload
        print(f"[{self.agent_id}] Result received: {payload.get('match_home')} vs {payload.get('match_away')} -> {payload.get('result')}")
    
    def run_full_scrape(self):
        """Ejecuta scraping completo de todas las ligas."""
        print(f"[{self.agent_id}] Starting full scrape...")
        
        all_matches = []
        for liga in LIGAS:
            print(f"[{self.agent_id}] Scraping {liga}...")
            matches = self.scrape_betexplorer_league(liga)
            all_matches.extend(matches)
            print(f"[{self.agent_id}] Found {len(matches)} matches in {liga}")
            time.sleep(1)
        
        # Actualizar performance del agente
        self.blackboard.update_agent_performance(
            self.agent_id, "scraper", "full_scrape",
            success=len(all_matches) > 0,
            response_time=0.0
        )
        
        print(f"[{self.agent_id}] Scrape complete: {len(all_matches)} total matches")
        return all_matches
    
    def scrape_tipster_from_x(self, handle: str, count: int = 10) -> List[dict]:
        """
        Scrapea picks de un tipster desde X.
        Por ahora es un stub - necesita xurl o browser automation.
        """
        # TODO: Implementar con xurl o browser
        print(f"[{self.agent_id}] Would scrape @{handle} for {count} picks")
        return []
    
    def get_match_odds(self, home: str, away: str, liga: str) -> Optional[dict]:
        """Busca odds para un partido específico."""
        events = self.blackboard.get_events(event_type=EventType.PICK_DETECTED.value, limit=50)
        
        for event in events:
            payload = event.payload
            if (payload.get('home') == home and 
                payload.get('away') == away and
                payload.get('liga') == liga):
                return {
                    'odds_1': payload.get('odds_1'),
                    'odds_X': payload.get('odds_X'),
                    'odds_2': payload.get('odds_2')
                }
        
        return None


if __name__ == "__main__":
    agent = ScraperAgent()
    agent.run_full_scrape()