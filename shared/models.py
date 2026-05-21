#!/usr/bin/env python3
"""
Shared Models para el sistema multi-agente.
Define las estructuras de datos compartidas.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional, List
from enum import Enum
import json

class EventType(Enum):
    """Tipos de eventos en el blackboard."""
    PICK_DETECTED = "pick.detected"
    PICK_EVALUATED = "pick.evaluated"
    PICK_ALERTED = "pick.alerted"
    PICK_RESULT = "pick.result"
    AGENT_PERFORMANCE_ALERT = "agent.performance.alert"
    PATTERN_DISCOVERED = "pattern.discovered"
    SYSTEM_ADJUSTMENT = "system.adjustment"

class Market(Enum):
    """Mercados de apuestas."""
    DC_1X = "DC_1X"      # Local gana o empata
    DC_X2 = "DC_X2"      # Empata o visitante
    DC_12 = "DC_12"      # No empata
    ML_1 = "ML_1"        # Moneyline local
    ML_X = "ML_X"        # Empate
    ML_2 = "ML_2"        # Moneyline visitante
    O_U = "O_U"          # Over/Under

@dataclass
class AgentEvent:
    """Evento en el blackboard."""
    id: str
    event_type: str
    publisher: str
    payload: dict
    timestamp: str
    confidence: float = 1.0
    references: List[str] = field(default_factory=list)
    processed_by: List[str] = field(default_factory=list)
    
    def to_dict(self):
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data):
        return cls(**data)

@dataclass
class Pick:
    """Un pick de apuestas."""
    id: Optional[int] = None
    tipster_handle: str = ""
    match_home: str = ""
    match_away: str = ""
    league: str = ""
    market: str = ""
    pick: str = ""  # e.g., "1X", "X2", "12"
    odds: float = 0.0
    stake: float = 50.0
    match_time: str = ""
    pick_time: str = ""
    value_score: float = 0.0
    confidence: float = 0.0
    roi_expected: float = 0.0
    status: str = "pending"  # pending, alerted, won, lost, void
    result: Optional[str] = None
    profit: float = 0.0
    alert_channel: str = ""
    notes: str = ""
    
    def to_dict(self):
        d = asdict(self)
        d['market'] = self.market.value if isinstance(self.market, Market) else self.market
        return d

@dataclass
class Pattern:
    """Patrón descubierto por cualquier agente."""
    id: Optional[int] = None
    pattern_type: str = ""  # "tipster", "liga", "market", "odds_range", "time"
    pattern_key: str = ""   # e.g., "@elperrote", "libertadores", "DC_1X", "1.20-1.40"
    observed_count: int = 0
    success_count: int = 0
    success_rate: float = 0.0
    avg_roi: float = 0.0
    confidence: float = 0.0
    discovered_by: str = ""
    discovered_at: str = ""
    last_verified: str = ""
    active: bool = True
    weight: float = 1.0  # Multiplier para decisiones futuras
    
    def to_dict(self):
        return asdict(self)

@dataclass
class AgentPerformance:
    """Performance de un agente."""
    agent_id: str = ""
    agent_type: str = ""
    total_events: int = 0
    accuracy: float = 0.0
    avg_response_time: float = 0.0
    success_rate: float = 0.0
    last_updated: str = ""
    confidence: float = 1.0  # 0-1, inicia en 1
    events_history: List[dict] = field(default_factory=list)
    
    def to_dict(self):
        return asdict(self)

@dataclass
class TipsterProfile:
    """Perfil de un tipster con stats dinámicas."""
    handle: str = ""
    source: str = "x"
    total_picks: int = 0
    wins: int = 0
    losses: int = 0
    voids: int = 0
    win_rate: float = 0.0
    total_profit: float = 0.0
    roi: float = 0.0
    best_league: str = ""
    best_market: str = ""
    avg_odds: float = 0.0
    last_pick_time: str = ""
    added_date: str = ""
    active: bool = True
    confidence: float = 1.0  # Se reduce si tiene mal ROI
    tags: List[str] = field(default_factory=list)  # ["high_roi", "libertadores_specialist", etc]
    
    def to_dict(self):
        return asdict(self)