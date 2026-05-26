import { useCallback, useEffect, useState } from 'react';
import { api } from '../services/api';

export const useDashboard = () => {
  const [dashboard, setDashboard] = useState(null);
  const [stats, setStats] = useState(null);
  const [recentContracts, setRecentContracts] = useState([]);
  const [pendingApprovals, setPendingApprovals] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const loadDashboardData = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const [dashboardData, statsData, recentData, pendingData] = await Promise.all([
        api.getDashboard(),
        api.getDashboardStats(),
        api.getRecentContracts(10),
        api.getPendingApprovals(),
      ]);
      setDashboard(dashboardData);
      setStats(statsData);
      setRecentContracts(recentData.data || []);
      setPendingApprovals(pendingData.data || []);
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Failed to load dashboard.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadDashboardData();
  }, [loadDashboardData]);

  return {
    dashboard,
    stats,
    recentContracts,
    pendingApprovals,
    loading,
    error,
    refresh: loadDashboardData,
  };
};

export default useDashboard;
