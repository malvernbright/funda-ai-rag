import React, { useState, useRef, useEffect } from 'react';
import axios from 'axios';
import ReactMarkdown from 'react-markdown';
import { 
  BookOpen, Send, AlertTriangle, Share2, 
  CheckCircle2, GraduationCap, Sparkles, ChevronDown, ChevronUp, User, 
  ShieldCheck, LogOut, Upload, FileUp, Lock, UserPlus, Plus, MessageSquare
} from 'lucide-react';

const API_BASE_URL = 'http://127.0.0.1:8000/api/v1';

const MessageBubble = ({ msg }) => {
  const [showContext, setShowContext] = useState(false);
  const isUser = msg.role === 'user';

  const shareToWhatsApp = () => {
    const text = `*Funda AI Interactive Tutor (${msg.level || 'Student'})*\n\n` +
      `*A:* ${msg.content}\n\n` +
      `_Verified against official Zimbabwe Curriculum._`;
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
            <span className="font-semibold text-slate-200">Interactive Tutor Response</span>
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
          <div className="prose prose-invert prose-emerald prose-sm max-w-none">
            <ReactMarkdown>{msg.content}</ReactMarkdown>
          </div>
        </div>

        {msg.context && msg.context.length > 0 && (
          <div className="border border-slate-800 rounded-xl overflow-hidden bg-slate-950/50 mb-4">
            <button 
              onClick={() => setShowContext(!showContext)}
              className="w-full px-4 py-3 text-xs font-semibold text-slate-400 hover:text-slate-200 flex items-center justify-between border-b border-slate-800/50 transition"
            >
              <span className="flex items-center gap-2">
                <BookOpen className="w-4 h-4 text-emerald-400" />
                Curriculum Grounding Sources ({msg.context.length} Chunks)
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
          <span>{msg.safeguard || "AI-generated tutoring response based on official curriculum standards."}</span>
        </div>
      </div>
    </div>
  );
};

export default function App() {
  const [currentUser, setCurrentUser] = useState(null);
  const [authMode, setAuthMode] = useState('login');
  const [usernameInput, setUsernameInput] = useState('');
  const [passwordInput, setPasswordInput] = useState('');
  const [authError, setAuthError] = useState('');

  // Sessions & Chat State
  const [sessions, setSessions] = useState([]);
  const [currentSessionId, setCurrentSessionId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [question, setQuestion] = useState('');
  const [studentLevel, setStudentLevel] = useState('Form 1');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const messagesEndRef = useRef(null);

  // Admin State
  const [selectedFile, setSelectedFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [uploadMessage, setUploadMessage] = useState(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    if (currentUser?.role === 'student') scrollToBottom();
  }, [messages, loading, currentUser]);

  useEffect(() => {
    if (currentUser && currentUser.role === 'student') {
      fetchSessions();
    }
  }, [currentUser]);

  const fetchSessions = async () => {
    try {
      const res = await axios.get(`${API_BASE_URL}/sessions/${currentUser.user_id}`);
      setSessions(res.data);
      if (res.data.length > 0 && !currentSessionId) {
        selectSession(res.data[0].session_id);
      } else if (res.data.length === 0) {
        createNewSession('First Lesson');
      }
    } catch (err) {
      console.error("Failed to load sessions", err);
    }
  };

  const selectSession = async (sessionId) => {
    setCurrentSessionId(sessionId);
    try {
      const res = await axios.get(`${API_BASE_URL}/sessions/${sessionId}/messages`);
      setMessages(res.data.messages);
    } catch (err) {
      console.error("Failed to load messages", err);
    }
  };

  const createNewSession = async (title = "New Lesson") => {
    try {
      const res = await axios.post(`${API_BASE_URL}/sessions`, {
        user_id: currentUser.user_id,
        title: title
      });
      const newSession = { session_id: res.data.session_id, title: res.data.title };
      setSessions(prev => [newSession, ...prev]);
      setCurrentSessionId(res.data.session_id);
      setMessages([]);
    } catch (err) {
      console.error("Failed to create session", err);
    }
  };

  const handleAuthSubmit = async (e) => {
    e.preventDefault();
    setAuthError('');
    const endpoint = authMode === 'login' ? '/auth/login' : '/auth/register';

    try {
      const res = await axios.post(`${API_BASE_URL}${endpoint}`, {
        username: usernameInput,
        password: passwordInput
      });
      setCurrentUser({ user_id: res.data.user_id, username: res.data.username, role: res.data.role });
      setUsernameInput('');
      setPasswordInput('');
    } catch (err) {
      setAuthError(err.response?.data?.detail || 'Authentication failed.');
    }
  };

  const handleQuery = async (e) => {
    e.preventDefault();
    if (!question.trim() || !currentSessionId) return;

    const userQuestion = question;
    const newHistory = [...messages, { role: 'user', content: userQuestion }];
    
    setMessages(newHistory);
    setQuestion('');
    setLoading(true);
    setError(null);

    try {
      const res = await axios.post(`${API_BASE_URL}/query`, {
        user_id: currentUser.user_id,
        session_id: currentSessionId,
        question: userQuestion,
        student_level: studentLevel,
        chat_history: messages.map(m => ({ role: m.role, content: m.content }))
      });
      
      setMessages([...newHistory, { 
        role: 'assistant', 
        content: res.data.answer, 
        context: res.data.context_used,
        safeguard: res.data.safeguard_notice,
        level: res.data.student_level
      }]);
    } catch (err) {
      setError('Failed to fetch response from backend.');
      setMessages(newHistory.slice(0, -1));
      setQuestion(userQuestion);
    } finally {
      setLoading(false);
    }
  };

  const handleUploadSyllabus = async (e) => {
    e.preventDefault();
    if (!selectedFile) return;
    setUploading(true);
    setUploadMessage(null);

    const formData = new FormData();
    formData.append('file', selectedFile);
    formData.append('user_id', currentUser.user_id);

    try {
      const res = await axios.post(`${API_BASE_URL}/admin/upload-syllabus`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      setUploadMessage({ type: 'success', text: res.data.message });
      setSelectedFile(null);
    } catch (err) {
      setUploadMessage({ type: 'error', text: 'Upload failed.' });
    } finally {
      setUploading(false);
    }
  };

  if (!currentUser) {
    return (
      <div className="min-h-screen bg-slate-950 text-slate-100 flex items-center justify-center p-6 font-sans">
        <div className="max-w-md w-full bg-slate-900 border border-slate-800 rounded-2xl p-8 shadow-2xl flex flex-col gap-6">
          <div className="flex flex-col items-center text-center gap-2">
            <div className="p-3 bg-emerald-500/10 text-emerald-400 rounded-xl border border-emerald-500/20">
              <GraduationCap className="w-8 h-8" />
            </div>
            <h1 className="text-2xl font-bold tracking-tight text-white">Funda AI Tutor Portal</h1>
            <p className="text-xs text-slate-400">Interactive Curriculum Learning Assistant</p>
          </div>

          <div className="flex bg-slate-950 p-1 rounded-xl border border-slate-800">
            <button onClick={() => setAuthMode('login')} className={`flex-1 py-2 text-xs font-semibold rounded-lg transition ${authMode === 'login' ? 'bg-emerald-600 text-white' : 'text-slate-400'}`}>Sign In</button>
            <button onClick={() => setAuthMode('register')} className={`flex-1 py-2 text-xs font-semibold rounded-lg transition ${authMode === 'register' ? 'bg-emerald-600 text-white' : 'text-slate-400'}`}>Register</button>
          </div>

          <form onSubmit={handleAuthSubmit} className="flex flex-col gap-4">
            <input 
              type="text" required value={usernameInput} onChange={e => setUsernameInput(e.target.value)} placeholder="Username"
              className="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-3 text-xs text-slate-200 focus:outline-none focus:border-emerald-500"
            />
            <input 
              type="password" required value={passwordInput} onChange={e => setPasswordInput(e.target.value)} placeholder="Password"
              className="w-full bg-slate-950 border border-slate-800 rounded-xl px-4 py-3 text-xs text-slate-200 focus:outline-none focus:border-emerald-500"
            />
            {authError && <p className="text-xs text-rose-400 bg-rose-950/30 p-2 rounded-lg border border-rose-900">{authError}</p>}
            <button type="submit" className="w-full bg-emerald-600 hover:bg-emerald-500 text-white py-3 rounded-xl font-medium text-sm transition">
              {authMode === 'login' ? 'Sign In' : 'Create Account'}
            </button>
          </form>
          <p className="text-center text-[10px] text-slate-500">Admin: <code className="text-slate-400">admin</code> / <code className="text-slate-400">admin2026</code></p>
        </div>
      </div>
    );
  }

  if (currentUser.role === 'admin') {
    return (
      <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans">
        <header className="border-b border-slate-800 bg-slate-900/50 px-6 py-4 flex items-center justify-between">
          <h1 className="font-bold text-xl text-white">Admin Syllabus Portal</h1>
          <button onClick={() => setCurrentUser(null)} className="text-xs bg-slate-800 hover:bg-slate-700 text-slate-300 px-3 py-2 rounded-lg flex items-center gap-2"><LogOut className="w-3.5 h-3.5" /> Logout</button>
        </header>
        <main className="flex-1 max-w-2xl w-full mx-auto p-6 flex flex-col justify-center">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 flex flex-col gap-6">
            <h2 className="text-lg font-bold text-white flex items-center gap-2"><FileUp className="w-5 h-5 text-emerald-400" /> Upload Syllabus PDF</h2>
            <form onSubmit={handleUploadSyllabus} className="flex flex-col gap-4">
              <input type="file" accept=".pdf" required onChange={e => setSelectedFile(e.target.files[0])} className="bg-slate-950 border border-slate-800 rounded-xl p-3 text-xs text-slate-300" />
              {uploadMessage && <p className="text-xs text-emerald-400">{uploadMessage.text}</p>}
              <button type="submit" disabled={uploading || !selectedFile} className="bg-emerald-600 text-white py-3 rounded-xl text-sm font-medium">{uploading ? 'Processing...' : 'Upload & Index'}</button>
            </form>
          </div>
        </main>
      </div>
    );
  }

  // Find active session title
  const activeSession = sessions.find(s => s.session_id === currentSessionId);
  const activeSessionTitle = activeSession ? activeSession.title : "Lesson Session";

  return (
    <div className="h-screen bg-slate-950 text-slate-100 flex font-sans overflow-hidden">
      {/* Sidebar for Chat Sessions */}
      <aside className="w-72 bg-slate-900 border-r border-slate-800 flex flex-col shrink-0">
        <div className="p-4 border-b border-slate-800 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <GraduationCap className="w-6 h-6 text-emerald-400" />
            <span className="font-bold text-sm tracking-tight text-white">Funda AI Tutor</span>
          </div>
        </div>

        <div className="p-3">
          <button 
            onClick={() => createNewSession("New Lesson")}
            className="w-full bg-emerald-600/20 hover:bg-emerald-600/30 text-emerald-400 border border-emerald-500/30 py-2.5 px-3 rounded-xl text-xs font-semibold flex items-center justify-center gap-2 transition"
          >
            <Plus className="w-4 h-4" /> New Lesson Session
          </button>
        </div>

        <div className="flex-1 overflow-y-auto px-3 py-2 flex flex-col gap-1">
          <p className="text-[10px] uppercase font-semibold text-slate-500 px-2 mb-1">Your Lessons</p>
          {sessions.map(s => (
            <button
              key={s.session_id}
              onClick={() => selectSession(s.session_id)}
              className={`w-full text-left px-3 py-2.5 rounded-xl text-xs font-medium flex items-center gap-2 transition ${currentSessionId === s.session_id ? 'bg-slate-800 text-emerald-400 border border-slate-700' : 'text-slate-400 hover:bg-slate-800/50 hover:text-slate-200'}`}
            >
              <MessageSquare className="w-3.5 h-3.5 shrink-0" />
              <span className="truncate">{s.title}</span>
            </button>
          ))}
        </div>

        <div className="p-4 border-t border-slate-800 flex items-center justify-between">
          <div className="flex items-center gap-2 text-xs text-slate-300 truncate">
            <div className="w-2 h-2 rounded-full bg-emerald-500"></div>
            <span className="truncate">{currentUser.username}</span>
          </div>
          <button onClick={() => setCurrentUser(null)} className="text-slate-400 hover:text-white transition"><LogOut className="w-4 h-4" /></button>
        </div>
      </aside>

      {/* Main Interactive Tutor View */}
      <div className="flex-1 flex flex-col h-screen overflow-hidden">
        <header className="border-b border-slate-800 bg-slate-900/50 backdrop-blur px-6 py-4 flex items-center justify-between z-10 shrink-0">
          <div className="flex items-center gap-3 overflow-hidden">
            <h1 className="font-bold text-sm text-white truncate max-w-md">
              {activeSessionTitle}
            </h1>
            <span className="text-[10px] font-medium px-2 py-0.5 bg-emerald-500/20 text-emerald-400 rounded-full border border-emerald-500/30 shrink-0">
              Socratic Active Learning
            </span>
          </div>
          <select 
            value={studentLevel} 
            onChange={(e) => setStudentLevel(e.target.value)}
            className="bg-slate-900 border border-slate-800 text-slate-200 text-xs rounded-xl px-3 py-1.5 focus:outline-none focus:border-emerald-500 shrink-0 ml-4"
          >
            <option value="Form 1">Form 1</option>
            <option value="Form 2">Form 2</option>
            <option value="Form 3">Form 3</option>
            <option value="Form 4">Form 4</option>
          </select>
        </header>

        <main className="flex-1 overflow-y-auto p-6 flex flex-col items-center">
          <div className="w-full max-w-3xl flex flex-col">
            {messages.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-64 text-slate-500 gap-3 mt-20 text-center">
                <GraduationCap className="w-14 h-14 text-slate-800" />
                <p className="text-sm">Welcome to your interactive lesson! Ask a question or request a quiz on any topic from the Zimbabwe Heritage Curriculum.</p>
              </div>
            ) : (
              messages.map((msg, idx) => <MessageBubble key={idx} msg={msg} />)
            )}
            
            {loading && (
              <div className="flex justify-start mb-4">
                <div className="bg-slate-900 border border-slate-800 rounded-2xl p-4 flex items-center gap-3 text-emerald-400 text-sm">
                  <Sparkles className="w-4 h-4 animate-spin" /> Tutor is formulating guidance & practice questions...
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>
        </main>

        <div className="bg-slate-900 border-t border-slate-800 p-4 shrink-0">
          <div className="max-w-3xl mx-auto flex flex-col gap-2">
            {error && <div className="text-xs text-rose-400 bg-rose-950/30 px-3 py-2 rounded-lg border border-rose-900">{error}</div>}
            <form onSubmit={handleQuery} className="flex gap-3">
              <input 
                type="text"
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
                placeholder="Ask your tutor a question or request a quiz..."
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
    </div>
  );
}