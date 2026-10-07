import asyncio
import random
import re
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, field_validator
import httpx

app = FastAPI(title="Backend Service (Multi-Layer Validation & Callback)", version="1.0.0")

class ProcessPayload(BaseModel):
    name: str = Field(..., min_length=1)
    request_id: str = Field(..., min_length=1)
    callback_url: str = Field(..., min_length=1, description="Webhook Callback URL provided by Middleware")

    @field_validator('name')
    @classmethod
    def validate_backend_name(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Backend Validation Error: Name cannot be empty or blank whitespace.")
        if len(cleaned) < 3:
            raise ValueError(f"Backend Validation Error: '{cleaned}' is too short. Name must be at least 3 letters long.")
        if not re.match(r"^[a-zA-Z]+(?:\s+[a-zA-Z]+)*$", cleaned):
            raise ValueError("Backend Validation Error: Name must contain only alphabetic letters (no numbers or special characters allowed).")
        return cleaned

@app.get("/")
async def root():
    return {
        "service": "FastAPI Backend Service",
        "status": "running",
        "port": 8001,
        "docs_url": "http://localhost:8001/docs",
        "health_url": "http://localhost:8001/health"
    }

@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "backend", "mode": "callback_webhook"}

async def execute_backend_job(name: str, request_id: str, callback_url: str):
    """Background task executing the 5s-12s delay, then invoking the Middleware Callback URL."""
    delay_seconds = round(random.uniform(5.0, 12.0), 1)
    print(f"[Backend] Started job for '{name}'. Sleeping {delay_seconds}s before calling Webhook: {callback_url}")
    
    # 1. Asynchronous sleep delay
    await asyncio.sleep(delay_seconds)
    
    result_message = f"Hello {name}"
    print(f"[Backend] Job complete for '{name}' after {delay_seconds}s. Executing Callback POST -> {callback_url}")
    
    # 2. Trigger HTTP POST callback to Middleware's Callback URL
    callback_payload = {
        "success": True,
        "message": result_message,
        "delay_seconds": delay_seconds,
        "request_id": request_id
    }
    
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(callback_url, json=callback_payload, timeout=10.0)
            print(f"[Backend] Callback response from Middleware: HTTP {resp.status_code}")
    except Exception as e:
        print(f"[Backend] Error executing Callback to {callback_url}: {e}")

@app.post("/process")
async def process_request(payload: ProcessPayload):
    name = payload.name
    
    # Spawn task in background and return 202 Accepted IMMEDIATELY
    asyncio.create_task(execute_backend_job(name, payload.request_id, payload.callback_url))
    
    return {
        "status": "accepted",
        "message": f"Backend validated name '{name}' and accepted task.",
        "request_id": payload.request_id,
        "callback_url": payload.callback_url
    }
