# Funda AI — Solution Documentation & Architecture

## 🏛️ System Architecture Overview

Funda AI is structured as a modern full-stack monorepo separating the AI/RAG data pipeline from the interactive web client.

```text
funda-ai-backend/
├── backend/
│   ├── knowledgebase/          # Official Ministry PDF syllabi & study notes
│   ├── chroma_db/              # Local persistent vector store
│   ├── database.py             # SQLAlchemy SQLite ORM models (Users, Sessions, Chats, Versions)
│   ├── main.py                 # FastAPI application routes (Auth, Queries, Sessions, Admin Uploads)
│   └── rag_engine.py           # LangChain RAG pipeline, Gemini embeddings, and Socratic tutor logic
├── frontend/
│   ├── src/
│   │   ├── App.jsx             # React client (Auth portal, Sidebar sessions, Chat UI, Markdown rendering)
│   │   └── index.css           # Tailwind CSS styling
│   ├── package.json            # Frontend dependencies
│   └── tailwind.config.js      # Tailwind & Typography plugin configuration
├── start_local.sh              # Automated build & startup script
└── stop_local.sh               # Service teardown script
🧠 Core Features & Functional Modules
1. Socratic Active Learning Tutor
Unlike basic QA lookup tools, Funda AI acts as an encouraging educational mentor.

Prompt Engineering: The LangChain pipeline instructs Gemini to break down historical and cultural concepts step-by-step according to the target student level (Form 1 to Form 4).

Formative Assessment: Responses conclude with check-for-understanding quiz questions or thought-provoking follow-ups to drive engagement.

2. Document Versioning & Incremental Indexing
Revision Tracking: When teachers upload new curriculum notes, the backend calculates the next version identifier (e.g., _v1, _v2), stores the file in the knowledgebase/, and logs metadata in SQLite via SQLAlchemy.

Vector Store Sync: Newly uploaded document versions are chunked and incrementally appended into the persistent ChromaDB store (vectorstore.add_documents()) without overwriting historical data.

3. Persistent SQLite Authentication & Chat Sessions
Role-Based Access Control (RBAC): Supports distinct workflows for authenticated Students and Admins (Teachers/Head Teachers).

Session Management: Students can create, switch between, and review multiple distinct lesson sessions saved in the SQLite database.

4. Enterprise Safety & Grounding Guardrails
Anti-Hallucination Constraints: The system relies strictly on retrieved vector chunks (k=3). If a topic is outside the indexed syllabus, the model explicitly declares it out-of-bounds.

Transparency: Every AI response includes a collapsible Curriculum Grounding Sources drawer displaying the exact PDF chunks used to generate the answer.

📦 Dependencies & Technology Stack
Backend Dependencies (Python 3.12+)
fastapi: High-performance asynchronous API framework.

uvicorn: ASGI server implementation.

sqlalchemy: Object-Relational Mapper (ORM) for SQLite database management.

langchain / langchain-community: Framework for document loading and text splitting.

langchain-google-genai: Google GenAI integration for LangChain.

google-genai: Official Google generative AI SDK.

langchain-chroma: Local vector database connector.

pypdf: Robust PDF parsing utility.

python-multipart: Form data and file upload parser for FastAPI.

python-dotenv: Secure environment variable management.

Frontend Dependencies (Node.js / React)
react & react-dom: Frontend component library.

vite: Lightning-fast build tool and development server.

tailwindcss & @tailwindcss/typography: Utility-first CSS framework and Markdown prose styling.

lucide-react: Clean modern UI icon pack.

react-markdown: Secure Markdown renderer for structured AI output.

axios: Promise-based HTTP client for API communication.