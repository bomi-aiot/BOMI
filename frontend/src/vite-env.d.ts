/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_BASE_URL?: string
  readonly VITE_WS_URL?: string
  readonly VITE_USE_MOCK_API?: string
  readonly VITE_GUARDIAN_API_AUTH_READY?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
