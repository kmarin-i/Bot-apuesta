#!/usr/bin/env python3
"""
CLI para el sistema de betting agent.
Uso: python3 betting_cli.py [comando]
"""

import sys
import json
from datetime import datetime

sys.path.insert(0, '/opt/data/proyectos/apuestas-agent')

from src.tipster_tracker import TipsterDB
from shared.blackboard import Blackboard
from src.dashboard_generator import DashboardGenerator
from orchestrator.main_orchestrator import Orchestrator

DB_PATH = "/opt/data/proyectos/apuestas-agent/data/matches.db"

def cmd_stats():
    """Muestra estadísticas generales."""
    from src.tipster_tracker import TipsterDB
    
    tracker = TipsterDB()
    tipsters = tracker.list_tipsters()
    
    total_picks = 0
    total_wins = 0
    total_profit = 0
    
    print("\n📊 ESTADÍSTICAS DEL SISTEMA")
    print("=" * 50)
    print(f"Total tipsters: {len(tipsters)}")
    
    # Get stats per tipster (tipsters is list of tuples: handle, source, added, pick_count, notes)
    top_tipsters = []
    for t in tipsters:
        handle = t[0]  # tuple format: (handle, source, added, pick_count, notes)
        stats = tracker.get_tipster_stats(handle)
        if stats:
            total_picks += stats['total_picks']
            total_wins += stats['wins']
            total_profit += stats['total_profit']
            if stats['total_picks'] >= 3:
                top_tipsters.append({
                    'handle': handle,
                    'total_picks': stats['total_picks'],
                    'wins': stats['wins'],
                    'profit': stats['total_profit']
                })
    
    win_rate = (total_wins / total_picks * 100) if total_picks > 0 else 0
    
    print(f"Total picks: {total_picks}")
    print(f"Wins: {total_wins} | Losses: {total_picks - total_wins}")
    print(f"Win rate: {win_rate:.1f}%")
    print(f"Profit total: ${total_profit:.2f}")
    
    # Top tipsters
    if top_tipsters:
        top_tipsters.sort(key=lambda x: x['profit'], reverse=True)
        print("\n🏆 TOP TIPSTERS:")
        for t in top_tipsters[:5]:
            wr = (t['wins'] / t['total_picks'] * 100) if t['total_picks'] > 0 else 0
            print(f"  @{t['handle']}: {t['total_picks']} picks, {wr:.1f}% WR, ${t['profit']:.2f}")

def cmd_list_tipsters():
    """Lista todos los tipsters."""
    tracker = TipsterDB()
    tipsters = tracker.list_tipsters()
    
    print("\n📋 TIPSTERS EN MONITOREO")
    print("=" * 50)
    for t in tipsters:
        handle = t[0]  # tuple: (handle, source, added, pick_count, notes)
        stats = tracker.get_tipster_stats(handle)
        wr = (stats['wins'] / stats['total_picks'] * 100) if stats['total_picks'] > 0 else 0
        status = "🟢" if stats['total_picks'] >= 5 else "🟡"
        print(f"{status} @{handle} | {stats['total_picks']} picks | {wr:.1f}% WR | {t[1]}")

def cmd_add_tipster(handle: str, source: str = "x", notes: str = ""):
    """Agrega un tipster."""
    tracker = TipsterDB()
    result = tracker.add_tipster(handle, source, notes)
    if result:
        print(f"✅ Tipster @{handle} agregado")
    else:
        print(f"⚠️ @{handle} ya existe")

def cmd_remove_tipster(handle: str):
    """Deja de seguir un tipster."""
    tracker = TipsterDB()
    result = tracker.remove_tipster(handle)
    if result:
        print(f"✅ @{handle} removido")
    else:
        print(f"❌ @{handle} no encontrado")

def cmd_low_roi(threshold: float = -5.0):
    """Muestra tipsters con ROI bajo."""
    tracker = TipsterDB()
    alerts = tracker.alert_low_roi(threshold)
    
    print(f"\n⚠️ TIPSTERS CON ROI < {threshold}%")
    print("=" * 50)
    if alerts:
        for a in alerts:
            print(f"  @{a['handle']}: {a['roi']:.1f}% ROI ({a['total_picks']} picks)")
    else:
        print("  Ningún tipster bajo el threshold")

