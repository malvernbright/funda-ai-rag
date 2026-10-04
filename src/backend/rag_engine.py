import os
import re
import time
import threading
import warnings
import requests
from dotenv import load_dotenv
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
from langchain_google_genai import GoogleGenerativeAIEmbeddings, ChatGoogleGenerativeAI
from langchain_core.output_parsers import StrOutputParser

warnings.filterwarnings("ignore", category=DeprecationWarning, module="langchain_community")

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VECTOR_STORE_PATH = os.path.join(os.path.dirname(BASE_DIR), "chroma_db")
KNOWLEDGEBASE_DIR = os.path.join(BASE_DIR, "knowledgebase")

EMBEDDING_MODEL = "models/gemini-embedding-001"
LLM_MODEL = "gemini-flash-latest"

# Morena runs as a local llama.cpp server, e.g.:
#   llama-server -hf vamboai/morena-1.5b-instruct-gguf:Q4_K_M --port 8081 -c 4096
MORENA_URL = os.getenv("MORENA_URL", "http://localhost:8081")

# Alternative: load the .gguf inside this Python process (needs `pip install llama-cpp-python`).
# If MORENA_MODEL_PATH is set, it is used instead of the server.
MORENA_MODEL_PATH = os.getenv("MORENA_MODEL_PATH")
_morena_llm = None
_morena_lock = threading.Lock()  # a llama.cpp model object must not be used by two requests at once

# Free-tier friendly indexing. 0 = index every chunk of every file.
MAX_CHUNKS_PER_FILE = int(os.getenv("INDEX_MAX_CHUNKS", "0")) or None
EMBED_BATCH_SIZE = int(os.getenv("EMBED_BATCH_SIZE", "50"))
EMBED_BATCH_PAUSE = float(os.getenv("EMBED_BATCH_PAUSE", "20"))

# OCR for scanned PDFs (pages with little or no extractable text)
OCR_ENABLED = os.getenv("OCR_ENABLED", "1") == "1"
OCR_LANG = os.getenv("OCR_LANG", "eng")          # Tesseract language code(s), e.g. "eng" or "eng+afr"
OCR_MIN_CHARS = int(os.getenv("OCR_MIN_CHARS", "50"))  # pages with fewer characters are OCR'd
OCR_DPI = int(os.getenv("OCR_DPI", "200"))

# UI label -> knowledgebase folder name
LEVELS = {
    "Form 1": "f1", "Form 2": "f2", "Form 3": "f3",
    "Form 4": "f4", "Form 5": "f5", "Form 6": "f6",
}

# folder name -> display label (unknown folders get a title-cased label)
SUBJECT_LABELS = {
    "comb_scie": "Combined Science",
    "english": "English Language",
    "geography": "Geography",
    "heritage_studies": "Heritage Studies",
    "math": "Mathematics",
    "shona": "Shona",
}

# Languages listed on the Morena model card. English is answered by Gemini.
LANGUAGES = {
    "English": "en",
    "Shona": "sn",
    "isiZulu": "zu",
    "isiXhosa": "xh",
    "Setswana": "tn",
    "Kiswahili": "sw",
    "Afrikaans": "af",
    "South Ndebele": "nr",
    "Kinyarwanda": "rw",
    "Hausa": "ha",
    "Yoruba": "yo",
    "Igbo": "ig",
    "Nigerian Pidgin": "pcm",
}

embeddings = GoogleGenerativeAIEmbeddings(model=EMBEDDING_MODEL)
llm = ChatGoogleGenerativeAI(model=LLM_MODEL, temperature=0.3)


# ------------------------------------------------------------------
# Knowledgebase structure helpers
# ------------------------------------------------------------------
def subject_label(subject_dir: str) -> str:
    return SUBJECT_LABELS.get(subject_dir, subject_dir.replace("_", " ").title())


def list_all_subject_dirs() -> list:
    """Known subjects plus any subject folders found on disk (used by the admin upload form)."""
    found = set(SUBJECT_LABELS)
    for level_dir in LEVELS.values():
        path = os.path.join(KNOWLEDGEBASE_DIR, level_dir)
        if os.path.isdir(path):
            found.update(d for d in os.listdir(path) if os.path.isdir(os.path.join(path, d)))
    return sorted(found)


