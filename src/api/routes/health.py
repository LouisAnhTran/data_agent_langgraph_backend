"""Health check and status endpoints"""

from fastapi import APIRouter
from pydantic import BaseModel
from datetime import datetime

from src.config import settings

router = APIRouter()


class HealthResponse(BaseModel):
    """Health check response model"""
    status: str
    timestamp: str
    version: str
    environment: str


class DummyResponse(BaseModel):
    """Dummy endpoint response model"""
    message: str
    data: dict


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """
    Health check endpoint

    Returns the current status of the API service
    """
    return HealthResponse(
        status="healthy",
        timestamp=datetime.utcnow().isoformat(),
        version=settings.app_version,
        environment="development" if settings.debug else "production"
    )


@router.get("/dummy", response_model=DummyResponse)
async def dummy_endpoint():
    """
    Dummy endpoint for testing

    Returns a simple test message with sample data
    """
    return DummyResponse(
        message="This is a dummy endpoint",
        data={
            "app_name": settings.app_name,
            "timestamp": datetime.utcnow().isoformat(),
            "sample_field": "sample_value"
        }
    )
