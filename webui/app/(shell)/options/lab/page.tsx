"use client";

import {
  Button,
  Card,
  Col,
  Form,
  InputNumber,
  Radio,
  Row,
  Statistic,
  Typography,
} from "antd";
import { useState } from "react";

import { PageContainer } from "@/components/shell/PageContainer";
import { apiFetch } from "@/lib/api/client";

const { Paragraph } = Typography;

interface GreeksResult {
  model: string;
  price?: number;
  delta?: number;
  gamma?: number;
  theta?: number;
  vega?: number;
  vanna?: number;
  volga?: number;
  veta?: number;
  price_btc?: number;
  price_usd?: number;
  delta_usd?: number;
  gamma_usd?: number;
  error?: string;
}

interface OptionsFormValues {
  forward: number;
  strike: number;
  time_to_expiry_years: number;
  sigma: number;
  is_call: boolean;
  model: "bachelier" | "inverse";
}

const errorMessage = (err: unknown): string =>
  err instanceof Error ? err.message : String(err);

export default function OptionsLabPage() {
  const [form] = Form.useForm();
  const [result, setResult] = useState<GreeksResult | null>(null);
  const [loading, setLoading] = useState(false);

  const onSubmit = async (values: OptionsFormValues) => {
    setLoading(true);
    try {
      const res = await apiFetch<string | GreeksResult>("/agents/tools/option_greeks_tool/run", {
        method: "POST",
        body: JSON.stringify(values),
      });
      const parsed: GreeksResult =
        typeof res === "string" ? (JSON.parse(res) as GreeksResult) : res;
      setResult(parsed);
    } catch (err: unknown) {
      setResult({ model: "error", error: errorMessage(err) });
    } finally {
      setLoading(false);
    }
  };

  return (
    <PageContainer title="Options Lab">
      <Paragraph>
        Options pricing and Greeks calculator. Bachelier (normal) model is
        appropriate for low-priced underlyings (rates, basis spreads); the
        inverse model matches Deribit-style options settled in BTC.
      </Paragraph>

      <Row gutter={16}>
        <Col xs={24} md={10}>
          <Card title="Inputs">
            <Form
              form={form}
              layout="vertical"
              initialValues={{
                forward: 100,
                strike: 100,
                time_to_expiry_years: 0.25,
                sigma: 0.2,
                is_call: true,
                model: "bachelier",
              }}
              onFinish={onSubmit}
            >
              <Form.Item label="Forward price" name="forward">
                <InputNumber min={0.0001} step={1} style={{ width: "100%" }} />
              </Form.Item>
              <Form.Item label="Strike" name="strike">
                <InputNumber min={0.0001} step={1} style={{ width: "100%" }} />
              </Form.Item>
              <Form.Item label="Time to expiry (years)" name="time_to_expiry_years">
                <InputNumber min={0.0001} step={0.01} style={{ width: "100%" }} />
              </Form.Item>
              <Form.Item label="Sigma" name="sigma">
                <InputNumber min={0.0001} step={0.01} style={{ width: "100%" }} />
              </Form.Item>
              <Form.Item label="Type" name="is_call">
                <Radio.Group>
                  <Radio value={true}>Call</Radio>
                  <Radio value={false}>Put</Radio>
                </Radio.Group>
              </Form.Item>
              <Form.Item label="Model" name="model">
                <Radio.Group>
                  <Radio value="bachelier">Bachelier (normal)</Radio>
                  <Radio value="inverse">Inverse (Deribit)</Radio>
                </Radio.Group>
              </Form.Item>
              <Button type="primary" htmlType="submit" loading={loading} block>
                Compute
              </Button>
            </Form>
          </Card>
        </Col>
        <Col xs={24} md={14}>
          <Card title="Greeks">
            {result ? (
              result.error ? (
                <Paragraph type="danger">{result.error}</Paragraph>
              ) : (
                <Row gutter={[16, 16]}>
                  {Object.entries(result).map(([k, v]) =>
                    typeof v === "number" ? (
                      <Col key={k} xs={12} md={8}>
                        <Statistic title={k} value={v} precision={6} />
                      </Col>
                    ) : null,
                  )}
                </Row>
              )
            ) : (
              <Paragraph>Submit the form to compute price + Greeks.</Paragraph>
            )}
          </Card>
        </Col>
      </Row>
    </PageContainer>
  );
}