def list_subjects(level_label: str) -> list:
    """Subjects for a level that actually contain at least one PDF: [(folder, label), ...]."""
    level_dir = LEVELS.get(level_label)
    if not level_dir:
        return []
    level_path = os.path.join(KNOWLEDGEBASE_DIR, level_dir)
    if not os.path.isdir(level_path):
        return []
    subjects = []
    for d in sorted(os.listdir(level_path)):
        sub_path = os.path.join(level_path, d)
        if os.path.isdir(sub_path) and any(f.lower().endswith(".pdf") for f in os.listdir(sub_path)):
            subjects.append((d, subject_label(d)))
    return subjects


def _parse_path(file_path: str) -> dict:
    """Derive level, subject, original name and version from knowledgebase/<level>/<subject>/<name>_vN.pdf"""
    rel = os.path.relpath(os.path.abspath(file_path), KNOWLEDGEBASE_DIR)
    parts = rel.split(os.sep)
    level, subject = "general", "general"
    if not rel.startswith("..") and len(parts) >= 3:
        level, subject = parts[0], parts[1]

    stem = os.path.splitext(parts[-1])[0]
    match = re.search(r"((?:_v\d+)+)$", stem)  # also copes with names like X_v1_v1
    if match:
        original_name = stem[:match.start()]
        version = int(re.findall(r"_v(\d+)", match.group(1))[-1])
    else:
        original_name, version = stem, 1

    return {
        "source_path": rel.replace(os.sep, "/"),
        "level": level,
        "subject": subject,
        "original_name": original_name,
        "version": version,
    }


# ------------------------------------------------------------------
# Indexing
# ------------------------------------------------------------------
def _get_vectorstore() -> Chroma:
    return Chroma(persist_directory=VECTOR_STORE_PATH, embedding_function=embeddings)


def _add_with_retry(vectorstore, batch, attempts: int = 3):
    for attempt in range(1, attempts + 1):
        try:
            vectorstore.add_documents(batch)
            return
        except Exception as e:
            if attempt == attempts:
                raise
            wait = 60 * attempt
            print(f"⚠️ Embedding batch failed ({e}). Retrying in {wait}s...")
            time.sleep(wait)


def _load_pdf(file_path: str):
    """Load a PDF page by page, running OCR on pages that have no real text layer."""
    docs = PyPDFLoader(file_path).load()
    if not OCR_ENABLED:
        return docs

    weak_pages = [i for i, d in enumerate(docs) if len(d.page_content.strip()) < OCR_MIN_CHARS]
    if not weak_pages:
        return docs

    try:
        import fitz  # PyMuPDF
        import pytesseract
        from PIL import Image
        pytesseract.get_tesseract_version()  # fails fast if the tesseract program is missing
    except Exception as e:
        print(f"⚠️ {len(weak_pages)} page(s) look scanned but OCR is unavailable ({e}). "
              "Install pymupdf, pytesseract, pillow and the tesseract program.")
        return docs

    print(f"🔍 OCR on {len(weak_pages)} of {len(docs)} pages in {os.path.basename(file_path)}...")
    pdf = fitz.open(file_path)
    try:
        for n, i in enumerate(weak_pages, start=1):
            try:
                pix = pdf[i].get_pixmap(dpi=OCR_DPI)
                image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                docs[i].page_content = pytesseract.image_to_string(image, lang=OCR_LANG)
                docs[i].metadata["ocr"] = True
            except Exception as e:
                print(f"⚠️ OCR failed on page {i + 1}: {e}")
            if n % 25 == 0:
                print(f"   ...{n}/{len(weak_pages)} pages done")
    finally:
        pdf.close()
    return docs


