"""
Model registry + multimodal calling for Funda AI Tutor.

* Lists the models a student can pick: Auto, Gemini, Morena, and every chat model
  installed in Ollama (embedding models are filtered out automatically).
* Detects which models can read images (Ollama reports a "vision" capability).
* Sends text + images to Gemini or Ollama through one code path (LangChain).
* If the chosen model cannot see images, a vision model describes the image first
  and that description is passed along as text.
"""
import io
import os
import time
import uuid
import mimetypes
from dataclasses import dataclass
from typing import List, Optional, Tuple

import requests
from langchain_core.messages import HumanMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_ollama import ChatOllama

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CHAT_UPLOADS_DIR = os.path.join(BASE_DIR, "uploads", "chat")

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-latest")
MAX_IMAGE_SIDE = int(os.getenv("MAX_IMAGE_SIDE", "1280"))   # downscale big phone photos
MAX_IMAGES = int(os.getenv("MAX_IMAGES", "3"))

# Models hidden from the student picker (comma-separated substrings, case-insensitive).
HIDDEN_PATTERNS = [p.strip().lower() for p in
                   os.getenv("HIDDEN_MODEL_PATTERNS", "uncensored,diddy").split(",") if p.strip()]
# Optional: if set, ONLY these Ollama models are offered (comma-separated exact names).
ALLOWLIST = [p.strip() for p in os.getenv("OLLAMA_MODEL_ALLOWLIST", "").split(",") if p.strip()]

# Used only if this Ollama version does not report capabilities.
_VISION_NAME_HINTS = ("vl", "vision", "llava", "gemma3", "qwen3.5", "minicpm-v", "kimi-k2.5")


@dataclass(frozen=True)
class ModelInfo:
    key: str        # stable id used by the UI/API: "auto", "gemini", "morena", "ollama:<name>"
    label: str      # text shown in the picker
    provider: str   # "auto" | "gemini" | "morena" | "ollama"
    name: str       # provider-side model name
    vision: bool    # can it read images directly?


AUTO = ModelInfo("auto", "✨ Auto (Gemini, Morena for African languages)", "auto", "", True)
GEMINI = ModelInfo("gemini", "👁 Gemini (cloud)", "gemini", GEMINI_MODEL, True)
MORENA = ModelInfo("morena", "📝 Morena 1.5B (local, African languages)", "morena", "morena-1.5b", False)


# ------------------------------------------------------------------
# Discovery
# ------------------------------------------------------------------
_show_cache = {}
_list_cache = {"t": 0.0, "models": None}


def _capabilities(name: str) -> Optional[list]:
    if name in _show_cache:
        return _show_cache[name]
    caps = None
    try:
        r = requests.post(f"{OLLAMA_URL}/api/show", json={"model": name}, timeout=5)
        r.raise_for_status()
        caps = r.json().get("capabilities")
    except Exception:
        pass
    if caps is not None:
        _show_cache[name] = caps
    return caps


def _ollama_models() -> List[ModelInfo]:
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=3)
        r.raise_for_status()
        names = [m["name"] for m in r.json().get("models", [])]
    except Exception:
        return []  # Ollama not running -> only Gemini/Morena are offered

    found = []
    for name in sorted(names):
        low = name.lower()
        if ALLOWLIST and name not in ALLOWLIST:
            continue
        if any(p in low for p in HIDDEN_PATTERNS):
            continue
        caps = _capabilities(name)
        if caps is not None:
            if "embedding" in caps or "completion" not in caps:
                continue
            vision = "vision" in caps
        else:
            if "embed" in low:
                continue
            vision = any(h in low for h in _VISION_NAME_HINTS)
        icon = "👁" if vision else "📝"
        where = "cloud" if low.endswith(":cloud") or "-cloud" in low else "local"
        found.append(ModelInfo(f"ollama:{name}", f"{icon} {name} ({where})", "ollama", name, vision))
    return found


def list_models(ttl: float = 30.0) -> List[ModelInfo]:
    """Everything a student can pick, cached briefly so Streamlit reruns stay fast."""
    now = time.time()
    if _list_cache["models"] is None or now - _list_cache["t"] > ttl:
        _list_cache["models"] = [AUTO, GEMINI, MORENA] + _ollama_models()
        _list_cache["t"] = now
    return _list_cache["models"]


