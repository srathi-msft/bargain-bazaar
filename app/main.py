"""Bargain Bazaar server: FastAPI + Server-Sent Events. Run:  python -m app.main"""
from __future__ import annotations

import asyncio
import io
import json
import os
import secrets
import time
from collections import deque
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.datastructures import MutableHeaders

from .config import ROOT, Game, Settings, load_game, load_settings
from .credits import credits_html
from .store import EVENTS, Err, Store
from .voice import Voice

STATIC = ROOT / "static"
CSP = ("default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; "
       "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")


class JoinIn(BaseModel):
    name: str = Field("", max_length=80)


class HaggleIn(BaseModel):
    item_id: str = Field(max_length=32)
    message: str = Field(max_length=800)


class ItemIn(BaseModel):
    item_id: str = Field(max_length=32)


class StartIn(BaseModel):
    minutes: int | None = Field(None, ge=0, le=90)


class ExtendIn(BaseModel):
    seconds: int = Field(120, ge=10, le=1800)


class KickIn(BaseModel):
    pid: str = Field(max_length=32)


class RevealIn(BaseModel):
    on: bool


class EventIn(BaseModel):
    kind: str = Field(max_length=16)


class SecureHeaders:
    """Pure ASGI middleware (BaseHTTPMiddleware would interfere with streaming responses)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        async def wrapped(message):
            if message["type"] == "http.response.start":
                h = MutableHeaders(scope=message)
                h["X-Content-Type-Options"] = "nosniff"
                h["Referrer-Policy"] = "no-referrer"
                h["X-Frame-Options"] = "DENY"
                h["Content-Security-Policy"] = CSP
                if scope["path"].startswith("/api/") or not scope["path"].startswith("/static/"):
                    h["Cache-Control"] = "no-store"
            await send(message)

        await self.app(scope, receive, wrapped)


def sse(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False, separators=(',', ':'))}\n\n"


def create_app(game: Game | None = None, settings: Settings | None = None, voice: Voice | None = None,
               clock=time.time, background: bool = True, transcript: bool = True, rng=None, auto_events: bool = True) -> FastAPI:
    game = game or load_game()
    settings = settings or load_settings()
    voice = voice or Voice(settings)
    store = Store(game, settings, voice, clock, transcript=transcript, rng=rng, auto_events=auto_events)
    fails: deque[float] = deque(maxlen=40)

    @asynccontextmanager
    async def lifespan(_app):
        tasks = []
        if background:
            if os.environ.get("RESUME") == "1" and store.load():
                print("Resumed previous game state.")
            tasks.append(asyncio.create_task(store.run_clock()))
            tasks.append(asyncio.create_task(voice.warmup()))
        yield
        for t in tasks:
            t.cancel()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(SecureHeaders)
    app.state.store, app.state.settings, app.state.voice = store, settings, voice

    # ------------------------------------------------------------------ errors and auth
    @app.exception_handler(Err)
    async def on_err(_r: Request, e: Err):
        return JSONResponse({"ok": False, "code": e.code, "error": e.message}, status_code=e.status)

    @app.exception_handler(RequestValidationError)
    async def on_bad(_r: Request, _e: RequestValidationError):
        return JSONResponse({"ok": False, "code": "bad_request", "error": "That didn't look right. Try again."}, status_code=400)

    def token_of(r: Request) -> str:
        return r.headers.get("x-token") or r.query_params.get("t") or ""

    def need_admin(r: Request) -> None:
        """The right key always works. Wrong keys are throttled: after 15 in a minute they are refused with 429. The throttle must never
        lock the host out, because every visitor reaches this server through the same tunnel, so a stranger's wrong guesses
        (or just a curious engineer poking at /admin) look just like the host's own traffic."""
        key = r.headers.get("x-admin-key") or r.query_params.get("key") or ""
        if secrets.compare_digest(key.encode(), settings.admin_key.encode()):
            return
        now = time.monotonic()
        while fails and now - fails[0] > 60:
            fails.popleft()
        if len(fails) >= 15:
            raise Err("locked", "Too many wrong admin keys. Wait a minute.", 429)
        fails.append(now)
        raise Err("admin", "Admin key required.", 401)

    async def stream(r: Request, bus, first: dict):
        q = bus.subscribe()
        try:
            yield "retry: 2000\n\n"
            yield sse(first["event"], first["data"])
            while True:
                try:
                    ev = await asyncio.wait_for(q.get(), timeout=12)
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
                    if await r.is_disconnected():
                        break
                    continue
                yield sse(ev["event"], ev["data"])
        finally:
            bus.unsubscribe(q)

    sse_headers = {"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no", "Connection": "keep-alive"}

    # ------------------------------------------------------------------ pages
    @app.get("/")
    async def index():
        return FileResponse(STATIC / "index.html")

    @app.get("/admin")
    async def admin_page():
        return FileResponse(STATIC / "admin.html")

    @app.get("/credits")
    async def credits():
        return HTMLResponse(credits_html(STATIC / "sfx" / "bazaar-sfx.json", game.title, game.shopkeeper))

    @app.get("/healthz")
    async def healthz():
        return {"ok": True, "status": store.status, "players": len(store.players)}

    # ------------------------------------------------------------------ player API
    @app.post("/api/join")
    async def join(body: JoinIn):
        p = store.join(body.name)
        return {"ok": True, "token": p.token, "me": store.me_view(p), "game": game.public(), "state": store.public_snapshot()}

    @app.get("/api/me")
    async def me(r: Request):
        p = store.auth(token_of(r))
        return {"ok": True, "me": store.me_view(p), "game": game.public(), "state": store.public_snapshot()}

    @app.get("/api/public")
    async def public():
        return {"ok": True, "game": game.public(), "state": store.public_snapshot()}

    @app.post("/api/haggle")
    async def haggle(body: HaggleIn, r: Request):
        return await store.haggle(token_of(r), body.item_id, body.message)

    @app.post("/api/walk")
    async def walk(body: ItemIn, r: Request):
        return await store.walk(token_of(r), body.item_id)

    @app.post("/api/buy")
    async def buy(body: ItemIn, r: Request):
        return await store.buy_now(token_of(r), body.item_id)

    @app.get("/api/stream")
    async def player_stream(r: Request):
        first = {"event": "snapshot", "data": store.public_snapshot()}
        return StreamingResponse(stream(r, store.bus, first), media_type="text/event-stream", headers=sse_headers)

    # ------------------------------------------------------------------ admin API
    @app.get("/api/admin/info")
    async def a_info(r: Request):
        need_admin(r)
        base = settings.public_url or str(r.base_url).rstrip("/")
        return {"ok": True, "join_url": base + "/", "game": game.public(), "snapshot": store.snapshot()}

    @app.get("/api/admin/stream")
    async def a_stream(r: Request):
        need_admin(r)
        first = {"event": "snapshot", "data": store.snapshot()}
        return StreamingResponse(stream(r, store.abus, first), media_type="text/event-stream", headers=sse_headers)

    @app.post("/api/admin/start")
    async def a_start(body: StartIn, r: Request):
        need_admin(r)
        store.start(body.minutes)
        return {"ok": True, "snapshot": store.snapshot()}

    @app.post("/api/admin/end")
    async def a_end(r: Request):
        need_admin(r)
        store.end()
        return {"ok": True, "snapshot": store.snapshot()}

    @app.post("/api/admin/extend")
    async def a_extend(body: ExtendIn, r: Request):
        need_admin(r)
        store.extend(body.seconds)
        return {"ok": True, "snapshot": store.snapshot()}

    @app.post("/api/admin/reset")
    async def a_reset(r: Request):
        need_admin(r)
        store.reset()
        return {"ok": True, "snapshot": store.snapshot()}

    @app.post("/api/admin/kick")
    async def a_kick(body: KickIn, r: Request):
        need_admin(r)
        store.kick(body.pid)
        return {"ok": True}

    @app.post("/api/admin/reveal")
    async def a_reveal(body: RevealIn, r: Request):
        need_admin(r)
        store.set_reveal(body.on)
        return {"ok": True, "reveal": store.reveal}

    @app.post("/api/admin/event")
    async def a_event(body: EventIn, r: Request):
        need_admin(r)
        if body.kind == "clear":
            store.clear_event()
        elif body.kind in EVENTS:
            store.start_event(body.kind)
        else:
            raise Err("bad_event", "Unknown event.", 400)
        return {"ok": True, "market": store.market_view()}

    @app.post("/api/admin/ai")
    async def a_ai(body: RevealIn, r: Request):
        need_admin(r)
        voice.muted = not body.on
        store.touch()
        return {"ok": True, "status": voice.status()}

    @app.post("/api/admin/test-ai")
    async def a_test(r: Request):
        need_admin(r)
        t0 = time.monotonic()
        problem = await voice.warmup()
        return {"ok": not problem, "message": problem or f"{game.shopkeeper}'s AI replies are ready.",
                "ms": int((time.monotonic() - t0) * 1000), "status": voice.status()}

    @app.get("/api/admin/qr")
    async def a_qr(r: Request, url: str = ""):
        need_admin(r)
        if not url.startswith(("http://", "https://")) or len(url) > 300:
            raise Err("bad_url", "Give a full http(s) URL.", 400)
        try:
            import segno
        except ImportError:
            raise Err("no_qr", "QR library not installed.", 404)
        buf = io.BytesIO()
        segno.make(url, error="m").save(buf, kind="svg", scale=10, border=1, dark="#1b1033", light="#ffffff", xmldecl=False,
                                        nl=False, svgns=True)
        return Response(buf.getvalue(), media_type="image/svg+xml")

    @app.get("/api/admin/export")
    async def a_export(r: Request):
        need_admin(r)
        rows = {row["id"]: row for row in store.snapshot()["players"]}
        out = {"game": game.public(), "status": store.status, "started_at": store.started_at, "ended_at": store.ended_at,
               "players": [{**rows.get(p.id, {}), "spent": p.spent, "tricks": p.tricks, "wits": p.wits, "messages": p.msgs,
                            "bought": p.bought, "chat": p.chat} for p in store.players.values()],
               "deals": store.deal_log}
        return Response(json.dumps(out, ensure_ascii=False, indent=1), media_type="application/json",
                        headers={"Content-Disposition": 'attachment; filename="bargain-bazaar-results.json"'})

    STATIC.mkdir(exist_ok=True)
    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app


def main() -> None:
    import uvicorn

    s = load_settings()
    print("=" * 64)
    print(f"  Players:   {s.public_url or f'http://localhost:{s.port}'}/")
    print(f"  Admin:     http://localhost:{s.port}/admin?key={s.admin_key}")
    print("=" * 64)
    uvicorn.run(create_app(settings=s), host="0.0.0.0", port=s.port, log_level="warning", timeout_keep_alive=65)


if __name__ == "__main__":
    main()
