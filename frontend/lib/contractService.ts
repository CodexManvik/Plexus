export type WorkflowState = "STAGED_DRAFT" | "PENDING_APPROVAL" | "PRODUCTION_ACTIVE";

export type ContractVersionResponse = {
    contract_id: string;
    version_number: number;
    workflow_state: WorkflowState;
    is_current: boolean;
    etag: string;
};

export type ParameterResponse = {
    parameter_id: number;
    parameter_key: string;
    original_extract?: string | null;
    user_override?: string | null;
    combined_score?: number | null;
    spatial_json?: SpatialBox | null; 
};

export type SpatialBox = {
    page: number;
    x_min: number;
    y_min: number;
    x_max: number;
    y_max: number;
    page_width?: number;
    page_height?: number;
};

export type ContractParameter = ParameterResponse & {
    verified?: boolean;
};

export type BatchAcceptResult = {
    updated: number;
    applyTo: (rows: ContractParameter[]) => ContractParameter[];
};

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000";

function ensureOk(response: Response) {
    if (!response.ok) {
        throw new Error(`HTTP Error: ${response.status} ${response.statusText}`);
    }
}

function alertOnConflict() {
    alert("This contract was modified by another user. Please refresh to see the latest version.");
}

// 1. Create a fresh contract ledger in PostgreSQL
export async function createContract(contractType: string = "General Agreement"): Promise<ContractVersionResponse> {
    const id = "DOC-" + Math.random().toString(36).substring(2, 9).toUpperCase();
    const response = await fetch(`${API_BASE_URL}/contracts`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            contract_id: id,
            contract_type: contractType,
            workflow_state: "STAGED_DRAFT"
        })
    });
    ensureOk(response);
    return response.json();
}

// 2. Feed text to local Llama 3 to get structured JSON parameters
// 2. Feed text to local Llama 3 to get structured JSON parameters
export async function extractContractParameters(contractId: string, text: string): Promise<ContractParameter[]> {
    const requestBody = {
        contract_text: text,
        parameters: [
            "Governing Law",
            "Limitation of Liability",
            "Effective Date",
            "Payment Terms",
            "Confidentiality Requirements"
        ]
    };
    
    // FIX: Removed "/versions/1" to match the FastAPI main.py router exactly
    const response = await fetch(`${API_BASE_URL}/contracts/${contractId}/extract`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(requestBody)
    });
    
    ensureOk(response);
    return response.json();
}

// 3. Save operator edits to the database
export async function updateParameterOverride(parameterId: number, userOverride: string): Promise<ParameterResponse> {
    const response = await fetch(`${API_BASE_URL}/parameters/${parameterId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_override: userOverride })
    });
    ensureOk(response);
    return response.json();
}

function applyBatchApprovalToState(rows: ContractParameter[]): ContractParameter[] {
    return rows.map((row) => {
        const hasOverride = row.user_override && row.user_override.trim().length > 0;
        if (hasOverride) return row; // Protect human edits
        return {
            ...row,
            user_override: row.original_extract,
            verified: true,
            combined_score: 1.0,
        };
    });
}

export async function submitBatchApproval(
    contractId: string,
    versionNumber: number,
): Promise<BatchAcceptResult> {
    try {
        const response = await fetch(
            `${API_BASE_URL}/contracts/${contractId}/versions/${versionNumber}/batch-accept`,
            { method: "POST", headers: { "Content-Type": "application/json" } },
        );
        if (response.status === 409) {
            alertOnConflict();
            throw new Error("Conflict");
        }
        ensureOk(response);
        const data = (await response.json()) as { updated?: number };
        return {
            updated: data.updated ?? 0,
            applyTo: applyBatchApprovalToState,
        };
    } catch (error) {
        if ((error as Error & { status?: number }).status === 409) alertOnConflict();
        throw error;
    }
}