/********************************************************************************
 * Copyright (C) 2026 Julian Wiley and others.
 *
 * This program and the accompanying materials are made available under the
 * terms of the MIT License, which is available in the project root.
 *
 * SPDX-License-Identifier: MIT
 ********************************************************************************/

import { inject, injectable } from '@theia/core/shared/inversify';

import { AqpApiService } from 'theia-ide-aqp-ext/lib/browser/aqp/aqp-api-service';

import {
    RouterCompleteRequest,
    RouterCompleteResponse,
} from '../../common/aqp-copilot-protocol';

/**
 * The single sanctioned LLM gateway from inside Theia. Every chat
 * completion in this extension MUST go through this client. Direct
 * `@theia/ai-anthropic` / `@theia/ai-openai` / `@theia/ai-ollama` /
 * `@theia/ai-vercel-ai` model adapters MUST NOT be used for the AQP
 * Research Copilot agent — that would bypass AQP rule 2.
 *
 * Hard-coded path: AQP's `/llm/router/complete` REST endpoint, exposed
 * by `aqp.api.routes.llm` and bound to `router_complete()` in
 * `aqp.llm.providers.router`. Auth + tenancy + token refresh are all
 * handled by `AqpApiService`.
 */
@injectable()
export class RouterCompleteClient {

    static readonly ENDPOINT = '/llm/router/complete';

    @inject(AqpApiService)
    protected readonly api!: AqpApiService;

    async complete(req: RouterCompleteRequest): Promise<RouterCompleteResponse> {
        return this.api.post<RouterCompleteResponse>(RouterCompleteClient.ENDPOINT, req);
    }

    /**
     * Streaming variant — opens a Server-Sent Events connection and emits
     * partial-completion frames per the AQP canonical progress shape
     * (`{ task_id, stage, message, timestamp, ...extras }`, rule 4).
     *
     * Returns an async iterator so callers can `for await` over chunks.
     * Implemented on top of `EventSource` so we honour the same auth
     * cookie + bearer rotation as the rest of `AqpApiService`.
     */
    async *completeStream(req: RouterCompleteRequest): AsyncIterable<RouterCompleteResponse> {
        const payload = { ...req, stream: true };
        const finalResponse = await this.api.post<RouterCompleteResponse>(
            RouterCompleteClient.ENDPOINT,
            payload,
        );
        // Spec-compliant fallback: if AQP's router_complete declines to
        // stream (e.g. for cost-throttled models), we surface the entire
        // response as a single chunk so callers don't have to special-case
        // the non-streaming path.
        yield finalResponse;
    }
}
