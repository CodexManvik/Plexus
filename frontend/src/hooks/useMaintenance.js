import { useCallback, useEffect, useState } from 'react';
import { api } from '../services/api';

const emptyRule = {
  contract_type: '',
  agreement_type: '',
  parameter_head: '',
  parameter_name: '',
  parameter_logic: '',
};

export const useMaintenance = () => {
  const [rules, setRules] = useState([]);
  const [ruleForm, setRuleForm] = useState(emptyRule);
  const [selectedRuleId, setSelectedRuleId] = useState(null);
  const [systemStatus, setSystemStatus] = useState(null);
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const currentUser = JSON.parse(localStorage.getItem('currentUser') || '{}');
  const actorId = currentUser.id || 'anonymous_user';

  const loadAll = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [ruleData, statusData, logData] = await Promise.all([
        api.listRules({ include_inactive: true }),
        api.getSystemStatus(),
        api.getErrorLogs(30),
      ]);
      setRules(ruleData || []);
      setSystemStatus(statusData || null);
      setLogs(logData.data || []);
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Failed to load maintenance data.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  const resetRuleForm = useCallback(() => {
    setRuleForm(emptyRule);
    setSelectedRuleId(null);
  }, []);

  const updateRuleField = useCallback((key, value) => {
    setRuleForm((prev) => ({
      ...prev,
      [key]: value,
    }));
  }, []);

  const editRule = useCallback((rule) => {
    setSelectedRuleId(rule.rule_id);
    setRuleForm({
      contract_type: rule.contract_type || '',
      agreement_type: rule.agreement_type || '',
      parameter_head: rule.parameter_head || '',
      parameter_name: rule.parameter_name || '',
      parameter_logic: rule.parameter_logic || '',
    });
  }, []);

  const saveRule = useCallback(async () => {
    if (!ruleForm.contract_type || !ruleForm.agreement_type || !ruleForm.parameter_head || !ruleForm.parameter_name) {
      setError('Contract type, agreement type, parameter head, and parameter name are required.');
      return;
    }
    setBusy(true);
    setError('');
    try {
      if (selectedRuleId) {
        await api.updateRule(selectedRuleId, ruleForm);
      } else {
        await api.createRule({
          ...ruleForm,
          created_by: actorId,
          is_active: true,
        });
      }
      await loadAll();
      resetRuleForm();
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Failed to save rule.');
    } finally {
      setBusy(false);
    }
  }, [actorId, loadAll, resetRuleForm, ruleForm, selectedRuleId]);

  const deleteRule = useCallback(
    async (ruleId) => {
      setBusy(true);
      setError('');
      try {
        await api.deleteRule(ruleId);
        await loadAll();
        if (selectedRuleId === ruleId) {
          resetRuleForm();
        }
      } catch (err) {
        setError(err.response?.data?.detail || err.message || 'Failed to delete rule.');
      } finally {
        setBusy(false);
      }
    },
    [loadAll, resetRuleForm, selectedRuleId]
  );

  const triggerSync = useCallback(async () => {
    setBusy(true);
    setError('');
    try {
      await api.triggerSync();
      await loadAll();
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Failed to trigger sync.');
    } finally {
      setBusy(false);
    }
  }, [loadAll]);

  return {
    rules,
    ruleForm,
    selectedRuleId,
    systemStatus,
    logs,
    loading,
    busy,
    error,
    refresh: loadAll,
    updateRuleField,
    editRule,
    saveRule,
    deleteRule,
    resetRuleForm,
    triggerSync,
  };
};

export default useMaintenance;
