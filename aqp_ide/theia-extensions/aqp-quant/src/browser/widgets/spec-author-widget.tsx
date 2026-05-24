/********************************************************************************
 * Copyright (C) 2026 Julian Wiley and others.
 *
 * This program and the accompanying materials are made available under the
 * terms of the MIT License, which is available in the project root.
 *
 * SPDX-License-Identifier: MIT
 ********************************************************************************/

import * as React from '@theia/core/shared/react';
import { inject, injectable, postConstruct } from '@theia/core/shared/inversify';

import { AqpWidgetBase } from 'theia-ide-aqp-ext/lib/browser/widgets/aqp-widget-base';

import {
    AQP_SPEC_KINDS,
    AqpQuantViewIds,
    AqpSpecKind,
    AqpSpecSummary,
} from '../../common/aqp-quant-protocol';
import { AqpRuntimeClient } from '../services/aqp-runtime-client';

interface SpecAuthorState {
    kind: AqpSpecKind;
    specs: AqpSpecSummary[];
    selectedSpec?: string;
    bodyJson: string;
    bodyError?: string;
    saving: boolean;
    lastSavedHash?: string;
    lastError?: string;
}

const PLACEHOLDER = '{\n  "name": "my-new-spec",\n  "version": 1\n}\n';

@injectable()
export class SpecAuthorWidget extends AqpWidgetBase {

    static readonly ID = AqpQuantViewIds.SPEC_AUTHOR;
    static readonly LABEL = 'AQP: Author Spec';

    @inject(AqpRuntimeClient)
    protected readonly runtime!: AqpRuntimeClient;

    protected state: SpecAuthorState = {
        kind: 'agent',
        specs: [],
        bodyJson: PLACEHOLDER,
        saving: false,
    };

    @postConstruct()
    protected init(): void {
        this.id = SpecAuthorWidget.ID;
        this.title.label = SpecAuthorWidget.LABEL;
        this.title.caption = SpecAuthorWidget.LABEL;
        this.title.closable = true;
        this.title.iconClass = 'codicon codicon-file-code';
        this.setupSubscriptions();
        this.toDispose.push(this.auth.onAuthStateChanged(s => {
            if (s.isAuthenticated) {
                this.refresh();
            }
        }));
        if (this.authState.isAuthenticated) {
            this.refresh();
        }
        this.update();
    }

    protected renderBody(): React.ReactNode {
        const s = this.state;
        const cfg = AQP_SPEC_KINDS.find(k => k.kind === s.kind)!;
        return (
            <div className="aqp-pane">
                <div className="aqp-section">
                    <label htmlFor="aqp-spec-kind">Spec kind</label>
                    <select
                        id="aqp-spec-kind"
                        value={s.kind}
                        onChange={e => this.setKind(e.target.value as AqpSpecKind)}
                    >
                        {AQP_SPEC_KINDS.map(k => (
                            <option key={k.kind} value={k.kind}>{k.label} — {k.runtime}</option>
                        ))}
                    </select>
                    <div className="aqp-muted">
                        Immutable, hash-locked snapshot per {cfg.immutabilityRule}.
                        Every save creates a new `*_spec_versions` row.
                    </div>
                </div>

                <div className="aqp-section">
                    <label htmlFor="aqp-spec-existing">Existing specs ({cfg.runtime})</label>
                    <select
                        id="aqp-spec-existing"
                        value={s.selectedSpec ?? ''}
                        onChange={e => this.loadExisting(e.target.value)}
                    >
                        <option value="">— new spec —</option>
                        {s.specs.map(spec => (
                            <option key={spec.name} value={spec.name}>
                                {spec.name}{spec.version !== undefined ? ` (v${spec.version})` : ''}
                            </option>
                        ))}
                    </select>
                </div>

                <div className="aqp-section">
                    <label htmlFor="aqp-spec-body">Spec body (JSON)</label>
                    <textarea
                        id="aqp-spec-body"
                        rows={14}
                        spellCheck={false}
                        value={s.bodyJson}
                        onChange={e => this.setState({ bodyJson: e.target.value, bodyError: undefined })}
                    />
                    {s.bodyError && <div className="aqp-error">{s.bodyError}</div>}
                </div>

                <div className="aqp-section">
                    <button
                        className="theia-button"
                        disabled={s.saving}
                        onClick={() => this.snapshot()}
                    >
                        {s.saving ? 'Snapshotting...' : `Snapshot (POST ${cfg.snapshotPath})`}
                    </button>
                </div>
                {s.lastSavedHash && (
                    <div className="aqp-section">
                        <div className="aqp-ok">Snapshotted. hash={s.lastSavedHash}</div>
                    </div>
                )}
                {s.lastError && (
                    <div className="aqp-section">
                        <div className="aqp-error">{s.lastError}</div>
                    </div>
                )}
            </div>
        );
    }

    protected setState(patch: Partial<SpecAuthorState>): void {
        this.state = { ...this.state, ...patch };
        this.update();
    }

    private setKind(kind: AqpSpecKind): void {
        this.setState({ kind, selectedSpec: undefined, bodyJson: PLACEHOLDER });
        this.refresh();
    }

    private async refresh(): Promise<void> {
        const specs = await this.runtime.listSpecs(this.state.kind);
        this.setState({ specs });
    }

    private async loadExisting(name: string): Promise<void> {
        if (!name) {
            this.setState({ selectedSpec: undefined, bodyJson: PLACEHOLDER });
            return;
        }
        try {
            const spec = await this.runtime.getSpec(this.state.kind, name);
            this.setState({
                selectedSpec: name,
                bodyJson: JSON.stringify(spec, undefined, 2) + '\n',
                lastSavedHash: undefined,
                lastError: undefined,
            });
        } catch (err) {
            this.setState({ lastError: err instanceof Error ? err.message : String(err) });
        }
    }

    private async snapshot(): Promise<void> {
        let parsed: unknown;
        try {
            parsed = JSON.parse(this.state.bodyJson || '{}');
        } catch (err) {
            this.setState({ bodyError: `Body is not valid JSON: ${(err as Error).message}` });
            return;
        }
        this.setState({ saving: true, lastError: undefined });
        try {
            const result = await this.runtime.snapshotSpec(this.state.kind, parsed);
            this.setState({ saving: false, lastSavedHash: String(result.hash ?? '(no hash returned)') });
            this.refresh();
        } catch (err) {
            this.setState({ saving: false, lastError: err instanceof Error ? err.message : String(err) });
        }
    }
}
