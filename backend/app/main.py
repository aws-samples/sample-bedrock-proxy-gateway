# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Bedrock FastAPI proxy module."""

import boto3
from config import config
from fastapi import FastAPI, HTTPException
from middleware.auth import AuthMiddleware
from middleware.guardrail import GuardrailMiddleware
from middleware.rate_limit import RateLimitMiddleware
from middleware.trace import TraceMiddleware
from observability.telemetry import instrument_app, setup_telemetry
from routes.bedrock_routes import create_bedrock_router
from routes.general_routes import setup_general_routes
from routes.health import health_router
from routes.operational_routes import setup_operational_routes
from services.bedrock_service import BedrockService
from services.guardrail_service import GuardrailService
from util.exception_handler import create_global_exception_handler


def create_app() -> FastAPI:
    """Create and configure FastAPI application."""
    # Initialize FastAPI app
    app = FastAPI(
        title="Sample Bedrock Proxy Gateway",
        description="Lightweight managed proxy for Amazon Bedrock APIs",
        version=config.app_hash or "0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # Setup telemetry first
    telemetry = setup_telemetry()
    logger = telemetry["logger"]

    # Initialize dependencies
    session = boto3.Session()
    bedrock_service = BedrockService(session, logger)

    # Initialize guardrail service
    guardrail_service = GuardrailService()

    # Setup middleware (order matters - middleware is executed in LIFO order)
    # TraceMiddleware is registered first so it will execute last, after RateLimitMiddleware
    # This ensures client name is extracted before tracing
    # Execution order: AuthMiddleware -> RateLimitMiddleware -> TraceMiddleware
    app.add_middleware(TraceMiddleware)
    app.add_middleware(GuardrailMiddleware, guardrail_service=guardrail_service)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(AuthMiddleware)

    # Setup routes (order matters - most specific first)
    app.include_router(health_router)
    app.include_router(setup_general_routes())
    app.include_router(setup_operational_routes())

    app.include_router(create_bedrock_router(bedrock_service, telemetry))

    # Setup exception handling
    exception_handler = create_global_exception_handler(logger)
    app.add_exception_handler(HTTPException, exception_handler)
    app.add_exception_handler(Exception, exception_handler)

    # Setup observability (should be last to capture all components)
    instrument_app(app)

    return app


# Create app instance
app = create_app()
