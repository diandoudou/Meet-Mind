import { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { 
  CheckSquare, 
  Clock, 
  AlertCircle, 
  ChevronRight, 
  Filter, 
  Search,
  CheckCircle2,
  Calendar,
  MoreVertical,
  Loader2,
  Inbox
} from 'lucide-react';
import { useFirebase } from '../context/FirebaseContext';
import { collectionGroup, query, where, onSnapshot, doc, updateDoc, orderBy } from 'firebase/firestore';
import { db, handleFirestoreError, OperationType } from '../firebase';
import { ActionItem } from '../types';
import { cn } from '../lib/utils';

export default function Tasks() {
  const { user } = useFirebase();
  const [tasks, setTasks] = useState<ActionItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<'all' | 'pending' | 'completed' | 'overdue'>('all');
  const [search, setSearch] = useState('');

  useEffect(() => {
    if (!user) return;

    // Only fetch action items assigned to the current user (by displayName or email)
    const byName = user.displayName
      ? query(collectionGroup(db, 'actionItems'), where('assignee', '==', user.displayName), orderBy('deadline', 'asc'))
      : null;
    const byEmail = user.email
      ? query(collectionGroup(db, 'actionItems'), where('assignee', '==', user.email), orderBy('deadline', 'asc'))
      : null;

    // Keep two separate lists and merge by id
    let nameItems: ActionItem[] = [];
    let emailItems: ActionItem[] = [];

    const update = () => {
      const merged = new Map<string, ActionItem>();
      [...nameItems, ...emailItems].forEach(item => merged.set(item.id, item));
      const sorted = Array.from(merged.values()).sort((a, b) => a.deadline - b.deadline);
      setTasks(sorted);
      setLoading(false);
    };

    const unsubs: (() => void)[] = [];

    if (byName) {
      unsubs.push(onSnapshot(byName, snap => {
        nameItems = snap.docs.map(d => ({ ...d.data(), id: d.id } as ActionItem));
        update();
      }, err => { console.warn('assignee name query failed', err); setLoading(false); }));
    }

    if (byEmail) {
      unsubs.push(onSnapshot(byEmail, snap => {
        emailItems = snap.docs.map(d => ({ ...d.data(), id: d.id } as ActionItem));
        update();
      }, err => { console.warn('assignee email query failed', err); setLoading(false); }));
    }

    if (!byName && !byEmail) setLoading(false);

    return () => unsubs.forEach(u => u());
  }, [user]);

  const toggleTaskStatus = async (task: ActionItem) => {
    try {
      const newStatus = task.status === 'completed' ? 'pending' : 'completed';
      // We need the full path to update. Since it's a collectionGroup doc, we use task.id but we need the project path.
      // In types.ts, ActionItem has projectId.
      const taskRef = doc(db, 'projects', task.projectId, 'actionItems', task.id);
      await updateDoc(taskRef, { status: newStatus });
    } catch (error) {
      handleFirestoreError(error, OperationType.UPDATE, `projects/${task.projectId}/actionItems/${task.id}`);
    }
  };

  const filteredTasks = tasks.filter(t => {
    const matchesFilter = filter === 'all' || t.status === filter;
    const matchesSearch = t.task.toLowerCase().includes(search.toLowerCase()) || 
                          t.assignee.toLowerCase().includes(search.toLowerCase());
    return matchesFilter && matchesSearch;
  });

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center bg-slate-50">
        <Loader2 className="w-8 h-8 text-academic-900 animate-spin" />
      </div>
    );
  }

  return (
    <div className="p-8 max-w-5xl mx-auto space-y-10">
      <header className="space-y-4">
        <div className="flex items-center justify-between">
          <div className="space-y-1">
             <h2 className="text-3xl font-bold tracking-tight text-slate-900">Smart Action Center</h2>
             <p className="text-slate-500">MeetMind automatically assigned these tasks from your recent syncs.</p>
          </div>
          <div className="flex items-center gap-3">
             <div className="px-4 py-2 bg-white border border-slate-200 rounded-2xl flex items-center gap-2 text-xs font-bold shadow-sm">
                <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
                Live Sync Active
             </div>
          </div>
        </div>

        <div className="flex flex-col md:flex-row gap-4">
          <div className="relative flex-1">
            <Search size={18} className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-400" />
            <input 
              type="text" 
              placeholder="Search across all project tasks..." 
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full pl-12 pr-6 py-4 bg-white border border-slate-100 rounded-2xl shadow-sm focus:ring-2 focus:ring-academic-900/10 focus:border-academic-900 transition-all"
            />
          </div>
          <div className="flex gap-2">
            {(['all', 'pending', 'completed', 'overdue'] as const).map((f) => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                className={cn(
                  "px-6 py-2 rounded-2xl text-[10px] uppercase font-bold tracking-widest transition-all border",
                  filter === f 
                    ? "bg-academic-900 text-white border-academic-900 shadow-lg" 
                    : "bg-white text-slate-500 border-slate-100 hover:bg-slate-50"
                )}
              >
                {f}
              </button>
            ))}
          </div>
        </div>
      </header>

      <div className="space-y-4">
        <AnimatePresence mode="popLayout">
          {filteredTasks.length > 0 ? filteredTasks.map((task, i) => {
            const isOverdue = task.status === 'pending' && task.deadline < Date.now();
            return (
              <motion.div
                key={task.id}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.95 }}
                transition={{ delay: i * 0.05 }}
                className={cn(
                  "bg-white border p-6 rounded-[32px] flex items-center gap-6 group hover:shadow-2xl transition-all",
                  task.status === 'completed' ? "border-slate-100 opacity-60" : "border-slate-50 shadow-sm",
                  isOverdue ? "border-red-100 bg-red-50/10" : ""
                )}
              >
                <button 
                  onClick={() => toggleTaskStatus(task)}
                  className={cn(
                    "w-12 h-12 rounded-2xl flex items-center justify-center shrink-0 transition-all border-2",
                    task.status === 'completed' 
                      ? "bg-academic-900 border-academic-900 text-white shadow-lg shadow-academic-900/20" 
                      : "bg-white border-slate-200 text-transparent hover:border-academic-900 hover:bg-slate-50"
                  )}
                >
                  <CheckCircle2 size={24} className={cn(task.status === 'completed' ? "scale-100" : "scale-0")} />
                </button>

                <div className="flex-1 space-y-2">
                  <div className="flex items-center gap-3">
                    <h4 className={cn(
                      "font-bold text-lg leading-tight",
                      task.status === 'completed' ? "line-through text-slate-400" : "text-slate-900"
                    )}>{task.task}</h4>
                    {isOverdue && (
                      <span className="px-2 py-0.5 bg-red-100 text-red-600 rounded text-[9px] font-bold uppercase tracking-widest flex items-center gap-1">
                        <AlertCircle size={10} /> Overdue
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-6">
                    <div className="flex items-center gap-2">
                       <div className="w-5 h-5 rounded bg-slate-100 flex items-center justify-center text-[10px] font-bold text-slate-400">
                          {task.assignee.charAt(0)}
                       </div>
                       <span className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">{task.assignee}</span>
                    </div>
                    <div className="flex items-center gap-2 text-slate-400">
                       <Calendar size={12} />
                       <span className="text-[10px] font-mono tracking-tighter">Due {new Date(task.deadline).toLocaleDateString()}</span>
                    </div>
                    <div className="px-3 py-0.5 bg-slate-50 rounded-full border border-slate-100 text-[9px] font-bold text-slate-400 uppercase tracking-tighter">
                       ID: {task.projectId.split('-')[1] || task.projectId}
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-4">
                  <button className="p-2 text-slate-300 hover:text-academic-900 hover:bg-slate-50 rounded-xl transition-all">
                    <MoreVertical size={20} />
                  </button>
                </div>
              </motion.div>
            );
          }) : (
            <div className="py-24 flex flex-col items-center justify-center text-center space-y-6">
               <div className="w-24 h-24 bg-slate-50 rounded-[40px] flex items-center justify-center text-slate-200 border-2 border-dashed border-slate-100">
                  <Inbox size={40} />
               </div>
               <div className="space-y-2">
                  <h4 className="text-xl font-bold text-slate-900">Clean Slate</h4>
                  <p className="text-slate-400 max-w-sm mx-auto">
                    You're all caught up. New tasks will appear here after your next MeetMind sync.
                  </p>
               </div>
            </div>
          )}
        </AnimatePresence>
      </div>

      {/* Ella Proactive Tip */}
      <motion.div 
        initial={{ opacity: 0, scale: 0.95 }}
        whileInView={{ opacity: 1, scale: 1 }}
        className="p-10 bg-slate-900 rounded-[48px] text-white flex flex-col md:flex-row items-center gap-10 shadow-massive overflow-hidden relative group"
      >
        <div className="absolute top-0 right-0 w-64 h-64 bg-academic-900/40 rounded-full blur-[100px] -translate-y-1/2 translate-x-1/2 group-hover:bg-academic-900/60 transition-all" />
        <div className="w-20 h-20 bg-white/10 backdrop-blur-3xl rounded-[32px] flex items-center justify-center border border-white/20 shadow-2xl shrink-0">
           <AlertCircle size={40} className="text-accent-gold" />
        </div>
        <div className="flex-1 space-y-4 relative z-10 text-center md:text-left">
           <h4 className="font-bold text-2xl tracking-tight">MeetMind Performance Insight</h4>
           <p className="text-slate-400 text-sm leading-relaxed">
             "Our audit shows you are most productive between 10 AM and 2 PM. Consider scheduling your deep research syncs during this window for optimal task extraction."
           </p>
           <div className="flex gap-4">
              <button className="px-6 py-2 bg-academic-900 rounded-full text-[10px] font-bold uppercase tracking-widest hover:bg-academic-800 transition-all">Optimize Calendar</button>
              <button className="px-6 py-2 bg-white/5 rounded-full text-[10px] font-bold uppercase tracking-widest hover:bg-white/10 transition-all border border-white/10">Dismiss</button>
           </div>
        </div>
      </motion.div>
    </div>
  );
}
