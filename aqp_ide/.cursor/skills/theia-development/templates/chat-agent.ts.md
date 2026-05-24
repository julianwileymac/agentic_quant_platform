# Theia AI chat agent template

A minimal chat agent with a system prompt, an agent-specific variable, an optional tool function, and registration. Adapt the snippets as needed.

## `src/common/my-chat-agent.ts`

```typescript
import { AbstractStreamParsingChatAgent, ChatAgent } from '@theia/ai-chat';
import {
    Agent,
    BasePromptFragment,
    LanguageModelRequirement,
    MutableChatRequestModel,
    PromptService
} from '@theia/ai-core';
import { CommandRegistry } from '@theia/core';
import { inject, injectable } from '@theia/core/shared/inversify';

export const myAgentPromptTemplate: BasePromptFragment = {
    id: 'my-agent-system-prompt',
    template: `You are MyAgent. Help the user accomplish tasks in {{productName}}.

Available commands (id: label) are:
Begin List:
{{command-ids}}
End List

When the user asks to run a command, respond with a JSON object of the shape:
{
    "type": "theia-command",
    "commandId": "<one of the ids above>"
}
`
};

@injectable()
export class MyChatAgent extends AbstractStreamParsingChatAgent {
    readonly id = 'MyAgent';
    readonly name = 'MyAgent';
    readonly description = 'Custom MyAgent that knows about IDE commands.';

    languageModelRequirements: LanguageModelRequirement[] = [{
        purpose: 'chat',
        identifier: 'default/universal'
    }];
    protected defaultLanguageModelPurpose = 'chat';

    override prompts = [{ id: myAgentPromptTemplate.id, defaultVariant: myAgentPromptTemplate }];
    protected override systemPromptId = myAgentPromptTemplate.id;

    @inject(CommandRegistry)
    protected readonly commandRegistry!: CommandRegistry;

    @inject(PromptService)
    protected readonly promptService!: PromptService;

    constructor() {
        super();
        this.agentSpecificVariables = [{
            name: 'command-ids',
            description: 'Newline-separated list of available IDE commands.',
            usedInPrompt: true
        }];
    }

    override async invoke(request: MutableChatRequestModel): Promise<void> {
        const knownCommands = this.commandRegistry
            .getAllCommands()
            .map(c => `${c.id}: ${c.label ?? c.id}`)
            .join('\n');

        const systemPrompt = await this.promptService.getPrompt(myAgentPromptTemplate.id, {
            'command-ids': knownCommands
        });

        // delegate to the base implementation, overriding the system prompt
        return super.invoke(request, systemPrompt);
    }
}
```

## Optional tool function

```typescript
import { ToolProvider, ToolRequest } from '@theia/ai-core';
import { FileService } from '@theia/filesystem/lib/browser/file-service';
import URI from '@theia/core/lib/common/uri';

@injectable()
export class ReadFileTool implements ToolProvider {
    static readonly ID = 'readFile';

    @inject(FileService) protected readonly fileService!: FileService;

    getTool(): ToolRequest {
        return {
            id: ReadFileTool.ID,
            name: ReadFileTool.ID,
            description: 'Read the contents of a workspace-relative file path.',
            parameters: {
                type: 'object',
                properties: {
                    file: { type: 'string', description: 'Workspace-relative path.' }
                },
                required: ['file']
            },
            handler: async (argString: string) => {
                const { file } = JSON.parse(argString) as { file: string };
                const content = await this.fileService.readFile(new URI(file));
                return content.value.toString();
            }
        };
    }
}
```

Reference it in the prompt with `~{readFile}` so the underlying LLM is told the tool exists.

## Optional global variable

```typescript
import {
    AIVariable,
    AIVariableContext,
    AIVariableContribution,
    AIVariableResolutionRequest,
    AIVariableResolver,
    AIVariableService,
    ResolvedAIVariable
} from '@theia/ai-core';

export const PRODUCT_VERSION_VARIABLE: AIVariable = {
    id: 'product-version-provider',
    name: 'productVersion',
    description: 'Resolves to the current product version.'
};

@injectable()
export class ProductVersionVariableContribution
    implements AIVariableContribution, AIVariableResolver
{
    registerVariables(service: AIVariableService): void {
        service.registerResolver(PRODUCT_VERSION_VARIABLE, this);
    }

    async resolve(
        request: AIVariableResolutionRequest,
        _context: AIVariableContext
    ): Promise<ResolvedAIVariable | undefined> {
        if (request.variable.name !== PRODUCT_VERSION_VARIABLE.name) {
            return undefined;
        }
        return { variable: request.variable, value: '1.0.0' };
    }
}
```

## `src/browser/my-agent-frontend-module.ts`

```typescript
import { ContainerModule } from '@theia/core/shared/inversify';
import { Agent, AIVariableContribution, ToolProvider } from '@theia/ai-core';
import { ChatAgent } from '@theia/ai-chat';
import { MyChatAgent } from '../common/my-chat-agent';
import { ReadFileTool } from './read-file-tool';
import { ProductVersionVariableContribution } from './product-version-variable';

export default new ContainerModule(bind => {
    bind(MyChatAgent).toSelf().inSingletonScope();
    bind(Agent).toService(MyChatAgent);
    bind(ChatAgent).toService(MyChatAgent);

    bind(ToolProvider).to(ReadFileTool).inSingletonScope();
    bind(AIVariableContribution).to(ProductVersionVariableContribution).inSingletonScope();
});
```

## Adding a slash command (optional)

```typescript
import { FrontendApplicationContribution } from '@theia/core/lib/browser';
import { PromptService } from '@theia/ai-core';

@injectable()
export class MyAgentSlashCommands implements FrontendApplicationContribution {
    @inject(PromptService) protected readonly promptService!: PromptService;

    onStart(): void {
        this.promptService.addBuiltInPromptFragment({
            id: 'my-agent-slash-explain',
            template: 'Explain the following in simple terms: $ARGUMENTS',
            isCommand: true,
            commandName: 'explain',
            commandDescription: 'Plain-language explanation',
            commandArgumentHint: 'topic',
            commandAgents: ['MyAgent']
        });
    }
}
```

Bind `FrontendApplicationContribution` to `MyAgentSlashCommands` in the same module.

## After binding

Run the application; type `@MyAgent` in the default chat to invoke it, or `/explain something` to use the slash command. Edit the prompt fragment from the prompt editor while iterating — no rebuild required.

## Tips

- Always bind both `Agent` and `ChatAgent` via `toService` so the same instance is reused.
- Use `{{productName}}` in prompts to keep them white-label-friendly.
- For multi-step flows, return structured response parts (`CommandChatResponseContentImpl`, `QuestionResponseContentImpl`) and call `request.response.waitForInput()` when expecting user follow-up.
- Test with at least two different LLM providers — capabilities (tool calling, structured output, reasoning) differ across them.
