/********************************************************************************
 * Copyright (C) 2026 Julian Wiley and others.
 *
 * This program and the accompanying materials are made available under the
 * terms of the MIT License, which is available in the project root.
 *
 * SPDX-License-Identifier: MIT
 ********************************************************************************/

import * as React from '@theia/core/shared/react';
import { injectable, postConstruct } from '@theia/core/shared/inversify';

import { AqpHttpError } from '../aqp/aqp-api-service';
import { AqpWorkflowRunSummary, AqpWorkflowSummary } from '../aqp/aqp-types';
import { AqpViewIds } from '../../common/aqp-protocol';
import { AqpWidgetBase } from './aqp-widget-base';

interface WorkflowsState {
    loading: boolean;
    workflows: AqpWorkflowSummary[];
    running: AqpWorkflowRunSummary[];
    selected?: string;
    inputJson: string;
    inputError?: string;
    isRunning: boolean;
    isHalting: boolean;
    lastRunId?: string;
    runError?: string;
    loadError?: string;
}

const DEFAULT_INPUT = '{}';

@injectable()
export class WorkflowsWidget extends AqpWidgetBase {

    static readonly ID = AqpViewIds.WORKFLOWS;
    static readonly LABEL = 'AQP: Workflows';

    private state: WorkflowsState = {
        loading: false,
        workflows: [],
        running: [],
        inputJson: DEFAULT_INPUT,
        isRunning: false,
        isHalting: false,
    };

    @postConstruct()
    protected init(): void {
        this.id = WorkflowsWidget.ID;
        this.title.label = WorkflowsWidget.LABEL;
        this.title.caption = WorkflowsWidget.LABEL;
        this.title.closable = true;
        this.title.iconClass = 'codicon codicon-circuit-board';
        this.setupSubscriptions();
        this.toDispose.push(this.auth.onAuthStateChanged(state => {
            if (state.isAuthenticated) {
                this.refresh();
            }
        }));
        if (this.authState.isAuthenticated) {
            this.refresh();
        }
        this.update();
    }

    protected getHeaderActions(): Array<{ label: string; onClick: () => void; disabled?: boolean; tooltip?: string }> {
        return [
            { label: 'Refresh', onClick: () => this.refresh(), disabled: this.state.loading },
            {
                label: this.state.isHalting ? 'Halting...' : 'Halt workflows',
                onClick: () => this.haltWorkflows(),
                disabled: this.state.isHalting,
                tooltip: 'POST /workflows/halt',
            },
        ];
    }

