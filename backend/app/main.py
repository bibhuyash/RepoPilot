import asyncio
import logging
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .config import origins
from .models import AnalyzeRequest, AnalyzeResponse, ErrorResponse
from .workflow import Investigator

logging.basicConfig(level=logging.INFO, format="%(message)s")
app = FastAPI(title="RepoPilot", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=origins(), allow_methods=["GET", "POST"], allow_headers=["Content-Type", "X-Request-ID"])
app.state.investigator = Investigator()


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/analyze", response_model=AnalyzeResponse, responses={400: {"model": ErrorResponse}, 429: {"model": ErrorResponse}, 502: {"model": ErrorResponse}})
async def analyze(payload: AnalyzeRequest, request: Request) -> AnalyzeResponse:
    request_id = str(uuid.uuid4())
    try:
        result = await asyncio.wait_for(request.app.state.investigator.analyze(payload.repository_url, payload.question, request_id), timeout=90)
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail={"error": "Investigation timed out. Please try again.", "request_id": request_id}) from exc
    if result.get("error"):
        raise HTTPException(status_code=result.get("status_code", 502), detail={"error": result["error"], "request_id": request_id})
    return AnalyzeResponse(report=result["report"], trace=result["trace"], request_id=request_id)


@app.exception_handler(HTTPException)
async def handle_http_error(_: Request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail if isinstance(exc.detail, dict) else {"error": str(exc.detail), "request_id": ""}
    return JSONResponse(status_code=exc.status_code, content=detail)


@app.exception_handler(Exception)
async def handle_error(request: Request, exc: Exception) -> JSONResponse:
    request_id = str(uuid.uuid4())
    logging.getLogger(__name__).error("analysis failure request_id=%s", request_id)
    return JSONResponse(status_code=500, content={"error": "An unexpected error occurred.", "request_id": request_id})
