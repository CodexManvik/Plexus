import { useCallback, useEffect, useMemo, useState } from 'react';
import { api } from '../services/api';

export const useVerification = () => {
  const [contractId, setContractId] = useState(localStorage.getItem('currentContractId') || '');
  const [contract, setContract] = useState(null);
  const [parameters, setParameters] = useState([]);
  const [activeParamId, setActiveParamId] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');

  const currentUser = useMemo(
    () => JSON.parse(localStorage.getItem('currentUser') || '{}'),
    []
  );
  const actorId = currentUser.id || 'anonymous_user';

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
      if (!activeParamId && data.parameters?.length) {
        setActiveParamId(data.parameters[0].parameter_id);
      }
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Failed to load verification data.');
    } finally {
      setLoading(false);
    }
  }, [activeParamId, contractId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const handleUpdateValue = useCallback(
    async (paramId, newValue) => {
      if (!contractId) return;
      setBusy(true);
      setError('');
      try {
        const updated = await api.updateParameter(contractId, paramId, {
          user_override: newValue,
          modified_by: actorId,
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
    [actorId, contractId]
  );

  const handleToggleVerify = useCallback(
    async (paramId, nextVerified) => {
      if (!contractId) return;
      setBusy(true);
      setError('');
      try {
        const updated = await api.verifyParameter(contractId, paramId, {
          is_verified: nextVerified,
          modified_by: actorId,
          note: nextVerified ? 'Verified by reviewer' : 'Verification removed',
        });
        setParameters((prev) =>
          prev.map((param) => (param.parameter_id === paramId ? updated : param))
        );
      } catch (err) {
        setError(err.response?.data?.detail || err.message || 'Failed to update verification.');
      } finally {
        setBusy(false);
      }
    },
    [actorId, contractId]
  );

  const handleSubmitDraft = useCallback(async () => {
    if (!contractId) return;
    setBusy(true);
    setMessage('');
    setError('');
    try {
      await api.submitDraft(contractId, {
        modified_by: actorId,
        comment: 'Draft saved from verification screen',
      });
      setMessage('Draft saved.');
      await refresh();
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Failed to save draft.');
    } finally {
      setBusy(false);
    }
  }, [actorId, contractId, refresh]);

  const handleSubmitForApproval = useCallback(async () => {
    if (!contractId) return;
    setBusy(true);
    setMessage('');
    setError('');
    try {
      await api.submitForApproval(contractId, {
        modified_by: actorId,
        comment: 'Submitted for managerial review',
      });
      setMessage('Submitted for approval.');
      await refresh();
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Failed to submit for approval.');
    } finally {
      setBusy(false);
    }
  }, [actorId, contractId, refresh]);

  return {
    contractId,
    contract,
    parameters,
    activeParamId,
    setActiveParamId,
    loading,
    busy,
    error,
    message,
    refresh,
    handleUpdateValue,
    handleToggleVerify,
    handleSubmitDraft,
    handleSubmitForApproval,
  };
};

export default useVerification;
