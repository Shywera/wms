"""Samostalni Skladište / WMS app — s prijavom, granularnim dozvolama i audit logom.

Isti skladišni modul kao u ERP-u (`app.modules.skladiste`, kopiran NETAKNUT), a
prijava/dozvole/audit dodani su kroz middleware + zaseban `auth` modul:
  * SessionMiddleware (potpisani httpOnly cookie) drži `user_id`.
  * `auth_audit` middleware: traži prijavu, provjerava dozvolu po putanji, te
    bilježi svaku mutaciju (POST/PUT/DELETE) u `audit_log` (tko/kad/što).

Pokretanje:  .venv\\Scripts\\uvicorn app.main:app --reload   (ili run.bat)
"""
from datetime import datetime

from fastapi import FastAPI, Request
from fastapi.responses import (FileResponse, HTMLResponse, PlainTextResponse,
                               RedirectResponse, Response)
from sqlalchemy import func, inspect as sa_inspect, select, text
from starlette.middleware.sessions import SessionMiddleware

from app.core.backup import auto_backup, db_putanja
from app.core.config import settings
from app.core.database import Base, SessionLocal, engine
from app.modules.auth import models as auth_models  # noqa: F401 — registrira korisnik/audit_log
from app.modules.auth import security as sec
from app.modules.auth.models import AuditLog, User
from app.modules.auth.routes import router as auth_router, templates as auth_templates
from app.modules.skladiste import models  # noqa: F401 — registrira skladišne tablice
from app.modules.skladiste.routes import router as skladiste_router
from app.modules.lokacija.routes import router as lokacija_router
from app.modules.zahtjevnica import models as zahtjevnica_models  # noqa: F401 — registrira zahtjevnica tablice
from app.modules.zahtjevnica.routes import router as zahtjevnica_router

auto_backup()  # backup postojeće baze prije starta

# Kreiraj sve tablice (skladišne + korisnik + audit_log) ako ne postoje.
Base.metadata.create_all(bind=engine)

# Makni stari UNIQUE indeks (jedna paleta/poziciji) ako postoji iz ranije verzije —
# WMS-app dozvoljava više paleta na istoj poziciji (reslovi). Idempotentno.
with engine.begin() as _conn:
    _conn.execute(text("DROP INDEX IF EXISTS uq_paleta_aktivna_pozicija"))

# Dodaj nove stupce na postojeću bazu ako fale (create_all ne mijenja postojeće tablice).
if "nepotpuna" not in {c["name"] for c in sa_inspect(engine).get_columns("paleta")}:
    with engine.begin() as _conn:
        _conn.execute(text("ALTER TABLE paleta ADD COLUMN nepotpuna BOOLEAN DEFAULT 0"))
if "ukljucena" not in {c["name"] for c in sa_inspect(engine).get_columns("zahtjevnica_stavka")}:
    with engine.begin() as _conn:
        _conn.execute(text("ALTER TABLE zahtjevnica_stavka ADD COLUMN ukljucena BOOLEAN DEFAULT 0"))


def _seed_admin() -> None:
    """Ako nema nijednog korisnika, kreiraj početnog admina (lozinka iz ADMIN_PASSWORD)."""
    db = SessionLocal()
    try:
        if (db.scalar(select(func.count(User.id))) or 0) == 0:
            pw = settings.admin_password
            db.add(User(username="admin", ime="Administrator",
                        lozinka_hash=sec.hash_password(pw), dozvole="admin", aktivan=True))
            db.commit()
            print(f"[WMS] Kreiran pocetni admin -> korisnik: admin  lozinka: {pw}  "
                  f"(PROMIJENI nakon prve prijave!)")
    finally:
        db.close()


_seed_admin()

app = FastAPI(title="Skladište WMS", docs_url="/api-docs", redoc_url=None)

# Zajednički dnevnik hub-a (Programi\hub_log.py) - tko je što radio.
# Uvijek u try/except: dnevnik je pomoćna stvar i ne smije spriječiti
# pokretanje programa ako ga netko premjesti ili obriše.
try:
    import sys as _sys
    from pathlib import Path as _Path
    _korijen = str(_Path(__file__).resolve().parents[3])   # ...\Programi
    if _korijen not in _sys.path:
        _sys.path.insert(0, _korijen)
    import hub_log as _hub_log
    _hub_log.ukljuci(app, "WMS")
except Exception:                                          # noqa: BLE001
    pass



@app.middleware("http")
async def auth_audit(request: Request, call_next):
    path = request.url.path
    if path in sec.PUBLIC_PATHS or path.startswith("/api-docs"):
        return await call_next(request)

    db = SessionLocal()
    try:
        uid = request.session.get("user_id")
        user = db.get(User, uid) if uid else None
        if user is not None and not user.aktivan:
            user = None
        request.state.user = user

        if user is None:
            if request.headers.get("HX-Request"):
                r = Response(status_code=401)
                r.headers["HX-Redirect"] = "/login"
                return r
            return RedirectResponse("/login", status_code=303)

        if sec.is_locked(path):
            return auth_templates.TemplateResponse(
                request, "radno.html", {}, status_code=423)

        needed = sec.required_perm(path)
        if needed and not sec.has_perm(user.dozvole, needed):
            return auth_templates.TemplateResponse(
                request, "auth/403.html", {"perm": needed,
                                           "opis": sec.PERMISSIONS.get(needed, needed)},
                status_code=403)

        response = await call_next(request)

        if sec.should_audit(request.method, path, response.status_code):
            db.add(AuditLog(user_id=user.id, username=user.username, metoda=request.method,
                            putanja=path, akcija=sec.akcija_label(request.method, path)))
            db.commit()
        return response
    finally:
        db.close()


# SessionMiddleware se dodaje ZADNJI -> vanjski sloj -> postavi request.session
# prije nego auth_audit pokuša čitati prijavu.
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key,
                   same_site="lax", https_only=False)

app.include_router(auth_router)
app.include_router(lokacija_router)
app.include_router(zahtjevnica_router)
app.include_router(skladiste_router)


@app.get("/backup", include_in_schema=False)
def backup(request: Request):
    """Preuzmi kopiju trenutne baze (samo administrator)."""
    u = getattr(request.state, "user", None)
    if not (u and sec.has_perm(u.dozvole, "admin")):
        return PlainTextResponse("Samo administrator.", status_code=403)
    p = db_putanja()
    if p is None or not p.exists():
        return PlainTextResponse("Baza ne postoji.", status_code=404)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return FileResponse(p, filename=f"{p.stem}_{stamp}{p.suffix}",
                        media_type="application/octet-stream")


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/skladiste")
