import { AgentTeamConsole } from "@/components/agents/AgentTeamConsole";

export const metadata = { title: "Trader Signal | AQP" };

export default function Page() {
  return (
    <AgentTeamConsole
      specName="trader.signal_emitter"
      title="Trader (Signal Emitter)"
      description="LLM-based trader that emits structured signals from windowed indicators + fundamentals RAG. Respects the kill switch."
      defaultPrompt="Emit a trading signal for AAPL.NASDAQ based on the latest windowed indicators and fundamentals."
    />
  );
}
