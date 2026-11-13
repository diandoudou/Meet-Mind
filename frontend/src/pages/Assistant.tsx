import React, { useState, useRef, useEffect, FormEvent } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { 
  Sparkles, 
  Send, 
  Bot, 
  User, 
  Plus, 
  Loader2,
} from 'lucide-react';
import { useFirebase } from '../context/FirebaseContext';
import { ragChat, type RagCitation } from '../services/ai';
import { cn } from '../lib/utils';
import { useNavigate } from 'react-router-dom';

export default function Assistant() {
  const navigate = useNavigate();
  const { user } = useFirebase();
  const [messages, setMessages] = useState<{ role: 'user' | 'assistant', content: string, citations?: RagCitation[] }[]>([
    { role: 'assistant', content: "Hello! I'm MeetMind with RAG-powered knowledge retrieval. Ask me about your meetings and documents across all projects." }
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
    if (!input.trim() || isTyping || !user) return;

    const userMsg = input.trim();
    setInput('');
    setMessages(prev => [...prev, { role: 'user', content: userMsg }]);
    setIsTyping(true);

    try {
      const response = await ragChat({
        message: userMsg,
        ownerUid: user.uid,
      });
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: response.answer,
        citations: response.citations,
      }]);
    } catch (error) {
      console.error("Assistant Error:", error);
      setMessages(prev => [...prev, { role: 'assistant', content: "I couldn't reach the knowledge base. Ensure the backend is running and you've indexed meetings or PDFs." }]);
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
             <p className="text-slate-500">RAG search across all your indexed meetings and PDFs.</p>
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
                  className={cn("flex gap-4", msg.role === 'user' ? "flex-row-reverse" : "")}
                >
                  <div className={cn(
                    "w-10 h-10 rounded-2xl flex items-center justify-center shrink-0",
                    msg.role === 'assistant' ? "bg-academic-900 text-white" : "bg-slate-100 text-slate-400"
                  )}>
                    {msg.role === 'assistant' ? <Sparkles size={18} /> : <User size={18} />}
                  </div>
                  <div className={cn(
                    "max-w-[80%] px-6 py-4 rounded-3xl text-sm leading-relaxed space-y-3",
                    msg.role === 'assistant' ? "bg-slate-50 text-slate-700 rounded-tl-none" : "bg-academic-900 text-white rounded-tr-none"
                  )}>
                    <p className="whitespace-pre-wrap">{msg.content}</p>
                    {msg.citations && msg.citations.length > 0 && (
                      <div className="pt-2 border-t border-slate-200 space-y-2">
                        {msg.citations.map(cite => (
                          <button
                            key={cite.chunk_id}
                            type="button"
                            onClick={() => cite.url_path && navigate(cite.url_path.split('?')[0])}
                            className="block w-full text-left p-2 bg-white border border-slate-100 rounded-xl text-xs hover:border-academic-900/20"
                          >
                            <span className="font-bold text-academic-900">{cite.label}</span> {cite.source_title}
                          </button>
                        ))}
                      </div>
                    )}
                  </div>
                </motion.div>
              ))}
              {isTyping && (
                <div className="flex gap-4 items-center text-slate-400 text-sm">
                  <Loader2 size={16} className="animate-spin" /> Searching knowledge base...
                </div>
              )}
            </AnimatePresence>
          </div>

          <form onSubmit={handleSend} className="p-8 border-t border-slate-50">
            <div className="relative">
              <input
                type="text"
                value={input}
                onChange={e => setInput(e.target.value)}
                placeholder="Ask about decisions, parameters, or past meetings..."
                className="w-full pl-6 pr-16 py-5 bg-slate-50 border border-slate-100 rounded-[24px] focus:bg-white focus:ring-2 focus:ring-academic-900/10 transition-all font-medium"
              />
              <button
                type="submit"
                disabled={isTyping || !user}
                className="absolute right-3 top-1/2 -translate-y-1/2 w-12 h-12 bg-academic-900 text-white rounded-2xl flex items-center justify-center hover:bg-academic-800 transition-all disabled:opacity-50"
              >
                <Send size={18} />
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}
