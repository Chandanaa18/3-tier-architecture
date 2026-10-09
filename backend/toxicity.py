import asyncio
import os
from typing import Dict, Any
from transformers import pipeline

# Global model instance (singleton pattern)
_toxicity_classifier = None

# Default configurable threshold
DEFAULT_TOXICITY_THRESHOLD = float(os.getenv("TOXICITY_THRESHOLD", "0.5"))

def load_toxicity_model(model_name: str = "yrrhall/bert-mini-toxicity"):
    """
    Loads Hugging Face BERT-Mini toxicity classification model once on Backend startup.
    """
    global _toxicity_classifier
    if _toxicity_classifier is None:
        print(f"[Backend Toxicity] Loading model '{model_name}' once during server initialization...")
        try:
            _toxicity_classifier = pipeline("text-classification", model=model_name)
            print(f"[Backend Toxicity] Model '{model_name}' loaded successfully!")
        except Exception as e:
            print(f"[Backend Toxicity] Failed to load model '{model_name}': {e}")
            _toxicity_classifier = None
    return _toxicity_classifier

def classify_text_sync(text: str, threshold: float = DEFAULT_TOXICITY_THRESHOLD) -> Dict[str, Any]:
    """
    Synchronously classifies incoming text as toxic or not-toxic using BERT-Mini.
    Returns predicted label, confidence score, and decision.
    """
    if _toxicity_classifier is None:
        # Fallback if model failed to load
        return {
            "label": "not-toxic",
            "raw_label": "unknown",
            "score": 0.0,
            "is_toxic": False,
            "threshold": threshold
        }
    
    results = _toxicity_classifier(text)
    # Pipeline output format: [{'label': 'toxic' / 'not-toxic' / 'LABEL_1' / 'LABEL_0', 'score': 0.98}]
    first_res = results[0] if isinstance(results, list) and len(results) > 0 else {}
    raw_label = str(first_res.get("label", "")).strip().lower()
    score = float(first_res.get("score", 0.0))
    
    # Check whether the model predicted toxicity
    # Note: Avoid substring match where 'toxic' matches 'not-toxic'
    if "not" in raw_label or "non" in raw_label or raw_label in {"label_0", "safe", "clean", "benign"}:
        label_is_toxic = False
    elif raw_label in {"toxic", "label_1", "abuse", "insult", "profanity"}:
        label_is_toxic = True
    else:
        # Fallback check for labels like 'toxic_speech' but not 'not_toxic'
        label_is_toxic = ("toxic" in raw_label) and ("not" not in raw_label) and ("non" not in raw_label)
    
    # Treat toxic label with confidence score >= threshold as toxic (rejected)
    is_toxic = label_is_toxic and (score >= threshold)
    
    canonical_label = "toxic" if is_toxic else "not-toxic"
    
    return {
        "label": canonical_label,
        "raw_label": raw_label,
        "score": score,
        "is_toxic": is_toxic,
        "threshold": threshold
    }

async def classify_text_async(text: str, threshold: float = DEFAULT_TOXICITY_THRESHOLD) -> Dict[str, Any]:
    """
    Asynchronous wrapper using asyncio.to_thread to run CPU-bound model inference
    in a separate threadpool, avoiding blocking the FastAPI event loop.
    """
    return await asyncio.to_thread(classify_text_sync, text, threshold)
