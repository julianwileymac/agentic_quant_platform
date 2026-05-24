# Theia AI

Theia AI is the AI framework shipped with the Theia platform. It provides agents, prompt management, language model abstractions, variables, tool functions, response part rendering, change sets, slash commands, and a default chat UI. Tool builders compose these to ship AI capabilities without forking Theia core.

## Agents and chat agents

An **agent** is an `@injectable()` service that mediates between a UI surface (widget, editor, menu) and a language model. A **chat agent** is a specialization that plugs into Theia AI's default chat UI.

Minimal chat agent:

```typescript
import { AbstractStreamParsingChatAgent } from '@theia/ai-chat';
import { Agent, BasePromptFragment, LanguageModelRequirement } from '@theia/ai-core';
import { ChatAgent } from '@theia/ai-chat';
import { injectable } from '@theia/core/shared/inversify';

export const commandPromptTemplate: BasePromptFragment = {
    id: 'command-chat-agent-system-prompt-template',
    template: 'Always respond with: "I am the command agent"'
};

@injectable()
export class CommandChatAgent extends AbstractStreamParsingChatAgent {
    id = 'Command';
    name = 'Command';
    description = 'Helps users find and execute commands in the IDE';

    languageModelRequirements: LanguageModelRequirement[] = [{
        purpose: 'chat',
        identifier: 'default/universal'
    }];
    protected defaultLanguageModelPurpose = 'chat';

    override prompts = [{ id: commandPromptTemplate.id, defaultVariant: commandPromptTemplate }];
    protected override systemPromptId = commandPromptTemplate.id;
}
```

Register the agent in your `ContainerModule`:

```typescript
bind(CommandChatAgent).toSelf().inSingletonScope();
bind(Agent).toService(CommandChatAgent);
bind(ChatAgent).toService(CommandChatAgent);
```

After this the agent is available in the default chat as `@Command`.

## Prompt fragments

A prompt fragment is an `id` + `template` pair. Theia AI's `PromptService` resolves variables (`{{name}}`), tool functions (`~{toolId}`), and capability blocks within templates. Fragments can be edited at runtime through the prompt editor, which is invaluable for iteration.

Register fragments with the agent via `prompts` (as above) or via `promptService.addBuiltInPromptFragment(...)` for system-wide fragments like slash commands.

## Variables

Two flavours:

### Agent-specific variables

The agent fills them in when invoked. They are not available to other agents or the default chat.

```typescript
const knownCommands = this.commandRegistry.getAllCommands()
    .map(c => `${c.id}: ${c.label}`);

const systemPrompt = await this.promptService.getPrompt(commandPromptTemplate.id, {
    'command-ids': knownCommands.join('\n')
});
```

Use them inside the template with `{{command-ids}}`. Optionally declare them so the UI can show which variables the agent uses:

```typescript
this.agentSpecificVariables = [{
    name: 'command-ids',
    description: 'List of all available commands.',
    usedInPrompt: true
}];
```

### Global variables

Available to all agents and the default chat. Implement `AIVariableContribution` and register a resolver:

```typescript
export const TODAY_VARIABLE: AIVariable = {
    id: 'today-provider',
    name: 'today',
    description: 'The current date',
    args: [
        { name: 'iso', description: 'Return ISO 8601 string' },
        { name: 'unix', description: 'Return Unix seconds' }
    ]
};

@injectable()
export class TodayVariableContribution implements AIVariableContribution, AIVariableResolver {
    registerVariables(service: AIVariableService): void {
        service.registerResolver(TODAY_VARIABLE, this);
    }
    async resolve(req: AIVariableResolutionRequest): Promise<ResolvedAIVariable | undefined> {
        if (req.variable.name !== TODAY_VARIABLE.name) return undefined;
        const date = new Date();
        if (req.arg === 'iso') return { variable: req.variable, value: date.toISOString() };
        if (req.arg === 'unix') return { variable: req.variable, value: Math.floor(date.getTime() / 1000).toString() };
        return { variable: req.variable, value: date.toDateString() };
    }
}
```

```typescript
bind(AIVariableContribution).to(TodayVariableContribution).inSingletonScope();
```

### Context variables

