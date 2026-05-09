/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL?: string;
  readonly VITE_WS_URL?: string;
  readonly VITE_DEFAULT_MODE?: string;
  readonly VITE_DASH_URL?: string;
  readonly VITE_MLFLOW_URL?: string;
  readonly VITE_JAEGER_URL?: string;
  readonly VITE_SUPERSET_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
