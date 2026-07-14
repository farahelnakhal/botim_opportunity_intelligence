/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_EXECUTIVE_API_BASE_URL?: string;
  readonly VITE_COPILOT_API_BASE_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
