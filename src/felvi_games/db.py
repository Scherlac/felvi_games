"""Persistence layer – SQLAlchemy 2.x + SQLite."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    select,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    relationship,
)

from felvi_games.config import (
    get_assets_dir,
    get_db_path,
    relative_asset_path,
    resolve_asset,
)
from felvi_games.models import Ertekeles, Feladat, FeladatCsoport, Menet, _list_to_json

# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


def get_engine(db_path: Path | None = None):
    path = db_path or get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(f"sqlite:///{path}", echo=False)


# ---------------------------------------------------------------------------
# ORM base & tables
# ---------------------------------------------------------------------------


class Base(DeclarativeBase):
    pass


class FelhasznaloRecord(Base):
    """A registered player."""

    __tablename__ = "felhasznalok"

    nev: Mapped[str] = mapped_column(String(64), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    menetek: Mapped[list["MenetRecord"]] = relationship(
        back_populates="felhasznalo", cascade="all, delete-orphan"
    )


class MenetRecord(Base):
    """A single playing session."""

    __tablename__ = "menetek"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    felhasznalo_nev: Mapped[str] = mapped_column(
        ForeignKey("felhasznalok.nev", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    targy: Mapped[str] = mapped_column(String(16), nullable=False)
    szint: Mapped[str] = mapped_column(String(32), nullable=False)
    feladat_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    megoldott: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pont: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    felhasznalo: Mapped["FelhasznaloRecord"] = relationship(back_populates="menetek")
    megoldasok: Mapped[list["MegoldasRecord"]] = relationship(back_populates="menet")

    def to_domain(self) -> Menet:
        return Menet(
            id=self.id,
            felhasznalo=self.felhasznalo_nev,
            targy=self.targy,
            szint=self.szint,
            feladat_limit=self.feladat_limit,
            megoldott=self.megoldott,
            pont=self.pont,
            started_at=self.started_at,
            ended_at=self.ended_at,
        )


class FeladatCsoportRecord(Base):
    """Összetartozó részfeladatok csoportja (pl. 3a, 3b, 3c)."""

    __tablename__ = "feladat_csoportok"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    targy: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    szint: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    feladat_sorszam: Mapped[str] = mapped_column(String(16), nullable=False)
    ev: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    valtozat: Mapped[int | None] = mapped_column(Integer, nullable=True)
    kontextus: Mapped[str | None] = mapped_column(Text, nullable=True)
    abra_van: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    feladat_oldal: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fl_pdf_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    ut_pdf_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    fl_szoveg_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    ut_szoveg_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    sorrend_kotelezo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    max_pont_ossz: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    def to_domain(self) -> FeladatCsoport:
        return FeladatCsoport.from_record(self)


class FeladatRecord(Base):
    """Persisted feladat with compiled assets."""

    __tablename__ = "feladatok"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    targy: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    neh: Mapped[int] = mapped_column(Integer, nullable=False)
    szint: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    kerdes: Mapped[str] = mapped_column(Text, nullable=False)
    helyes_valasz: Mapped[str] = mapped_column(Text, nullable=False)
    hint: Mapped[str] = mapped_column(Text, nullable=False)
    magyarazat: Mapped[str] = mapped_column(Text, nullable=False)

    # Source tracking
    ev: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    valtozat: Mapped[int | None] = mapped_column(Integer, nullable=True)
    feladat_sorszam: Mapped[str | None] = mapped_column(String(16), nullable=True)

    # Group membership (no FK constraint – SQLite compatible)
    csoport_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    csoport_sorrend: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Task type & scoring
    feladat_tipus: Mapped[str | None] = mapped_column(String(32), nullable=True)
    elfogadott_valaszok: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list
    valaszlehetosegek: Mapped[str | None] = mapped_column(Text, nullable=True)    # JSON list
    max_pont: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    reszpontozas: Mapped[str | None] = mapped_column(Text, nullable=True)
    ertekeles_megjegyzes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Compiled TTS assets – relative paths to MP3 files under assets_dir
    tts_kerdes_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    tts_magyarazat_path: Mapped[str | None] = mapped_column(String(512), nullable=True)

    # Extraction context
    kontextus: Mapped[str | None] = mapped_column(Text, nullable=True)
    abra_van: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    feladat_oldal: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fl_szoveg_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    ut_szoveg_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    fl_pdf_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    ut_pdf_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    review_elvegezve: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    review_megjegyzes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationship to user attempts
    megoldasok: Mapped[list["MegoldasRecord"]] = relationship(
        back_populates="feladat", cascade="all, delete-orphan"
    )

    def to_domain(self) -> Feladat:
        return Feladat.from_record(self)


class MegoldasRecord(Base):
    """A single user attempt at a Feladat."""

    __tablename__ = "megoldasok"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    feladat_id: Mapped[str] = mapped_column(
        ForeignKey("feladatok.id", ondelete="CASCADE"), index=True
    )
    menet_id: Mapped[int | None] = mapped_column(
        ForeignKey("menetek.id"), nullable=True, index=True
    )
    felhasznalo_nev: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    adott_valasz: Mapped[str] = mapped_column(Text, nullable=False)
    helyes: Mapped[bool] = mapped_column(Boolean, nullable=False)
    pont: Mapped[int] = mapped_column(Integer, nullable=False)
    visszajelzes: Mapped[str] = mapped_column(Text, nullable=False)
    elapsed_sec: Mapped[float | None] = mapped_column(Float, nullable=True)
    segitseg_kert: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    hibajelezes: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    feladat: Mapped["FeladatRecord"] = relationship(back_populates="megoldasok")
    menet: Mapped["MenetRecord | None"] = relationship(back_populates="megoldasok")


def init_db(db_path: Path | None = None) -> None:
    """Create all tables if they don't exist."""
    Base.metadata.create_all(get_engine(db_path))


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------


