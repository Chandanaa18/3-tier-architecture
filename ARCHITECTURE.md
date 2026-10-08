# 3-Tier Application Architecture

## 📦 System Block Diagram

```text
+-----------------------------------------------------------------------------------+
|                             3-TIER SYSTEM ARCHITECTURE                            |
+--------------------------+--------------------------+-----------------------------+
|     1. FRONTEND (UI)     |  2. MIDDLEWARE (GATEWAY) |     3. BACKEND (WORKER)     |
|       (Port 5173)        |        (Port 8000)       |         (Port 8001)         |
|                          |                          |                             |
|  • React + Vite          |  • JWT Auth (/login)     |  • Pydantic Schema          |
|  • EventSource Listener  |  • Layer-1 Validation    |  • Async Job (5s-12s)       |
|  • Real-Time UI          |  • Webhook Receiver      |  • HTTPX Webhook Trigger    |
+--------------------------+--------------------------+-----------------------------+
             |                           |                           |
             |--- 1. POST /login ------->|                           |
             |<-- Returns JWT Token -----|                           |
             |                           |                           |
             |--- 2. Connect SSE ------->|                           |
             |                           |                           |
             |--- 3. Submit Data ------->|--- 4. Validate & Forward->|
             |<-- Immediate 202 ---------|<-- 5. Return 202 ----------|
             |                           |                           |
             |                           |<=== 6. Webhook Callback ==|
             |<=== 7. SSE Realtime Push =|    (Job Done Notification)|
```

---

## 🏗️ 3-Tier Summary

| Tier | Component | Technology | Port | Key Features |
| :--- | :--- | :--- | :--- | :--- |
| **Tier 1** | **Frontend** | React, TypeScript, Vite | `5173` | UI Form, EventSource SSE listener, Live Logs. |
| **Tier 2** | **Middleware** | FastAPI (Python) | `8000` | JWT Auth, Layer-1 Validation, SSE Queue, Webhook Receiver. |
| **Tier 3** | **Backend** | FastAPI (Python) | `8001` | Layer-2 Pydantic Validation, 5-12s Async Job, Webhook Trigger. |

---

## ⚡ Concept Flow

```
[ User Input ] 
      ↓
[ JWT Login ] ──► [ Layer-1 Validation ] ──► [ Layer-2 Validation ]
                                                    ↓
[ Real-Time SSE Push ] ◄── [ Webhook Callback ] ◄── [ Async 5s-12s Job ]
```
