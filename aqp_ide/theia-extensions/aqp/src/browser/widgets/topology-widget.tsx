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
import { AqpTopologySnapshot, AqpTopologyTarget } from '../aqp/aqp-types';
import { AqpViewIds } from '../../common/aqp-protocol';
import { AqpWidgetBase } from './aqp-widget-base';

interface TopologyState {
    loading: boolean;
    snapshot?: AqpTopologySnapshot;
    loadError?: string;
}

@injectable()
export class TopologyWidget extends AqpWidgetBase {

    static readonly ID = AqpViewIds.TOPOLOGY;
    static readonly LABEL = 'AQP: Topology';

    private state: TopologyState = { loading: false };

    @postConstruct()
    protected init(): void {
        this.id = TopologyWidget.ID;
        this.title.label = TopologyWidget.LABEL;
        this.title.caption = TopologyWidget.LABEL;
        this.title.closable = true;
        this.title.iconClass = 'codicon codicon-server-environment';
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
        ];
    }

    protected renderBody(): React.ReactNode {
        const s = this.state;
        return (
            <div className="aqp-pane">
                {s.loadError && <div className="aqp-error">{s.loadError}</div>}
                {s.loading && <div className="aqp-muted">Loading topology...</div>}
                {s.snapshot && (
                    <>
                        <div className="aqp-muted">
                            Snapshot at {s.snapshot.generated_at ?? 'unknown time'}
                        </div>
                        {s.snapshot.targets.length === 0 && (
                            <div className="aqp-muted">No deployment targets registered.</div>
                        )}
                        {s.snapshot.targets.length > 0 && (
                            <table className="aqp-table">
                                <thead>
                                    <tr>
                                        <th>Name</th>
                                        <th>Kind</th>
                                        <th>Cluster</th>
                                        <th>Namespace</th>
                                        <th>Region</th>
                                        <th>Ready</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {s.snapshot.targets.map(t => (
                                        <tr key={String(t.id)}>
                                            <td>{t.name ?? String(t.id)}</td>
                                            <td>{t.kind ?? '-'}</td>
                                            <td>{t.cluster ?? '-'}</td>
                                            <td>{t.namespace ?? '-'}</td>
                                            <td>{t.region ?? '-'}</td>
                                            <td>{renderReady(t)}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        )}
                    </>
                )}
            </div>
        );
    }

    private setState(patch: Partial<TopologyState>): void {
        this.state = { ...this.state, ...patch };
        this.update();
    }

    private async refresh(): Promise<void> {
        this.setState({ loading: true, loadError: undefined });
        try {
            const snapshot = await this.api.get<AqpTopologySnapshot | { targets: AqpTopologyTarget[] }>(
                '/control-plane/topology'
            );
            const normalised: AqpTopologySnapshot = Array.isArray((snapshot as AqpTopologySnapshot)?.targets)
                ? (snapshot as AqpTopologySnapshot)
                : { targets: (snapshot as { targets?: AqpTopologyTarget[] })?.targets ?? [] };
            this.setState({ loading: false, snapshot: normalised });
        } catch (err) {
            this.setState({ loading: false, loadError: describeError(err, 'GET /control-plane/topology') });
        }
    }
}

function renderReady(target: AqpTopologyTarget): React.ReactNode {
    if (target.ready === undefined) {
        return '-';
    }
    return target.ready ? <span className="aqp-ok">ready</span> : <span className="aqp-warn">not ready</span>;
}

function describeError(err: unknown, context: string): string {
    if (err instanceof AqpHttpError) {
        return `${context}: HTTP ${err.status} ${err.statusText}`;
    }
    return `${context}: ${err instanceof Error ? err.message : String(err)}`;
}