def ingest_curriculum_document(file_path: str):
    meta = _parse_path(file_path)

    docs = _load_pdf(file_path)
    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    splits = splitter.split_documents(docs)
    if MAX_CHUNKS_PER_FILE:
        splits = splits[:MAX_CHUNKS_PER_FILE]
    if not splits:
        raise ValueError("No readable text found in this PDF (scanned pages need OCR to be installed and enabled).")

    for doc in splits:
        doc.metadata.update(meta)
        doc.metadata["source_file"] = os.path.basename(file_path)
        doc.metadata["total_chunks"] = len(splits)

    vectorstore = _get_vectorstore()

    # Clear any partial leftovers from an earlier interrupted run of this same file
    try:
        vectorstore.delete(where={"source_path": meta["source_path"]})
    except Exception:
        pass

    # A newer version replaces older versions of the same document in the same level/subject
    try:
        vectorstore.delete(where={"$and": [
            {"original_name": meta["original_name"]},
            {"level": meta["level"]},
            {"subject": meta["subject"]},
            {"version": {"$lt": meta["version"]}},
        ]})
    except Exception as e:
        print(f"⚠️ Could not remove older versions: {e}")

    for i in range(0, len(splits), EMBED_BATCH_SIZE):
        _add_with_retry(vectorstore, splits[i:i + EMBED_BATCH_SIZE])
        if i + EMBED_BATCH_SIZE < len(splits):
            time.sleep(EMBED_BATCH_PAUSE)

    return {"status": "success", "chunks_indexed": len(splits), **meta}


_index_run_lock = threading.Lock()
_index_state = {"running": False, "total": 0, "done": 0, "current": None, "failed": []}
_auto_index_started = False


def indexing_status() -> dict:
    return dict(_index_state)


def index_knowledgebase() -> dict:
    """Index every PDF under knowledgebase/<level>/<subject>/ that is not indexed yet (latest version only)."""
    if not _index_run_lock.acquire(blocking=False):
        return {"indexed": [], "skipped": [], "failed": [], "busy": True}
    try:
        _index_state.update(running=True, total=0, done=0, current=None, failed=[])

        latest = {}
        for level_dir in LEVELS.values():
            for root, _, files in os.walk(os.path.join(KNOWLEDGEBASE_DIR, level_dir)):
                for name in files:
                    if not name.lower().endswith(".pdf"):
                        continue
                    path = os.path.join(root, name)
                    meta = _parse_path(path)
                    if meta["level"] == "general":
                        continue
                    key = (meta["level"], meta["subject"], meta["original_name"])
                    if key not in latest or meta["version"] > latest[key][0]:
                        latest[key] = (meta["version"], path, meta)

        vectorstore = _get_vectorstore()
        indexed, skipped, failed, pending = [], [], [], []
        for _, (_, path, meta) in sorted(latest.items()):
            existing = vectorstore.get(where={"source_path": meta["source_path"]}, include=["metadatas"])
            ids = existing["ids"]
            expected = (existing["metadatas"][0] or {}).get("total_chunks", 0) if ids else 0
            if ids and len(ids) >= expected:
                skipped.append(meta["source_path"])
            else:
                pending.append((path, meta))

        _index_state["total"] = len(pending)
        for path, meta in pending:
            _index_state["current"] = meta["source_path"]
            try:
                result = ingest_curriculum_document(path)
                indexed.append(f"{meta['source_path']} ({result['chunks_indexed']} chunks)")
            except Exception as e:
                failed.append(f"{meta['source_path']}: {e}")
            _index_state["done"] += 1
            _index_state["failed"] = list(failed)

        return {"indexed": indexed, "skipped": skipped, "failed": failed}
    finally:
        _index_state.update(running=False, current=None)
        _index_run_lock.release()


def start_background_indexing():
    """Index the whole knowledgebase in a background thread, once per process, without blocking startup."""
    global _auto_index_started
    if _auto_index_started:
        return
    _auto_index_started = True
    _index_state["running"] = True

    def _run():
        try:
            summary = index_knowledgebase()
            print(f"📚 Indexed: {len(summary['indexed'])} | Already indexed: {len(summary['skipped'])} | Failed: {len(summary['failed'])}")
            for item in summary["failed"]:
                print(f"❌ {item}")
        except Exception as e:
            print(f"❌ Background indexing crashed: {e}")
            _index_state["running"] = False

    threading.Thread(target=_run, daemon=True, name="kb-indexer").start()


def initialize_knowledgebase():
    start_background_indexing()


# ------------------------------------------------------------------
# Tutoring
# ------------------------------------------------------------------
def format_docs(docs):
    return "\n\n".join(doc.page_content for doc in docs)


def _build_filter(level_dir, subject):
    clauses = []
    if level_dir:
        clauses.append({"level": level_dir})
    if subject:
        clauses.append({"subject": subject})
    if not clauses:
        return None
    return clauses[0] if len(clauses) == 1 else {"$and": clauses}


