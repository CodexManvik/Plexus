import React, { useEffect, useMemo, useState } from 'react';
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
        setSelectedIds((current) => {
          if (current.length > 0) {
            return current.filter((id) => items.some((item) => item.contract_id === id));
          }
          return items.slice(0, 3).map((item) => item.contract_id);
        });
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

  const filteredDocuments = useMemo(() => {
    const term = searchTerm.trim().toLowerCase();
    if (!term) {
      return documents;
    }
    return documents.filter((item) => {
      const haystack = [
        item.contract_id,
        item.contract_type,
        item.agreement_type,
        item.organization,
        item.business_unit,
        item.department,
        item.customer_partner_name,
        item.workflow_state,
      ]
        .filter(Boolean)
        .join(' ')
        .toLowerCase();
      return haystack.includes(term);
    });
  }, [documents, searchTerm]);

  const selectedDocuments = useMemo(
    () => documents.filter((item) => selectedIds.includes(item.contract_id)),
    [documents, selectedIds]
  );

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
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Failed to ask assistant.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="flex flex-col gap-lg w-full min-h-screen">
      <div className="rounded-3xl border border-outline-variant bg-gradient-to-r from-surface-container-lowest via-surface to-surface-container-high p-lg shadow-sm">
        <p className="text-xs font-black uppercase tracking-[0.35em] text-primary">AI Assistant</p>
        <h1 className="mt-sm text-3xl font-black text-primary tracking-tight">Ask the selected contract corpus</h1>
        <p className="mt-xs max-w-3xl text-sm text-on-surface-variant font-medium">
          Choose the documents you want to search, then ask for a summary, clause comparison, or specific obligation.
          The assistant answers from the selected corpus and falls back gracefully if Azure OpenAI is not configured.
        </p>
      </div>

      {error ? (
        <div className="p-sm rounded border border-error bg-error-container text-on-error-container text-sm">
          {error}
        </div>
      ) : null}

      <div className="grid gap-lg xl:grid-cols-[minmax(0,0.95fr)_minmax(0,1.05fr)]">
        <section className="rounded-2xl border border-outline-variant bg-surface-container-lowest p-lg shadow-sm">
          <div className="flex items-center justify-between gap-sm">
            <div>
              <h2 className="text-lg font-black text-primary">Documents</h2>
              <p className="text-xs text-on-surface-variant">Select the corpus you want the assistant to use.</p>
            </div>
            <div className="rounded-full bg-primary-container px-sm py-xs text-xs font-bold text-on-primary-container">
              {selectedDocuments.length} selected
            </div>
          </div>

          <input
            className="mt-md w-full rounded-xl border border-outline-variant bg-surface px-sm py-sm text-sm outline-none focus:ring-1 focus:ring-primary"
            placeholder="Filter by contract id, type, partner, or workflow state"
            value={searchTerm}
            onChange={(event) => setSearchTerm(event.target.value)}
          />

          <div className="mt-md max-h-[620px] space-y-sm overflow-auto pr-1">
            {loadingDocuments ? (
              <div className="rounded-xl border border-dashed border-outline-variant p-lg text-sm text-on-surface-variant">
                Loading documents...
              </div>
            ) : filteredDocuments.length === 0 ? (
              <div className="rounded-xl border border-dashed border-outline-variant p-lg text-sm text-on-surface-variant">
                No documents match the filter.
              </div>
            ) : (
              filteredDocuments.map((document) => {
                const checked = selectedIds.includes(document.contract_id);
                return (
                  <label
                    key={document.contract_id}
                    className={`flex cursor-pointer items-start gap-sm rounded-2xl border p-md transition-all ${
                      checked
                        ? 'border-primary bg-primary-fixed/20 shadow-sm'
                        : 'border-outline-variant bg-surface hover:border-primary/50'
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => toggleSelection(document.contract_id)}
                      className="mt-1 h-4 w-4 accent-primary"
                    />
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-xs">
                        <p className="text-sm font-bold text-primary">{document.contract_id}</p>
                        <span className="rounded-full bg-surface-container-high px-xs py-[2px] text-[10px] font-bold uppercase tracking-[0.2em] text-on-surface-variant">
                          {document.workflow_state}
                        </span>
                      </div>
                      <p className="mt-1 text-sm font-semibold text-on-surface">{document.contract_type}</p>
                      <p className="text-xs text-on-surface-variant">{document.agreement_type || 'Unassigned family'}</p>
                      <p className="mt-1 text-xs text-on-surface-variant">
                        {document.organization || '-'} • {document.business_unit || '-'} • {document.customer_partner_name || '-'}
                      </p>
                    </div>
                  </label>
                );
              })
            )}
          </div>
        </section>

        <section className="space-y-lg">
          <form
            onSubmit={askQuestion}
            className="rounded-2xl border border-outline-variant bg-surface-container-lowest p-lg shadow-sm"
          >
            <div className="flex items-center justify-between gap-sm">
              <div>
                <h2 className="text-lg font-black text-primary">Ask a question</h2>
                <p className="text-xs text-on-surface-variant">Try payment, termination, confidentiality, or liability questions.</p>
              </div>
              <button
                type="submit"
                disabled={submitting || selectedIds.length === 0}
                className="rounded-xl bg-primary px-md py-sm text-sm font-semibold text-on-primary transition-all hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {submitting ? 'Thinking...' : 'Ask Assistant'}
              </button>
            </div>

            <textarea
              className="mt-md min-h-[160px] w-full rounded-2xl border border-outline-variant bg-surface px-md py-md text-sm outline-none focus:ring-1 focus:ring-primary"
              placeholder="Ask about obligations, dates, clauses, or compare terms across the selected contracts."
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
            />

            <div className="mt-md flex flex-wrap gap-xs">
              {examplePrompts.map((prompt) => (
                <button
                  key={prompt}
                  type="button"
                  onClick={() => setQuestion(prompt)}
                  className="rounded-full border border-outline-variant bg-surface px-sm py-xs text-xs font-semibold text-on-surface-variant transition-colors hover:border-primary hover:text-primary"
                >
                  {prompt}
                </button>
              ))}
            </div>
          </form>

          <div className="grid gap-lg lg:grid-cols-2">
            <div className="rounded-2xl border border-outline-variant bg-surface-container-lowest p-lg shadow-sm">
              <h3 className="text-sm font-black uppercase tracking-[0.3em] text-primary">Answer</h3>
              {answer ? (
                <p className="mt-md whitespace-pre-wrap text-sm leading-6 text-on-surface">{answer}</p>
              ) : (
                <p className="mt-md text-sm text-on-surface-variant">
                  Ask a question to generate a retrieval-backed response from the selected documents.
                </p>
              )}
            </div>

            <div className="rounded-2xl border border-outline-variant bg-surface-container-lowest p-lg shadow-sm">
              <div className="flex items-center justify-between gap-sm">
                <h3 className="text-sm font-black uppercase tracking-[0.3em] text-primary">Sources used</h3>
                <span className="rounded-full bg-surface-container-high px-sm py-xs text-xs font-semibold text-on-surface-variant">
                  {sources.length} snippets
                </span>
              </div>
              <div className="mt-md space-y-sm">
                {sources.length === 0 ? (
                  <p className="text-sm text-on-surface-variant">Source snippets will appear here after you ask a question.</p>
                ) : (
                  sources.map((source) => (
                    <div key={`${source.contract_id}-${source.title}`} className="rounded-xl border border-outline-variant p-md">
                      <div className="flex flex-wrap items-center gap-xs">
                        <p className="text-sm font-bold text-primary">{source.contract_id}</p>
                        <span className="text-[10px] font-bold uppercase tracking-[0.2em] text-on-surface-variant">
                          {source.source_type}
                        </span>
                      </div>
                      <p className="mt-1 text-sm font-semibold text-on-surface">{source.title}</p>
                      <p className="mt-1 text-xs text-on-surface-variant">Score: {source.score.toFixed(2)}</p>
                      <p className="mt-2 text-sm leading-6 text-on-surface-variant">{source.snippet}</p>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
};

export default Assistant;