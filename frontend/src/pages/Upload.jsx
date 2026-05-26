import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import useUpload from '../hooks/useUpload';

const fieldClass =
  'w-full bg-surface border border-outline-variant rounded px-sm py-sm text-sm outline-none focus:ring-1 focus:ring-primary';

const Upload = () => {
  const navigate = useNavigate();
  const {
    metadata,
    metadataOptions,
    updateMetadata,
    hasRequiredMetadata,
    isDragging,
    setIsDragging,
    loading,
    error,
    processingQueue,
    uploadFile,
    handleDrop,
    handleFileSelect,
  } = useUpload();
  const [selectedFile, setSelectedFile] = useState(null);

  const onUploadClick = async () => {
    if (!selectedFile) return;
    const contract = await uploadFile(selectedFile);
    if (contract?.contract_id) {
      navigate('/extraction');
    }
  };

  return (
    <div className="flex flex-col gap-lg w-full min-h-screen">
      <div>
        <h1 className="text-3xl font-black text-primary tracking-tight">Contract Upload & Intake</h1>
        <p className="text-sm text-on-surface-variant font-medium">
          Upload a PDF, Word, or Excel contract and tag the contract family plus specific type before extraction.
        </p>
      </div>

      {error ? (
        <div className="p-sm rounded border border-error bg-error-container text-on-error-container text-sm">
          {error}
        </div>
      ) : null}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-lg">
        <div className="bg-surface-container-lowest border border-outline-variant rounded-xl p-lg space-y-md">
          <div
            onDragOver={(event) => {
              event.preventDefault();
              setIsDragging(true);
            }}
            onDragLeave={() => setIsDragging(false)}
            onDrop={handleDrop}
            className={`border-2 border-dashed rounded-lg p-xl text-center ${
              isDragging ? 'border-primary bg-primary-fixed/20' : 'border-outline-variant'
            }`}
          >
            <p className="text-sm font-semibold mb-sm">
              Drag contract file here or select manually.
            </p>
            <input
              type="file"
              accept=".pdf,.docx,.txt,.xlsx,.xlsm"
              onChange={(event) => {
                const [file] = Array.from(event.target.files || []);
                setSelectedFile(file || null);
              }}
            />
            {selectedFile ? (
              <p className="text-xs text-on-surface-variant mt-sm">
                Selected: <span className="font-semibold">{selectedFile.name}</span>
              </p>
            ) : null}
          </div>

          <button
            type="button"
            onClick={onUploadClick}
            disabled={!selectedFile || !hasRequiredMetadata || loading}
            className="w-full bg-primary text-on-primary py-sm rounded font-semibold disabled:opacity-50"
          >
            {loading ? 'Uploading...' : 'Upload & Start Extraction'}
          </button>

          <input
            type="file"
            className="hidden"
            onChange={handleFileSelect}
          />

          <div>
            <h3 className="font-bold text-primary mb-xs">Processing Queue</h3>
            <div className="space-y-xs">
              {processingQueue.length === 0 ? (
                <p className="text-xs text-on-surface-variant">No files processed yet.</p>
              ) : (
                processingQueue.map((item) => (
                  <div key={item.id} className="p-sm border border-outline-variant rounded">
                    <p className="text-sm font-semibold">{item.name}</p>
                    <p className="text-xs text-on-surface-variant">{item.status}</p>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>

        <div className="bg-surface-container-lowest border border-outline-variant rounded-xl p-lg space-y-sm">
          <h2 className="font-bold text-primary">Metadata</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-sm">
            <input className={fieldClass} placeholder="Organization *" value={metadata.organization} onChange={(e) => updateMetadata('organization', e.target.value)} list="organization-options" />
            <input className={fieldClass} placeholder="Business Unit *" value={metadata.business_unit} onChange={(e) => updateMetadata('business_unit', e.target.value)} list="business-unit-options" />
            <input className={fieldClass} placeholder="Location" value={metadata.location} onChange={(e) => updateMetadata('location', e.target.value)} list="location-options" />
            <input className={fieldClass} placeholder="Department" value={metadata.department} onChange={(e) => updateMetadata('department', e.target.value)} list="department-options" />
            <input className={fieldClass} placeholder="Customer / Partner Name" value={metadata.customer_partner_name} onChange={(e) => updateMetadata('customer_partner_name', e.target.value)} list="customer-options" />
            <input className={fieldClass} placeholder="Financial Year" value={metadata.financial_year} onChange={(e) => updateMetadata('financial_year', e.target.value)} list="financial-year-options" />
            <input className={fieldClass} placeholder="Specific Contract Type *" value={metadata.contract_type} onChange={(e) => updateMetadata('contract_type', e.target.value)} list="contract-type-options" />
            <input className={fieldClass} placeholder="Contract Family *" value={metadata.agreement_type} onChange={(e) => updateMetadata('agreement_type', e.target.value)} list="agreement-type-options" />
            <input className={fieldClass} placeholder="Contract Number / Reference ID" value={metadata.contract_number} onChange={(e) => updateMetadata('contract_number', e.target.value)} />
            <input className={fieldClass} placeholder="Version / Amendment Number" value={metadata.version_amendment_number} onChange={(e) => updateMetadata('version_amendment_number', e.target.value)} />
            <input className={fieldClass} placeholder="Execution Type" value={metadata.execution_type} onChange={(e) => updateMetadata('execution_type', e.target.value)} list="execution-type-options" />
            <input className={fieldClass} placeholder="Effective Date (YYYY-MM-DD)" value={metadata.effective_date} onChange={(e) => updateMetadata('effective_date', e.target.value)} />
            <input className={fieldClass} placeholder="Governing Entity / Business Unit" value={metadata.governing_entity} onChange={(e) => updateMetadata('governing_entity', e.target.value)} />
            <input className={fieldClass} placeholder="Jurisdiction" value={metadata.jurisdiction} onChange={(e) => updateMetadata('jurisdiction', e.target.value)} />
            <input className={fieldClass} placeholder="Governing Law" value={metadata.governing_law} onChange={(e) => updateMetadata('governing_law', e.target.value)} />
            <input className={fieldClass} placeholder="Roles (Buyer, Supplier, Contractor...)" value={metadata.party_roles} onChange={(e) => updateMetadata('party_roles', e.target.value)} />
          </div>

          <textarea className={fieldClass} rows={2} placeholder="Legal Names of Parties" value={metadata.legal_names_of_parties} onChange={(e) => updateMetadata('legal_names_of_parties', e.target.value)} />
          <textarea className={fieldClass} rows={2} placeholder="Registered Addresses" value={metadata.registered_addresses} onChange={(e) => updateMetadata('registered_addresses', e.target.value)} />
          <textarea className={fieldClass} rows={2} placeholder="CIN / Registration Numbers" value={metadata.cin_registration_numbers} onChange={(e) => updateMetadata('cin_registration_numbers', e.target.value)} />
          <textarea className={fieldClass} rows={2} placeholder="Authorized Signatories" value={metadata.authorized_signatories} onChange={(e) => updateMetadata('authorized_signatories', e.target.value)} />
          <textarea className={fieldClass} rows={2} placeholder="Contact Persons" value={metadata.contact_persons} onChange={(e) => updateMetadata('contact_persons', e.target.value)} />
          <textarea className={fieldClass} rows={2} placeholder="Affiliates / Subsidiaries Involved" value={metadata.affiliates_subsidiaries_involved} onChange={(e) => updateMetadata('affiliates_subsidiaries_involved', e.target.value)} />
          <textarea className={fieldClass} rows={2} placeholder="Additional Info" value={metadata.additional_info} onChange={(e) => updateMetadata('additional_info', e.target.value)} />
        </div>
      </div>

      <datalist id="organization-options">{metadataOptions.organizations.map((value) => <option key={value} value={value} />)}</datalist>
      <datalist id="business-unit-options">{metadataOptions.business_units.map((value) => <option key={value} value={value} />)}</datalist>
      <datalist id="location-options">{metadataOptions.locations.map((value) => <option key={value} value={value} />)}</datalist>
      <datalist id="department-options">{metadataOptions.departments.map((value) => <option key={value} value={value} />)}</datalist>
      <datalist id="customer-options">{metadataOptions.customer_partner_names.map((value) => <option key={value} value={value} />)}</datalist>
      <datalist id="financial-year-options">{metadataOptions.financial_years.map((value) => <option key={value} value={value} />)}</datalist>
      <datalist id="contract-type-options">{metadataOptions.contract_types.map((value) => <option key={value} value={value} />)}</datalist>
      <datalist id="agreement-type-options">{metadataOptions.agreement_types.map((value) => <option key={value} value={value} />)}</datalist>
      <datalist id="execution-type-options">{metadataOptions.execution_types.map((value) => <option key={value} value={value} />)}</datalist>
    </div>
  );
};

export default Upload;
