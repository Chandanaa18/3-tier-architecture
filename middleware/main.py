import asyncio
import json
import re
from typing import Dict
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
import httpx

app = FastAPI(title="Middleware Service (Validation & Callback Pattern)", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory dictionary mapping request_id -> asyncio.Queue
pending_requests: Dict[str, asyncio.Queue] = {}

BACKEND_URL = "http://127.0.0.1:8001/process"

class ProcessRequest(BaseModel):
    name: str = Field(..., description="User's name to validate")
    request_id: str = Field(..., min_length=1, description="Unique correlation ID for SSE connection")

class CallbackPayload(BaseModel):
    success: bool
    message: str
    delay_seconds: float
    request_id: str

def validate_name(name: str) -> str:
    """
    Validates that the input name:
    1. Is not empty or blank whitespace.
    2. Has a MINIMUM length of 3 alphabetic characters (e.g., 'tom' is valid, 'uy' is invalid).
    3. Contains ONLY alphabetic letters (a-z, A-Z) and single spaces between words.
    4. Rejects numbers (0-9) and special characters (!, @, #, $, %, etc.).
    """
    cleaned = name.strip()
    
    # Check 1: Empty or blank whitespace check
    if not cleaned:
        raise ValueError("Validation Error: Name cannot be empty or consist only of whitespace.")

    # Check 2: Minimum length check (must be at least 3 letters)
    if len(cleaned) < 3:
        raise ValueError(f"Validation Error: '{cleaned}' is too short. Name must be at least 3 alphabetic letters long.")
    
    # Check 3: Regex check - Only alphabetic characters and single spaces between words
    if not re.match(r"^[a-zA-Z]+(?:\s+[a-zA-Z]+)*$", cleaned):
        raise ValueError("Validation Error: Name must contain only alphabetic letters (no numbers or special characters allowed).")
    
    return cleaned

@app.get("/")
async def root():
    return {
        "service": "FastAPI Middleware Service",
        "status": "running",
        "port": 8000,
        "active_sse_streams": len(pending_requests),
        "docs_url": "http://localhost:8000/docs",
        "health_url": "http://localhost:8000/health"
    }

@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "service": "middleware",
        "mode": "callback_webhook",
        "active_sse_connections": len(pending_requests)
    }

async def sse_event_generator(request_id: str):
    queue = asyncio.Queue()
    pending_requests[request_id] = queue
    print(f"[Middleware] SSE Connection established for request_id: {request_id}")
    
    try:
        init_event = {
            "type": "flow_step",
            "step": 1,
            "node": "middleware",
            "title": "SSE Stream Connected",
            "detail": f"Native EventSource connected to Middleware (Port 8000) [request_id: {request_id[:8]}...]",
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
async def stream_events(request_id: str):
    return StreamingResponse(
        sse_event_generator(request_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

@app.post("/api/process")
async def process_request(request: ProcessRequest):
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
        
        # Send error event over SSE to notify frontend UI
        await queue.put({
            "type": "error",
            "success": False,
            "error": error_message,
            "request_id": request_id
        })
        
        raise HTTPException(status_code=400, detail=error_message)

    callback_url = f"http://127.0.0.1:8000/api/callback/{request_id}"

    # Step 2 Event: POST Validated Successfully
    await queue.put({
        "type": "flow_step",
        "step": 2,
        "node": "middleware",
        "title": "POST Validated Successfully",
        "detail": f"Name '{validated_name}' passed validation (min 3 letters). Callback URL: {callback_url}"
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
        "message": f"Name '{validated_name}' validated and dispatched to backend",
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
