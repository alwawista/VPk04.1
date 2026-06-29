from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, status
from fastapi.responses import FileResponse, JSONResponse

from app.config import Settings
from app.llm import InvalidLLMOutput, LLMClient, LLMUnavailable
from app.models import HealthResponse, StoredTicket, TicketIn, TriageResponse, TriageResult
from app.rate_limit import RateLimitExceeded, RateLimiter, RateLimitRule
from app.safety import detect_prompt_injection, operator_fallback, prompt_injection_result, validate_llm_result
from app.security import get_client_ip, hash_key, optional_bearer_token
from app.spool import EmergencySpool
from app.storage import SQLiteStorage, StorageUnavailable

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings.from_env()
    storage = SQLiteStorage(settings.database_url)
    await storage.init()
    app.state.settings = settings
    app.state.storage = storage
    app.state.spool = EmergencySpool(settings.spool_path)
    app.state.rate_limiter = RateLimiter(settings.redis_url)
    app.state.llm = LLMClient(settings)
    try:
        yield
    finally:
        await app.state.rate_limiter.close()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Support Triage MVP",
        version="0.2.0",
        description="ИИ-сервис первичной обработки обращений: классификация, черновик ответа, эскалация.",
        lifespan=lifespan,
    )

    @app.exception_handler(RateLimitExceeded)
    async def rate_limit_handler(_: Request, exc: RateLimitExceeded) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            headers={"Retry-After": str(exc.retry_after)},
            content={
                "detail": "Rate limit exceeded",
                "limit_key": exc.key,
                "retry_after": exc.retry_after,
            },
        )

    @app.get("/", include_in_schema=False)
    async def demo_ui() -> FileResponse:
        index_path = STATIC_DIR / "index.html"
        if not index_path.is_file():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Demo UI not found")
        return FileResponse(index_path, media_type="text/html; charset=utf-8")

    @app.get("/health", response_model=HealthResponse)
    async def health(request: Request) -> HealthResponse:
        settings: Settings = request.app.state.settings
        limiter: RateLimiter = request.app.state.rate_limiter
        warnings: list[str] = []
        if limiter.warning:
            warnings.append(limiter.warning)
        if settings.database_url.startswith("sqlite:///"):
            warnings.append("SQLite — режим демо. Для продакшена используйте PostgreSQL.")
        if settings.llm_provider == "mock":
            warnings.append("Включён mock LLM — внешние вызовы не выполняются.")
        if not settings.require_api_auth:
            warnings.append("API-авторизация отключена (REQUIRE_API_AUTH=false).")
        return HealthResponse(
            status="ok",
            storage="sqlite-demo" if settings.database_url.startswith("sqlite:///") else "external",
            limiter=limiter.mode,
            llm_provider=settings.llm_provider,
            warnings=warnings,
        )

    async def api_key_dependency(
        request: Request,
        authorization: str | None = Header(default=None, alias="Authorization"),
    ) -> str | None:
        return optional_bearer_token(request.app.state.settings, authorization)

    async def body_size_dependency(request: Request) -> None:
        settings: Settings = request.app.state.settings
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > settings.max_request_body_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Request body is too large",
            )

    def to_response(result: TriageResult) -> TriageResponse:
        return TriageResponse(
            category=result.category,
            draft_reply=result.draft_reply,
            confidence=result.confidence,
            escalate=result.escalate,
        )

    async def process_ticket(request: Request, ticket: TicketIn, _api_key: str | None) -> TriageResponse:
        settings: Settings = request.app.state.settings
        storage: SQLiteStorage = request.app.state.storage
        spool: EmergencySpool = request.app.state.spool
        limiter: RateLimiter = request.app.state.rate_limiter
        llm: LLMClient = request.app.state.llm

        client_ip = get_client_ip(request)
        client_hash = hash_key(ticket.client_id)
        ip_hash = hash_key(client_ip)

        rules = [
            RateLimitRule(f"rate:client:{client_hash}", settings.rate_limit_client_per_minute),
            RateLimitRule(f"rate:ip:{ip_hash}", settings.rate_limit_ip_per_minute),
            RateLimitRule("rate:global", settings.rate_limit_global_per_minute),
        ]
        if _api_key:
            rules.insert(0, RateLimitRule(f"rate:api_key:{hash_key(_api_key)}", settings.rate_limit_api_key_per_minute))
        await limiter.check_many(rules)

        error_note: str | None = None
        ticket_id: int | None = None

        try:
            ticket_id = await storage.create_ticket(ticket)
        except StorageUnavailable as exc:
            error_note = str(exc)
            result = operator_fallback()
            await spool.append(
                "storage_create_failed",
                {"ticket": ticket.model_dump(), "result": result.model_dump(mode="json"), "error": error_note},
            )
            return to_response(result)

        if detect_prompt_injection(ticket.text):
            result = prompt_injection_result()
            error_note = "prompt_injection_detected"
        else:
            try:
                llm_result = await llm.classify(ticket)
                result = validate_llm_result(ticket, llm_result)
            except InvalidLLMOutput as exc:
                result = operator_fallback()
                error_note = f"invalid_llm_output: {exc}"
            except LLMUnavailable as exc:
                result = operator_fallback()
                error_note = f"llm_unavailable: {exc}"

        if ticket_id is not None:
            try:
                await storage.update_ticket(ticket_id, result, error=error_note)
            except StorageUnavailable as exc:
                await spool.append(
                    "storage_update_failed",
                    {
                        "ticket_id": ticket_id,
                        "ticket": ticket.model_dump(),
                        "result": result.model_dump(mode="json"),
                        "error": str(exc),
                    },
                )

        return to_response(result)

    @app.get("/tickets", response_model=list[StoredTicket])
    async def list_tickets(
        request: Request,
        limit: int = Query(default=10, ge=1, le=100),
    ) -> list[StoredTicket]:
        storage: SQLiteStorage = request.app.state.storage
        try:
            return await storage.list_tickets(limit)
        except StorageUnavailable as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(exc),
            ) from exc

    @app.post(
        "/triage",
        response_model=TriageResponse,
        dependencies=[Depends(body_size_dependency)],
    )
    async def triage(
        request: Request,
        ticket: TicketIn,
        api_key: str | None = Depends(api_key_dependency),
    ) -> TriageResponse:
        return await process_ticket(request, ticket, api_key)

    @app.post(
        "/lead",
        response_model=TriageResponse,
        dependencies=[Depends(body_size_dependency)],
    )
    async def lead(
        request: Request,
        ticket: TicketIn,
        api_key: str | None = Depends(api_key_dependency),
    ) -> TriageResponse:
        return await process_ticket(request, ticket, api_key)

    return app


app = create_app()
