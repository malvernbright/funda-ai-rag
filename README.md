# Funda AI — Zimbabwe Heritage-Based Curriculum Interactive Tutor - System Run Guide

Funda AI is an offline-first, RAG-powered interactive tutoring platform designed for the Zimbabwe Heritage-Based Curriculum (Forms 1–4). It features Socratic active learning, multi-session chat history, document versioning, and real-time administrative syllabus management.

---

## 🚀 Quick Start (Automated Scripts)

The repository includes shell scripts to automatically check, build, and run both the backend and frontend services simultaneously.

### 1. Prerequisites
* **Python 3.12+** and **`uv`** package manager installed.
* **Node.js (v18+)** and **npm** installed.
* A valid **Google Gemini API Key**.

### 2. Configure Environment Variables
Create a `.env` file inside the `backend/` directory:
```
GOOGLE_API_KEY=your_gemini_api_key_here
```
## Run the System

## Backend

```
cd backend 
create virtualenvironment
```
* Run
```
python3 -m venv .venv
```

* Run 
```
source .venv/bin/activate
```

* Run
```
pip install --upgrade pip
```

* Run
```
pip install -r requirements.txt
```

* Run
```
uvicorn backend.main:app --reload --port 8000
```

## Frontend
cd frontend
* RUN 
```
npm install
```

* RUN
```
npm run dev
```
Frontend UI: [http://localhost:5173](http://localhost:5173)

Backend API Docs: [http://localhost:8000/docs](http://localhost:8000/docs)

🔐 Default Credentials
Admin Account:

Username: admin

Password: admin2026

Student Account: You can register any new student account directly from the frontend login portal.