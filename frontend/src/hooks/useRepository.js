import { useCallback, useEffect, useMemo, useState } from 'react';
import { api } from '../services/api';

const initialFilters = {
  organization: '',
  business_unit: '',
  contract_type: '',
  agreement_type: '',
  workflow_state: '',
  department: '',
  location: '',
  customer_partner_name: '',
  financial_year: '',
};

export const useRepository = () => {
  const [searchQuery, setSearchQuery] = useState('');
  const [filters, setFilters] = useState(initialFilters);
  const [results, setResults] = useState([]);
  const [total, setTotal] = useState(0);
  const [metadataOptions, setMetadataOptions] = useState({
    organizations: [],
    business_units: [],
    locations: [],
    departments: [],
    customer_partner_names: [],
    financial_years: [],
    contract_types: [],
    agreement_types: [],
  });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const loadMetadataBundle = useCallback(async () => {
    try {
      const bundle = await api.getMetadataBundle();
      setMetadataOptions(bundle);
    } catch (err) {
      console.error('[Repository] Failed to load metadata bundle', err);
    }
  }, []);

  const loadContracts = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      if (searchQuery.trim()) {
        const data = await api.searchContracts(searchQuery.trim(), filters);
        setResults(data.data || []);
        setTotal(data.total || 0);
      } else {
        const data = await api.listContracts(filters);
        setResults(data.data || []);
        setTotal(data.total || 0);
      }
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Failed to load repository data.');
    } finally {
      setLoading(false);
    }
  }, [filters, searchQuery]);

  useEffect(() => {
    loadMetadataBundle();
  }, [loadMetadataBundle]);

  useEffect(() => {
    loadContracts();
  }, [loadContracts]);

  const updateFilter = useCallback((key, value) => {
    setFilters((prev) => ({
      ...prev,
      [key]: value,
    }));
  }, []);

  const clearFilters = useCallback(() => {
    setFilters(initialFilters);
    setSearchQuery('');
  }, []);

  const hasActiveFilters = useMemo(
    () => Object.values(filters).some((value) => String(value || '').trim()) || Boolean(searchQuery.trim()),
    [filters, searchQuery]
  );

  return {
    searchQuery,
    setSearchQuery,
    filters,
    updateFilter,
    clearFilters,
    hasActiveFilters,
    results,
    total,
    metadataOptions,
    loading,
    error,
    refresh: loadContracts,
  };
};

export default useRepository;
