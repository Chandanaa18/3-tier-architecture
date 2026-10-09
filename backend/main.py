import asyncio
import random
import re
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, field_validator
import httpx
try:
    from backend.toxicity import load_toxicity_model, classify_text_async
except ImportError:
    from toxicity import load_toxicity_model, classify_text_async

app = FastAPI(title="Backend Service (Toxicity Classifier & Callback)", version="1.0.0")

@app.on_event("startup")
async def startup_event():
    """Load yrrhall/bert-mini-toxicity model once when Backend server starts up."""
    print("[Backend] Server starting up. Pre-loading BERT-Mini toxicity model...")
    load_toxicity_model()

class ProcessPayload(BaseModel):
    name: str = Field(..., min_length=1)
    request_id: str = Field(..., min_length=1)
    callback_url: str = Field(..., min_length=1, description="Webhook Callback URL provided by Middleware")

    @field_validator('name')
    @classmethod
    def validate_backend_name(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("Backend Validation Error: Input cannot be empty or blank whitespace.")
        if not re.search(r"[a-zA-Z0-9]", cleaned):
            raise ValueError("Backend Validation Error: Input cannot consist only of special characters.")
        
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
    return {"status": "ok", "service": "backend", "mode": "callback_webhook", "toxicity_classifier": "enabled"}

async def execute_backend_job(name: str, request_id: str, callback_url: str):
    """
    Background task executing:
    1. Async non-blocking BERT-Mini toxicity classification
    2. If toxic: return rejection via callback immediately without delay
    3. If not-toxic: proceed with 5s-12s processing delay and callback completion
    """
    # 1. Run BERT-Mini toxicity classification asynchronously (using asyncio.to_thread)
    toxicity_res = await classify_text_async(name, threshold=0.5)
    
    is_toxic = toxicity_res["is_toxic"]
    score = toxicity_res["score"]
    label = toxicity_res["label"]
    
    print(f"[Backend] Toxicity Evaluation for '{name}': label='{label}', score={score:.4f}, is_toxic={is_toxic}")
    
    # 2. Rejection branch for toxic content
    if is_toxic:
        print(f"[Backend] REJECTED: Input '{name}' classified as toxic (score={score:.4f}). Skipping processing.")
        rejection_payload = {
            "success": False,
            "message": "Content rejected: Input text failed toxicity classification policy.",
            "delay_seconds": 0.0,
            "request_id": request_id
        }
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(callback_url, json=rejection_payload, timeout=10.0)
                print(f"[Backend] Rejection callback sent to Middleware: HTTP {resp.status_code}")
        except Exception as e:
            print(f"[Backend] Error executing rejection callback to {callback_url}: {e}")
        return

    # 3. Continuation branch for non-toxic content
    delay_seconds = round(random.uniform(5.0, 12.0), 1)
    print(f"[Backend] Passed toxicity check. Sleeping {delay_seconds}s before calling Webhook: {callback_url}")
    
    await asyncio.sleep(delay_seconds)
    
    result_message = f"Hello {name}"
    print(f"[Backend] Job complete for '{name}' after {delay_seconds}s. Executing Callback POST -> {callback_url}")
    
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

