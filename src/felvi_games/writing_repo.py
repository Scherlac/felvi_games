"""Persistence for writing-practice sessions, drafts, reviews, and tutor messages."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from felvi_games.db import (
    WritingDraftRevisionRecord,
    WritingPracticeSessionRecord,
    WritingTutorMessageRecord,
    get_engine,
    init_db,
)
from felvi_games.writing_tasks import WritingPracticeTask

_MAX_TIMER_CHECKPOINT_GAP_SECONDS = 2


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _timer_checkpoint_seconds(started_at: datetime, now: datetime) -> int:
    elapsed = max(0, int((now - _as_utc(started_at)).total_seconds()))
    return min(elapsed, _MAX_TIMER_CHECKPOINT_GAP_SECONDS)


@dataclass(frozen=True)
class WritingPracticeSession:
    id: int
    felhasznalo_nev: str
    task_id: str
    task_prompt: str
    task_metadata_json: str
    guide_id: str
    guide_json: str
    status: str
    utc_started_at: datetime
    utc_last_resumed_at: datetime | None
    active_seconds: int
    utc_submitted_at: datetime | None


@dataclass(frozen=True)
class WritingDraftRevision:
    id: int
    session_id: int
    revision_no: int
    draft_text: str
    feedback_json: str | None
    utc_saved_at: datetime


@dataclass(frozen=True)
class WritingTutorMessage:
    id: int
    session_id: int
    role: Literal["user", "assistant"]
    content: str
    utc_created_at: datetime


class WritingPracticeRepository:
    """Persist and retrieve writing sessions scoped to a learner profile name."""

    def __init__(self, db_path: Path | None = None) -> None:
        self._engine = get_engine(db_path)
        init_db(db_path)

    def create_session(
        self,
        felhasznalo_nev: str,
        task: WritingPracticeTask,
    ) -> WritingPracticeSession:
        now = _utc_now()
        record = WritingPracticeSessionRecord(
            felhasznalo_nev=felhasznalo_nev,
            feladat_id=task.task_id,
            feladat_prompt=task.prompt,
            task_metadata_json=json.dumps(task.metadata(), ensure_ascii=False),
            guide_id=task.guide.guide_id,
            guide_json=json.dumps(asdict(task.guide), ensure_ascii=False),
            status="active",
            utc_started_at=now,
            utc_last_resumed_at=now,
            active_seconds=0,
        )
        with Session(self._engine) as session:
            session.add(record)
            session.commit()
            session.refresh(record)
            return self._to_session(record)

    def get_session(self, session_id: int, felhasznalo_nev: str) -> WritingPracticeSession | None:
        with Session(self._engine) as session:
            record = session.get(WritingPracticeSessionRecord, session_id)
            if record is None or record.felhasznalo_nev != felhasznalo_nev:
                return None
            return self._to_session(record)

    def list_sessions(self, felhasznalo_nev: str, limit: int = 20) -> list[WritingPracticeSession]:
        if limit < 1:
            raise ValueError("limit must be positive")
        with Session(self._engine) as session:
            records = session.scalars(
                select(WritingPracticeSessionRecord)
                .where(WritingPracticeSessionRecord.felhasznalo_nev == felhasznalo_nev)
                .order_by(WritingPracticeSessionRecord.utc_started_at.desc())
                .limit(limit)
            ).all()
            return [self._to_session(record) for record in records]

    def list_revisions(
        self,
        session_id: int,
        felhasznalo_nev: str,
    ) -> list[WritingDraftRevision]:
        with Session(self._engine) as session:
            if not self._owns_session(session, session_id, felhasznalo_nev):
                return []
            records = session.scalars(
                select(WritingDraftRevisionRecord)
                .where(WritingDraftRevisionRecord.session_id == session_id)
                .order_by(WritingDraftRevisionRecord.revision_no)
            ).all()
            return [self._to_revision(record) for record in records]

    def list_messages(
        self,
        session_id: int,
        felhasznalo_nev: str,
    ) -> list[WritingTutorMessage]:
        with Session(self._engine) as session:
            if not self._owns_session(session, session_id, felhasznalo_nev):
                return []
            records = session.scalars(
                select(WritingTutorMessageRecord)
                .where(WritingTutorMessageRecord.session_id == session_id)
                .order_by(WritingTutorMessageRecord.id)
            ).all()
            return [self._to_message(record) for record in records]

    def save_chat_message(
        self,
        session_id: int,
        felhasznalo_nev: str,
        role: Literal["user", "assistant"],
        content: str,
    ) -> WritingTutorMessage:
        if role not in ("user", "assistant"):
            raise ValueError("Chat message role must be 'user' or 'assistant'.")
        if not content.strip():
            raise ValueError("Chat message content must not be empty.")
        record = WritingTutorMessageRecord(
            session_id=session_id,
            role=role,
            content=content,
            utc_created_at=_utc_now(),
        )
        with Session(self._engine) as session:
            self._require_active_session(session, session_id, felhasznalo_nev)
            session.add(record)
            session.commit()
            session.refresh(record)
            return self._to_message(record)

    def save_revision(
        self,
        session_id: int,
        felhasznalo_nev: str,
        draft_text: str,
    ) -> WritingDraftRevision:
        with Session(self._engine) as session:
            writing_session = self._require_active_session(session, session_id, felhasznalo_nev)
            last_revision = session.scalar(
                select(WritingDraftRevisionRecord)
                .where(WritingDraftRevisionRecord.session_id == session_id)
                .order_by(WritingDraftRevisionRecord.revision_no.desc())
                .limit(1)
            )
            if last_revision is not None and last_revision.draft_text == draft_text:
                return self._to_revision(last_revision)
            record = WritingDraftRevisionRecord(
                session_id=session_id,
                revision_no=(last_revision.revision_no if last_revision else 0) + 1,
                draft_text=draft_text,
                feedback_json=None,
                utc_saved_at=_utc_now(),
            )
            writing_session.status = "active"
            session.add(record)
            session.commit()
            session.refresh(record)
            return self._to_revision(record)

    def save_review(
        self,
        session_id: int,
        revision_id: int,
        felhasznalo_nev: str,
        feedback_json: str,
    ) -> WritingDraftRevision:
        with Session(self._engine) as session:
            self._require_active_session(session, session_id, felhasznalo_nev)
            record = session.get(WritingDraftRevisionRecord, revision_id)
            if record is None or record.session_id != session_id:
                raise LookupError(f"Revision {revision_id} does not belong to session {session_id}.")
            record.feedback_json = feedback_json
            session.commit()
            session.refresh(record)
            return self._to_revision(record)

    def pause_session(self, session_id: int, felhasznalo_nev: str) -> WritingPracticeSession:
        with Session(self._engine) as session:
            record = self._require_active_session(session, session_id, felhasznalo_nev)
            now = _utc_now()
            if record.utc_last_resumed_at is None:
                raise ValueError("An active session must have a running timer.")
            record.active_seconds += _timer_checkpoint_seconds(record.utc_last_resumed_at, now)
            record.utc_last_resumed_at = None
            record.status = "paused"
            session.commit()
            session.refresh(record)
            return self._to_session(record)

    def resume_session(self, session_id: int, felhasznalo_nev: str) -> WritingPracticeSession:
        with Session(self._engine) as session:
            record = self._require_owned_session(session, session_id, felhasznalo_nev)
            if record.status != "paused":
                raise ValueError("Only paused sessions can be resumed.")
            record.utc_last_resumed_at = _utc_now()
            record.status = "active"
            session.commit()
            session.refresh(record)
            return self._to_session(record)

    def submit_session(self, session_id: int, felhasznalo_nev: str) -> WritingPracticeSession:
        with Session(self._engine) as session:
            record = self._require_active_session(session, session_id, felhasznalo_nev)
            now = _utc_now()
            if record.utc_last_resumed_at is not None:
                record.active_seconds += _timer_checkpoint_seconds(record.utc_last_resumed_at, now)
            record.utc_last_resumed_at = None
            record.utc_submitted_at = now
            record.status = "submitted"
            session.commit()
            session.refresh(record)
            return self._to_session(record)

    def checkpoint_active_time(self, session_id: int, felhasznalo_nev: str) -> int:
        with Session(self._engine) as session:
            record = self._require_active_session(session, session_id, felhasznalo_nev)
            if record.utc_last_resumed_at is None:
                raise ValueError("An active session must have a running timer.")
            now = _utc_now()
            record.active_seconds += _timer_checkpoint_seconds(record.utc_last_resumed_at, now)
            record.utc_last_resumed_at = now
            session.commit()
            return record.active_seconds

    def elapsed_seconds(self, session_id: int, felhasznalo_nev: str) -> int:
        record = self.get_session(session_id, felhasznalo_nev)
        if record is None:
            raise LookupError(f"Writing practice session {session_id} was not found.")
        if record.status != "active" or record.utc_last_resumed_at is None:
            return record.active_seconds
        return record.active_seconds + _timer_checkpoint_seconds(record.utc_last_resumed_at, _utc_now())

    @staticmethod
    def _owns_session(session: Session, session_id: int, felhasznalo_nev: str) -> bool:
        record = session.get(WritingPracticeSessionRecord, session_id)
        return record is not None and record.felhasznalo_nev == felhasznalo_nev

    @staticmethod
    def _require_owned_session(
        session: Session,
        session_id: int,
        felhasznalo_nev: str,
    ) -> WritingPracticeSessionRecord:
        record = session.get(WritingPracticeSessionRecord, session_id)
        if record is None or record.felhasznalo_nev != felhasznalo_nev:
            raise LookupError(f"Writing practice session {session_id} was not found.")
        return record

    @classmethod
    def _require_active_session(
        cls,
        session: Session,
        session_id: int,
        felhasznalo_nev: str,
    ) -> WritingPracticeSessionRecord:
        record = cls._require_owned_session(session, session_id, felhasznalo_nev)
        if record.status != "active":
            raise ValueError("Writing practice session is not active.")
        return record

    @staticmethod
    def _to_session(record: WritingPracticeSessionRecord) -> WritingPracticeSession:
        return WritingPracticeSession(
            id=record.id,
            felhasznalo_nev=record.felhasznalo_nev,
            task_id=record.feladat_id,
            task_prompt=record.feladat_prompt,
            task_metadata_json=record.task_metadata_json,
            guide_id=record.guide_id,
            guide_json=record.guide_json,
            status=record.status,
            utc_started_at=_as_utc(record.utc_started_at),
            utc_last_resumed_at=(
                _as_utc(record.utc_last_resumed_at)
                if record.utc_last_resumed_at is not None
                else None
            ),
            active_seconds=record.active_seconds,
            utc_submitted_at=(
                _as_utc(record.utc_submitted_at)
                if record.utc_submitted_at is not None
                else None
            ),
        )

    @staticmethod
    def _to_revision(record: WritingDraftRevisionRecord) -> WritingDraftRevision:
        return WritingDraftRevision(
            id=record.id,
            session_id=record.session_id,
            revision_no=record.revision_no,
            draft_text=record.draft_text,
            feedback_json=record.feedback_json,
            utc_saved_at=_as_utc(record.utc_saved_at),
        )

    @staticmethod
    def _to_message(record: WritingTutorMessageRecord) -> WritingTutorMessage:
        return WritingTutorMessage(
            id=record.id,
            session_id=record.session_id,
            role=record.role,
            content=record.content,
            utc_created_at=_as_utc(record.utc_created_at),
        )
