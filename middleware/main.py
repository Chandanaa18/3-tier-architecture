import asyncio
import json
import re
import hmac
import hashlib
import base64
import time
from typing import Dict, Optional
from fastapi import FastAPI, HTTPException, Header, Depends, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
import httpx

app = FastAPI(title="Middleware Service (Validation & Callback Pattern)", version="1.0.0")

# Security Secrets from Environment
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "jwt-secret-key-frontend-to-middleware-2026")
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "60"))

security_bearer = HTTPBearer(auto_error=False)

# Lightweight standard JWT implementation without external dependencies
def base64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode('utf-8').rstrip('=')

def base64url_decode(data: str) -> bytes:
    padding = '=' * (4 - (len(data) % 4))
    return base64.urlsafe_b64decode(data + padding)

def create_jwt_token(username: str) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": username,
        "iat": int(time.time()),
        "exp": int(time.time()) + (JWT_EXPIRE_MINUTES * 60)
    }
    header_b64 = base64url_encode(json.dumps(header).encode('utf-8'))
    payload_b64 = base64url_encode(json.dumps(payload).encode('utf-8'))
    
    sig_input = f"{header_b64}.{payload_b64}".encode('utf-8')
    sig = hmac.new(JWT_SECRET_KEY.encode('utf-8'), sig_input, hashlib.sha256).digest()
    sig_b64 = base64url_encode(sig)
    return f"{header_b64}.{payload_b64}.{sig_b64}"

def verify_jwt_token(token: str) -> Optional[dict]:
    try:
        parts = token.split('.')
        if len(parts) != 3:
            return None
        header_b64, payload_b64, sig_b64 = parts
        sig_input = f"{header_b64}.{payload_b64}".encode('utf-8')
        expected_sig = hmac.new(JWT_SECRET_KEY.encode('utf-8'), sig_input, hashlib.sha256).digest()
        actual_sig = base64url_decode(sig_b64)
        if not hmac.compare_digest(expected_sig, actual_sig):
            return None
        payload = json.loads(base64url_decode(payload_b64).decode('utf-8'))
        if payload.get("exp", 0) < time.time():
            return None  # Expired token
        return payload
    except Exception:
        return None

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

import os

# In-memory dictionary mapping request_id -> asyncio.Queue
pending_requests: Dict[str, asyncio.Queue] = {}

BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8001/process")
MIDDLEWARE_HOST = os.getenv("MIDDLEWARE_HOST", "http://127.0.0.1:8000")

class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)

class ProcessRequest(BaseModel):
    name: str = Field(..., description="User's name to validate")
    request_id: str = Field(..., min_length=1, description="Unique correlation ID for SSE connection")

class CallbackPayload(BaseModel):
    success: bool
    message: str
    delay_seconds: float
    request_id: str

def validate_name(name: str) -> str:
    cleaned = name.strip()
    if not cleaned:
        raise ValueError("Validation Error: Input cannot be empty or consist only of whitespace.")
    if not re.search(r"[a-zA-Z0-9]", cleaned):
        raise ValueError("Validation Error: Input cannot consist only of special characters.")
    
    return cleaned


@app.get("/")
async def root():
    return {
        "service": "FastAPI Middleware Service",
        "status": "running",
        "port": 8000,
        "jwt_auth": "enabled",
        "active_sse_streams": len(pending_requests),
        "docs_url": "http://localhost:8000/docs",
        "health_url": "http://localhost:8000/health"
    }

@app.post("/api/login")
async def login(req: LoginRequest):
    """Generates a valid JWT Access Token for authenticated users."""
    if not req.username or not req.password:
        raise HTTPException(status_code=400, detail="Username and password required")
    
    token = create_jwt_token(req.username)
    return {
        "status": "success",
        "access_token": token,
        "token_type": "bearer",
        "user": req.username,
        "expires_in_minutes": JWT_EXPIRE_MINUTES
    }

@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "service": "middleware",
        "mode": "callback_webhook",
        "jwt_auth": "enabled",
        "active_sse_connections": len(pending_requests)
    }

async def sse_event_generator(request_id: str, username: str):
    queue = asyncio.Queue()
    pending_requests[request_id] = queue
    print(f"[Middleware] Authenticated SSE Connection for '{username}', request_id: {request_id}")
    
    try:
        init_event = {
            "type": "flow_step",
            "step": 1,
            "node": "middleware",
            "title": "JWT Authenticated SSE Stream Connected",
            "detail": f"JWT Token verified for '{username}'. Connected to Middleware (Port 8000)",
            "status": "connected"
        }
        yield f"event: flow_step\ndata: {json.dumps(init_event)}\n\n"
        
        while True:
            event_item = await queue.get()
            event_type = event_item.get("type", "message")
            payload = json.dumps(event_item)
            yield f"event: {event_type}\ndata: {payload}\n\n"
            
            if event_type in ["message", "error"]:
                break
                
    except asyncio.CancelledError:
        print(f"[Middleware] SSE Client disconnected for request_id: {request_id}")
    finally:
        pending_requests.pop(request_id, None)
        print(f"[Middleware] SSE Connection cleaned up for request_id: {request_id}")

