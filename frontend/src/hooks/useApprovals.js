import { useCallback, useEffect, useMemo, useState } from 'react';
import { api } from '../services/api';

export const useApprovals = () => {
  const [activeTab, setActiveTab] = useState('Pending');
  const [contracts, setContracts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState('');
  const [error, setError] = useState('');

  const currentUser = useMemo(
    () => JSON.parse(localStorage.getItem('currentUser') || '{}'),
    []
  );
  const actorId = currentUser.id || 'anonymous_user';

  const loadApprovals = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const response = await api.getPendingApprovals();
      setContracts(response.data || []);
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Failed to load approvals.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadApprovals();
  }, [loadApprovals]);

  const handleApprove = useCallback(
    async (contractId) => {
      setBusyId(contractId);
      setError('');
      try {
        await api.approveContract(contractId, {
          modified_by: actorId,
          comment: 'Approved by operations head',
        });
        await loadApprovals();
      } catch (err) {
        setError(err.response?.data?.detail || err.message || 'Failed to approve contract.');
      } finally {
        setBusyId('');
      }
    },
    [actorId, loadApprovals]
  );

  const handleSendBack = useCallback(
    async (contractId, reason) => {
      setBusyId(contractId);
      setError('');
      try {
        await api.sendBackContract(contractId, {
          modified_by: actorId,
          comment: reason || 'Sent back for correction',
        });
        await loadApprovals();
      } catch (err) {
        setError(err.response?.data?.detail || err.message || 'Failed to send back contract.');
      } finally {
        setBusyId('');
      }
    },
    [actorId, loadApprovals]
  );

  const filteredContracts = useMemo(() => {
    if (activeTab === 'All') return contracts;
    if (activeTab === 'Pending') {
      return contracts.filter((item) => item.workflow_state === 'PENDING_APPROVAL');
    }
    return contracts;
  }, [activeTab, contracts]);

  return {
    activeTab,
    setActiveTab,
    contracts: filteredContracts,
    loading,
    busyId,
    error,
    refresh: loadApprovals,
    handleApprove,
    handleSendBack,
  };
};

export default useApprovals;
