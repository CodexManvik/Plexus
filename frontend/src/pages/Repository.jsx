import React from 'react';
import { useNavigate } from 'react-router-dom';
import useRepository from '../hooks/useRepository';

const selectClass =
  'w-full bg-surface border border-outline-variant rounded px-sm py-xs text-sm outline-none focus:ring-1 focus:ring-primary';

const Repository = () => {
  const navigate = useNavigate();
  const {
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
    refresh,
  } = useRepository();

  return (
    <div className="flex flex-col gap-lg w-full min-h-screen">
      <div className="flex justify-between items-end">
        <div>
          <h1 className="text-3xl font-black text-primary tracking-tight">Contract Repository</h1>
          <p className="text-sm text-on-surface-variant font-medium">
            Search and filter stored contracts with complete metadata.
          </p>
        </div>
        <button
          type="button"
          onClick={refresh}
          className="px-md py-sm bg-primary text-on-primary rounded text-sm font-semibold"
        >
          Refresh
        </button>
      </div>

      {error ? (
        <div className="p-sm rounded border border-error bg-error-container text-on-error-container text-sm">
          {error}
        </div>
      ) : null}

      <div className="bg-surface-container-lowest border border-outline-variant rounded-xl p-lg space-y-sm">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-sm">
          <input
            className={selectClass}
            placeholder="Search by contract id, number, text..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
          <select className={selectClass} value={filters.organization} onChange={(e) => updateFilter('organization', e.target.value)}>
            <option value="">All Organizations</option>
            {metadataOptions.organizations.map((value) => <option key={value} value={value}>{value}</option>)}
          </select>
          <select className={selectClass} value={filters.business_unit} onChange={(e) => updateFilter('business_unit', e.target.value)}>
            <option value="">All Business Units</option>
            {metadataOptions.business_units.map((value) => <option key={value} value={value}>{value}</option>)}
          </select>
          <select className={selectClass} value={filters.contract_type} onChange={(e) => updateFilter('contract_type', e.target.value)}>
            <option value="">All Contract Types</option>
            {metadataOptions.contract_types.map((value) => <option key={value} value={value}>{value}</option>)}
          </select>
          <select className={selectClass} value={filters.agreement_type} onChange={(e) => updateFilter('agreement_type', e.target.value)}>
            <option value="">All Agreement Types</option>
            {metadataOptions.agreement_types.map((value) => <option key={value} value={value}>{value}</option>)}
          </select>
          <select className={selectClass} value={filters.workflow_state} onChange={(e) => updateFilter('workflow_state', e.target.value)}>
            <option value="">All Workflow States</option>
            <option value="STAGED_DRAFT">STAGED_DRAFT</option>
            <option value="PENDING_APPROVAL">PENDING_APPROVAL</option>
            <option value="APPROVED">APPROVED</option>
            <option value="SENT_BACK">SENT_BACK</option>
          </select>
        </div>
        {hasActiveFilters ? (
          <button
            type="button"
            onClick={clearFilters}
            className="px-md py-xs rounded border border-outline-variant text-sm"
          >
            Clear Filters
          </button>
        ) : null}
      </div>

      <div className="bg-surface-container-lowest border border-outline-variant rounded-xl overflow-auto">
        <div className="px-lg py-sm border-b border-outline-variant text-sm text-on-surface-variant">
          Total: {total}
        </div>
        {loading ? (
          <div className="p-lg text-sm text-on-surface-variant">Loading contracts...</div>
        ) : results.length === 0 ? (
          <div className="p-lg text-sm text-on-surface-variant">No contracts found.</div>
        ) : (
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-outline-variant">
                <th className="py-sm px-sm text-xs font-black text-on-surface-variant">ID</th>
                <th className="py-sm px-sm text-xs font-black text-on-surface-variant">ORG / BU</th>
                <th className="py-sm px-sm text-xs font-black text-on-surface-variant">TYPE</th>
                <th className="py-sm px-sm text-xs font-black text-on-surface-variant">PARTNER</th>
                <th className="py-sm px-sm text-xs font-black text-on-surface-variant">STATE</th>
                <th className="py-sm px-sm text-xs font-black text-on-surface-variant">ACTION</th>
              </tr>
            </thead>
            <tbody>
              {results.map((contract) => (
                <tr key={contract.contract_id} className="border-b border-outline-variant/40">
                  <td className="py-sm px-sm text-sm font-semibold text-primary">{contract.contract_id}</td>
                  <td className="py-sm px-sm text-sm">
                    {contract.organization}
                    <p className="text-xs text-on-surface-variant">{contract.business_unit}</p>
                  </td>
                  <td className="py-sm px-sm text-sm">
                    {contract.contract_type}
                    <p className="text-xs text-on-surface-variant">{contract.agreement_type}</p>
                  </td>
                  <td className="py-sm px-sm text-sm">{contract.customer_partner_name || '-'}</td>
                  <td className="py-sm px-sm text-sm">{contract.workflow_state}</td>
                  <td className="py-sm px-sm">
                    <button
                      type="button"
                      className="px-sm py-xs rounded bg-primary text-on-primary text-xs font-semibold"
                      onClick={() => {
                        localStorage.setItem('currentContractId', contract.contract_id);
                        navigate('/extraction');
                      }}
                    >
                      Open
                    </button>
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

export default Repository;
