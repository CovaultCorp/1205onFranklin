from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.bootstrap import seed_initial_admin
from app.config import get_settings
from app.db import init_db
from app.routes import admin, auth, reports, requester, verify

templates = Jinja2Templates(directory="app/templates")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    seed_initial_admin()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Building Access Registry", lifespan=lifespan)
    app.mount("/static", StaticFiles(directory="app/static"), name="static")

    @app.get("/")
    def home(request: Request):
        return templates.TemplateResponse(request, "home.html", {})

    @app.get("/healthz")
    def healthz():
        return {
            "status": "ok",
            "enable_writes": settings.enable_writes,
            "enable_email": settings.enable_email,
        }

    app.include_router(auth.router)
    app.include_router(requester.router)
    app.include_router(admin.router)
    app.include_router(reports.router)
    app.include_router(verify.router)
    return app


app = create_app()
