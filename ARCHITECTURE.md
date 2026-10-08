# Simple Architecture & System Summary

## 🟢 Overview
A 3-Tier Web Application featuring **JWT Authentication**, **2-Layer Input Validation**, **Asynchronous Background Processing**, **Webhook Callbacks**, and **Real-Time Server-Sent Events (SSE)**.

---

## 🏗️ 3-Tier Components & Tech Stack

| Tier | Component | Technology | Port | Primary Responsibilities |
| :--- | :--- | :--- | :--- | :--- |
| **Tier 1** | **Frontend** | React, TypeScript, Vite | `5173` | User Interface, Form Inputs, JWT state management, Real-time SSE listener, Visual progress status. |
| **Tier 2** | **Middleware** | FastAPI (Python) | `8000` | User login (JWT), 1st-level validation, SSE stream connection manager, Callback webhook receiver. |
| **Tier 3** | **Backend** | FastAPI (Python) | `8001` | 2nd-level validation (Pydantic), Asynchronous background jobs (5–12s delay), Webhook triggers. |

---

## ⚙️ Key Concepts & Techniques Used

1. **JWT Authentication:**
   - User logs in $\rightarrow$ Middleware generates a secure JWT token $\rightarrow$ Frontend attaches token to requests.

2. **2-Layer Input Validation:**
   - **Layer 1 (Middleware):** Validates name length ($\ge$ 3 letters) and ensures alphabetic characters only.
   - **Layer 2 (Backend):** Uses Pydantic models to enforce data schemas before starting execution.

3. **Asynchronous Background Processing:**
   - Backend returns `202 Accepted` immediately so the UI stays responsive, while executing a long task (5–12 seconds) in the background.

4. **Webhook Callback:**
   - When the Backend finishes processing, it sends an HTTP `POST` request to Middleware's callback URL to report completion.

5. **Server-Sent Events (SSE):**
   - Middleware pushes real-time updates directly to the React UI without any polling.
