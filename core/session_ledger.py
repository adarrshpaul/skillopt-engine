"""
Append-only session event ledger inspired by DeepSeek Harness's SessionEvent log.
Every model-visible fact and execution action is logged here.
Invariant: Model-Visible ⟺ Logged.
"""
import json
import time
import uuid
import sqlite3
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional, List, Dict, Any, Union
from contracts import SessionLedger

@dataclass
class SessionEvent:
    event_type: str          # turn/start, step/start, user/message, assistant/chunk,
                             # assistant/message, tool/call, tool/result, turn/end,
                             # guard/denied, guard/ask, review/result, compaction/triggered
    seq: int = 0
    timestamp: float = field(default_factory=time.time)
    session_id: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)
    tokens_in: int = 0
    tokens_out: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SessionEvent':
        return cls(**data)


class JSONLSessionLedger:
    """JSONL backend — human-readable, append-only, trivially greppable and replayable."""

    def __init__(self, path: Union[str, Path], session_id: str = ""):
        self.path = Path(path)
        self.session_id = session_id or uuid.uuid4().hex[:8]
        self._seq = 0
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Restore sequence counter if file already exists
        if self.path.exists():
            existing_events = self.replay(0)
            if existing_events:
                self._seq = max(e.seq for e in existing_events)

    def append(self, event: Union[SessionEvent, Dict[str, Any]]) -> int:
        self._seq += 1
        if isinstance(event, dict):
            if "event_type" not in event:
                raise ValueError("Event dict must contain 'event_type'")
            event_obj = SessionEvent(
                event_type=event["event_type"],
                seq=self._seq,
                session_id=event.get("session_id", self.session_id),
                payload=event.get("payload", {}),
                tokens_in=event.get("tokens_in", 0),
                tokens_out=event.get("tokens_out", 0),
                timestamp=event.get("timestamp", time.time())
            )
        else:
            event.seq = self._seq
            if not event.session_id:
                event.session_id = self.session_id
            event_obj = event

        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event_obj.to_dict()) + "\n")
            f.flush()
        return self._seq

    def replay(self, from_seq: int = 0) -> List[SessionEvent]:
        events: List[SessionEvent] = []
        if not self.path.exists():
            return events
        with open(self.path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    event = SessionEvent.from_dict(data)
                    if event.seq >= from_seq:
                        events.append(event)
                except json.JSONDecodeError:
                    continue
        return events

    def get_events_by_type(self, event_type: str) -> List[SessionEvent]:
        return [e for e in self.replay(0) if e.event_type == event_type]

    def get_token_usage(self) -> Dict[str, int]:
        events = self.replay(0)
        return {
            "total_tokens_in": sum(e.tokens_in for e in events),
            "total_tokens_out": sum(e.tokens_out for e in events),
            "total_tokens": sum(e.tokens_in + e.tokens_out for e in events),
        }

    def fork(self, boundary_seq: int) -> 'JSONLSessionLedger':
        """Forks the session at boundary_seq into a new child ledger."""
        child_id = f"{self.session_id}_fork_{uuid.uuid4().hex[:6]}"
        child_path = self.path.parent / f"session_{child_id}.jsonl"
        child_ledger = JSONLSessionLedger(child_path, session_id=child_id)
        for event in self.replay(0):
            if event.seq <= boundary_seq:
                child_ledger.append(event)
        return child_ledger


class SQLiteSessionLedger:
    """SQLite backend — high concurrency, indexed querying, structured replay."""

    def __init__(self, db_path: Union[str, Path], session_id: str = ""):
        self.db_path = Path(db_path)
        self.session_id = session_id or uuid.uuid4().hex[:8]
        self._seq = 0
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self.db_path))

    def _init_db(self) -> None:
        with self._get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS session_events (
                    seq INTEGER PRIMARY KEY,
                    session_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    payload TEXT NOT NULL,
                    tokens_in INTEGER DEFAULT 0,
                    tokens_out INTEGER DEFAULT 0
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_session_id ON session_events(session_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_event_type ON session_events(event_type)")
            cursor = conn.cursor()
            cursor.execute("SELECT COALESCE(MAX(seq), 0) FROM session_events WHERE session_id = ?", (self.session_id,))
            row = cursor.fetchone()
            self._seq = row[0] if row else 0

    def append(self, event: Union[SessionEvent, Dict[str, Any]]) -> int:
        self._seq += 1
        if isinstance(event, dict):
            event_type = event["event_type"]
            session_id = event.get("session_id", self.session_id)
            timestamp = event.get("timestamp", time.time())
            payload = json.dumps(event.get("payload", {}))
            tokens_in = event.get("tokens_in", 0)
            tokens_out = event.get("tokens_out", 0)
        else:
            event.seq = self._seq
            event_type = event.event_type
            session_id = event.session_id or self.session_id
            timestamp = event.timestamp
            payload = json.dumps(event.payload)
            tokens_in = event.tokens_in
            tokens_out = event.tokens_out

        with self._get_conn() as conn:
            conn.execute("""
                INSERT INTO session_events (seq, session_id, event_type, timestamp, payload, tokens_in, tokens_out)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (self._seq, session_id, event_type, timestamp, payload, tokens_in, tokens_out))
        return self._seq

    def replay(self, from_seq: int = 0) -> List[SessionEvent]:
        events = []
        with self._get_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT seq, session_id, event_type, timestamp, payload, tokens_in, tokens_out
                FROM session_events
                WHERE session_id = ? AND seq >= ?
                ORDER BY seq ASC
            """, (self.session_id, from_seq))
            for row in cursor.fetchall():
                seq, s_id, e_type, ts, payload_str, t_in, t_out = row
                events.append(SessionEvent(
                    seq=seq,
                    session_id=s_id,
                    event_type=e_type,
                    timestamp=ts,
                    payload=json.loads(payload_str),
                    tokens_in=t_in,
                    tokens_out=t_out
                ))
        return events

    def fork(self, boundary_seq: int) -> 'SQLiteSessionLedger':
        child_id = f"{self.session_id}_fork_{uuid.uuid4().hex[:6]}"
        child = SQLiteSessionLedger(self.db_path, session_id=child_id)
        for event in self.replay(0):
            if event.seq <= boundary_seq:
                child.append(event)
        return child
