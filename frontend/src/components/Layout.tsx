import { Outlet, NavLink, Link } from 'react-router-dom';
import type { ReactNode } from 'react';
import { 
  LayoutDashboard, 
  FolderKanban, 
  Mic2,
  Search, 
  CheckSquare, 
  Settings, 
  Bell,
  GraduationCap,
  LogOut,
  LogIn,
  Loader2
} from 'lucide-react';
import { cn } from '../lib/utils';
import { useFirebase } from '../context/FirebaseContext';

export default function Layout() {
  const { user, login, logout, loading } = useFirebase();

  if (loading) {
    return (
      <div className="h-screen w-full flex items-center justify-center bg-slate-50">
        <Loader2 className="w-8 h-8 text-academic-900 animate-spin" />
      </div>
    );
  }

  return (
    <div className="flex h-screen bg-slate-50">
      {/* Sidebar */}
      <aside className="w-64 border-r border-slate-200 bg-white flex flex-col">
        <div className="p-6 flex items-center gap-3">
          <div className="w-10 h-10 bg-academic-900 rounded-lg flex items-center justify-center text-white shadow-lg">
            <GraduationCap size={24} />
          </div>
          <div>
            <h1 className="font-bold text-slate-900 tracking-tight text-lg">MeetMind</h1>
            <p className="text-[10px] text-academic-500 uppercase tracking-widest font-mono font-bold">Second Brain</p>
          </div>
        </div>

        <nav className="flex-1 px-4 py-4 space-y-1">
          <NavItem to="/" icon={<LayoutDashboard size={20} />} label="Project Spaces" />
          <NavItem to="/tasks" icon={<CheckSquare size={20} />} label="Action Center" />
          <NavItem to="/search" icon={<Search size={20} />} label="Knowledge Base" />
        </nav>

        <div className="p-4 border-t border-slate-100">
          {user ? (
            <div className="bg-slate-50 rounded-xl p-4 flex items-center gap-3">
              <div className="w-8 h-8 rounded-full overflow-hidden border border-slate-200">
                <img src={user.photoURL || `https://ui-avatars.com/api/?name=${user.displayName}`} alt={user.displayName || 'User'} referrerPolicy="no-referrer" />
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-xs font-semibold text-slate-900 truncate">{user.displayName}</p>
                <p className="text-[10px] text-slate-500 truncate">{user.email}</p>
              </div>
              <button 
                onClick={logout}
                className="p-1.5 text-slate-400 hover:text-red-500 hover:bg-red-50 rounded-lg transition-all"
                title="Logout"
              >
                <LogOut size={14} />
              </button>
            </div>
          ) : (
            <button 
              onClick={login}
              className="w-full flex items-center justify-center gap-2 py-2.5 bg-academic-900 text-white rounded-xl text-sm font-bold hover:bg-academic-800 transition-all shadow-lg"
            >
              <LogIn size={16} />
              Sign In with Google
            </button>
          )}
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 flex flex-col overflow-hidden">
        {/* Header */}
        <header className="h-16 border-bottom border-slate-200 bg-white/50 backdrop-blur-sm flex items-center justify-between px-8 z-10">
          <div className="flex items-center gap-4 flex-1">
             <div className="relative max-w-md w-full">
                <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                <input 
                  type="text" 
                  placeholder="Ask MeetMind anything about your projects..." 
                  className="w-full pl-10 pr-4 py-2 bg-slate-100 border-transparent rounded-full text-sm focus:bg-white focus:ring-2 focus:ring-academic-900/10 focus:border-academic-900/20 transition-all"
                />
             </div>
          </div>
          <div className="flex items-center gap-4">
            <button className="relative p-2 text-slate-500 hover:bg-slate-100 rounded-full transition-colors">
              <Bell size={20} />
              <span className="absolute top-1.5 right-1.5 w-2 h-2 bg-red-500 rounded-full border-2 border-white"></span>
            </button>
            <Link to="/meeting/new" className="flex items-center gap-2 bg-academic-900 text-white px-4 py-2 rounded-full text-sm font-medium hover:bg-academic-800 transition-all shadow-sm">
              <Mic2 size={16} />
              New Meeting
            </Link>
          </div>
        </header>

        <div className="flex-1 overflow-y-auto">
          <Outlet />
        </div>
      </main>
    </div>
  );
}

function NavItem({ to, icon, label }: { to: string, icon: ReactNode, label: string }) {
  return (
    <NavLink 
      to={to}
      className={({ isActive }) => cn(
        "flex items-center gap-3 px-4 py-2.5 rounded-lg text-sm font-medium transition-all group",
        isActive 
          ? "bg-academic-50 text-academic-900 shadow-sm" 
          : "text-slate-500 hover:bg-slate-50 hover:text-slate-900"
      )}
    >
      <span className={cn(
        "transition-colors",
        "group-hover:text-academic-900 text-slate-400"
      )}>{icon}</span>
      {label}
    </NavLink>
  );
}
