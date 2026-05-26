import React from 'react';
import useMaintenance from '../hooks/useMaintenance';

const inputClass =
  'w-full bg-surface border border-outline-variant rounded px-sm py-xs text-sm outline-none focus:ring-1 focus:ring-primary';

const Maintenance = () => {
  const {
    rules,
    ruleForm,
    selectedRuleId,
    systemStatus,
    logs,
    loading,
    busy,
    error,
    updateRuleField,
    editRule,
    saveRule,
    deleteRule,
    resetRuleForm,
    triggerSync,
  } = useMaintenance();

  return (
    <div className="flex flex-col gap-lg w-full min-h-screen">
      <div>
        <h1 className="text-3xl font-black text-primary tracking-tight">Master Data Maintenance</h1>
        <p className="text-sm text-on-surface-variant font-medium">
          Maintain extraction rules and monitor backend system diagnostics.
        </p>
      </div>

      {error ? (
        <div className="p-sm rounded border border-error bg-error-container text-on-error-container text-sm">
          {error}
        </div>
      ) : null}

      {loading ? (
        <div className="text-sm text-on-surface-variant">Loading maintenance data...</div>
      ) : (
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-lg">
          <div className="bg-surface-container-lowest border border-outline-variant rounded-xl p-lg space-y-sm">
            <h2 className="font-bold text-primary">
              {selectedRuleId ? `Edit Rule #${selectedRuleId}` : 'Create Rule'}
            </h2>
            <input
              className={inputClass}
              placeholder="Contract Type"
              value={ruleForm.contract_type}
              onChange={(e) => updateRuleField('contract_type', e.target.value)}
            />
            <input
              className={inputClass}
              placeholder="Agreement Type"
              value={ruleForm.agreement_type}
              onChange={(e) => updateRuleField('agreement_type', e.target.value)}
            />
            <input
              className={inputClass}
              placeholder="Parameter Head"
              value={ruleForm.parameter_head}
              onChange={(e) => updateRuleField('parameter_head', e.target.value)}
            />
            <input
              className={inputClass}
              placeholder="Parameter Name"
              value={ruleForm.parameter_name}
              onChange={(e) => updateRuleField('parameter_name', e.target.value)}
            />
            <input
              className={inputClass}
              placeholder="Parameter Logic (example: P1 + P2 + P3)"
              value={ruleForm.parameter_logic}
              onChange={(e) => updateRuleField('parameter_logic', e.target.value)}
            />
            <div className="flex gap-xs">
              <button
                type="button"
                disabled={busy}
                onClick={saveRule}
                className="px-md py-sm rounded bg-primary text-on-primary text-sm font-semibold disabled:opacity-60"
              >
                {selectedRuleId ? 'Update Rule' : 'Create Rule'}
              </button>
              <button
                type="button"
                disabled={busy}
                onClick={resetRuleForm}
                className="px-md py-sm rounded border border-outline-variant text-sm font-semibold"
              >
                Reset
              </button>
            </div>
          </div>

          <div className="bg-surface-container-lowest border border-outline-variant rounded-xl p-lg space-y-sm">
            <h2 className="font-bold text-primary">System Status</h2>
            <p className="text-sm">API: {systemStatus?.api || 'unknown'}</p>
            <p className="text-sm">Database: {systemStatus?.database || 'unknown'}</p>
            <p className="text-sm">Driver: {systemStatus?.databaseDriver || 'unknown'}</p>
            <button
              type="button"
              disabled={busy}
              onClick={triggerSync}
              className="px-md py-sm rounded bg-primary text-on-primary text-sm font-semibold disabled:opacity-60"
            >
              Trigger Sync
            </button>
          </div>
        </div>
      )}

      <div className="bg-surface-container-lowest border border-outline-variant rounded-xl overflow-auto">
        <div className="px-lg py-sm border-b border-outline-variant">
          <h2 className="font-bold text-primary">Master Extraction Rules</h2>
        </div>
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="border-b border-outline-variant">
              <th className="py-sm px-sm text-xs font-black text-on-surface-variant">RULE</th>
              <th className="py-sm px-sm text-xs font-black text-on-surface-variant">HEAD / NAME</th>
              <th className="py-sm px-sm text-xs font-black text-on-surface-variant">LOGIC</th>
              <th className="py-sm px-sm text-xs font-black text-on-surface-variant">ACTION</th>
            </tr>
          </thead>
          <tbody>
            {rules.map((rule) => (
              <tr key={rule.rule_id} className="border-b border-outline-variant/40">
                <td className="py-sm px-sm text-xs">
                  {rule.contract_type} • {rule.agreement_type}
                </td>
                <td className="py-sm px-sm text-xs">
                  <p className="font-semibold">{rule.parameter_head}</p>
                  <p className="text-on-surface-variant">{rule.parameter_name}</p>
                </td>
                <td className="py-sm px-sm text-xs">{rule.parameter_logic || '-'}</td>
                <td className="py-sm px-sm">
                  <div className="flex gap-xs">
                    <button
                      type="button"
                      onClick={() => editRule(rule)}
                      className="px-sm py-xs rounded border border-outline-variant text-xs font-semibold"
                    >
                      Edit
                    </button>
                    <button
                      type="button"
                      onClick={() => deleteRule(rule.rule_id)}
                      className="px-sm py-xs rounded border border-error text-xs font-semibold text-error"
                    >
                      Delete
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="bg-surface-container-lowest border border-outline-variant rounded-xl p-lg">
        <h2 className="font-bold text-primary mb-sm">Recent Audit Logs</h2>
        {logs.length === 0 ? (
          <p className="text-sm text-on-surface-variant">No audit logs found.</p>
        ) : (
          <div className="space-y-xs">
            {logs.map((log) => (
              <div key={log.id} className="p-sm border border-outline-variant rounded">
                <p className="text-xs font-semibold">
                  {log.contract_id} • {log.action_type}
                </p>
                <p className="text-xs text-on-surface-variant">
                  {log.modified_by} • {log.timestamp}
                </p>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default Maintenance;
