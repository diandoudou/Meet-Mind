import { useParams, useNavigate } from 'react-router-dom';
import { useState, useEffect, useRef } from 'react';
import type { ReactNode, MouseEvent, FormEvent } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { 
  Folder, 
  Clock, 
  Users, 
  FileText, 
  Search, 
  ChevronRight,
  TrendingUp,
  MessageSquare,
  Play,
  Loader2,
  Calendar,
  Plus,
  Sparkles,
  Send,
  Bot,
  User,
  X,
  CheckCircle2,
  Circle,
  AlertCircle,
  AlignLeft,
  ListChecks,
  Upload,
  Trash2,
  ExternalLink
} from 'lucide-react';
import { cn } from '../lib/utils';
import { Project, Meeting, ActionItem } from '../types';
import { useFirebase } from '../context/FirebaseContext';
import { doc, onSnapshot, collection, query, orderBy, getDocs, addDoc, deleteDoc } from 'firebase/firestore';
import { db, handleFirestoreError, OperationType, storage } from '../firebase';
import { ref, uploadBytesResumable, getDownloadURL, deleteObject } from 'firebase/storage';
import { GoogleGenAI } from '@google/genai';
import { ProjectFile } from '../types';

export default function ProjectDetail() {
  const { projectId } = useParams();
  const navigate = useNavigate();
  const { user } = useFirebase();
  const [project, setProject] = useState<Project | null>(null);
  const [meetings, setMeetings] = useState<Meeting[]>([]);
  const [actions, setActions] = useState<ActionItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<'sessions' | 'assistant'>('sessions');
  const [selectedMeeting, setSelectedMeeting] = useState<Meeting | null>(null);
  const [meetingActions, setMeetingActions] = useState<ActionItem[]>([]);
  const [meetingDetailTab, setMeetingDetailTab] = useState<'summary' | 'actions' | 'transcript'>('summary');

  // AI Assistant state
  const [messages, setMessages] = useState<{ role: 'user' | 'assistant', content: string }[]>([
    { role: 'assistant', content: "Hi! I'm your project AI assistant. Ask me anything about this project's meetings, decisions, or action items." }
  ]);
  const [aiInput, setAiInput] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [messages, isTyping]);

  const [files, setFiles] = useState<ProjectFile[]>([]);
  const [uploadProgress, setUploadProgress] = useState<Record<string, number>>({});
  const [isDragOver, setIsDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!selectedMeeting || !projectId) return;
    const filtered = actions.filter(a => a.meetingId === selectedMeeting.id);
    setMeetingActions(filtered);
  }, [selectedMeeting, actions, projectId]);

  useEffect(() => {
    if (!projectId || !user) return;

    // Project metadata listener
    const unsubProj = onSnapshot(doc(db, 'projects', projectId), (snap) => {
      if (snap.exists()) {
        setProject({ ...snap.data(), id: snap.id } as Project);
      }
      setLoading(false);
    }, (err) => handleFirestoreError(err, OperationType.GET, `projects/${projectId}`));

    // Sessions listener
    const qMtg = query(collection(db, 'projects', projectId, 'meetings'), orderBy('date', 'desc'));
    const unsubMtg = onSnapshot(qMtg, (snap) => {
      setMeetings(snap.docs.map(d => ({ ...d.data(), id: d.id } as Meeting)));
    }, (err) => handleFirestoreError(err, OperationType.LIST, `projects/${projectId}/meetings`));

    // Action items listener
    const qAct = query(collection(db, 'projects', projectId, 'actionItems'), orderBy('deadline', 'asc'));
    const unsubAct = onSnapshot(qAct, (snap) => {
      setActions(snap.docs.map(d => ({ ...d.data(), id: d.id } as ActionItem)));
    }, (err) => handleFirestoreError(err, OperationType.LIST, `projects/${projectId}/actionItems`));

    return () => {
      unsubProj();
      unsubMtg();
      unsubAct();
    };
  }, [projectId, user]);

  // Listen for project files
  useEffect(() => {
    if (!projectId) return;
    const q = query(collection(db, 'projects', projectId, 'files'), orderBy('uploadedAt', 'desc'));
    const unsub = onSnapshot(q, snap => {
      setFiles(snap.docs.map(d => ({ ...d.data(), id: d.id } as ProjectFile)));
    });
    return unsub;
  }, [projectId]);

  if (loading) {
    return (
      <div className="h-full w-full flex items-center justify-center bg-slate-50">
        <Loader2 className="w-8 h-8 text-academic-900 animate-spin" />
      </div>
    );
  }

  if (!project) {
    return (
      <div className="p-20 text-center space-y-4">
        <h2 className="text-2xl font-bold text-slate-900">Project Not Found</h2>
        <button onClick={() => navigate('/')} className="text-academic-900 font-bold hover:underline">Back to Dashboard</button>
      </div>
    );
  }

  const completedActions = actions.filter(a => a.status === 'completed').length;
  const taskVelocity = actions.length > 0 ? Math.round((completedActions / actions.length) * 100) : 0;

  const handleUpload = (fileList: FileList | null) => {
    if (!fileList || !projectId || !user) return;
    Array.from(fileList).forEach(file => {
      if (file.type !== 'application/pdf') return;
      const storagePath = `projects/${projectId}/files/${Date.now()}_${file.name}`;
      const storageRef = ref(storage, storagePath);
      const task = uploadBytesResumable(storageRef, file);
      task.on('state_changed',
        snap => {
          const pct = Math.round((snap.bytesTransferred / snap.totalBytes) * 100);
          setUploadProgress(prev => ({ ...prev, [file.name]: pct }));
        },
        err => console.error('Upload error', err),
        async () => {
          const downloadURL = await getDownloadURL(task.snapshot.ref);
          await addDoc(collection(db, 'projects', projectId, 'files'), {
            name: file.name,
            size: file.size,
            type: file.type,
            storagePath,
            downloadURL,
            uploadedAt: Date.now(),
            uploadedBy: user.displayName || user.email || 'Unknown',
          });
          setUploadProgress(prev => { const n = { ...prev }; delete n[file.name]; return n; });
        }
      );
    });
  };

  const handleDeleteFile = async (file: ProjectFile) => {
    if (!projectId) return;
    try {
      await deleteObject(ref(storage, file.storagePath));
      await deleteDoc(doc(db, 'projects', projectId, 'files', file.id));
    } catch (err) {
      console.error('Delete error', err);
    }
  };

  const handleDeleteMeeting = async (meeting: Meeting, e: MouseEvent) => {
    e.stopPropagation(); // 防止触发会议详情打开
    if (!projectId) return;
    if (!confirm(`Are you sure you want to delete "${meeting.title}"? This will also remove all related action items.`)) return;
    
    try {
      // 删除相关的 action items
      const relatedActions = actions.filter(a => a.meetingId === meeting.id);
      await Promise.all(relatedActions.map(action => 
        deleteDoc(doc(db, 'projects', projectId, 'actionItems', action.id))
      ));
      
      // 删除会议本身
      await deleteDoc(doc(db, 'projects', projectId, 'meetings', meeting.id));
      
      // 如果当前打开的详情是被删除的会议，关闭详情面板
      if (selectedMeeting?.id === meeting.id) {
        setSelectedMeeting(null);
      }
    } catch (err) {
      console.error('Delete meeting error', err);
      alert('Failed to delete meeting. Please try again.');
    }
  };

  const handleAiSend = async (e: FormEvent) => {
    e.preventDefault();
    if (!aiInput.trim() || isTyping) return;
    const userMsg = aiInput.trim();
    setAiInput('');
    setMessages(prev => [...prev, { role: 'user', content: userMsg }]);
    setIsTyping(true);
    try {
      let context = `Project: ${project?.name}\nDescription: ${project?.description}\n\n`;
      meetings.forEach(m => {
        context += `Meeting: ${m.title} (${new Date(m.date).toLocaleDateString()})\nSummary: ${m.summary || 'N/A'}\n\n`;
      });
      actions.forEach(a => {
        context += `Action Item: ${a.title} - Status: ${a.status}\n`;
      });

      const apiKey = import.meta.env.VITE_GEMINI_API_KEY;
      if (!apiKey) {
        setMessages(prev => [...prev, { role: 'assistant', content: "Gemini API key is not configured. Please set VITE_GEMINI_API_KEY in frontend/.env." }]);
        return;
      }

      const ai = new GoogleGenAI({ apiKey });
      const result = await ai.models.generateContent({
        model: "gemini-2.0-flash-exp",
        contents: userMsg,
        config: {
          systemInstruction: `You are an AI assistant for the project "${project?.name}". Answer questions based on the project context below. Be concise and helpful.\n\nContext:\n${context}`
        }
      });
      setMessages(prev => [...prev, { role: 'assistant', content: result.text || "I couldn't process that request." }]);
    } catch (err) {
      console.error(err);
      setMessages(prev => [...prev, { role: 'assistant', content: "Error retrieving project knowledge. Please check your API configuration." }]);
    } finally {
      setIsTyping(false);
    }
  };

  return (
    <div className="flex-1 overflow-y-auto pb-20">
      {/* Hero Header */}
      <div className="h-80 bg-academic-900 relative overflow-hidden flex items-center px-16">
         <div className="absolute inset-0 opacity-20">
            <div className="absolute top-0 right-0 w-[500px] h-[500px] bg-accent-gold rounded-full blur-[120px] -translate-y-1/2 translate-x-1/2" />
            <div className="absolute bottom-0 left-0 w-[400px] h-[400px] bg-blue-500 rounded-full blur-[100px] translate-y-1/2 -translate-x-1/2" />
         </div>
         
         <div className="relative z-10 flex flex-col md:flex-row md:items-center justify-between w-full gap-8">
            <div className="flex items-center gap-8">
              <div className="w-24 h-24 bg-white/10 backdrop-blur-xl rounded-3xl flex items-center justify-center border border-white/20 shadow-2xl shrink-0">
                 <Folder size={48} className="text-white" />
              </div>
              <div className="space-y-3">
                 <div className="flex items-center gap-3">
                   <h2 className="text-4xl font-bold text-white tracking-tight">{project.name}</h2>
                   <span className="px-3 py-1 bg-accent-gold text-academic-950 font-bold rounded-full text-[10px] uppercase tracking-widest shadow-lg shadow-accent-gold/20">Active Node</span>
                 </div>
                 <p className="text-academic-50/70 max-w-xl text-lg leading-relaxed">{project.description}</p>
              </div>
            </div>
            <button 
              onClick={() => navigate(`/meeting/active?projectId=${projectId}`)}
              className="bg-white text-academic-900 px-8 py-4 rounded-2xl font-bold flex items-center gap-3 shadow-2xl hover:bg-accent-gold transition-all active:scale-95 shrink-0"
            >
              <Play size={20} className="fill-current" />
              Start New Session
            </button>
         </div>
      </div>

      <div className="p-12 max-w-7xl mx-auto -mt-12 relative z-20">
        <div className="grid grid-cols-1 lg:grid-cols-4 gap-12">
          
          {/* Main Content Area */}
          <div className="lg:col-span-3 space-y-8">
            {/* Stats Bar */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
               <StatCard icon={<Clock size={16} />} label="Total Syncs" value={meetings.length.toString()} />
               <StatCard icon={<Users size={16} />} label="Contributors" value={(project.members.length + 1).toString()} />
               <StatCard icon={<TrendingUp size={16} />} label="Task Velocity" value={`${taskVelocity}%`} />
               <StatCard icon={<MessageSquare size={16} />} label="Action Items" value={actions.length.toString()} />
            </div>

            {/* Tabs */}
            <div className="flex gap-1 bg-slate-100 p-1 rounded-2xl w-fit">
              <button
                onClick={() => setActiveTab('sessions')}
                className={cn(
                  "px-6 py-2.5 rounded-xl text-sm font-bold transition-all",
                  activeTab === 'sessions' ? "bg-white text-academic-900 shadow-sm" : "text-slate-400 hover:text-slate-700"
                )}
              >
                <span className="flex items-center gap-2"><Calendar size={15} /> Session History</span>
              </button>
              <button
                onClick={() => setActiveTab('assistant')}
                className={cn(
                  "px-6 py-2.5 rounded-xl text-sm font-bold transition-all",
                  activeTab === 'assistant' ? "bg-white text-academic-900 shadow-sm" : "text-slate-400 hover:text-slate-700"
                )}
              >
                <span className="flex items-center gap-2"><Sparkles size={15} /> AI Assistant</span>
              </button>
            </div>

            {/* Session History Tab */}
            {activeTab === 'sessions' && (
            <section className="space-y-8">
               <div className="flex items-center justify-between border-b border-slate-100 pb-4">
                 <h3 className="text-xl font-bold flex items-center gap-2">
                    <Calendar size={22} className="text-academic-500" />
                    Session History
                 </h3>
                 <button className="text-academic-900 font-bold text-xs uppercase tracking-widest hover:underline">Download Archive</button>
               </div>

               <div className="space-y-4">
                  {meetings.length > 0 ? meetings.map((session, i) => (
                    <motion.div 
                      key={session.id}
                      initial={{ opacity: 0, y: 10 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: i * 0.05 }}
                      onClick={() => { setSelectedMeeting(session); setMeetingDetailTab('summary'); }}
                      className="bg-white border border-slate-100 rounded-3xl p-8 flex items-center justify-between hover:shadow-2xl hover:border-academic-900/10 transition-all cursor-pointer group relative"
                    >
                      {/* Delete button */}
                      <button
                        onClick={(e) => handleDeleteMeeting(session, e)}
                        className="absolute top-6 right-6 opacity-0 group-hover:opacity-100 transition-opacity p-2 hover:bg-red-50 rounded-xl text-slate-400 hover:text-red-500"
                        title="Delete meeting"
                      >
                        <Trash2 size={16} />
                      </button>

                      <div className="flex items-center gap-8">
                        <div className="text-center w-16 px-2 py-4 bg-slate-50 rounded-2xl border border-slate-100 shadow-inner group-hover:bg-academic-50 transition-colors">
                           <p className="text-[10px] font-bold text-slate-400 uppercase tracking-tighter">{new Date(session.date).toLocaleString('default', { month: 'short' })}</p>
                           <p className="text-xl font-bold text-slate-900 tracking-tighter">{new Date(session.date).getDate()}</p>
                        </div>
                        <div className="space-y-2">
                          <h4 className="font-bold text-slate-900 text-lg group-hover:text-academic-900 transition-colors">{session.title}</h4>
                          <div className="flex items-center gap-3">
                            <p className="text-xs text-slate-500 line-clamp-1 max-w-sm">{session.summary || 'Synopsizing pending...'}</p>
                          </div>
                        </div>
                      </div>
                      <div className="flex items-center gap-8">
                        <div className="flex flex-col items-end">
                           <span className="text-[10px] uppercase font-mono tracking-widest text-slate-400">Recorded</span>
                           <span className="text-xs font-bold text-slate-900">{new Date(session.date).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                        </div>
                        <ChevronRight size={24} className="text-slate-200 group-hover:text-academic-900 group-hover:translate-x-1 transition-all" />
                      </div>
                    </motion.div>
                  )) : (
                    <div className="py-20 bg-slate-50 rounded-3xl border-2 border-dashed border-slate-200 text-center space-y-4">
                      <Clock size={48} className="text-slate-200 mx-auto" />
                      <div className="space-y-1">
                        <h4 className="font-bold text-slate-900">No sessions recorded yet</h4>
                        <p className="text-xs text-slate-500">MeetMind AI will index your first sync here.</p>
                      </div>
                    </div>
                  )}
               </div>
            </section>
            )}

            {/* AI Assistant Tab */}
            {activeTab === 'assistant' && (
            <section className="space-y-0">
              <div className="bg-white rounded-3xl border border-slate-100 shadow-sm flex flex-col overflow-hidden" style={{ height: '560px' }}>
                {/* Chat header */}
                <div className="flex items-center gap-3 px-8 py-5 border-b border-slate-50 bg-slate-50/50">
                  <div className="w-9 h-9 rounded-xl bg-academic-900 flex items-center justify-center">
                    <Sparkles size={17} className="text-white" />
                  </div>
                  <div>
                    <p className="text-sm font-bold text-slate-900">Project AI Assistant</p>
                    <p className="text-[10px] text-slate-400 font-medium">Scoped to <span className="text-academic-900">{project.name}</span></p>
                  </div>
                </div>

                {/* Messages */}
                <div ref={scrollRef} className="flex-1 overflow-y-auto p-8 space-y-6">
                  <AnimatePresence mode="popLayout">
                    {messages.map((msg, i) => (
                      <motion.div
                        key={i}
                        initial={{ opacity: 0, y: 8 }}
                        animate={{ opacity: 1, y: 0 }}
                        className={cn("flex gap-4", msg.role === 'user' ? "flex-row-reverse" : "")}
                      >
                        <div className={cn(
                          "w-8 h-8 rounded-xl flex items-center justify-center shrink-0",
                          msg.role === 'assistant' ? "bg-academic-900 text-white" : "bg-slate-100 text-slate-400"
                        )}>
                          {msg.role === 'assistant' ? <Sparkles size={15} /> : <User size={15} />}
                        </div>
                        <div className={cn(
                          "max-w-[75%] px-5 py-4 rounded-2xl text-sm leading-relaxed",
                          msg.role === 'assistant'
                            ? "bg-slate-50 text-slate-700 rounded-tl-none"
                            : "bg-academic-900 text-white rounded-tr-none font-medium"
                        )}>
                          {msg.content}
                        </div>
                      </motion.div>
                    ))}
                    {isTyping && (
                      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="flex gap-4">
                        <div className="w-8 h-8 rounded-xl bg-academic-900 text-white flex items-center justify-center shrink-0">
                          <Sparkles size={15} className="animate-pulse" />
                        </div>
                        <div className="bg-slate-50 px-5 py-4 rounded-2xl rounded-tl-none">
                          <span className="flex gap-1">
                            <span className="w-1.5 h-1.5 bg-slate-300 rounded-full animate-bounce" style={{ animationDelay: '0s' }} />
                            <span className="w-1.5 h-1.5 bg-slate-300 rounded-full animate-bounce" style={{ animationDelay: '0.2s' }} />
                            <span className="w-1.5 h-1.5 bg-slate-300 rounded-full animate-bounce" style={{ animationDelay: '0.4s' }} />
                          </span>
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>

                {/* Input */}
                <div className="p-6 border-t border-slate-50">
                  <form onSubmit={handleAiSend} className="relative">
                    <input
                      type="text"
                      value={aiInput}
                      onChange={e => setAiInput(e.target.value)}
                      placeholder={`Ask about ${project.name}...`}
                      className="w-full pl-5 pr-16 py-4 bg-slate-50 border border-slate-100 rounded-2xl text-sm focus:bg-white focus:ring-2 focus:ring-academic-900/10 transition-all"
                    />
                    <button
                      type="submit"
                      disabled={isTyping || !aiInput.trim()}
                      className="absolute right-2 top-1/2 -translate-y-1/2 w-10 h-10 bg-academic-900 text-white rounded-xl flex items-center justify-center hover:bg-academic-800 disabled:opacity-40 transition-all"
                    >
                      <Send size={16} />
                    </button>
                  </form>
                </div>
              </div>
            </section>
            )}

          </div>

          {/* Sidebar Area */}
          <div className="space-y-10">
             <section className="space-y-6">
                <h4 className="text-[10px] font-bold text-slate-400 uppercase tracking-[0.2em] border-b border-slate-100 pb-2">Research Team</h4>
                <div className="flex -space-x-3 overflow-hidden ml-1">
                  <div className="inline-block h-10 w-10 rounded-2xl ring-4 ring-white bg-academic-900 flex items-center justify-center text-[10px] font-bold text-white shadow-lg">
                     {user.displayName?.charAt(0)}
                  </div>
                  {project.members.map((m, i) => (
                    <div key={i} className="inline-block h-10 w-10 rounded-2xl ring-4 ring-white bg-slate-200 flex items-center justify-center text-[10px] font-bold text-slate-600 shadow-md">
                       U
                    </div>
                  ))}
                  <button className="flex items-center justify-center h-10 w-10 rounded-2xl ring-4 ring-white bg-slate-50 text-slate-400 text-xs font-bold border border-slate-200 hover:bg-slate-100 transition-colors">
                    +
                  </button>
                </div>
             </section>

             <section className="space-y-4">
                <h4 className="text-[10px] font-bold text-slate-400 uppercase tracking-[0.2em] border-b border-slate-100 pb-2">PDF Documents</h4>

                {/* Drop zone */}
                <div
                  onDragOver={e => { e.preventDefault(); setIsDragOver(true); }}
                  onDragLeave={() => setIsDragOver(false)}
                  onDrop={e => { e.preventDefault(); setIsDragOver(false); handleUpload(e.dataTransfer.files); }}
                  onClick={() => fileInputRef.current?.click()}
                  className={cn(
                    'border-2 border-dashed rounded-2xl p-5 text-center cursor-pointer transition-all',
                    isDragOver ? 'border-academic-900 bg-academic-50' : 'border-slate-200 hover:border-academic-400 hover:bg-slate-50'
                  )}
                >
                  <Upload size={20} className={cn('mx-auto mb-2', isDragOver ? 'text-academic-900' : 'text-slate-300')} />
                  <p className="text-xs font-bold text-slate-400">Drop PDF here</p>
                  <p className="text-[10px] text-slate-300 mt-0.5">or click to browse</p>
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept="application/pdf"
                    multiple
                    className="hidden"
                    onChange={e => handleUpload(e.target.files)}
                  />
                </div>

                {/* Upload progress */}
                {Object.entries(uploadProgress).map(([name, pct]) => (
                  <div key={name} className="bg-slate-50 rounded-xl p-3 space-y-1.5">
                    <div className="flex items-center justify-between">
                      <span className="text-[11px] font-bold text-slate-600 truncate max-w-[140px]">{name}</span>
                      <span className="text-[10px] font-bold text-academic-900">{pct}%</span>
                    </div>
                    <div className="w-full bg-slate-200 rounded-full h-1.5">
                      <div className="bg-academic-900 h-1.5 rounded-full transition-all" style={{ width: `${pct}%` }} />
                    </div>
                  </div>
                ))}

                {/* File list */}
                <div className="space-y-2">
                  {files.map(file => (
                    <div key={file.id} className="flex items-center gap-3 p-3 bg-white border border-slate-100 rounded-2xl shadow-sm group hover:border-academic-900/20 hover:shadow-md transition-all">
                      <div className="w-8 h-8 bg-red-50 rounded-lg flex items-center justify-center shrink-0">
                        <FileText size={15} className="text-red-400" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <p className="text-xs font-bold text-slate-700 truncate">{file.name}</p>
                        <p className="text-[10px] text-slate-400">{(file.size / 1024).toFixed(0)} KB</p>
                      </div>
                      <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                        <a
                          href={file.downloadURL}
                          target="_blank"
                          rel="noopener noreferrer"
                          onClick={e => e.stopPropagation()}
                          className="p-1.5 text-slate-400 hover:text-academic-900 hover:bg-slate-100 rounded-lg transition-all"
                        >
                          <ExternalLink size={13} />
                        </a>
                        <button
                          onClick={() => handleDeleteFile(file)}
                          className="p-1.5 text-slate-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-all"
                        >
                          <Trash2 size={13} />
                        </button>
                      </div>
                    </div>
                  ))}
                  {files.length === 0 && Object.keys(uploadProgress).length === 0 && (
                    <p className="text-[11px] text-slate-300 text-center py-2">No documents uploaded yet</p>
                  )}
                </div>
             </section>

             <div className="p-8 bg-slate-900 rounded-[32px] text-white space-y-6 shadow-massive relative overflow-hidden group">
               <div className="absolute top-0 right-0 w-32 h-32 bg-academic-900 rounded-full blur-3xl opacity-50 -translate-y-1/2 translate-x-1/2 group-hover:opacity-80 transition-opacity" />
               <div className="flex items-center gap-3">
                 <Sparkles size={20} className="text-accent-gold" />
                 <h4 className="font-bold tracking-tight">MeetMind Performance Audit</h4>
               </div>
               <p className="text-[11px] text-slate-400 leading-relaxed font-medium">
                 Analysis of the last {meetings.length} syncs shows a high correlation between discussed milestones and task completion. Task velocity is up {taskVelocity}% this period.
               </p>
               <button 
                 onClick={() => navigate('/tasks')}
                 className="w-full py-3 bg-white/5 hover:bg-white/10 transition-all rounded-xl text-[10px] font-bold uppercase tracking-widest border border-white/10"
               >
                 View Action Center
               </button>
             </div>
          </div>

        </div>
      </div>

      {/* Meeting Detail Drawer */}
      <AnimatePresence>
        {selectedMeeting && (
          <>
            {/* Backdrop */}
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setSelectedMeeting(null)}
              className="fixed inset-0 bg-slate-900/40 backdrop-blur-sm z-40"
            />
            {/* Panel */}
            <motion.div
              initial={{ x: '100%' }}
              animate={{ x: 0 }}
              exit={{ x: '100%' }}
              transition={{ type: 'spring', damping: 30, stiffness: 300 }}
              className="fixed right-0 top-0 h-full w-full max-w-2xl bg-white shadow-2xl z-50 flex flex-col"
            >
              {/* Panel Header */}
              <div className="flex items-start justify-between p-8 border-b border-slate-100 shrink-0">
                <div className="space-y-1">
                  <p className="text-[10px] font-bold uppercase tracking-widest text-slate-400">
                    {new Date(selectedMeeting.date).toLocaleDateString(undefined, { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })}
                  </p>
                  <h2 className="text-xl font-bold text-slate-900">{selectedMeeting.title}</h2>
                </div>
                <button
                  onClick={() => setSelectedMeeting(null)}
                  className="p-2 text-slate-400 hover:bg-slate-100 hover:text-slate-700 rounded-xl transition-all"
                >
                  <X size={20} />
                </button>
              </div>

              {/* Tabs */}
              <div className="flex gap-1 bg-slate-50 p-1 mx-8 mt-6 rounded-2xl shrink-0">
                {([
                  { key: 'summary', label: 'AI Summary', icon: <Sparkles size={13} /> },
                  { key: 'actions', label: 'Action Items', icon: <ListChecks size={13} /> },
                  { key: 'transcript', label: 'Full Transcript', icon: <AlignLeft size={13} /> },
                ] as const).map(tab => (
                  <button
                    key={tab.key}
                    onClick={() => setMeetingDetailTab(tab.key)}
                    className={cn(
                      'flex-1 flex items-center justify-center gap-1.5 py-2.5 rounded-xl text-xs font-bold transition-all',
                      meetingDetailTab === tab.key ? 'bg-white text-academic-900 shadow-sm' : 'text-slate-400 hover:text-slate-700'
                    )}
                  >
                    {tab.icon} {tab.label}
                  </button>
                ))}
              </div>

              {/* Tab Content */}
              <div className="flex-1 overflow-y-auto px-8 py-6">

                {/* AI Summary */}
                {meetingDetailTab === 'summary' && (
                  <div className="space-y-4">
                    <div className="flex items-center gap-2 mb-2">
                      <div className="w-7 h-7 rounded-lg bg-academic-900 flex items-center justify-center">
                        <Sparkles size={14} className="text-white" />
                      </div>
                      <span className="text-[10px] font-bold uppercase tracking-widest text-slate-400">MeetMind AI Summary</span>
                    </div>
                    {selectedMeeting.summary ? (
                      <div className="bg-slate-50 rounded-2xl p-6 text-sm text-slate-700 leading-relaxed whitespace-pre-wrap border border-slate-100">
                        {selectedMeeting.summary}
                      </div>
                    ) : (
                      <div className="py-16 flex flex-col items-center justify-center gap-3 text-center bg-slate-50 rounded-2xl border-2 border-dashed border-slate-200">
                        <Sparkles size={32} className="text-slate-200" />
                        <p className="text-sm font-bold text-slate-400">No AI summary generated yet</p>
                        <p className="text-xs text-slate-400">Summary is created automatically after session ends.</p>
                      </div>
                    )}
                  </div>
                )}

                {/* Action Items */}
                {meetingDetailTab === 'actions' && (
                  <div className="space-y-4">
                    <div className="flex items-center gap-2 mb-2">
                      <div className="w-7 h-7 rounded-lg bg-academic-900 flex items-center justify-center">
                        <ListChecks size={14} className="text-white" />
                      </div>
                      <span className="text-[10px] font-bold uppercase tracking-widest text-slate-400">Action Items from this session</span>
                    </div>
                    {meetingActions.length > 0 ? meetingActions.map((item, i) => (
                      <motion.div
                        key={item.id}
                        initial={{ opacity: 0, y: 6 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: i * 0.05 }}
                        className="bg-white border border-slate-100 rounded-2xl p-5 flex items-start gap-4 shadow-sm"
                      >
                        <div className={cn(
                          'mt-0.5 shrink-0',
                          item.status === 'completed' ? 'text-emerald-500' : item.status === 'overdue' ? 'text-red-400' : 'text-slate-300'
                        )}>
                          {item.status === 'completed' ? <CheckCircle2 size={18} /> : item.status === 'overdue' ? <AlertCircle size={18} /> : <Circle size={18} />}
                        </div>
                        <div className="flex-1 min-w-0">
                          <p className={cn('text-sm font-semibold', item.status === 'completed' && 'line-through text-slate-400')}>{item.task}</p>
                          <div className="flex items-center gap-3 mt-1">
                            <span className="text-[10px] text-slate-400 font-medium">{item.assignee}</span>
                            {item.deadline && (
                              <span className="text-[10px] text-slate-400">
                                Due {new Date(item.deadline).toLocaleDateString()}
                              </span>
                            )}
                          </div>
                        </div>
                        <span className={cn(
                          'text-[10px] font-bold uppercase tracking-widest px-3 py-1 rounded-full',
                          item.status === 'completed' ? 'bg-emerald-50 text-emerald-600' :
                          item.status === 'overdue' ? 'bg-red-50 text-red-500' : 'bg-slate-100 text-slate-400'
                        )}>{item.status}</span>
                      </motion.div>
                    )) : (
                      <div className="py-16 flex flex-col items-center justify-center gap-3 text-center bg-slate-50 rounded-2xl border-2 border-dashed border-slate-200">
                        <ListChecks size={32} className="text-slate-200" />
                        <p className="text-sm font-bold text-slate-400">No action items for this session</p>
                      </div>
                    )}
                  </div>
                )}

                {/* Full Transcript */}
                {meetingDetailTab === 'transcript' && (
                  <div className="space-y-4">
                    <div className="flex items-center gap-2 mb-2">
                      <div className="w-7 h-7 rounded-lg bg-academic-900 flex items-center justify-center">
                        <AlignLeft size={14} className="text-white" />
                      </div>
                      <span className="text-[10px] font-bold uppercase tracking-widest text-slate-400">Full Transcript</span>
                    </div>
                    {selectedMeeting.transcript && selectedMeeting.transcript.length > 0 ? (
                      <div className="space-y-3">
                        {selectedMeeting.transcript.map((entry, i) => (
                          <div key={i} className={cn(
                            'flex gap-3 p-4 rounded-2xl text-sm',
                            entry.isCommand ? 'bg-academic-50 border border-academic-200' : 'bg-slate-50'
                          )}>
                            <div className="shrink-0 mt-0.5">
                              {entry.isCommand ? (
                                <span className="inline-flex items-center justify-center w-6 h-6 rounded-md bg-academic-900 text-white">
                                  <Sparkles size={11} />
                                </span>
                              ) : (
                                <span className="inline-flex items-center justify-center w-6 h-6 rounded-md bg-slate-200 text-slate-500 text-[10px] font-bold">
                                  {entry.speaker.charAt(0)}
                                </span>
                              )}
                            </div>
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-2 mb-1">
                                <span className="text-[11px] font-bold text-slate-700">{entry.speaker}</span>
                                <span className="text-[10px] text-slate-300 font-mono">
                                  {new Date(entry.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                                </span>
                                {entry.language && entry.language !== 'en' && (
                                  <span className="text-[9px] font-bold uppercase tracking-widest px-1.5 py-0.5 bg-slate-200 text-slate-500 rounded">{entry.language}</span>
                                )}
                              </div>
                              <p className="text-slate-600 leading-relaxed">{entry.text}</p>
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div className="py-16 flex flex-col items-center justify-center gap-3 text-center bg-slate-50 rounded-2xl border-2 border-dashed border-slate-200">
                        <AlignLeft size={32} className="text-slate-200" />
                        <p className="text-sm font-bold text-slate-400">No transcript available</p>
                        <p className="text-xs text-slate-400">Transcript is recorded live during the session.</p>
                      </div>
                    )}
                  </div>
                )}

              </div>
            </motion.div>
          </>
        )}
      </AnimatePresence>
    </div>
  );
}

function StatCard({ icon, label, value }: { icon: ReactNode, label: string, value: string }) {
  return (
    <div className="bg-white border border-slate-100 rounded-3xl p-6 shadow-sm hover:shadow-xl transition-all border-b-4 border-b-academic-900/5">
      <div className="flex items-center gap-2 text-academic-500 mb-2">
        {icon}
        <span className="text-[10px] font-bold uppercase tracking-widest text-slate-400">{label}</span>
      </div>
      <p className="text-3xl font-bold text-slate-900 tracking-tighter">{value}</p>
    </div>
  );
}
