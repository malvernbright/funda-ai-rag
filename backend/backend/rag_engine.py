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

VECTOR_STORE_PATH = "./chroma_db"
EMBEDDING_MODEL = "models/gemini-embedding-001"
LLM_MODEL = "gemini-3.6-flash"

embeddings = GoogleGenerativeAIEmbeddings(model=EMBEDDING_MODEL)
llm = ChatGoogleGenerativeAI(model=LLM_MODEL, temperature=0.3)


def ingest_curriculum_document(file_path: str):
    """Parses a syllabus PDF and indexes chunks into ChromaDB respecting Gemini rate limits."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Document not found at: {file_path}")
        
    loader = PyPDFLoader(file_path)
    docs = loader.load()

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000, 
        chunk_overlap=200
    )
    splits = text_splitter.split_documents(docs)

    # Slice to 80 chunks to stay under Gemini's 100 RPM Free Tier limit
    demo_splits = splits[:80]

    Chroma.from_documents(
        documents=demo_splits, 
        embedding=embeddings, 
        persist_directory=VECTOR_STORE_PATH
    )
    return {
        "status": "success", 
        "chunks_indexed": len(demo_splits), 
        "total_chunks_found": len(splits),
        "file_path": file_path
    }

def format_docs(docs):
    return "\n\n".join(doc.page_content for doc in docs)
    

def query_tutor(student_query: str, student_level: str = "Form 1", chat_history: list = None):
    """Queries the local Chroma vector store and generates a response with chat memory."""
    history_text = ""
    if chat_history:
        history_text = "\n".join([f"{msg['role'].capitalize()}: {msg['content']}" for msg in chat_history])

    vectorstore = Chroma(
        persist_directory=VECTOR_STORE_PATH, 
        embedding_function=embeddings
    )
    retriever = vectorstore.as_retriever(search_kwargs={"k": 3})

    prompt = ChatPromptTemplate.from_template(
        "You are an expert AI tutor for the Zimbabwe Heritage-Based Curriculum.\n"
        "Explain the topic to a {student_level} student strictly using the provided context.\n"
        "If the context does not contain the answer, state clearly that the information is outside the provided syllabus material.\n\n"
        "Previous Conversation History:\n{history}\n\n"
        "Context:\n{context}\n\n"
        "Question: {question}\n\n"
        "Format your answer with:\n"
        "1. Summary Explanation\n"
        "2. Core Key Facts\n"
        "3. Contemporary Relevance to Zimbabwe"
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