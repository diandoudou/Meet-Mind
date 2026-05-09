import React, { Component, ErrorInfo, ReactNode } from 'react';
import { AlertCircle, RefreshCw } from 'lucide-react';

interface Props {
  children?: ReactNode;
}

interface State {
  hasError: boolean;
  errorInfo: string | null;
}

export class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
    errorInfo: null,
  };

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, errorInfo: error.message };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error("Uncaught error:", error, errorInfo);
  }

  public render() {
    const { children } = (this as any).props;

    if (this.state.hasError) {
      let isFirestoreError = false;
      let displayMessage = "Something went wrong. Please try again later.";
      
      try {
        const parsed = JSON.parse(this.state.errorInfo || "");
        if (parsed.operationType) {
          isFirestoreError = true;
          displayMessage = `Database Error: ${parsed.error}. Operation: ${parsed.operationType} on ${parsed.path || 'unknown path'}`;
        }
      } catch (e) {
        // Not a JSON error
      }

      return (
        <div className="min-h-screen flex items-center justify-center bg-slate-50 p-6">
          <div className="max-w-md w-full bg-white rounded-3xl p-8 shadow-2xl border border-red-100 space-y-6">
            <div className="w-16 h-16 bg-red-50 rounded-2xl flex items-center justify-center text-red-500 mx-auto">
              <AlertCircle size={32} />
            </div>
            <div className="text-center space-y-2">
              <h2 className="text-2xl font-bold text-slate-900">Oops! An error occurred</h2>
              <p className="text-slate-500 text-sm leading-relaxed">
                {displayMessage}
              </p>
            </div>
            <button 
              onClick={() => window.location.reload()}
              className="w-full py-3 bg-red-500 text-white rounded-xl font-bold flex items-center justify-center gap-2 hover:bg-red-600 transition-all active:scale-95 shadow-lg shadow-red-500/20"
            >
              <RefreshCw size={18} />
              Reload Application
            </button>
            {isFirestoreError && (
              <p className="text-[10px] text-center text-slate-400 font-mono uppercase tracking-widest">
                Firestore Error Boundary Triggered
              </p>
            )}
          </div>
        </div>
      );
    }

    return children;
  }
}
