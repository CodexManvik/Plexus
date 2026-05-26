import { useCallback, useEffect, useMemo, useState } from 'react';
import { api } from '../services/api';

const emptyMetadata = {
  organization: '',
  business_unit: '',
  location: '',
  department: '',
  customer_partner_name: '',
  financial_year: '',
  contract_type: '',
  agreement_type: '',
  additional_info: '',
  contract_number: '',
  version_amendment_number: '',
  execution_type: '',
  governing_entity: '',
  jurisdiction: '',
  governing_law: '',
  legal_names_of_parties: '',
  registered_addresses: '',
  cin_registration_numbers: '',
  authorized_signatories: '',
  contact_persons: '',
  party_roles: '',
  affiliates_subsidiaries_involved: '',
  effective_date: '',
};

export const useUpload = () => {
  const [metadata, setMetadata] = useState(emptyMetadata);
  const [metadataOptions, setMetadataOptions] = useState({
    organizations: [],
    business_units: [],
    locations: [],
    departments: [],
    customer_partner_names: [],
    financial_years: [],
    contract_types: [],
    agreement_types: [],
    execution_types: [],
  });
  const [isDragging, setIsDragging] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [processingQueue, setProcessingQueue] = useState([]);

  useEffect(() => {
    const loadMetadata = async () => {
      try {
        const bundle = await api.getMetadataBundle();
        setMetadataOptions(bundle);
      } catch (err) {
        console.error('[Upload] Failed to load metadata bundle', err);
      }
    };
    loadMetadata();
  }, []);

  const requiredFields = useMemo(
    () => ['organization', 'business_unit', 'contract_type', 'agreement_type'],
    []
  );

  const hasRequiredMetadata = useMemo(
    () => requiredFields.every((key) => String(metadata[key] || '').trim()),
    [metadata, requiredFields]
  );

  const updateMetadata = useCallback((key, value) => {
    setMetadata((prev) => ({
      ...prev,
      [key]: value,
    }));
  }, []);

  const uploadFile = useCallback(
    async (file) => {
      setError('');
      if (!hasRequiredMetadata) {
        setError('Please complete all mandatory metadata fields before uploading.');
        return null;
      }

      const currentUser = JSON.parse(localStorage.getItem('currentUser') || '{}');
      const queueId = `${Date.now()}_${file.name}`;
      setProcessingQueue((prev) => [
        {
          id: queueId,
          name: file.name,
          progress: 10,
          status: 'Uploading',
        },
        ...prev,
      ]);
      setLoading(true);

      try {
        setProcessingQueue((prev) =>
          prev.map((item) =>
            item.id === queueId ? { ...item, progress: 45, status: 'Extracting' } : item
          )
        );
        const contract = await api.uploadContract({
          file,
          metadata: {
            ...metadata,
            user_id: currentUser.id || 'anonymous_user',
          },
        });
        localStorage.setItem('last_uploaded_id', contract.contract_id);
        localStorage.setItem('currentContractId', contract.contract_id);

        setProcessingQueue((prev) =>
          prev.map((item) =>
            item.id === queueId
              ? { ...item, progress: 100, status: 'Complete', contractId: contract.contract_id }
              : item
          )
        );
        return contract;
      } catch (err) {
        const message = err.response?.data?.detail || err.message || 'Upload failed';
        setError(message);
        setProcessingQueue((prev) =>
          prev.map((item) =>
            item.id === queueId ? { ...item, progress: 0, status: `Error: ${message}` } : item
          )
        );
        return null;
      } finally {
        setLoading(false);
      }
    },
    [hasRequiredMetadata, metadata]
  );

  const handleDrop = useCallback(
    async (event) => {
      event.preventDefault();
      setIsDragging(false);
      const [file] = Array.from(event.dataTransfer.files || []);
      if (file) {
        await uploadFile(file);
      }
    },
    [uploadFile]
  );

  const handleFileSelect = useCallback(
    async (event) => {
      const [file] = Array.from(event.target.files || []);
      if (file) {
        await uploadFile(file);
      }
    },
    [uploadFile]
  );

  return {
    metadata,
    metadataOptions,
    updateMetadata,
    hasRequiredMetadata,
    isDragging,
    setIsDragging,
    loading,
    error,
    setError,
    processingQueue,
    setProcessingQueue,
    uploadFile,
    handleDrop,
    handleFileSelect,
  };
};

export default useUpload;
