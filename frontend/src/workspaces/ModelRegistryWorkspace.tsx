import React, { useEffect, useState } from 'react';
import { apiService } from '../services/api';
import { ModelRegistryItem } from '../types';
import { 
  FileCode, CheckCircle2, BookOpen, Layers, Cpu, ShieldCheck, 
  ExternalLink, Search, RefreshCw, AlertCircle, Hash, Zap
} from 'lucide-react';

export const ModelRegistryWorkspace: React.FC = () => {
  const [registryData, setRegistryData] = useState<any>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [selectedCategory, setSelectedCategory] = useState<string>('ALL');
  const [searchQuery, setSearchQuery] = useState<string>('');
  const [error, setError] = useState<string | null>(null);

  const fetchRegistry = async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await apiService.getModelRegistry();
      setRegistryData(res);
    } catch (err: any) {
      console.error('Error fetching model registry:', err);
      setError(err?.message || 'Failed to fetch model registry');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchRegistry();
  }, []);

  const models: ModelRegistryItem[] = registryData?.models || [];

  const categories = ['ALL', ...Array.from(new Set(models.map((m) => m.category)))];

  const filteredModels = models.filter((m) => {
    const matchesCategory = selectedCategory === 'ALL' || m.category === selectedCategory;
    const matchesSearch =
      m.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      m.short_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
      m.file_path.toLowerCase().includes(searchQuery.toLowerCase()) ||
      (m.economic_intuition && m.economic_intuition.toLowerCase().includes(searchQuery.toLowerCase()));
    return matchesCategory && matchesSearch;
  });

  return (
    <div className="flex-1 flex flex-col h-full bg-[#080b11] text-slate-100 overflow-y-auto p-4 space-y-4">
      {/* Top Header */}
      <div className="flex flex-wrap items-center justify-between gap-3 bg-[#0d111a] p-4 rounded-lg border border-[#1f293d]/80">
        <div>
          <div className="flex items-center gap-2">
            <span className="p-1.5 rounded bg-indigo-500/10 text-indigo-400 border border-indigo-500/30">
              <FileCode className="w-5 h-5" />
            </span>
            <h1 className="text-lg font-bold tracking-tight text-white flex items-center gap-2">
              Quantitative Model Registry & IEEE Specifications
              <span className="text-xs px-2 py-0.5 rounded font-mono font-normal bg-indigo-950/80 text-indigo-300 border border-indigo-700/50">
                Peer-Review Audited
              </span>
            </h1>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Complete mathematical formulations, calibrated coefficients, optimization algorithms, and empirical citations for all 7 production models.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <div className="text-xs font-mono bg-[#151c2c] px-3 py-1.5 rounded border border-[#23314d] text-slate-300">
            Target: <span className="text-amber-300 font-bold">{registryData?.target_underlying || 'NIFTY 50'}</span> | Models:{' '}
            <span className="text-cyan-400 font-bold">{registryData?.models_count || 7}</span>
          </div>

          <button
            onClick={fetchRegistry}
            disabled={loading}
            className="px-3 py-1.5 bg-[#151c2c] hover:bg-[#1a2337] text-slate-200 border border-[#23314d] rounded text-xs font-mono flex items-center gap-1.5 transition-colors"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      {error && (
        <div className="p-3 bg-rose-950/40 border border-rose-800 text-rose-300 rounded text-xs flex items-center gap-2">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Filter & Search Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 bg-[#0d111a] p-3 rounded-lg border border-[#1f293d]">
        <div className="flex flex-wrap items-center gap-1.5">
          {categories.map((cat) => (
            <button
              key={cat}
              onClick={() => setSelectedCategory(cat)}
              className={`px-2.5 py-1 rounded text-xs font-mono transition-colors ${
                selectedCategory === cat
                  ? 'bg-indigo-600 text-white font-bold'
                  : 'bg-[#151c2c] text-slate-400 hover:text-slate-200 hover:bg-[#1a2337]'
              }`}
            >
              {cat.replace(/_/g, ' ')}
            </button>
          ))}
        </div>

        <div className="relative min-w-[240px]">
          <Search className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-500" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search model, parameter, formula..."
            className="w-full bg-[#080b11] border border-[#1f293d] rounded pl-8 pr-3 py-1 text-xs text-slate-200 font-mono placeholder-slate-500 focus:outline-none focus:border-indigo-500"
          />
        </div>
      </div>

      {/* Models List */}
      <div className="space-y-4">
        {filteredModels.map((model) => (
          <div
            key={model.id}
            className="bg-[#0d111a] p-5 rounded-lg border border-[#1f293d] hover:border-slate-600 transition-all space-y-4"
          >
            {/* Model Card Header */}
            <div className="flex flex-wrap items-start justify-between gap-2 border-b border-[#1f293d] pb-3">
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <span className="px-2 py-0.5 rounded text-[11px] font-mono font-bold bg-indigo-950/70 text-indigo-300 border border-indigo-700/50">
                    {model.id.toUpperCase()}
                  </span>
                  <span className="px-2 py-0.5 rounded text-[11px] font-mono bg-[#162032] text-cyan-300 border border-cyan-800/40">
                    {model.category}
                  </span>
                  <span className="text-xs font-mono text-slate-400">
                    {model.version}
                  </span>
                </div>
                <h2 className="text-base font-bold text-white font-mono flex items-center gap-2">
                  {model.short_name}: {model.name}
                </h2>
                <div className="text-xs font-mono text-slate-400 mt-1 flex items-center gap-1.5">
                  <span className="text-slate-500">Source:</span>
                  <code className="text-amber-300/90 bg-[#090d15] px-1.5 py-0.5 rounded border border-[#162032]">
                    {model.file_path}
                  </code>
                </div>
              </div>

              <div className="flex items-center gap-2">
                <span className="px-2.5 py-1 rounded text-xs font-mono font-semibold bg-emerald-500/15 text-emerald-400 border border-emerald-500/40 flex items-center gap-1.5">
                  <CheckCircle2 className="w-3.5 h-3.5" />
                  {model.validation_status}
                </span>
              </div>
            </div>

            {/* Governing Mathematical Equation */}
            <div className="bg-[#080b11] p-3.5 rounded border border-[#1a2337]">
              <div className="text-[11px] font-mono uppercase tracking-wider text-slate-400 mb-1.5 flex items-center gap-1.5">
                <Cpu className="w-3.5 h-3.5 text-indigo-400" />
                Governing Equation (LaTeX Specification)
              </div>
              <div className="font-mono text-sm text-cyan-300 bg-[#06080d] p-3 rounded border border-[#141b2b] overflow-x-auto">
                <code>{model.governing_equation_latex}</code>
              </div>
            </div>

            {/* Economic Intuition */}
            {model.economic_intuition && (
              <div className="text-xs text-slate-300 bg-[#121826]/70 p-3 rounded border border-[#1c273e] flex items-start gap-2">
                <BookOpen className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
                <div className="leading-relaxed">
                  <span className="font-bold text-slate-200">Economic Rationale: </span>
                  {model.economic_intuition}
                </div>
              </div>
            )}

            {/* Model-Specific Detailed Parameters Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
              {/* Calibrated Parameters */}
              {model.parameters && (
                <div className="bg-[#090d15] p-3 rounded border border-[#1a2337] col-span-1 md:col-span-2">
                  <div className="text-[11px] font-mono uppercase tracking-wider text-slate-400 mb-2">
                    Calibrated Numerical Parameters
                  </div>
                  <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 font-mono text-xs">
                    {Object.entries(model.parameters).map(([paramKey, paramVal]) => (
                      <div key={paramKey} className="bg-[#0d121e] p-2 rounded border border-[#141b2b]">
                        <div className="text-[10px] text-slate-400 truncate">{paramKey}</div>
                        <div className="text-amber-300 font-bold text-sm mt-0.5">{String(paramVal)}</div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Training Window & Coverage */}
              <div className="bg-[#090d15] p-3 rounded border border-[#1a2337]">
                <div className="text-[11px] font-mono uppercase tracking-wider text-slate-400 mb-2">
                  Dataset & Calibration Domain
                </div>
                <div className="space-y-2 text-xs font-mono">
                  {model.training_window && (
                    <div>
                      <span className="text-slate-500 block text-[10px]">Training Window:</span>
                      <span className="text-slate-200">{model.training_window}</span>
                    </div>
                  )}
                  {model.annualization_factor && (
                    <div>
                      <span className="text-slate-500 block text-[10px]">Annualization Factor:</span>
                      <span className="text-cyan-300">{model.annualization_factor}</span>
                    </div>
                  )}
                  {model.coverage && (
                    <div>
                      <span className="text-slate-500 block text-[10px]">Empirical Coverage:</span>
                      <span className="text-emerald-400">{model.coverage}</span>
                    </div>
                  )}
                </div>
              </div>

              {/* HMM Specific: Hidden States Table */}
              {model.states && (
                <div className="bg-[#090d15] p-3 rounded border border-[#1a2337] col-span-1 md:col-span-3">
                  <div className="text-[11px] font-mono uppercase tracking-wider text-slate-400 mb-2">
                    Inferred Latent Regimes (4-State Ergocenter)
                  </div>
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs font-mono">
                      <thead>
                        <tr className="border-b border-[#1a2337] text-slate-400 text-left">
                          <th className="pb-1.5 px-2">State</th>
                          <th className="pb-1.5 px-2">Label</th>
                          <th className="pb-1.5 px-2">Annual Volatility</th>
                          <th className="pb-1.5 px-2">Strategic Mandate</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-[#141b2b]">
                        {model.states.map((st) => (
                          <tr key={st.state}>
                            <td className="py-1.5 px-2 text-indigo-400 font-bold">State {st.state}</td>
                            <td className="py-1.5 px-2 text-white font-semibold">{st.label}</td>
                            <td className="py-1.5 px-2 text-amber-300">{st.typical_annual_vol}</td>
                            <td className="py-1.5 px-2 text-slate-300">{st.action}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* BSM Specific: Greeks Supported */}
              {model.greeks_supported && (
                <div className="bg-[#090d15] p-3 rounded border border-[#1a2337] col-span-1 md:col-span-3">
                  <div className="text-[11px] font-mono uppercase tracking-wider text-slate-400 mb-2">
                    Closed-Form Closed Analytical Derivatives
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {model.greeks_supported.map((gk) => (
                      <span key={gk} className="px-2.5 py-1 rounded bg-[#0d121e] border border-[#1a2337] text-xs font-mono text-cyan-300 font-bold">
                        {gk}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* M-Score Specific: Signal Thresholds */}
              {model.signal_thresholds && (
                <div className="bg-[#090d15] p-3 rounded border border-[#1a2337] col-span-1 md:col-span-3">
                  <div className="text-[11px] font-mono uppercase tracking-wider text-slate-400 mb-2">
                    Empirical Alpha Signal Thresholds
                  </div>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 font-mono text-xs">
                    {Object.entries(model.signal_thresholds).map(([thKey, thVal]) => (
                      <div key={thKey} className="bg-[#0d121e] p-2 rounded border border-[#141b2b]">
                        <span className="text-[10px] text-slate-400 block">{thKey}:</span>
                        <span className="text-emerald-400 font-bold">{thVal}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* IEEE Methodology Integrity Statement */}
      <div className="bg-[#0d111a] p-4 rounded-lg border border-[#1f293d] text-xs text-slate-400 space-y-2">
        <div className="flex items-center gap-2 text-slate-200 font-bold uppercase font-mono">
          <ShieldCheck className="w-4 h-4 text-emerald-400" />
          IEEE Transactions Research Traceability & Reproducibility Statement
        </div>
        <p className="leading-relaxed">
          All 7 quantitative models documented above correspond to exact code modules located under <code>backend/services/</code>. Model training adheres to non-lookahead walk-forward rolling calibration windows. Implied volatilities are resolved via double-precision Brent-Decker roots within numerical tolerance \(\varepsilon \le 10^{-6}\). Paper trading logs and execution latencies are stored in an append-only SQLite ledger with monotonic nanosecond timestamps.
        </p>
      </div>
    </div>
  );
};
export default ModelRegistryWorkspace;

