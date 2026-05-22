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
    spatial_json?: SpatialBox | null;
    param_group_id?: string | null;
    param_structure_type?: string | null;
    verified?: boolean;
};

export type BatchAcceptResult = {
    updated: number;
    applyTo: (rows: ContractParameter[]) => ContractParameter[];
};

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

function applyBatchApprovalToState(rows: ContractParameter[]): ContractParameter[] {
    return rows.map((row) => {
        const hasOverride = row.user_override && row.user_override.trim().length > 0;
        const score = row.combined_score ?? 0;
        if (hasOverride || score < 0.99) {
            return row;
        }

        return {
            ...row,
            user_override: row.original_extract ?? row.user_override ?? "",
            combined_score: 1.0,
            verified: true,
        };
    });
}

function buildHeaders(etag?: string): Record<string, string> {
    const headers: Record<string, string> = { "Content-Type": "application/json" };
    if (etag) {
        headers["If-Match"] = etag;
    }
    return headers;
}

function ensureOk(response: Response): void {
    if (!response.ok) {
        const error = new Error(`Request failed with status ${response.status}`);
        (error as Error & { status?: number }).status = response.status;
        throw error;
    }
}

function alertOnConflict(): void {
    if (typeof window !== "undefined") {
        window.alert("This record was updated elsewhere. Please refresh to get the latest _etag.");
    }
}

export async function fetchContractVersion(
    contractId: string,
    versionNumber: number,
): Promise<ContractVersionResponse> {
    try {
        const response = await fetch(
            `${API_BASE_URL}/contracts/${contractId}/versions/${versionNumber}`,
            { method: "GET", headers: { "Content-Type": "application/json" } },
        );
        if (response.status === 409) {
            alertOnConflict();
            throw new Error("Conflict");
        }
        ensureOk(response);
        return (await response.json()) as ContractVersionResponse;
    } catch (error) {
        if ((error as Error & { status?: number }).status === 409) {
            alertOnConflict();
        }
        throw error;
    }
}

export async function fetchContractParameters(
    contractId: string,
    versionNumber: number,
): Promise<ContractParameter[]> {
    try {
        const response = await fetch(
            `${API_BASE_URL}/contracts/${contractId}/versions/${versionNumber}/parameters`,
            { method: "GET", headers: { "Content-Type": "application/json" } },
        );
        if (response.status === 409) {
            alertOnConflict();
            throw new Error("Conflict");
        }
        ensureOk(response);
        return (await response.json()) as ContractParameter[];
    } catch (error) {
        if ((error as Error & { status?: number }).status === 409) {
            alertOnConflict();
        }
        throw error;
    }
}

export async function updateParameterOverride(
    parameterId: number,
    userOverride: string,
): Promise<ParameterResponse> {
    try {
        const response = await fetch(`${API_BASE_URL}/parameters/${parameterId}`, {
            method: "PATCH",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ user_override: userOverride }),
        });
        if (response.status === 409) {
            alertOnConflict();
            throw new Error("Conflict");
        }
        ensureOk(response);
        return (await response.json()) as ParameterResponse;
    } catch (error) {
        if ((error as Error & { status?: number }).status === 409) {
            alertOnConflict();
        }
        throw error;
    }
}

export async function submitBatchApproval(
    contractId: string,
    versionNumber: number,
    etag?: string,
): Promise<BatchAcceptResult> {
    try {
        const response = await fetch(
            `${API_BASE_URL}/contracts/${contractId}/versions/${versionNumber}/batch-accept`,
            { method: "POST", headers: buildHeaders(etag) },
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
        if ((error as Error & { status?: number }).status === 409) {
            alertOnConflict();
        }
        throw error;
    }
}

export async function triggerStateTransition(
    contractId: string,
    action: "submit" | "approve",
    etag?: string,
): Promise<ContractVersionResponse> {
    const endpoint =
        action === "submit"
            ? `${API_BASE_URL}/contracts/${contractId}/submit-for-approval`
            : `${API_BASE_URL}/contracts/${contractId}/approve`;

    try {
        const response = await fetch(endpoint, {
            method: "POST",
            headers: buildHeaders(etag),
        });
        if (response.status === 409) {
            alertOnConflict();
            throw new Error("Conflict");
        }
        ensureOk(response);
        return (await response.json()) as ContractVersionResponse;
    } catch (error) {
        if ((error as Error & { status?: number }).status === 409) {
            alertOnConflict();
        }
        throw error;
    }
}
