/********************************************************************************
 * Copyright (C) 2026 Julian Wiley and others.
 *
 * This program and the accompanying materials are made available under the
 * terms of the MIT License, which is available in the project root.
 *
 * SPDX-License-Identifier: MIT
 ********************************************************************************/

import {
    Command,
    CommandContribution,
    CommandRegistry,
    MenuContribution,
    MenuModelRegistry,
    MessageService,
} from '@theia/core';
import {
    FrontendApplication,
    FrontendApplicationContribution,
    StatusBar,
    StatusBarAlignment,
} from '@theia/core/lib/browser';
import { inject, injectable } from '@theia/core/shared/inversify';

import { Auth0Service } from '../auth/auth0-service';
import { AqpCommandIds } from '../../common/aqp-protocol';
import { AQP_CATEGORY, AqpMenus } from './aqp-view-contributions';

const LOGIN: Command = {
    id: AqpCommandIds.LOGIN,
    category: AQP_CATEGORY,
    label: 'Sign in',
};

const LOGOUT: Command = {
    id: AqpCommandIds.LOGOUT,
    category: AQP_CATEGORY,
    label: 'Sign out',
};

const STATUS_BAR_ID = 'aqp.statusbar.login';

/**
 * Owns the AQP "Sign in" / "Sign out" commands, the View -> AQP menu
 * entries for them, and the status-bar pill that mirrors the current
 * Auth0 session.
 *
 * Implements FrontendApplicationContribution so it can register the
 * status-bar item once the IDE is up and re-render it whenever the auth
 * state changes (login, logout, silent refresh).
 */
@injectable()
export class AqpLoginContribution implements CommandContribution, MenuContribution, FrontendApplicationContribution {

    @inject(Auth0Service)
    protected readonly auth: Auth0Service;

    @inject(StatusBar)
    protected readonly statusBar: StatusBar;

    @inject(MessageService)
    protected readonly messages: MessageService;

    onStart(_app: FrontendApplication): void {
        this.renderStatusBar();
        this.auth.onAuthStateChanged(() => this.renderStatusBar());
    }

    registerCommands(commands: CommandRegistry): void {
        commands.registerCommand(LOGIN, {
            execute: async () => {
                try {
                    await this.auth.login();
                } catch (err) {
                    const message = err instanceof Error ? err.message : String(err);
                    this.messages.error(`AQP login failed: ${message}`);
                }
            },
            isEnabled: () => !this.auth.getState().isAuthenticated,
            isVisible: () => true,
        });
        commands.registerCommand(LOGOUT, {
            execute: async () => {
                try {
                    await this.auth.logout();
                } catch (err) {
                    const message = err instanceof Error ? err.message : String(err);
                    this.messages.error(`AQP logout failed: ${message}`);
                }
            },
            isEnabled: () => this.auth.getState().isAuthenticated,
            isVisible: () => true,
        });
    }

    registerMenus(menus: MenuModelRegistry): void {
        menus.registerMenuAction(AqpMenus.AQP_VIEWS, {
            commandId: LOGIN.id,
            label: LOGIN.label,
            order: '8',
        });
        menus.registerMenuAction(AqpMenus.AQP_VIEWS, {
            commandId: LOGOUT.id,
            label: LOGOUT.label,
            order: '9',
        });
    }

    protected renderStatusBar(): void {
        const state = this.auth.getState();
        if (!state.isReady) {
            this.statusBar.setElement(STATUS_BAR_ID, {
                text: '$(sync~spin) AQP',
                alignment: StatusBarAlignment.RIGHT,
                priority: 1000,
                tooltip: 'AQP: loading auth configuration...',
            });
            return;
        }
        if (state.error === 'auth0 not configured') {
            this.statusBar.setElement(STATUS_BAR_ID, {
                text: '$(warning) AQP not configured',
                alignment: StatusBarAlignment.RIGHT,
                priority: 1000,
                tooltip: 'AQP: AQP_THEIA_AUTH0_* env vars are missing on the Theia backend.',
            });
            return;
        }
        if (!state.isAuthenticated) {
            this.statusBar.setElement(STATUS_BAR_ID, {
                text: '$(sign-in) AQP: Sign in',
                alignment: StatusBarAlignment.RIGHT,
                priority: 1000,
                tooltip: 'Sign in to the Agentic Quant Platform via Auth0',
                command: AqpCommandIds.LOGIN,
            });
            return;
        }
        const label = state.user?.name ?? state.user?.email ?? 'signed in';
        this.statusBar.setElement(STATUS_BAR_ID, {
            text: `$(account) AQP: ${label}`,
            alignment: StatusBarAlignment.RIGHT,
            priority: 1000,
            tooltip: `Signed in to AQP as ${state.user?.email ?? label}. Click to sign out.`,
            command: AqpCommandIds.LOGOUT,
        });
    }
}
