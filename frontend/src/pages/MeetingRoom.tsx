import { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { 
  Play, 
  Square, 
  Mic, 
  Radio, 
  MessageSquare, 
  Sparkles,
  User,
  MoreVertical,
  Terminal,
  Save,
  Share2,
  CheckCircle2,
  Loader2,
  ChevronDown,
  ChevronRight,
  ArrowLeft,
  Folder,
  FileText,
  AlertCircle,
  Clock,
  Wifi,
  WifiOff,
  Languages
} from 'lucide-react';
import { cn } from '../lib/utils';
import { TranscriptEntry, Project, ActionItem } from '../types';
import { extractActionItems } from '../services/ai';
import { useFirebase } from '../context/FirebaseContext';
import { collection, doc, setDoc, query, where, getDocs, limit, addDoc } from 'firebase/firestore';
import { db, handleFirestoreError, OperationType } from '../firebase';

const API_URL = import.meta.env.VITE_BACKEND_URL || 'http://localhost:8765';
const WS_URL = `${API_URL.replace(/^http/, 'ws')}/ws`;

export default function MeetingRoom() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { user } = useFirebase();
  const [projectId, setProjectId] = useState<string | null>(searchParams.get('projectId'));
  const [projects, setProjects] = useState<Project[]>([]);
  const [isRecording, setIsRecording] = useState(false);
  const [isSummarizing, setIsSummarizing] = useState(false);
  const [summary, setSummary] = useState<string | null>(null);
  const [transcript, setTranscript] = useState<TranscriptEntry[]>([]);
  const [lastActions, setLastActions] = useState<ActionItem[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);
  const [meetingId] = useState(`mtg-${Date.now()}`);
  const [wsConnected, setWsConnected] = useState(false);
  const [agentStatus, setAgentStatus] = useState<string>('Idle');
  const wsRef = useRef<WebSocket | null>(null);

  // Translation function using Gemini
  const translateToEnglish = async (index: number, text: string) => {
    // Set translating state
    setTranscript(prev => prev.map((item, i) => 
      i === index ? { ...item, isTranslating: true } : item
    ));

    try {
      const { GoogleGenAI } = await import('@google/genai');
      const apiKey = import.meta.env.VITE_GEMINI_API_KEY;
      if (!apiKey) {
        setTranscript(prev => prev.map((item, i) => 
          i === index ? { ...item, translation: 'Gemini API key not configured', isTranslating: false } : item
        ));
        return;
      }

      const ai = new GoogleGenAI({ apiKey });
      
      const result = await ai.models.generateContent({
        model: 'gemini-2.0-flash-exp',
        contents: `Translate the following text to English. Only return the translation, nothing else:\n\n${text}`,
      });

      const translation = result.text || 'Translation failed';

      // Update with translation
      setTranscript(prev => prev.map((item, i) => 
        i === index ? { ...item, translation, isTranslating: false } : item
      ));
    } catch (error) {
      console.error('Translation error:', error);
      setTranscript(prev => prev.map((item, i) => 
        i === index ? { ...item, translation: 'Translation error', isTranslating: false } : item
      ));
    }
  };

  // WebSocket connection
  useEffect(() => {
    const ws = new WebSocket(WS_URL);
    wsRef.current = ws;

    ws.onopen = () => {
      setWsConnected(true);
      setAgentStatus('Connected');
      console.log('[WS] Connected to MeetingAssistant');
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        console.log('[WS] Message:', data);

        switch (data.type) {
          case 'connected':
            setAgentStatus('Ready');
            break;
          case 'transcript':
            setTranscript(prev => [...prev, {
              speaker: data.speaker || 'Unknown',
              text: data.text,
              timestamp: new Date(data.timestamp).getTime(),
              language: data.language || 'mixed'
            }]);
            break;
          case 'interim':
            // Real-time text update - could show in UI
            break;
          case 'summary_update':
            setSummary(data.summary);
            break;
          case 'status':
            setAgentStatus(data.message);
            break;
          case 'error':
            console.error('[WS] Error:', data.message);
            setAgentStatus(`Error: ${data.message}`);
            break;
        }
      } catch (err) {
        console.error('[WS] Parse error:', err);
      }
    };

    ws.onerror = (err) => {
      console.error('[WS] Error:', err);
      setWsConnected(false);
      setAgentStatus('Connection Error');
    };

    ws.onclose = () => {
      setWsConnected(false);
      setAgentStatus('Disconnected');
      console.log('[WS] Disconnected');
    };

    return () => {
      ws.close();
    };
  }, []);

  // Fetch projects and context
  useEffect(() => {
    if (!user) return;
    const q = query(collection(db, 'projects'), where('ownerUid', '==', user.uid));
    getDocs(q).then(snap => {
      setProjects(snap.docs.map(d => ({ ...d.data(), id: d.id } as Project)));
    });
  }, [user]);

  // Fetch contextual briefing (last meeting's pending tasks)
  useEffect(() => {
    if (!projectId || !user) return;
    const q = query(
      collection(db, 'projects', projectId, 'actionItems'), 
      where('status', '==', 'pending'),
      limit(5)
    );
    getDocs(q).then(snap => {
      setLastActions(snap.docs.map(d => ({ ...d.data(), id: d.id } as ActionItem)));
    });
  }, [projectId, user]);

  // Auto-scroll to bottom when new transcript arrives
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [transcript]);

  // Ensure backend listening stops if user leaves page mid-session
  useEffect(() => {
    return () => {
      if (isRecording) {
        fetch(`${API_URL}/stop`, { method: 'POST' }).catch(() => undefined);
      }
    };
  }, [isRecording]);

  const handleToggleRecording = async () => {
    if (!projectId) return;

    if (isRecording) {
      // Stop recording
      setIsRecording(false);
      setIsSummarizing(true);
      setAgentStatus('Stopping recording...');

      try {
        const response = await fetch(`${API_URL}/stop`, { method: 'POST' });
        if (!response.ok) {
          const errorText = await response.text();
          throw new Error(errorText || 'Stop API failed');
        }
        const data = await response.json();

        setSummary(data.summary || 'No summary generated');
        
        // Use transcript from backend or fallback to local
        const finalTranscript = data.transcript && data.transcript.length > 0 
          ? data.transcript.map((t: any) => ({
              speaker: t.speaker,
              text: t.text,
              timestamp: new Date(t.timestamp).getTime(),
              language: t.language || 'mixed'
            }))
          : transcript;

        // Save meeting to Firestore
        const mtgRef = doc(db, 'projects', projectId, 'meetings', meetingId);
        await setDoc(mtgRef, {
          id: meetingId,
          projectId,
          title: `Meeting ${new Date().toLocaleDateString()}`,
          date: Date.now(),
          summary: data.summary || '',
          transcript: finalTranscript,
          authorUid: user?.uid
        });

        // Extract and save action items
        const rawActions = await extractActionItems(finalTranscript, projectId, meetingId);
        for (const action of rawActions) {
          await addDoc(collection(db, 'projects', projectId, 'actionItems'), {
            ...action,
            createdAt: Date.now()
          });
        }

        setAgentStatus('Meeting saved');
      } catch (e) {
        console.error('Stop recording error:', e);
        setAgentStatus('Error stopping recording');
        // Do not throw here: recording should still be considered stopped
      } finally {
        setIsSummarizing(false);
      }
    } else {
      // Start recording
      setIsRecording(true);
      setSummary(null);
      setTranscript([]);
      setAgentStatus('Starting recording...');

      try {
        const response = await fetch(`${API_URL}/start`, { method: 'POST' });
        if (!response.ok) {
          const errorText = await response.text();
          throw new Error(errorText || 'Start API failed');
        }
        const data = await response.json();
        setAgentStatus(data.status === 'started' ? 'Recording... Speak now' : 'Agent already running');
      } catch (e) {
        console.error('Start recording error:', e);
        const msg = e instanceof Error ? e.message : 'Failed to start - check backend .env and API keys';
        setAgentStatus(msg);
        setIsRecording(false);
      }
    }
  };

  if (!projectId) {
    return (
      <div className="h-full flex flex-col items-center justify-center p-8 bg-slate-50 text-center space-y-8">
        <div className="w-24 h-24 bg-academic-900 rounded-[40px] flex items-center justify-center text-white shadow-massive">
          <Folder size={40} />
        </div>
        <div className="space-y-4 max-w-md">
          <h2 className="text-3xl font-bold text-slate-900">Prepare Session</h2>
          <p className="text-slate-500 text-lg opacity-80">
            Select an academic project space to begin intelligent transcription and Ella AI assistance.
          </p>
        </div>
        <div className="w-full max-w-xs space-y-2">
          {projects.length > 0 ? (
            projects.map(p => (
              <button 
                key={p.id}
                onClick={() => setProjectId(p.id)}
                className="w-full p-4 bg-white border border-slate-200 rounded-2xl flex items-center justify-between group hover:border-academic-900 transition-all font-bold text-slate-700"
              >
                <div className="flex items-center gap-3">
                  <div className="w-2 h-2 rounded-full" style={{ backgroundColor: p.color }} />
                  {p.name}
                </div>
                <ChevronRight size={16} className="text-slate-300 group-hover:text-academic-900 group-hover:translate-x-1 transition-all" />
              </button>
            ))
          ) : (
            <div className="p-10 bg-white border border-dashed border-slate-200 rounded-3xl space-y-4">
              <p className="text-xs text-slate-400 font-mono uppercase tracking-widest">No active spacesfound</p>
              <button onClick={() => navigate('/')} className="px-6 py-2 bg-slate-900 text-white rounded-full text-[10px] font-bold uppercase tracking-widest">Create Space</button>
            </div>
          )}
        </div>
      </div>
    );
  }

  const activeProject = projects.find(p => p.id === projectId);

  return (
    <div className="h-full flex flex-col bg-slate-100">
      {/* Connection Status Banner */}
      <div className={cn(
        "text-white px-4 py-1.5 text-[10px] font-bold uppercase tracking-widest text-center flex items-center justify-center gap-2",
        wsConnected ? "bg-academic-900" : "bg-red-500"
      )}>
        {wsConnected ? <Wifi size={12} /> : <WifiOff size={12} />}
        {wsConnected ? `MeetingAssistant Connected • ${agentStatus}` : 'Backend Disconnected - Check http://localhost:8765'}
      </div>

      <div className="flex-1 flex overflow-hidden">
        {/* Left Side: Transcription Area */}
        <div className="flex-1 flex flex-col min-w-0 bg-white">
          <div className="p-8 border-b border-slate-100 flex items-center justify-between bg-white z-10">
            <div className="flex items-center gap-6">
              <button
                onClick={() => navigate(projectId ? `/project/${projectId}` : '/')}
                className="flex items-center gap-2 px-3 py-2 rounded-xl border border-slate-200 text-slate-600 hover:bg-slate-50 hover:text-academic-900 transition-all text-xs font-bold"
                title="返回项目页"
              >
                <ArrowLeft size={14} />
                返回
              </button>
              <div className="space-y-1">
                <div className="flex items-center gap-3">
                   <h2 className="text-2xl font-bold text-slate-900 tracking-tight">Session Workspace</h2>
                   <div className="px-2 py-0.5 bg-slate-100 rounded text-[9px] font-bold text-slate-500 uppercase tracking-widest">{activeProject?.name}</div>
                </div>
                <p className="text-slate-400 text-xs font-mono">ID: {meetingId}</p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <button 
                onClick={handleToggleRecording}
                disabled={isSummarizing}
                className={cn(
                  "flex items-center gap-3 px-8 py-3 rounded-2xl font-bold transition-all disabled:opacity-50 text-sm shadow-massive",
                  isRecording 
                    ? "bg-slate-100 text-slate-600 hover:bg-slate-200" 
                    : "bg-academic-900 text-white hover:bg-academic-800"
                )}
              >
                {isSummarizing ? <Loader2 size={18} className="animate-spin text-white" /> : (isRecording ? <Square size={18} /> : <Play size={18} />)}
                {isSummarizing ? "Processing Session..." : (isRecording ? "Finish" : "Start Session")}
              </button>
            </div>
          </div>

          {/* Transcription Feed & Summary */}
          <div ref={scrollRef} className="flex-1 overflow-y-auto p-10 space-y-10 bg-slate-50/30">
             {summary && (
               <motion.div 
                 initial={{ opacity: 0, y: 30 }}
                 animate={{ opacity: 1, y: 0 }}
                 className="p-10 bg-white border border-slate-200 rounded-[40px] shadow-2xl space-y-6 mb-12 relative overflow-hidden"
               >
                 <div className="absolute top-0 right-0 w-64 h-64 bg-academic-900/5 rounded-full blur-3xl -translate-y-1/2 translate-x-1/2" />
                 <div className="flex items-center gap-3">
                   <div className="w-10 h-10 bg-academic-900 rounded-2xl flex items-center justify-center text-white">
                    <Sparkles size={20} />
                   </div>
                   <div>
                    <h3 className="font-bold text-slate-900 text-lg">AI Synopsis</h3>
                    <p className="text-[10px] text-slate-400 font-mono uppercase tracking-widest">Verified by Academic Engine</p>
                   </div>
                 </div>
                 <div className="text-slate-700 text-sm leading-relaxed space-y-4 whitespace-pre-wrap">
                   {summary}
                 </div>
                 <div className="pt-6 border-t border-slate-100 flex items-center justify-between">
                   <button 
                     onClick={() => navigate(`/project/${projectId}`)}
                     className="flex items-center gap-2 text-academic-900 font-bold text-xs hover:gap-3 transition-all"
                   >
                      Go to Project Space <ChevronRight size={14} />
                   </button>
                   <div className="flex items-center gap-2">
                      <button className="p-2 text-slate-400 hover:text-academic-900 transition-colors"><Share2 size={16} /></button>
                      <button className="p-2 text-slate-400 hover:text-academic-900 transition-colors"><Save size={16} /></button>
                   </div>
                 </div>
               </motion.div>
             )}
             
             <div className="max-w-3xl mx-auto space-y-8">
               <AnimatePresence>
                 {transcript.map((item, i) => (
                   <motion.div 
                     key={i}
                     initial={{ opacity: 0, x: -10 }}
                     animate={{ opacity: 1, x: 0 }}
                     className={cn(
                       "flex gap-6",
                       item.isSystem ? "opacity-60" : ""
                     )}
                   >
                     <div className={cn(
                        "w-12 h-12 rounded-2xl flex-shrink-0 flex items-center justify-center shadow-inner",
                        item.speaker === 'MeetMind' ? "bg-academic-900 text-white" : "bg-white border border-slate-200"
                     )}>
                        {item.speaker === 'MeetMind' ? <Sparkles size={24} /> : <div className="text-xs font-bold text-slate-400">{item.speaker.charAt(0)}</div>}
                     </div>
                     <div className="flex-1 space-y-2">
                       <div className="flex items-center justify-between">
                         <span className="text-[10px] font-bold text-slate-900 uppercase tracking-widest">{item.speaker}</span>
                         <div className="flex items-center gap-3">
                           {!item.translation && !item.isTranslating && (
                             <button
                               onClick={() => translateToEnglish(i, item.text)}
                               className="group flex items-center gap-1.5 px-2 py-1 rounded-lg hover:bg-slate-100 transition-all"
                               title="Translate to English"
                             >
                               <Languages size={12} className="text-slate-400 group-hover:text-academic-900 transition-colors" />
                               <span className="text-[9px] font-bold text-slate-400 group-hover:text-academic-900 uppercase tracking-wider">Translate</span>
                             </button>
                           )}
                           {item.isTranslating && (
                             <div className="flex items-center gap-1.5 px-2 py-1">
                               <Loader2 size={12} className="text-academic-900 animate-spin" />
                               <span className="text-[9px] font-bold text-academic-900 uppercase tracking-wider">Translating...</span>
                             </div>
                           )}
                           <span className="text-[10px] text-slate-300 font-mono">{new Date(item.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}</span>
                         </div>
                       </div>
                       <div className={cn(
                         "p-4 rounded-2xl text-sm leading-relaxed shadow-sm relative group/message",
                         item.speaker === 'MeetMind' ? "bg-academic-50 text-academic-900 border border-academic-100" : "bg-white text-slate-700 border border-slate-100",
                         item.isCommand ? "bg-amber-50 border-amber-200" : ""
                       )}>
                         {item.text.split('->').length > 1 ? (
                           <span className="flex flex-wrap items-center gap-1">
                             {item.text.split('->')[0]}
                             <span className="px-1.5 py-0.5 bg-green-500 text-white text-[9px] font-bold rounded-full animate-pulse">Correction</span>
                             <ChevronRight size={10} className="text-slate-300" />
                             <span className="text-academic-900 font-bold underline decoration-academic-200 underline-offset-4">{item.text.split('->')[1]}</span>
                           </span>
                         ) : item.text}
                         
                         {item.isSystem && i === 1 && (
                           <div className="absolute -top-3 left-4 px-2 py-0.5 bg-academic-900 text-white text-[8px] font-bold uppercase tracking-widest rounded-full shadow-lg">
                             Context Briefing
                           </div>
                         )}
                       </div>
                       {item.translation && (
                         <motion.div
                           initial={{ opacity: 0, height: 0 }}
                           animate={{ opacity: 1, height: 'auto' }}
                           className={cn(
                             "p-4 rounded-2xl text-sm leading-relaxed shadow-sm border-2 border-dashed relative",
                             "bg-blue-50 text-blue-900 border-blue-200"
                           )}
                         >
                           <div className="absolute -top-2.5 left-4 px-2 py-0.5 bg-blue-500 text-white text-[8px] font-bold uppercase tracking-widest rounded-full shadow-md flex items-center gap-1">
                             <Languages size={10} />
                             English Translation
                           </div>
                           {item.translation}
                         </motion.div>
                       )}
                       {item.isCommand && (
                         <div className="inline-flex items-center gap-2 px-3 py-1 bg-academic-900 text-white rounded-lg text-[10px] font-bold uppercase tracking-wider ml-1 mt-1 shadow-lg shadow-academic-900/20">
                           <Terminal size={12} />
                           System Trigger: Tracking 분담
                         </div>
                       )}
                     </div>
                   </motion.div>
                 ))}
                 {!isRecording && transcript.length === 0 && !summary && (
                   <div className="py-20 flex flex-col items-center justify-center text-center space-y-6">
                      <div className="w-24 h-24 bg-slate-50 rounded-full flex items-center justify-center text-slate-200 border-2 border-dashed border-slate-100">
                        <Mic size={40} />
                      </div>
                      <div className="space-y-2">
                        <h4 className="text-xl font-bold text-slate-900">Transcript Engine Ready</h4>
                        <p className="text-slate-400 max-w-sm mx-auto">
                          Ella is prepared to capture bilingual dialogue and academic terminology corrections.
                        </p>
                      </div>
                   </div>
                 )}
               </AnimatePresence>
             </div>
          </div>
        </div>

        {/* Right Side: AI Assistant Panel */}
        <div className="w-96 border-l border-slate-200 bg-white flex flex-col shadow-2xl">
          <div className="p-8 border-b border-slate-100 flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Sparkles size={22} className="text-academic-900" />
              <h3 className="font-bold text-slate-900 tracking-tight">Ella Audit</h3>
            </div>
            <div className="w-2 h-2 rounded-full bg-academic-900" />
          </div>

          <div className="flex-1 overflow-y-auto p-8 space-y-10">
            {/* Contextual Agenda */}
            <section className="space-y-6">
              <h4 className="text-[10px] font-bold text-slate-400 uppercase tracking-[0.2em] border-b border-slate-100 pb-2">Contextual Agenda</h4>
              <ul className="space-y-4">
                {lastActions.length > 0 ? lastActions.map((task, i) => (
                  <li key={i} className="flex items-start gap-4 group">
                    <div className="w-5 h-5 rounded bg-slate-100 flex items-center justify-center text-[8px] text-slate-400 font-bold shrink-0">
                      {i + 1}
                    </div>
                    <div className="space-y-1">
                       <p className="text-[11px] text-slate-700 font-medium leading-tight group-hover:text-academic-900 transition-colors cursor-pointer capitalize">Resolve: {task.task}</p>
                       <p className="text-[9px] text-slate-400 font-mono uppercase tracking-tighter">Assigned: {task.assignee}</p>
                    </div>
                  </li>
                )) : (
                  ['Contextual Review: Last session delta', 'Live Transcribing: Academic Corr', 'Entity Extraction: Tasks & Dates'].map((item, i) => (
                    <li key={i} className="flex items-center gap-4 group">
                      <div className="w-2 h-2 rounded-full bg-academic-200" />
                      <span className="text-xs text-slate-600 font-medium group-hover:text-academic-900 transition-colors cursor-pointer">{item}</span>
                    </li>
                  ))
                )}
              </ul>
            </section>

            {/* Potential Action Items */}
            <section className="space-y-6">
              <h4 className="text-[10px] font-bold text-slate-400 uppercase tracking-[0.2em] border-b border-slate-100 pb-2">Pending Commitments</h4>
              <div className="space-y-4">
                <div className="p-6 rounded-[24px] bg-slate-50 border border-slate-100 space-y-3 shadow-inner">
                  <div className="flex items-start justify-between">
                    <p className="text-xs font-bold text-academic-900 leading-snug">MeetMind Captures: Tom - Frontend Demo</p>
                    <CheckCircle2 size={16} className="text-slate-200" />
                  </div>
                  <div className="flex items-center gap-2 text-[10px] text-slate-400 font-mono">
                    <Clock size={12} />
                    Target: Week 17
                  </div>
                </div>
              </div>
            </section>

            {/* Academic Reference */}
            <section className="space-y-6">
              <h4 className="text-[10px] font-bold text-slate-400 uppercase tracking-[0.2em] border-b border-slate-100 pb-2">References Context</h4>
              <div className="p-6 rounded-[24px] bg-academic-900/5 border border-academic-900/10 relative overflow-hidden">
                <div className="absolute top-0 right-0 p-2 opacity-10">
                   <FileText size={40} />
                </div>
                <p className="text-xs text-academic-900 leading-relaxed relative z-10">
                  "Alignment verification often requires RMSD calculations on rigid body transforms..."
                </p>
                <div className="mt-4 flex items-center gap-2 text-[10px] text-academic-900 font-bold uppercase tracking-widest relative z-10">
                  <Radio size={12} />
                  Live Sync
                </div>
              </div>
            </section>
          </div>

          <div className="p-8 border-t border-slate-100 space-y-4">
            <button 
              onClick={() => navigate(`/project/${projectId}`)}
              className="w-full flex items-center justify-center gap-3 py-4 bg-academic-900 text-white rounded-[20px] text-sm font-bold hover:bg-academic-800 transition-all shadow-massive animate-in fade-in slide-in-from-bottom-2"
            >
              <Save size={18} />
              Finalize Minutes
            </button>
            <p className="text-[10px] text-center text-slate-400">A copy will be indexed in project history.</p>
          </div>
        </div>
      </div>
    </div>
  );
}
