from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional
from backend.rag_engine import query_tutor, ingest_curriculum_document

app = FastAPI(
    title="Funda AI Tutoring API",
    description="Local offline RAG engine for the Zimbabwe Heritage-Based Curriculum",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatMessage(BaseModel):
    role: str
    content: str

class StudentQueryRequest(BaseModel):
    question: str = Field(..., example="What is the significance of Great Zimbabwe?")
    student_level: Optional[str] = Field("Form 1", example="Form 2")
    chat_history: List[ChatMessage] = []

class IngestDocumentRequest(BaseModel):
    file_path: str = Field(..., example="knowledgebase/Heritage-notes-form-1-4-2.pdf")

class QueryResponse(BaseModel):
    answer: str
    context_used: List[str]
    student_level: str
    safeguard_notice: str

@app.post("/api/v1/query", response_model=QueryResponse)
def ask_heritage_tutor(payload: StudentQueryRequest):
    """Processes a student question against the local vector database with memory."""
    if not payload.question.strip():
        raise HTTPException(status_code=400, detail="Question string cannot be empty.")
        
    try:
        # Convert Pydantic models to standard dictionaries for the RAG engine
        history_list = [{"role": msg.role, "content": msg.content} for msg in payload.chat_history]
        
        response = query_tutor(payload.question, payload.student_level, history_list)
        return response
    except Exception as e:
        error_msg = str(e)
        if "503" in error_msg or "ResourceExhausted" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE, 
                detail="Gemini API is currently experiencing high demand. Please retry in a few moments."
            )
        raise HTTPException(status_code=500, detail=error_msg)

@app.post("/api/v1/ingest")
def ingest_document(payload: IngestDocumentRequest):
    """Triggers parsing and embedding of a new curriculum PDF."""
    try:
        result = ingest_curriculum_document(payload.file_path)
        return result
    except FileNotFoundError as fnf:
        raise HTTPException(status_code=404, detail=str(fnf))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "Funda AI Engine",
        "gemini_integration": "active",
        "models": {"llm": "gemini-3.6-flash", "embeddings": "models/gemini-embedding-001"}
    }