Special global variables that also contribute a `contextValue` to `ChatRequestModel.context`. Use them when the user attaches files, symbols, or other rich elements to a request. Combine with a `FrontendVariableContribution` to register drag-and-drop, argument pickers, and label providers.

Reference the predefined `#contextSummary` or `#contextDetails` variables, or use the tool functions `~{context_ListChatContext}` / `~{context_ResolveChatContext}` for on-demand retrieval.

### Product name variable

`{{productName}}` resolves to the application's `applicationName`. Use it in custom prompts so white-labeled deployments automatically refer to the right product.

## Tool functions

Tool functions let the LLM trigger actions or retrieve data. Implement `ToolProvider`:

```typescript
@injectable()
export class FileContentFunction implements ToolProvider {
    static readonly ID = 'getFileContent';

    @inject(FileService) protected readonly fileService: FileService;

    getTool(): ToolRequest {
        return {
            id: FileContentFunction.ID,
            name: FileContentFunction.ID,
            description: 'Read the content of a workspace file',
            parameters: {
                type: 'object',
                properties: {
                    file: { type: 'string', description: 'Workspace-relative file path' }
                },
                required: ['file']
            },
            handler: async (argString: string) => {
                const { file } = JSON.parse(argString);
                const content = await this.fileService.readFile(new URI(file));
                return content.value.toString();
            }
        };
    }
}
```

Register it:

```typescript
bind(ToolProvider).to(FileContentFunction).inSingletonScope();
```

Reference it from a prompt with `~{getFileContent}` so the LLM knows it can call it.

## Slash commands

Slash commands are prompt fragments with extra metadata. They appear in autocomplete as `/name`:

```typescript
this.promptService.addBuiltInPromptFragment({
    id: 'my-agent-slash-explain',
    template: 'Provide a concise explanation of: $ARGUMENTS',
    isCommand: true,
    commandName: 'explain',
    commandDescription: 'Explain something',
    commandArgumentHint: 'topic',
    commandAgents: ['MyAgent']
});
```

Templates support `$ARGUMENTS`, `$1`, `$2`, ..., and quoted arguments (`/hello "John Doe"` → `$1 = "John Doe"`).

## Modes and capabilities

### Modes

A chat agent can declare operational `modes` (e.g. concise vs detailed). The chat input shows a selector; the selection arrives on `request.request.modeId`:

```typescript
modes = [
    { id: 'concise', name: 'Concise' },
    { id: 'detailed', name: 'Detailed' }
];

override async invoke(request: MutableChatRequestModel): Promise<void> {
    const modeId = request.request.modeId ?? 'concise';
    // adjust behaviour
}
```

### Capabilities

Capabilities are toggleable behaviours surfaced as chips in the chat input. Declare them inside a prompt template:

```
{{capability:my-shell-feature default off}}
{{capability:my-reporting-feature default on}}
```

Each capability is backed by a prompt fragment whose content is included when the chip is enabled. Add YAML frontmatter to the `.prompttemplate` file (`name`, `description`) for friendly labels and tooltips.

## Response part rendering

By default an agent streams text back. To produce richer UI (buttons, structured cards, follow-up prompts) augment the response with structured parts and register a renderer.

1. **Reliable prompt** — instruct the LLM to emit JSON or a tagged block.
2. **Parse in the agent** — turn the structured output into a `ChatResponseContent` implementation (`CommandChatResponseContentImpl`, `QuestionResponseContentImpl`, ...).
3. **Content matchers** for streaming responses:

   ```typescript
   @postConstruct()
   addContentMatchers(): void {
       this.contentMatchers.push({
           start: /^<question>.*$/m,
           end: /^<\/question>$/m,
           contentFactory: (content, request) => {
               const q = JSON.parse(content.replace(/^<question>\n|<\/question>$/g, ''));
               return new QuestionResponseContentImpl(q.question, q.options, request, opt => this.handleAnswer(opt, request));
           }
       });
   }
   ```

