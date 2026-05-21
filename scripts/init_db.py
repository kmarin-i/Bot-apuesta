#!/usr/bin/env python3
"""
Init DB - Agrega índices y optimizaciones a la DB del agente de apuestas.
Ejecutar una sola vez o después de crear nuevas tablas.
"""

import sqlite3
import sys
sys.path.insert(0, '/opt/data/proyectos/apuestas-agent')

DB_PATH = "/opt/data/proyectos/apuestas-agent/data/matches.db"
BLACKBOARD_DB = "/opt/data/proyectos/apuestas-agent/data/agent_blackboard.db"

def init_matches_db():
    """Optimiza la DB de matches."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    print("📊 Optimizando matches.db...")
    
    # Índices para queries frecuentes
    indexes = [
        ("idx_matches_liga", "matches", "liga"),
        ("idx_matches_result", "matches", "result"),
        ("idx_matches_date", "matches", "match_date"),
        ("idx_tipster_picks_handle", "tipster_picks", "tipster_handle"),
        ("idx_tipster_picks_result", "tipster_picks", "result"),
        ("idx_pending_results", "pending_results", "checked"),
        ("idx_detected_picks_processed", "detected_picks", "processed"),
    ]
    
    for idx_name, table, column in indexes:
        try:
            c.execute(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table}({column})")
            print(f"  ✅ {idx_name}")
        except Exception as e:
            print(f"  ⚠️ {idx_name}: {e}")
    
    # Verificar tabla de matches - agregar columnas faltantes si es necesario
    c.execute("PRAGMA table_info(matches)")
    columns = [row[1] for row in c.fetchall()]
    
    if 'match_date' not in columns:
        c.execute("ALTER TABLE matches ADD COLUMN match_date TEXT")
        print("  ✅ Agregada columna match_date")
    
    if 'scraped_at' not in columns:
        c.execute("ALTER TABLE matches ADD COLUMN scraped_at TEXT")
        print("  ✅ Agregada columna scraped_at")
    
    # Tabla de tipsters
    c.execute('''CREATE TABLE IF NOT EXISTS tipsters (
        handle TEXT PRIMARY KEY,
        source TEXT DEFAULT 'x',
        added_at TEXT,
        pick_count INTEGER DEFAULT 0,
        notes TEXT
    )''')
    print("  ✅ Tabla tipsters verificada")
    
    # Tabla de tipster_picks
    c.execute('''CREATE TABLE IF NOT EXISTS tipster_picks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tipster_handle TEXT,
        pick_text TEXT,
        stake REAL DEFAULT 50.0,
        odds REAL,
        result TEXT,
        result_checked INTEGER DEFAULT 0,
        profit REAL DEFAULT 0,
        roi REAL DEFAULT 0,
        created_at TEXT,
        checked_at TEXT,
        FOREIGN KEY (tipster_handle) REFERENCES tipsters(handle)
    )''')
    
    if 'stake' not in [row[1] for row in c.execute("PRAGMA table_info(tipster_picks)").fetchall()]:
        c.execute("ALTER TABLE tipster_picks ADD COLUMN stake REAL DEFAULT 50.0")
        print("  ✅ Agregada columna stake a tipster_picks")
    
    if 'roi' not in [row[1] for row in c.execute("PRAGMA table_info(tipster_picks)").fetchall()]:
        c.execute("ALTER TABLE tipster_picks ADD COLUMN roi REAL DEFAULT 0")
        print("  ✅ Agregada columna roi a tipster_picks")
    
    print("  ✅ Tabla tipster_picks verificada")
    
    conn.commit()
    conn.close()
    print("✅ matches.db optimizada\n")

def init_blackboard_db():
    """Optimiza la DB del blackboard."""
    conn = sqlite3.connect(BLACKBOARD_DB)
    c = conn.cursor()
    
    print("📊 Optimizando agent_blackboard.db...")
    
    # Índices para eventos
    indexes = [
        ("idx_events_type", "events", "event_type"),
        ("idx_events_publisher", "events", "publisher"),
        ("idx_events_timestamp", "events", "timestamp"),
        ("idx_patterns_type", "patterns", "pattern_type"),
    ]
    
    for idx_name, table, column in indexes:
        try:
            c.execute(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {table}({column})")
            print(f"  ✅ {idx_name}")
        except Exception as e:
            print(f"  ⚠️ {idx_name}: {e}")
    
    conn.commit()
    conn.close()
    print("✅ agent_blackboard.db optimizada\n")

def init_pending_results():
    """Crea tabla de pending results si no existe."""
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
        match_datetime TEXT,
        checked INTEGER DEFAULT 0,
        result TEXT,
        home_score INTEGER,
        away_score INTEGER,
        created_at TEXT,
        checked_at TEXT,
        scraped_at TEXT
    )''')
    
    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_matches_db()
    init_blackboard_db()
    init_pending_results()
    print("🎉 Base de datos inicializada correctamente")