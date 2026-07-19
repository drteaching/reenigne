/// <reference types="vite/client" />

type MediaAccessStatus = "not-determined" | "granted" | "denied" | "restricted" | "unknown";

interface PreflightError {
  reason: "ffmpeg_missing" | "permission_denied" | "other";
  message: string;
  detail: string;
}

interface PreflightResult {
  ffmpeg_found: boolean;
  ffmpeg_path: string | null;
  screen_ok: boolean;
  mic_ok: boolean;
  errors: PreflightError[];
}

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
  permStatus: () => Promise<{
    platform: string;
    microphone: MediaAccessStatus;
    screen: MediaAccessStatus;
  }>;
  requestMicrophone: () => Promise<boolean>;
  openPermissionSettings: (pane: "screen" | "microphone") => Promise<unknown>;
}

interface Window {
  reenigne: ReenigneBridge;
}