@app.get("/api/stream/{request_id}")
async def stream_events(request_id: str, token: str = Query(...)):
    # Verify JWT Token from URL Query Parameter
    payload = verify_jwt_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid or expired JWT Token for SSE stream")

    return StreamingResponse(
        sse_event_generator(request_id, payload.get("sub", "user")),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

@app.post("/api/process")
async def process_request(
    request: ProcessRequest,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_bearer)
):
    # SECURITY: Verify JWT Authorization Bearer Token
    if not credentials or not credentials.credentials:
        raise HTTPException(status_code=401, detail="Unauthorized: Missing Authorization Bearer JWT Token")

    jwt_payload = verify_jwt_token(credentials.credentials)
    if not jwt_payload:
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid or expired JWT Token")

    username = jwt_payload.get("sub", "user")
    request_id = request.request_id
    queue = pending_requests.get(request_id)
    
    if not queue:
        raise HTTPException(
            status_code=400,
            detail=f"No active SSE stream for request_id '{request_id}'."
        )

    # -------------------------------------------------------------
    # MIDDLEWARE INPUT VALIDATION
    # -------------------------------------------------------------
    try:
        validated_name = validate_name(request.name)
    except ValueError as val_err:
        error_message = str(val_err)
        print(f"[Middleware] Validation Failed for request_id {request_id}: {error_message}")
        
        await queue.put({
            "type": "error",
            "success": False,
            "error": error_message,
            "request_id": request_id
        })
        
        raise HTTPException(status_code=400, detail=error_message)

    callback_url = f"{MIDDLEWARE_HOST}/api/callback/{request_id}"

    # Step 2 Event: POST Validated & JWT Verified
    await queue.put({
        "type": "flow_step",
        "step": 2,
        "node": "middleware",
        "title": "JWT Verified & Name Validated",
        "detail": f"JWT User '{username}' authenticated. Name '{validated_name}' passed validation."
    })

    # Step 3 Event: Sending Callback URL to Backend
    await queue.put({
        "type": "flow_step",
        "step": 3,
        "node": "backend",
        "title": "POST Forwarded to Backend with Callback URL",
        "detail": f"Sent validated payload + callback_url to Backend. Backend returns 202 Accepted immediately."
    })

    # Send POST to Backend containing callback_url
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                BACKEND_URL,
                json={
                    "name": validated_name,
                    "request_id": request_id,
                    "callback_url": callback_url
                },
                timeout=5.0
            )
        print(f"[Middleware] Backend acknowledged POST with status {resp.status_code}: {resp.json()}")
    except Exception as e:
        print(f"[Middleware] Error calling Backend: {e}")
        await queue.put({
            "type": "error",
            "success": False,
            "error": f"Failed to post to backend: {str(e)}",
            "request_id": request_id
        })

    return {
        "status": "accepted",
        "message": f"Name '{validated_name}' validated for JWT user '{username}' and dispatched to backend",
        "request_id": request_id,
        "callback_url": callback_url
    }

# Callback Webhook invoked by Backend when computation completes!
@app.post("/api/callback/{request_id}")
async def receive_backend_callback(request_id: str, payload: CallbackPayload):
    print(f"[Middleware] Webhook Callback received from Backend for request_id {request_id}: {payload}")
    
    queue = pending_requests.get(request_id)
    if not queue:
        print(f"[Middleware] Warning: No active SSE listener for callback request_id {request_id}")
        return {"status": "ignored", "reason": "No active listener"}

    # Step 4 Event: Callback Webhook Triggered by Backend
    await queue.put({
        "type": "flow_step",
        "step": 4,
        "node": "middleware",
        "title": f"Backend Callback Webhook Triggered ({payload.delay_seconds}s)",
        "detail": f"Backend finished 5s-12s job and invoked POST {payload.request_id} callback URL!",
        "delay_seconds": payload.delay_seconds
    })

    # Step 5 Event: Push SSE Event to React
    await queue.put({
        "type": "flow_step",
        "step": 5,
        "node": "frontend",
        "title": "Pushing SSE Event to Frontend",
        "detail": f"Pushing Server-Sent Event to React client.",
    })

    # Final Result Event
    await queue.put({
        "type": "message",
        "success": payload.success,
        "data": {
            "message": payload.message,
            "delay_seconds": payload.delay_seconds
        },
        "request_id": request_id
    })

    return {"status": "ok", "message": "Callback processed and delivered to SSE queue"}