class FeladatRepository:
    """CRUD + asset operations for Feladat persistence."""

    def __init__(self, db_path: Path | None = None) -> None:
        self._engine = get_engine(db_path)
        init_db(db_path)

    # --- Feladat CRUD ---

    def upsert(self, feladat: Feladat) -> None:
        """Insert or update a Feladat (domain model → DB record)."""
        with Session(self._engine) as session:
            existing = session.get(FeladatRecord, feladat.id)
            if existing:
                existing.targy = feladat.targy
                existing.neh = feladat.neh
                existing.szint = feladat.szint
                existing.kerdes = feladat.kerdes
                existing.helyes_valasz = feladat.helyes_valasz
                existing.hint = feladat.hint
                existing.magyarazat = feladat.magyarazat
                existing.ev = feladat.ev
                existing.valtozat = feladat.valtozat
                existing.feladat_sorszam = feladat.feladat_sorszam
                existing.csoport_id = feladat.csoport_id
                existing.csoport_sorrend = feladat.csoport_sorrend
                existing.feladat_tipus = feladat.feladat_tipus
                existing.elfogadott_valaszok = _list_to_json(feladat.elfogadott_valaszok)
                existing.valaszlehetosegek = _list_to_json(feladat.valaszlehetosegek)
                existing.max_pont = feladat.max_pont
                existing.reszpontozas = feladat.reszpontozas
                existing.ertekeles_megjegyzes = feladat.ertekeles_megjegyzes
                if feladat.tts_kerdes_path is not None:
                    existing.tts_kerdes_path = feladat.tts_kerdes_path
                if feladat.tts_magyarazat_path is not None:
                    existing.tts_magyarazat_path = feladat.tts_magyarazat_path
                existing.kontextus = feladat.kontextus
                existing.abra_van = feladat.abra_van
                existing.feladat_oldal = feladat.feladat_oldal
                if feladat.fl_szoveg_path is not None:
                    existing.fl_szoveg_path = feladat.fl_szoveg_path
                if feladat.ut_szoveg_path is not None:
                    existing.ut_szoveg_path = feladat.ut_szoveg_path
                if feladat.fl_pdf_path is not None:
                    existing.fl_pdf_path = feladat.fl_pdf_path
                if feladat.ut_pdf_path is not None:
                    existing.ut_pdf_path = feladat.ut_pdf_path
                existing.review_elvegezve = feladat.review_elvegezve
                if feladat.review_megjegyzes is not None:
                    existing.review_megjegyzes = feladat.review_megjegyzes
                existing.updated_at = datetime.now(timezone.utc)
            else:
                session.add(FeladatRecord(
                    id=feladat.id,
                    targy=feladat.targy,
                    neh=feladat.neh,
                    szint=feladat.szint,
                    kerdes=feladat.kerdes,
                    helyes_valasz=feladat.helyes_valasz,
                    hint=feladat.hint,
                    magyarazat=feladat.magyarazat,
                    ev=feladat.ev,
                    valtozat=feladat.valtozat,
                    feladat_sorszam=feladat.feladat_sorszam,
                    csoport_id=feladat.csoport_id,
                    csoport_sorrend=feladat.csoport_sorrend,
                    feladat_tipus=feladat.feladat_tipus,
                    elfogadott_valaszok=_list_to_json(feladat.elfogadott_valaszok),
                    valaszlehetosegek=_list_to_json(feladat.valaszlehetosegek),
                    max_pont=feladat.max_pont,
                    reszpontozas=feladat.reszpontozas,
                    ertekeles_megjegyzes=feladat.ertekeles_megjegyzes,
                    tts_kerdes_path=feladat.tts_kerdes_path,
                    tts_magyarazat_path=feladat.tts_magyarazat_path,
                    kontextus=feladat.kontextus,
                    abra_van=feladat.abra_van,
                    feladat_oldal=feladat.feladat_oldal,
                    fl_szoveg_path=feladat.fl_szoveg_path,
                    ut_szoveg_path=feladat.ut_szoveg_path,
                    fl_pdf_path=feladat.fl_pdf_path,
                    ut_pdf_path=feladat.ut_pdf_path,
                    review_elvegezve=feladat.review_elvegezve,
                    review_megjegyzes=feladat.review_megjegyzes,
                ))
            session.commit()

    def upsert_many(self, feladatok: list[Feladat]) -> None:
        """Bulk upsert – more efficient than calling upsert() in a loop."""
        with Session(self._engine) as session:
            existing_ids = {
                row[0]
                for row in session.execute(
                    select(FeladatRecord.id).where(
                        FeladatRecord.id.in_([f.id for f in feladatok])
                    )
                )
            }
            now = datetime.now(timezone.utc)
            for f in feladatok:
                if f.id in existing_ids:
                    session.merge(FeladatRecord(
                        id=f.id, targy=f.targy, neh=f.neh, szint=f.szint,
                        kerdes=f.kerdes, helyes_valasz=f.helyes_valasz,
                        hint=f.hint, magyarazat=f.magyarazat,
                        ev=f.ev,
                        valtozat=f.valtozat,
                        feladat_sorszam=f.feladat_sorszam,
                        csoport_id=f.csoport_id,
                        csoport_sorrend=f.csoport_sorrend,
                        feladat_tipus=f.feladat_tipus,
                        elfogadott_valaszok=_list_to_json(f.elfogadott_valaszok),
                        valaszlehetosegek=_list_to_json(f.valaszlehetosegek),
                        max_pont=f.max_pont,
                        reszpontozas=f.reszpontozas,
                        ertekeles_megjegyzes=f.ertekeles_megjegyzes,
                        tts_kerdes_path=f.tts_kerdes_path,
                        tts_magyarazat_path=f.tts_magyarazat_path,
                        kontextus=f.kontextus,
                        abra_van=f.abra_van,
                        feladat_oldal=f.feladat_oldal,
                        fl_szoveg_path=f.fl_szoveg_path,
                        ut_szoveg_path=f.ut_szoveg_path,
                        fl_pdf_path=f.fl_pdf_path,
                        ut_pdf_path=f.ut_pdf_path,
                        review_elvegezve=f.review_elvegezve,
                        review_megjegyzes=f.review_megjegyzes,
                        updated_at=now,
                    ))
                else:
                    session.add(FeladatRecord(
                        id=f.id, targy=f.targy, neh=f.neh, szint=f.szint,
                        kerdes=f.kerdes, helyes_valasz=f.helyes_valasz,
                        hint=f.hint, magyarazat=f.magyarazat,
                        ev=f.ev,
                        valtozat=f.valtozat,
                        feladat_sorszam=f.feladat_sorszam,
                        csoport_id=f.csoport_id,
                        csoport_sorrend=f.csoport_sorrend,
                        feladat_tipus=f.feladat_tipus,
                        elfogadott_valaszok=_list_to_json(f.elfogadott_valaszok),
                        valaszlehetosegek=_list_to_json(f.valaszlehetosegek),
                        max_pont=f.max_pont,
                        reszpontozas=f.reszpontozas,
                        ertekeles_megjegyzes=f.ertekeles_megjegyzes,
                        tts_kerdes_path=f.tts_kerdes_path,
                        tts_magyarazat_path=f.tts_magyarazat_path,
                        kontextus=f.kontextus,
                        abra_van=f.abra_van,
                        feladat_oldal=f.feladat_oldal,
                        fl_szoveg_path=f.fl_szoveg_path,
                        ut_szoveg_path=f.ut_szoveg_path,
                        fl_pdf_path=f.fl_pdf_path,
                        ut_pdf_path=f.ut_pdf_path,
                        review_elvegezve=f.review_elvegezve,
                        review_megjegyzes=f.review_megjegyzes,
                    ))
            session.commit()

    def get(self, feladat_id: str) -> Feladat | None:
        with Session(self._engine) as session:
            record = session.get(FeladatRecord, feladat_id)
            return record.to_domain() if record else None

    def all(self, targy: str | None = None, szint: str | None = None) -> list[Feladat]:
        with Session(self._engine) as session:
            stmt = select(FeladatRecord)
            if targy:
                stmt = stmt.where(FeladatRecord.targy == targy)
            if szint:
                stmt = stmt.where(FeladatRecord.szint == szint)
            return [r.to_domain() for r in session.scalars(stmt)]

    def count(self) -> int:
        with Session(self._engine) as session:
            return session.query(FeladatRecord).count()

    # --- FeladatCsoport CRUD ---

    def upsert_csoport(self, csoport: FeladatCsoport) -> None:
        """Insert or update a FeladatCsoport record."""
        with Session(self._engine) as session:
            existing = session.get(FeladatCsoportRecord, csoport.id)
            if existing:
                existing.targy = csoport.targy
                existing.szint = csoport.szint
                existing.feladat_sorszam = csoport.feladat_sorszam
                existing.ev = csoport.ev
                existing.valtozat = csoport.valtozat
                existing.kontextus = csoport.kontextus
                existing.abra_van = csoport.abra_van
                existing.feladat_oldal = csoport.feladat_oldal
                existing.fl_pdf_path = csoport.fl_pdf_path
                existing.ut_pdf_path = csoport.ut_pdf_path
                existing.fl_szoveg_path = csoport.fl_szoveg_path
                existing.ut_szoveg_path = csoport.ut_szoveg_path
                existing.sorrend_kotelezo = csoport.sorrend_kotelezo
                existing.max_pont_ossz = csoport.max_pont_ossz
                existing.updated_at = datetime.now(timezone.utc)
            else:
                session.add(FeladatCsoportRecord(
                    id=csoport.id,
                    targy=csoport.targy,
                    szint=csoport.szint,
                    feladat_sorszam=csoport.feladat_sorszam,
                    ev=csoport.ev,
                    valtozat=csoport.valtozat,
                    kontextus=csoport.kontextus,
                    abra_van=csoport.abra_van,
                    feladat_oldal=csoport.feladat_oldal,
                    fl_pdf_path=csoport.fl_pdf_path,
                    ut_pdf_path=csoport.ut_pdf_path,
                    fl_szoveg_path=csoport.fl_szoveg_path,
                    ut_szoveg_path=csoport.ut_szoveg_path,
                    sorrend_kotelezo=csoport.sorrend_kotelezo,
                    max_pont_ossz=csoport.max_pont_ossz,
                ))
            session.commit()

    def upsert_many_csoportok(self, csoportok: list[FeladatCsoport]) -> None:
        """Bulk upsert for FeladatCsoport records."""
        for c in csoportok:
            self.upsert_csoport(c)

    def get_csoport(self, csoport_id: str) -> FeladatCsoport | None:
        with Session(self._engine) as session:
            record = session.get(FeladatCsoportRecord, csoport_id)
            return record.to_domain() if record else None

    def get_feladatok_by_csoport(self, csoport_id: str) -> list[Feladat]:
        """Return all Feladatok belonging to a group, ordered by csoport_sorrend."""
        with Session(self._engine) as session:
            stmt = (
                select(FeladatRecord)
                .where(FeladatRecord.csoport_id == csoport_id)
                .order_by(FeladatRecord.csoport_sorrend)
            )
            return [r.to_domain() for r in session.scalars(stmt)]

    # --- Asset operations ---

    def save_tts_assets(
        self,
        feladat: Feladat,
        tts_kerdes: bytes | None = None,
        tts_magyarazat: bytes | None = None,
    ) -> Feladat:
        """
        Write TTS bytes to files and persist the relative paths in the DB.
        Returns an updated Feladat with the new path fields set.
        """
        with Session(self._engine) as session:
            record = session.get(FeladatRecord, feladat.id)
            if record is None:
                raise KeyError(f"Feladat not found: {feladat.id}")

            new_kerdes_path: str | None = None
            new_magyarazat_path: str | None = None

            if tts_kerdes is not None:
                rel = relative_asset_path(feladat.id, "kerdes", feladat.szint, feladat.ev, feladat.valtozat)
                abs_path = resolve_asset(rel)
                abs_path.parent.mkdir(parents=True, exist_ok=True)
                abs_path.write_bytes(tts_kerdes)
                record.tts_kerdes_path = rel
                new_kerdes_path = rel

            if tts_magyarazat is not None:
                rel = relative_asset_path(feladat.id, "magyarazat", feladat.szint, feladat.ev, feladat.valtozat)
                abs_path = resolve_asset(rel)
                abs_path.parent.mkdir(parents=True, exist_ok=True)
                abs_path.write_bytes(tts_magyarazat)
                record.tts_magyarazat_path = rel
                new_magyarazat_path = rel

            record.updated_at = datetime.now(timezone.utc)
            session.commit()

        return feladat.with_assets(
            tts_kerdes_path=new_kerdes_path,
            tts_magyarazat_path=new_magyarazat_path,
        )

    def load_tts_bytes(self, relative_path: str) -> bytes:
        """Read TTS MP3 bytes from the asset file."""
        return resolve_asset(relative_path).read_bytes()

    def missing_tts(self, targy: str | None = None) -> Sequence[Feladat]:
        """Return feladatok that have no pre-rendered TTS audio yet."""
        with Session(self._engine) as session:
            stmt = select(FeladatRecord).where(FeladatRecord.tts_kerdes_path.is_(None))
            if targy:
                stmt = stmt.where(FeladatRecord.targy == targy)
            return [r.to_domain() for r in session.scalars(stmt)]

    # --- Megoldas (attempt) tracking ---

    def save_megoldas(
        self,
        feladat: Feladat,
        adott_valasz: str,
        ertekeles: Ertekeles,
        *,
        felhasznalo_nev: str = "",
        menet_id: int | None = None,
        elapsed_sec: float | None = None,
        segitseg_kert: bool = False,
        hibajelezes: bool = False,
    ) -> None:
        with Session(self._engine) as session:
            session.add(MegoldasRecord(
                feladat_id=feladat.id,
                menet_id=menet_id,
                felhasznalo_nev=felhasznalo_nev,
                adott_valasz=adott_valasz,
                helyes=ertekeles.helyes,
                pont=ertekeles.pont,
                visszajelzes=ertekeles.visszajelzes,
                elapsed_sec=elapsed_sec,
                segitseg_kert=segitseg_kert,
                hibajelezes=hibajelezes,
            ))
            session.commit()

    def save_review(self, feladat: Feladat, megjegyzes: str | None = None) -> Feladat:
        """Mark a feladat as reviewed, clear all pending hibajelezes flags, return updated domain."""
        with Session(self._engine) as session:
            record = session.get(FeladatRecord, feladat.id)
            if record is None:
                raise KeyError(f"Feladat not found: {feladat.id}")
            record.review_elvegezve = True
            record.review_megjegyzes = megjegyzes
            record.updated_at = datetime.now(timezone.utc)
            # Clear pending error flags on all attempts for this feladat
            session.execute(
                __import__("sqlalchemy").update(MegoldasRecord)
                .where(MegoldasRecord.feladat_id == feladat.id)
                .values(hibajelezes=False)
            )
            session.commit()
            return record.to_domain()

    def stats(self) -> dict:
        """Return aggregate statistics across all attempts."""
        with Session(self._engine) as session:
            total = session.query(MegoldasRecord).count()
            helyes = session.query(MegoldasRecord).filter_by(helyes=True).count()
            return {
                "total_attempts": total,
                "correct": helyes,
                "accuracy": round(helyes / total * 100, 1) if total else 0.0,
            }

    # --- Felhasznalo & Menet ---

    def get_or_create_felhasznalo(self, nev: str) -> None:
        """Ensure a player record exists for the given name."""
        with Session(self._engine) as session:
            if session.get(FelhasznaloRecord, nev) is None:
                session.add(FelhasznaloRecord(nev=nev))
                session.commit()

    def start_menet(
        self,
        felhasznalo_nev: str,
        targy: str,
        szint: str,
        feladat_limit: int,
    ) -> int:
        """Create a new playing session and return its id."""
        with Session(self._engine) as session:
            record = MenetRecord(
                felhasznalo_nev=felhasznalo_nev,
                targy=targy,
                szint=szint,
                feladat_limit=feladat_limit,
            )
            session.add(record)
            session.commit()
            return record.id

    def end_menet(self, menet_id: int) -> None:
        """Mark a session as ended."""
        with Session(self._engine) as session:
            record = session.get(MenetRecord, menet_id)
            if record and record.ended_at is None:
                record.ended_at = datetime.now(timezone.utc)
                session.commit()

    def update_menet_progress(self, menet_id: int, megoldott: int, pont: int) -> None:
        """Persist in-progress counters (task count + score) to the session record."""
        with Session(self._engine) as session:
            record = session.get(MenetRecord, menet_id)
            if record:
                record.megoldott = megoldott
                record.pont = pont
                session.commit()

    def get_menetek(self, felhasznalo_nev: str, limit: int = 10) -> list[Menet]:
        """Return recent sessions for a user, newest first."""
        with Session(self._engine) as session:
            stmt = (
                select(MenetRecord)
                .where(MenetRecord.felhasznalo_nev == felhasznalo_nev)
                .order_by(MenetRecord.started_at.desc())
                .limit(limit)
            )
            return [r.to_domain() for r in session.scalars(stmt)]
