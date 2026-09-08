import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.models.schemas import MessageRecord, SessionDetail


@dataclass
class Session:
    session_id: str
    customer_id: str | None = None
    messages: list[MessageRecord] = field(default_factory=list)


class SessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}
        self._lock = threading.Lock()

    def create_session(self, customer_id: str | None = None) -> str:
        session_id = str(uuid.uuid4())
        with self._lock:
            self._sessions[session_id] = Session(session_id=session_id, customer_id=customer_id)
        return session_id

    def get_or_create(self, session_id: str | None, customer_id: str | None = None) -> Session:
        with self._lock:
            if session_id and session_id in self._sessions:
                session = self._sessions[session_id]
                if customer_id and not session.customer_id:
                    session.customer_id = customer_id
                return session

            new_id = session_id or str(uuid.uuid4())
            session = Session(session_id=new_id, customer_id=customer_id)
            self._sessions[new_id] = session
            return session

    def get_session(self, session_id: str) -> Session | None:
        with self._lock:
            return self._sessions.get(session_id)

    def add_message(self, session_id: str, role: str, content: str) -> None:
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                raise KeyError(f"Session '{session_id}' not found.")
            session.messages.append(
                MessageRecord(
                    role=role,  # type: ignore[arg-type]
                    content=content,
                    timestamp=datetime.now(timezone.utc),
                )
            )

    def get_history(self, session_id: str, max_turns: int) -> list[MessageRecord]:
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return []
            return session.messages[-max_turns:]

    def to_detail(self, session_id: str) -> SessionDetail | None:
        with self._lock:
            session = self._sessions.get(session_id)
            if not session:
                return None
            return SessionDetail(
                session_id=session.session_id,
                customer_id=session.customer_id,
                messages=list(session.messages),
            )


session_store = SessionStore()
