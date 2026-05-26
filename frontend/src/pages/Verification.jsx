import React from 'react';
import { useNavigate } from 'react-router-dom';
import useVerification from '../hooks/useVerification';

const Verification = () => {
  const navigate = useNavigate();
  const {
    contractId,
    contract,
    parameters,
    activeParamId,
    setActiveParamId,
    loading,
    busy,
    error,
    message,
    handleUpdateValue,
    handleToggleVerify,
    handleSubmitDraft,
    handleSubmitForApproval,
  } = useVerification();

  return (
    <div className="flex flex-col gap-lg w-full min-h-screen">
      <div className="flex justify-between items-end">
        <div>
          <h1 className="text-3xl font-black text-primary tracking-tight">Verification Workspace</h1>
          <p className="text-sm text-on-surface-variant font-medium">
            Contract ID: {contractId || 'No contract selected'} | Status:{' '}
            {contract?.workflow_state || 'N/A'}
          </p>
        </div>
        <button
          type="button"
          onClick={() => navigate('/approvals')}
          className="bg-surface border border-outline-variant px-md py-sm rounded text-sm font-semibold"
        >
          View Approvals
        </button>
      </div>

      {error ? (
        <div className="p-sm rounded border border-error bg-error-container text-on-error-container text-sm">
          {error}
        </div>
      ) : null}
      {message ? (
        <div className="p-sm rounded border border-primary bg-primary-fixed/20 text-primary text-sm">
          {message}
        </div>
      ) : null}

      {loading ? (
        <div className="text-sm text-on-surface-variant">Loading verification data...</div>
      ) : (
        <div className="bg-surface-container-lowest border border-outline-variant rounded-xl p-lg overflow-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-outline-variant">
                <th className="py-sm text-xs font-black text-on-surface-variant">PARAMETER</th>
                <th className="py-sm text-xs font-black text-on-surface-variant">ORIGINAL</th>
                <th className="py-sm text-xs font-black text-on-surface-variant">CHANGED</th>
                <th className="py-sm text-xs font-black text-on-surface-variant">VERIFY</th>
              </tr>
            </thead>
            <tbody>
              {parameters.map((param) => {
                const verified = Boolean(param.is_verified);
                return (
                  <tr
                    key={param.parameter_id}
                    className={`border-b border-outline-variant/40 ${
                      activeParamId === param.parameter_id ? 'bg-primary-fixed/10' : ''
                    }`}
                    onClick={() => setActiveParamId(param.parameter_id)}
                  >
                    <td className="py-sm pr-sm align-top">
                      <p className="text-xs font-bold text-primary">{param.header_name}</p>
                      <p className="text-xs text-on-surface-variant">{param.param_name}</p>
                    </td>
                    <td className="py-sm pr-sm align-top text-xs">{param.original_extract || '-'}</td>
                    <td className="py-sm pr-sm align-top">
                      <textarea
                        className="w-full bg-surface border border-outline-variant rounded p-xs text-xs"
                        rows={3}
                        defaultValue={param.user_override || param.original_extract || ''}
                        onBlur={(event) =>
                          handleUpdateValue(param.parameter_id, event.target.value)
                        }
                      />
                    </td>
                    <td className="py-sm align-top">
                      <button
                        type="button"
                        disabled={busy}
                        className={`px-sm py-xs rounded text-xs font-semibold ${
                          verified
                            ? 'bg-primary text-on-primary'
                            : 'bg-surface border border-outline-variant'
                        }`}
                        onClick={(event) => {
                          event.stopPropagation();
                          handleToggleVerify(param.parameter_id, !verified);
                        }}
                      >
                        {verified ? 'Verified' : 'Mark Verify'}
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>

          <div className="flex gap-sm mt-md">
            <button
              type="button"
              disabled={busy}
              onClick={handleSubmitDraft}
              className="px-md py-sm rounded border border-outline-variant bg-surface text-sm font-semibold"
            >
              Save Draft
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={handleSubmitForApproval}
              className="px-md py-sm rounded bg-primary text-on-primary text-sm font-semibold"
            >
              Submit For Approval
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default Verification;
