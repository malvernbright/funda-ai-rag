import os
import warnings
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_chroma import Chroma
from langchain_ollama import OllamaEmbeddings, ChatOllama
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser

# Suppress the community sunset warning
warnings.filterwarnings("ignore", category=DeprecationWarning, module="langchain_community")

# 1. Configuration (Local strictly)
VECTOR_STORE_PATH = "./chroma_db"
EMBEDDING_MODEL = "nomic-embed-text"
# LLM_MODEL = "llama3.1:latest"
LLM_MODEL = "stablelm-zephyr:latest"

embeddings = OllamaEmbeddings(model=EMBEDDING_MODEL)
llm = ChatOllama(model=LLM_MODEL, temperature=0.2)

def ingest_curriculum_document(file_path: str):
    """Parses a PDF, chunks it, and saves to the local Chroma vector store."""
    print(f"Loading {file_path}...")
    loader = PyPDFLoader(file_path)
    docs = loader.load()

    # Split the document into manageable chunks for the vector store
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000, 
        chunk_overlap=200
    )
    splits = text_splitter.split_documents(docs)

    print(f"Indexing {len(splits)} chunks into ChromaDB...")
    vectorstore = Chroma.from_documents(
        documents=splits, 
        embedding=embeddings, 
        persist_directory=VECTOR_STORE_PATH
    )
    return {"status": "success", "chunks_indexed": len(splits)}

def format_docs(docs):
    return "\n\n".join(doc.page_content for doc in docs)

def query_tutor(student_query: str):
    """Retrieves relevant curriculum context and generates a response using LCEL."""
    # Load existing vector store
    vectorstore = Chroma(
        persist_directory=VECTOR_STORE_PATH, 
        embedding_function=embeddings
    )
    # Retrieve top 3 most relevant chunks
    retriever = vectorstore.as_retriever(search_kwargs={"k": 3})

    # Strict prompt to prevent hallucinations outside the curriculum
    prompt = ChatPromptTemplate.from_template(
        "You are an AI tutor for the Zimbabwe Heritage-Based Curriculum. "
        "Answer the student's question strictly using the provided context. "
        "If the context does not contain the answer, say you don't know.\n\n"
        "Context: {context}\n\n"
        "Question: {question}"
    )

    # Modern LangChain Expression Language (LCEL) architecture
    rag_chain = (
        {"context": retriever | format_docs, "question": RunnablePassthrough()}
        | prompt
        | llm
        | StrOutputParser()
    )

    # Execute the chain
    response_text = rag_chain.invoke(student_query)
    
    # Retrieve the exact documents used for the dashboard
    docs_used = retriever.invoke(student_query)
    
    return {
        "answer": response_text,
        "context_used": [doc.page_content for doc in docs_used]
    }

# --- Hackathon Testing ---
# Run this once to populate chroma_db, then comment it out on subsequent runs
# ingest_curriculum_document("knowledgebase/Heritage-notes-form-1-4-2.pdf")

# # 2. Test the retrieval:
# result = query_tutor("What is the significance of the Great Zimbabwe ruins?")
# print(result["answer"])