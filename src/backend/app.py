import streamlit as st
import os
from datetime import datetime
from backend.database import SessionLocal, init_db, User, ChatSession, ChatRecord, DocumentVersion, hash_password
from backend.rag_engine import query_tutor, ingest_curriculum_document, BASE_DIR

# Initialize SQLite database and ChromaDB knowledgebase on startup
init_db()

st.set_page_config(
    page_title="Funda AI Tutor",
    page_icon="🎓",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Dark Theme Styling
st.markdown("""
    <style>
        .stApp { background-color: #0e1117; color: #e6e6e6; }
        section[data-testid="stSidebar"] { background-color: #161b22; }
        .portal-title { text-align: center; font-size: 2rem; font-weight: 700; margin-bottom: 0; }
        .portal-subtitle { text-align: center; opacity: 0.7; margin-bottom: 1.5rem; }
        .hint-text { text-align: center; font-size: 0.8rem; opacity: 0.5; margin-top: 1.5rem; }
    </style>
""", unsafe_allow_html=True)

# Session State Initialization
if "user" not in st.session_state:
    st.session_state.user = None
if "current_session_id" not in st.session_state:
    st.session_state.current_session_id = None

db = SessionLocal()

# ==========================================
# 1. AUTHENTICATION PORTAL (Sign In / Register)
# ==========================================
if not st.session_state.user:
    col1, col2, col3 = st.columns([1, 1.5, 1])
    with col2:
        st.markdown("<div class='portal-title'>🎓 Funda AI Portal</div>", unsafe_allow_html=True)
        st.markdown("<div class='portal-subtitle'>Zimbabwe Heritage-Based Curriculum Assistant</div>", unsafe_allow_html=True)

        tab1, tab2 = st.tabs(["Sign In", "Register"])

        with tab1:
            with st.form("login_form"):
                username = st.text_input("Username")
                password = st.text_input("Password", type="password")
                submit = st.form_submit_button("Sign In", use_container_width=True)
                if submit:
                    user_record = db.query(User).filter(User.username == username).first()
                    if user_record and user_record.password_hash == hash_password(password):
                        st.session_state.user = {
                            "id": user_record.id,
                            "username": user_record.username,
                            "role": user_record.role
                        }
                        db.close()
                        st.rerun()
                    else:
                        st.error("Invalid username or password.")

        with tab2:
            with st.form("register_form"):
                new_user = st.text_input("Choose Username")
                new_pass = st.text_input("Choose Password", type="password")
                reg_submit = st.form_submit_button("Create Account", use_container_width=True)
                if reg_submit:
                    existing = db.query(User).filter(User.username == new_user).first()
                    if existing:
                        st.error("Username already exists.")
                    elif new_user and new_pass:
                        user_record = User(
                            username=new_user,
                            password_hash=hash_password(new_pass),
                            role="student"
                        )
                        db.add(user_record)
                        db.commit()
                        st.success("Account created successfully! Please switch to Sign In.")
                    else:
                        st.error("Please fill in all fields.")

        st.markdown(
            "<div class='hint-text'>Default Admin: admin / admin2026</div>",
            unsafe_allow_html=True
        )

    db.close()
    st.stop()

user = st.session_state.user

# ==========================================
# 2. ADMIN DASHBOARD (Curriculum Upload & Versioning)
# ==========================================
if user["role"] == "admin":
    st.sidebar.title("🛡️ Admin Portal")
    st.sidebar.write(f"Logged in as: {user['username']}")
    if st.sidebar.button("🚪 Logout", use_container_width=True):
        st.session_state.user = None
        st.session_state.current_session_id = None
        db.close()
        st.rerun()

    st.title("📚 Curriculum Document Management & Versioning")
    st.write("Upload updated official Ministry syllabi or study notes. The system automatically version-tracks and indexes chunks into ChromaDB.")

    uploaded_file = st.file_uploader("Select PDF Curriculum Document", type=["pdf"])
    if uploaded_file and st.button("Upload & Index Document Version", type="primary"):
        knowledgebase_dir = os.path.join(BASE_DIR, "knowledgebase")
        os.makedirs(knowledgebase_dir, exist_ok=True)

        # Determine next version number for this file
        latest_version = db.query(DocumentVersion).filter(
            DocumentVersion.original_filename == uploaded_file.name
        ).order_by(DocumentVersion.version.desc()).first()
        next_version = (latest_version.version + 1) if latest_version else 1

        base_name, ext = os.path.splitext(uploaded_file.name)
        stored_filename = f"{base_name}_v{next_version}{ext}"
        file_path = os.path.join(knowledgebase_dir, stored_filename)

        with open(file_path, "wb") as f:
            f.write(uploaded_file.getbuffer())

        doc_version = DocumentVersion(
            original_filename=uploaded_file.name,
            version=next_version,
            stored_filename=stored_filename,
            file_path=file_path,
            uploaded_by=user["id"]
        )
        db.add(doc_version)
        db.commit()

        with st.spinner("Processing and vectorizing document chunks..."):
            try:
                result = ingest_curriculum_document(file_path)
                st.success(
                    f"Successfully uploaded {uploaded_file.name} as Version {next_version} "
                    f"and indexed {result['chunks_indexed']} chunks!"
                )
            except Exception as e:
                st.error(f"Document was saved but indexing failed: {e}")

    db.close()
    st.stop()

# ==========================================
# 3. STUDENT SIDEBAR & LESSON SESSIONS
# ==========================================
with st.sidebar:
    st.markdown("### 🎓 Funda AI Tutor")
    st.markdown(f"Student: **{user['username']}**")

    if st.button("➕ New Lesson Session", use_container_width=True):
        new_sess = ChatSession(
            user_id=user["id"],
            title=f"Lesson {datetime.now().strftime('%b %d, %H:%M')}"
        )
        db.add(new_sess)
        db.commit()
        db.refresh(new_sess)
        st.session_state.current_session_id = new_sess.id
        db.close()
        st.rerun()

    st.markdown("---")
    st.markdown("##### 📁 Your Lesson History")

    sessions = db.query(ChatSession).filter(
        ChatSession.user_id == user["id"]
    ).order_by(ChatSession.timestamp.desc()).all()

    # Drop a stale session id that doesn't belong to this user
    if st.session_state.current_session_id and not any(
        s.id == st.session_state.current_session_id for s in sessions
    ):
        st.session_state.current_session_id = None

    if not sessions:
        default_sess = ChatSession(user_id=user["id"], title="First Lesson")
        db.add(default_sess)
        db.commit()
        db.refresh(default_sess)
        st.session_state.current_session_id = default_sess.id
        sessions = [default_sess]
    elif not st.session_state.current_session_id:
        st.session_state.current_session_id = sessions[0].id

    for s in sessions:
        btn_type = "primary" if st.session_state.current_session_id == s.id else "secondary"
        if st.button(s.title, key=f"sess_{s.id}", use_container_width=True, type=btn_type):
            st.session_state.current_session_id = s.id
            db.close()
            st.rerun()

    st.markdown("---")
    if st.button("🚪 Logout", use_container_width=True):
        st.session_state.user = None
        st.session_state.current_session_id = None
        db.close()
        st.rerun()

# ==========================================
# 4. MAIN SOCRATIC TUTOR CHAT INTERFACE
# ==========================================
current_session = db.query(ChatSession).filter(
    ChatSession.id == st.session_state.current_session_id,
    ChatSession.user_id == user["id"]
).first()

col_head1, col_head2 = st.columns([3, 1])
with col_head1:
    session_title = current_session.title if current_session else "Interactive Session"
    st.markdown(f"#### 🤖 {session_title} — Socratic Active Learning")
with col_head2:
    student_level = st.selectbox(
        "Form Level",
        ["Form 1", "Form 2", "Form 3", "Form 4"],
        label_visibility="collapsed"
    )

# Render chat history for current session
if current_session:
    records = db.query(ChatRecord).filter(
        ChatRecord.session_id == current_session.id
    ).order_by(ChatRecord.timestamp.asc()).all()

    if not records:
        st.info("👋 Welcome to your interactive lesson! Ask a question or request a quiz on any topic from the Zimbabwe Heritage Curriculum.")

    for r in records:
        with st.chat_message("user"):
            st.write(r.question)
        with st.chat_message("assistant"):
            st.markdown(r.answer)

    # Handle incoming user query
    if prompt := st.chat_input("Ask your tutor a question or request a quiz..."):
        with st.chat_message("user"):
            st.write(prompt)

        # Previous messages in this session for the context window
        chat_history = []
        for r in records:
            chat_history.append({"role": "user", "content": r.question})
            chat_history.append({"role": "assistant", "content": r.answer})

        with st.chat_message("assistant"):
            with st.spinner("Tutor is formulating guidance & practice questions..."):
                try:
                    response = query_tutor(prompt, student_level, chat_history)
                    st.markdown(response["answer"])

                    # Persist to database
                    chat_entry = ChatRecord(
                        session_id=current_session.id,
                        question=prompt,
                        answer=response["answer"],
                        student_level=student_level
                    )
                    db.add(chat_entry)
                    db.commit()
                except Exception as e:
                    db.rollback()
                    st.error(f"Error generating response: {e}")

db.close()