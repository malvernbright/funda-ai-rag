import os
from sqlalchemy import create_engine, Column, Integer, String, Text, ForeignKey, DateTime, inspect, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
import datetime
import hashlib

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "funda_ai.db")
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, default="student")
    sessions = relationship("ChatSession", back_populates="user", cascade="all, delete-orphan")
    documents = relationship("DocumentVersion", back_populates="uploader")

class ChatSession(Base):
    __tablename__ = "chat_sessions"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    title = Column(String, default="New Tutoring Session")
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    user = relationship("User", back_populates="sessions")
    chats = relationship("ChatRecord", back_populates="session", cascade="all, delete-orphan")

class ChatRecord(Base):
    __tablename__ = "chats"
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("chat_sessions.id"))
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    student_level = Column(String, default="Form 1")
    image_paths = Column(Text, nullable=True)   # JSON list of saved image files attached to the question
    model_used = Column(String, nullable=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    session = relationship("ChatSession", back_populates="chats")

class DocumentVersion(Base):
    __tablename__ = "document_versions"
    id = Column(Integer, primary_key=True, index=True)
    original_filename = Column(String, nullable=False)
    version = Column(Integer, nullable=False, default=1)
    stored_filename = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    uploaded_by = Column(Integer, ForeignKey("users.id"))
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)
    uploader = relationship("User", back_populates="documents")

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def _add_missing_columns():
    """create_all() never alters existing tables, so add the new chat columns to an existing funda_ai.db."""
    existing = {c["name"] for c in inspect(engine).get_columns("chats")}
    with engine.begin() as conn:
        if "image_paths" not in existing:
            conn.execute(text("ALTER TABLE chats ADD COLUMN image_paths TEXT"))
        if "model_used" not in existing:
            conn.execute(text("ALTER TABLE chats ADD COLUMN model_used VARCHAR"))


def init_db():
    Base.metadata.create_all(bind=engine)
    _add_missing_columns()
    db = SessionLocal()
    admin_user = db.query(User).filter(User.username == "admin").first()
    if not admin_user:
        admin = User(username="admin", password_hash=hash_password("admin2026"), role="admin")
        db.add(admin)
        db.commit()
    db.close()