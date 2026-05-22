"use client";

import { useEffect, useMemo, useState, type ChangeEvent } from "react";
import { useSearchParams } from "next/navigation";

import ContractValidationWorkspace from "../../components/ContractValidationWorkspace";
import {
  type ContractParameter,
  type ContractVersionResponse,
  fetchContractParameters,
  fetchContractVersion,
  submitBatchApproval,
  triggerStateTransition,
  updateParameterOverride,
} from "../../lib/contractService";

const DEFAULT_PDF = "/sample.pdf";

export default function ValidationPage() {
  const searchParams = useSearchParams();
  const contractId = searchParams.get("contractId")?.trim() ?? "";
  const versionParam = searchParams.get("version") ?? "1";
  const queryPdf = searchParams.get("pdf");

  const [uploadedFile, setUploadedFile] = useState<File | null>(null);
  const [uploadedPdfUrl, setUploadedPdfUrl] = useState<string | null>(null);
  const [pdfUrlState, setPdfUrlState] = useState<string>(queryPdf ?? DEFAULT_PDF);

  useEffect(() => {
    const query = searchParams.get("pdf");
    if (!uploadedFile) {
      setPdfUrlState(query ?? DEFAULT_PDF);
    }
  }, [searchParams, uploadedFile]);

  useEffect(() => {
    return () => {
      if (uploadedPdfUrl?.startsWith("blob:")) {
        URL.revokeObjectURL(uploadedPdfUrl);
      }
    };
  }, [uploadedPdfUrl]);

  const pdfUrl = uploadedPdfUrl ?? pdfUrlState;

  const versionNumber = useMemo(() => {
    const parsed = Number(versionParam);
    return Number.isFinite(parsed) && parsed > 0 ? parsed : 1;
  }, [versionParam]);

  const [version, setVersion] = useState<ContractVersionResponse | null>(null);
  const [parameters, setParameters] = useState<ContractParameter[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!contractId) {
      setVersion(null);
      setParameters([]);
      return;
    }
    let cancelled = false;

    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const [versionData, paramRows] = await Promise.all([
          fetchContractVersion(contractId, versionNumber),
          fetchContractParameters(contractId, versionNumber),
        ]);
        if (!cancelled) {
          setVersion(versionData);
          setParameters(paramRows);
        }
      } catch (err) {
        if (!cancelled) {
          setError((err as Error).message || "Failed to load contract data");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    load();
    return () => {
      cancelled = true;
    };
  }, [contractId, versionNumber]);

  const handleOverrideChange = async (parameterId: number, value: string) => {
    try {
      const updated = await updateParameterOverride(parameterId, value);
      setParameters((prev) =>
        prev.map((row) =>
          row.parameter_id === parameterId
            ? {
                ...row,
                user_override: updated.user_override ?? value,
                combined_score: updated.combined_score ?? row.combined_score,
              }
            : row,
        ),
      );
    } catch (err) {
      setError((err as Error).message || "Failed to update parameter");
    }
  };

  const handlePdfUpload = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }

    if (file.type !== "application/pdf") {
      setError("Please upload a PDF file.");
      return;
    }

    setError(null);
    setUploadedFile(file);

    if (uploadedPdfUrl?.startsWith("blob:")) {
      URL.revokeObjectURL(uploadedPdfUrl);
    }

    setUploadedPdfUrl(URL.createObjectURL(file));
  };

  const clearUploadedPdf = () => {
    if (uploadedPdfUrl?.startsWith("blob:")) {
      URL.revokeObjectURL(uploadedPdfUrl);
    }
    setUploadedFile(null);
    setUploadedPdfUrl(null);
    setPdfUrlState(queryPdf ?? DEFAULT_PDF);
  };

  const handleBatchAccept = async () => {
    if (!version) {
      return;
    }
    try {
      const result = await submitBatchApproval(
        version.contract_id,
        version.version_number,
        version.etag,
      );
      setParameters((prev) => result.applyTo(prev));
    } catch (err) {
      setError((err as Error).message || "Batch accept failed");
    }
  };

  const handleTransition = async (action: "submit" | "approve") => {
    if (!version) {
      return;
    }
    try {
      const next = await triggerStateTransition(version.contract_id, action, version.etag);
      setVersion(next);
    } catch (err) {
      setError((err as Error).message || "State transition failed");
    }
  };

  return (
    <div className="validation-shell">
      <header className="validation-header">
        <div>
          <h1>Contract Validation</h1>
          <p>
            Contract <strong>{contractId || "—"}</strong> · Version {versionNumber}
          </p>
          {version && <span className="state">{version.workflow_state}</span>}
        </div>

        <div className="upload-area">
          <label className="upload-button">
            <input type="file" accept="application/pdf" onChange={handlePdfUpload} />
            {uploadedFile ? `Uploaded: ${uploadedFile.name}` : "Upload PDF"}
          </label>
          {uploadedFile && (
            <button type="button" className="clear-upload" onClick={clearUploadedPdf}>
              Clear
            </button>
          )}
        </div>

        <div className="actions">
          <button type="button" onClick={handleBatchAccept} disabled={!version || loading}>
            Batch Accept
          </button>
          <button
            type="button"
            onClick={() => handleTransition("submit")}
            disabled={!version || loading}
          >
            Submit
          </button>
          <button
            type="button"
            onClick={() => handleTransition("approve")}
            disabled={!version || loading}
          >
            Approve
          </button>
        </div>
      </header>

      {error && <div className="error">{error}</div>}

      <ContractValidationWorkspace
        pdfUrl={pdfUrl}
        parameters={parameters}
        onOverrideChange={handleOverrideChange}
      />

      <style jsx>{`
        .validation-shell {
          min-height: 100vh;
          background: #0b1222;
        }

        .validation-header {
          display: grid;
          grid-template-columns: minmax(0, 1fr) auto auto;
          align-items: center;
          padding: 16px 24px;
          color: #f8fafc;
          gap: 16px;
          row-gap: 12px;
        }

        .validation-header h1 {
          margin: 0;
          font-size: 1.4rem;
        }

        .upload-area {
          display: flex;
          align-items: center;
          gap: 10px;
          flex-wrap: wrap;
        }

        .upload-button {
          position: relative;
          display: inline-flex;
          align-items: center;
          justify-content: center;
          padding: 10px 16px;
          background: rgba(34, 197, 94, 0.18);
          border: 1px solid rgba(34, 197, 94, 0.4);
          color: #d9f99d;
          border-radius: 999px;
          cursor: pointer;
          font-size: 0.95rem;
          overflow: hidden;
        }

        .upload-button input {
          position: absolute;
          inset: 0;
          width: 100%;
          height: 100%;
          opacity: 0;
          cursor: pointer;
        }

        .clear-upload {
          padding: 10px 16px;
          border-radius: 999px;
          border: 1px solid rgba(148, 163, 184, 0.4);
          background: rgba(15, 23, 42, 0.85);
          color: #f8fafc;
          cursor: pointer;
        }

        .validation-header p {
          margin: 4px 0 0;
          color: rgba(226, 232, 240, 0.75);
        }

        .state {
          display: inline-flex;
          margin-top: 6px;
          padding: 4px 10px;
          border-radius: 999px;
          background: rgba(14, 165, 233, 0.2);
          color: #e0f2fe;
          font-size: 0.75rem;
          letter-spacing: 0.08em;
          text-transform: uppercase;
        }

        .actions {
          display: flex;
          gap: 10px;
        }

        .actions button {
          border: 1px solid rgba(148, 163, 184, 0.4);
          background: rgba(15, 23, 42, 0.85);
          color: #f8fafc;
          padding: 8px 14px;
          border-radius: 10px;
          cursor: pointer;
        }

        .actions button:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }

        .error {
          margin: 0 24px 12px;
          padding: 10px 14px;
          border-radius: 10px;
          background: rgba(239, 68, 68, 0.2);
          color: #fee2e2;
        }

        .validation-empty {
          min-height: 100vh;
          display: grid;
          place-items: center;
          text-align: center;
          color: #e2e8f0;
          background: #0b1222;
          padding: 32px;
        }

        .validation-empty code {
          background: rgba(148, 163, 184, 0.2);
          padding: 2px 6px;
          border-radius: 6px;
        }
      `}</style>
    </div>
  );
}
