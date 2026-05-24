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
import { AqpBotSummary } from '../aqp/aqp-types';
import { AqpViewIds } from '../../common/aqp-protocol';
import { AqpWidgetBase } from './aqp-widget-base';

interface BotsState {
    loading: boolean;
    bots: AqpBotSummary[];
    haltingAll: boolean;
    perBotHalting: Record<string, boolean>;
    loadError?: string;
}

@injectable()
export class BotsWidget extends AqpWidgetBase {

    static readonly ID = AqpViewIds.BOTS;
    static readonly LABEL = 'AQP: Bots';

    private state: BotsState = {
        loading: false,
        bots: [],
        haltingAll: false,
        perBotHalting: {},
    };

    @postConstruct()
    protected init(): void {
        this.id = BotsWidget.ID;
        this.title.label = BotsWidget.LABEL;
        this.title.caption = BotsWidget.LABEL;
        this.title.closable = true;
        this.title.iconClass = 'codicon codicon-robot';
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
                label: this.state.haltingAll ? 'Halting all...' : 'Halt all bots',
                onClick: () => this.haltAll(),
                disabled: this.state.haltingAll,
                tooltip: 'POST /bots/halt-all',
            },
        ];
    }

    protected renderBody(): React.ReactNode {
        const s = this.state;
        return (
            <div className="aqp-pane">
                {s.loadError && <div className="aqp-error">{s.loadError}</div>}
                {s.bots.length === 0 && !s.loading && (
                    <div className="aqp-muted">No bots registered.</div>
                )}
                {s.loading && <div className="aqp-muted">Loading bots...</div>}
                {s.bots.length > 0 && (
                    <table className="aqp-table">
                        <thead>
                            <tr>
                                <th>Name</th>
                                <th>Kind</th>
                                <th>Status</th>
                                <th>Spec hash</th>
                                <th></th>
                            </tr>
                        </thead>
                        <tbody>
                            {s.bots.map(b => {
                                const ref = String(b.id);
                                const halting = !!s.perBotHalting[ref];
                                return (
                                    <tr key={ref}>
                                        <td>{b.name}</td>
                                        <td>{b.kind ?? '-'}</td>
                                        <td>{b.status ?? '-'}</td>
                                        <td title={b.spec_hash}>{b.spec_hash ? `${b.spec_hash.slice(0, 8)}...` : '-'}</td>
                                        <td>
                                            <button
                                                className="theia-button secondary"
                                                disabled={halting}
                                                onClick={() => this.haltOne(ref, b.name)}
                                                title={`POST /bots/${ref}/halt`}
                                            >
                                                {halting ? 'Halting...' : 'Halt'}
                                            </button>
                                        </td>
                                    </tr>
                                );
                            })}
                        </tbody>
                    </table>
                )}
            </div>
        );
    }

    private setState(patch: Partial<BotsState>): void {
        this.state = { ...this.state, ...patch };
        this.update();
    }

    private async refresh(): Promise<void> {
        this.setState({ loading: true, loadError: undefined });
        try {
            const data = await this.api.get<AqpBotSummary[] | { bots: AqpBotSummary[] }>('/bots');
            const bots = Array.isArray(data) ? data : (data?.bots ?? []);
            this.setState({ loading: false, bots });
        } catch (err) {
            this.setState({ loading: false, loadError: describeError(err, 'GET /bots') });
        }
    }

    private async haltAll(): Promise<void> {
        this.setState({ haltingAll: true });
        const outcome = await this.api.safePost('/bots/halt-all');
        this.setState({ haltingAll: false });
        if (outcome.ok) {
            this.messages.info('AQP: halted all bots.');
        } else {
            this.messages.error(`AQP: halt-all failed (${outcome.status}): ${outcome.body}`);
        }
        await this.refresh();
    }

    private async haltOne(ref: string, name: string): Promise<void> {
        this.setState({ perBotHalting: { ...this.state.perBotHalting, [ref]: true } });
        const encoded = encodeURIComponent(ref);
        const outcome = await this.api.safePost(`/bots/${encoded}/halt`);
        const nextMap = { ...this.state.perBotHalting };
        delete nextMap[ref];
        this.setState({ perBotHalting: nextMap });
        if (outcome.ok) {
            this.messages.info(`AQP: halted bot ${name}.`);
        } else {
            this.messages.error(`AQP: halt ${name} failed (${outcome.status}): ${outcome.body}`);
        }
        await this.refresh();
    }
}

function describeError(err: unknown, context: string): string {
    if (err instanceof AqpHttpError) {
        return `${context}: HTTP ${err.status} ${err.statusText}`;
    }
    return `${context}: ${err instanceof Error ? err.message : String(err)}`;
}
