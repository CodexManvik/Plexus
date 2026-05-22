'use client';

import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";

import type { ContractParameter, SpatialBox } from "../lib/contractService";

pdfjs.GlobalWorkerOptions.workerSrc = `//cdnjs.cloudflare.com/ajax/libs/pdf.js/${pdfjs.version}/pdf.worker.min.js`;

const PAGE_GAP = 16;

const defaultSpatial: SpatialBox = {
    page: 1,
    x_min: 0,
    y_min: 0,
    x_max: 0,
    y_max: 0,
};

type ContractValidationWorkspaceProps = {
    pdfUrl: string;
    parameters: ContractParameter[];
    onOverrideChange?: (parameterId: number, value: string) => void;
};

type ConnectorState = {
    width: number;
    height: number;
    y1: number;
    y2: number;
};

export default function ContractValidationWorkspace({
    pdfUrl,
    parameters,
    onOverrideChange,
}: ContractValidationWorkspaceProps) {
    const [rows, setRows] = useState<ContractParameter[]>(parameters);
    const [numPages, setNumPages] = useState(1);
    const [pageSizes, setPageSizes] = useState<Array<{ width: number; height: number }>>([]);
    const [activeId, setActiveId] = useState<number | null>(null);
    const [connector, setConnector] = useState<ConnectorState | null>(null);
    const [pageWidth, setPageWidth] = useState(720);

    const containerRef = useRef<HTMLDivElement | null>(null);
    const leftPanelRef = useRef<HTMLDivElement | null>(null);
    const centerPanelRef = useRef<HTMLDivElement | null>(null);
    const rightPanelRef = useRef<HTMLDivElement | null>(null);
    const overlayRef = useRef<HTMLDivElement | null>(null);

    const rowRefs = useRef<Record<number, HTMLDivElement | null>>({});
    const overlayRefs = useRef<Record<number, HTMLDivElement | null>>({});
    const pageRefs = useRef<Record<number, HTMLDivElement | null>>({});
    const pendingScrollIdRef = useRef<number | null>(null);

    useEffect(() => {
        setRows(parameters);
    }, [parameters]);

    useLayoutEffect(() => {
        if (!leftPanelRef.current) {
            return;
        }
        const updateWidth = () => {
            const width = leftPanelRef.current?.clientWidth ?? 720;
            setPageWidth(Math.max(width - 32, 320));
        };
        updateWidth();
        const observer = new ResizeObserver(updateWidth);
        observer.observe(leftPanelRef.current);
        return () => observer.disconnect();
    }, []);

    useLayoutEffect(() => {
        const updateSizes = () => {
            const sizes = Array.from({ length: numPages }).map((_, idx) => {
                const ref = pageRefs.current[idx + 1];
                if (!ref) {
                    return { width: 0, height: 0 };
                }
                const rect = ref.getBoundingClientRect();
                return { width: rect.width, height: rect.height };
            });
            setPageSizes(sizes);
        };

        updateSizes();
        const observer = new ResizeObserver(updateSizes);
        Object.values(pageRefs.current).forEach((ref) => {
            if (ref) {
                observer.observe(ref);
            }
        });
        return () => observer.disconnect();
    }, [numPages, pageWidth]);

    const pageOffsets = useMemo(() => {
        let offset = 0;
        return pageSizes.map((size) => {
            const current = offset;
            offset += size.height + PAGE_GAP;
            return current;
        });
    }, [pageSizes]);

    const overlayHeight = useMemo(() => {
        if (!pageSizes.length) {
            return 0;
        }
        return pageSizes.reduce((sum, size) => sum + size.height, 0) + PAGE_GAP * (pageSizes.length - 1);
    }, [pageSizes]);

    useEffect(() => {
        if (!rightPanelRef.current) {
            return;
        }
        const observer = new IntersectionObserver(
            (entries) => {
                entries.forEach((entry) => {
                    const element = entry.target as HTMLDivElement;
                    const id = Number(element.dataset.paramId);
                    if (entry.isIntersecting && pendingScrollIdRef.current === id) {
                        pendingScrollIdRef.current = null;
                        scrollToSpatial(id);
                    }
                });
            },
            { root: rightPanelRef.current, threshold: 0.6 },
        );

        Object.values(rowRefs.current).forEach((row) => {
            if (row) {
                observer.observe(row);
            }
        });

        return () => observer.disconnect();
    }, [rows]);

    useLayoutEffect(() => {
        if (!activeId) {
            setConnector(null);
            return;
        }
        const overlayEl = overlayRefs.current[activeId];
        const rowEl = rowRefs.current[activeId];
        const centerEl = centerPanelRef.current;
        const containerEl = containerRef.current;
        if (!overlayEl || !rowEl || !centerEl || !containerEl) {
            setConnector(null);
            return;
        }

        const overlayRect = overlayEl.getBoundingClientRect();
        const rowRect = rowEl.getBoundingClientRect();
        const containerRect = containerEl.getBoundingClientRect();
        const centerRect = centerEl.getBoundingClientRect();

        const y1 = overlayRect.top + overlayRect.height / 2 - containerRect.top;
        const y2 = rowRect.top + rowRect.height / 2 - containerRect.top;

        setConnector({
            width: centerRect.width,
            height: containerRect.height,
            y1,
            y2,
        });
    }, [activeId, overlayHeight, pageOffsets, pageSizes]);

    const handleOverrideChange = (parameterId: number, value: string) => {
        setRows((prev) =>
            prev.map((row) =>
                row.parameter_id === parameterId
                    ? {
                          ...row,
                          user_override: value,
                      }
                    : row,
            ),
        );
        if (onOverrideChange) {
            onOverrideChange(parameterId, value);
        }
    };

    const handleRowActivate = (parameterId: number) => {
        setActiveId(parameterId);
        pendingScrollIdRef.current = parameterId;
    };

    const scrollToSpatial = (parameterId: number) => {
        const overlayEl = overlayRefs.current[parameterId];
        const leftPanel = leftPanelRef.current;
        if (!overlayEl || !leftPanel) {
            return;
        }
        const panelRect = leftPanel.getBoundingClientRect();
        const overlayRect = overlayEl.getBoundingClientRect();
        const target = leftPanel.scrollTop + overlayRect.top - panelRect.top - 120;
        leftPanel.scrollTo({ top: target, behavior: "smooth" });
    };

    const renderSpatialOverlay = (row: ContractParameter) => {
        const spatial = row.spatial_json ?? defaultSpatial;
        if (!row.spatial_json) {
            return null;
        }
        const pageIndex = Math.max(1, spatial.page) - 1;
        const pageSize = pageSizes[pageIndex];
        if (!pageSize) {
            return null;
        }
        const pageOffset = pageOffsets[pageIndex] ?? 0;
        const scaleX = spatial.page_width ? pageSize.width / spatial.page_width : 1;
        const scaleY = spatial.page_height ? pageSize.height / spatial.page_height : 1;
        const left = spatial.x_min * scaleX;
        const top = pageOffset + spatial.y_min * scaleY;
        const width = Math.max((spatial.x_max - spatial.x_min) * scaleX, 6);
        const height = Math.max((spatial.y_max - spatial.y_min) * scaleY, 6);

        return (
            <div
                key={`${row.parameter_id}-overlay`}
                className={`overlay-box ${activeId === row.parameter_id ? "active" : ""}`}
                ref={(node) => {
                    overlayRefs.current[row.parameter_id] = node;
                }}
                style={{ left, top, width, height }}
                onMouseEnter={() => handleRowActivate(row.parameter_id)}
                role="button"
                tabIndex={0}
                aria-label={`Highlight ${row.parameter_key}`}
            />
        );
    };

    return (
        <div className="workspace" ref={containerRef}>
            <section className="panel pdf-panel" ref={leftPanelRef}>
                <div className="panel-header">
                    <h2>Source Document</h2>
                    <span className="panel-subtitle">Read-only PDF canvas with spatial overlay</span>
                </div>
                <div className="pdf-stage">
                    <Document
                        file={pdfUrl}
                        loading={<div className="pdf-loading">Loading PDF...</div>}
                        onLoadSuccess={(info) => setNumPages(info.numPages)}
                    >
                        {Array.from({ length: numPages }).map((_, index) => {
                            const pageNumber = index + 1;
                            return (
                                <div
                                    className="pdf-page"
                                    key={`page-${pageNumber}`}
                                    ref={(node) => {
                                        pageRefs.current[pageNumber] = node;
                                    }}
                                >
                                    <Page
                                        pageNumber={pageNumber}
                                        width={pageWidth}
                                        renderAnnotationLayer={false}
                                        renderTextLayer={false}
                                    />
                                </div>
                            );
                        })}
                    </Document>
                    <div
                        className="pdf-overlay"
                        ref={overlayRef}
                        style={{ height: overlayHeight || "100%" }}
                    >
                        <div className="overlay-grid" />
                        {rows.map(renderSpatialOverlay)}
                    </div>
                </div>
            </section>

            <section className="panel connector-panel" ref={centerPanelRef}>
                <div className="panel-header">
                    <h2>Trace Link</h2>
                    <span className="panel-subtitle">Spatial alignment bridge</span>
                </div>
                <div className="connector-canvas">
                    <svg
                        className="connector-svg"
                        width="100%"
                        height="100%"
                        viewBox={`0 0 ${connector?.width ?? 100} ${connector?.height ?? 100}`}
                        preserveAspectRatio="none"
                    >
                        <defs>
                            <linearGradient id="flow" x1="0" x2="1" y1="0" y2="0">
                                <stop offset="0%" stopColor="#f97316" />
                                <stop offset="100%" stopColor="#facc15" />
                            </linearGradient>
                        </defs>
                        {connector && (
                            <>
                                <line
                                    x1={0}
                                    y1={connector.y1}
                                    x2={connector.width}
                                    y2={connector.y2}
                                    stroke="url(#flow)"
                                    strokeWidth={4}
                                    strokeLinecap="round"
                                />
                                <circle cx={8} cy={connector.y1} r={6} fill="#f97316" />
                                <circle cx={connector.width - 8} cy={connector.y2} r={6} fill="#facc15" />
                            </>
                        )}
                    </svg>
                </div>
            </section>

            <section className="panel form-panel" ref={rightPanelRef}>
                <div className="panel-header">
                    <h2>Validation Grid</h2>
                    <span className="panel-subtitle">Edit human overrides without losing context</span>
                </div>
                <div className="form-grid">
                    {rows.map((row) => (
                        <div
                            key={row.parameter_id}
                            className={`form-row ${activeId === row.parameter_id ? "active" : ""}`}
                            ref={(node) => {
                                rowRefs.current[row.parameter_id] = node;
                            }}
                            data-param-id={row.parameter_id}
                            onMouseEnter={() => handleRowActivate(row.parameter_id)}
                            onFocus={() => handleRowActivate(row.parameter_id)}
                        >
                            <div className="form-row-header">
                                <span className="param-key">{row.parameter_key}</span>
                                <span className={`status ${row.combined_score && row.combined_score >= 0.99 ? "high" : ""}`}>
                                    {row.combined_score?.toFixed(2) ?? "--"}
                                </span>
                            </div>
                            <label className="form-label">Original Extract</label>
                            <textarea
                                className="field read-only"
                                value={row.original_extract ?? ""}
                                readOnly
                                rows={2}
                            />
                            <label className="form-label">User Override</label>
                            <input
                                className="field"
                                value={row.user_override ?? ""}
                                onChange={(event) => handleOverrideChange(row.parameter_id, event.target.value)}
                            />
                        </div>
                    ))}
                </div>
            </section>

            <style jsx>{`
                .workspace {
                    --ink: #111827;
                    --ink-muted: #475569;
                    --panel-bg: rgba(248, 250, 252, 0.92);
                    --panel-border: rgba(15, 23, 42, 0.12);
                    --accent: #f97316;
                    --accent-2: #facc15;
                    --grid: rgba(148, 163, 184, 0.35);
                    --shadow: 0 12px 30px rgba(15, 23, 42, 0.12);

                    min-height: 100vh;
                    display: grid;
                    grid-template-columns: 45% 10% 45%;
                    gap: 0;
                    padding: 24px;
                    background: radial-gradient(circle at top left, #fef3c7 0%, transparent 50%),
                        radial-gradient(circle at 80% 20%, #bae6fd 0%, transparent 55%),
                        linear-gradient(120deg, #f8fafc 0%, #fefce8 50%, #f1f5f9 100%);
                    color: var(--ink);
                    font-family: "Space Grotesk", "Sora", "IBM Plex Sans", sans-serif;
                    box-sizing: border-box;
                }

                .panel {
                    display: flex;
                    flex-direction: column;
                    padding: 16px;
                    border: 1px solid var(--panel-border);
                    background: var(--panel-bg);
                    box-shadow: var(--shadow);
                    backdrop-filter: blur(12px);
                    animation: fadeUp 0.6s ease both;
                }

                .pdf-panel {
                    border-radius: 20px 0 0 20px;
                }

                .connector-panel {
                    border-left: 0;
                    border-right: 0;
                }

                .form-panel {
                    border-radius: 0 20px 20px 0;
                }

                .panel-header h2 {
                    margin: 0;
                    font-size: 1.2rem;
                    letter-spacing: 0.04em;
                    text-transform: uppercase;
                }

                .panel-subtitle {
                    display: block;
                    margin-top: 4px;
                    color: var(--ink-muted);
                    font-size: 0.85rem;
                }

                .pdf-stage {
                    position: relative;
                    flex: 1;
                    overflow: auto;
                    margin-top: 16px;
                    border-radius: 16px;
                    background: #0f172a;
                    padding: 16px;
                }

                .pdf-page {
                    margin-bottom: ${PAGE_GAP}px;
                    display: flex;
                    justify-content: center;
                }

                .pdf-page :global(canvas) {
                    border-radius: 12px;
                    box-shadow: 0 12px 20px rgba(15, 23, 42, 0.35);
                }

                .pdf-loading {
                    color: #f8fafc;
                    padding: 24px;
                    text-align: center;
                }

                .pdf-overlay {
                    position: absolute;
                    inset: 16px 16px auto 16px;
                    pointer-events: none;
                }

                .overlay-grid {
                    position: absolute;
                    inset: 0;
                    background-image: linear-gradient(var(--grid) 1px, transparent 1px),
                        linear-gradient(90deg, var(--grid) 1px, transparent 1px);
                    background-size: 40px 40px;
                    opacity: 0.35;
                }

                .overlay-box {
                    position: absolute;
                    border: 2px solid rgba(250, 204, 21, 0.9);
                    background: rgba(250, 204, 21, 0.12);
                    border-radius: 6px;
                    pointer-events: auto;
                    transition: transform 0.2s ease, box-shadow 0.2s ease;
                }

                .overlay-box.active {
                    border-color: var(--accent);
                    box-shadow: 0 0 0 2px rgba(249, 115, 22, 0.4);
                    transform: scale(1.01);
                }

                .connector-canvas {
                    position: relative;
                    flex: 1;
                    margin-top: 16px;
                }

                .connector-svg {
                    position: absolute;
                    inset: 0;
                }

                .form-grid {
                    margin-top: 16px;
                    overflow: auto;
                    display: grid;
                    gap: 16px;
                }

                .form-row {
                    background: rgba(255, 255, 255, 0.75);
                    border: 1px solid rgba(148, 163, 184, 0.4);
                    border-radius: 14px;
                    padding: 14px;
                    display: grid;
                    gap: 8px;
                    transition: border 0.2s ease, box-shadow 0.2s ease;
                    animation: fadeUp 0.6s ease both;
                }

                .form-row.active {
                    border-color: var(--accent);
                    box-shadow: 0 10px 22px rgba(249, 115, 22, 0.15);
                }

                .form-row-header {
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    font-weight: 600;
                    font-size: 0.95rem;
                }

                .param-key {
                    color: #0f172a;
                }

                .status {
                    background: rgba(148, 163, 184, 0.2);
                    padding: 2px 8px;
                    border-radius: 999px;
                    font-size: 0.75rem;
                }

                .status.high {
                    background: rgba(16, 185, 129, 0.2);
                    color: #065f46;
                }

                .form-label {
                    font-size: 0.75rem;
                    text-transform: uppercase;
                    letter-spacing: 0.08em;
                    color: var(--ink-muted);
                }

                .field {
                    width: 100%;
                    border-radius: 10px;
                    border: 1px solid rgba(148, 163, 184, 0.5);
                    padding: 8px 10px;
                    font-size: 0.9rem;
                    font-family: inherit;
                    background: #ffffff;
                }

                .field.read-only {
                    background: #f1f5f9;
                    color: #475569;
                }

                @keyframes fadeUp {
                    from {
                        opacity: 0;
                        transform: translateY(8px);
                    }
                    to {
                        opacity: 1;
                        transform: translateY(0);
                    }
                }

                @media (max-width: 980px) {
                    .workspace {
                        grid-template-columns: 1fr;
                        grid-auto-rows: minmax(0, auto);
                    }

                    .pdf-panel,
                    .connector-panel,
                    .form-panel {
                        border-radius: 16px;
                    }

                    .connector-panel {
                        min-height: 140px;
                    }
                }
            `}</style>
        </div>
    );
}
