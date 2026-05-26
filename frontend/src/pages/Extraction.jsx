import React, { useMemo, useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import useExtraction from '../hooks/useExtraction';
import { PARAMETER_GROUPS } from '../services/taxonomy';
import { api } from '../services/api';

const Extraction = () => {
  const navigate = useNavigate();
  const {
    contractId,
    contract,
    parameters,
    selectedParamId,
    setSelectedParamId,
    selectedParameter,
    loading,
    busy,
    error,
    updateParameter,
  } = useExtraction();

  const [activeGroup, setActiveGroup] = useState('1. Basic Contract Metadata');
  const [pdfDoc, setPdfDoc] = useState(null);
  const [pdfLoading, setPdfLoading] = useState(false);
  const [workflowStatus, setWorkflowStatus] = useState('');
  const canvasRef = useRef(null);
  const renderTaskRef = useRef(null);

  // Synchronize internal status tracking when contract record completes mapping hydration
  useEffect(() => {
    if (contract?.workflow_state) {
      setWorkflowStatus(contract.workflow_state);
    }
  }, [contract]);

  // Handle lazy loading of the global CDN PDF.js engine inside DOM runtime limits
  useEffect(() => {
    if (window.pdfjsLib) return;
    setPdfLoading(true);
    const script = document.createElement('script');
    script.src = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.4.120/pdf.min.js';
    script.onload = () => {
      window.pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.4.120/pdf.worker.min.js';
      setPdfLoading(false);
      loadPdfDocument();
    };
    document.head.appendChild(script);
  }, []);

  // Re-fetch document binary instances when state triggers change
  useEffect(() => {
    if (window.pdfjsLib && contractId) {
      loadPdfDocument();
    }
  }, [contractId]);

  // Render target pages when active citation selections shift focus parameters
  useEffect(() => {
    if (pdfDoc) {
      const targetPage = selectedParameter?.spatial_json?.page || 1;
      renderPdfPage(targetPage);
    }
  }, [pdfDoc, selectedParamId, selectedParameter]);

  const loadPdfDocument = async () => {
    if (!contractId || !window.pdfjsLib) return;
    try {
      setPdfLoading(true);
      // Fetch binary blob directly from raw endpoint
      const fileUrl = `${import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api'}/contracts/${contractId}/document`;
      const loadingTask = window.pdfjsLib.getDocument(fileUrl);
      const doc = await loadingTask.promise;
      setPdfDoc(doc);
    } catch (err) {
      console.error('Failed to parse document stream:', err);
    } finally {
      setPdfLoading(false);
    }
  };

  const renderPdfPage = async (pageNumber) => {
    if (!pdfDoc || !canvasRef.current) return;
    try {
      // Clean up outstanding canvas evaluation tasks to avoid threading conflicts
      if (renderTaskRef.current) {
        renderTaskRef.current.cancel();
      }

      const page = await pdfDoc.getPage(pageNumber);
      const canvas = canvasRef.current;
      const context = canvas.getContext('2d');
      
      const parentWidth = canvas.parentElement.clientWidth - 32;
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
      console.warn('Interrupted rendering page thread context:', err);
    }
  };

  // Group fields using the standard hierarchical category arrays
  const categorizedParameters = useMemo(() => {
    const categories = {};
    Object.keys(PARAMETER_GROUPS).forEach((key) => { categories[key] = []; });

    parameters.forEach((param) => {
      let assigned = false;
      for (const [groupName, paramList] of Object.entries(PARAMETER_GROUPS)) {
        const matchesName = paramList.some(p => 
          String(param.param_name).toLowerCase().includes(p.toLowerCase())
        );
        if (matchesName || String(param.header_name).toLowerCase() === groupName.toLowerCase()) {
          categories[groupName].push(param);
          assigned = true;
          break;
        }
      }
      if (!assigned) {
        categories['1. Basic Contract Metadata'].push(param);
      }
    });
    return categories;
  }, [parameters]);

  // Compute absolute highlight dimensions dynamically using injected backend coordinate boundaries
  const overlayStyle = useMemo(() => {
    if (!selectedParameter?.spatial_json?.rects || !canvasRef.current) return null;
    const spatial = selectedParameter.spatial_json;
    if (spatial.char_fallback) return null; // Skip rendering text backups on raw layout overlays

    const [rect] = spatial.rects;
    const [x0, y0, x1, y1] = rect;
    const baseW = spatial.page_width || 612;
    const baseH = spatial.page_height || 792;

    const currentW = canvasRef.current.width;
    const currentH = canvasRef.current.height;

    // Convert raw structural bounding boxes to proportional layout offsets
    return {
      left: `${(x0 / baseW) * currentW}px`,
      top: `${(y0 / baseH) * currentH}px`,
      width: `${((x1 - x0) / baseW) * currentW}px`,
      height: `${((y1 - y0) / baseH) * currentH}px`,
      position: 'absolute',
      backgroundColor: 'rgba(245, 158, 11, 0.35)',
      border: '2px solid rgb(217, 119, 6)',
      pointerEvents: 'none',
      borderRadius: '4px',
      transition: 'all 0.15s cubic-bezier(0.4, 0, 0.2, 1)',
    };
  }, [selectedParameter, selectedParamId, pdfDoc]);

  // Execute stage changes back to database constraints
  const executeWorkflowTransition = async (action) => {
    try {
      const payload = { comment: 'Action executed via Extraction Workbench Panel.', modified_by: 'Current User' };
      if (action === 'submit') {
        await api.submitForApproval(contractId, payload);
        setWorkflowStatus('PENDING_APPROVAL');
      } else if (action === 'approve') {
        await api.approveContract(contractId, payload);
        setWorkflowStatus('APPROVED');
      }
    } catch (err) {
      console.error('Failed to change workflow state:', err);
    }
  };

  return (
    <div className="flex flex-col gap-md w-full min-h-screen p-md text-slate-900 bg-slate-50">
      {/* Structural Workbench Controls Header */}
      <div className="flex flex-wrap justify-between items-center gap-sm bg-white p-md rounded-2xl border border-slate-200 shadow-sm">
        <div>
          <h1 className="text-2xl font-black text-slate-900 tracking-tight">Structured Pipeline Verification</h1>
          <div className="flex items-center gap-xs mt-1">
            <span className="text-xs font-mono text-slate-500 bg-slate-100 px-sm py-[2px] rounded-md">{contractId}</span>
            <span className={`text-[10px] font-black uppercase tracking-wider px-sm py-[2px] rounded-full ${
              workflowStatus === 'APPROVED' ? 'bg-emerald-100 text-emerald-800' : 
              workflowStatus === 'PENDING_APPROVAL' ? 'bg-amber-100 text-amber-800' : 'bg-blue-100 text-blue-800'
            }`}>
              {workflowStatus || 'STAGED_DRAFT'}
            </span>
          </div>
        </div>

        <div className="flex items-center gap-xs">
          {workflowStatus !== 'APPROVED' && workflowStatus !== 'PENDING_APPROVAL' && (
            <button
              type="button"
              onClick={() => executeWorkflowTransition('submit')}
              className="bg-amber-600 hover:bg-amber-700 text-white text-xs font-bold px-md py-sm rounded-xl shadow-sm transition-colors"
            >
              Submit for Approval
            </button>
          )}
          {workflowStatus === 'PENDING_APPROVAL' && (
            <button
              type="button"
              onClick={() => executeWorkflowTransition('approve')}
              className="bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold px-md py-sm rounded-xl shadow-sm transition-colors"
            >
              Approve & Commit Metadata
            </button>
          )}
          <button
            type="button"
            onClick={() => navigate('/verification')}
            className="border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 text-xs font-bold px-md py-sm rounded-xl transition-colors"
          >
            Exit Workspace
          </button>
        </div>
      </div>

      {error && (
        <div className="p-sm rounded-xl border border-rose-200 bg-rose-50 text-rose-700 text-sm font-semibold shadow-sm">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-[1fr_480px] gap-md items-start w-full">
        {/* Render Frame Window: Interactive PDF Viewer Panel */}
        <div className="bg-white border border-slate-200 rounded-2xl p-md shadow-sm flex flex-col items-center justify-center min-h-[780px]">
          <div className="w-full flex justify-between items-center border-b border-slate-100 pb-sm mb-md">
            <h2 className="font-bold text-sm text-slate-800">Visual PDF Target Preview Matrix</h2>
            {selectedParameter?.spatial_json?.page && (
              <span className="text-xs font-bold text-amber-700 bg-amber-50 px-sm py-[2px] rounded-md">
                Displaying Target Page: {selectedParameter.spatial_json.page}
              </span>
            )}
          </div>

          {pdfLoading ? (
            <div className="text-xs font-semibold text-slate-400 animate-pulse">Streaming object canvas views...</div>
          ) : (
            <div className="relative border border-slate-200 bg-slate-100 rounded-xl overflow-hidden p-2 shadow-inner">
              <canvas ref={canvasRef} className="block shadow-sm rounded-lg" />
              {/* Proportional Render Box Container */}
              {overlayStyle && <div style={overlayStyle} className="animate-pulse" />}
            </div>
          )}

          {selectedParameter?.citation_text && (
            <div className="w-full mt-md p-md border border-slate-100 bg-slate-50 rounded-xl">
              <span className="text-[10px] font-black uppercase tracking-wider text-slate-400">Azure Ground Truth Citation Source</span>
              <p className="text-xs text-slate-700 mt-1 leading-relaxed italic">"{selectedParameter.citation_text}"</p>
            </div>
          )}
        </div>

        {/* Action Panel Window: Hierarchical Category Groupings */}
        <div className="space-y-sm max-h-[820px] overflow-y-auto pr-1">
          {Object.entries(PARAMETER_GROUPS).map(([groupName]) => {
            const matches = categorizedParameters[groupName] || [];
            const isOpen = activeGroup === groupName;

            return (
              <div key={groupName} className="border border-slate-200 bg-white rounded-2xl overflow-hidden shadow-sm transition-all">
                <button
                  type="button"
                  onClick={() => setActiveGroup(isOpen ? '' : groupName)}
                  className={`w-full flex justify-between items-center p-md text-left font-bold text-xs transition-colors ${
                    isOpen ? 'bg-slate-900 text-white' : 'bg-white text-slate-800 hover:bg-slate-50'
                  }`}
                >
                  <span>{groupName}</span>
                  <span className={`px-sm py-[2px] rounded-full text-[10px] font-black ${
                    isOpen ? 'bg-white/20 text-white' : 'bg-slate-100 text-slate-600'
                  }`}>
                    {matches.length} Fields
                  </span>
                </button>

                {isOpen && (
                  <div className="p-md space-y-md bg-slate-50/50 border-t border-slate-100 max-h-[460px] overflow-y-auto">
                    {matches.length === 0 ? (
                      <p className="text-xs text-slate-400 p-sm italic text-center">No extraction rows populated for this rule parameter category.</p>
                    ) : (
                      matches.map((param) => {
                        const isSelected = selectedParamId === param.parameter_id;
                        return (
                          <div
                            key={param.parameter_id}
                            onClick={() => setSelectedParamId(param.parameter_id)}
                            className={`p-md border rounded-xl transition-all ${
                              isSelected 
                                ? 'border-amber-500 bg-amber-500/5 shadow-sm ring-1 ring-amber-500/20' 
                                : 'border-slate-200 bg-white hover:border-slate-300'
                            }`}
                          >
                            <div className="flex justify-between items-start gap-sm mb-sm">
                              <span className="text-xs font-bold text-slate-800">{param.param_name}</span>
                              {param.match_score ? (
                                <span className="text-[10px] font-mono font-bold px-sm py-[2px] bg-slate-100 rounded-md text-slate-500">
                                  Conf: {(param.match_score * 100).toFixed(0)}%
                                </span>
                              ) : null}
                            </div>

                            <input
                              type="text"
                              disabled={busy || workflowStatus === 'APPROVED'}
                              className="w-full bg-white border border-slate-200 focus:border-amber-500 rounded-xl px-sm py-sm text-xs shadow-inner outline-none transition-all disabled:opacity-60"
                              defaultValue={param.user_override || param.original_extract || ''}
                              onBlur={(e) => updateParameter(param.parameter_id, e.target.value)}
                              onClick={(e) => e.stopPropagation()} // Stop click capture bubblings
                            />
                          </div>
                        );
                      })
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};

export default Extraction;