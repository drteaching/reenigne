/// <reference types="vite/client" />

interface ReenigneBridge {
  getAuth: () => Promise<{ token: string | null; email: string | null; apiUrl: string }>;
  setAuth: (token: string, email: string) => Promise<boolean>;
  clearAuth: () => Promise<boolean>;
  apiFetch: (
    path: string,
    method?: string,
    body?: unknown
  ) => Promise<{ status: number; data: unknown }>;
  workerRpc: (method: string, params?: Record<string, unknown>) => Promise<unknown>;
  openPath: (p: string) => Promise<string>;
  openExternal: (url: string) => Promise<void>;
  showPermissionsHelp: () => Promise<boolean>;
}

interface Window {
  reenigne: ReenigneBridge;
}
