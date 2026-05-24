/********************************************************************************
 * Copyright (C) 2026 Julian Wiley and others.
 *
 * This program and the accompanying materials are made available under the
 * terms of the MIT License, which is available in the project root.
 *
 * SPDX-License-Identifier: MIT
 ********************************************************************************/

import * as React from '@theia/core/shared/react';
import { Disposable } from '@theia/core';
import { inject, injectable, postConstruct } from '@theia/core/shared/inversify';

import { AqpWidgetBase } from 'theia-ide-aqp-ext/lib/browser/widgets/aqp-widget-base';

import { AqpProgressFrame, AqpQuantViewIds } from '../../common/aqp-quant-protocol';
import { AqpWsClient, AqpTaskSubscription } from '../services/aqp-ws-client';

interface RunInspectorState {
    taskIdInput: string;
    attachedTaskId?: string;
    frames: AqpProgressFrame[];
    attaching: boolean;
    attachError?: string;
}

const MAX_FRAMES = 200;

@injectable()
export class RunInspectorWidget extends AqpWidgetBase {

    static readonly ID = AqpQuantViewIds.RUN_INSPECTOR;
    static readonly LABEL = 'AQP: Inspect Run';

    @inject(AqpWsClient)
    protected readonly ws!: AqpWsClient;

    protected state: RunInspectorState = {
        taskIdInput: '',
        frames: [],
        attaching: false,
    };

    protected current?: AqpTaskSubscription;
    protected currentFrameListener?: Disposable;

    @postConstruct()
    protected init(): void {
        this.id = RunInspectorWidget.ID;
        this.title.label = RunInspectorWidget.LABEL;
        this.title.caption = RunInspectorWidget.LABEL;
        this.title.closable = true;
        this.title.iconClass = 'codicon codicon-pulse';
        this.setupSubscriptions();
        this.update();
    }

    /**
     * Public entry point used by other extensions / commands (e.g. the
     * BacktestRunnerWidget after it launches a run) to attach the
     * inspector to a freshly-created `task_id` without the user typing it.
     */
    attachTaskId(taskId: string): void {
        this.setState({ taskIdInput: taskId });
        this.attach();
    }

    protected renderBody(): React.ReactNode {
        const s = this.state;
        return (
            <div className="aqp-pane">
                <div className="aqp-section">
                    <label htmlFor="aqp-inspector-taskid">Task id</label>
                    <input
                        id="aqp-inspector-taskid"
                        type="text"
                        spellCheck={false}
                        value={s.taskIdInput}
                        onChange={e => this.setState({ taskIdInput: e.target.value })}
                        placeholder="paste a task id from a recent run"
                    />
                </div>
                <div className="aqp-section">
                    <button
                        className="theia-button"
                        onClick={() => this.attach()}
                        disabled={!s.taskIdInput || s.attaching}
                    >
                        {s.attaching ? 'Attaching...' : 'Attach (WebSocket /ws/tasks/{task_id})'}
                    </button>
                    <button
                        className="theia-button secondary"
                        onClick={() => this.detach()}
                        disabled={!this.current}
                        style={{ marginLeft: '6px' }}
                    >
                        Detach
                    </button>
                </div>
                {s.attachError && <div className="aqp-error">{s.attachError}</div>}
                {s.attachedTaskId && (
                    <div className="aqp-section">
                        <div className="aqp-subtitle">Live frames — task {s.attachedTaskId}</div>
                        {s.frames.length === 0
                            ? <div className="aqp-muted">Waiting for the first frame...</div>
                            : (
                                <table className="aqp-table">
                                    <thead>
                                        <tr>
                                            <th>Stage</th>
                                            <th>Message</th>
                                            <th>Timestamp</th>
                                            <th>Extras</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {s.frames.map((f, i) => (
                                            <tr key={`${f.timestamp}-${i}`}>
                                                <td>{f.stage}</td>
                                                <td>{f.message}</td>
                                                <td>{this.formatTs(f.timestamp)}</td>
                                                <td>{this.formatExtras(f)}</td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            )}
                    </div>
                )}
            </div>
        );
    }

    protected setState(patch: Partial<RunInspectorState>): void {
        this.state = { ...this.state, ...patch };
        this.update();
    }

    private async attach(): Promise<void> {
        const taskId = this.state.taskIdInput.trim();
        if (!taskId) {
            return;
        }
        this.detach();
        this.setState({ attaching: true, attachError: undefined, frames: [], attachedTaskId: undefined });
        try {
            const sub = await this.ws.subscribe(taskId);
            this.current = sub;
            this.currentFrameListener = sub.onFrame(frame => this.onFrame(frame));
            this.setState({ attaching: false, attachedTaskId: taskId });
        } catch (err) {
            const message = err instanceof Error ? err.message : String(err);
            this.setState({ attaching: false, attachError: `Subscribe failed: ${message}` });
        }
    }

    private detach(): void {
        this.currentFrameListener?.dispose();
        this.current?.dispose();
        this.current = undefined;
        this.currentFrameListener = undefined;
    }

    private onFrame(frame: AqpProgressFrame): void {
        const frames = [...this.state.frames, frame];
        if (frames.length > MAX_FRAMES) {
            frames.splice(0, frames.length - MAX_FRAMES);
        }
        this.setState({ frames });
    }

    private formatTs(ts: number | string): string {
        if (typeof ts === 'number') {
            return new Date(ts * 1000).toISOString();
        }
        return String(ts);
    }

    private formatExtras(frame: AqpProgressFrame): string {
        const extras: Record<string, unknown> = {};
        for (const [k, v] of Object.entries(frame)) {
            if (k === 'task_id' || k === 'stage' || k === 'message' || k === 'timestamp') {
                continue;
            }
            extras[k] = v;
        }
        const keys = Object.keys(extras);
        if (keys.length === 0) {
            return '';
        }
        return keys.length <= 2 ? JSON.stringify(extras) : `${keys.length} keys`;
    }

    override dispose(): void {
        this.detach();
        super.dispose();
    }
}
