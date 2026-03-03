"""General API routes for Bedrock Gateway."""

from config import config
from fastapi import APIRouter


def setup_general_routes():
    """Configure general API routes.

    Returns
    -------
        APIRouter: Configured general router with endpoints.
    """
    # Create a new router instance each time to avoid closure issues
    general_router = APIRouter()

    @general_router.get("/", include_in_schema=False)
    async def root():
        """Root endpoint.

        Returns
        -------
            dict: Welcome message and environment information.
        """
        return {
            "message": "Hello from Bedrock Gateway",
            "environment": config.environment,
        }

    @general_router.get("/debug", include_in_schema=False)
    async def debug():
        """Debug endpoint for API information.

        Returns
        -------
            dict: API status and documentation URLs.
        """
        return {
            "status": "ok",
            "docs_url": "/docs",
            "redoc_url": "/redoc",
            "openapi_url": "/openapi.json",
        }

    return general_router
