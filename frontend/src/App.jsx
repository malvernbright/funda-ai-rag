import React, { useState, useRef, useEffect } from 'react';
import axios from 'axios';
import ReactMarkdown from 'react-markdown';
import { 
  BookOpen, Send, FileCheck, AlertTriangle, Share2, 
  CheckCircle2, GraduationCap, Sparkles, ChevronDown, ChevronUp, User
} from 'lucide-react';

const API_BASE_URL = 'http://127.0.0.1:8000/api/v1';

// Component for individual Chat Messages
const MessageBubble = ({ msg, isLatest }) => {
  const [showContext, setShowContext] = useState(false);
  const isUser = msg.role === 'user';

  const shareToWhatsApp = () => {
    const text = `*Funda AI Tutor Answer (${msg.level || 'Student'})*\n\n` +
      `*Q:* ${msg.originalQuestion || 'Question'}\n\n` +
      `*A:* ${msg.content}\n\n` +
      `_Verified against official Zimbabwe Heritage-Based Curriculum documents._`;
    window.open(`https://api.whatsapp.com/send?text=${encodeURIComponent(text)}`, '_blank');
  };

  if (isUser) {
    return (
      <div className="flex justify-end mb-4 animate-fade-in">
        <div className="bg-emerald-900/40 border border-emerald-800/50 rounded-2xl rounded-tr-sm p-4 max-w-[85%]">
          <div className="flex items-center gap-2 mb-2 text-emerald-400">
            <User className="w-4 h-4" />
            <span className="font-semibold text-xs">You</span>
          </div>
          <p className="text-sm text-emerald-50">{msg.content}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex justify-start mb-6 animate-fade-in w-full">
      <div className="bg-slate-900 border border-slate-800 rounded-2xl rounded-tl-sm p-5 w-full shadow-lg">
        <div className="flex items-center justify-between border-b border-slate-800 pb-3 mb-4">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-400" />
            <span className="font-semibold text-slate-200">AI Tutor Response</span>
            {msg.level && (
              <span className="text-xs bg-slate-800 text-slate-400 px-2 py-0.5 rounded border border-slate-700">
                {msg.level}
              </span>
            )}
          </div>
          <button 
            onClick={shareToWhatsApp}
            className="bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 px-2 py-1 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition"
          >
            <Share2 className="w-3 h-3" /> Share
          </button>
        </div>

        <div className="text-slate-300 text-sm leading-relaxed font-sans mb-4">
          <ReactMarkdown className="prose prose-invert prose-emerald prose-sm max-w-none">
            {msg.content}
          </ReactMarkdown>
        </div>

        {msg.context && msg.context.length > 0 && (
          <div className="border border-slate-800 rounded-xl overflow-hidden bg-slate-950/50 mb-4">
            <button 
              onClick={() => setShowContext(!showContext)}
              className="w-full px-4 py-3 text-xs font-semibold text-slate-400 hover:text-slate-200 flex items-center justify-between border-b border-slate-800/50 transition"
            >
              <span className="flex items-center gap-2">
                <BookOpen className="w-4 h-4 text-emerald-400" />
                Retrieved Context Grounding ({msg.context.length} Chunks)
              </span>
              {showContext ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
            </button>
            {showContext && (
              <div className="p-4 flex flex-col gap-3 bg-slate-950">
                {msg.context.map((chunk, idx) => (
                  <div key={idx} className="p-3 bg-slate-900 border border-slate-800 rounded-lg text-xs text-slate-400 font-mono leading-relaxed">
                    <span className="text-emerald-500 font-semibold mb-1 block">Chunk {idx + 1}</span>
                    {chunk}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        <div className="bg-amber-950/20 border border-amber-800/40 rounded-xl p-3 flex items-start gap-3 text-xs text-amber-300/80 mt-2">
          <AlertTriangle className="w-4 h-4 text-amber-400 flex-shrink-0" />
          <span>{msg.safeguard}</span>
        </div>
      </div>
    </div>
  );
};

export default function App() {
  const [messages, setMessages] = useState([]);
  const [question, setQuestion] = useState('');
  const [studentLevel, setStudentLevel] = useState('Form 1');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  
  const [filePath, setFilePath] = useState('knowledgebase/Heritage-notes-form-1-4-2.pdf');
  const [ingestStatus, setIngestStatus] = useState(null);
  const [ingesting, setIngesting] = useState(false);

  const messagesEndRef = useRef(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, loading]);

  const handleQuery = async (e) => {
    e.preventDefault();
    if (!question.trim()) return;

    const userQuestion = question;
    const newHistory = [...messages, { role: 'user', content: userQuestion }];
    
    setMessages(newHistory);
    setQuestion('');
    setLoading(true);
    setError(null);

    try {
      const res = await axios.post(`${API_BASE_URL}/query`, {
        question: userQuestion,
        student_level: studentLevel,
        chat_history: messages.map(m => ({ role: m.role, content: m.content }))
      });
      
      setMessages([...newHistory, { 
        role: 'assistant', 
        content: res.data.answer, 
        context: res.data.context_used,
        safeguard: res.data.safeguard_notice,
        level: res.data.student_level,
        originalQuestion: userQuestion
      }]);
    } catch (err) {
      if (err.response?.status === 503) {
        setError('Gemini API is experiencing high demand. Please wait a few seconds and try again.');
      } else {
        setError(err.response?.data?.detail || 'Failed to fetch response from backend.');
      }
      setMessages(newHistory.slice(0, -1)); // Remove the user message if it failed completely
      setQuestion(userQuestion); // Put it back in the input box
    } finally {
      setLoading(false);
    }
  };

  const handleIngest = async () => {
    if (!filePath.trim()) return;
    setIngesting(true);
    setIngestStatus(null);
    try {
      const res = await axios.post(`${API_BASE_URL}/ingest`, { file_path: filePath });
      setIngestStatus(`Successfully indexed ${res.data.chunks_indexed} chunks!`);
    } catch (err) {
      setIngestStatus(`Ingestion failed: ${err.response?.data?.detail || err.message}`);
    } finally {
      setIngesting(false);
    }
  };

  return (
    <div className="h-screen bg-slate-950 text-slate-100 flex flex-col font-sans overflow-hidden">
      <header className="border-b border-slate-800 bg-slate-900/50 backdrop-blur px-6 py-4 flex items-center justify-between z-10 shrink-0">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-emerald-500/10 text-emerald-400 rounded-lg border border-emerald-500/20">
            <GraduationCap className="w-6 h-6" />
          </div>
          <div>
            <h1 className="font-bold text-xl tracking-tight text-white flex items-center gap-2">
              Funda AI <span className="text-xs font-semibold px-2 py-0.5 bg-emerald-500/20 text-emerald-400 rounded border border-emerald-500/30">Gemini RAG</span>
            </h1>
            <p className="text-xs text-slate-400">Zimbabwe Heritage-Based Curriculum Assistant</p>
          </div>
        </div>

        <div className="flex items-center gap-2 bg-slate-900 border border-slate-800 p-1.5 rounded-xl">
          <BookOpen className="w-4 h-4 text-slate-400 ml-2" />
          <input 
            type="text" 
            value={filePath}
            onChange={(e) => setFilePath(e.target.value)}
            placeholder="Syllabus PDF Path..."
            className="bg-transparent text-xs text-slate-200 focus:outline-none w-56 px-1"
          />
          <button 
            onClick={handleIngest}
            disabled={ingesting}
            className="text-xs bg-slate-800 hover:bg-slate-700 text-slate-200 px-3 py-1.5 rounded-lg border border-slate-700 transition font-medium flex items-center gap-1.5 disabled:opacity-50"
          >
            {ingesting ? <Sparkles className="w-3.5 h-3.5 animate-spin text-emerald-400" /> : <FileCheck className="w-3.5 h-3.5 text-emerald-400" />}
            {ingesting ? 'Indexing...' : 'Ingest PDF'}
          </button>
        </div>
      </header>

      {ingestStatus && (
        <div className="bg-slate-900 border-b border-slate-800 px-6 py-2 text-xs text-center text-emerald-400 font-medium shrink-0">
          {ingestStatus}
        </div>
      )}

      <main className="flex-1 overflow-y-auto p-6 flex flex-col items-center">
        <div className="w-full max-w-4xl flex flex-col">
          {messages.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-64 text-slate-500 gap-4 mt-10">
              <GraduationCap className="w-16 h-16 text-slate-800" />
              <p>Type a question below to start learning from the Heritage Curriculum.</p>
            </div>
          ) : (
            messages.map((msg, idx) => (
              <MessageBubble 
                key={idx} 
                msg={msg} 
                isLatest={idx === messages.length - 1}
              />
            ))
          )}
          
          {loading && (
            <div className="flex justify-start mb-4">
              <div className="bg-slate-900 border border-slate-800 rounded-2xl p-4 flex items-center gap-3 text-emerald-400 text-sm">
                <Sparkles className="w-4 h-4 animate-spin" />
                Thinking...
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>
      </main>

      <div className="bg-slate-900 border-t border-slate-800 p-4 shrink-0">
        <div className="max-w-4xl mx-auto flex flex-col gap-2">
          {error && (
            <div className="text-xs text-rose-400 bg-rose-950/30 px-3 py-2 rounded-lg border border-rose-900 flex items-center gap-2">
              <AlertTriangle className="w-3 h-3" /> {error}
            </div>
          )}
          <form onSubmit={handleQuery} className="flex gap-3">
            <select 
              value={studentLevel} 
              onChange={(e) => setStudentLevel(e.target.value)}
              className="bg-slate-950 border border-slate-800 text-slate-200 text-xs rounded-xl px-4 focus:outline-none focus:border-emerald-500 shrink-0"
            >
              <option value="Form 1">Form 1</option>
              <option value="Form 2">Form 2</option>
              <option value="Form 3">Form 3</option>
              <option value="Form 4">Form 4</option>
            </select>
            <input 
              type="text"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="Ask a question about Heritage Studies..."
              className="flex-1 bg-slate-950 border border-slate-800 rounded-xl px-4 py-3 text-sm text-slate-100 placeholder-slate-600 focus:outline-none focus:border-emerald-500 transition"
            />
            <button 
              type="submit"
              disabled={loading || !question.trim()}
              className="bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white px-6 py-3 rounded-xl font-medium transition flex items-center gap-2 text-sm shadow-lg shadow-emerald-900/20 shrink-0"
            >
              <Send className="w-4 h-4" />
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}