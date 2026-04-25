"use client";

import { CloseOutlined, PlayCircleOutlined } from "@ant-design/icons";
import { App, Alert, Button, Card, Col, Form, Input, Row, Select, Space, Tag, Typography } from "antd";
import { useEffect, useMemo, useState } from "react";

import { Sparkline } from "@/components/charts";
import { PageContainer } from "@/components/shell/PageContainer";
import { apiFetch } from "@/lib/api/client";
import { useLiveStream, type LiveBar, type LiveQuote, type LiveSignal, type LiveTick } from "@/lib/ws";

const { Text } = Typography;

interface SubscribeResponse {
  channel_id: string;
  venue: string;
  symbols: string[];
  stream_url: string;
}

const POINTS_PER_SYMBOL = 60;

function priceOf(ev: LiveBar | LiveQuote | LiveTick | LiveSignal): number | null {
  if (ev.kind === "bar") return ev.close;
  if (ev.kind === "quote") return (ev.bid_close + ev.ask_close) / 2;
  if (ev.kind === "tick") return ev.last;
  return null;
}

export function LiveMarket() {
  const { message } = App.useApp();
  const [form] = Form.useForm();
  const [channelId, setChannelId] = useState<string | null>(null);
  const [series, setSeries] = useState<Record<string, Array<{ x: number; y: number }>>>({});
  const live = useLiveStream({ channelId, bufferSize: 4096 });

  useEffect(() => {
    if (live.buffer.length === 0) return;
    const last = live.buffer.at(-1);
    if (!last) return;
    const sym = "vt_symbol" in last ? last.vt_symbol : null;
    const price = priceOf(last);
    if (!sym || price === null || Number.isNaN(price)) return;
    setSeries((prev) => {
      const arr = (prev[sym] ?? []).concat({ x: Date.now(), y: price });
      if (arr.length > POINTS_PER_SYMBOL) arr.splice(0, arr.length - POINTS_PER_SYMBOL);
      return { ...prev, [sym]: arr };
    });
  }, [live.buffer.length]); // eslint-disable-line react-hooks/exhaustive-deps

  const symbols = useMemo(() => Object.keys(live.latest), [live.latest]);

  async function subscribe() {
    const v = await form.validateFields();
    const symbols = String(v.symbols)
      .split(/[,\s]+/)
      .map((s) => s.trim())
      .filter(Boolean);
    try {
      const res = await apiFetch<SubscribeResponse>("/live/subscribe", {
        method: "POST",
        body: JSON.stringify({
          venue: v.venue,
          symbols,
          poll_cadence_seconds: Number(v.poll_cadence_seconds ?? 5),
        }),
      });
      setChannelId(res.channel_id);
      setSeries({});
      message.success(`Subscribed (channel ${res.channel_id})`);
    } catch (err) {
      message.error((err as Error).message);
    }
  }

  async function unsubscribe() {
    if (!channelId) return;
    try {
      await apiFetch(`/live/subscribe/${channelId}`, { method: "DELETE" });
      setChannelId(null);
      setSeries({});
      message.success("Unsubscribed");
    } catch (err) {
      message.error((err as Error).message);
    }
  }

  return (
    <PageContainer
      title="Live Market"
      subtitle="Subscribe to a venue and watch quotes / bars stream into the UI."
      extra={
        channelId ? (
          <Button danger icon={<CloseOutlined />} onClick={unsubscribe}>
            Stop ({channelId.slice(0, 6)})
          </Button>
        ) : null
      }
    >
      <Row gutter={16}>
        <Col xs={24} lg={8}>
          <Card title="Subscribe" size="small">
            <Form
              form={form}
              layout="vertical"
              initialValues={{
                venue: "simulated",
                symbols: "AAPL, MSFT, SPY",
                poll_cadence_seconds: 5,
              }}
            >
              <Form.Item label="Venue" name="venue">
                <Select
                  options={[
                    { value: "simulated", label: "Simulated (demo)" },
                    { value: "alpaca", label: "Alpaca" },
                    { value: "ibkr", label: "Interactive Brokers" },
                    { value: "kafka", label: "Kafka (features.normalized)" },
                  ]}
                />
              </Form.Item>
              <Form.Item
                label="Symbols"
                name="symbols"
                rules={[{ required: true, message: "Required" }]}
              >
                <Input.TextArea autoSize placeholder="AAPL, MSFT, SPY" />
              </Form.Item>
              <Form.Item label="Cadence (sec)" name="poll_cadence_seconds">
                <Input type="number" min={1} step={1} />
              </Form.Item>
              <Button
                type="primary"
                icon={<PlayCircleOutlined />}
                disabled={Boolean(channelId)}
                onClick={subscribe}
              >
                Start stream
              </Button>
            </Form>
            <div style={{ marginTop: 12 }}>
              <Tag color={live.status === "open" ? "green" : "default"}>{live.status}</Tag>
              {channelId ? <Tag>{channelId}</Tag> : null}
            </div>
            {live.error ? <Alert type="error" message={live.error} style={{ marginTop: 12 }} /> : null}
          </Card>
        </Col>
        <Col xs={24} lg={16}>
          <Card title="Symbols" size="small">
            {symbols.length === 0 ? (
              <Text type="secondary">Awaiting first message…</Text>
            ) : (
              <Space direction="vertical" size={6} style={{ width: "100%" }}>
                {symbols.map((sym) => {
                  const ev = live.latest[sym];
                  const price = ev ? priceOf(ev) : null;
                  return (
                    <Row key={sym} gutter={12} align="middle">
                      <Col span={5}>
                        <Text strong>{sym}</Text>
                      </Col>
                      <Col span={5}>
                        <Text style={{ fontVariantNumeric: "tabular-nums" }}>
                          {price !== null ? price.toFixed(2) : "—"}
                        </Text>
                      </Col>
                      <Col span={14}>
                        <Sparkline data={series[sym] ?? []} />
                      </Col>
                    </Row>
                  );
                })}
              </Space>
            )}
          </Card>
        </Col>
      </Row>
    </PageContainer>
  );
}