    protected renderBody(): React.ReactNode {
        const s = this.state;
        return (
            <div className="aqp-pane">
                {s.loadError && <div className="aqp-error">{s.loadError}</div>}
                <div className="aqp-section">
                    <label htmlFor="aqp-workflow-name">Workflow</label>
                    <select
                        id="aqp-workflow-name"
                        value={s.selected ?? ''}
                        disabled={s.loading || s.workflows.length === 0}
                        onChange={e => this.setState({ selected: e.target.value || undefined })}
                    >
                        <option value="">
                            {s.loading ? 'Loading workflows...' : s.workflows.length === 0 ? 'No workflows available' : 'Pick a workflow'}
                        </option>
                        {s.workflows.map(w => (
                            <option key={w.name} value={w.name}>
                                {w.name}{w.adapter_kind ? ` (${w.adapter_kind})` : ''}
                            </option>
                        ))}
                    </select>
                </div>
                <div className="aqp-section">
                    <label htmlFor="aqp-workflow-input">Input (JSON)</label>
                    <textarea
                        id="aqp-workflow-input"
                        rows={6}
                        spellCheck={false}
                        value={s.inputJson}
                        onChange={e => this.setState({ inputJson: e.target.value, inputError: undefined })}
                    />
                    {s.inputError && <div className="aqp-error">{s.inputError}</div>}
                </div>
                <div className="aqp-section">
                    <button
                        className="theia-button"
                        disabled={!s.selected || s.isRunning}
                        onClick={() => this.runSelected()}
                    >
                        {s.isRunning ? 'Submitting...' : 'Run workflow (POST /workflows/{name}/run)'}
                    </button>
                    {s.lastRunId && (
                        <div className="aqp-muted">Last run id: <code>{s.lastRunId}</code></div>
                    )}
                </div>
                {s.runError && <div className="aqp-error">{s.runError}</div>}
                <div className="aqp-section">
                    <div className="aqp-subtitle">Running workflows</div>
                    {s.running.length === 0 && <div className="aqp-muted">No workflows currently running.</div>}
                    {s.running.length > 0 && (
                        <table className="aqp-table">
                            <thead>
                                <tr>
                                    <th>Run id</th>
                                    <th>Workflow</th>
                                    <th>Status</th>
                                    <th>Started</th>
                                </tr>
                            </thead>
                            <tbody>
                                {s.running.map(r => (
                                    <tr key={r.run_id}>
                                        <td title={r.run_id}>{shortId(r.run_id)}</td>
                                        <td>{r.workflow_name ?? '-'}</td>
                                        <td>{r.status ?? '-'}</td>
                                        <td>{r.started_at ?? '-'}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    )}
                </div>
            </div>
        );
    }

    private setState(patch: Partial<WorkflowsState>): void {
        this.state = { ...this.state, ...patch };
        this.update();
    }

    private async refresh(): Promise<void> {
        this.setState({ loading: true, loadError: undefined });
        const [workflows, running] = await Promise.all([
            this.fetchWorkflows(),
            this.fetchRunning(),
        ]);
        this.setState({ loading: false, workflows, running });
    }

    private async fetchWorkflows(): Promise<AqpWorkflowSummary[]> {
        try {
            const data = await this.api.get<AqpWorkflowSummary[] | { workflows: AqpWorkflowSummary[] }>('/workflows');
            return Array.isArray(data) ? data : (data?.workflows ?? []);
        } catch (err) {
            this.setState({ loadError: describeError(err, 'GET /workflows') });
            return [];
        }
    }

    private async fetchRunning(): Promise<AqpWorkflowRunSummary[]> {
        try {
            const data = await this.api.get<AqpWorkflowRunSummary[] | { runs: AqpWorkflowRunSummary[] }>('/workflows/runs?status=running');
            return Array.isArray(data) ? data : (data?.runs ?? []);
        } catch (err) {
            if (err instanceof AqpHttpError && err.status === 404) {
                return [];
            }
            this.setState({ loadError: describeError(err, 'GET /workflows/runs') });
            return [];
        }
    }

    private async runSelected(): Promise<void> {
        const name = this.state.selected;
        if (!name) {
            return;
        }
        let parsed: unknown;
        try {
            parsed = JSON.parse(this.state.inputJson || DEFAULT_INPUT);
        } catch (err) {
            this.setState({ inputError: `Input is not valid JSON: ${(err as Error).message}` });
            return;
        }
        this.setState({ isRunning: true, runError: undefined, lastRunId: undefined });
        try {
            const encoded = encodeURIComponent(name);
            const result = await this.api.post<{ run_id?: string }>(`/workflows/${encoded}/run`, parsed);
            this.setState({ isRunning: false, lastRunId: result?.run_id });
            await this.refresh();
        } catch (err) {
            this.setState({ isRunning: false, runError: describeError(err, `POST /workflows/${name}/run`) });
        }
    }

    private async haltWorkflows(): Promise<void> {
        this.setState({ isHalting: true });
        const outcome = await this.api.safePost('/workflows/halt');
        this.setState({ isHalting: false });
        if (outcome.ok) {
            this.messages.info('AQP: workflows halted.');
        } else {
            this.messages.error(`AQP: workflow halt failed (${outcome.status}): ${outcome.body}`);
        }
        await this.refresh();
    }
}

function shortId(id: string | undefined): string {
    if (!id) {
        return '-';
    }
    return id.length > 12 ? `${id.slice(0, 8)}...` : id;
}

function describeError(err: unknown, context: string): string {
    if (err instanceof AqpHttpError) {
        return `${context}: HTTP ${err.status} ${err.statusText}`;
    }
    return `${context}: ${err instanceof Error ? err.message : String(err)}`;
}
