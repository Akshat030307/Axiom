import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes_auth import router as auth_router
from app.api.routes_eval import router as eval_router
from app.api.routes_evidence import router as evidence_router
from app.api.routes_figures import figures_router, research_figures_router
from app.api.routes_reports import router as reports_router
from app.api.routes_research import router as research_router
from app.api.routes_sources import router as sources_router
from app.api.routes_trace import router as trace_router
from app.api.ws import router as ws_router
from app.config import get_settings
from app.graph.checkpointer import close_checkpointer, init_checkpointer

settings = get_settings()
logging.basicConfig(level=settings.LOG_LEVEL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_checkpointer()
    yield
    await close_checkpointer()


app = FastAPI(title="Axiom API", description="Research, without the noise.", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(research_router)
app.include_router(reports_router)
app.include_router(sources_router)
app.include_router(evidence_router)
app.include_router(research_figures_router)
app.include_router(figures_router)
app.include_router(trace_router)
app.include_router(eval_router)
app.include_router(ws_router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
