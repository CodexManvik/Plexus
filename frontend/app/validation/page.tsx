"use client";

import { useState } from "react";
import * as pdfjsLib from "pdfjs-dist";
import ContractValidationWorkspace from "../../components/ContractValidationWorkspace";
import {
    type ContractParameter,
    createContract,
    extractContractParameters,
    updateParameterOverride,
    submitBatchApproval
} from "../../lib/contractService";

pdfjsLib.GlobalWorkerOptions.workerSrc = `//cdnjs.cloudflare.com/ajax/libs/pdf.js/${pdfjsLib.version}/pdf.worker.min.js`;

export default function ValidationPage() {
    const [pdfFile, setPdfFile] = useState<File | null>(null);
    const [pdfUrl, setPdfUrl] = useState<string | null>(null);
    const [parameters, setParameters] = useState<ContractParameter[]>([]);
    const [isUploading, setIsUploading] = useState(false);
    const [contractId, setContractId] = useState<string | null>(null);

    const extractTextFromPdf = async (file: File) => {
        const arrayBuffer = await file.arrayBuffer();
        const pdf = await pdfjsLib.getDocument({ data: arrayBuffer }).promise;
        let fullText = "";
        for (let i = 1; i <= pdf.numPages; i++) {
            const page = await pdf.getPage(i);
            const textContent = await page.getTextContent();
            const pageText = textContent.items.map((item: any) => item.str).join(" ");
            fullText += pageText + "\n\n";
        }
        return fullText;
    };

    const onFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (!file) return;

        setPdfFile(file);
        setPdfUrl(URL.createObjectURL(file));
        setIsUploading(true);

        try {
            // 1. Client-side layout text scrape
            const text = await extractTextFromPdf(file);
            
            // 2. Setup Database ledger object
            const contract = await createContract("Uploaded Agreement");
            setContractId(contract.contract_id);
            
            // 3. Pipe to local Llama 3 via FastAPI
            const extractedParams = await extractContractParameters(contract.contract_id, text);
            setParameters(extractedParams);
        } catch (error) {
            console.error("Extraction failed:", error);
            alert("Extraction failed. Ensure your FastAPI backend (Port 8000) and Llama server (Port 8080) are active.");
        } finally {
            setIsUploading(false);
        }
    };

    const handleOverrideChange = async (parameterId: number, value: string) => {
        try {
            await updateParameterOverride(parameterId, value); // Save specific edit to Postgres
        } catch (error) {
            console.error("Failed to save override:", error);
        }
    };

    const handleBatchAccept = async () => {
        if (!contractId) return;
        try {
            const result = await submitBatchApproval(contractId, 1);
            setParameters(result.applyTo(parameters));
            alert(`Successfully batch-verified ${result.updated} unchanged parameters.`);
        } catch (error) {
            console.error("Batch accept failed:", error);
        }
    };

    return (
        <div className="container">
            <header className="header">
                <h1>Contract Validation Workspace</h1>
                {parameters.length > 0 && (
                    <div className="header-actions">
                        <button className="btn-secondary" onClick={handleBatchAccept}>
                            Batch Accept Unchanged
                        </button>
                        <button className="btn-primary" onClick={() => alert("Forwarded to Operation Head!")}>
                            Submit for Approval
                        </button>
                    </div>
                )}
            </header>

            {!pdfFile && (
                <div className="upload-zone">
                    <input type="file" accept="application/pdf" onChange={onFileUpload} id="pdf-upload" />
                    <label htmlFor="pdf-upload" className="upload-label">
                        <div className="upload-icon">📄</div>
                        <span>Drag & Drop PDF or Click to Browse</span>
                    </label>
                </div>
            )}

            {isUploading && (
                <div className="loading-state">
                    <div className="spinner"></div>
                    <p>Llama 3 is analyzing document layout & extracting parameters locally...</p>
                </div>
            )}

            {pdfUrl && !isUploading && parameters.length > 0 && (
                <ContractValidationWorkspace
                    pdfUrl={pdfUrl}
                    parameters={parameters}
                    onOverrideChange={handleOverrideChange}
                />
            )}

            <style jsx>{`
                .container {
                    max-width: 1600px;
                    margin: 0 auto;
                    padding: 2rem;
                }
                .header {
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    margin-bottom: 2rem;
                }
                h1 {
                    font-size: 1.5rem;
                    font-weight: 600;
                    color: #0f172a;
                }
                .header-actions {
                    display: flex;
                    gap: 1rem;
                }
                button {
                    padding: 0.5rem 1rem;
                    border-radius: 6px;
                    font-weight: 500;
                    cursor: pointer;
                    transition: all 0.2s;
                }
                .btn-secondary {
                    background: white;
                    border: 1px solid #cbd5e1;
                    color: #475569;
                }
                .btn-secondary:hover {
                    background: #f8fafc;
                }
                .btn-primary {
                    background: #2563eb;
                    border: none;
                    color: white;
                }
                .btn-primary:hover {
                    background: #1d4ed8;
                }
                .upload-zone {
                    border: 2px dashed #cbd5e1;
                    border-radius: 12px;
                    padding: 4rem 2rem;
                    text-align: center;
                    background: #f8fafc;
                    transition: border-color 0.2s;
                }
                .upload-zone:hover {
                    border-color: #94a3b8;
                }
                input[type="file"] {
                    display: none;
                }
                .upload-label {
                    cursor: pointer;
                    display: flex;
                    flex-direction: column;
                    align-items: center;
                    gap: 1rem;
                    color: #475569;
                    font-size: 1.1rem;
                }
                .upload-icon {
                    font-size: 3rem;
                }
                .loading-state {
                    display: flex;
                    flex-direction: column;
                    align-items: center;
                    gap: 1.5rem;
                    padding: 4rem;
                    color: #475569;
                }
                .spinner {
                    width: 40px;
                    height: 40px;
                    border: 3px solid #e2e8f0;
                    border-top-color: #2563eb;
                    border-radius: 50%;
                    animation: spin 1s linear infinite;
                }
                @keyframes spin {
                    to {
                        transform: rotate(360deg);
                    }
                }
            `}</style>
        </div>
    );
}