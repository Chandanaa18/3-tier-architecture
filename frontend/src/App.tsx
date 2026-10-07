import React, { useState, useEffect, useRef } from 'react';
import './index.css';

interface LogEntry {
  id: string;
  time: string;
  text: string;
  type: 'info' | 'success' | 'warn' | 'error';
}

interface ActiveRequest {
  id: string;
  name: string;
  startTime: number;
  elapsedSeconds: number;
  status: string;
  step: number;
}

interface ToastAlert {
  id: string;
  name: string;
  message: string;
  delaySeconds: number;
  timeStr: string;
}

export const App: React.FC = () => {
  const [nameInput, setNameInput] = useState<string>('');
  const [validationError, setValidationError] = useState<string | null>(null);
  const [activeRequests, setActiveRequests] = useState<ActiveRequest[]>([]);
  const [toasts, setToasts] = useState<ToastAlert[]>([]);
  const [logs, setLogs] = useState<LogEntry[]>([]);

  const inputRef = useRef<HTMLInputElement>(null);
  const activeStreamsRef = useRef<{ [key: string]: EventSource }>({});
  const timerRef = useRef<number | null>(null);

  const addLog = (text: string, type: 'info' | 'success' | 'warn' | 'error' = 'info') => {
    const time = new Date().toLocaleTimeString();
    const entry: LogEntry = { id: Math.random().toString(36).substring(2, 9), time, text, type };
    setLogs((prev) => [entry, ...prev]);
  };

  useEffect(() => {
    addLog('Multi-Layer Validated 3-Tier Application ready.', 'info');
    inputRef.current?.focus();

    // Live ticker for elapsed seconds on active in-flight requests
    timerRef.current = window.setInterval(() => {
      const now = Date.now();
      setActiveRequests((prevRequests) =>
        prevRequests.map((req) => ({
          ...req,
          elapsedSeconds: Math.round(((now - req.startTime) / 1000) * 10) / 10,
        }))
      );
    }, 100);

    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
      Object.values(activeStreamsRef.current).forEach((es) => es.close());
    };
  }, []);

  // INSTANT FRONTEND INPUT VALIDATION
  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    setNameInput(value);

    const trimmed = value.trim();

    if (!value) {
      setValidationError(null);
      return;
    }

    if (trimmed.length < 3) {
      setValidationError("⚠️ Frontend Validation Warning: Name must be at least 3 alphabetic letters long (e.g. 'tom' is valid, 'uy' is too short).");
      return;
    }

    // Check for numbers or special characters using regex
    const nameRegex = /^[a-zA-Z]+(?:\s+[a-zA-Z]+)*$/;
    if (!nameRegex.test(trimmed)) {
      setValidationError('⚠️ Frontend Validation Warning: Name must contain only alphabetic letters (no numbers or special characters).');
    } else {
      setValidationError(null);
    }
  };

  const handleDismissToast = (id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const cleanName = nameInput.trim();

    // FRONTEND VALIDATION CHECK BEFORE DISPATCHING
    if (!cleanName) {
      setValidationError('⚠️ Please enter a name.');
      addLog('Frontend Validation Error: Empty name input.', 'error');
      return;
    }

    if (cleanName.length < 3) {
      setValidationError(`⚠️ '${cleanName}' is too short. Name must be at least 3 letters long.`);
      addLog(`Frontend Validation Error: Rejected '${cleanName}' (too short)`, 'error');
      return;
    }

    const nameRegex = /^[a-zA-Z]+(?:\s+[a-zA-Z]+)*$/;
    if (!nameRegex.test(cleanName)) {
      setValidationError('⚠️ Name must contain only alphabetic letters (no numbers or symbols).');
      addLog(`Frontend Validation Error: Rejected '${cleanName}'`, 'error');
      return;
    }

    // Clear input & validation state immediately for non-blocking submit
    setNameInput('');
    setValidationError(null);
    inputRef.current?.focus();

    const newRequestId = crypto.randomUUID();
    const startTime = Date.now();

    addLog(`[Submit] Dispatched request for '${cleanName}' (ID: ${newRequestId.substring(0, 8)}...)`, 'info');

    const newReqItem: ActiveRequest = {
      id: newRequestId,
      name: cleanName,
      startTime,
      elapsedSeconds: 0,
      status: 'Connecting SSE Stream...',
      step: 1,
    };
    setActiveRequests((prev) => [...prev, newReqItem]);

    // 1. Establish Native SSE stream for this request_id
    const sseUrl = `http://localhost:8000/api/stream/${newRequestId}`;
    const eventSource = new EventSource(sseUrl);
    activeStreamsRef.current[newRequestId] = eventSource;

    // Listen to flow step events
    eventSource.addEventListener('flow_step', (event: MessageEvent) => {
      try {
        const payload = JSON.parse(event.data);
        const { step, title } = payload;

        setActiveRequests((prev) =>
          prev.map((req) => (req.id === newRequestId ? { ...req, step, status: title } : req))
        );

        if (step === 1) {
          // SSE Connected! Send Native fetch() POST to Middleware
          fetch('http://localhost:8000/api/process', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name: cleanName, request_id: newRequestId }),
          })
            .then(async (res) => {
              if (!res.ok) {
                const errData = await res.json();
                throw new Error(errData.detail || `HTTP ${res.status}`);
              }
              return res.json();
            })
            .catch((err) => {
              addLog(`Middleware Rejected: ${err.message}`, 'error');
              eventSource.close();
              delete activeStreamsRef.current[newRequestId];
              setActiveRequests((prev) => prev.filter((r) => r.id !== newRequestId));
            });
        }
      } catch (err: any) {
        addLog(`Error parsing SSE flow step: ${err.message}`, 'error');
      }
    });

    // Listen for final result message pushed over SSE
    eventSource.addEventListener('message', (event: MessageEvent) => {
      try {
        const payload = JSON.parse(event.data);

        if (payload.success && payload.data?.message) {
          const finalMsg = payload.data.message;
          const delaySec = payload.data.delay_seconds || Math.round(((Date.now() - startTime) / 1000) * 10) / 10;

          addLog(`🎉 [SSE Result Received] '${cleanName}': "${finalMsg}" (backend delay: ${delaySec}s)`, 'success');

          // Push popup alert toast
          const newToast: ToastAlert = {
            id: Math.random().toString(36).substring(2, 9),
            name: cleanName,
            message: finalMsg,
            delaySeconds: delaySec,
            timeStr: new Date().toLocaleTimeString(),
          };
          setToasts((prev) => [newToast, ...prev]);
        } else {
          addLog(`Error for '${cleanName}': ${payload.error}`, 'error');
        }

        // Cleanup SSE stream
        eventSource.close();
        delete activeStreamsRef.current[newRequestId];
        setActiveRequests((prev) => prev.filter((r) => r.id !== newRequestId));
      } catch (err: any) {
        addLog(`Error parsing result message: ${err.message}`, 'error');
        eventSource.close();
        delete activeStreamsRef.current[newRequestId];
        setActiveRequests((prev) => prev.filter((r) => r.id !== newRequestId));
      }
    });

    eventSource.onerror = () => {
      eventSource.close();
      delete activeStreamsRef.current[newRequestId];
      setActiveRequests((prev) => prev.filter((r) => r.id !== newRequestId));
    };
  };

  return (
    <div className="app-container">
      {/* POPUP TOAST ALERTS STACK */}
      <div className="toast-container">
        {toasts.map((toast) => (
          <div key={toast.id} className="toast-alert">
            <div className="toast-header">
              <span className="toast-title">🎉 Response Received ({toast.delaySeconds}s)</span>
              <button className="toast-close-btn" onClick={() => handleDismissToast(toast.id)}>
                ✕
              </button>
            </div>
            <div className="toast-message">{toast.message}</div>
            <div className="toast-meta">
              Pushed via SSE at {toast.timeStr} • Verified by Frontend, Middleware & Backend
            </div>
          </div>
        ))}
      </div>

      <header className="header">
        <h1>Multi-Layer Validated 3-Tier Architecture</h1>
        <p>Instant Frontend Validation + Middleware Edge Security + Backend Data Integrity</p>
        <div className="badge-row">
          <span className="tech-badge"><span className="dot"></span>React Frontend Validation</span>
          <span className="tech-badge"><span className="dot"></span>FastAPI Middleware Security</span>
          <span className="tech-badge"><span className="dot"></span>FastAPI Backend Pydantic Check</span>
          <span className="tech-badge"><span className="dot"></span>Min 3 Letters Rule</span>
        </div>
      </header>

      {/* Input Form with Instant Live Validation */}
      <div className="form-card">
        <form onSubmit={handleSubmit}>
          <div className="input-group">
            <input
              ref={inputRef}
              type="text"
              className={`input-field ${validationError ? 'input-error' : ''}`}
              value={nameInput}
              onChange={handleInputChange}
              placeholder="Enter name (min 3 letters, e.g. tom, alex, harsha)..."
            />
            <button type="submit" className="btn-submit" disabled={!!validationError}>
              Submit
            </button>
          </div>
          {validationError && (
            <div className="validation-warning-text">{validationError}</div>
          )}
        </form>
      </div>

      {/* Active In-Flight Requests Monitor */}
      <div className="active-requests-panel">
        <div className="panel-header">
          <div className="panel-title">
            <span>In-Flight Requests (Processing in Backend)</span>
            <span className="active-count-badge">{activeRequests.length} Active</span>
          </div>
        </div>

        {activeRequests.length === 0 ? (
          <div style={{ color: 'var(--text-muted)', fontSize: '0.9rem', textAlign: 'center', padding: '1rem' }}>
            No active requests. Enter a name above and click <strong>Submit</strong>!
          </div>
        ) : (
          <div className="request-cards-grid">
            {activeRequests.map((req) => (
              <div key={req.id} className="req-card">
                <div className="req-card-header">
                  <span className="req-name">{req.name}</span>
                  <span className="req-timer">{req.elapsedSeconds.toFixed(1)}s</span>
                </div>
                <div className="req-status-text">
                  <span className="pulse-dot"></span> {req.status}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Real-Time Communication Log */}
      <div className="log-console">
        <div className="log-header">
          <span>Real-Time Event Stream Log</span>
          <span>{activeRequests.length} active streams</span>
        </div>
        {logs.map((log) => (
          <div key={log.id} className={`log-item ${log.type}`}>
            <span className="time">[{log.time}]</span>
            {log.text}
          </div>
        ))}
      </div>
    </div>
  );
};

export default App;
