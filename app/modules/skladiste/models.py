from datetime import date, datetime

from sqlalchemy import (
    Boolean, Date, DateTime, ForeignKey, Index, Integer,
    Numeric, String, Text, func, text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Paleta(Base):
    """Aktivne + povijesne palete. `datum_out IS NULL` = aktivna (na poziciji)."""
    __tablename__ = "paleta"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    qr_raw: Mapped[str] = mapped_column(String(255), index=True)   # skenirani barkod (ključ)

    # Podaci o artiklu — pri zaprimanju dolaze iz ERP lookupa (ili ručno)
    sifra: Mapped[str | None] = mapped_column(String(60), index=True)
    naziv: Mapped[str | None] = mapped_column(String(255))
    lot: Mapped[str | None] = mapped_column(String(80))
    kolicina: Mapped[float | None] = mapped_column(Numeric(12, 3))
    jedinica: Mapped[str | None] = mapped_column(String(20))
    datum_ulaza: Mapped[date | None] = mapped_column(Date)         # ISO
    rok_trajanja: Mapped[date | None] = mapped_column(Date, index=True)  # ISO, za FEFO

    pozicija: Mapped[str] = mapped_column(String(20), index=True)  # validirano protiv REGALI
    datum_in: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    datum_out: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    izvor: Mapped[str | None] = mapped_column(String(10))          # erp | rucno
    nepotpuna: Mapped[bool] = mapped_column(Boolean, default=False)  # WMS-app: stane još na isto mjesto

    __table_args__ = (
        # WMS-app: VIŠE aktivnih paleta po istoj poziciji je DOZVOLJENO (reslovi/ostaci —
        # nepotpune palete pa ih više stane). Indeks je NE-unique, samo za brzo dohvaćanje
        # aktivnih paleta po poziciji. (ERP kopija drži unique — ovdje je namjerno relaksirano.)
        Index(
            "ix_paleta_aktivna_pozicija", "pozicija",
            sqlite_where=text("datum_out IS NULL"),
            postgresql_where=text("datum_out IS NULL"),
        ),
    )


class Prijem(Base):
    """Plan zaprimanja (header)."""
    __tablename__ = "prijem"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sifra: Mapped[str | None] = mapped_column(String(60))
    broj_paleta: Mapped[int] = mapped_column(Integer, default=0)
    datum_plan: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="aktivan")  # aktivan|zavrsen|odustao
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    stavke: Mapped[list["PrijemStavka"]] = relationship(
        back_populates="prijem", cascade="all, delete-orphan",
        order_by="PrijemStavka.redni_broj",
    )


class PrijemStavka(Base):
    """Stavka plana zaprimanja — jedna predložena/potvrđena pozicija."""
    __tablename__ = "prijem_stavka"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    prijem_id: Mapped[int] = mapped_column(ForeignKey("prijem.id"), index=True)
    redni_broj: Mapped[int] = mapped_column(Integer, default=0)
    pozicija: Mapped[str] = mapped_column(String(20))
    qr_raw: Mapped[str | None] = mapped_column(String(255))        # popuni se na potvrdi
    datum_potvrda: Mapped[datetime | None] = mapped_column(DateTime)  # NULL = nepotvrđeno

    prijem: Mapped["Prijem"] = relationship(back_populates="stavke")


class Inventura(Base):
    """Popis stanja (header)."""
    __tablename__ = "inventura"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    datum_pocetka: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    datum_kraja: Mapped[datetime | None] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(20), default="aktivan")  # aktivan|zavrsen|ponistena

    stavke: Mapped[list["InventuraStavka"]] = relationship(
        back_populates="inventura", cascade="all, delete-orphan",
    )


class InventuraStavka(Base):
    __tablename__ = "inventura_stavka"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    inventura_id: Mapped[int] = mapped_column(ForeignKey("inventura.id"), index=True)
    qr_raw: Mapped[str] = mapped_column(String(255))
    pozicija_skenirana: Mapped[str | None] = mapped_column(String(20))
    datum_skeniranja: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    inventura: Mapped["Inventura"] = relationship(back_populates="stavke")


class Prioritet(Base):
    """Pravilo smještaja po šifri (koji mod + dozvoljeni regali)."""
    __tablename__ = "prioritet"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sifra: Mapped[str] = mapped_column(String(60), index=True)
    # standardno | puni_rupe | lijevi | strogo_lijevo
    mod: Mapped[str] = mapped_column(String(20), default="standardno")
    rack_ids: Mapped[str | None] = mapped_column(Text)            # CSV dozvoljenih regala
    napomena: Mapped[str | None] = mapped_column(Text)
    aktivan: Mapped[bool] = mapped_column(Boolean, default=True)


class SkladisteEvent(Base):
    """Audit log — što se dogodilo i kada (tko dolazi kasnije s ERP auth-om)."""
    __tablename__ = "skladiste_event"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    tip: Mapped[str] = mapped_column(String(40))
    poruka: Mapped[str | None] = mapped_column(Text)
    detalji: Mapped[str | None] = mapped_column(Text)
