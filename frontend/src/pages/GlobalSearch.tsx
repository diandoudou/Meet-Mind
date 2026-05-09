import { useState, type FormEvent } from 'react';
import { motion } from 'motion/react';
import { Search, GraduationCap, Clock, FileText, ExternalLink, ChevronRight, Zap } from 'lucide-react';
import { cn } from '../lib/utils';

export default function GlobalSearch() {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<any[]>([]);

  const handleSearch = (e: FormEvent) => {
    e.preventDefault();
    if (!query) return;

    // Simulated results
    setResults([
      { title: 'Robot Vision Parameter Sync', project: 'Robot Vision', date: '2d ago', match: 'LiDAR calibration constant set to 0.42v during Tuesday session.', type: 'meeting' },
      { title: 'LiDAR Alignment Best Practices', project: 'Knowledge Base', date: 'Academic Source', match: 'Research on point cloud alignment for autonomous bots.', type: 'reference' },
      { title: 'Meeting with Dr. Zhang', project: 'Robot Vision', date: '1w ago', match: 'Mentioned using fixed-seed for deterministic vision output.', type: 'meeting' },
    ]);
  };

  return (
    <div className="p-8 max-w-4xl mx-auto space-y-12">
      <section className="text-center space-y-4 py-12">
        <h2 className="text-4xl font-bold tracking-tighter text-slate-900">Knowledge Retrieval</h2>
        <p className="text-slate-500 max-w-lg mx-auto">
          "Deep search across all meetings, experimental parameters, and academic feedback."
        </p>
      </section>

      <div className="space-y-8">
        <form onSubmit={handleSearch} className="relative group">
          <Search size={24} className="absolute left-6 top-1/2 -translate-y-1/2 text-slate-400 group-focus-within:text-academic-900 transition-colors" />
          <input 
            type="text" 
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search parameters, references, or meeting decisions..." 
            className="w-full pl-16 pr-8 py-6 bg-white border border-slate-200 rounded-3xl text-xl shadow-xl shadow-slate-200/50 focus:outline-none focus:ring-2 focus:ring-academic-900/10 focus:border-academic-900/30 transition-all font-medium"
          />
          <button 
            type="submit"
            className="absolute right-4 top-1/2 -translate-y-1/2 px-6 py-2 bg-academic-900 text-white rounded-2xl font-bold text-sm hover:bg-academic-800 transition-all active:scale-95"
          >
            Search
          </button>
        </form>

        <div className="space-y-6">
          <h4 className="data-grid-header flex items-center gap-2">
            <Zap size={14} className="text-amber-400" />
            Top Matches
          </h4>

          <div className="space-y-4">
            {results.map((result, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.1 }}
                className="glass-card rounded-2xl p-6 hover:shadow-md transition-shadow group cursor-pointer"
              >
                <div className="flex items-start justify-between mb-3 underline-offset-4">
                   <div>
                     <div className="flex items-center gap-2 mb-1">
                        <span className={cn(
                          "px-2 py-0.5 rounded-[4px] text-[10px] font-bold uppercase tracking-wider",
                          result.type === 'meeting' ? "bg-blue-50 text-blue-600" : "bg-emerald-50 text-emerald-600"
                        )}>
                          {result.type}
                        </span>
                        <span className="text-[10px] text-slate-400 font-mono">{result.date} • {result.project}</span>
                     </div>
                     <h5 className="text-lg font-bold text-slate-900 group-hover:text-academic-900 transition-colors">{result.title}</h5>
                   </div>
                   <ExternalLink size={16} className="text-slate-300 group-hover:text-slate-600 transition-colors" />
                </div>
                <p className="text-sm text-slate-600 leading-relaxed bg-slate-50 p-4 rounded-xl border border-dotted border-slate-200">
                  <span className="text-academic-900 font-bold">"... "</span>
                  {result.match}
                  <span className="text-academic-900 font-bold"> " ..."</span>
                </p>
              </motion.div>
            ))}

            {query && results.length === 0 && (
              <div className="text-center py-12 space-y-2 opacity-50">
                <FileText size={48} className="mx-auto text-slate-200" />
                <p className="text-slate-500">Scan complete. No matches found for "{query}".</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
