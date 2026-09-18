from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from funda_ai_backend.rag_engine import query_tutor, ingest_curriculum_document

app = FastAPI(
    title="Funda AI Tutoring API",
    description="Local offline RAG engine for the Zimbabwe Heritage-Based Curriculum",
    version="1.0.0"
)

class QueryRequest(BaseModel):
    question: str

class IngestRequest(BaseModel):
    file_path: str

@app.post("/api/v1/query")
def ask_tutor(payload: QueryRequest):
    """Processes a student question against the local vector database."""
    try:
        response = query_tutor(payload.question)
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/ingest")
def ingest_document(payload: IngestRequest):
    """Triggers parsing and embedding of a new curriculum PDF."""
    try:
        result = ingest_curriculum_document(payload.file_path)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
def health_check():
    return {"status": "healthy", "engine": "ollama-local"}
