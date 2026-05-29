import React, { useMemo, useState, useEffect, useRef } from 'react';
import useVerification from '../hooks/useVerification';

const Verification = () => {
  const {
    contractId,
    parameters,
    activeParamId,
    setActiveParamId,
    loading,
    busy,
    error,
    message,
    handleUpdateValue,
    handleToggleVerify,
    handleSubmitDraft,
    handleSubmitForApproval,
  } = useVerification();

  const [pdfDoc, setPdfDoc] = useState(null);
  const [pdfLoading, setPdfLoading] = useState(false);
  const [currentPage, setCurrentPage] = useState(1);
  const [editedValue, setEditedValue] = useState('');

  const canvasRef = useRef(null);
  const containerRef = useRef(null);
  const renderTaskRef = useRef(null);

  // Load PDF document from API
  const loadPdfDocument = React.useCallback(async () => {
    if (!contractId || !window.pdfjsLib) return;
    try {
      setPdfLoading(true);
      const fileUrl = `${import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api'}/contracts/${contractId}/document`;
      const loadingTask = window.pdfjsLib.getDocument(fileUrl);
      const doc = await loadingTask.promise;
      setPdfDoc(doc);
    } catch (err) {
      console.error('Failed to load PDF document representation:', err);
    } finally {
      setPdfLoading(false);
    }
  }, [contractId]);

  // Initialize PDF.js CDN
  useEffect(() => {
    if (window.pdfjsLib) {
      loadPdfDocument();
      return;
    }
    setPdfLoading(true);
    const script = document.createElement('script');
    script.src = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.4.120/pdf.min.js';
    script.onload = () => {
      window.pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.4.120/pdf.worker.min.js';
      setPdfLoading(false);
      loadPdfDocument();
    };
    document.head.appendChild(script);
  }, [loadPdfDocument]);

  useEffect(() => {
    if (window.pdfjsLib && contractId) {
      loadPdfDocument();
    }
  }, [contractId, loadPdfDocument]);

  // Render current PDF page
  const renderPdfPage = React.useCallback(async (pageNumber) => {
    if (!pdfDoc || !canvasRef.current) return;
    try {
      if (renderTaskRef.current) {
        renderTaskRef.current.cancel();
      }

      const page = await pdfDoc.getPage(pageNumber);
      const canvas = canvasRef.current;
      const context = canvas.getContext('2d');
      
      let parentWidth = containerRef.current ? containerRef.current.clientWidth - 16 : 500;
      if (parentWidth <= 0) parentWidth = 500;
      const unscaledViewport = page.getViewport({ scale: 1.0 });
      const computedScale = parentWidth / unscaledViewport.width;
      const viewport = page.getViewport({ scale: computedScale });

      canvas.height = viewport.height;
      canvas.width = viewport.width;

      const renderContext = {
        canvasContext: context,
        viewport: viewport,
      };

      renderTaskRef.current = page.render(renderContext);
      await renderTaskRef.current.promise;
    } catch (err) {
      console.warn('Interrupted PDF render page:', err);
    }
  }, [pdfDoc]);

  // Trigger render when page changes
  useEffect(() => {
    if (pdfDoc) {
      renderPdfPage(currentPage);
    }
  }, [pdfDoc, currentPage, renderPdfPage]);

  // Get active parameter object
  const activeParameter = useMemo(() => {
    return parameters.find(p => p.parameter_id === activeParamId) || null;
  }, [parameters, activeParamId]);

  // Set edited value when parameter loads
  useEffect(() => {
    if (activeParameter) {
      setEditedValue(activeParameter.user_override || activeParameter.original_extract || '');
      
      // Auto-transition PDF page
      const targetPage = activeParameter.spatial_json?.page;
      if (targetPage) {
        setCurrentPage(Number(targetPage));
      }
    }
  }, [activeParamId, activeParameter]);

  // Sort parameters by validation priority: Failures/Invalid ➔ Needs Review ➔ Verified
  const sortedParameters = useMemo(() => {
    const getPriority = (p) => {
      if (p.is_verified) return 3; // Verified (Lowest Priority)
      const state = String(p.validation_state).toLowerCase();
      if (state === 'invalid' || state === 'fail') return 1; // Failure (Highest)
      return 2; // Needs Review (Medium)
    };

    return [...parameters].sort((a, b) => getPriority(a) - getPriority(b));
  }, [parameters]);

  // Categorize validation states
  const getValidationBadge = (state, isVerified) => {
    if (isVerified) {
      return { label: 'Verified Pass', color: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' };
    }
    const cleanState = String(state).toLowerCase();
    switch (cleanState) {
      case 'valid':
        return { label: 'Automated Pass', color: 'bg-teal-500/10 text-teal-400 border-teal-500/20' };
      case 'invalid':
      case 'fail':
        return { label: 'Validation Failure', color: 'bg-rose-500/10 text-rose-400 border-rose-500/20' };
      case 'needs_review':
      default:
        return { label: 'Requires Review', color: 'bg-amber-500/10 text-amber-400 border-amber-500/20' };
    }
  };

  // Bounding box style overlay
  const overlayStyle = useMemo(() => {
    if (!activeParameter?.spatial_json?.rects) return null;
    const spatial = activeParameter.spatial_json;
    if (spatial.char_fallback) return null;
    if (Number(currentPage) !== Number(spatial.page)) return null;

    const [rect] = spatial.rects;
    const [x0, y0, x1, y1] = rect;
    const baseW = spatial.page_width || 612;
    const baseH = spatial.page_height || 792;

    return {
      left: `${(x0 / baseW) * 100}%`,
      top: `${(y0 / baseH) * 100}%`,
      width: `${((x1 - x0) / baseW) * 100}%`,
      height: `${((y1 - y0) / baseH) * 100}%`,
      position: 'absolute',
      backgroundColor: 'rgba(236, 72, 153, 0.25)', // Premium bright translucent overlay
      border: '2px dashed rgb(236, 72, 153)',
      pointerEvents: 'none',
      borderRadius: '4px',
      transition: 'all 0.15s cubic-bezier(0.4, 0, 0.2, 1)',
    };
  }, [activeParameter, currentPage]);

  const handleUpdate = () => {
    if (activeParameter) {
      handleUpdateValue(activeParameter.parameter_id, editedValue);
    }
  };

  return (
    <div className="flex flex-col gap-md w-full min-h-[calc(100vh-6rem)] p-md text-slate-100 bg-slate-950 font-sans">
      {/* Workbench Header Controls */}
      <div className="flex flex-wrap justify-between items-center gap-sm bg-slate-900/50 border border-slate-800 p-md rounded-2xl shadow-xl backdrop-blur-md">
        <div>
          <h1 className="text-xl font-black text-slate-100 tracking-tight flex items-center gap-xs">
            <span className="material-symbols-outlined text-pink-500">fact_check</span>
            Draft Workspace Verification
          </h1>
          <p className="text-xs text-slate-400 mt-1">
            Contract ID: <span className="font-mono text-slate-300">{contractId || 'None'}</span> • Staged Draft Review Zone
          </p>
        </div>

        <div className="flex items-center gap-xs">
          <button
            type="button"
            disabled={busy}
            onClick={handleSubmitDraft}
            className="border border-slate-700 bg-slate-800 hover:bg-slate-700 text-slate-100 text-xs font-bold px-md py-sm rounded-xl transition-all shadow-sm flex items-center gap-xs"
          >
            <span className="material-symbols-outlined text-[16px]">save</span>
            Save Progress
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={handleSubmitForApproval}
            className="bg-primary hover:opacity-90 text-on-primary text-xs font-bold px-md py-sm rounded-xl transition-all shadow-md flex items-center gap-xs"
          >
            <span className="material-symbols-outlined text-[16px]">publish</span>
            Submit Approval
          </button>
        </div>
      </div>

      {error && (
        <div className="p-sm rounded-xl border border-rose-500/20 bg-rose-500/10 text-rose-400 text-xs font-semibold">
          {error}
        </div>
      )}
      {message && (
        <div className="p-sm rounded-xl border border-emerald-500/20 bg-emerald-500/10 text-emerald-400 text-xs font-semibold">
          {message}
        </div>
      )}

      {loading ? (
        <div className="flex-1 flex items-center justify-center text-slate-400 text-sm animate-pulse">
          Loading verification pipeline...
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-[320px_1fr_340px] gap-md h-[calc(100vh-14rem)] min-h-[500px]">
          {/* LEFT PANEL: Parameter Explorer */}
          <div className="bg-slate-900/40 border border-slate-800 rounded-2xl flex flex-col overflow-hidden">
            <div className="p-md border-b border-slate-800 bg-slate-900/60 shrink-0">
              <h2 className="text-xs font-black text-slate-200 uppercase tracking-widest">Staged Parameters</h2>
              <p className="text-[10px] text-slate-500 mt-[2px]">Sorted by validation priority</p>
            </div>
            
            <div className="flex-1 overflow-y-auto p-sm space-y-xs custom-scrollbar">
              {sortedParameters.map((param) => {
                const isActive = param.parameter_id === activeParamId;
                const badge = getValidationBadge(param.validation_state, param.is_verified);
                return (
                  <button
                    key={param.parameter_id}
                    onClick={() => setActiveParamId(param.parameter_id)}
                    className={`w-full text-left p-sm rounded-xl border transition-all flex flex-col gap-xs ${
                      isActive 
                        ? 'bg-slate-800/80 border-slate-700 shadow-md ring-1 ring-slate-700/50' 
                        : 'bg-transparent border-slate-900 hover:bg-slate-900/30'
                    }`}
                  >
                    <div className="flex justify-between items-start w-full">
                      <span className="text-[10px] text-pink-400 font-bold tracking-wide">{param.header_name}</span>
                      <span className={`text-[8px] font-black uppercase px-sm py-[2px] rounded-full border ${badge.color}`}>
                        {badge.label}
                      </span>
                    </div>
                    <span className="text-xs font-black text-slate-200">{param.param_name}</span>
                    <span className="text-[10px] text-slate-500 truncate max-w-full">
                      {param.user_override || param.original_extract || 'Null extraction'}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* CENTER PANEL: Dynamic PDF Page Canvas */}
          <div className="bg-slate-900/20 border border-slate-800 rounded-2xl flex flex-col overflow-hidden relative" ref={containerRef}>
            <div className="p-sm bg-slate-900/60 border-b border-slate-800 shrink-0 flex items-center justify-between z-10">
              <div className="flex items-center gap-xs">
                <button
                  type="button"
                  disabled={currentPage <= 1 || pdfLoading}
                  onClick={() => setCurrentPage(prev => Math.max(1, prev - 1))}
                  className="p-xs hover:bg-slate-800 rounded text-slate-400 hover:text-slate-200 transition-colors disabled:opacity-30"
                >
                  <span className="material-symbols-outlined">navigate_before</span>
                </button>
                <span className="text-xs text-slate-400 font-mono">
                  Page {currentPage} of {pdfDoc?.numPages || 1}
                </span>
                <button
                  type="button"
                  disabled={currentPage >= (pdfDoc?.numPages || 1) || pdfLoading}
                  onClick={() => setCurrentPage(prev => Math.min(pdfDoc?.numPages || 1, prev + 1))}
                  className="p-xs hover:bg-slate-800 rounded text-slate-400 hover:text-slate-200 transition-colors disabled:opacity-30"
                >
                  <span className="material-symbols-outlined">navigate_next</span>
                </button>
              </div>
              <span className="text-[10px] text-slate-500 font-mono">
                {pdfDoc ? 'PDF Engine Active' : 'Loading document...'}
              </span>
            </div>

            <div className="flex-1 overflow-auto p-md flex items-start justify-center relative bg-slate-950 custom-scrollbar">
              <div className="relative border border-slate-800/80 shadow-2xl rounded-lg overflow-hidden bg-white shrink-0">
                <canvas ref={canvasRef} />
                {overlayStyle && <div style={overlayStyle} />}
              </div>
            </div>
          </div>

          {/* RIGHT PANEL: Evidence Inspector */}
          <div className="bg-slate-900/40 border border-slate-800 rounded-2xl flex flex-col overflow-hidden">
            <div className="p-md border-b border-slate-800 bg-slate-900/60 shrink-0">
              <h2 className="text-xs font-black text-slate-200 uppercase tracking-widest">Evidence Inspector</h2>
              <p className="text-[10px] text-slate-500 mt-[2px]">Layout coordinates & validation details</p>
            </div>

            {activeParameter ? (
              <div className="flex-1 overflow-y-auto p-md space-y-md custom-scrollbar flex flex-col">
                <div className="space-y-xs">
                  <span className="text-[10px] text-slate-500 font-bold uppercase tracking-wider">Parameter Path</span>
                  <p className="text-sm font-black text-slate-200 leading-tight">
                    {activeParameter.header_name} / {activeParameter.param_name}
                  </p>
                </div>

                <div className="space-y-xs">
                  <span className="text-[10px] text-slate-500 font-bold uppercase tracking-wider">System Confidence Score</span>
                  <div className="flex items-center gap-xs">
                    <div className="h-2 w-24 bg-slate-800 rounded-full overflow-hidden">
                      <div 
                        className={`h-full ${
                          activeParameter.match_score >= 0.8 ? 'bg-emerald-500' :
                          activeParameter.match_score >= 0.5 ? 'bg-amber-500' : 'bg-rose-500'
                        }`} 
                        style={{ width: `${(activeParameter.match_score || 0) * 100}%` }} 
                      />
                    </div>
                    <span className="text-xs font-mono font-bold text-slate-300">
                      {Math.round((activeParameter.match_score || 0) * 100)}%
                    </span>
                  </div>
                </div>

                <div className="space-y-xs">
                  <span className="text-[10px] text-slate-500 font-bold uppercase tracking-wider">Verbatim Citation Excerpt</span>
                  <div className="p-sm bg-slate-950/60 rounded-xl border border-slate-800 text-[11px] font-mono text-slate-400 leading-relaxed max-h-36 overflow-y-auto custom-scrollbar">
                    "{activeParameter.citation_text || 'No supporting citation found'}"
                  </div>
                </div>

                <div className="space-y-xs">
                  <span className="text-[10px] text-slate-500 font-bold uppercase tracking-wider">Verification Notes / Status</span>
                  <p className="text-xs text-slate-400 italic">
                    {activeParameter.validation_message || 'No automatic exceptions generated.'}
                  </p>
                </div>

                <div className="space-y-xs flex-1">
                  <span className="text-[10px] text-slate-500 font-bold uppercase tracking-wider">Effective Override Value</span>
                  <textarea
                    value={editedValue}
                    onChange={(e) => setEditedValue(e.target.value)}
                    className="w-full bg-slate-950/80 border border-slate-800 hover:border-slate-700 focus:border-pink-500/80 rounded-xl p-sm text-xs text-slate-200 outline-none transition-all resize-none h-24"
                    placeholder="Enter manual correction..."
                  />
                  <button
                    type="button"
                    onClick={handleUpdate}
                    disabled={busy || editedValue === (activeParameter.user_override || activeParameter.original_extract || '')}
                    className="w-full bg-slate-800 hover:bg-slate-700 text-slate-200 py-[6px] rounded-lg text-xs font-bold shadow-sm transition-all border border-slate-700 disabled:opacity-40"
                  >
                    Save Value Override
                  </button>
                </div>

                <div className="border-t border-slate-800 pt-md shrink-0 flex gap-xs">
                  <button
                    type="button"
                    disabled={busy || activeParameter.is_verified}
                    onClick={() => handleToggleVerify(activeParameter.parameter_id, true)}
                    className="flex-1 bg-emerald-600 hover:bg-emerald-500 text-white font-bold py-sm rounded-xl text-xs shadow-md transition-all flex items-center justify-center gap-xs disabled:opacity-45"
                  >
                    <span className="material-symbols-outlined text-[14px]">done</span>
                    Approve
                  </button>
                  <button
                    type="button"
                    disabled={busy || !activeParameter.is_verified}
                    onClick={() => handleToggleVerify(activeParameter.parameter_id, false)}
                    className="flex-1 bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 font-bold py-sm rounded-xl text-xs shadow-sm transition-all flex items-center justify-center gap-xs disabled:opacity-45"
                  >
                    <span className="material-symbols-outlined text-[14px]">close</span>
                    Reject Pass
                  </button>
                </div>
              </div>
            ) : (
              <div className="flex-1 flex items-center justify-center text-slate-500 text-xs p-md text-center">
                Select a staged parameter to examine its citation grounding evidence.
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default Verification;
