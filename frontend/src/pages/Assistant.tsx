import React, { useState, useRef, useEffect, FormEvent } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { 
  Sparkles, 
  Send, 
  Bot, 
  User, 
  Search, 
  Plus, 
  MessageSquare,
  ChevronRight,
  FolderOpen
} from 'lucide-react';
import { useFirebase } from '../context/FirebaseContext';
import { GoogleGenAI } from '@google/genai';
import { collection, query, where, getDocs, limit } from 'firebase/firestore';
import { db } from '../firebase';
import { cn } from '../lib/utils';

export default function Assistant() {
  const { user } = useFirebase();
  const [messages, setMessages] = useState<{ role: 'user' | 'assistant', content: string }[]>([
    { role: 'assistant', content: "Hello! I'm MeetMind, your project-centric 'Second Brain'. Ask me anything about your previous research syncs, advisor comments, or lab results." }
  ]);
  const [input, setInput] = useState('');
  const [isTyping, setIsTyping] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, isTyping]);

  const handleSend = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isTyping) return;

    const userMsg = input.trim();
    setInput('');
    setMessages(prev => [...prev, { role: 'user', content: userMsg }]);
    setIsTyping(true);

    try {
      // 1. Retrieve Context (Real RAG simulation)
      // We look for relevant meetings across all user's projects
      // This is a simplified RAG approach for this prototype
      const mtgQuery = query(collection(db, 'projects'), where('ownerUid', '==', user?.uid), limit(5));
      const projectsSnap = await getDocs(mtgQuery);
      let context = "";
      
      for (const projDoc of projectsSnap.docs) {
        const mtgsSnap = await getDocs(collection(db, 'projects', projDoc.id, 'meetings'));
        mtgsSnap.docs.forEach(d => {
            const data = d.data();
            context += `Project: ${projDoc.data().name}\nMeeting: ${data.title}\nSummary: ${data.summary}\n\n`;
        });
      }

      // 2. Call Gemini
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
          systemInstruction: `You are MeetMind, an AI student assistant optimized for academic research. 
          You have access to the user's project context below. 
          Context: ${context || 'No historical data found.'}
          
          Answer questions specifically using the provided context. 
          If you don't know the answer, say you haven't indexed that specific detail yet. 
          Keep your tone professional, encouraging, and academic.`
        }
      });

      const text = result.text || "I encountered an issue processing your request.";

      setMessages(prev => [...prev, { role: 'assistant', content: text }]);
    } catch (error) {
      console.error("Assistant Error:", error);
      setMessages(prev => [...prev, { role: 'assistant', content: "I encountered an issue retrieving your project knowledge. Please ensure your AI keys are configured." }]);
    } finally {
      setIsTyping(false);
    }
  };

  return (
    <div className="h-full flex flex-col bg-slate-50">
      <div className="flex-1 overflow-hidden flex flex-col max-w-4xl mx-auto w-full p-8 space-y-8">
        <header className="flex items-center justify-between shrink-0">
          <div className="space-y-1">
             <h2 className="text-3xl font-bold tracking-tight text-slate-900 flex items-center gap-3">
               <Bot className="text-academic-900" size={32} />
               Knowledge Retrieval Hub
             </h2>
             <p className="text-slate-500">Query your project history and academic decisions.</p>
          </div>
          <button className="flex items-center gap-2 px-4 py-2 border border-slate-200 rounded-2xl text-[10px] font-bold uppercase tracking-widest text-slate-400 hover:bg-white transition-all">
             <Plus size={14} /> New Thread
          </button>
        </header>

        <div className="flex-1 bg-white rounded-[48px] shadow-massive border border-slate-100 flex flex-col overflow-hidden">
          <div ref={scrollRef} className="flex-1 overflow-y-auto p-10 space-y-8">
            <AnimatePresence mode="popLayout">
              {messages.map((msg, i) => (
                <motion.div
                  key={i}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  className={cn(
                    "flex gap-6",
                    msg.role === 'assistant' ? "items-start" : "items-start flex-row-reverse"
                  )}
                >
                  <div className={cn(
                    "w-10 h-10 rounded-2xl flex items-center justify-center shrink-0 shadow-lg",
                    msg.role === 'assistant' ? "bg-academic-900 text-white" : "bg-slate-100 text-slate-400"
                  )}>
                    {msg.role === 'assistant' ? <Sparkles size={20} /> : <User size={20} />}
                  </div>
                  <div className={cn(
                    "max-w-[80%] p-6 rounded-[32px] text-sm leading-relaxed",
                    msg.role === 'assistant' 
                      ? "bg-slate-50 text-slate-700 rounded-tl-none font-medium" 
                      : "bg-academic-900 text-white rounded-tr-none font-bold"
                  )}>
                    {msg.content}
                  </div>
                </motion.div>
              ))}
              {isTyping && (
                <motion.div 
                  initial={{ opacity: 0 }} 
                  animate={{ opacity: 1 }}
                  className="flex gap-6"
                >
                  <div className="w-10 h-10 rounded-2xl bg-academic-900 text-white flex items-center justify-center shrink-0">
                    <Sparkles size={20} className="animate-pulse" />
                  </div>
                  <div className="bg-slate-50 p-6 rounded-[32px] rounded-tl-none">
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

          <div className="p-10 border-t border-slate-50">
            <form onSubmit={handleSend} className="relative">
              <input 
                type="text" 
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Suggest some next steps for my Thesis paper based on the last lab sync..." 
                className="w-full pl-6 pr-24 py-5 bg-slate-50 border-transparent rounded-[32px] focus:bg-white focus:ring-4 focus:ring-academic-900/5 transition-all text-sm"
              />
              <button 
                type="submit" 
                disabled={isTyping || !input.trim()}
                className="absolute right-3 top-1/2 -translate-y-1/2 w-16 h-12 bg-academic-900 text-white rounded-2xl flex items-center justify-center hover:bg-academic-800 disabled:opacity-50 transition-all shadow-lg shadow-academic-900/10"
              >
                <Send size={20} />
              </button>
            </form>
            <div className="flex justify-center gap-6 mt-6">
               <QuickTip label="What was the advisor's feedback on experimental group B?" />
               <QuickTip label="Summarize the core technical decisions from last week." />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function QuickTip({ label }: { label: string }) {
  return (
    <button className="text-[10px] text-slate-400 font-bold uppercase tracking-widest hover:text-academic-900 transition-colors flex items-center gap-2">
       <MessageSquare size={12} /> {label}
    </button>
  );
}
