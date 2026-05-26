import React from 'react';
import { useNavigate } from 'react-router-dom';
import useDashboard from '../hooks/useDashboard';

const Dashboard = () => {
  const navigate = useNavigate();
  const { dashboard, stats, recentContracts, pendingApprovals, loading, error } = useDashboard();

  const kpis = dashboard?.kpis || {
    executed: { value: 0, label: '' },
    pending: { value: 0, label: '' },
    closingSoon: { value: 0, label: '' },
  };

  return (
    <div className="flex flex-col gap-lg w-full min-h-screen">
      <div>
        <h1 className="text-3xl font-black text-primary tracking-tight">Executive Dashboard</h1>
        <p className="text-sm text-on-surface-variant font-medium">
          Real-time insight from staged and approved contract records.
        </p>
      </div>

      {error ? (
        <div className="p-sm rounded border border-error bg-error-container text-on-error-container text-sm">
          {error}
        </div>
      ) : null}

      {loading ? (
        <div className="text-sm text-on-surface-variant">Loading dashboard...</div>
      ) : (
        <>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-sm">
            <div className="p-md rounded border border-outline-variant bg-surface-container-lowest">
              <p className="text-xs text-on-surface-variant">Total Contracts</p>
              <p className="text-2xl font-black text-primary">{stats?.totalContracts ?? 0}</p>
            </div>
            <div className="p-md rounded border border-outline-variant bg-surface-container-lowest">
              <p className="text-xs text-on-surface-variant">Executed</p>
              <p className="text-2xl font-black text-primary">{kpis.executed.value}</p>
            </div>
            <div className="p-md rounded border border-outline-variant bg-surface-container-lowest">
              <p className="text-xs text-on-surface-variant">Pending</p>
              <p className="text-2xl font-black text-primary">{kpis.pending.value}</p>
            </div>
            <div className="p-md rounded border border-outline-variant bg-surface-container-lowest">
              <p className="text-xs text-on-surface-variant">Closing Soon</p>
              <p className="text-2xl font-black text-primary">{kpis.closingSoon.value}</p>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-lg">
            <div className="bg-surface-container-lowest border border-outline-variant rounded-xl p-lg">
              <h2 className="font-bold text-primary mb-sm">Stage-wise Pending (Department)</h2>
              {(dashboard?.backlog || []).length === 0 ? (
                <p className="text-sm text-on-surface-variant">No pending backlog by department.</p>
              ) : (
                <div className="space-y-xs">
                  {dashboard.backlog.map((item) => (
                    <div key={`${item.department}_${item.count}`} className="flex justify-between text-sm">
                      <span>{item.department}</span>
                      <span className="font-semibold">{item.count}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="bg-surface-container-lowest border border-outline-variant rounded-xl p-lg">
              <h2 className="font-bold text-primary mb-sm">Approaching Close</h2>
              {(dashboard?.expiries || []).length === 0 ? (
                <p className="text-sm text-on-surface-variant">No contracts in close horizon.</p>
              ) : (
                <div className="space-y-xs">
                  {dashboard.expiries.map((item) => (
                    <button
                      key={`${item.contract_id}_${item.date}`}
                      type="button"
                      onClick={() => {
                        localStorage.setItem('currentContractId', item.contract_id);
                        navigate('/repository');
                      }}
                      className="w-full text-left p-sm border border-outline-variant rounded hover:bg-surface"
                    >
                      <p className="text-sm font-semibold text-primary">{item.title}</p>
                      <p className="text-xs text-on-surface-variant">
                        {item.partner || 'No partner'} • {item.daysLeft} days
                      </p>
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-lg">
            <div className="bg-surface-container-lowest border border-outline-variant rounded-xl p-lg">
              <h2 className="font-bold text-primary mb-sm">Recent Contracts</h2>
              {(recentContracts || []).length === 0 ? (
                <p className="text-sm text-on-surface-variant">No recent contracts.</p>
              ) : (
                <div className="space-y-xs">
                  {recentContracts.map((item) => (
                    <div key={item.contract_id} className="p-sm border border-outline-variant rounded">
                      <p className="text-sm font-semibold text-primary">{item.contract_id}</p>
                      <p className="text-xs text-on-surface-variant">
                        {item.type} • {item.status}
                      </p>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="bg-surface-container-lowest border border-outline-variant rounded-xl p-lg">
              <h2 className="font-bold text-primary mb-sm">Pending Approvals</h2>
              {(pendingApprovals || []).length === 0 ? (
                <p className="text-sm text-on-surface-variant">No pending approvals.</p>
              ) : (
                <div className="space-y-xs">
                  {pendingApprovals.map((item) => (
                    <button
                      key={item.contract_id}
                      type="button"
                      onClick={() => {
                        localStorage.setItem('currentContractId', item.contract_id);
                        navigate('/approvals');
                      }}
                      className="w-full text-left p-sm border border-outline-variant rounded hover:bg-surface"
                    >
                      <p className="text-sm font-semibold text-primary">{item.contract_id}</p>
                      <p className="text-xs text-on-surface-variant">
                        {item.contract_type} • {item.organization}
                      </p>
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
};

export default Dashboard;
