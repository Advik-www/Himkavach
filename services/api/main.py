"""HimKavach API Service Entrypoint."""

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(
    title="HimKavach Polar Energy Management API",
    description="Intelligent Energy Flight-Planner and Safety Supervisor for Polar Research Stations",
    version="0.1.0",
)


class SystemHealthResponse(BaseModel):
    status: str
    version: str
    service: str


@app.get("/health", response_model=SystemHealthResponse)
async def health_check() -> SystemHealthResponse:
    """System health check endpoint."""
    return SystemHealthResponse(
        status="HEALTHY",
        version="0.1.0",
        service="himkavach-api",
    )
