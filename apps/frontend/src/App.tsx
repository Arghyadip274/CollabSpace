import { useState, useRef } from 'react';
import { 
  Sparkles, 
  MessageSquare, 
  FileText, 
  Search, 
  CheckSquare, 
  UserCheck, 
  UserPlus, 
  Zap, 
  Send, 
  Bot, 
  RefreshCw, 
  Hash, 
  ShieldCheck, 
  Layers,
  Copy,
  ArrowUp,
  ArrowDown,
  Save,
  Users,
  Wifi,
  WifiOff
} from 'lucide-react';
import { useCollaborativeDoc } from './hooks/useCollaborativeDoc';

function App() {
  // Navigation & Auth States
  const [activeTab, setActiveTab] = useState<'auth' | 'editor' | 'chat' | 'ai'>('auth');
  const [token, setToken] = useState<string>('');
  const [email, setEmail] = useState<string>('alice_test@example.com');
  const [password, setPassword] = useState<string>('Password1!');
  const [name, setName] = useState<string>('Alice Test');

  // Workspace & Resource States
  const [workspaceId, setWorkspaceId] = useState<string>('');
  const [workspaceName] = useState<string>('Engineering Core');
  const [docId, setDocId] = useState<string>('');
  const [docTitle] = useState<string>('Product Roadmap 2026');
  const [joinDocId, setJoinDocId] = useState<string>('');
  const [channelId, setChannelId] = useState<string>('');
  const [channelName, setChannelName] = useState<string>('general');

  // Real-time collaborative doc hook (Yjs over WebSocket)
  const { docText, setDocText, wsStatus, onlineCount, manualSave, saveStatus, setSaveStatus, latestMessage } =
    useCollaborativeDoc(docId, workspaceId, channelId, token);

  // Real-time Chat States
  const [messages, setMessages] = useState<any[]>([]);
  const [chatInput, setChatInput] = useState<string>('');
  const chatBottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (latestMessage) {
      setMessages(prev => {
        // Prevent duplicate messages
        if (prev.some(m => m.id === latestMessage.id)) return prev;
        return [...prev, latestMessage];
      });
      // Scroll to bottom
      setTimeout(() => chatBottomRef.current?.scrollIntoView({ behavior: 'smooth' }), 100);
    }
  }, [latestMessage]);

  // AI Feature States
  const [docSummary, setDocSummary] = useState<string>('');
  const [isSummarizingDoc, setIsSummarizingDoc] = useState<boolean>(false);
  const [chatSummary, setChatSummary] = useState<any>(null);
  const [isSummarizingChat, setIsSummarizingChat] = useState<boolean>(false);
  
  const [searchQuery, setSearchQuery] = useState<string>('roadmap deadlines');
  const [searchResults, setSearchResults] = useState<any>(null);
  const [isSearching, setIsSearching] = useState<boolean>(false);
  
  const [assistText, setAssistText] = useState<string>('We need to quickly wrap up the backend service before next monday release.');
  const [assistInstruction, setAssistInstruction] = useState<string>('Make it formal and executive-ready');
  const [assistResult, setAssistResult] = useState<string>('');
  const [isStreamingAssist, setIsStreamingAssist] = useState<boolean>(false);
  
  const [extractText, setExtractText] = useState<string>('Alice will deploy the Postgres migration by 5 PM. Bob needs to update the API documentation.');
  const [tasks, setTasks] = useState<any[]>([]);
  const [isExtractingTasks, setIsExtractingTasks] = useState<boolean>(false);

  // Status Indicators
  const [statusMsg, setStatusMsg] = useState<string>('');

  const showStatus = (msg: string) => {
    setStatusMsg(msg);
    setTimeout(() => setStatusMsg(''), 4000);
  };

  // handleManualSave comes from useCollaborativeDoc hook

  // Quick Demo Setup
  const handleQuickDemo = async () => {
    try {
      showStatus('⏳ Initializing demo session...');
      let jwtToken = '';
      
      // Try login first
      const loginRes = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password })
      });

      if (loginRes.ok) {
        const data = await loginRes.json();
        jwtToken = data.access_token;
      } else {
        // If login fails, signup with unique email
        const demoEmail = `user_${Math.floor(Math.random()*10000)}@example.com`;
        setEmail(demoEmail);
        const signupRes = await fetch('/api/auth/signup', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ email: demoEmail, name, password })
        });
        if (signupRes.ok) {
          const data = await signupRes.json();
          jwtToken = data.access_token;
        }
      }

      if (!jwtToken) {
        showStatus('❌ Auth failed. Please check backend server.');
        return;
      }
      setToken(jwtToken);

      // 2. Create Workspace
      const wsRes = await fetch('/api/workspaces', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${jwtToken}` },
        body: JSON.stringify({ name: workspaceName })
      });
      let wsId = '';
      if (wsRes.ok) {
        const wsData = await wsRes.json();
        wsId = wsData.id;
        setWorkspaceId(wsId);
      }

      if (wsId) {
        // 3. Create Doc
        const docRes = await fetch(`/api/documents/${wsId}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${jwtToken}` },
          body: JSON.stringify({ title: docTitle })
        });
        if (docRes.ok) {
          const dData = await docRes.json();
          setDocId(dData.id);
        }

        // 4. Create Channel & Initial Message
        const chRes = await fetch(`/api/workspaces/${wsId}/channels`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${jwtToken}` },
          body: JSON.stringify({ name: 'general-' + Math.floor(Math.random()*100), type: 'PUBLIC' })
        });
        if (chRes.ok) {
          const chData = await chRes.json();
          setChannelId(chData.id);
          setChannelName(chData.name);

          // Add demo message
          await fetch(`/api/channels/${chData.id}/messages`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${jwtToken}` },
            body: JSON.stringify({ content: 'Welcome to the team workspace! @Alice let us review the sprint goals.' })
          });

          // Fetch messages
          fetchMessages(chData.id, jwtToken);
        }
      }

      showStatus('🚀 Demo Workspace initialized!');
      setActiveTab('editor');
    } catch (e: any) {
      showStatus('Error initializing: ' + e.message);
    }
  };

  const fetchMessages = async (cId: string, tok: string) => {
    try {
      const res = await fetch(`/api/channels/${cId}/messages`, {
        headers: { Authorization: `Bearer ${tok}` }
      });
      if (res.ok) {
        const data = await res.json();
        setMessages(data.messages.reverse() || []);
      }
    } catch (e) {}
  };

  const handleSendMessage = async () => {
    if (!chatInput.trim() || !channelId || !token) return;
    const content = chatInput;
    setChatInput('');

    try {
      const res = await fetch(`/api/channels/${channelId}/messages`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ content })
      });
      if (res.ok) {
        fetchMessages(channelId, token);
      }
    } catch (e) {}
  };

  // AI Feature Handlers
  const handleSummarizeDoc = async () => {
    if (!docId || !token) return;
    setIsSummarizingDoc(true);
    setDocSummary('');
    setSaveStatus('Saving...');
    try {
      const res = await fetch(`/api/ai/document/${docId}/summarize`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ content: docText })
      });
      const data = await res.json();
      setDocSummary(data.summary || 'Summary generated successfully.');
      setSaveStatus('Saved');
    } catch (e: any) {
      setDocSummary('Failed to summarize document.');
      setSaveStatus('Error saving');
    } finally {
      setIsSummarizingDoc(false);
    }
  };

  const handleSummarizeChat = async () => {
    if (!channelId || !token) return;
    setIsSummarizingChat(true);
    setChatSummary(null);
    try {
      const res = await fetch(`/api/ai/channel/${channelId}/summarize`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ since_hours: 24 })
      });
      const data = await res.json();
      setChatSummary(data);
    } catch (e: any) {
      setChatSummary({ error: 'Failed to summarize chat.' });
    } finally {
      setIsSummarizingChat(false);
    }
  };

  const handleSearch = async () => {
    if (!workspaceId || !token || !searchQuery) return;
    setIsSearching(true);
    try {
      const res = await fetch(`/api/ai/search`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ query: searchQuery, workspace_id: workspaceId })
      });
      const data = await res.json();
      setSearchResults(data);
    } catch (e: any) {
      setSearchResults({ error: 'Search failed' });
    } finally {
      setIsSearching(false);
    }
  };

  const handleAssist = async () => {
    if (!token || !assistText) return;
    setIsStreamingAssist(true);
    setAssistResult('');
    try {
      const res = await fetch(`/api/ai/assist`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ text: assistText, instruction: assistInstruction })
      });
      
      const reader = res.body?.getReader();
      const decoder = new TextDecoder();
      if (!reader) return;

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        setAssistResult(prev => prev + decoder.decode(value));
      }
    } catch (e) {
      setAssistResult('Error streaming response.');
    } finally {
      setIsStreamingAssist(false);
    }
  };

  const handleExtractTasks = async () => {
    if (!workspaceId || !token || !extractText) return;
    setIsExtractingTasks(true);
    try {
      const res = await fetch(`/api/ai/extract-tasks`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ content: extractText, workspace_id: workspaceId })
      });
      const data = await res.json();
      setTasks(data.tasks || []);
    } catch (e) {
      setTasks([]);
    } finally {
      setIsExtractingTasks(false);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh' }}>
      {/* ─── Top Navbar ────────────────────────────────────────────────── */}
      <header style={{ 
        height: '64px', 
        borderBottom: '1px solid var(--border-subtle)', 
        background: 'rgba(15, 23, 42, 0.8)', 
        backdropFilter: 'blur(12px)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0 24px',
        zIndex: 10
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div style={{ 
            width: '36px', 
            height: '36px', 
            borderRadius: '10px', 
            background: 'var(--gradient-brand)', 
            display: 'flex', 
            alignItems: 'center', 
            justifyContent: 'center',
            boxShadow: '0 0 16px rgba(99, 102, 241, 0.5)'
          }}>
            <Zap size={20} color="#FFF" />
          </div>
          <div>
            <h1 className="font-heading gradient-text" style={{ fontSize: '20px', fontWeight: '800', lineHeight: 1 }}>CollabSpace AI</h1>
            <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Enterprise Collaboration Engine</span>
          </div>
        </div>

        {/* Global Controls & Status */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          {statusMsg && (
            <div className="badge badge-primary animate-fade">
              <Sparkles size={12} /> {statusMsg}
            </div>
          )}

          {token ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              <span className="badge badge-success">
                <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: '#34D399', display: 'inline-block' }}></span>
                Connected
              </span>
              <div style={{ 
                background: 'rgba(30, 41, 59, 0.8)', 
                padding: '6px 12px', 
                borderRadius: '20px', 
                border: '1px solid var(--border-subtle)',
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                fontSize: '13px'
              }}>
                <UserCheck size={14} color="#818CF8" />
                <span>{name}</span>
              </div>
            </div>
          ) : (
            <button className="btn-primary" onClick={handleQuickDemo}>
              <Zap size={16} /> One-Click Demo Setup
            </button>
          )}
        </div>
      </header>

      {/* ─── Main Workspace Body ───────────────────────────────────────── */}
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        
        {/* Left Sidebar Navigation */}
        <aside style={{ 
          width: '260px', 
          borderRight: '1px solid var(--border-subtle)', 
          background: 'rgba(11, 15, 25, 0.9)', 
          padding: '20px 14px',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'space-between'
        }}>
          <div>
            <div style={{ marginBottom: '24px' }}>
              <div style={{ fontSize: '11px', fontWeight: 700, color: 'var(--text-dim)', textTransform: 'uppercase', letterSpacing: '1px', marginBottom: '8px' }}>
                WORKSPACE
              </div>
              <div style={{ 
                background: 'rgba(30, 41, 59, 0.5)', 
                padding: '10px 12px', 
                borderRadius: '10px', 
                border: '1px solid var(--border-subtle)',
                display: 'flex',
                alignItems: 'center',
                gap: '10px'
              }}>
                <Layers size={18} color="#818CF8" />
                <span style={{ fontWeight: 600, fontSize: '14px' }}>{workspaceName}</span>
              </div>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
              <div style={{ fontSize: '11px', fontWeight: 700, color: 'var(--text-dim)', textTransform: 'uppercase', letterSpacing: '1px', marginBottom: '4px' }}>
                NAVIGATION
              </div>
              
              <button 
                className={`btn-secondary ${activeTab === 'auth' ? 'glass-card' : ''}`}
                style={{ justifyContent: 'flex-start', width: '100%', borderColor: activeTab === 'auth' ? 'var(--primary)' : 'transparent' }}
                onClick={() => setActiveTab('auth')}
              >
                <ShieldCheck size={18} color={activeTab === 'auth' ? '#818CF8' : '#94A3B8'} />
                <span>1. Auth & Setup</span>
              </button>

              <button 
                className={`btn-secondary ${activeTab === 'editor' ? 'glass-card' : ''}`}
                style={{ justifyContent: 'flex-start', width: '100%', borderColor: activeTab === 'editor' ? 'var(--primary)' : 'transparent' }}
                onClick={() => setActiveTab('editor')}
                disabled={!token}
              >
                <FileText size={18} color={activeTab === 'editor' ? '#818CF8' : '#94A3B8'} />
                <span>2. Docs Editor</span>
              </button>

              <button 
                className={`btn-secondary ${activeTab === 'chat' ? 'glass-card' : ''}`}
                style={{ justifyContent: 'flex-start', width: '100%', borderColor: activeTab === 'chat' ? 'var(--primary)' : 'transparent' }}
                onClick={() => setActiveTab('chat')}
                disabled={!token}
              >
                <MessageSquare size={18} color={activeTab === 'chat' ? '#818CF8' : '#94A3B8'} />
                <span>3. Realtime Chat</span>
              </button>

              <button 
                className={`btn-secondary ${activeTab === 'ai' ? 'glass-card' : ''}`}
                style={{ justifyContent: 'flex-start', width: '100%', borderColor: activeTab === 'ai' ? 'var(--primary)' : 'transparent' }}
                onClick={() => setActiveTab('ai')}
                disabled={!token}
              >
                <Bot size={18} color={activeTab === 'ai' ? '#818CF8' : '#94A3B8'} />
                <span>4. AI Studio</span>
                <span className="badge badge-primary" style={{ marginLeft: 'auto', fontSize: '10px' }}>5 API</span>
              </button>
            </div>
          </div>

          <div className="glass-card" style={{ padding: '12px', fontSize: '12px', color: 'var(--text-muted)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '4px', fontWeight: 600, color: '#F8FAFC' }}>
              <Zap size={14} color="#F59E0B" /> Phase 7 Stack
            </div>
            FastAPI • Redis • Postgres pgvector • Yjs CRDT
          </div>
        </aside>

        {/* Central Content Canvas */}
        <main style={{ flex: 1, padding: '24px', overflowY: 'auto' }}>
          
          {/* TAB 1: AUTH & WORKSPACE SETUP */}
          {activeTab === 'auth' && (
            <div className="animate-fade" style={{ maxWidth: '800px', margin: '0 auto' }}>
              <div style={{ marginBottom: '24px' }}>
                <h2 className="font-heading" style={{ fontSize: '26px', fontWeight: 700 }}>Authentication & Workspace Control</h2>
                <p style={{ color: 'var(--text-muted)' }}>Authenticate, issue JWT tokens, and provision real-time collaborative workspaces.</p>
              </div>

              <div className="glass-panel" style={{ padding: '24px', marginBottom: '24px' }}>
                <h3 style={{ fontSize: '18px', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <UserPlus size={20} color="#818CF8" /> User Credential Token Generator
                </h3>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', marginBottom: '16px' }}>
                  <div>
                    <label style={{ fontSize: '12px', color: 'var(--text-muted)', display: 'block', marginBottom: '6px' }}>Full Name</label>
                    <input className="input-field" value={name} onChange={e => setName(e.target.value)} />
                  </div>
                  <div>
                    <label style={{ fontSize: '12px', color: 'var(--text-muted)', display: 'block', marginBottom: '6px' }}>Email Address</label>
                    <input className="input-field" value={email} onChange={e => setEmail(e.target.value)} />
                  </div>
                  <div style={{ gridColumn: 'span 2' }}>
                    <label style={{ fontSize: '12px', color: 'var(--text-muted)', display: 'block', marginBottom: '6px' }}>Password</label>
                    <input className="input-field" type="password" value={password} onChange={e => setPassword(e.target.value)} />
                  </div>
                </div>

                <div style={{ display: 'flex', gap: '12px' }}>
                  <button className="btn-primary" onClick={handleQuickDemo}>
                    <Zap size={16} /> Instant One-Click Demo Setup
                  </button>
                </div>
              </div>

              {token && (
                <div className="glass-panel animate-fade" style={{ padding: '24px' }}>
                  <h3 style={{ fontSize: '18px', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <Layers size={20} color="#34D399" /> Provision Workspace Resources
                  </h3>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', marginBottom: '16px' }}>
                    <div>
                      <label style={{ fontSize: '12px', color: 'var(--text-muted)', display: 'block', marginBottom: '6px' }}>Workspace ID</label>
                      <input className="input-field" value={workspaceId} readOnly placeholder="Created on setup..." />
                    </div>
                    <div>
                      <label style={{ fontSize: '12px', color: 'var(--text-muted)', display: 'block', marginBottom: '6px' }}>Document ID (yours)</label>
                      <input className="input-field" value={docId} readOnly placeholder="Created on setup..." />
                    </div>
                  </div>

                  {/* Join another user's document */}
                  <div style={{ borderTop: '1px solid var(--border-subtle)', paddingTop: '16px' }}>
                    <div style={{ fontSize: '13px', color: 'var(--text-muted)', marginBottom: '8px', fontWeight: 600 }}>
                      🔗 Join a Colleague's Document (Paste their Doc ID below to collaborate live)
                    </div>
                    <div style={{ display: 'flex', gap: '8px' }}>
                      <input
                        className="input-field"
                        value={joinDocId}
                        onChange={e => setJoinDocId(e.target.value)}
                        placeholder="Paste Document ID here..."
                      />
                      <button
                        className="btn-primary"
                        style={{ whiteSpace: 'nowrap' }}
                        disabled={!joinDocId.trim()}
                        onClick={() => { setDocId(joinDocId.trim()); setActiveTab('editor'); }}
                      >
                        Join Doc
                      </button>
                    </div>
                  </div>

                  {/* Join another user's channel */}
                  <div style={{ borderTop: '1px solid var(--border-subtle)', paddingTop: '16px', marginTop: '16px' }}>
                    <div style={{ fontSize: '13px', color: 'var(--text-muted)', marginBottom: '8px', fontWeight: 600 }}>
                      💬 Join a Colleague's Chat (Paste their Channel ID below)
                    </div>
                    <div style={{ display: 'flex', gap: '8px' }}>
                      <input
                        className="input-field"
                        value={channelId}
                        onChange={e => setChannelId(e.target.value)}
                        placeholder="Paste Channel ID here..."
                      />
                      <button
                        className="btn-primary"
                        style={{ whiteSpace: 'nowrap' }}
                        disabled={!channelId.trim()}
                        onClick={() => { setActiveTab('chat'); }}
                      >
                        Join Chat
                      </button>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* TAB 2: GOOGLE DOCS COLLABORATIVE EDITOR */}
          {activeTab === 'editor' && (
            <div className="animate-fade" style={{ maxWidth: '1000px', margin: '0 auto' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '20px' }}>
                <div>
                  <h2 className="font-heading" style={{ fontSize: '24px', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <FileText color="#818CF8" /> {docTitle}
                  </h2>
                  <div style={{ display: 'flex', gap: '12px', marginTop: '6px', fontSize: '12px', color: 'var(--text-muted)', alignItems: 'center' }}>
                    <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                      {wsStatus === 'Live'
                        ? <Wifi size={12} color="#34D399" />
                        : <WifiOff size={12} color="#ef4444" />}
                      <span style={{ color: wsStatus === 'Live' ? '#34D399' : '#ef4444', fontWeight: 600 }}>{wsStatus}</span>
                    </span>
                    <span>•</span>
                    <span style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                      <Users size={12} color="#818CF8" /> {onlineCount} online
                    </span>
                    <span>•</span>
                    <span>CRDT: Yjs</span>
                  </div>
                </div>

                <button className="btn-primary" onClick={handleSummarizeDoc} disabled={isSummarizingDoc || !docId}>
                  <Sparkles size={16} /> {isSummarizingDoc ? 'Summarizing...' : 'AI Summarize Doc'}
                </button>
              </div>

              {/* AI Summary Banner */}
              {docSummary && (
                <div className="glass-panel animate-fade" style={{ padding: '16px', marginBottom: '20px', borderLeft: '4px solid var(--primary)', background: 'rgba(99, 102, 241, 0.1)' }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 600, color: '#818CF8' }}>
                      <Bot size={16} /> Gemini Document Summary
                    </div>
                    <div style={{ display: 'flex', gap: '8px' }}>
                      <button className="btn-secondary" style={{ padding: '6px 12px', fontSize: '12px' }} onClick={() => { navigator.clipboard.writeText(docSummary); showStatus("Copied to clipboard!"); }}>
                        <Copy size={14} /> Copy
                      </button>
                      <button className="btn-secondary" style={{ padding: '6px 12px', fontSize: '12px' }} onClick={() => setDocText(docSummary + '\n\n' + docText)}>
                        <ArrowUp size={14} /> Insert Top
                      </button>
                      <button className="btn-secondary" style={{ padding: '6px 12px', fontSize: '12px' }} onClick={() => setDocText(docText + '\n\n' + docSummary)}>
                        <ArrowDown size={14} /> Insert Bottom
                      </button>
                    </div>
                  </div>
                  <pre style={{ fontSize: '14px', lineHeight: 1.5, whiteSpace: 'pre-wrap', fontFamily: 'inherit' }}>{docSummary}</pre>
                </div>
              )}

              {/* Collaborative Editor Panel */}
              <div className="glass-panel" style={{ padding: '24px', minHeight: '400px', display: 'flex', flexDirection: 'column' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: '1px solid var(--border-subtle)', paddingBottom: '12px', marginBottom: '16px' }}>
                  <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                    <span className="badge badge-primary">Collaborative View</span>
                    <span className={`badge ${saveStatus === 'Saved' ? 'badge-success' : 'badge-warning'}`}>
                      {saveStatus}
                    </span>
                  </div>
                  <div style={{ display: 'flex', gap: '8px' }}>
                    <button className="btn-secondary" style={{ padding: '6px 12px', fontSize: '12px' }} onClick={manualSave}>
                      <Save size={14} /> Save Now
                    </button>
                    <div style={{ fontSize: '12px', color: 'var(--text-dim)', alignSelf: 'center' }}>ID: {docId}</div>
                  </div>
                </div>

                <textarea 
                  className="input-field" 
                  style={{ flex: 1, minHeight: '300px', fontFamily: 'monospace', fontSize: '14px', lineHeight: '1.6', resize: 'vertical' }}
                  value={docText}
                  onChange={e => setDocText(e.target.value)}
                  placeholder="Type document content here... Open a second tab and join this document to see live collaboration!"
                />
              </div>
            </div>
          )}

          {/* TAB 3: SLACK-LIKE CHAT & PRESENCE */}
          {activeTab === 'chat' && (
            <div className="animate-fade" style={{ maxWidth: '1000px', margin: '0 auto', height: '100%', display: 'flex', flexDirection: 'column' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
                <div>
                  <h2 className="font-heading" style={{ fontSize: '24px', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <Hash color="#818CF8" /> {channelName}
                  </h2>
                  <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>Realtime Redis Pub/Sub + Presence Tracking</span>
                </div>

                <button className="btn-secondary" onClick={handleSummarizeChat} disabled={isSummarizingChat || !channelId}>
                  <Sparkles size={16} color="#818CF8" /> {isSummarizingChat ? 'Extracting...' : 'AI Meeting Summary'}
                </button>
              </div>

              {/* AI Structured Meeting Summary Modal/Banner */}
              {chatSummary && (
                <div className="glass-panel animate-fade" style={{ padding: '16px', marginBottom: '16px', borderLeft: '4px solid var(--secondary)' }}>
                  <div style={{ fontWeight: 700, color: '#A855F7', marginBottom: '8px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <Bot size={16} /> Structured Chat Summary & Action Items
                  </div>
                  <pre style={{ fontSize: '13px', background: 'rgba(15, 23, 42, 0.6)', padding: '12px', borderRadius: '8px', overflowX: 'auto', whiteSpace: 'pre-wrap' }}>
                    {JSON.stringify(chatSummary, null, 2)}
                  </pre>
                </div>
              )}

              {/* Chat Stream Window */}
              <div className="glass-panel" style={{ flex: 1, minHeight: '350px', padding: '20px', display: 'flex', flexDirection: 'column', gap: '16px', overflowY: 'auto' }}>
                {messages.length === 0 ? (
                  <div style={{ textAlign: 'center', color: 'var(--text-dim)', margin: 'auto' }}>
                    <MessageSquare size={32} style={{ opacity: 0.3, marginBottom: '8px' }} />
                    <p>No messages yet. Send a message to get started!</p>
                  </div>
                ) : (
                  messages.map((m: any, idx: number) => (
                    <div key={idx} style={{ display: 'flex', gap: '12px', alignItems: 'flex-start' }}>
                      <div style={{ width: '32px', height: '32px', borderRadius: '50%', background: 'var(--gradient-brand)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700, fontSize: '12px' }}>
                        {m.authorName ? m.authorName.charAt(0) : 'U'}
                      </div>
                      <div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '2px' }}>
                          <span style={{ fontWeight: 600, fontSize: '14px' }}>{m.authorName || 'Member'}</span>
                          <span style={{ fontSize: '11px', color: 'var(--text-dim)' }}>
                            {m.createdAt ? new Date(m.createdAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : 'just now'}
                          </span>
                        </div>
                        <div style={{ background: 'rgba(30, 41, 59, 0.6)', padding: '10px 14px', borderRadius: '0 12px 12px 12px', fontSize: '14px', maxWidth: '600px' }}>
                          {m.content}
                        </div>
                      </div>
                    </div>
                  ))
                )}
                <div ref={chatBottomRef} />
              </div>

              {/* Message Input Box */}
              <div style={{ display: 'flex', gap: '12px', marginTop: '16px' }}>
                <input 
                  className="input-field" 
                  placeholder="Type message... (Use @Name to mention members)" 
                  value={chatInput} 
                  onChange={e => setChatInput(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && handleSendMessage()}
                />
                <button className="btn-primary" onClick={handleSendMessage}>
                  <Send size={16} /> Send
                </button>
              </div>
            </div>
          )}

          {/* TAB 4: AI STUDIO (SEMANTIC SEARCH, ASSISTANT, TASK EXTRACTION) */}
          {activeTab === 'ai' && (
            <div className="animate-fade" style={{ maxWidth: '1000px', margin: '0 auto' }}>
              <div style={{ marginBottom: '24px' }}>
                <h2 className="font-heading" style={{ fontSize: '26px', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '10px' }}>
                  <Bot color="#EC4899" /> AI Command Studio
                </h2>
                <p style={{ color: 'var(--text-muted)' }}>Explore vector similarity search, streaming writing assistance, and automated task extraction.</p>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
                
                {/* 1. Vector Search */}
                <div className="glass-panel" style={{ padding: '20px' }}>
                  <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '12px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <Search size={18} color="#818CF8" /> Vector Similarity Search (pgvector)
                  </h3>
                  <div style={{ display: 'flex', gap: '8px', marginBottom: '12px' }}>
                    <input className="input-field" value={searchQuery} onChange={e => setSearchQuery(e.target.value)} placeholder="Search query..." />
                    <button className="btn-primary" onClick={handleSearch} disabled={isSearching}>
                      {isSearching ? <RefreshCw className="animate-pulse-slow" size={16} /> : <Search size={16} />}
                    </button>
                  </div>
                  {searchResults && (
                    <pre style={{ fontSize: '12px', background: 'rgba(15, 23, 42, 0.6)', padding: '10px', borderRadius: '8px', maxHeight: '180px', overflowY: 'auto' }}>
                      {JSON.stringify(searchResults, null, 2)}
                    </pre>
                  )}
                </div>

                {/* 2. Task Extraction */}
                <div className="glass-panel" style={{ padding: '20px' }}>
                  <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '12px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <CheckSquare size={18} color="#34D399" /> Task Extraction Engine
                  </h3>
                  <textarea 
                    className="input-field" 
                    style={{ height: '70px', marginBottom: '12px', fontSize: '13px' }} 
                    value={extractText} 
                    onChange={e => setExtractText(e.target.value)} 
                  />
                  <button className="btn-secondary" style={{ width: '100%', justifyContent: 'center' }} onClick={handleExtractTasks} disabled={isExtractingTasks}>
                    <Sparkles size={16} color="#34D399" /> {isExtractingTasks ? 'Extracting...' : 'Extract Actionable Tasks'}
                  </button>

                  {tasks.length > 0 && (
                    <div style={{ marginTop: '12px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
                      {tasks.map((t: any, i: number) => (
                        <div key={i} className="glass-card" style={{ padding: '8px 12px', fontSize: '13px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <span>{t.title || t.description}</span>
                          <span className="badge badge-primary">{t.assignee || 'Unassigned'}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {/* 3. AI Writing Assistant (Streaming) */}
                <div className="glass-panel" style={{ gridColumn: 'span 2', padding: '20px' }}>
                  <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '12px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <Sparkles size={18} color="#EC4899" /> SSE Streaming Writing Assistant
                  </h3>
                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', marginBottom: '12px' }}>
                    <textarea 
                      className="input-field" 
                      style={{ height: '80px', fontSize: '13px' }}
                      value={assistText} 
                      onChange={e => setAssistText(e.target.value)}
                      placeholder="Input text to rewrite..." 
                    />
                    <input 
                      className="input-field" 
                      value={assistInstruction} 
                      onChange={e => setAssistInstruction(e.target.value)}
                      placeholder="Instruction (e.g. Make concise)" 
                    />
                  </div>

                  <button className="btn-primary" style={{ width: '100%', justifyContent: 'center' }} onClick={handleAssist} disabled={isStreamingAssist}>
                    <Zap size={16} /> {isStreamingAssist ? 'Streaming Output...' : 'Generate AI Stream Output'}
                  </button>

                  {assistResult && (
                    <div style={{ marginTop: '16px', background: 'rgba(15, 23, 42, 0.8)', padding: '14px', borderRadius: '10px', border: '1px solid var(--border-active)' }}>
                      <div style={{ fontSize: '11px', color: 'var(--text-dim)', marginBottom: '6px', fontWeight: 700 }}>STREAMED OUTPUT</div>
                      <p style={{ fontSize: '14px', lineHeight: 1.5, color: '#F8FAFC' }}>{assistResult}</p>
                    </div>
                  )}
                </div>

              </div>
            </div>
          )}

        </main>
      </div>
    </div>
  );
}

export default App;
