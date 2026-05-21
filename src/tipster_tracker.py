#!/usr/bin/env python3
"""
Tipster Tracker - Monitorea ROI por tipster y alerta cuando uno baja del threshold.
Uso: python3 tipster_tracker.py [comando]
Comandos:
  add <handle> <fuente>   - Agregar tipster a seguir
  list                    - Listar todos los tipsters
  stats <handle>          - Ver stats de un tipster
  alert_low_roi <threshold> - Mostrar tipsters con ROI bajo
  remove <handle>         - Dejar de seguir un tipster
"""

import sqlite3
from datetime import datetime, timedelta
from enum import Enum

DB_PATH = "/opt/data/proyectos/apuestas-agent/data/matches.db"
DEFAULT_THRESHOLD = -5.0  # ROI bajo = alertarme

class TipsterDB:
    def __init__(self):
        self._init_db()
    
    def _init_db(self):
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        c.execute('''CREATE TABLE IF NOT EXISTS tipsters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            handle TEXT UNIQUE NOT NULL,
            source TEXT,
            added_date TEXT,
            active INTEGER DEFAULT 1,
            notes TEXT
        )''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS tipster_picks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tipster_handle TEXT,
            pick_text TEXT,
            match_home TEXT,
            match_away TEXT,
            market TEXT,
            pick TEXT,
            odds REAL,
            stake REAL,
            pick_time TEXT,
            match_time TEXT,
            result_checked INTEGER DEFAULT 0,
            result TEXT,
            profit REAL,
            roi REAL,
            checked_at TEXT,
            FOREIGN KEY (tipster_handle) REFERENCES tipsters(handle)
        )''')
        
        conn.commit()
        conn.close()
    
    def add_tipster(self, handle, source="x", notes=""):
        """Agrega un tipster a seguir."""
        handle = handle.strip().replace("@", "").lower()
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        try:
            c.execute('''INSERT INTO tipsters (handle, source, added_date, notes)
                          VALUES (?, ?, ?, ?)''',
                      (handle, source, datetime.now().isoformat(), notes))
            conn.commit()
            result = f"✅ Tipster @{handle} agregado"
        except sqlite3.IntegrityError:
            result = f"⚠️ @{handle} ya existe"
        
        conn.close()
        return result
    
    def remove_tipster(self, handle):
        """Deja de seguir un tipster."""
        handle = handle.strip().replace("@", "").lower()
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # Soft delete - marcar inactivo
        c.execute('UPDATE tipsters SET active=0 WHERE handle=?', (handle,))
        if c.rowcount > 0:
            result = f"🚫 @{handle} removido (inactivo)"
        else:
            result = f"⚠️ @{handle} no encontrado"
        
        conn.commit()
        conn.close()
        return result
    
    def list_tipsters(self, active_only=True):
        """Lista todos los tipsters."""
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        query = 'SELECT handle, source, added_date, active, notes FROM tipsters'
        if active_only:
            query += ' WHERE active=1'
        query += ' ORDER BY handle'
        
        rows = c.execute(query).fetchall()
        conn.close()
        
        return rows
    
    def get_tipster_stats(self, handle):
        """Obtiene stats de un tipster."""
        handle = handle.strip().replace("@", "").lower()
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # Stats generales
        stats = c.execute('''
            SELECT 
                COUNT(*) as total_picks,
                SUM(CASE WHEN result='WIN' THEN 1 ELSE 0 END) as wins,
                SUM(CASE WHEN result='LOSS' THEN 1 ELSE 0 END) as losses,
                SUM(CASE WHEN result='VOID' THEN 1 ELSE 0 END) as voids,
                SUM(profit) as total_profit,
                AVG(roi) as avg_roi
            FROM tipster_picks
            WHERE tipster_handle=? AND result_checked=1
        ''', (handle,)).fetchone()
        
        total, wins, losses, voids, profit, avg_roi = stats
        
        if total and total > 0:
            win_rate = (wins or 0) / total * 100
            roi = (profit or 0) / (total * 50) * 100 if profit else 0  # assuming $50 avg stake
        else:
            win_rate = 0
            roi = 0
        
        conn.close()
        
        return {
            "handle": handle,
            "total_picks": total or 0,
            "wins": wins or 0,
            "losses": losses or 0,
            "voids": voids or 0,
            "win_rate": win_rate,
            "total_profit": profit or 0,
            "roi": roi
        }
    
    def alert_low_roi(self, threshold=DEFAULT_THRESHOLD):
        """Alertar tipsters con ROI bajo."""
        tipsters = self.list_tipsters(active_only=True)
        
        alerts = []
        for (handle, source, added, active, notes) in tipsters:
            stats = self.get_tipster_stats(handle)
            if stats["total_picks"] >= 5:  # Mínimo 5 picks para evaluar
                if stats["roi"] < threshold:
                    alerts.append({
                        "handle": handle,
                        "roi": stats["roi"],
                        "total_picks": stats["total_picks"],
                        "wins": stats["wins"],
                        "losses": stats["losses"],
                        "win_rate": stats["win_rate"],
                        "total_profit": stats["total_profit"],
                        "recommendation": "🚫 BAJAR ROI - Considerar dejar de seguir"
                    })
                elif stats["roi"] > 15:
                    alerts.append({
                        "handle": handle,
                        "roi": stats["roi"],
                        "total_picks": stats["total_picks"],
                        "wins": stats["wins"],
                        "losses": stats["losses"],
                        "win_rate": stats["win_rate"],
                        "total_profit": stats["total_profit"],
                        "recommendation": "⭐ ALTO ROI - Prioridad máxima"
                    })
        
        return alerts
    
    def add_pick(self, handle, pick_data):
        """Agrega un pick de un tipster."""
        handle = handle.strip().replace("@", "").lower()
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        c.execute('''INSERT INTO tipster_picks 
            (tipster_handle, pick_text, match_home, match_away, market, pick, odds, stake, pick_time, match_time)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
            (handle, pick_data.get("pick_text", ""),
             pick_data.get("match_home", ""),
             pick_data.get("match_away", ""),
             pick_data.get("market", ""),
             pick_data.get("pick", ""),
             pick_data.get("odds", 0),
             pick_data.get("stake", 50),
             datetime.now().isoformat(),
             pick_data.get("match_time", "")))
        
        conn.commit()
        conn.close()
    
    def update_pick_result(self, pick_id, result, profit, roi):
        """Actualiza resultado de un pick."""
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        c.execute('''UPDATE tipster_picks 
            SET result=?, profit=?, roi=?, result_checked=1, checked_at=?
            WHERE id=?''',
            (result, profit, roi, datetime.now().isoformat(), pick_id))
        
        conn.commit()
        conn.close()


def format_tipster_report(handle):
    """Formatea reporte de un tipster para Telegram."""
    db = TipsterDB()
    stats = db.get_tipster_stats(handle)
    
    emoji_roi = "🟢" if stats["roi"] >= 10 else ("🟡" if stats["roi"] >= 0 else "🔴")
    
    msg = f"""
📊 *@{stats['handle']}*
━━━━━━━━━━━━━━━
🎯 Picks: *{stats['total_picks']}*
✅ Wins: *{stats['wins']}*
❌ Losses: *{stats['losses']}*
➖ Voids: *{stats['voids']}*
📈 Win Rate: *{stats['win_rate']:.1f}%*
💰 Profit: *${stats['total_profit']:.2f}*
{emoji_roi} ROI: *{stats['roi']:.1f}%*
━━━━━━━━━━━━━━━
"""
    return msg


def main():
    import sys
    
    db = TipsterDB()
    args = sys.argv[1:]
    
    if not args:
        # Default: list tipsters + alerts
        tipsters = db.list_tipsters()
        print(f"\n📋 Tipsters siguiendo: {len(tipsters)}")
        for t in tipsters:
            stats = db.get_tipster_stats(t[0])
            emoji = "🟢" if stats["roi"] >= 10 else ("🟡" if stats["roi"] >= 0 else "🔴")
            print(f"  {emoji} @{t[0]} | Picks: {stats['total_picks']} | ROI: {stats['roi']:.1f}%")
        
        alerts = db.alert_low_roi()
        if alerts:
            print(f"\n🚨 ALERTAS ROI BAJO:")
            for a in alerts:
                print(f"  🚫 @{a['handle']} | ROI: {a['roi']:.1f}% ({a['total_picks']} picks)")
        return
    
    cmd = args[0].lower()
    
    if cmd == "add" and len(args) >= 2:
        handle = args[1]
        source = args[2] if len(args) > 2 else "x"
        print(db.add_tipster(handle, source))
    
    elif cmd == "list":
        tipsters = db.list_tipsters()
        print(f"\n📋 Tipsters ({len(tipsters)}):")
        for t in tipsters:
            print(format_tipster_report(t[0]))
    
    elif cmd == "stats" and len(args) >= 2:
        print(format_tipster_report(args[1]))
    
    elif cmd == "alert_low_roi":
        threshold = float(args[1]) if len(args) > 1 else DEFAULT_THRESHOLD
        alerts = db.alert_low_roi(threshold)
        if alerts:
            print(f"\n🚨 Tipsters con ROI < {threshold}%:")
            for a in alerts:
                print(f"  🚫 @{a['handle']} | ROI: {a['roi']:.1f}% | Wins: {a['wins']}/{a['total_picks']}")
        else:
            print(f"\n✅ Ningún tipster con ROI bajo (< {threshold}%)")
    
    elif cmd == "remove" and len(args) >= 2:
        print(db.remove_tipster(args[1]))
    
    else:
        print(__doc__)


if __name__ == "__main__":
    main()