def cmd_dashboard():
    """Genera el dashboard."""
    gen = DashboardGenerator()
    path = gen.generate()
    print(f"✅ Dashboard generado: {path}")

def cmd_run_cycle():
    """Ejecuta un ciclo completo del orquestador."""
    print("🚀 Ejecutando ciclo completo del orquestador...\n")
    orch = Orchestrator()
    orch.run_full_cycle()
    print("\n✅ Ciclo completo")

def cmd_run_orchestrator_continuous():
    """Ejecuta el orquestador continuamente."""
    print("🎛️ Ejecutando orquestador en modo continuo...")
    print("   Presiona Ctrl+C para detener\n")
    orch = Orchestrator()
    orch.run_continuous(interval_minutes=30)

def cmd_events():
    """Muestra eventos recientes del blackboard."""
    bb = Blackboard()
    print("\n📨 EVENTOS RECIENTES")
    print("=" * 50)
    
    from shared.models import EventType
    
    for event_type in [EventType.PICK_DETECTED.value, EventType.PICK_EVALUATED.value, 
                       EventType.PICK_ALERTED.value, EventType.PICK_RESULT.value]:
        events = bb.get_events(event_type, limit=3)
        if events:
            print(f"\n{event_type}:")
            for e in events:
                print(f"  [{e.timestamp}] {e.publisher} - conf: {e.confidence:.2f}")
                if e.payload:
                    print(f"    {json.dumps(e.payload)[:100]}...")

def cmd_patterns():
    """Muestra patrones descubiertos."""
    bb = Blackboard()
    print("\n🔍 PATRONES DESCUBIERTOS")
    print("=" * 50)
    
    for ptype in ['liga', 'tipster', 'market']:
        patterns = bb.get_patterns(pattern_type=ptype)
        if patterns:
            print(f"\n{ptype.upper()}:")
            for p in patterns[:5]:
                print(f"  {p['pattern_key']}: {p['success_rate']:.1%} success rate ({p['observed_count']} obs)")

def cmd_help():
    """Muestra ayuda."""
    print("""
📖 COMANDOS DISPONIBLES

  stats                 - Muestra estadísticas generales
  list                  - Lista todos los tipsters
  add <handle> [source]  - Agrega un tipster
  remove <handle>        - Deja de seguir un tipster
  lowroi [threshold]     - Muestra tipsters con ROI bajo (default: -5%)
  dashboard             - Genera dashboard HTML
  run                   - Ejecuta un ciclo completo
  continuous            - Ejecuta orquestador continuamente
  events                - Muestra eventos recientes del blackboard
  patterns              - Muestra patrones descubiertos
  help                  - Muestra esta ayuda

EJEMPLOS:
  python3 betting_cli.py stats
  python3 betting_cli.py add JoseTipster x "Especialista en Premier"
  python3 betting_cli.py lowroi -10
  python3 betting_cli.py run
""")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        cmd_help()
        sys.exit(0)
    
    cmd = sys.argv[1].lower()
    
    if cmd == "stats":
        cmd_stats()
    elif cmd == "list":
        cmd_list_tipsters()
    elif cmd == "add" and len(sys.argv) >= 3:
        cmd_add_tipster(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "x", 
                       sys.argv[4] if len(sys.argv) > 4 else "")
    elif cmd == "remove" and len(sys.argv) >= 3:
        cmd_remove_tipster(sys.argv[2])
    elif cmd == "lowroi":
        threshold = float(sys.argv[2]) if len(sys.argv) > 2 else -5.0
        cmd_low_roi(threshold)
    elif cmd == "dashboard":
        cmd_dashboard()
    elif cmd == "run":
        cmd_run_cycle()
    elif cmd == "continuous":
        cmd_run_orchestrator_continuous()
    elif cmd == "events":
        cmd_events()
    elif cmd == "patterns":
        cmd_patterns()
    elif cmd in ["help", "--help", "-h"]:
        cmd_help()
    else:
        print(f"❌ Comando desconocido: {cmd}")
        print("   Usa 'python3 betting_cli.py help' para ver comandos disponibles")