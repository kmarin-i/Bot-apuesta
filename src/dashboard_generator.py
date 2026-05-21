#!/usr/bin/env python3
"""
Dashboard Generator - Crea un dashboard HTML con stats del sistema.
Se actualiza cada vez que corre el orchestrator.
"""

import sqlite3
import json
from datetime import datetime
from pathlib import Path

DB_PATH = "/opt/data/proyectos/apuestas-agent/data/matches.db"
OUTPUT_PATH = "/opt/data/proyectos/apuestas-agent/data/dashboard.html"

class DashboardGenerator:
    """
    Genera dashboard HTML con estadísticas del sistema de apuestas.
    """
    
    def generate(self) -> str:
        """Genera el HTML completo del dashboard."""
        stats = self.collect_stats()
        
        html = self._generate_html(stats)
        
        with open(OUTPUT_PATH, 'w') as f:
            f.write(html)
        
        return OUTPUT_PATH
    
    def collect_stats(self) -> dict:
        """Recolecta todas las estadísticas del sistema."""
        conn = sqlite3.connect(DB_PATH)
        
        stats = {}
        
        # Stats de matches
        try:
            total_matches = conn.execute("SELECT COUNT(*) FROM matches").fetchone()[0]
            matches_with_result = conn.execute("SELECT COUNT(*) FROM matches WHERE result IS NOT NULL").fetchone()[0]
            stats['total_matches'] = total_matches
            stats['matches_with_result'] = matches_with_result
            stats['upcoming_matches'] = total_matches - matches_with_result
        except:
            stats['total_matches'] = 0
            stats['matches_with_result'] = 0
            stats['upcoming_matches'] = 0
        
        # Stats de tipsters
        try:
            total_tipsters = conn.execute("SELECT COUNT(*) FROM tipsters").fetchone()[0]
            stats['total_tipsters'] = total_tipsters
        except:
            stats['total_tipsters'] = 0
        
        # Stats de picks
        try:
            total_picks = conn.execute("SELECT COUNT(*) FROM tipster_picks").fetchone()[0]
            checked_picks = conn.execute("SELECT COUNT(*) FROM tipster_picks WHERE result_checked=1").fetchone()[0]
            wins = conn.execute("SELECT COUNT(*) FROM tipster_picks WHERE result='WIN'").fetchone()[0]
            losses = conn.execute("SELECT COUNT(*) FROM tipster_picks WHERE result='LOSS'").fetchone()[0]
            
            stats['total_picks'] = total_picks
            stats['checked_picks'] = checked_picks
            stats['wins'] = wins
            stats['losses'] = losses
            stats['win_rate'] = (wins / checked_picks * 100) if checked_picks > 0 else 0
            
            total_profit = conn.execute("SELECT SUM(profit) FROM tipster_picks WHERE result_checked=1").fetchone()[0] or 0
            stats['total_profit'] = total_profit
        except Exception as e:
            stats['total_picks'] = 0
            stats['checked_picks'] = 0
            stats['wins'] = 0
            stats['losses'] = 0
            stats['win_rate'] = 0
            stats['total_profit'] = 0
        
        # Matches por liga
        try:
            liga_stats = conn.execute('''
                SELECT liga, COUNT(*) as total, 
                       SUM(CASE WHEN result IS NOT NULL THEN 1 ELSE 0 END) as with_result
                FROM matches 
                GROUP BY liga
            ''').fetchall()
            stats['liga_stats'] = liga_stats
        except:
            stats['liga_stats'] = []
        
        # Top tipsters
        try:
            top_tipsters = conn.execute('''
                SELECT tipster_handle, 
                       COUNT(*) as picks,
                       SUM(CASE WHEN result='WIN' THEN 1 ELSE 0 END) as wins,
                       SUM(profit) as profit
                FROM tipster_picks 
                WHERE result_checked=1
                GROUP BY tipster_handle
                ORDER BY profit DESC
                LIMIT 5
            ''').fetchall()
            stats['top_tipsters'] = top_tipsters
        except:
            stats['top_tipsters'] = []
        
        # Últimos resultados
        try:
            recent_results = conn.execute('''
                SELECT match_home, match_away, result, 
                       home_score, away_score, profit
                FROM tipster_picks 
                WHERE result_checked=1
                ORDER BY checked_at DESC
                LIMIT 10
            ''').fetchall()
            stats['recent_results'] = recent_results
        except:
            stats['recent_results'] = []
        
        conn.close()
        stats['generated_at'] = datetime.now().isoformat()
        
        return stats
    
    def _generate_html(self, stats: dict) -> str:
        """Genera el HTML del dashboard."""
        # Colores
        green = '#22c55e'
        red = '#ef4444'
        blue = '#3b82f6'
        yellow = '#eab308'
        
        # Win rate color
        win_rate = stats['win_rate']
        wr_color = green if win_rate >= 55 else (yellow if win_rate >= 45 else red)
        
        # Profit color
        profit = stats['total_profit']
        profit_color = green if profit >= 0 else red
        
        html = f'''<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Bet Agent Dashboard</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ 
            font-family: 'Segoe UI', system-ui, sans-serif; 
            background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
            color: #f1f5f9; 
            min-height: 100vh;
            padding: 20px;
        }}
        .header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 30px;
        }}
        h1 {{ color: #38bdf8; font-size: 28px; }}
        .subtitle {{ color: #94a3b8; font-size: 14px; }}
        
        .grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}
        
        .card {{
            background: rgba(255,255,255,0.05);
            border-radius: 16px;
            padding: 24px;
            border: 1px solid rgba(255,255,255,0.1);
        }}
        .card-title {{ color: #94a3b8; font-size: 12px; text-transform: uppercase; letter-spacing: 1px; }}
        .card-value {{ font-size: 36px; font-weight: 700; margin-top: 8px; }}
        .card-value.green {{ color: {green}; }}
        .card-value.red {{ color: {red}; }}
        .card-value.blue {{ color: {blue}; }}
        .card-value.yellow {{ color: {yellow}; }}
        
        .section {{ margin-bottom: 30px; }}
        h2 {{ color: #38bdf8; font-size: 18px; margin-bottom: 16px; border-left: 4px solid #38bdf8; padding-left: 12px; }}
        
        table {{ width: 100%; border-collapse: collapse; }}
        th {{ text-align: left; color: #94a3b8; font-size: 11px; text-transform: uppercase; padding: 8px 12px; border-bottom: 1px solid rgba(255,255,255,0.1); }}
        td {{ padding: 12px; border-bottom: 1px solid rgba(255,255,255,0.05); }}
        tr:hover {{ background: rgba(255,255,255,0.03); }}
        
        .status-win {{ color: {green}; }}
        .status-loss {{ color: {red}; }}
        
        .badge {{
            display: inline-block;
            padding: 4px 8px;
            border-radius: 6px;
            font-size: 11px;
            font-weight: 600;
        }}
        .badge-green {{ background: rgba(34,197,94,0.2); color: {green}; }}
        .badge-red {{ background: rgba(239,68,68,0.2); color: {red}; }}
        
        .progress-bar {{
            width: 100%;
            height: 8px;
            background: rgba(255,255,255,0.1);
            border-radius: 4px;
            overflow: hidden;
            margin-top: 8px;
        }}
        .progress-fill {{ height: 100%; border-radius: 4px; transition: width 0.5s ease; }}
        
        .agents-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 16px;
        }}
        
        .agent-card {{
            background: rgba(255,255,255,0.03);
            border-radius: 12px;
            padding: 16px;
            border: 1px solid rgba(255,255,255,0.05);
        }}
        .agent-name {{ font-weight: 600; color: #f1f5f9; }}
        .agent-status {{ font-size: 12px; margin-top: 4px; }}
        .status-online {{ color: {green}; }}
        .status-warning {{ color: {yellow}; }}
        .status-offline {{ color: {red}; }}
        
        .footer {{
            text-align: center;
            color: #64748b;
            font-size: 12px;
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid rgba(255,255,255,0.05);
        }}
    </style>
</head>
<body>
    <div class="header">
        <div>
            <h1>🎯 Bet Agent Dashboard</h1>
            <p class="subtitle">Sistema multi-agente de apuestas autónomas</p>
        </div>
        <div style="text-align: right;">
            <div style="font-size: 12px; color: #64748b;">Actualizado</div>
            <div style="font-size: 14px;">{datetime.now().strftime('%Y-%m-%d %H:%M')}</div>
        </div>
    </div>
    
    <div class="grid">
        <div class="card">
            <div class="card-title">Total Picks</div>
            <div class="card-value blue">{stats['total_picks']}</div>
        </div>
        <div class="card">
            <div class="card-title">Win Rate</div>
            <div class="card-value" style="color: {wr_color};">{stats['win_rate']:.1f}%</div>
            <div class="progress-bar">
                <div class="progress-fill" style="width: {stats['win_rate']}%; background: {wr_color};"></div>
            </div>
        </div>
        <div class="card">
            <div class="card-title">Profit Total</div>
            <div class="card-value" style="color: {profit_color};">${profit:.2f}</div>
        </div>
        <div class="card">
            <div class="card-title">Matches en DB</div>
            <div class="card-value">{stats['total_matches']}</div>
        </div>
        <div class="card">
            <div class="card-title">Tipsters</div>
            <div class="card-value">{stats['total_tipsters']}</div>
        </div>
        <div class="card">
            <div class="card-title">W / L</div>
            <div class="card-value">{stats['wins']} <span style="color: {green};">/</span> <span style="color: {red};">{stats['losses']}</span></div>
        </div>
    </div>
    
    <div class="grid">
        <div class="card">
            <div class="card-title">Matches con resultado</div>
            <div class="card-value green">{stats['matches_with_result']}</div>
        </div>
        <div class="card">
            <div class="card-title">Próximos partidos</div>
            <div class="card-value yellow">{stats['upcoming_matches']}</div>
        </div>
    </div>
    
    <div class="section">
        <h2>📊 Estadísticas por Liga</h2>
        <table>
            <thead>
                <tr>
                    <th>Liga</th>
                    <th>Total</th>
                    <th>Con Resultado</th>
                    <th>Tasa</th>
                </tr>
            </thead>
            <tbody>
'''
        
        for liga, total, with_result in stats.get('liga_stats', []):
            rate = (with_result / total * 100) if total > 0 else 0
            html += f'''                <tr>
                    <td>{liga}</td>
                    <td>{total}</td>
                    <td>{with_result}</td>
                    <td>{rate:.0f}%</td>
                </tr>
'''
        
        html += '''            </tbody>
        </table>
    </div>
    
    <div class="section">
        <h2>🏆 Top Tipsters</h2>
        <table>
            <thead>
                <tr>
                    <th>Tipster</th>
                    <th>Picks</th>
                    <th>Wins</th>
                    <th>Win Rate</th>
                    <th>Profit</th>
                </tr>
            </thead>
            <tbody>
'''
        
        for handle, picks, wins, profit in stats.get('top_tipsters', []):
            wr = (wins / picks * 100) if picks > 0 else 0
            wr_color = green if wr >= 55 else (yellow if wr >= 45 else red)
            profit_color = green if profit >= 0 else red
            html += f'''                <tr>
                    <td><span class="badge badge-green">@{handle}</span></td>
                    <td>{picks}</td>
                    <td class="status-win">{wins}</td>
                    <td style="color: {wr_color};">{wr:.1f}%</td>
                    <td style="color: {profit_color};">${profit:.2f}</td>
                </tr>
'''
        
        if not stats.get('top_tipsters'):
            html += '''                <tr><td colspan="5" style="text-align: center; color: #64748b;">Sin datos aún</td></tr>
'''
        
        html += '''            </tbody>
        </table>
    </div>
    
    <div class="section">
        <h2>🤖 Estado de Agentes</h2>
        <div class="agents-grid">
            <div class="agent-card">
                <div class="agent-name">Scraper Agent</div>
                <div class="agent-status status-online">● Activo - Scraping Betexplorer</div>
            </div>
            <div class="agent-card">
                <div class="agent-name">Analyzer Agent</div>
                <div class="agent-status status-online">● Activo - Evaluando picks</div>
            </div>
            <div class="agent-card">
                <div class="agent-name">Alerter Agent</div>
                <div class="agent-status status-online">● Activo - Monitoreando alertas</div>
            </div>
            <div class="agent-card">
                <div class="agent-name">Result Agent</div>
                <div class="agent-status status-online">● Activo - Verificando resultados</div>
            </div>
            <div class="agent-card">
                <div class="agent-name">X Tipster Monitor</div>
                <div class="agent-status status-warning">● Esperando API key de X</div>
            </div>
        </div>
    </div>
    
    <div class="section">
        <h2>📈 Resultados Recientes</h2>
        <table>
            <thead>
                <tr>
                    <th>Partido</th>
                    <th>Resultado</th>
                    <th>Profit</th>
                </tr>
            </thead>
            <tbody>
'''
        
        for home, away, result, hs, as_, profit in stats.get('recent_results', []):
            res_class = 'status-win' if profit >= 0 else 'status-loss'
            html += f'''                <tr>
                    <td>{home} vs {away}</td>
                    <td>{hs}:{as_} ({result})</td>
                    <td class="{res_class}">${profit:.2f}</td>
                </tr>
'''
        
        if not stats.get('recent_results'):
            html += '''                <tr><td colspan="3" style="text-align: center; color: #64748b;">Sin resultados aún</td></tr>
'''
        
        html += f'''            </tbody>
        </table>
    </div>
    
    <div class="footer">
        Bet Agent System v1.0 — Multi-Agent Architecture con Self-Improvement Loop<br>
        Generated: {stats['generated_at']}
    </div>
</body>
</html>'''
        
        return html


if __name__ == "__main__":
    generator = DashboardGenerator()
    path = generator.generate()
    print(f"✅ Dashboard generado: {path}")