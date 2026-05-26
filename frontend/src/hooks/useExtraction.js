import { useCallback, useEffect, useMemo, useState } from 'react';
import { api } from '../services/api';

export const useExtraction = () => {
  const [contractId, setContractId] = useState(localStorage.getItem('currentContractId') || '');
  const [contract, setContract] = useState(null);
  const [parameters, setParameters] = useState([]);
  const [selectedParamId, setSelectedParamId] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchHeader, setSearchHeader] = useState('');
  const [searchName, setSearchName] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const refresh = useCallback(async () => {
    const activeId = contractId || localStorage.getItem('currentContractId') || '';
    if (!activeId) {
      setLoading(false);
      return;
    }
    setContractId(activeId);
    setLoading(true);
    setError('');
    try {
      const data = await api.getContractDetails(activeId);
      setContract(data);
      setParameters(data.parameters || []);
      if (!selectedParamId && data.parameters?.length) {
        setSelectedParamId(data.parameters[0].parameter_id);
      }
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Failed to load extraction data.');
    } finally {
      setLoading(false);
    }
  }, [contractId, selectedParamId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const selectedParameter = useMemo(
    () => parameters.find((param) => param.parameter_id === selectedParamId) || null,
    [parameters, selectedParamId]
  );

  const updateParameter = useCallback(
    async (paramId, value) => {
      if (!contractId) return;
      const currentUser = JSON.parse(localStorage.getItem('currentUser') || '{}');
      setBusy(true);
      setError('');
      try {
        const updated = await api.updateParameter(contractId, paramId, {
          user_override: value,
          modified_by: currentUser.id || 'anonymous_user',
        });
        setParameters((prev) =>
          prev.map((param) => (param.parameter_id === paramId ? updated : param))
        );
      } catch (err) {
        setError(err.response?.data?.detail || err.message || 'Failed to update parameter.');
      } finally {
        setBusy(false);
      }
    },
    [contractId]
  );

  const addDynamicSearchRecord = useCallback(async () => {
    if (!contractId || !searchQuery.trim() || !searchHeader.trim() || !searchName.trim()) {
      setError('Provide query, parameter head, and parameter name.');
      return;
    }
    const currentUser = JSON.parse(localStorage.getItem('currentUser') || '{}');
    setBusy(true);
    setError('');
    try {
      const created = await api.addParameterBySearch(contractId, {
        query: searchQuery.trim(),
        parameter_head: searchHeader.trim(),
        parameter_name: searchName.trim(),
        modified_by: currentUser.id || 'anonymous_user',
      });
      setParameters((prev) => [...prev, created]);
      setSearchQuery('');
      setSearchHeader('');
      setSearchName('');
      if (!selectedParamId) {
        setSelectedParamId(created.parameter_id);
      }
    } catch (err) {
      setError(
        err.response?.data?.detail || err.message || 'Failed to append dynamic extraction record.'
      );
    } finally {
      setBusy(false);
    }
  }, [contractId, searchHeader, searchName, searchQuery, selectedParamId]);

  return {
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
    refresh,
    updateParameter,
    addDynamicSearchRecord,
  };
};

export default useExtraction;
