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
import {
    AqpAgentRunResult,
    AqpAgentRunSummary,
    AqpAgentSpecSummary,
} from '../aqp/aqp-types';
import { AqpViewIds } from '../../common/aqp-protocol';
import { AqpWidgetBase } from './aqp-widget-base';

interface AgentRunsState {
    loading: boolean;
    specs: AqpAgentSpecSummary[];
    recent: AqpAgentRunSummary[];
    selectedSpec?: string;
    inputJson: string;
    inputError?: string;
    lastResult?: AqpAgentRunResult;
    runError?: string;
    isRunning: boolean;
    isHalting: boolean;
    loadError?: string;
}

const DEFAULT_INPUT = '{}';

@injectable()
export class AgentRunsWidget extends AqpWidgetBase {

    static readonly ID = AqpViewIds.AGENT_RUNS;
    static readonly LABEL = 'AQP: Agent Runs';

    private state: AgentRunsState = {
        loading: false,
        specs: [],
        recent: [],
        inputJson: DEFAULT_INPUT,
        isRunning: false,
        isHalting: false,
    };

    @postConstruct()
    protected init(): void {
        this.id = AgentRunsWidget.ID;
        this.title.label = AgentRunsWidget.LABEL;
        this.title.caption = AgentRunsWidget.LABEL;
        this.title.closable = true;
        this.title.iconClass = 'codicon codicon-rocket';
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
                label: this.state.isHalting ? 'Halting...' : 'Halt agents',
                onClick: () => this.haltAgents(),
                disabled: this.state.isHalting,
                tooltip: 'POST /agents/halt',
            },
        ];
    }

    protected renderBody(): React.ReactNode {
        const s = this.state;
        return (
            <div className="aqp-pane">
                {s.loadError && <div className="aqp-error">{s.loadError}</div>}
                <div className="aqp-section">
                    <label htmlFor="aqp-agent-spec">Agent spec</label>
                    <select
                        id="aqp-agent-spec"
                        value={s.selectedSpec ?? ''}
                        disabled={s.loading || s.specs.length === 0}
                        onChange={e => this.setSelected(e.target.value)}
                    >
                        <option value="">
                            {s.loading ? 'Loading specs...' : s.specs.length === 0 ? 'No specs available' : 'Pick a spec'}
                        </option>
                        {s.specs.map(spec => (
                            <option key={spec.name} value={spec.name}>
                                {spec.name}{spec.version ? ` (v${spec.version})` : ''}
                            </option>
                        ))}
                    </select>
                </div>
                <div className="aqp-section">
                    <label htmlFor="aqp-agent-input">Input (JSON)</label>
                    <textarea
                        id="aqp-agent-input"
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
                        disabled={!s.selectedSpec || s.isRunning}
                        onClick={() => this.runSelected()}
                    >
                        {s.isRunning ? 'Running...' : 'Run agent (POST /agents/runs/v2/sync)'}
                    </button>
                </div>
                {s.runError && <div className="aqp-error">{s.runError}</div>}
                {s.lastResult && (
                    <div className="aqp-section">
                        <div className="aqp-subtitle">Last result</div>
                        <pre className="aqp-code-block">{JSON.stringify(s.lastResult, undefined, 2)}</pre>
                    </div>
                )}
                <div className="aqp-section">
                    <div className="aqp-subtitle">Recent runs</div>
                    {s.recent.length === 0 && <div className="aqp-muted">No recent runs.</div>}
                    {s.recent.length > 0 && (
                        <table className="aqp-table">
                            <thead>
                                <tr>
                                    <th>Run id</th>
                                    <th>Spec</th>
                                    <th>Status</th>
                                    <th>Started</th>
                                </tr>
                            </thead>
                            <tbody>
                                {s.recent.map(r => (
                                    <tr key={r.run_id}>
                                        <td title={r.run_id}>{shortId(r.run_id)}</td>
                                        <td>{r.spec_name ?? '-'}</td>
                                        <td>{r.status ?? '-'}</td>
                                        <td>{r.created_at ?? '-'}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    )}
                </div>
            </div>
        );
    }

    private setState(patch: Partial<AgentRunsState>): void {
        this.state = { ...this.state, ...patch };
        this.update();
    }

    private setSelected(name: string): void {
        this.setState({ selectedSpec: name || undefined });
    }

    private async refresh(): Promise<void> {
        this.setState({ loading: true, loadError: undefined });
        const [specs, recent] = await Promise.all([
            this.fetchSpecs(),
            this.fetchRecent(),
        ]);
        this.setState({ loading: false, specs, recent });
    }

    private async fetchSpecs(): Promise<AqpAgentSpecSummary[]> {
        try {
            const data = await this.api.get<AqpAgentSpecSummary[] | { specs: AqpAgentSpecSummary[] }>('/agents/specs');
            return Array.isArray(data) ? data : (data?.specs ?? []);
        } catch (err) {
            this.setState({ loadError: describeError(err, 'GET /agents/specs') });
            return [];
        }
    }

    private async fetchRecent(): Promise<AqpAgentRunSummary[]> {
        try {
            const data = await this.api.get<AqpAgentRunSummary[] | { runs: AqpAgentRunSummary[] }>('/agents/runs/v2?limit=20');
            return Array.isArray(data) ? data : (data?.runs ?? []);
        } catch (err) {
            // /agents/runs/v2 may 404 on older AQP builds - keep that quiet
            // and only surface real errors.
            if (err instanceof AqpHttpError && err.status === 404) {
                return [];
            }
            this.setState({ loadError: describeError(err, 'GET /agents/runs/v2') });
            return [];
        }
    }

    private async runSelected(): Promise<void> {
        const spec = this.state.selectedSpec;
        if (!spec) {
            return;
        }
        let parsed: unknown;
        try {
            parsed = JSON.parse(this.state.inputJson || DEFAULT_INPUT);
        } catch (err) {
            this.setState({ inputError: `Input is not valid JSON: ${(err as Error).message}` });
            return;
        }
        this.setState({ isRunning: true, runError: undefined, lastResult: undefined });
        try {
            const result = await this.api.post<AqpAgentRunResult>('/agents/runs/v2/sync', {
                spec_name: spec,
                input: parsed,
            });
            this.setState({ isRunning: false, lastResult: result });
            await this.refresh();
        } catch (err) {
            this.setState({ isRunning: false, runError: describeError(err, 'POST /agents/runs/v2/sync') });
        }
    }

    private async haltAgents(): Promise<void> {
        this.setState({ isHalting: true });
        const outcome = await this.api.safePost('/agents/halt');
        this.setState({ isHalting: false });
        if (outcome.ok) {
            this.messages.info('AQP: agent runs halted.');
        } else {
            this.messages.error(`AQP: halt failed (${outcome.status}): ${outcome.body}`);
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