4. **Renderer** — implement `ChatResponsePartRenderer`:

   ```typescript
   canHandle(response: ChatResponseContent): number {
       return isCommandChatResponseContent(response) ? 10 : -1;
   }
   render(response: CommandChatResponseContent): ReactNode {
       const enabled = this.commandRegistry.isEnabled(response.command.id);
       return enabled
         ? <button className="theia-button main" onClick={() => this.commandService.executeCommand(response.command.id)}>
             {response.command.label}
           </button>
         : <div>Command "{response.command.id}" is not executable here.</div>;
   }
   ```

   Bind: `bind(ChatResponsePartRenderer).to(CommandPartRenderer).inSingletonScope();`

## Response state management

A response has three flags: `isComplete`, `isWaitingForInput`, `isError`. Drive them from the agent:

```typescript
const progress = request.response.addProgressMessage({ content: 'Analyzing...', show: 'whileIncomplete' });
// later
request.response.updateProgressMessage({ ...progress, show: 'whileIncomplete', status: 'completed' });
request.response.complete();        // success
request.response.error(new Error('...'));
request.response.cancel();
request.response.waitForInput();    // suspend without completing
```

Use `waitForInput()` together with `QuestionResponseContentImpl` to build multi-step interactive flows. Resume via `onResponseComplete`.

## Change sets

Change sets let agents propose reviewable changes. Theia AI ships a default file-based implementation; adopters can implement custom `ChangeSetElement`s for domain-specific data.

```typescript
const changeSet = new ChangeSetImpl('My Test Change Set');
changeSet.addElement(this.fileChangeFactory({
    uri: fileToAdd, type: 'add', state: 'pending',
    targetState: 'Hello World!', changeSet, chatSessionId: request.session.id
}));
request.session.setChangeSet(changeSet);
request.response.complete();
```

Each `ChangeSetElement` is identified by URI, owns its presentation (label, icon, info), and chooses how `open`, `openChange`, `accept`, and `discard` behave. The default chat UI renders the review surface.

## Chat suggestions

Surface contextual nudges on the chat session:

```typescript
model.setSuggestions([
    {
        kind: 'callback',
        content: '[Fix problems](_callback) in the current file.',
        callback: () => this.chatService.sendRequest(session.id, {
            text: '@Coder please look at src/docs/theia_ai.md and fix any problems.'
        })
    }
]);
```

For command-driven suggestions, embed `command:` links in a `MarkdownStringImpl`.

## Custom LLM providers

Implement the `LanguageModel` interface and register it with `LanguageModelRegistry`:

```typescript
this.languageModelRegistry.addLanguageModels([new MyOpenAICompatibleModel()]);
```

Theia ships built-in providers for OpenAI-compatible APIs, Hugging Face, Ollama, and Llamafile. To add a provider, mirror an existing one in `@theia/ai-openai` or `@theia/ai-ollama`. If you want users to configure URLs and model lists, integrate with Theia's preferences system.

For models that support reasoning, set `reasoningSupport` on the model description (`off`/`minimal`/`low`/`medium`/`high`/`auto`) and translate `request.reasoning?.level` in `getSettings()`. The chat input renders a selector automatically when at least one model declares support.

## GitHub Copilot integration

The `@theia/ai-copilot` package ships out of the box. The default OAuth configuration is for the Theia IDE; downstream products must register their own GitHub OAuth App and rebind:

```typescript
rebind(CopilotOAuthConfig).toConstantValue({
    clientId: 'your-client-id'
    // optional: deviceCodeUrl, accessTokenUrl, scopes
});
```

Set `ai-features.copilot.enabled` to `false` to disable the integration entirely. Use `ai-features.copilot.enterpriseUrl` for GitHub Enterprise routing.

## Useful references in the Theia source

- `packages/ai-core` — base abstractions (Agent, PromptService, variables, tool providers).
- `packages/ai-chat` — `AbstractStreamParsingChatAgent`, chat session model, change sets.
- `packages/ai-chat-ui` — default chat UI, response part renderers.
- `packages/ai-ide` — sample agents (Coder, Architect, Command, Universal).
- `packages/ai-openai`, `packages/ai-ollama` — LLM provider templates.
- `examples/api-samples/src/browser/chat/` — minimal samples (mode chat agent, ask-and-continue, change-set).

See `templates/chat-agent.ts.md` for a paste-ready agent skeleton.
