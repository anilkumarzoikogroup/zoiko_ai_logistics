import { Component } from "react";
import type { ReactNode, ErrorInfo } from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";

interface Props  { children: ReactNode; fallback?: ReactNode }
interface State  { error: Error | null }

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("[ErrorBoundary]", error, info.componentStack);
  }

  render() {
    if (this.state.error) {
      if (this.props.fallback) return this.props.fallback;
      return (
        <div className="flex flex-col items-center justify-center min-h-[320px] gap-4 p-8">
          <div className="h-12 w-12 rounded-full bg-red-50 border border-red-200 flex items-center justify-center">
            <AlertTriangle className="h-5 w-5 text-red-500" />
          </div>
          <div className="text-center max-w-md">
            <p className="font-semibold text-slate-700 text-sm">Something went wrong</p>
            <p className="text-xs text-slate-400 mt-1 leading-relaxed font-mono break-all">
              {this.state.error.message}
            </p>
          </div>
          <button
            onClick={() => this.setState({ error: null })}
            className="flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-sm font-medium transition-colors"
          >
            <RefreshCw className="h-3.5 w-3.5" /> Try again
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
