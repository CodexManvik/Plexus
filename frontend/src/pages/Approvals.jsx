import React from 'react';
import { useNavigate } from 'react-router-dom';
import useApprovals from '../hooks/useApprovals';

const Approvals = () => {
  const navigate = useNavigate();
  const { activeTab, setActiveTab, contracts, loading, busyId, error, handleApprove, handleSendBack } =
    useApprovals();

  return (
    <div className="flex flex-col gap-lg w-full min-h-screen">
      <div>
        <h1 className="text-3xl font-black text-primary tracking-tight">Approval Queue</h1>
        <p className="text-sm text-on-surface-variant font-medium">
          Manager review for submitted contract drafts.
        </p>
      </div>

      {error ? (
        <div className="p-sm rounded border border-error bg-error-container text-on-error-container text-sm">
          {error}
        </div>
      ) : null}

      <div className="flex gap-xs">
        {['Pending', 'All'].map((tab) => (
          <button
            key={tab}
            type="button"
            onClick={() => setActiveTab(tab)}
            className={`px-md py-xs rounded text-sm font-semibold ${
              activeTab === tab ? 'bg-primary text-on-primary' : 'bg-surface border border-outline-variant'
            }`}
          >
            {tab}
          </button>
        ))}
      </div>

      <div className="bg-surface-container-lowest border border-outline-variant rounded-xl overflow-auto">
        {loading ? (
          <div className="p-lg text-sm text-on-surface-variant">Loading approvals...</div>
        ) : contracts.length === 0 ? (
          <div className="p-lg text-sm text-on-surface-variant">No contracts pending approval.</div>
        ) : (
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-outline-variant">
                <th className="py-sm px-sm text-xs font-black text-on-surface-variant">CONTRACT</th>
                <th className="py-sm px-sm text-xs font-black text-on-surface-variant">ORG</th>
                <th className="py-sm px-sm text-xs font-black text-on-surface-variant">DEPARTMENT</th>
                <th className="py-sm px-sm text-xs font-black text-on-surface-variant">STATE</th>
                <th className="py-sm px-sm text-xs font-black text-on-surface-variant">ACTION</th>
              </tr>
            </thead>
            <tbody>
              {contracts.map((item) => (
                <tr key={item.contract_id} className="border-b border-outline-variant/40">
                  <td className="py-sm px-sm">
                    <button
                      type="button"
                      className="text-sm font-semibold text-primary hover:underline"
                      onClick={() => {
                        localStorage.setItem('currentContractId', item.contract_id);
                        navigate('/verification');
                      }}
                    >
                      {item.contract_id}
                    </button>
                    <p className="text-xs text-on-surface-variant">
                      {item.contract_type} • {item.agreement_type}
                    </p>
                  </td>
                  <td className="py-sm px-sm text-sm">{item.organization || '-'}</td>
                  <td className="py-sm px-sm text-sm">{item.department || '-'}</td>
                  <td className="py-sm px-sm text-sm">{item.workflow_state}</td>
                  <td className="py-sm px-sm">
                    <div className="flex gap-xs">
                      <button
                        type="button"
                        disabled={busyId === item.contract_id}
                        onClick={() => handleApprove(item.contract_id)}
                        className="px-sm py-xs rounded bg-primary text-on-primary text-xs font-semibold disabled:opacity-60"
                      >
                        Approve
                      </button>
                      <button
                        type="button"
                        disabled={busyId === item.contract_id}
                        onClick={() => handleSendBack(item.contract_id, 'Requires correction')}
                        className="px-sm py-xs rounded border border-outline-variant text-xs font-semibold disabled:opacity-60"
                      >
                        Send Back
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
};

export default Approvals;
