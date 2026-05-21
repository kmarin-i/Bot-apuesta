#!/usr/bin/env python3
"""
X Tipster Monitor - Scrapea tweets de tipsters para detectar picks.
Usa Playwright para renderizar JavaScript.
"""

import re
import time
import json
from datetime import datetime, timedelta
from urllib.request import Request, urlopen

import sys
sys.path.insert(0, '/opt/data/proyectos/apuestas-agent')

from shared.blackboard import Blackboard
from shared.models import AgentEvent, EventType

# Lista de tipsters a monitorear
TIPSTERS = [
    'OlgaDiazApuestas',
    'JuanCarlosVM_',
    'TipsterMX',
    'ElPochoAnalista',
    'OverGolApuestas',
    'DaveTipsterESP',
    'CuervosApostando',
    'GolesyPronosticos',
]

DB_PATH = "/opt/data/proyectos/apuestas-agent/data/matches.db"

class XTipsterMonitor:
    """
    Monitorea cuentas de X para detectar picks automáticamente.
    """
    
    def __init__(self):
        self.blackboard = Blackboard()
        self.agent_id = "x_tipster_monitor"
    
    def fetch_x_profile(self, handle: str) -> str:
        """Scrapea el timeline de un usuario en X (página pública)."""
        # X tiene protección anti-scraping, intentamos con mobile o without JS
        urls_to_try = [
            f"https://nitter.net/{handle}?type=LATEST",
            f"https://nitter.privacydev.net/{handle}?type=LATEST",
        ]
        
        for url in urls_to_try:
            try:
                req = Request(url, headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
                })
                with urlopen(req, timeout=15) as resp:
                    html = resp.read().decode('utf-8', errors='replace')
                    if 'tweet' in html.lower() or 'timeline' in html.lower():
                        return html
            except:
                continue
        
        return ""
    
    def parse_tweets(self, html: str) -> list:
        """Extrae tweets de una página de Nitter."""
        tweets = []
        
        # Pattern para tweets en Nitter
        tweet_pattern = re.compile(
            r'<div class="tweet-content[^>]*>(.*?)</div>',
            re.DOTALL
        )
        
        matches = tweet_pattern.findall(html)
        for m in matches:
            # Limpiar HTML tags
            text = re.sub(r'<[^>]+>', '', m).strip()
            if len(text) > 10:
                tweets.append(text)
        
        return tweets[:20]  # Últimos 20 tweets
    
    def detect_pick_in_text(self, text: str) -> dict:
        """
        Detecta si un texto contiene un pick de apuestas.
        Pattern: equipo + DC/1X/X2 + cuota
        """
        text_lower = text.lower()
        
        # Flags de pick
        pick_indicators = ['dc', '1x', 'x2', 'doble oportunidad', 'victoria', 'gana', 'empate', 'over', 'under', 'btts', 'ambos']
        
        has_indicator = any(ind in text_lower for ind in pick_indicators)
        
        # Buscar cuotas (formato: @1.25, 1.25, odd 1.25)
        odds_pattern = re.compile(r'[@\s]?(\d+[.,]\d+)')
        odds_matches = odds_pattern.findall(text)
        
        if odds_matches:
            try:
                odds = float(odds_matches[0].replace(',', '.'))
            except:
                odds = None
        else:
            odds = None
        
        # Buscar equipos (patrones comunes)
        team_patterns = [
            r'\b([A-Z][a-zA-Z\s]{3,20})\s+(?:vs|hace|contra|vs\.)\s+([A-Z][a-zA-Z\s]{3,20})',
            r'\b([A-Z][a-zA-Z\s]{3,20})\s+(?:DC|1X|X2)',
            r'(?:Picks?|Jugando|Toca)\s+([A-Z][a-zA-Z\s]{3,20})',
        ]
        
        teams = []
        for pattern in team_patterns:
            match = re.search(pattern, text)
            if match:
                teams = [g.strip() for g in match.groups() if g]
                break
        
        return {
            'has_pick': has_indicator and odds is not None and len(teams) > 0,
            'odds': odds,
            'teams': teams,
            'text': text[:200]  # Primeros 200 chars
        }
    
    def scan_tipster(self, handle: str) -> list:
        """Escanea el timeline de un tipster buscando picks."""
        html = self.fetch_x_profile(handle)
        
        if not html:
            return []
        
        tweets = self.parse_tweets(html)
        picks = []
        
        for tweet in tweets:
            pick_info = self.detect_pick_in_text(tweet)
            if pick_info['has_pick']:
                picks.append({
                    'tipster': handle,
                    'odds': pick_info['odds'],
                    'teams': pick_info['teams'],
                    'text': pick_info['text'],
                    'detected_at': datetime.now().isoformat()
                })
        
        return picks
    
    def run(self) -> list:
        """Escanea todos los tipsters y devuelve picks detectados."""
        all_picks = []
        
        print(f"[{self.agent_id}] Scanning {len(TIPSTERS)} tipsters...")
        
        for handle in TIPSTERS:
            try:
                picks = self.scan_tipster(handle)
                if picks:
                    print(f"[{self.agent_id}] @{handle}: {len(picks)} picks detected")
                    all_picks.extend(picks)
                    
                    # Guardar picks en DB
                    self.save_picks_to_db(picks)
                    
                    # Publicar evento de nuevo pick
                    for pick in picks:
                        event = AgentEvent(
                            id="",
                            event_type=EventType.PICK_DETECTED.value,
                            publisher=self.agent_id,
                            payload=pick,
                            timestamp=datetime.now().isoformat(),
                            confidence=0.7  # Medium confidence - manual verification needed
                        )
                        self.blackboard.publish(event)
                
                time.sleep(2)  # Rate limit
            except Exception as e:
                print(f"[{self.agent_id}] Error scanning @{handle}: {e}")
                continue
        
        print(f"[{self.agent_id}] Total picks detected: {len(all_picks)}")
        return all_picks
    
    def save_picks_to_db(self, picks: list):
        """Guarda picks detectados en la DB."""
        import sqlite3
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # Asegurar tabla existe
        c.execute('''CREATE TABLE IF NOT EXISTS detected_picks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tipster_handle TEXT,
            teams TEXT,
            odds REAL,
            pick_text TEXT,
            detected_at TEXT,
            processed INTEGER DEFAULT 0
        )''')
        
        for pick in picks:
            c.execute('''INSERT OR IGNORE INTO detected_picks 
                (tipster_handle, teams, odds, pick_text, detected_at)
                VALUES (?, ?, ?, ?, ?)''',
                (pick['tipster'], json.dumps(pick['teams']), pick['odds'],
                 pick['text'][:500], pick['detected_at']))
        
        conn.commit()
        conn.close()


if __name__ == "__main__":
    monitor = XTipsterMonitor()
    picks = monitor.run()
    
    if picks:
        print("\n📋 Picks detectados:")
        for p in picks:
            print(f"  @{p['tipster']}: {' vs '.join(p['teams'])} @ {p['odds']}")
    else:
        print("\n🔍 No se detectaron picks nuevos en los timelines.")
        print("Nota: X tiene protección anti-scraping. Los resultados pueden variar.")
        print("Alternativa: usar API de X cuando esté disponible.")