def resolve_model(key: Optional[str]) -> Optional[ModelInfo]:
    """UI key -> ModelInfo. Returns None for 'auto' (the engine's default routing)."""
    if not key or key == "auto":
        return None
    for m in list_models():
        if m.key == key:
            return m
    raise ValueError(f"Model '{key}' is not available. Is Ollama running?")


# ------------------------------------------------------------------
# Images
# ------------------------------------------------------------------
def prepare_image(raw: bytes, mime: str = "image/jpeg") -> Tuple[bytes, str]:
    """Downscale + convert to JPEG so small local models stay fast. Falls back to the original bytes."""
    try:
        from PIL import Image, ImageOps
        img = ImageOps.exif_transpose(Image.open(io.BytesIO(raw)))
        img.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))
        if img.mode != "RGB":
            img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=85)
        return buf.getvalue(), "image/jpeg"
    except Exception:
        return raw, mime or "image/jpeg"


def save_image(raw: bytes, mime: str) -> str:
    os.makedirs(CHAT_UPLOADS_DIR, exist_ok=True)
    ext = mimetypes.guess_extension(mime or "") or ".jpg"
    path = os.path.join(CHAT_UPLOADS_DIR, f"{uuid.uuid4().hex}{ext}")
    with open(path, "wb") as f:
        f.write(raw)
    return path


def _blocks(prompt: str, images) -> list:
    import base64
    content = [{"type": "text", "text": prompt}]
    for raw, mime in (images or [])[:MAX_IMAGES]:
        b64 = base64.b64encode(raw).decode()
        content.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}})
    return content


# ------------------------------------------------------------------
# Calling models
# ------------------------------------------------------------------
_chat_cache = {}


def _chat_model(info: ModelInfo):
    if info.key not in _chat_cache:
        if info.provider == "gemini":
            _chat_cache[info.key] = ChatGoogleGenerativeAI(model=info.name, temperature=0.3)
        elif info.provider == "ollama":
            _chat_cache[info.key] = ChatOllama(model=info.name, base_url=OLLAMA_URL, temperature=0.3)
        else:
            raise ValueError(f"{info.provider} models are not called through LangChain.")
    return _chat_cache[info.key]


def invoke_model(info: ModelInfo, prompt: str, images=None) -> str:
    """Send a prompt (plus images, if the model can see) to Gemini or an Ollama model."""
    content = _blocks(prompt, images) if (images and info.vision) else prompt
    return (_chat_model(info) | StrOutputParser()).invoke([HumanMessage(content=content)]).strip()


_DESCRIBE_PROMPT = (
    "Look at the attached image from a school student. Transcribe ALL visible text and maths exactly as written. "
    "Then describe any diagram, graph, map or picture in 2-3 sentences. "
    "Do NOT answer any question in it; only report what is there."
)


def describe_images(images, preferred: Optional[ModelInfo] = None,
                    prompt: Optional[str] = None, prefer_local: bool = False) -> str:
    """Turn images into text so they can drive retrieval and reach text-only models.
    prefer_local=True tries local Ollama vision models before Gemini (used for bulk figure captioning)."""
    candidates = []
    if preferred and preferred.vision and preferred.provider in ("gemini", "ollama"):
        candidates.append(preferred)
    local = [m for m in list_models() if m.provider == "ollama" and m.vision and not m.name.lower().endswith(":cloud")]
    cloud = [m for m in list_models() if m.provider == "ollama" and m.vision and m.name.lower().endswith(":cloud")]
    candidates += (local + [GEMINI] + cloud) if prefer_local else ([GEMINI] + local + cloud)

    seen, errors = set(), []
    for m in candidates:
        if m.key in seen:
            continue
        seen.add(m.key)
        try:
            return invoke_model(m, prompt or _DESCRIBE_PROMPT, images)
        except Exception as e:
            errors.append(f"{m.name}: {e}")
    raise RuntimeError("No vision model could read the image. " + " | ".join(errors))