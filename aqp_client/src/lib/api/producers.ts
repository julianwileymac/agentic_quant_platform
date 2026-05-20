export {
  producersApi,
  type ProducerSummary,
  type ProducerStatus,
  type ProducerLogs,
} from "./streaming";

import type { ProducerSummary as _ProducerSummary } from "./streaming";

/**
 * Loose create-request shape kept for back-compat with the earlier
 * minimal producers wrapper — full create payload is whatever the
 * backend `ProducerSpec` accepts. Cast to `Record<string, unknown>`
 * before passing to `producersApi.create`.
 */
export interface ProducerCreateRequest extends Partial<_ProducerSummary> {
  name: string;
  kind: string;
  config?: Record<string, unknown>;
}
