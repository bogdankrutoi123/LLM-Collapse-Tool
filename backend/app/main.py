from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.core.config import get_settings
from app.api.routes import auth, models, prompts
from app.api.routes import users, thresholds, notifications, data, analysis, audit, collapse_events, rules, backup

settings = get_settings()

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="API for detecting collapse of large language models",
    debug=settings.DEBUG
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    try:
        detail = f"{exc.__class__.__name__}: {exc}"
    except Exception:
        detail = exc.__class__.__name__
    return JSONResponse(
        status_code=500,
        content={"detail": detail},
    )


# CORS goes outermost so error responses still carry the headers
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# plain Starlette middleware (not BaseHTTPMiddleware) avoids the exception
# propagation bug that can strip CORS headers from error responses
from starlette.middleware.base import BaseHTTPMiddleware  # noqa: E402


class EnforceHttpsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if settings.ENFORCE_HTTPS:
            proto = request.headers.get("x-forwarded-proto", request.url.scheme)
            if proto != "https":
                return JSONResponse(
                    status_code=403,
                    content={"detail": "HTTPS is required"},
                )
        try:
            return await call_next(request)
        except Exception as exc:
            try:
                detail = f"{exc.__class__.__name__}: {exc}"
            except Exception:
                detail = exc.__class__.__name__
            return JSONResponse(status_code=500, content={"detail": detail})


app.add_middleware(EnforceHttpsMiddleware)

app.include_router(auth.router, prefix=settings.API_V1_PREFIX)
app.include_router(models.router, prefix=settings.API_V1_PREFIX)
app.include_router(prompts.router, prefix=settings.API_V1_PREFIX)
app.include_router(users.router, prefix=settings.API_V1_PREFIX)
app.include_router(thresholds.router, prefix=settings.API_V1_PREFIX)
app.include_router(notifications.router, prefix=settings.API_V1_PREFIX)
app.include_router(data.router, prefix=settings.API_V1_PREFIX)
app.include_router(analysis.router, prefix=settings.API_V1_PREFIX)
app.include_router(audit.router, prefix=settings.API_V1_PREFIX)
app.include_router(collapse_events.router, prefix=settings.API_V1_PREFIX)
app.include_router(rules.router, prefix=settings.API_V1_PREFIX)
app.include_router(backup.router, prefix=settings.API_V1_PREFIX)


@app.get("/")
def root():
    """Root endpoint."""
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running"
    }


@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG
    )
