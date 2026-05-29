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
    busy,
    error: hookError,
    refresh,
    updateParameter,
  } = useExtraction();

  const [activeGroup, setActiveGroup] = useState('1. Basic Contract Metadata');
  const [pdfDoc, setPdfDoc] = useState(null);
  const [pdfLoading, setPdfLoading] = useState(false);
  const [workflowStatus, setWorkflowStatus] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const [customError, setCustomError] = useState('');
  const [customSuccess, setCustomSuccess] = useState('');
  const [checkpointComment, setCheckpointComment] = useState('');
  const [showPauseModal, setShowPauseModal] = useState(false);
  
  // Tag suggestions state when contract is in TAG_SUGGESTION_READY status
  const [tagSuggestions, setTagSuggestions] = useState(null);
  const [suggestionsLoading, setSuggestionsLoading] = useState(false);
  const [editingSuggestions, setEditingSuggestions] = useState(false);
  
  // Edited values for tag suggestions
  const [editedContractType, setEditedContractType] = useState('');
  const [editedBusinessUnit, setEditedBusinessUnit] = useState('');
  const [editedJurisdiction, setEditedJurisdiction] = useState('');

  // Expandable state for parameter versioning accordions
  const [expandedVersionId, setExpandedVersionId] = useState(null);

  const canvasRef = useRef(null);
  const containerRef = useRef(null);
  const renderTaskRef = useRef(null);

  const error = hookError || customError;

  // 1. loadPdfDocument wrapped in useCallback
  const loadPdfDocument = React.useCallback(async () => {
    if (!contractId || !window.pdfjsLib) return;
    try {
      setPdfLoading(true);
      const fileUrl = `${import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api'}/contracts/${contractId}/document`;
      const loadingTask = window.pdfjsLib.getDocument(fileUrl);
      const doc = await loadingTask.promise;
      setPdfDoc(doc);
    } catch (err) {
      console.error('Failed to parse document stream:', err);
      setCustomError('Failed to load PDF document representation.');
    } finally {
      setPdfLoading(false);
    }
  }, [contractId]);

  // 2. loadTagSuggestions wrapped in useCallback
  const loadTagSuggestions = React.useCallback(async () => {
    try {
      setSuggestionsLoading(true);
      const suggestions = await api.getTagSuggestions(contractId);
      setTagSuggestions(suggestions);
      
      // Initialize edit fields
      setEditedContractType(suggestions.contract_type?.value || '');
      setEditedBusinessUnit(suggestions.business_unit?.value || '');
      setEditedJurisdiction(suggestions.jurisdiction?.value || '');
    } catch (err) {
      console.error('Failed to load tag suggestions:', err);
      setCustomError('Failed to retrieve suggested metadata tags.');
    } finally {
      setSuggestionsLoading(false);
    }
  }, [contractId]);

  // 3. renderPdfPage wrapped in useCallback
  const renderPdfPage = React.useCallback(async (pageNumber) => {
    if (!pdfDoc || !canvasRef.current) return;
    try {
      if (renderTaskRef.current) {
        renderTaskRef.current.cancel();
      }

      const page = await pdfDoc.getPage(pageNumber);
      const canvas = canvasRef.current;
      const context = canvas.getContext('2d');
      
      let parentWidth = containerRef.current ? containerRef.current.clientWidth - 32 : 800;
      if (parentWidth <= 0) parentWidth = 800;
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
  }, [pdfDoc]);

  // Synchronize internal status tracking when contract record completes mapping hydration
  useEffect(() => {
    if (contract?.workflow_state) {
      setWorkflowStatus(contract.workflow_state);
      
      // Load tag suggestions if in TAG_SUGGESTION_READY state
      if (contract.workflow_state === 'TAG_SUGGESTION_READY') {
        loadTagSuggestions();
      }
    }
  }, [contract, loadTagSuggestions]);

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
  }, [loadPdfDocument]);

  // Re-fetch document binary instances when state triggers change
  useEffect(() => {
    if (window.pdfjsLib && contractId) {
      loadPdfDocument();
    }
  }, [contractId, loadPdfDocument]);

  // Synchronize page when selected parameter changes
  useEffect(() => {
    const targetPage = selectedParameter?.spatial_json?.page;
    if (targetPage) {
      setCurrentPage(Number(targetPage));
    }
  }, [selectedParamId, selectedParameter]);

  // Render page when PDF document loads or current page shifts
  useEffect(() => {
    if (pdfDoc) {
      renderPdfPage(currentPage);
    }
  }, [pdfDoc, currentPage, renderPdfPage]);

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

  // Compute absolute highlight dimensions dynamically using pure percentage based CSS!
  const overlayStyle = useMemo(() => {
    if (!selectedParameter?.spatial_json?.rects) return null;
    const spatial = selectedParameter.spatial_json;
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
      backgroundColor: 'rgba(245, 158, 11, 0.35)',
      border: '2px solid rgb(217, 119, 6)',
      pointerEvents: 'none',
      borderRadius: '4px',
      transition: 'all 0.15s cubic-bezier(0.4, 0, 0.2, 1)',
    };
  }, [selectedParameter, currentPage]);

  const executeWorkflowTransition = async (action) => {
    setCustomError('');
    setCustomSuccess('');
    try {
      const currentUser = JSON.parse(localStorage.getItem('currentUser') || '{}');
      const payload = { comment: 'Action executed via Extraction Workbench Panel.', modified_by: currentUser.id || 'Current User' };
      
      if (action === 'submit') {
        await api.submitForApproval(contractId, payload);
        setWorkflowStatus('PENDING_APPROVAL');
        setCustomSuccess('Contract successfully submitted to approvals queue!');
        await refresh();
      } else if (action === 'approve') {
        await api.approveContract(contractId, payload);
        setWorkflowStatus('APPROVED');
        setCustomSuccess('Contract successfully approved and knowledge base promoted!');
        await refresh();
      }
    } catch (err) {
      console.error('Failed to change workflow state:', err);
      setCustomError(err.response?.data?.detail || 'Failed to trigger state transition.');
    }
  };

  const handleAcceptSuggestions = async () => {
    setCustomError('');
    setCustomSuccess('');
    try {
      const currentUser = JSON.parse(localStorage.getItem('currentUser') || '{}');
      await api.acceptTags(contractId, { modified_by: currentUser.id || 'Current User' });
      setCustomSuccess('Suggested tags accepted. Ingestion pipeline triggered successfully!');
      await refresh();
    } catch (err) {
      console.error('Failed to accept tags suggestions:', err);
      setCustomError(err.response?.data?.detail || 'Failed to confirm suggested tags.');
    }
  };

  const handleEditSuggestionsSubmit = async (e) => {
    e.preventDefault();
    setCustomError('');
    setCustomSuccess('');
    try {
      const currentUser = JSON.parse(localStorage.getItem('currentUser') || '{}');
      await api.editTags(contractId, {
        modified_by: currentUser.id || 'Current User',
        contract_type: editedContractType,
        business_unit: editedBusinessUnit,
        jurisdiction: editedJurisdiction,
      });
      setCustomSuccess('Tags modified and ingestion pipeline executed successfully!');
      setEditingSuggestions(false);
      await refresh();
    } catch (err) {
      console.error('Failed to save edited tags:', err);
      setCustomError(err.response?.data?.detail || 'Failed to submit tags modifications.');
    }
  };

  const handlePauseDraft = async () => {
    setCustomError('');
    setCustomSuccess('');
    try {
      const currentUser = JSON.parse(localStorage.getItem('currentUser') || '{}');
      await api.pauseDraft(contractId, {
        comment: checkpointComment || 'Draft paused by user.',
        modified_by: currentUser.id || 'Current User'
      });
      setCustomSuccess('Review state checkpoint successfully saved on server.');
      setShowPauseModal(false);
      await refresh();
    } catch (err) {
      console.error('Failed to pause draft:', err);
      setCustomError(err.response?.data?.detail || 'Failed to save review draft.');
    }
  };

  const handleResumeDraft = async () => {
    setCustomError('');
    setCustomSuccess('');
    try {
      const currentUser = JSON.parse(localStorage.getItem('currentUser') || '{}');
      await api.resumeDraft(contractId, {
        modified_by: currentUser.id || 'Current User'
      });
      setCustomSuccess('Review state checkpoint successfully loaded from database.');
      await refresh();
    } catch (err) {
      console.error('Failed to resume draft:', err);
      setCustomError(err.response?.data?.detail || 'Failed to restore review draft.');
    }
  };

  const handleToggleVerification = async (param) => {
    setCustomError('');
    try {
      const currentUser = JSON.parse(localStorage.getItem('currentUser') || '{}');
      await api.verifyParameter(contractId, param.parameter_id, {
        is_correct: !param.is_verified,
        verification_note: param.is_verified ? 'Unmarked verified by user' : 'Verified by user in workbench',
        modified_by: currentUser.id || 'Current User'
      });
      await refresh();
    } catch (err) {
      console.error('Failed to verify parameter:', err);
      setCustomError(err.response?.data?.detail || 'Failed to toggle parameter verification state.');
    }
  };

  // Helper colors for validation states
  const getValidationStyles = (state) => {
    switch (state) {
      case 'valid':
        return { bg: 'bg-emerald-50 border-emerald-200 text-emerald-800', badge: 'bg-emerald-100 text-emerald-800', icon: '✓', label: 'Deterministic Pass' };
      case 'invalid':
        return { bg: 'bg-rose-50 border-rose-200 text-rose-800', badge: 'bg-rose-100 text-rose-800', icon: '✗', label: 'Validation Failure' };
      case 'needs_review':
        return { bg: 'bg-amber-50 border-amber-200 text-amber-800', badge: 'bg-amber-100 text-amber-800', icon: '⚠', label: 'Review Suggested' };
      case 'missing_evidence':
        return { bg: 'bg-slate-100 border-slate-200 text-slate-700', badge: 'bg-slate-200 text-slate-800', icon: '?', label: 'Missing Evidence' };
      case 'ambiguous':
        return { bg: 'bg-indigo-50 border-indigo-200 text-indigo-800', badge: 'bg-indigo-100 text-indigo-800', icon: '◆', label: 'Ambiguous' };
      default:
        return { bg: 'bg-slate-50 border-slate-200 text-slate-800', badge: 'bg-slate-100 text-slate-800', icon: '•', label: 'Needs Review' };
    }
  };

  // Helper colors for confidence score badges
  const getConfidenceBadgeStyles = (score) => {
    if (score >= 0.85) return 'bg-emerald-100 text-emerald-800 border-emerald-200';
    if (score >= 0.5) return 'bg-amber-100 text-amber-800 border-amber-200';
    return 'bg-rose-100 text-rose-800 border-rose-200';
  };

  return (
    <div className="flex flex-col gap-md w-full min-h-screen p-md text-slate-900 bg-slate-50 font-sans">
      {/* Structural Workbench Controls Header */}
      <div className="flex flex-wrap justify-between items-center gap-sm bg-white p-md rounded-2xl border border-slate-200 shadow-sm">
        <div>
          <h1 className="text-2xl font-black text-slate-900 tracking-tight">Structured Pipeline Verification</h1>
          <div className="flex items-center gap-xs mt-1 flex-wrap">
            <span className="text-xs font-mono text-slate-500 bg-slate-100 px-sm py-[2px] rounded-md">{contractId}</span>
            <span className="text-[10px] font-bold text-slate-500 bg-slate-100 px-sm py-[2px] rounded-md">V{contract?.document_version || 1}</span>
            <span className={`text-[10px] font-black uppercase tracking-wider px-sm py-[2px] rounded-full ${
              workflowStatus === 'APPROVED' ? 'bg-emerald-100 text-emerald-800 border border-emerald-200' : 
              workflowStatus === 'PENDING_APPROVAL' ? 'bg-amber-100 text-amber-800 border border-amber-200' : 
              workflowStatus === 'TAG_SUGGESTION_READY' ? 'bg-purple-100 text-purple-800 border border-purple-200' :
              workflowStatus === 'REVIEW_PENDING' ? 'bg-rose-100 text-rose-800 border border-rose-200' : 'bg-blue-100 text-blue-800 border border-blue-200'
            }`}>
              {workflowStatus || 'STAGED_DRAFT'}
            </span>
            {contract?.checked_out_by && (
              <span className="text-[10px] text-slate-500 bg-slate-100 px-sm py-[2px] rounded-md">
                Locked by: {contract.checked_out_by}
              </span>
            )}
          </div>
        </div>

        <div className="flex items-center gap-xs flex-wrap">
          {/* Pause Draft Actions */}
          {workflowStatus !== 'APPROVED' && (
            <button
              type="button"
              onClick={() => setShowPauseModal(true)}
              className="border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 text-xs font-bold px-md py-sm rounded-xl transition-all shadow-sm"
            >
              Pause Draft
            </button>
          )}

          {contract?.draft_checkpoint && workflowStatus !== 'APPROVED' && (
            <button
              type="button"
              onClick={handleResumeDraft}
              className="bg-indigo-50 border border-indigo-200 hover:bg-indigo-100 text-indigo-700 text-xs font-bold px-md py-sm rounded-xl transition-all shadow-sm"
              title="Restore last paused session checkpoint"
            >
              Resume Checkpoint
            </button>
          )}

          {/* Workflow Transitions */}
          {workflowStatus !== 'APPROVED' && workflowStatus !== 'PENDING_APPROVAL' && workflowStatus !== 'TAG_SUGGESTION_READY' && (
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
        <div className="p-sm rounded-xl border border-rose-200 bg-rose-50 text-rose-700 text-sm font-semibold shadow-sm animate-pulse">
          {error}
        </div>
      )}

      {customSuccess && (
        <div className="p-sm rounded-xl border border-emerald-200 bg-emerald-50 text-emerald-700 text-sm font-semibold shadow-sm">
          {customSuccess}
        </div>
      )}

      {/* Resumed Checkpoint Notice */}
      {contract?.draft_checkpoint && (
        <div className="p-md rounded-2xl border border-indigo-100 bg-indigo-50/50 text-indigo-800 text-xs flex justify-between items-center shadow-sm">
          <div className="flex items-center gap-xs">
            <span className="text-base font-black">ℹ</span>
            <div>
              <p className="font-bold">Active Draft Checkpoint Saved</p>
              <p className="text-slate-500 font-mono mt-[2px]">{contract.draft_checkpoint}</p>
            </div>
          </div>
        </div>
      )}

      {/* Pause Draft Modal */}
      {showPauseModal && (
        <div className="fixed inset-0 bg-slate-900/40 backdrop-blur-sm z-50 flex items-center justify-center p-md">
          <div className="bg-white border border-slate-200 rounded-3xl p-lg shadow-xl max-w-md w-full space-y-md animate-in fade-in zoom-in-95 duration-150">
            <h3 className="text-lg font-black text-slate-900">Pause Active Review Draft</h3>
            <p className="text-xs text-slate-500 leading-relaxed">
              This will serialize your current cell overrides, parameter verification states, and active session variables directly to Oracle 23ai's master repository. You can resume this session exactly where you left off.
            </p>
            <div className="space-y-xs">
              <label htmlFor="comment" className="text-[10px] font-black uppercase tracking-wider text-slate-400">Checkpoint Comment / Progress Note</label>
              <input
                id="comment"
                type="text"
                value={checkpointComment}
                onChange={(e) => setCheckpointComment(e.target.value)}
                placeholder="e.g. Completed Section 1, waiting on vendor confirmation..."
                className="w-full bg-slate-50 border border-slate-200 focus:border-amber-500 focus:bg-white rounded-xl px-md py-sm text-xs outline-none transition-all"
              />
            </div>
            <div className="flex justify-end gap-xs pt-sm">
              <button
                type="button"
                onClick={() => setShowPauseModal(false)}
                className="border border-slate-200 hover:bg-slate-50 text-slate-700 text-xs font-bold px-md py-sm rounded-xl transition-all"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handlePauseDraft}
                className="bg-amber-600 hover:bg-amber-700 text-white text-xs font-bold px-md py-sm rounded-xl shadow-sm transition-all"
              >
                Save & Pause Draft
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-[1fr_480px] gap-md items-start w-full">
        {/* Left Pane: interactive Viewer or Tag Classification Panel */}
        <div className="space-y-md flex flex-col w-full">
          
          {/* Tag Classification Workspace (Workflow State: TAG_SUGGESTION_READY) */}
          {workflowStatus === 'TAG_SUGGESTION_READY' && (
            <div className="bg-white border border-slate-200 rounded-3xl p-lg shadow-sm space-y-md">
              <div className="border-b border-slate-100 pb-md">
                <span className="text-[10px] font-black uppercase tracking-wider text-purple-600 bg-purple-50 px-sm py-[2px] rounded-full border border-purple-200">System Pipeline Step 1</span>
                <h2 className="text-xl font-black text-slate-900 mt-sm">Upload-Time Metadata Suggestions</h2>
                <p className="text-xs text-slate-500 mt-1">
                  The AI Agent has completed a first-pass metadata tagging sweep of the contract. Verify or modify the predicted taxonomy below to launch deep-rules parameter extraction.
                </p>
              </div>

              {suggestionsLoading ? (
                <div className="py-xl text-center text-xs text-slate-400 animate-pulse font-semibold">
                  Analyzing uploaded document segments...
                </div>
              ) : tagSuggestions ? (
                <div className="space-y-md">
                  {editingSuggestions ? (
                    <form onSubmit={handleEditSuggestionsSubmit} className="space-y-md bg-slate-50 p-md rounded-2xl border border-slate-200">
                      <h3 className="text-xs font-black text-slate-800">Edit Predicted Classification</h3>
                      <div className="grid grid-cols-1 md:grid-cols-3 gap-md">
                        <div className="space-y-xs">
                          <label htmlFor="ct" className="text-[10px] font-black uppercase tracking-wider text-slate-400">Contract Type</label>
                          <input
                            id="ct"
                            type="text"
                            value={editedContractType}
                            onChange={(e) => setEditedContractType(e.target.value)}
                            className="w-full bg-white border border-slate-200 rounded-xl px-md py-sm text-xs outline-none focus:border-amber-500 transition-all"
                          />
                        </div>
                        <div className="space-y-xs">
                          <label htmlFor="bu" className="text-[10px] font-black uppercase tracking-wider text-slate-400">Business Unit</label>
                          <input
                            id="bu"
                            type="text"
                            value={editedBusinessUnit}
                            onChange={(e) => setEditedBusinessUnit(e.target.value)}
                            className="w-full bg-white border border-slate-200 rounded-xl px-md py-sm text-xs outline-none focus:border-amber-500 transition-all"
                          />
                        </div>
                        <div className="space-y-xs">
                          <label htmlFor="ju" className="text-[10px] font-black uppercase tracking-wider text-slate-400">Jurisdiction</label>
                          <input
                            id="ju"
                            type="text"
                            value={editedJurisdiction}
                            onChange={(e) => setEditedJurisdiction(e.target.value)}
                            className="w-full bg-white border border-slate-200 rounded-xl px-md py-sm text-xs outline-none focus:border-amber-500 transition-all"
                          />
                        </div>
                      </div>
                      <div className="flex justify-end gap-xs pt-xs">
                        <button
                          type="button"
                          onClick={() => setEditingSuggestions(false)}
                          className="border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 text-xs font-bold px-md py-sm rounded-xl transition-all"
                        >
                          Cancel
                        </button>
                        <button
                          type="submit"
                          className="bg-amber-600 hover:bg-amber-700 text-white text-xs font-bold px-md py-sm rounded-xl shadow-sm transition-all"
                        >
                          Confirm & Ingest
                        </button>
                      </div>
                    </form>
                  ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-md">
                      {/* Contract Type */}
                      <div className="border border-slate-100 bg-slate-50 p-md rounded-2xl flex flex-col justify-between">
                        <div className="space-y-xs">
                          <div className="flex justify-between items-center">
                            <span className="text-[10px] font-black uppercase tracking-wider text-slate-400">Predicted Contract Type</span>
                            <span className={`text-[10px] font-bold px-sm py-[2px] rounded-md border ${getConfidenceBadgeStyles(tagSuggestions.contract_type?.confidence)}`}>
                              {(tagSuggestions.contract_type?.confidence * 100).toFixed(0)}% Confidence
                            </span>
                          </div>
                          <p className="text-sm font-black text-slate-900 mt-xs">{tagSuggestions.contract_type?.value || 'Unknown'}</p>
                          <p className="text-xs text-slate-500 leading-relaxed mt-1">{tagSuggestions.contract_type?.rationale}</p>
                        </div>
                      </div>

                      {/* Business Unit */}
                      <div className="border border-slate-100 bg-slate-50 p-md rounded-2xl flex flex-col justify-between">
                        <div className="space-y-xs">
                          <div className="flex justify-between items-center">
                            <span className="text-[10px] font-black uppercase tracking-wider text-slate-400">Target Business Unit</span>
                            <span className={`text-[10px] font-bold px-sm py-[2px] rounded-md border ${getConfidenceBadgeStyles(tagSuggestions.business_unit?.confidence)}`}>
                              {(tagSuggestions.business_unit?.confidence * 100).toFixed(0)}% Confidence
                            </span>
                          </div>
                          <p className="text-sm font-black text-slate-900 mt-xs">{tagSuggestions.business_unit?.value || 'Unknown'}</p>
                          <p className="text-xs text-slate-500 leading-relaxed mt-1">{tagSuggestions.business_unit?.rationale}</p>
                        </div>
                      </div>

                      {/* Jurisdiction */}
                      <div className="border border-slate-100 bg-slate-50 p-md rounded-2xl flex flex-col justify-between">
                        <div className="space-y-xs">
                          <div className="flex justify-between items-center">
                            <span className="text-[10px] font-black uppercase tracking-wider text-slate-400">Jurisdictional Bounds</span>
                            <span className={`text-[10px] font-bold px-sm py-[2px] rounded-md border ${getConfidenceBadgeStyles(tagSuggestions.jurisdiction?.confidence)}`}>
                              {(tagSuggestions.jurisdiction?.confidence * 100).toFixed(0)}% Confidence
                            </span>
                          </div>
                          <p className="text-sm font-black text-slate-900 mt-xs">{tagSuggestions.jurisdiction?.value || 'Unknown'}</p>
                          <p className="text-xs text-slate-500 leading-relaxed mt-1">{tagSuggestions.jurisdiction?.rationale}</p>
                        </div>
                      </div>

                      {/* Risk Level */}
                      <div className="border border-slate-100 bg-slate-50 p-md rounded-2xl flex flex-col justify-between">
                        <div className="space-y-xs">
                          <div className="flex justify-between items-center">
                            <span className="text-[10px] font-black uppercase tracking-wider text-slate-400">Pre-Extraction Risk Tier</span>
                            <span className={`text-[10px] font-bold px-sm py-[2px] rounded-md border ${getConfidenceBadgeStyles(tagSuggestions.risk_level?.confidence)}`}>
                              {(tagSuggestions.risk_level?.confidence * 100).toFixed(0)}% Confidence
                            </span>
                          </div>
                          <p className="text-sm font-black text-slate-900 mt-xs">{tagSuggestions.risk_level?.value || 'Unknown'}</p>
                          <p className="text-xs text-slate-500 leading-relaxed mt-1">{tagSuggestions.risk_level?.rationale}</p>
                        </div>
                      </div>
                    </div>
                  )}

                  {!editingSuggestions && (
                    <div className="flex justify-end gap-xs pt-sm border-t border-slate-100">
                      <button
                        type="button"
                        onClick={() => setEditingSuggestions(true)}
                        className="border border-slate-200 hover:bg-slate-50 text-slate-700 text-xs font-bold px-md py-sm rounded-xl transition-all"
                      >
                        Modify Tags
                      </button>
                      <button
                        type="button"
                        onClick={handleAcceptSuggestions}
                        className="bg-purple-600 hover:bg-purple-700 text-white text-xs font-bold px-md py-sm rounded-xl shadow-sm transition-all"
                      >
                        Accept Suggested Metadata Tags
                      </button>
                    </div>
                  )}
                </div>
              ) : (
                <p className="text-xs text-slate-400 italic py-md text-center">Failed to hydrate upload suggestions.</p>
              )}
            </div>
          )}

          {/* Interactive PDF Viewer Panel */}
          <div className="bg-white border border-slate-200 rounded-3xl p-md shadow-sm flex flex-col w-full min-h-[780px]">
            <div className="w-full flex justify-between items-center border-b border-slate-100 pb-sm mb-md">
              <h2 className="font-bold text-sm text-slate-800">Visual PDF Target Preview Matrix</h2>
              {pdfDoc && (
                <div className="flex items-center gap-xs">
                  <button
                    type="button"
                    disabled={currentPage <= 1}
                    onClick={() => setCurrentPage(prev => Math.max(1, prev - 1))}
                    className="p-1 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 text-slate-600 disabled:opacity-40 disabled:hover:bg-white transition-colors"
                    title="Previous Page"
                  >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 19l-7-7 7-7" />
                    </svg>
                  </button>
                  <span className="text-xs font-mono font-bold text-slate-600 bg-slate-100 px-sm py-[2px] rounded-md">
                    Page {currentPage} of {pdfDoc.numPages}
                  </span>
                  <button
                    type="button"
                    disabled={currentPage >= pdfDoc.numPages}
                    onClick={() => setCurrentPage(prev => Math.min(pdfDoc.numPages, prev + 1))}
                    className="p-1 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 text-slate-600 disabled:opacity-40 disabled:hover:bg-white transition-colors"
                    title="Next Page"
                  >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 5l7 7-7 7" />
                    </svg>
                  </button>
                </div>
              )}
            </div>

            {pdfLoading ? (
              <div className="flex-1 w-full flex items-center justify-center text-xs font-semibold text-slate-400 animate-pulse">
                Streaming object canvas views...
              </div>
            ) : (
              <div ref={containerRef} className="flex-1 w-full flex justify-center overflow-auto bg-slate-100 rounded-xl p-4 shadow-inner border border-slate-200 max-h-[750px] custom-scrollbar">
                <div className="relative h-fit">
                  <canvas ref={canvasRef} className="block shadow-sm rounded-lg pdf-page-shadow" />
                  {/* Proportional Render Box Container */}
                  {overlayStyle && <div style={overlayStyle} className="animate-pulse" />}
                </div>
              </div>
            )}

            {selectedParameter?.citation_text && (
              <div className="w-full mt-md p-md border border-slate-100 bg-slate-50 rounded-xl">
                <span className="text-[10px] font-black uppercase tracking-wider text-slate-400">Ground Truth Citation Source</span>
                <p className="text-xs text-slate-700 mt-1 leading-relaxed italic">"{selectedParameter.citation_text}"</p>
              </div>
            )}
          </div>
        </div>

        {/* Right Pane: Contract Risk Audit Card & Hierarchical Category Groupings */}
        <div className="space-y-md max-h-[920px] overflow-y-auto pr-1">
          
          {/* Overall Contract Risk Footprint widget */}
          {contract && contract.risk_level && (
            <div className="bg-white border border-slate-200 rounded-3xl p-md shadow-sm space-y-sm">
              <div className="flex justify-between items-center">
                <h3 className="font-black text-xs uppercase tracking-wider text-slate-400">Overall Contract Risk Footprint</h3>
                <span className={`text-[10px] font-black px-sm py-[2px] rounded-full border ${
                  contract.risk_level === 'HIGH' ? 'bg-rose-50 border-rose-200 text-rose-700' :
                  contract.risk_level === 'MEDIUM' ? 'bg-amber-50 border-amber-200 text-amber-700' : 'bg-emerald-50 border-emerald-200 text-emerald-700'
                }`}>
                  {contract.risk_level} RISK
                </span>
              </div>
              <div className="flex items-center gap-md">
                {/* Radial score display */}
                <div className="relative w-16 h-16 flex items-center justify-center bg-slate-50 border border-slate-100 rounded-full shadow-inner">
                  <span className="text-sm font-black text-slate-900">{contract.risk_score || 0}</span>
                  <span className="text-[8px] font-bold text-slate-400 absolute bottom-2">/100</span>
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-[10px] font-black uppercase tracking-wider text-slate-400">AI Risk Assessment Summary</p>
                  <p className="text-xs text-slate-600 leading-normal mt-[2px] line-clamp-3 hover:line-clamp-none transition-all duration-300 cursor-pointer" title="Click to expand full audit trail">
                    {contract.risk_rationale}
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* Action Panel Window: Hierarchical Category Groupings */}
          {Object.entries(PARAMETER_GROUPS).map(([groupName]) => {
            const matches = categorizedParameters[groupName] || [];
            const isOpen = activeGroup === groupName;

            return (
              <div key={groupName} className="border border-slate-200 bg-white rounded-3xl overflow-hidden shadow-sm transition-all">
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
                  <div className="p-md space-y-md bg-slate-50/50 border-t border-slate-100 max-h-[550px] overflow-y-auto custom-scrollbar">
                    {matches.length === 0 ? (
                      <p className="text-xs text-slate-400 p-sm italic text-center">No extraction rows populated for this rule parameter category.</p>
                    ) : (
                      matches.map((param) => {
                        const isSelected = selectedParamId === param.parameter_id;
                        const validation = getValidationStyles(param.validation_state);
                        const isExpandedVersion = expandedVersionId === param.parameter_id;

                        return (
                          <div
                            key={param.parameter_id}
                            onClick={() => setSelectedParamId(param.parameter_id)}
                            className={`p-md border rounded-2xl transition-all space-y-sm cursor-pointer ${
                              isSelected 
                                ? 'border-amber-500 bg-amber-500/5 shadow-sm ring-1 ring-amber-500/20' 
                                : 'border-slate-200 bg-white hover:border-slate-300'
                            }`}
                          >
                            {/* Header of parameter card */}
                            <div className="flex justify-between items-start gap-sm">
                              <div className="flex flex-col gap-[2px]">
                                <span className="text-xs font-black text-slate-900">{param.param_name}</span>
                                <span className="text-[10px] text-slate-400 font-mono">{param.header_name}</span>
                              </div>
                              <div className="flex items-center gap-xs">
                                {param.match_score !== undefined && param.match_score !== null && (
                                  <span className={`text-[10px] font-mono font-bold px-sm py-[2px] rounded-md border ${getConfidenceBadgeStyles(param.match_score)}`}>
                                    Conf: {(param.match_score * 100).toFixed(0)}%
                                  </span>
                                )}
                                {param.is_verified && (
                                  <span className="text-[10px] font-black px-sm py-[2px] bg-emerald-100 text-emerald-800 border border-emerald-200 rounded-md">
                                    Verified
                                  </span>
                                )}
                              </div>
                            </div>

                            {/* Deterministic Validation Message Alert */}
                            {param.validation_state && param.validation_state !== 'valid' && (
                              <div className={`p-sm rounded-xl border text-[10px] font-medium leading-normal flex gap-xs ${validation.bg}`}>
                                <span className="font-black text-xs">{validation.icon}</span>
                                <div>
                                  <span className="font-bold mr-1">{validation.label}:</span>
                                  {param.validation_message || 'This parameter has a potential issue. Verify the extract.'}
                                </div>
                              </div>
                            )}

                            {/* Values Displays */}
                            {isSelected && (
                              <div className="space-y-xs pt-1 border-t border-slate-100 animate-in fade-in duration-200">
                                {/* Original AI Extract */}
                                <div className="text-[10px] text-slate-500 flex flex-wrap gap-xs items-center">
                                  <span className="font-black uppercase tracking-wider text-slate-400">AI Original:</span>
                                  <span className="font-mono text-slate-700 bg-slate-100 px-sm py-[2px] rounded">{param.original_extract || 'Null'}</span>
                                </div>

                                {/* User Override Display */}
                                {param.user_override && param.user_override !== param.original_extract && (
                                  <div className="text-[10px] text-amber-700 flex flex-wrap gap-xs items-center font-medium bg-amber-50 border border-amber-100 p-xs rounded-lg">
                                    <span className="font-black uppercase tracking-wider">User Override active</span>
                                  </div>
                                )}
                              </div>
                            )}

                            {/* Interactive Input Override */}
                            <div className="flex gap-xs items-center" onClick={(e) => e.stopPropagation()}>
                              <input
                                type="text"
                                disabled={busy || workflowStatus === 'APPROVED'}
                                className="flex-1 bg-white border border-slate-200 focus:border-amber-500 rounded-xl px-md py-sm text-xs shadow-inner outline-none transition-all disabled:opacity-60"
                                defaultValue={param.user_override || param.original_extract || ''}
                                onBlur={(e) => updateParameter(param.parameter_id, e.target.value)}
                                placeholder="Edit extraction override..."
                              />
                              
                              {/* Verify Toggle Action */}
                              {workflowStatus !== 'APPROVED' && (
                                <button
                                  type="button"
                                  onClick={() => handleToggleVerification(param)}
                                  className={`p-sm rounded-xl border transition-all ${
                                    param.is_verified 
                                      ? 'bg-emerald-50 border-emerald-300 text-emerald-700 hover:bg-emerald-100'
                                      : 'border-slate-200 hover:bg-slate-50 text-slate-400'
                                  }`}
                                  title={param.is_verified ? "Unverify parameter" : "Mark parameter as verified"}
                                >
                                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M5 13l4 4L19 7" />
                                  </svg>
                                </button>
                              )}
                            </div>

                            {/* Collapsible Embedding & Parser Versioning Drawer */}
                            {isSelected && (
                              <div className="pt-xs" onClick={(e) => e.stopPropagation()}>
                                <button
                                  type="button"
                                  onClick={() => setExpandedVersionId(isExpandedVersion ? null : param.parameter_id)}
                                  className="w-full flex justify-between items-center text-[10px] font-black uppercase tracking-wider text-slate-400 hover:text-slate-600 transition-colors"
                                >
                                  <span>Engine Versioning Metadata</span>
                                  <span>{isExpandedVersion ? '▲ Hide' : '▼ View Details'}</span>
                                </button>

                                {isExpandedVersion && (
                                  <div className="mt-xs p-sm bg-slate-100 rounded-xl border border-slate-200 font-mono text-[9px] text-slate-600 space-y-xs animate-in slide-in-from-top-1 duration-150">
                                    <div className="flex justify-between border-b border-slate-200 pb-[2px]">
                                      <span className="font-bold">Embedding Model</span>
                                      <span className="text-slate-900">{param.embed_model_name || 'bge-large-en-v1.5'}</span>
                                    </div>
                                    <div className="flex justify-between border-b border-slate-200 pb-[2px]">
                                      <span className="font-bold">Vector Dimension</span>
                                      <span className="text-slate-900">{param.embed_dimension || 1024}</span>
                                    </div>
                                    <div className="flex justify-between border-b border-slate-200 pb-[2px]">
                                      <span className="font-bold">Quantization Type</span>
                                      <span className="text-slate-900">{param.embed_quant_type || 'FLOAT32'}</span>
                                    </div>
                                    <div className="flex justify-between border-b border-slate-200 pb-[2px]">
                                      <span className="font-bold">Layout Parser Version</span>
                                      <span className="text-slate-900">V{param.parser_version || '1.0.0'}</span>
                                    </div>
                                    <div className="flex justify-between border-b border-slate-200 pb-[2px]">
                                      <span className="font-bold">Chunker Strategy</span>
                                      <span className="text-slate-900">V{param.chunking_version || '1.0.0'}</span>
                                    </div>
                                    {param.embed_created_at && (
                                      <div className="flex justify-between">
                                        <span className="font-bold">Ingested At</span>
                                        <span className="text-slate-900">{new Date(param.embed_created_at).toLocaleString()}</span>
                                      </div>
                                    )}
                                  </div>
                                )}
                              </div>
                            )}

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