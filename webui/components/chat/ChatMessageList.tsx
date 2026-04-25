"use client";

import { Avatar } from "antd";
import { useEffect, useRef } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface ChatMessage {
  role: "user" | "assistant" | "system";
  content: string;
}

interface ChatMessageListProps {
  messages: ChatMessage[];
}

export function ChatMessageList({ messages }: ChatMessageListProps) {
  const ref = useRef<HTMLDivElement>(null);

  const lastContent = messages.at(-1)?.content;
  useEffect(() => {
    ref.current?.scrollTo({ top: ref.current.scrollHeight, behavior: "smooth" });
  }, [messages.length, lastContent]);

  return (
    <div ref={ref} style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      {messages.map((m, i) => (
        <div
          key={i}
          style={{
            display: "flex",
            alignItems: "flex-start",
            gap: 8,
            flexDirection: m.role === "user" ? "row-reverse" : "row",
          }}
        >
          <Avatar
            size={26}
            style={{
              background: m.role === "user" ? "#3b82f6" : "#10b981",
              fontSize: 12,
            }}
          >
            {m.role === "user" ? "U" : "A"}
          </Avatar>
          <div
            style={{
              background:
                m.role === "user"
                  ? "rgba(59,130,246,0.16)"
                  : "var(--ant-color-bg-elevated, #1f2937)",
              border: "1px solid var(--ant-color-border, #1f2937)",
              borderRadius: 8,
              padding: "6px 10px",
              maxWidth: "85%",
              fontSize: 13,
              lineHeight: 1.5,
              wordBreak: "break-word",
            }}
          >
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.content}</ReactMarkdown>
          </div>
        </div>
      ))}
    </div>
  );
}
