"""
Health check and monitoring endpoints
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, Any
import psutil
import os
from app.services.cache_service import cache_service
from app.database import get_db

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
async def health_check() -> Dict[str, str]:
    """Basic health check"""
    return {"status": "healthy"}


@router.get("/detailed")
async def detailed_health() -> Dict[str, Any]:
    """Detailed health check with system metrics"""
    try:
        # System metrics
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')

        # Cache stats
        cache_stats = cache_service.get_stats()

        # Check database connection
        db_healthy = True
        try:
            from app.database import engine
            with engine.connect() as conn:
                conn.execute("SELECT 1")
        except Exception as e:
            db_healthy = False

        return {
            "status": "healthy",
            "system": {
                "cpu_percent": cpu_percent,
                "memory_percent": memory.percent,
                "memory_available_mb": memory.available // (1024 * 1024),
                "disk_percent": disk.percent,
                "disk_free_gb": disk.free // (1024 * 1024 * 1024)
            },
            "cache": cache_stats,
            "database": {
                "connected": db_healthy
            },
            "environment": {
                "python_version": os.sys.version.split()[0],
                "platform": os.sys.platform
            }
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Health check failed: {str(e)}")


@router.get("/ready")
async def readiness_check() -> Dict[str, Any]:
    """Kubernetes readiness probe"""
    try:
        # Check database
        from app.database import engine
        with engine.connect() as conn:
            conn.execute("SELECT 1")

        return {"status": "ready"}

    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Service not ready: {str(e)}")


@router.get("/live")
async def liveness_check() -> Dict[str, str]:
    """Kubernetes liveness probe"""
    return {"status": "alive"}
