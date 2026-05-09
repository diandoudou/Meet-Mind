import React, { useState, useEffect, FormEvent } from 'react';
import { motion } from 'motion/react';
import { useNavigate } from 'react-router-dom';
import { 
  Folder, 
  Clock, 
  Calendar, 
  ChevronRight,
  Plus,
  AlertCircle,
  FileText,
  CheckSquare,
  Search,
  Loader2,
  Sparkles
} from 'lucide-react';
import { cn } from '../lib/utils';
import { Project, ActionItem } from '../types';
import { useFirebase } from '../context/FirebaseContext';
import { collection, query, where, onSnapshot, addDoc, doc, serverTimestamp, setDoc } from 'firebase/firestore';
import { db, handleFirestoreError, OperationType } from '../firebase';

export default function Dashboard() {
  const navigate = useNavigate();
  const { user } = useFirebase();
  const [projects, setProjects] = useState<Project[]>([]);
  const [actions, setActions] = useState<ActionItem[]>([]);
  const [isNewProjectModalOpen, setIsNewProjectModalOpen] = useState(false);
  const [newProjectName, setNewProjectName] = useState('');
  const [newProjectDesc, setNewProjectDesc] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!user) {
      setProjects([]);
      setActions([]);
      setLoading(false);
      return;
    }

    // Listener for projects
    const q = query(collection(db, 'projects'), where('ownerUid', '==', user.uid));
    const unsubscribe = onSnapshot(q, (snapshot) => {
      const projs = snapshot.docs.map(doc => ({ ...doc.data(), id: doc.id } as Project));
      setProjects(projs);
      setLoading(false);
    }, (error) => {
      handleFirestoreError(error, OperationType.LIST, 'projects');
    });

    return () => unsubscribe();
  }, [user]);

  const handleCreateProject = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!user || !newProjectName) return;

    try {
      const projectId = `proj-${Date.now()}`;
      await setDoc(doc(db, 'projects', projectId), {
        id: projectId,
        name: newProjectName,
        description: newProjectDesc,
        color: ['#3b82f6', '#10b981', '#8b5cf6', '#f59e0b', '#ef4444'][Math.floor(Math.random() * 5)],
        ownerUid: user.uid,
        members: [],
        createdAt: Date.now()
      });
      setIsNewProjectModalOpen(false);
      setNewProjectName('');
      setNewProjectDesc('');
    } catch (error) {
      handleFirestoreError(error, OperationType.CREATE, 'projects');
    }
  };

  if (!user) {
    return (
      <div className="h-full flex flex-col items-center justify-center p-8 text-center space-y-6">
        <div className="w-20 h-20 bg-slate-100 rounded-3xl flex items-center justify-center text-slate-300">
          <Folder size={40} />
        </div>
        <div className="space-y-2">
          <h2 className="text-2xl font-bold text-slate-900">Welcome to MeetMind</h2>
          <p className="text-slate-500 max-w-sm mx-auto opacity-70">Sign in to begin organizing your academic research and meeting insights with your AI 'Second Brain'.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="p-8 max-w-7xl mx-auto space-y-10">
      {/* Welcome Header */}
      <section className="space-y-1">
        <h2 className="text-3xl font-bold tracking-tight text-slate-900">Project Spaces Hub</h2>
        <div className="flex items-center gap-2">
          <div className="h-0.5 w-12 bg-academic-900 rounded-full" />
          <p className="text-slate-500 text-sm opacity-60">The Second Brain of {user.displayName}</p>
        </div>
      </section>

      {/* Grid Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        
        {/* Project Spaces */}
        <div className="lg:col-span-2 space-y-6">
          <div className="flex items-center justify-between">
            <h3 className="text-lg font-bold flex items-center gap-2">
              <Folder className="text-academic-500" size={20} />
              Project Spaces
            </h3>
            <button 
              onClick={() => setIsNewProjectModalOpen(true)}
              className="px-4 py-1.5 bg-academic-900 text-white rounded-full text-[10px] font-bold uppercase tracking-widest hover:bg-academic-800 transition-all shadow-md shadow-academic-900/10 flex items-center gap-1.5"
            >
              <Plus size={14} /> New Space
            </button>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {loading ? (
              <div className="col-span-2 py-20 flex justify-center">
                <Loader2 className="w-6 h-6 text-slate-300 animate-spin" />
              </div>
            ) : projects.length > 0 ? (
              projects.map((project, i) => (
                <motion.div
                  key={project.id}
                  initial={{ opacity: 0, scale: 0.95 }}
                  animate={{ opacity: 1, scale: 1 }}
                  transition={{ delay: i * 0.05 }}
                  whileHover={{ y: -4 }}
                  onClick={() => navigate(`/project/${project.id}`)}
                  className="glass-card rounded-3xl p-6 cursor-pointer group hover:border-academic-900/20 transition-all border border-transparent"
                >
                  <div className="flex items-start justify-between mb-4">
                    <div className="w-12 h-12 rounded-2xl flex items-center justify-center shadow-inner" style={{ backgroundColor: `${project.color}15` }}>
                      <Folder style={{ color: project.color }} size={24} />
                    </div>
                    <ChevronRight size={18} className="text-slate-300 group-hover:text-academic-900 group-hover:translate-x-1 transition-all" />
                  </div>
                  <h4 className="font-bold text-slate-900 mb-1 text-lg leading-tight">{project.name}</h4>
                  <p className="text-xs text-slate-500 line-clamp-2 mb-6 leading-relaxed opacity-60">{project.description || 'No description provided.'}</p>
                  
                  <div className="flex items-center justify-between border-t border-slate-100 pt-4 mt-auto">
                    <div className="flex items-center gap-1 text-[10px] text-slate-400 font-mono uppercase tracking-wider">
                      <Clock size={12} />
                      Created {new Date(project.createdAt).toLocaleDateString()}
                    </div>
                    <div className="px-2 py-0.5 bg-slate-50 rounded text-[9px] font-bold text-slate-400 uppercase tracking-tighter">
                      Owner
                    </div>
                  </div>
                </motion.div>
              ))
            ) : (
              <div className="col-span-2 py-12 border-2 border-dashed border-slate-200 rounded-3xl flex flex-col items-center justify-center text-center space-y-4 opacity-70">
                <div className="p-4 bg-slate-100 rounded-full">
                  <Folder size={32} className="text-slate-400" />
                </div>
                <div className="space-y-1">
                  <h5 className="font-bold text-slate-900">No project spaces found</h5>
                  <p className="text-xs text-slate-500">Create your first space to begin organizing meetings.</p>
                </div>
                <button 
                  onClick={() => setIsNewProjectModalOpen(true)}
                  className="px-6 py-2 bg-white border border-slate-200 rounded-full text-xs font-bold hover:bg-slate-50 transition-all"
                >
                  Get Started
                </button>
              </div>
            )}
          </div>
        </div>

        {/* Global Action Items */}
        <div className="space-y-6">
          <h3 className="text-lg font-bold flex items-center gap-2 cursor-pointer hover:text-academic-900 transition-all" onClick={() => navigate('/tasks')}>
            <CheckSquare className="text-academic-500" size={20} />
            Smart Action Center
          </h3>

          <div className="space-y-3">
             <div className="p-6 bg-white border border-slate-100 rounded-3xl shadow-sm text-center space-y-3">
                <div className="w-12 h-12 bg-amber-50 rounded-full flex items-center justify-center text-amber-500 mx-auto">
                   <AlertCircle size={24} />
                </div>
                <div className="space-y-1">
                  <h4 className="font-bold text-slate-900 text-sm">Automated Execution</h4>
                  <p className="text-[10px] text-slate-500 leading-relaxed font-medium">
                    MeetMind extracts commitments from your live sessions into actionable task lists.
                  </p>
                </div>
                <button onClick={() => navigate('/tasks')} className="text-xs font-bold text-academic-900 hover:underline">View All Tasks</button>
             </div>
          </div>

          <div className="bg-academic-900 rounded-3xl p-8 text-white space-y-6 shadow-2xl relative overflow-hidden">
            <div className="absolute top-0 right-0 w-32 h-32 bg-accent-gold/20 rounded-full blur-3xl -translate-y-1/2 translate-x-1/2" />
            <div className="space-y-2 relative z-10">
              <div className="flex items-center gap-2 mb-2">
                <Sparkles size={18} className="text-accent-gold" />
                <h4 className="font-bold text-sm tracking-tight">MeetMind Intelligence</h4>
              </div>
              <p className="text-sm text-academic-50/70 leading-relaxed font-medium">
                Connect your previous research syncs to corrective transcription and smart asset transformation.
              </p>
            </div>
            <button 
              onClick={() => navigate('/meeting/new')}
              className="w-full py-2.5 bg-white text-academic-900 rounded-xl text-xs font-bold shadow-lg hover:bg-accent-gold transition-colors relative z-10"
            >
              Enter Research Flow
            </button>
          </div>
        </div>

      </div>

      {/* New Project Modal */}
      {isNewProjectModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-6 bg-slate-900/60 backdrop-blur-sm">
          <motion.div 
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            className="bg-white w-full max-w-md rounded-[32px] p-10 shadow-massive"
          >
            <div className="space-y-2 mb-8 text-center">
              <h3 className="text-2xl font-bold text-slate-900">Initiate Workspace</h3>
              <p className="text-slate-500 text-sm">Define the bounds of your new research area.</p>
            </div>
            <form onSubmit={handleCreateProject} className="space-y-6">
              <div className="space-y-2">
                <label className="text-[10px] font-bold uppercase tracking-widest text-slate-400 px-1">Project Identifier</label>
                <input 
                  type="text" 
                  value={newProjectName}
                  onChange={(e) => setNewProjectName(e.target.value)}
                  placeholder="e.g. Robot Vision 2026"
                  className="w-full px-6 py-4 bg-slate-50 border-transparent rounded-2xl focus:bg-white focus:ring-2 focus:ring-academic-900/10 focus:border-academic-900/20 transition-all font-semibold"
                  required
                />
              </div>
              <div className="space-y-2">
                <label className="text-[10px] font-bold uppercase tracking-widest text-slate-400 px-1">Abstract / Scope</label>
                <textarea 
                  value={newProjectDesc}
                  onChange={(e) => setNewProjectDesc(e.target.value)}
                  placeholder="Briefly describe research objectives..."
                  className="w-full px-6 py-4 bg-slate-50 border-transparent rounded-2xl focus:bg-white focus:ring-2 focus:ring-academic-900/10 focus:border-academic-900/20 transition-all text-sm h-32 resize-none leading-relaxed"
                />
              </div>
              <div className="flex gap-3 pt-4">
                <button 
                  type="button"
                  onClick={() => setIsNewProjectModalOpen(false)}
                  className="flex-1 py-3 border border-slate-200 rounded-2xl text-xs font-bold text-slate-400 hover:bg-slate-50 transition-all"
                >
                  Discard
                </button>
                <button 
                  type="submit"
                  className="flex-1 py-3 bg-academic-900 text-white rounded-2xl text-xs font-bold hover:bg-academic-800 shadow-xl shadow-academic-900/20 transition-all"
                >
                  Create Space
                </button>
              </div>
            </form>
          </motion.div>
        </div>
      )}
    </div>
  );
}
