import os
import warnings
from dotenv import load_dotenv
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
from langchain_google_genai import GoogleGenerativeAIEmbeddings, ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser

warnings.filterwarnings("ignore", category=DeprecationWarning, module="langchain_community")

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VECTOR_STORE_PATH = os.path.join(os.path.dirname(BASE_DIR), "chroma_db")
DEFAULT_SYLLABUS_PATH = os.path.join(BASE_DIR, "knowledgebase", "Heritage-notes-form-1-4-2.pdf")

EMBEDDING_MODEL = "models/gemini-embedding-001"
LLM_MODEL = "gemini-flash-latest"

embeddings = GoogleGenerativeAIEmbeddings(model=EMBEDDING_MODEL)
llm = ChatGoogleGenerativeAI(model=LLM_MODEL, temperature=0.3)

def initialize_knowledgebase():
    if not os.path.exists(DEFAULT_SYLLABUS_PATH):
        print(f"⚠️ Warning: Default syllabus not found at {DEFAULT_SYLLABUS_PATH}")
        return

    if os.path.exists(VECTOR_STORE_PATH) and os.listdir(VECTOR_STORE_PATH):
        print("✅ Knowledgebase vector store already initialized.")
        return
        
    print(f"📚 Auto-indexing default curriculum document: {DEFAULT_SYLLABUS_PATH}")
    try:
        ingest_curriculum_document(DEFAULT_SYLLABUS_PATH)
        print("✅ Auto-indexing complete!")
    except Exception as e:
        print(f"❌ Failed to auto-index: {e}")

def ingest_curriculum_document(file_path: str):
    loader = PyPDFLoader(file_path)
    docs = loader.load()

    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    splits = text_splitter.split_documents(docs)
    demo_splits = splits[:80] # Stay within free tier rate limit

    # Add metadata for version tracking
    for doc in demo_splits:
        doc.metadata["source_file"] = os.path.basename(file_path)

    if os.path.exists(VECTOR_STORE_PATH) and os.listdir(VECTOR_STORE_PATH):
        # Append new version documents to existing vector store
        vectorstore = Chroma(persist_directory=VECTOR_STORE_PATH, embedding_function=embeddings)
        vectorstore.add_documents(demo_splits)
    else:
        # Create new vector store
        Chroma.from_documents(
            documents=demo_splits, 
            embedding=embeddings, 
            persist_directory=VECTOR_STORE_PATH
        )
        
    return {"status": "success", "chunks_indexed": len(demo_splits)}

def format_docs(docs):
    return "\n\n".join(doc.page_content for doc in docs)
    
def query_tutor(student_query: str, student_level: str = "Form 1", chat_history: list = None):
    history_text = ""
    if chat_history:
        history_text = "\n".join([f"{msg['role'].capitalize()}: {msg['content']}" for msg in chat_history])

    try:
        vectorstore = Chroma(persist_directory=VECTOR_STORE_PATH, embedding_function=embeddings)
        retriever = vectorstore.as_retriever(search_kwargs={"k": 3})

        prompt = ChatPromptTemplate.from_template(
            "You are an expert, encouraging AI tutor for the Zimbabwe Heritage-Based Curriculum.\n"
            "Your goal is to TEACH the student ({student_level}), not just give static answers. Explain concepts clearly, break them down step-by-step, and conclude with a quick check-for-understanding question or a thought-provoking follow-up quiz question.\n"
            "Strictly use the provided context. If the context does not contain the answer, state clearly that the information is outside the syllabus.\n\n"
            "Previous Conversation History:\n{history}\n\n"
            "Context:\n{context}\n\n"
            "Student Message: {question}"
        )

        rag_chain = (
            {
                "context": retriever | format_docs, 
                "question": RunnablePassthrough(), 
                "student_level": lambda _: student_level,
                "history": lambda _: history_text
            }
            | prompt
            | llm
            | StrOutputParser()
        )

        response_text = rag_chain.invoke(student_query)
        docs_used = retriever.invoke(student_query)
        
        return {
            "answer": response_text,
            "context_used": [doc.page_content for doc in docs_used],
            "student_level": student_level,
            "safeguard_notice": "AI-generated response based on indexed curriculum documents. Verify critical historical facts against official textbooks."
        }
    except Exception as e:
        print(f"❌ RAG Execution Error: {str(e)}")
        raise e