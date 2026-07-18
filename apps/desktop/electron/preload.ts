import { contextBridge, ipcRenderer } from "electron";

contextBridge.exposeInMainWorld("reenigne", {
  getAuth: () => ipcRenderer.invoke("auth:get"),
  setAuth: (token: string, email: string) =>
    ipcRenderer.invoke("auth:set", { token, email }),
  clearAuth: () => ipcRenderer.invoke("auth:clear"),
  apiFetch: (path: string, method?: string, body?: unknown) =>
    ipcRenderer.invoke("api:fetch", { path, method, body }),
  workerRpc: (method: string, params?: Record<string, unknown>) =>
    ipcRenderer.invoke("worker:rpc", method, params || {}),
  openPath: (p: string) => ipcRenderer.invoke("shell:open", p),
  openExternal: (url: string) => ipcRenderer.invoke("shell:external", url),
  showPermissionsHelp: () => ipcRenderer.invoke("dialog:permissions"),
});
