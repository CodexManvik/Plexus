import React, { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import useExtraction from '../hooks/useExtraction';

const escapeHtml = (value = '') =>
  String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');

const escapeRegExp = (value = '') => String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

const Extraction = () => {
  const navigate = useNavigate();
  const {
    contractId,
    contract,
    parameters,
    selectedParamId,
    setSelectedParamId,
    selectedParameter,
    searchQuery,
    setSearchQuery,
    searchHeader,
    setSearchHeader,
    searchName,
    setSearchName,
    loading,
    busy,
    error,
    updateParameter,
    addDynamicSearchRecord,
  } = useExtraction();

  const documentPreview = useMemo(() => {
    const raw = contract?.document_text || '';
    return raw.length > 6000 ? `${raw.slice(0, 6000)}\n\n...` : raw;
  }, [contract?.document_text]);

  const highlightedPreview = useMemo(() => {
    const fallbackText = documentPreview || 'No text extracted from document.';
    const citation = selectedParameter?.citation_text?.trim();
    const safeText = escapeHtml(fallbackText).replaceAll('\n', '<br />');

    if (!citation || !documentPreview) {
      return safeText;
    }

    const regex = new RegExp(escapeRegExp(citation), 'i');
    if (!regex.test(documentPreview)) {
      return safeText;
    }

    return escapeHtml(documentPreview)
      .replace(regex, (match) => `<mark class="bg-amber-200 text-slate-900 px-1 rounded">${escapeHtml(match)}</mark>`)
      .replaceAll('\n', '<br />');
  }, [documentPreview, selectedParameter?.citation_text]);

  return (
    <div className="flex flex-col gap-lg w-full min-h-screen">
      <div className="flex justify-between items-end">
        <div>
          <h1 className="text-3xl font-black text-primary tracking-tight">Extraction & Citation</h1>
          <p className="text-sm text-on-surface-variant font-medium">
            Contract ID: {contractId || 'No contract selected'}
          </p>
        </div>
        <button
          type="button"
          onClick={() => navigate('/verification')}
          className="bg-primary text-on-primary px-md py-sm rounded font-semibold"
        >
          Go to Verification
        </button>
      </div>

      {error ? (
        <div className="p-sm rounded border border-error bg-error-container text-on-error-container text-sm">
          {error}
        </div>
      ) : null}

      {loading ? (
        <div className="text-sm text-on-surface-variant">Loading extraction data...</div>
      ) : (
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-lg">
          <div className="bg-surface-container-lowest border border-outline-variant rounded-xl p-lg">
            <h2 className="font-bold text-primary mb-sm">Document Text</h2>
            <pre
              className="whitespace-pre-wrap text-xs leading-relaxed bg-surface p-sm rounded border border-outline-variant max-h-[640px] overflow-auto"
              dangerouslySetInnerHTML={{ __html: highlightedPreview }}
            />
            {selectedParameter?.citation_text ? (
              <div className="mt-sm p-sm border border-primary rounded bg-primary-fixed/20">
                <p className="text-xs font-bold text-primary">Selected Citation</p>
                <p className="text-xs">{selectedParameter.citation_text}</p>
              </div>
            ) : null}
          </div>

          <div className="bg-surface-container-lowest border border-outline-variant rounded-xl p-lg space-y-md">
            <h2 className="font-bold text-primary">Extracted Parameters</h2>
            {parameters.length === 0 ? (
              <p className="text-sm text-on-surface-variant">
                No extraction rows found. Add one using dynamic search below or configure rules in Maintenance.
              </p>
            ) : (
              <div className="space-y-sm max-h-[420px] overflow-auto">
                {parameters.map((param) => (
                  <button
                    key={param.parameter_id}
                    type="button"
                    onClick={() => setSelectedParamId(param.parameter_id)}
                    className={`w-full text-left p-sm border rounded ${
                      selectedParamId === param.parameter_id
                        ? 'border-primary bg-primary-fixed/20'
                        : 'border-outline-variant bg-surface'
                    }`}
                  >
                    <p className="text-xs font-bold text-primary">
                      {param.header_name} • {param.param_name}
                    </p>
                    <p className="text-xs text-on-surface-variant">
                      Match Score: {param.match_score ?? 0}
                    </p>
                    {param.source_query ? (
                      <p className="text-xs text-on-surface-variant">Source Query: {param.source_query}</p>
                    ) : null}
                    <p className="text-xs mt-xs">{param.user_override || param.original_extract || 'No match'}</p>
                    {selectedParamId === param.parameter_id ? (
                      <textarea
                        className="mt-xs w-full text-xs p-xs bg-surface border border-outline-variant rounded"
                        rows={3}
                        defaultValue={param.user_override || param.original_extract || ''}
                        onBlur={(event) => updateParameter(param.parameter_id, event.target.value)}
                      />
                    ) : null}
                  </button>
                ))}
              </div>
            )}

            <div className="border-t border-outline-variant pt-sm space-y-xs">
              <h3 className="text-sm font-bold text-primary">Dynamic Search Addition</h3>
              <input
                className="w-full bg-surface border border-outline-variant rounded px-sm py-xs text-sm"
                placeholder="Search query on contract text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
              <input
                className="w-full bg-surface border border-outline-variant rounded px-sm py-xs text-sm"
                placeholder="Parameter Head"
                value={searchHeader}
                onChange={(e) => setSearchHeader(e.target.value)}
              />
              <input
                className="w-full bg-surface border border-outline-variant rounded px-sm py-xs text-sm"
                placeholder="Parameter Name"
                value={searchName}
                onChange={(e) => setSearchName(e.target.value)}
              />
              <button
                type="button"
                disabled={busy}
                onClick={addDynamicSearchRecord}
                className="bg-primary text-on-primary px-md py-xs rounded text-sm font-semibold disabled:opacity-60"
              >
                Add Match Row
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default Extraction;
