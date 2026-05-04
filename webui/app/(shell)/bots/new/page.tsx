"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { BotBuilder } from "@/components/bots/BotBuilder";
import { PageContainer } from "@/components/shell/PageContainer";

export default function NewBotPage() {
  return (
    <Suspense fallback={null}>
      <NewBotContents />
    </Suspense>
  );
}

function NewBotContents() {
  const router = useRouter();
  const params = useSearchParams();
  const kind = (params.get("kind") === "research" ? "research" : "trading") as "research" | "trading";

  return (
    <PageContainer
      title="New Bot"
      subtitle={`Compose a ${kind} bot graphically.`}
      full
    >
      <BotBuilder
        defaultKind={kind}
        onSaved={(saved) => router.push(`/bots/${saved.id}`)}
      />
    </PageContainer>
  );
}
