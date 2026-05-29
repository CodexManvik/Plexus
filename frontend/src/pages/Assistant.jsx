import React, { useEffect, useMemo, useState, useRef } from 'react';
import { api } from '../services/api';

const examplePrompts = [
  'Summarize the termination rights and notice period.',
  'What payment and liability terms should I highlight?',
  'List the confidentiality and data handling obligations.',
];

const Assistant = () => {
  const [documents, setDocuments] = useState([]);
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedIds, setSelectedIds] = useState([]);
  const [question, setQuestion] = useState(examplePrompts[0]);
  const [answer, setAnswer] = useState('');
  const [sources, setSources] = useState([]);
  const [loadingDocuments, setLoadingDocuments] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  // PDF.js grounded rendering state
  const [activeContractId, setActiveContractId] = useState(null);
  const [pdfDoc, setPdfDoc] = useState(null);
  const [pdfLoading, setPdfLoading] = useState(false);
  const [currentPage, setCurrentPage] = useState(1);
  const [activeSpatialJson, setActiveSpatialJson] = useState(null);

  const canvasRef = useRef(null);
  const containerRef = useRef(null);
  const renderTaskRef = useRef(null);

  // Load PDF document for the active grounded source
  const loadPdfDocument = React.useCallback(async (contractId) => {
    if (!contractId || !window.pdfjsLib) return;
    try {
      setPdfLoading(true);
      const fileUrl = `${import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api'}/contracts/${contractId}/document`;
      const loadingTask = window.pdfjsLib.getDocument(fileUrl);
      const doc = await loadingTask.promise;
      setPdfDoc(doc);
    } catch (err) {
      console.error('Failed to load PDF representation:', err);
    } finally {
      setPdfLoading(false);
    }
  }, []);

  // Initialize PDF.js CDN
  useEffect(() => {
    if (window.pdfjsLib) {
      if (activeContractId) loadPdfDocument(activeContractId);
      return;
    }
    setPdfLoading(true);
    const script = document.createElement('script');
    script.src = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.4.120/pdf.min.js';
    script.onload = () => {
      window.pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.4.120/pdf.worker.min.js';
      setPdfLoading(false);
      if (activeContractId) loadPdfDocument(activeContractId);
    };
    document.head.appendChild(script);
  }, [activeContractId, loadPdfDocument]);

  // Fetch list of documents for corpus selection
  useEffect(() => {
    let active = true;
    const loadDocuments = async () => {
      setLoadingDocuments(true);
      setError('');
      try {
        const response = await api.listContracts({ limit: 100 });
        if (!active) return;
        const items = response.data || [];
        setDocuments(items);
        setSelectedIds(items.slice(0, 3).map((item) => item.contract_id));
      } catch (err) {
        if (active) {
          setError(err.response?.data?.detail || err.message || 'Failed to load documents.');
        }
      } finally {
        if (active) {
          setLoadingDocuments(false);
        }
      }
    };
    loadDocuments();
    return () => {
      active = false;
    };
  }, []);

  // Filter documents by search term
  const filteredDocuments = useMemo(() => {
    const term = searchTerm.trim().toLowerCase();
    if (!term) return documents;
    return documents.filter((item) => {
      const haystack = [
        item.contract_id,
        item.contract_type,
        item.agreement_type,
        item.organization,
        item.business_unit,
        item.customer_partner_name,
      ].filter(Boolean).join(' ').toLowerCase();
      return haystack.includes(term);
    });
  }, [documents, searchTerm]);



  // Load PDF when active contract shifts
  useEffect(() => {
    if (activeContractId) {
      loadPdfDocument(activeContractId);
    }
  }, [activeContractId, loadPdfDocument]);

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
      
      let parentWidth = containerRef.current ? containerRef.current.clientWidth - 16 : 400;
      if (parentWidth <= 0) parentWidth = 400;
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

  // Re-render page when document or page changes
  useEffect(() => {
    if (pdfDoc) {
      renderPdfPage(currentPage);
    }
  }, [pdfDoc, currentPage, renderPdfPage]);

  // Click handler for grounded sources
  const handleGroundSourceClick = (source) => {
    setActiveContractId(source.contract_id);
    setActiveSpatialJson(source.spatial_json);
    if (source.spatial_json?.page) {
      setCurrentPage(Number(source.spatial_json.page));
    } else {
      setCurrentPage(1);
    }
  };

  // Grounded source highlight style
  const overlayStyle = useMemo(() => {
    if (!activeSpatialJson?.rects) return null;
    if (Number(currentPage) !== Number(activeSpatialJson.page)) return null;

    const [rect] = activeSpatialJson.rects;
    const [x0, y0, x1, y1] = rect;
    const baseW = activeSpatialJson.page_width || 612;
    const baseH = activeSpatialJson.page_height || 792;

    return {
      left: `${(x0 / baseW) * 100}%`,
      top: `${(y0 / baseH) * 100}%`,
      width: `${((x1 - x0) / baseW) * 100}%`,
      height: `${((y1 - y0) / baseH) * 100}%`,
      position: 'absolute',
      backgroundColor: 'rgba(59, 130, 246, 0.25)', // Bright digital blue translucent overlay
      border: '2px solid rgb(59, 130, 246)',
      pointerEvents: 'none',
      borderRadius: '4px',
      transition: 'all 0.15s cubic-bezier(0.4, 0, 0.2, 1)',
    };
  }, [activeSpatialJson, currentPage]);

  const toggleSelection = (contractId) => {
    setSelectedIds((current) =>
      current.includes(contractId)
        ? current.filter((id) => id !== contractId)
        : [...current, contractId]
    );
  };

  const askQuestion = async (event) => {
    event.preventDefault();
    if (!selectedIds.length) {
      setError('Select at least one document before asking a question.');
      return;
    }

    setSubmitting(true);
    setError('');
    try {
      const response = await api.askAssistant({
        question,
        contract_ids: selectedIds,
        top_k: 4,
      });
      setAnswer(response.answer || 'No answer returned.');
      setSources(response.sources || []);
      
      // Auto-ground to first source returned
      if (response.sources?.length > 0) {
        handleGroundSourceClick(response.sources[0]);
      }
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Failed to ask assistant.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="flex flex-col gap-md w-full min-h-[calc(100vh-6rem)] p-md text-slate-100 bg-slate-950 font-sans">
      {/* Header Panel */}
      <div className="rounded-3xl border border-slate-800 bg-gradient-to-r from-slate-950 via-slate-900 to-slate-950 p-lg shadow-xl shrink-0">
        <p className="text-[10px] font-black uppercase tracking-[0.35em] text-pink-500">AI Grounded Assistant</p>
        <h1 className="mt-sm text-2xl font-black text-slate-100 tracking-tight flex items-center gap-xs">
          <span className="material-symbols-outlined text-blue-500">forum</span>
          Layout-Aware RAG Workspace
        </h1>
        <p className="mt-xs max-w-4xl text-xs text-slate-400 leading-relaxed">
          Select target documents from the corpus, ask any business query, and click on any returned evidence snippet to instantly view and highlight the exact citation bounding box on the original PDF sheet.
        </p>
      </div>

      {error && (
        <div className="p-sm rounded-xl border border-rose-500/20 bg-rose-500/10 text-rose-400 text-xs font-semibold shrink-0">
          {error}
        </div>
      )}

      {/* Split Screen Viewport Grid */}
      <div className="grid grid-cols-1 xl:grid-cols-[1fr_420px] gap-md h-[calc(100vh-16rem)] min-h-[500px]">
        {/* LEFT COLUMN: Conversational search + selection */}
        <div className="grid grid-cols-1 md:grid-cols-[280px_1fr] gap-md overflow-hidden h-full">
          {/* Document selection tree */}
          <div className="bg-slate-900/40 border border-slate-800 rounded-2xl flex flex-col overflow-hidden h-full">
            <div className="p-md border-b border-slate-800 bg-slate-900/60 shrink-0 flex justify-between items-center">
              <div>
                <h2 className="text-xs font-black text-slate-200 uppercase tracking-widest">Select Corpus</h2>
                <p className="text-[9px] text-slate-500 mt-[2px]">Target parameters search</p>
              </div>
              <span className="text-[10px] font-bold text-blue-400 bg-blue-500/10 px-sm py-[2px] rounded-full border border-blue-500/20">
                {selectedIds.length} selected
              </span>
            </div>

            <div className="p-sm border-b border-slate-800 shrink-0">
              <input
                className="w-full bg-slate-950 border border-slate-800 rounded-xl px-sm py-xs text-xs text-slate-200 outline-none focus:border-blue-500 transition-all"
                placeholder="Filter contracts..."
                value={searchTerm}
                onChange={(event) => setSearchTerm(event.target.value)}
              />
            </div>

            <div className="flex-1 overflow-y-auto p-sm space-y-xs custom-scrollbar">
              {loadingDocuments ? (
                <div className="text-[10px] text-slate-500 italic animate-pulse p-sm">Loading corpus...</div>
              ) : filteredDocuments.length === 0 ? (
                <div className="text-[10px] text-slate-500 italic p-sm">No contracts found.</div>
              ) : (
                filteredDocuments.map((doc) => {
                  const isChecked = selectedIds.includes(doc.contract_id);
                  return (
                    <label
                      key={doc.contract_id}
                      className={`flex cursor-pointer items-start gap-xs rounded-xl border p-sm transition-all ${
                        isChecked
                          ? 'bg-slate-800/60 border-slate-700'
                          : 'bg-transparent border-transparent hover:bg-slate-900/20'
                      }`}
                    >
                      <input
                        type="checkbox"
                        checked={isChecked}
                        onChange={() => toggleSelection(doc.contract_id)}
                        className="mt-1 h-3.5 w-3.5 accent-blue-500"
                      />
                      <div className="min-w-0 flex-1">
                        <p className="text-[11px] font-bold text-slate-200 truncate">{doc.contract_id}</p>
                        <p className="text-[10px] text-slate-400 truncate font-semibold">{doc.contract_type}</p>
                        <p className="text-[9px] text-slate-500 truncate">{doc.customer_partner_name || 'No partner'}</p>
                      </div>
                    </label>
                  );
                })
              )}
            </div>
          </div>

          {/* Assistant conversation column */}
          <div className="flex flex-col h-full overflow-hidden space-y-md">
            {/* Ask panel */}
            <form
              onSubmit={askQuestion}
              className="bg-slate-900/40 border border-slate-800 rounded-2xl p-md shrink-0 flex flex-col gap-sm"
            >
              <div className="flex items-center justify-between gap-sm">
                <div>
                  <h3 className="text-xs font-black text-slate-200 uppercase tracking-widest">Ask Business Query</h3>
                  <p className="text-[9px] text-slate-500 mt-[2px]">Azure OpenAI / Cohere active reasoning</p>
                </div>
                <button
                  type="submit"
                  disabled={submitting || selectedIds.length === 0}
                  className="bg-primary hover:opacity-90 text-on-primary text-xs font-bold px-md py-[6px] rounded-xl shadow-md transition-all disabled:opacity-40"
                >
                  {submitting ? 'Searching...' : 'Search'}
                </button>
              </div>

              <textarea
                className="w-full bg-slate-950 border border-slate-800 focus:border-blue-500/80 rounded-xl p-sm text-xs text-slate-200 outline-none transition-all resize-none h-20"
                placeholder="Ask about payments, expirations, caps, termination clauses..."
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
              />

              <div className="flex flex-wrap gap-xs">
                {examplePrompts.map((prompt) => (
                  <button
                    key={prompt}
                    type="button"
                    onClick={() => setQuestion(prompt)}
                    className="rounded-full border border-slate-800 bg-slate-900/60 px-sm py-[3px] text-[9px] text-slate-400 transition-all hover:border-slate-700 hover:text-slate-200"
                  >
                    {prompt}
                  </button>
                ))}
              </div>
            </form>

            {/* Answer feed pane */}
            <div className="flex-1 overflow-y-auto bg-slate-900/20 border border-slate-800 rounded-2xl p-md custom-scrollbar flex flex-col gap-md">
              <div className="space-y-xs shrink-0">
                <span className="text-[10px] text-pink-500 font-bold uppercase tracking-wider">Semantic Synthesis</span>
                {answer ? (
                  <p className="text-xs leading-relaxed text-slate-200 bg-slate-950/40 p-md rounded-2xl border border-slate-800/80 whitespace-pre-wrap">
                    {answer}
                  </p>
                ) : (
                  <p className="text-xs text-slate-500 italic">Ask a query above to generate a grounded RAG response.</p>
                )}
              </div>

              {/* Source snippets used */}
              {sources.length > 0 && (
                <div className="space-y-sm">
                  <span className="text-[10px] text-blue-400 font-bold uppercase tracking-wider">Grounding Source Citations</span>
                  <div className="grid grid-cols-1 gap-sm">
                    {sources.map((source, idx) => {
                      const isGrounded = activeContractId === source.contract_id && activeSpatialJson === source.spatial_json;
                      return (
                        <button
                          key={idx}
                          type="button"
                          onClick={() => handleGroundSourceClick(source)}
                          className={`w-full text-left p-sm rounded-xl border transition-all flex flex-col gap-xs ${
                            isGrounded
                              ? 'bg-slate-800/60 border-slate-700 shadow-md ring-1 ring-slate-700/50'
                              : 'bg-slate-900/30 border-slate-800 hover:bg-slate-900/60'
                          }`}
                        >
                          <div className="flex justify-between items-center w-full">
                            <span className="text-[10px] text-pink-400 font-bold">{source.contract_id}</span>
                            <span className="text-[9px] text-slate-500 font-mono">Score: {source.score.toFixed(2)}</span>
                          </div>
                          <span className="text-xs font-black text-slate-200 leading-tight">{source.title}</span>
                          <p className="text-[10px] leading-relaxed text-slate-400 line-clamp-3 italic">
                            "{source.snippet}"
                          </p>
                          {source.spatial_json?.page && (
                            <span className="text-[8px] font-black uppercase text-blue-400 bg-blue-500/10 px-sm py-[2px] rounded-full border border-blue-500/20 self-start mt-xs flex items-center gap-[2px]">
                              <span className="material-symbols-outlined text-[10px]">location_on</span>
                              Grounded: Page {source.spatial_json.page}
                            </span>
                          )}
                        </button>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>

        {/* RIGHT COLUMN: Interactive Grounded PDF Viewport */}
        <div className="bg-slate-900/40 border border-slate-800 rounded-2xl flex flex-col overflow-hidden h-full" ref={containerRef}>
          <div className="p-sm bg-slate-900/60 border-b border-slate-800 shrink-0 flex items-center justify-between">
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
            <span className="text-[9px] text-slate-500 font-mono truncate max-w-[150px]">
              {activeContractId ? `Viewing: ${activeContractId}` : 'No active source'}
            </span>
          </div>

          <div className="flex-1 overflow-auto p-md flex items-start justify-center relative bg-slate-950 custom-scrollbar">
            {activeContractId ? (
              <div className="relative border border-slate-800 shadow-2xl rounded-lg overflow-hidden bg-white shrink-0">
                <canvas ref={canvasRef} />
                {overlayStyle && <div style={overlayStyle} />}
              </div>
            ) : (
              <div className="text-slate-500 italic text-xs text-center p-xl flex flex-col items-center justify-center gap-xs h-full">
                <span className="material-symbols-outlined text-3xl text-slate-700">visibility</span>
                Evidence Canvas Grounder
                <p className="text-[10px] text-slate-600 font-normal mt-1 leading-normal max-w-[200px]">
                  Click on any RAG Grounding Source Citation on the left to paint its layout bounding box.
                </p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default Assistant;