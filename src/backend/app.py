import streamlit as st
import os
from datetime import datetime
from backend.database import SessionLocal, init_db, User, ChatSession, ChatRecord, DocumentVersion, hash_password
from backend.rag_engine import (
    query_tutor, ingest_curriculum_document, index_knowledgebase,
    KNOWLEDGEBASE_DIR, LEVELS, LANGUAGES, SUBJECT_LABELS,
    list_subjects, list_all_subject_dirs, subject_label,
    start_background_indexing, indexing_status
)

# Initialize SQLite database and ChromaDB knowledgebase on startup
init_db()
start_background_indexing()  # indexes new/unfinished PDFs in the background, once per server process

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

    OTHER = "➕ New subject..."
    c1, c2 = st.columns(2)
    with c1:
        admin_level = st.selectbox("Education Level", list(LEVELS.keys()), key="admin_level")
    with c2:
        admin_subject = st.selectbox(
            "Subject",
            list_all_subject_dirs() + [OTHER],
            format_func=lambda d: d if d == OTHER else subject_label(d),
            key="admin_subject"
        )
    if admin_subject == OTHER:
        custom = st.text_input("New subject folder name (e.g. history, accounts)")
        admin_subject = "".join(ch for ch in custom.strip().lower().replace(" ", "_") if ch.isalnum() or ch == "_")

    uploaded_file = st.file_uploader("Select PDF Curriculum Document", type=["pdf"])
    if uploaded_file and not admin_subject:
        st.warning("Enter a subject folder name before uploading.")
    if uploaded_file and admin_subject and st.button("Upload & Index Document Version", type="primary"):
        knowledgebase_dir = os.path.join(KNOWLEDGEBASE_DIR, LEVELS[admin_level], admin_subject)
        os.makedirs(knowledgebase_dir, exist_ok=True)

        # Determine next version number for this file
        latest_version = db.query(DocumentVersion).filter(
            DocumentVersion.original_filename == uploaded_file.name,
            DocumentVersion.file_path.like(f"{knowledgebase_dir}%")
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

    st.divider()
    st.subheader("Bulk indexing")
    st.caption("Indexes every PDF placed manually under knowledgebase/<level>/<subject>/ that isn't indexed yet.")
    status = indexing_status()
    if status["running"]:
        st.info(f"📚 Background indexing in progress: {status['done']}/{status['total']} files"
                + (f" (now: {status['current']})" if status["current"] else "") + ". Refresh the page to update.")
    for item in status["failed"]:
        st.error(item)
    if st.button("🔄 Index all new documents"):
        with st.spinner("Indexing... large books can take several minutes on the free API tier."):
            summary = index_knowledgebase()
        if summary.get("busy"):
            st.info("Indexing is already running in the background.")
        else:
            st.success(
                f"Indexed {len(summary['indexed'])} new file(s); {len(summary['skipped'])} already indexed.")
            for item in summary["indexed"]:
                st.write(f"✅ {item}")
            for item in summary["failed"]:
                st.error(item)

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

    index_status = indexing_status()
    if index_status["running"]:
        st.info(f"📚 Library is still being indexed ({index_status['done']}/{index_status['total']} files). "
                "Some subjects may not have answers yet.")

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

col_head1, col_head2, col_head3, col_head4 = st.columns([3, 1, 1.5, 1.3])
with col_head1:
    session_title = current_session.title if current_session else "Interactive Session"
    st.markdown(f"#### 🤖 {session_title} — Socratic Active Learning")
with col_head2:
    student_level = st.selectbox(
        "Form Level",
        list(LEVELS.keys()),
        label_visibility="collapsed"
    )
with col_head3:
    subject_labels = {"": "All subjects", **dict(list_subjects(student_level))}
    selected_subject = st.selectbox(
        "Subject",
        list(subject_labels.keys()),
        format_func=lambda k: subject_labels[k],
        label_visibility="collapsed"
    )
with col_head4:
    selected_language = st.selectbox(
        "Language",
        list(LANGUAGES.keys()),
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
                    response = query_tutor(
                        prompt, student_level, chat_history,
                        subject=selected_subject or None,
                        language=selected_language
                    )
                    st.markdown(response["answer"])
                    st.caption(f"Answered by {response['model_used']} · {selected_language}")

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
