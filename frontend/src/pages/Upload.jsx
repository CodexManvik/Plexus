import React, { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import useUpload from '../hooks/useUpload';
import { CONTRACT_TAXONOMY } from '../services/taxonomy';

const Upload = () => {
  const navigate = useNavigate();
  const {
    metadata,
    updateMetadata,
    hasRequiredMetadata,
    isDragging,
    setIsDragging,
    loading,
    error,
    uploadFile,
    handleDrop,
  } = useUpload();
  
  const [selectedFile, setSelectedFile] = useState(null);

  // Dynamic derivation of matching subtypes based on selected Family
  const availableSubtypes = useMemo(() => {
    if (!metadata.agreement_type) return [];
    return CONTRACT_TAXONOMY[metadata.agreement_type] || [];
  }, [metadata.agreement_type]);

  const onUploadClick = async () => {
    if (!selectedFile) return;
    const contract = await uploadFile(selectedFile);
    if (contract?.contract_id) navigate('/extraction');
  };

  return (
    <div className="flex flex-col gap-lg w-full min-h-screen p-md">
      <div>
        <h1 className="text-3xl font-black text-primary tracking-tight">Contract Intake Portal</h1>
        <p className="text-sm text-on-surface-variant font-medium">
          Upload multi-format assets into the Oracle 23ai parsing vector engine.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-lg">
        {/* Dropzone Layout Column */}
        <div className="space-y-md bg-surface-container-lowest border border-outline-variant rounded-xl p-lg">
          <div
            onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
            onDragLeave={() => setIsDragging(false)}
            onDrop={handleDrop}
            className={`border-2 border-dashed rounded-lg p-xl text-center ${isDragging ? 'border-primary bg-primary-fixed/20' : 'border-outline-variant'}`}
          >
            <p className="text-sm font-semibold mb-sm">Drag or select files manually</p>
            <input type="file" accept=".pdf,.docx,.txt,.xlsx" onChange={(e) => setSelectedFile(e.target.files[0] || null)} />
            {selectedFile && <p className="text-xs text-primary mt-sm font-semibold">Ready: {selectedFile.name}</p>}
          </div>

          {/* Core Structured Selection Toggles */}
          <div className="space-y-sm">
            <label className="block text-xs font-bold text-primary">CONTRACT FAMILY *</label>
            <select 
              className="w-full bg-surface border border-outline-variant rounded p-sm text-sm outline-none"
              value={metadata.agreement_type || ''} 
              onChange={(e) => {
                updateMetadata('agreement_type', e.target.value);
                updateMetadata('contract_type', ''); // Reset child when parent variations shift
              }}
            >
              <option value="">-- Choose Family Group --</option>
              {Object.keys(CONTRACT_TAXONOMY).map(family => (
                <option key={family} value={family}>{family}</option>
              ))}
            </select>

            <label className="block text-xs font-bold text-primary mt-sm">SPECIFIC CONTRACT TYPE *</label>
            <select 
              className="w-full bg-surface border border-outline-variant rounded p-sm text-sm outline-none disabled:opacity-50"
              value={metadata.contract_type || ''} 
              onChange={(e) => updateMetadata('contract_type', e.target.value)}
              disabled={!metadata.agreement_type}
            >
              <option value="">-- Select Specific Type --</option>
              {availableSubtypes.map(type => (
                <option key={type} value={type}>{type}</option>
              ))}
            </select>
          </div>

          <button
            type="button"
            onClick={onUploadClick}
            disabled={!selectedFile || !metadata.agreement_type || !metadata.contract_type || loading}
            className="w-full bg-primary text-on-primary py-sm rounded font-semibold disabled:opacity-50 transition-opacity"
          >
            {loading ? 'Executing Engine Parsing...' : 'Ingest Asset & Begin Extraction'}
          </button>
        </div>

        {/* Extended Optional Metadata Attributes Container */}
        <div className="bg-surface-container-lowest border border-outline-variant rounded-xl p-lg">
          <h3 className="font-bold text-primary mb-sm">Supplementary Target Attributes</h3>
          <div className="grid grid-cols-1 gap-xs">
            <input className="w-full bg-surface border border-outline-variant rounded px-sm py-xs text-xs" placeholder="Organization Unit" value={metadata.organization || ''} onChange={(e) => updateMetadata('organization', e.target.value)} />
            <input className="w-full bg-surface border border-outline-variant rounded px-sm py-xs text-xs" placeholder="Business Context Unit" value={metadata.business_unit || ''} onChange={(e) => updateMetadata('business_unit', e.target.value)} />
            <input className="w-full bg-surface border border-outline-variant rounded px-sm py-xs text-xs" placeholder="Jurisdictional Boundary" value={metadata.jurisdiction || ''} onChange={(e) => updateMetadata('jurisdiction', e.target.value)} />
          </div>
        </div>
      </div>
    </div>
  );
};

export default Upload;