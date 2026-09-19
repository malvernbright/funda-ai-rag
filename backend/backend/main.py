import os
from fastapi import FastAPI, HTTPException, status, UploadFile, File, Form, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional
from contextlib import asynccontextmanager
from sqlalchemy.orm import Session
from backend.rag_engine import query_tutor, initialize_knowledgebase, ingest_curriculum_document, BASE_DIR
from backend.database import SessionLocal, init_db, User, ChatSession, ChatRecord, hash_password

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    initialize_knowledgebase()
    yield

app = FastAPI(
    title="Funda AI Tutoring API",
    description="Interactive RAG Tutor with Sessions & SQLite Auth",
    version="2.1.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class UserAuthRequest(BaseModel):
    username: str
    password: str

class CreateSessionRequest(BaseModel):
    user_id: int
    title: str

class ChatMessage(BaseModel):
    role: str
    content: str

class StudentQueryRequest(BaseModel):
    user_id: int
    session_id: int
    question: str
    student_level: Optional[str] = "Form 1"
    chat_history: List[ChatMessage] = []

class QueryResponse(BaseModel):
    answer: str
    context_used: List[str]
    student_level: str
    safeguard_notice: str

@app.post("/api/v1/auth/register")
def register_user(payload: UserAuthRequest, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.username == payload.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="Username already exists.")
    new_user = User(username=payload.username, password_hash=hash_password(payload.password), role="student")
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return {"status": "success", "user_id": new_user.id, "username": new_user.username, "role": new_user.role}

@app.post("/api/v1/auth/login")
def login_user(payload: UserAuthRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == payload.username).first()
    if not user or user.password_hash != hash_password(payload.password):
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    return {"status": "success", "user_id": user.id, "username": user.username, "role": user.role}

# --- Session Management ---
@app.post("/api/v1/sessions")
def create_session(payload: CreateSessionRequest, db: Session = Depends(get_db)):
    new_session = ChatSession(user_id=payload.user_id, title=payload.title)
    db.add(new_session)
    db.commit()
    db.refresh(new_session)
    return {"status": "success", "session_id": new_session.id, "title": new_session.title}

@app.get("/api/v1/sessions/{user_id}")
def get_user_sessions(user_id: int, db: Session = Depends(get_db)):
    sessions = db.query(ChatSession).filter(ChatSession.user_id == user_id).order_by(ChatSession.timestamp.desc()).all()
    return [{"session_id": s.id, "title": s.title, "timestamp": s.timestamp} for s in sessions]

@app.get("/api/v1/sessions/{session_id}/messages")
def get_session_messages(session_id: int, db: Session = Depends(get_db)):
    records = db.query(ChatRecord).filter(ChatRecord.session_id == session_id).order_by(ChatRecord.timestamp.asc()).all()
    history = []
    for r in records:
        history.append({"role": "user", "content": r.question})
        history.append({"role": "assistant", "content": r.answer, "level": r.student_level})
    return {"status": "success", "messages": history}

# --- Query & Persistence ---
@app.post("/api/v1/query", response_model=QueryResponse)
def ask_heritage_tutor(payload: StudentQueryRequest, db: Session = Depends(get_db)):
    if not payload.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")
        
    try:
        history_list = [{"role": msg.role, "content": msg.content} for msg in payload.chat_history]
        response = query_tutor(payload.question, payload.student_level, history_list)
        
        chat_entry = ChatRecord(
            session_id=payload.session_id,
            question=payload.question,
            answer=response["answer"],
            student_level=payload.student_level
        )
        db.add(chat_entry)
        db.commit()
        
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v1/admin/upload-syllabus")
async def upload_and_index_syllabus(file: UploadFile = File(...), user_id: int = Form(...), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user or user.role != "admin":
        raise HTTPException(status_code=403, detail="Unauthorized.")
    
    knowledgebase_dir = os.path.join(BASE_DIR, "knowledgebase")
    os.makedirs(knowledgebase_dir, exist_ok=True)
    file_path = os.path.join(knowledgebase_dir, file.filename)
    
    contents = await file.read()
    with open(file_path, "wb") as f:
        f.write(contents)
        
    result = ingest_curriculum_document(file_path)
    return {"status": "success", "message": f"Indexed {file.filename}!", "chunks_indexed": result["chunks_indexed"]}

@app.get("/health")
def health_check():
    return {"status": "healthy", "service": "Interactive RAG Tutor Active"}