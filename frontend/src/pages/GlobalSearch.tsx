import { useState, type FormEvent } from 'react';
import { motion } from 'motion/react';
import { useNavigate } from 'react-router-dom';
import { Search, FileText, ExternalLink, Zap, Loader2 } from 'lucide-react';
import { cn } from '../lib/utils';
import { useFirebase } from '../context/FirebaseContext';
import { searchKnowledge, type RagSearchResult } from '../services/ai';

export default function GlobalSearch() {
  const navigate = useNavigate();
  const { user } = useFirebase();
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<RagSearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSearch = async (e: FormEvent) => {
    e.preventDefault();
    if (!query.trim() || !user) return;

    setLoading(true);
    setError(null);
    try {
      const hits = await searchKnowledge({
        query: query.trim(),
        ownerUid: user.uid,
        topK: 10,
      });
      setResults(hits);
    } catch (err) {
      console.error(err);
      setError('Search failed. Ensure the backend is running and knowledge has been indexed.');
      setResults([]);
    } finally {
      setLoading(false);
    }
  };

  const openResult = (result: RagSearchResult) => {
    if (result.project_id && result.source_id) {
      if (result.source_type === 'pdf') {
        navigate(`/project/${result.project_id}?file=${result.source_id}`);
      } else {
        navigate(`/project/${result.project_id}?meeting=${result.source_id}`);
      }
    }
  };

  const formatDate = (timestamp?: number) => {
    if (!timestamp) return 'Indexed';
    return new Date(timestamp).toLocaleDateString();
  };

  if (!user) {
    return (
      <div className="p-8 max-w-4xl mx-auto text-center py-20 text-slate-500">
        Sign in to search your project knowledge base.
      </div>
    );
  }

  return (
    <div className="p-8 max-w-4xl mx-auto space-y-12">
      <section className="text-center space-y-4 py-12">
        <h2 className="text-4xl font-bold tracking-tighter text-slate-900">Knowledge Retrieval</h2>
        <p className="text-slate-500 max-w-lg mx-auto">
          Hybrid search across meetings, summaries, and PDF documents (vector + keyword).
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
            disabled={loading}
            className="absolute right-4 top-1/2 -translate-y-1/2 px-6 py-2 bg-academic-900 text-white rounded-2xl font-bold text-sm hover:bg-academic-800 transition-all active:scale-95 disabled:opacity-50 flex items-center gap-2"
          >
            {loading ? <Loader2 size={14} className="animate-spin" /> : null}
            Search
          </button>
        </form>

        {error && (
          <p className="text-sm text-red-500 text-center">{error}</p>
        )}

        <div className="space-y-6">
          <h4 className="data-grid-header flex items-center gap-2">
            <Zap size={14} className="text-amber-400" />
            Top Matches {results.length > 0 && `(${results.length})`}
          </h4>

          <div className="space-y-4">
            {results.map((result, i) => (
              <motion.div
                key={result.chunk_id || i}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: i * 0.05 }}
                onClick={() => openResult(result)}
                className="glass-card rounded-2xl p-6 hover:shadow-md transition-shadow group cursor-pointer"
              >
                <div className="flex items-start justify-between mb-3">
                  <div>
                    <div className="flex items-center gap-2 mb-1 flex-wrap">
                      <span className={cn(
                        'px-2 py-0.5 rounded-[4px] text-[10px] font-bold uppercase tracking-wider',
                        result.source_type === 'pdf' ? 'bg-emerald-50 text-emerald-600' : 'bg-blue-50 text-blue-600'
                      )}>
                        {result.source_type.replace('_', ' ')}
                      </span>
                      <span className="text-[10px] text-slate-400 font-mono">
                        score {result.score.toFixed(2)} • {formatDate(result.timestamp)}
                        {result.project_id ? ` • ${result.project_id}` : ''}
                      </span>
                    </div>
                    <h5 className="text-lg font-bold text-slate-900 group-hover:text-academic-900 transition-colors">
                      {result.source_title}
                    </h5>
                    {result.speaker && (
                      <p className="text-[10px] text-slate-400 mt-1">Speaker: {result.speaker}</p>
                    )}
                  </div>
                  <ExternalLink size={16} className="text-slate-300 group-hover:text-slate-600 transition-colors shrink-0" />
                </div>
                <p className="text-sm text-slate-600 leading-relaxed bg-slate-50 p-4 rounded-xl border border-dotted border-slate-200">
                  {result.text}
                </p>
              </motion.div>
            ))}

            {query && !loading && results.length === 0 && !error && (
              <div className="text-center py-12 space-y-2 opacity-70">
                <FileText size={48} className="mx-auto text-slate-200" />
                <p className="text-slate-500">No matches for &quot;{query}&quot;. Finish a meeting or upload a PDF to build the index.</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
