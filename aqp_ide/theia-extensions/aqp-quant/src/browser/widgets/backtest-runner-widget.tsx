/********************************************************************************
 * Copyright (C) 2026 Julian Wiley and others.
 *
 * This program and the accompanying materials are made available under the
 * terms of the MIT License, which is available in the project root.
 *
 * SPDX-License-Identifier: MIT
 ********************************************************************************/

import * as React from '@theia/core/shared/react';
import { CommandService } from '@theia/core';
import { inject, injectable, postConstruct } from '@theia/core/shared/inversify';

import { AqpWidgetBase } from 'theia-ide-aqp-ext/lib/browser/widgets/aqp-widget-base';

import {
    AqpQuantCommandIds,
    AqpQuantViewIds,
} from '../../common/aqp-quant-protocol';
import { AqpRuntimeClient } from '../services/aqp-runtime-client';

type LauncherTarget = 'bot' | 'workflow' | 'rl' | 'analysis';

interface BacktestRunnerState {
    target: LauncherTarget;
    options: Array<{ id: string; label: string }>;
    selected?: string;
    inputJson: string;
    launching: boolean;
    lastTaskId?: string;
    lastError?: string;
}

@injectable()
export class BacktestRunnerWidget extends AqpWidgetBase {

    static readonly ID = AqpQuantViewIds.BACKTEST_RUNNER;
    static readonly LABEL = 'AQP: Run Backtest';

    @inject(AqpRuntimeClient)
    protected readonly runtime!: AqpRuntimeClient;

    @inject(CommandService)
    protected readonly commandService!: CommandService;

    protected state: BacktestRunnerState = {
        target: 'bot',
        options: [],
        inputJson: '{}',
        launching: false,
    };

    @postConstruct()
    protected init(): void {
        this.id = BacktestRunnerWidget.ID;
        this.title.label = BacktestRunnerWidget.LABEL;
        this.title.caption = BacktestRunnerWidget.LABEL;
        this.title.closable = true;
        this.title.iconClass = 'codicon codicon-play';
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
        return (
            <div className="aqp-pane">
                <div className="aqp-section">
                    <label htmlFor="aqp-runner-target">Launch via</label>
                    <select
                        id="aqp-runner-target"
                        value={s.target}
                        onChange={e => this.setTarget(e.target.value as LauncherTarget)}
                    >
                        <option value="bot">Bot — POST /bots/{'{ref}'}/backtest</option>
                        <option value="workflow">Workflow — POST /workflows/{'{name}'}/run</option>
                        <option value="rl">RL Experiment — POST /rl/runs</option>
                        <option value="analysis">Analysis — POST /analysis/runs</option>
                    </select>
                </div>

                <div className="aqp-section">
                    <label htmlFor="aqp-runner-selected">
                        {this.targetLabel(s.target)}
                    </label>
                    <select
                        id="aqp-runner-selected"
                        value={s.selected ?? ''}
                        onChange={e => this.setState({ selected: e.target.value || undefined })}
                    >
                        <option value="">{s.options.length === 0 ? 'Loading...' : 'Pick one'}</option>
                        {s.options.map(opt => (
                            <option key={opt.id} value={opt.id}>{opt.label}</option>
                        ))}
                    </select>
                </div>

                <div className="aqp-section">
                    <label htmlFor="aqp-runner-input">Input (JSON)</label>
                    <textarea
                        id="aqp-runner-input"
                        rows={6}
                        spellCheck={false}
                        value={s.inputJson}
                        onChange={e => this.setState({ inputJson: e.target.value })}
                    />
                </div>

                <div className="aqp-section">
                    <button
                        className="theia-button"
                        disabled={!s.selected || s.launching}
                        onClick={() => this.launch()}
                    >
                        {s.launching ? 'Launching...' : 'Launch'}
                    </button>
                </div>

                {s.lastError && <div className="aqp-error">{s.lastError}</div>}
                {s.lastTaskId && (
                    <div className="aqp-section">
                        <div className="aqp-ok">
                            Launched. task_id = <code>{s.lastTaskId}</code>
                        </div>
                        <button
                            className="theia-button secondary"
                            onClick={() => this.attachInspector(s.lastTaskId!)}
                        >
                            Attach Run Inspector
                        </button>
                    </div>
                )}
            </div>
        );
    }

    protected setState(patch: Partial<BacktestRunnerState>): void {
        this.state = { ...this.state, ...patch };
        this.update();
    }

    private setTarget(target: LauncherTarget): void {
        this.setState({ target, selected: undefined, options: [] });
        this.refresh();
    }

    private async refresh(): Promise<void> {
        let options: Array<{ id: string; label: string }> = [];
        try {
            switch (this.state.target) {
                case 'bot': {
                    const bots = await this.runtime.listBots();
                    options = bots.map(b => ({ id: b.ref, label: `${b.ref}${b.kind ? ` (${b.kind})` : ''}` }));
                    break;
                }
                case 'workflow': {
                    const specs = await this.runtime.listSpecs('workflow');
                    options = specs.map(s => ({ id: s.name, label: s.name }));
                    break;
                }
                case 'rl': {
                    const specs = await this.runtime.listSpecs('rl');
                    options = specs.map(s => ({ id: s.name, label: s.name }));
                    break;
                }
                case 'analysis': {
                    const specs = await this.runtime.listSpecs('analysis');
                    options = specs.map(s => ({ id: s.name, label: s.name }));
                    break;
                }
            }
        } catch (err) {
            this.setState({ lastError: err instanceof Error ? err.message : String(err) });
        }
        this.setState({ options });
    }

    private async launch(): Promise<void> {
        const ref = this.state.selected;
        if (!ref) {
            return;
        }
        let body: unknown;
        try {
            body = JSON.parse(this.state.inputJson || '{}');
        } catch (err) {
            this.setState({ lastError: `Input is not valid JSON: ${(err as Error).message}` });
            return;
        }
        this.setState({ launching: true, lastError: undefined, lastTaskId: undefined });
        try {
            let result: { task_id: string };
            switch (this.state.target) {
                case 'bot':
                    result = await this.runtime.backtestBot(ref, body);
                    break;
                case 'workflow':
                    result = await this.runtime.runSpec('workflow', ref, body);
                    break;
                case 'rl':
                    result = await this.runtime.runSpec('rl', ref, body);
                    break;
                case 'analysis':
                    result = await this.runtime.runSpec('analysis', ref, body);
                    break;
            }
            this.setState({ launching: false, lastTaskId: result.task_id });
        } catch (err) {
            this.setState({ launching: false, lastError: err instanceof Error ? err.message : String(err) });
        }
    }

    private attachInspector(taskId: string): void {
        this.commandService.executeCommand(AqpQuantCommandIds.ATTACH_RUN, taskId);
    }

    private targetLabel(target: LauncherTarget): string {
        switch (target) {
            case 'bot': return 'Bot';
            case 'workflow': return 'Workflow spec';
            case 'rl': return 'RL experiment';
            case 'analysis': return 'Analysis spec';
        }
    }
}
