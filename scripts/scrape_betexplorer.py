#!/usr/bin/env python3
"""
Scraper para Betexplorer - versión stdlib (sin deps externos)
Usa: python3 scrape_betexplorer.py [liga]
"""

import re
import sqlite3
import time
from datetime import datetime
from urllib.request import Request, urlopen

BETEXPLORER_BASE = "https://www.betexplorer.com"
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/148.0"

LIGAS = [
    "south-america/copa-libertadores",
    "south-america/copa-sudamericana",
    "mexico/liga-mx",
    "argentina/liga-profesional",
    "brazil/serie-a-betano",
    "england/premier-league",
]

DB_PATH = "/opt/data/proyectos/apuestas-agent/data/matches.db"

def fetch(url):
    req = Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urlopen(req, timeout=15) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"  Error fetching {url}: {e}")
        return ""

def scrape_league(liga_path):
    url = f"{BETEXPLORER_BASE}/football/{liga_path}/"
    html = fetch(url)
    if not html:
        return []
    
    matches = []
    
    # Pattern for teams with strong tags (result known)
    team_score_pat = re.compile(
        r'<span><strong>([^<]+)</strong></span> - <span>([^<]+)</span></a></td>\s*'
        r'<td class="h-text-center"><a[^>]*>\s*(\d+):(\d+)\s*</a></td>',
        re.DOTALL
    )
    
    team_matches = team_score_pat.findall(html)
    print(f"  Matches con resultado: {len(team_matches)}")
    
    # Pattern for teams WITHOUT strong tags (no result yet - upcoming)
    upcoming_pat = re.compile(
        r'<span>([^<]+)</span> - <span>([^<]+)</span></a></td>\s*'
        r'<td class="h-text-center">\s*</td>',
        re.DOTALL
    )
    
    upcoming_matches = upcoming_pat.findall(html)
    print(f"  Matches sin resultado (próximos): {len(upcoming_matches)}")
    
    # Get all data-odd values
    all_odds = re.findall(r'data-odd="(\d+\.\d+)"', html)
    print(f"  Odds encontradas: {len(all_odds)}")
    
    # Group odds by 3
    odds_groups = [all_odds[i:i+3] for i in range(0, len(all_odds), 3)]
    
    # Process matches with results
    for idx, (home, away, home_score, away_score) in enumerate(team_matches):
        if idx >= len(odds_groups):
            break
        odds = odds_groups[idx]
        
        hs = int(home_score)
        as_ = int(away_score)
        result = "HOME" if hs > as_ else ("DRAW" if hs == as_ else "AWAY")
        
        matches.append({
            "liga": liga_path,
            "home": home.strip(),
            "away": away.strip(),
            "home_score": hs,
            "away_score": as_,
            "result": result,
            "odds_1": float(odds[0]) if len(odds) > 0 else None,
            "odds_X": float(odds[1]) if len(odds) > 1 else None,
            "odds_2": float(odds[2]) if len(odds) > 2 else None,
            "has_result": True,
            "datetime": datetime.now().isoformat(),
        })
    
    # Process upcoming matches (no result)
    for idx, (home, away) in enumerate(upcoming_matches):
        base_idx = len(team_matches) + idx
        if base_idx >= len(odds_groups):
            break
        odds = odds_groups[base_idx]
        
        matches.append({
            "liga": liga_path,
            "home": home.strip(),
            "away": away.strip(),
            "home_score": None,
            "away_score": None,
            "result": None,
            "odds_1": float(odds[0]) if len(odds) > 0 else None,
            "odds_X": float(odds[1]) if len(odds) > 1 else None,
            "odds_2": float(odds[2]) if len(odds) > 2 else None,
            "has_result": False,
            "datetime": datetime.now().isoformat(),
        })
    
    return matches

def save_matches(matches):
    if not matches:
        return 0
    
    from pathlib import Path
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS matches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        liga TEXT,
        home TEXT,
        away TEXT,
        home_score INTEGER,
        away_score INTEGER,
        result TEXT,
        odds_1 REAL,
        odds_X REAL,
        odds_2 REAL,
        has_result INTEGER DEFAULT 0,
        datetime TEXT,
        scraped_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(home, away, datetime)
    )''')
    
    saved = 0
    for m in matches:
        try:
            c.execute('''INSERT OR IGNORE INTO matches 
                (liga, home, away, home_score, away_score, result, odds_1, odds_X, odds_2, has_result, datetime)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                (m['liga'], m['home'], m['away'], m['home_score'], m['away_score'], 
                 m['result'], m['odds_1'], m['odds_X'], m['odds_2'], 1 if m['has_result'] else 0, m['datetime']))
            if c.rowcount > 0:
                saved += 1
        except Exception as e:
            pass  # Skip duplicates
    
    conn.commit()
    conn.close()
    return saved

def show_stats():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    total = c.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
    with_result = c.execute("SELECT COUNT(*) FROM matches WHERE has_result=1").fetchone()[0]
    upcoming = c.execute("SELECT COUNT(*) FROM matches WHERE has_result=0").fetchone()[0]
    
    print(f"\nTotal partidos en DB: {total} ({with_result} con resultado, {upcoming} próximos)")
    
    stats = c.execute("""
        SELECT liga, 
               SUM(CASE WHEN has_result=1 THEN 1 ELSE 0 END) as with_res,
               SUM(CASE WHEN has_result=0 THEN 1 ELSE 0 END) as upcoming
        FROM matches 
        GROUP BY liga 
        ORDER BY liga
    """).fetchall()
    
    print("\nPor liga:")
    for s in stats:
        print(f"  {s[0]}: {s[1]} terminados, {s[2]} próximos")
    
    # Result distribution for finished matches
    res_stats = c.execute("""
        SELECT result, COUNT(*) as cnt 
        FROM matches 
        WHERE has_result=1 
        GROUP BY result
    """).fetchall()
    
    print("\nResultados (partidos terminados):")
    for r in res_stats:
        print(f"  {r[0]}: {r[1]}")
    
    conn.close()

def main():
    import sys
    
    ligas = [sys.argv[1]] if len(sys.argv) > 1 else LIGAS
    
    total = 0
    for liga in ligas:
        print(f"Scrapeando: {liga}")
        matches = scrape_league(liga)
        n = save_matches(matches)
        print(f"  -> {n} partidos guardados (sin duplicados)")
        total += n
        time.sleep(1)
    
    print(f"\nTotal: {total} partidos guardados")
    show_stats()

if __name__ == "__main__":
    main()