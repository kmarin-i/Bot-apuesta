#!/usr/bin/env python3
"""
Blackboard - Sistema de eventos compartido entre agentes.
Todos los agentes publican y escuchan eventos aquí.
Es el "sistema nervioso" del orquestador.
"""

import sqlite3
import json
import uuid
from datetime import datetime
from typing import List, Callable, Optional
from collections import defaultdict

from shared.models import AgentEvent, EventType

DB_PATH = "/opt/data/proyectos/apuestas-agent/data/agent_blackboard.db"

class Blackboard:
    """
    Sistema de pizarra compartida donde todos los agentes publican eventos.
    Los agentes pueden suscribirse a tipos específicos de eventos.
    """
    
    def __init__(self):
        self._init_db()
        self._subscribers = defaultdict(list)  # event_type -> [callback_functions]
        self._event_cache = {}  # cache local de últimos eventos
    
    def _init_db(self):
        """Inicializa las tablas del blackboard."""
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # Tabla principal de eventos
        c.execute('''CREATE TABLE IF NOT EXISTS events (
            id TEXT PRIMARY KEY,
            event_type TEXT NOT NULL,
            publisher TEXT NOT NULL,
            payload TEXT,
            timestamp TEXT,
            confidence REAL DEFAULT 1.0,
            event_references TEXT,
            processed_by TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )''')
        
        # Tabla de subscribers
        c.execute('''CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            subscriber_agent TEXT NOT NULL,
            callback_function TEXT,
            active INTEGER DEFAULT 1
        )''')
        
        # Tabla de patrones descubiertos
        c.execute('''CREATE TABLE IF NOT EXISTS patterns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pattern_type TEXT,
            pattern_key TEXT,
            observed_count INTEGER DEFAULT 0,
            success_count INTEGER DEFAULT 0,
            success_rate REAL DEFAULT 0.0,
            avg_roi REAL DEFAULT 0.0,
            confidence REAL DEFAULT 0.0,
            discovered_by TEXT,
            discovered_at TEXT,
            last_verified TEXT,
            active INTEGER DEFAULT 1,
            weight REAL DEFAULT 1.0,
            UNIQUE(pattern_type, pattern_key)
        )''')
        
        # Tabla de performance de agentes
        c.execute('''CREATE TABLE IF NOT EXISTS agent_performance (
            agent_id TEXT PRIMARY KEY,
            agent_type TEXT,
            total_events INTEGER DEFAULT 0,
            accuracy REAL DEFAULT 0.0,
            avg_response_time REAL DEFAULT 0.0,
            success_rate REAL DEFAULT 0.0,
            confidence REAL DEFAULT 1.0,
            events_history TEXT,
            last_updated TEXT
        )''')
        
        # Índice para búsqueda rápida
        c.execute('CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_patterns_key ON patterns(pattern_type, pattern_key)')
        
        conn.commit()
        conn.close()
    
    def publish(self, event: AgentEvent) -> str:
        """Publica un evento en el blackboard. Retorna el ID del evento."""
        event.id = event.id or str(uuid.uuid4())
        event.timestamp = event.timestamp or datetime.now().isoformat()
        
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        c.execute('''INSERT OR REPLACE INTO events 
            (id, event_type, publisher, payload, timestamp, confidence, event_references, processed_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
            (event.id, event.event_type, event.publisher, json.dumps(event.payload),
             event.timestamp, event.confidence, json.dumps(event.references),
             json.dumps(event.processed_by)))
        
        conn.commit()
        conn.close()
        
        # Notificar subscribers
        self._notify_subscribers(event)
        
        # Guardar en cache
        self._event_cache[event.id] = event
        
        return event.id
    
    def subscribe(self, event_type: str, agent_id: str, callback: Optional[Callable] = None):
        """Suscribe un agente a un tipo de evento."""
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        c.execute('''INSERT OR IGNORE INTO subscriptions (event_type, subscriber_agent, callback_function)
                     VALUES (?, ?, ?)''',
                  (event_type, agent_id, str(callback) if callback else None))
        
        conn.commit()
        conn.close()
        
        if callback:
            self._subscribers[event_type].append(callback)
    
    def _notify_subscribers(self, event: AgentEvent):
        """Notifica a todos los subscribers de un evento."""
        for callback in self._subscribers.get(event.event_type, []):
            try:
                callback(event)
            except Exception as e:
                print(f"Error en callback para {event.event_type}: {e}")
    
    def get_events(self, event_type: Optional[str] = None, 
                   limit: int = 100, since: Optional[str] = None) -> List[AgentEvent]:
        """Obtiene eventos del blackboard."""
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        
        query = "SELECT * FROM events WHERE 1=1"
        params = []
        
        if event_type:
            query += " AND event_type = ?"
            params.append(event_type)
        
        if since:
            query += " AND timestamp >= ?"
            params.append(since)
        
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)
        
        rows = c.execute(query, params).fetchall()
        conn.close()
        
        events = []
        for row in rows:
            events.append(AgentEvent(
                id=row['id'],
                event_type=row['event_type'],
                publisher=row['publisher'],
                payload=json.loads(row['payload']),
                timestamp=row['timestamp'],
                confidence=row['confidence'],
                references=json.loads(row['references']) if row['references'] else [],
                processed_by=json.loads(row['processed_by']) if row['processed_by'] else []
            ))
        
        return events
    
    def mark_processed(self, event_id: str, agent_id: str):
        """Marca un evento como procesado por un agente."""
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        row = c.execute("SELECT processed_by FROM events WHERE id = ?", (event_id,)).fetchone()
        if row:
            processed = json.loads(row['processed_by'])
            if agent_id not in processed:
                processed.append(agent_id)
            c.execute("UPDATE events SET processed_by = ? WHERE id = ?",
                      (json.dumps(processed), event_id))
        
        conn.commit()
        conn.close()
    
    def discover_pattern(self, pattern_type: str, pattern_key: str, 
                         discovered_by: str, data: dict = None):
        """Registra un nuevo patrón descubierto por cualquier agente."""
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        now = datetime.now().isoformat()
        data = data or {}
        
        c.execute('''INSERT INTO patterns 
            (pattern_type, pattern_key, observed_count, success_count, 
             success_rate, avg_roi, confidence, discovered_by, discovered_at, last_verified)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(pattern_type, pattern_key) DO UPDATE SET
                observed_count = observed_count + 1,
                last_verified = ?''',
            (pattern_type, pattern_key, 
             data.get('observed_count', 1),
             data.get('success_count', 0),
             data.get('success_rate', 0.0),
             data.get('avg_roi', 0.0),
             data.get('confidence', 0.0),
             discovered_by, now, now))
        
        conn.commit()
        conn.close()
    
    def get_patterns(self, pattern_type: Optional[str] = None, 
                     min_confidence: float = 0.0, active_only: bool = True) -> List[dict]:
        """Obtiene patrones descubiertos."""
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        
        query = "SELECT * FROM patterns WHERE 1=1"
        params = []
        
        if pattern_type:
            query += " AND pattern_type = ?"
            params.append(pattern_type)
        
        if min_confidence > 0:
            query += " AND confidence >= ?"
            params.append(min_confidence)
        
        if active_only:
            query += " AND active = 1"
        
        query += " ORDER BY confidence DESC, success_rate DESC"
        
        rows = c.execute(query, params).fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    def update_agent_performance(self, agent_id: str, agent_type: str, 
                                 event_type: str, success: bool, 
                                 response_time: float = 0.0):
        """Actualiza stats de performance de un agente."""
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        now = datetime.now().isoformat()
        
        # Obtener stats actuales
        row = c.execute("SELECT * FROM agent_performance WHERE agent_id = ?", 
                       (agent_id,)).fetchone()
        
        if row:
            # Actualizar existente - handle both tuple and Row types
            if hasattr(row, 'keys'):
                # sqlite3.Row object
                history = json.loads(row['events_history']) if row['events_history'] else []
                total_events = row['total_events']
                avg_response_time = row['avg_response_time']
            else:
                # tuple - columns: agent_id(0), agent_type(1), total_events(2), accuracy(3), avg_response_time(4), success_rate(5), confidence(6), events_history(7), last_updated(8)
                history_str = row[7] if row[7] else '[]'
                history = json.loads(history_str) if isinstance(history_str, str) else []
                total_events = row[2]
                avg_response_time = row[4]
            
            history.append({'event': event_type, 'success': success, 'time': now})
            if len(history) > 100:
                history = history[-100:]
            
            total = total_events + 1
            successes = sum(1 for h in history if h['success'])
            avg_time = (avg_response_time * total_events + response_time) / total
            
            c.execute('''UPDATE agent_performance SET
                total_events = ?,
                success_rate = ?,
                avg_response_time = ?,
                events_history = ?,
                last_updated = ?
                WHERE agent_id = ?''',
                (total, successes/total, avg_time, json.dumps(history), now, agent_id))
        else:
            # Crear nuevo
            history = [{'event': event_type, 'success': success, 'time': now}]
            c.execute('''INSERT INTO agent_performance 
                (agent_id, agent_type, total_events, success_rate, avg_response_time, 
                 events_history, last_updated, confidence)
                VALUES (?, ?, 1, ?, ?, ?, ?, 1.0)''',
                (agent_id, agent_type, 1.0 if success else 0.0, response_time,
                 json.dumps(history), now))
        
        conn.commit()
        conn.close()
    
    def get_agent_performance(self, agent_id: str) -> Optional[dict]:
        """Obtiene performance de un agente."""
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        
        row = c.execute("SELECT * FROM agent_performance WHERE agent_id = ?", 
                       (agent_id,)).fetchone()
        conn.close()
        
        return dict(row) if row else None
    
    def adjust_agent_confidence(self, agent_id: str, adjustment: float):
        """
        Ajusta la confianza de un agente.
        Si adjustment > 0, aumenta confianza (buen desempeño).
        Si adjustment < 0, reduce confianza (mal desempeño).
        """
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        row = c.execute("SELECT confidence FROM agent_performance WHERE agent_id = ?",
                       (agent_id,)).fetchone()
        
        if row:
            new_conf = max(0.1, min(1.0, row['confidence'] + adjustment))
            c.execute("UPDATE agent_performance SET confidence = ?, last_updated = ? WHERE agent_id = ?",
                      (new_conf, datetime.now().isoformat(), agent_id))
        
        conn.commit()
        conn.close()
    
    def get_high_value_picks(self, min_confidence: float = 0.7) -> List[dict]:
        """Obtiene picks de alta calidad según patrones descubiertos."""
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        picks = c.execute('''SELECT * FROM events 
            WHERE event_type = 'pick.detected'
            AND json_extract(payload, '$.confidence') >= ?
            ORDER BY timestamp DESC
            LIMIT 20''', (min_confidence,)).fetchall()
        
        conn.close()
        
        return [json.loads(row['payload']) for row in picks]
    
    def close(self):
        """Cierra conexiones."""
        pass  # SQLite connection closes automatically