def _build_prompt(question, level, subject, language, history, context):
    scope = level + (f", {subject_label(subject)}" if subject else "")
    return (
        "You are an expert, encouraging AI tutor for the Zimbabwe Heritage-Based Curriculum.\n"
        f"Your goal is to TEACH the student ({scope}), not just give static answers. "
        "Explain concepts clearly, step by step, and finish with one short check-for-understanding question.\n"
        "Use ONLY the context below. If the context does not contain the answer, say clearly that the information is outside the syllabus.\n"
        f"Write your entire reply in {language}.\n\n"
        f"Previous Conversation History:\n{history}\n\n"
        f"Context:\n{context}\n\n"
        f"Student Message: {question}"
    )


def _morena_prompt(prompt: str) -> str:
    """Morena uses <reserved_0> (user) and <reserved_1> (assistant) as its chat turn tokens."""
    return f"<reserved_0>\n{prompt}\n<reserved_1>\n"


def _call_morena_local(prompt: str) -> str:
    global _morena_llm
    with _morena_lock:
        if _morena_llm is None:  # loaded lazily on first use
            from llama_cpp import Llama
            _morena_llm = Llama(model_path=MORENA_MODEL_PATH, n_ctx=4096, verbose=False)
        result = _morena_llm.create_completion(
            prompt=_morena_prompt(prompt),
            max_tokens=600,
            temperature=0.3,
            stop=["<reserved_0>", "<reserved_1>"],
        )
    return result["choices"][0]["text"].strip()


def _call_morena(prompt: str) -> str:
    if MORENA_MODEL_PATH:
        return _call_morena_local(prompt)
    return _call_morena_server(prompt)


def _call_morena_server(prompt: str) -> str:
    payload = {
        "prompt": _morena_prompt(prompt),
        "n_predict": 600,
        "temperature": 0.3,
        "stop": ["<reserved_0>", "<reserved_1>"],
    }
    response = requests.post(f"{MORENA_URL}/completion", json=payload, timeout=120)
    response.raise_for_status()
    return response.json()["content"].strip()


def query_tutor(student_query: str, student_level: str = "Form 1", chat_history: list = None,
                subject: str = None, language: str = "English"):
    # Keep only the last few turns so small-context models are not overloaded
    history_text = "\n".join(
        f"{msg['role'].capitalize()}: {msg['content']}" for msg in (chat_history or [])[-6:]
    )

    try:
        vectorstore = _get_vectorstore()
        search_filter = _build_filter(LEVELS.get(student_level), subject)
        docs = vectorstore.similarity_search(student_query, k=4, filter=search_filter)

        if not docs:
            scope = student_level + (f" {subject_label(subject)}" if subject else "")
            status = indexing_status()
            if status["running"]:
                message = (f"The library is still being indexed ({status['done']} of {status['total']} files done), "
                           f"so I can't see all the {scope} material yet. Please try again in a few minutes.")
            else:
                message = (f"I couldn't find any indexed material for {scope} that matches your question. "
                           "Try another subject, or ask your teacher to upload the relevant book.")
            return {
                "answer": message,
                "context_used": [],
                "student_level": student_level,
                "subject": subject,
                "language": language,
                "model_used": "none",
                "safeguard_notice": "No curriculum material was retrieved for this question."
            }

        prompt = _build_prompt(student_query, student_level, subject, language, history_text, format_docs(docs))

        answer, model_used = None, "gemini"
        if language != "English":
            try:
                answer = _call_morena(prompt)
                model_used = "morena-1.5b"
            except Exception as e:
                print(f"⚠️ Morena unavailable ({e}); falling back to Gemini.")
        if not answer:
            answer = (llm | StrOutputParser()).invoke(prompt)
            model_used = "gemini"

        notice = ("AI-generated response based on indexed curriculum documents. "
                  "Verify critical historical facts against official textbooks.")
        if model_used == "morena-1.5b":
            notice += " This reply was written by a small 1.5B-parameter model, so check it carefully."

        return {
            "answer": answer,
            "context_used": [doc.page_content for doc in docs],
            "student_level": student_level,
            "subject": subject,
            "language": language,
            "model_used": model_used,
            "safeguard_notice": notice
        }
    except Exception as e:
        print(f"❌ RAG Execution Error: {str(e)}")
        raise e
        