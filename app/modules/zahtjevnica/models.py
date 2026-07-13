"""Zahtjevnica materijala (uvezena iz Pauka) + stavke.

Skladištar uveze zahtjevnicu; software zadrži i grupira stavke po šifri, filtrira
papir (za ovo skladište) od boja/lakova/pudera, i vodi izdavanje stavku po stavku.
Ne dira `app.modules.skladiste` (mora ostati 1:1 s ERP-om) — samo koristi njegov servis.
"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Zahtjevnica(Base):
    __tablename__ = "zahtjevnica"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    oznaka: Mapped[str] = mapped_column(String(250))                 # npr. "RN 1983-26, 1995-26…"
    rn_popis: Mapped[str | None] = mapped_column(String(300))        # svi RN-ovi (CSV)
    izvor_naziv: Mapped[str | None] = mapped_column(String(255))     # originalni naziv datoteke
    sadrzaj_hash: Mapped[str] = mapped_column(String(40), index=True)  # za detekciju duplog uvoza
    status: Mapped[str] = mapped_column(String(20), default="uvezena")  # uvezena/u_tijeku/zavrsena
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    stavke: Mapped[list["ZahtjevnicaStavka"]] = relationship(
        back_populates="zahtjevnica", cascade="all, delete-orphan",
        order_by="ZahtjevnicaStavka.je_papir.desc(), ZahtjevnicaStavka.naziv")

    @property
    def papir_stavke(self) -> list["ZahtjevnicaStavka"]:
        """Popis za izdavanje: papir + ručno uključene ostale stavke (npr. boja na stanju)."""
        return [s for s in self.stavke if s.je_papir or s.ukljucena]

    @property
    def ostale_stavke(self) -> list["ZahtjevnicaStavka"]:
        return [s for s in self.stavke if not (s.je_papir or s.ukljucena)]

    @property
    def broj_papir(self) -> int:
        return len(self.papir_stavke)

    @property
    def broj_izdano(self) -> int:
        return sum(1 for s in self.papir_stavke if s.izdano)

    @property
    def broj_preostalo(self) -> int:
        return self.broj_papir - self.broj_izdano

    @property
    def gotovo(self) -> bool:
        return self.broj_papir > 0 and self.broj_izdano == self.broj_papir


class ZahtjevnicaStavka(Base):
    __tablename__ = "zahtjevnica_stavka"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    zahtjevnica_id: Mapped[int] = mapped_column(Integer, ForeignKey("zahtjevnica.id"), index=True)
    zahtjevnica: Mapped["Zahtjevnica"] = relationship(back_populates="stavke")

    sifra: Mapped[str | None] = mapped_column(String(60), index=True)
    naziv: Mapped[str | None] = mapped_column(String(300))
    jedinica: Mapped[str | None] = mapped_column(String(20))         # "arak" | "kg" | …
    trazena_kolicina: Mapped[float] = mapped_column(Float, default=0.0)
    rn_popis: Mapped[str | None] = mapped_column(String(300))        # RN-ovi za ovu šifru
    je_papir: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    # Ručno uključena u izdavanje (npr. boja koja se ipak zatekла na stanju ovog skladišta)
    ukljucena: Mapped[bool] = mapped_column(Boolean, default=False)

    izdano: Mapped[bool] = mapped_column(Boolean, default=False)
    izdano_kolicina: Mapped[float] = mapped_column(Float, default=0.0)
    izdano_paleta_ids: Mapped[str | None] = mapped_column(String(300))  # CSV id-eva paleta
    napomena: Mapped[str | None] = mapped_column(Text)
