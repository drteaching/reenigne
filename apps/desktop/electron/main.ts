import {
  app,
  BrowserWindow,
  Tray,
  Menu,
  nativeImage,
  ipcMain,
  shell,
  dialog,
} from "electron";
import * as path from "path";
import * as fs from "fs";
import { spawn, ChildProcessWithoutNullStreams } from "child_process";
import { autoUpdater } from "electron-updater";

const API_URL = process.env.REENIGNE_API_URL || "https://api.reenigne.dev";
const STORE_PATH = () => path.join(app.getPath("userData"), "session.json");

type StoreData = {
  token?: string;
  email?: string;
};

function readStore(): StoreData {
  try {
    return JSON.parse(fs.readFileSync(STORE_PATH(), "utf-8"));
  } catch {
    return {};
  }
}

function writeStore(data: StoreData) {
  fs.writeFileSync(STORE_PATH(), JSON.stringify(data, null, 2));
}

let mainWindow: BrowserWindow | null = null;
let tray: Tray | null = null;
let worker: ChildProcessWithoutNullStreams | null = null;
let rpcId = 1;
const pending = new Map<
  number,
  { resolve: (v: unknown) => void; reject: (e: Error) => void }
>();

function isDev() {
  return !app.isPackaged;
}

function workerCommand(): { cmd: string; args: string[]; env: NodeJS.ProcessEnv } {
  const env = {
    ...process.env,
    REENIGNE_API_URL: API_URL,
    REENIGNE_API_TOKEN: readStore().token || "",
    PATH: process.env.PATH || "",
  };

  // Prefer bundled ffmpeg on PATH for worker
  const ffmpegDir = isDev()
    ? path.join(__dirname, "../resources/ffmpeg")
    : path.join(process.resourcesPath, "ffmpeg");
  if (fs.existsSync(ffmpegDir)) {
    env.PATH = `${ffmpegDir}${path.delimiter}${env.PATH}`;
  }

  if (isDev()) {
    const workerRoot = path.join(__dirname, "../../../packages/worker");
    return {
      cmd: process.env.REENIGNE_PYTHON || "python3",
      args: ["-m", "reenigne.worker_rpc"],
      env: {
        ...env,
        PYTHONPATH: path.join(workerRoot, "src"),
      },
    };
  }

  const bin = path.join(
    process.resourcesPath,
    "worker",
    process.platform === "win32" ? "reenigne-worker.exe" : "reenigne-worker"
  );
  return { cmd: bin, args: [], env };
}

function ensureWorker() {
  if (worker && !worker.killed) return;
  const { cmd, args, env } = workerCommand();
  worker = spawn(cmd, args, { env, stdio: ["pipe", "pipe", "pipe"] });
  let buffer = "";
  worker.stdout.on("data", (chunk: Buffer) => {
    buffer += chunk.toString();
    let idx: number;
    while ((idx = buffer.indexOf("\n")) >= 0) {
      const line = buffer.slice(0, idx).trim();
      buffer = buffer.slice(idx + 1);
      if (!line) continue;
      try {
        const msg = JSON.parse(line);
        const p = pending.get(msg.id);
        if (!p) continue;
        pending.delete(msg.id);
        if (msg.error) p.reject(new Error(msg.error.message));
        else p.resolve(msg.result);
      } catch {
        /* ignore partial */
      }
    }
  });
  worker.stderr.on("data", (d) => console.error("[worker]", d.toString()));
  worker.on("exit", () => {
    worker = null;
  });
}

function rpc(method: string, params: Record<string, unknown> = {}): Promise<unknown> {
  ensureWorker();
  const id = rpcId++;
  return new Promise((resolve, reject) => {
    pending.set(id, { resolve, reject });
    worker!.stdin.write(JSON.stringify({ jsonrpc: "2.0", id, method, params }) + "\n");
    setTimeout(() => {
      if (pending.has(id)) {
        pending.delete(id);
        reject(new Error(`RPC timeout: ${method}`));
      }
    }, 30 * 60 * 1000);
  });
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 960,
    height: 680,
    minWidth: 720,
    minHeight: 520,
    titleBarStyle: process.platform === "darwin" ? "hiddenInset" : "default",
    backgroundColor: "#0c0f12",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  if (isDev()) {
    mainWindow.loadURL("http://localhost:5173");
  } else {
    mainWindow.loadFile(path.join(__dirname, "../dist/index.html"));
  }

  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}

function createTray() {
  const icon = nativeImage.createEmpty();
  tray = new Tray(icon);
  const menu = Menu.buildFromTemplate([
    {
      label: "Show reenigne",
      click: () => {
        if (!mainWindow) createWindow();
        else mainWindow.show();
      },
    },
    { type: "separator" },
    { label: "Quit", click: () => app.quit() },
  ]);
  tray.setToolTip("reenigne");
  tray.setContextMenu(menu);
}

function registerIpc() {
  ipcMain.handle("auth:get", () => {
    const s = readStore();
    return { token: s.token || null, email: s.email || null, apiUrl: API_URL };
  });

  ipcMain.handle("auth:set", (_e, data: { token: string; email: string }) => {
    writeStore({ token: data.token, email: data.email });
    // Restart worker so env picks up new token
    if (worker) {
      worker.kill();
      worker = null;
    }
    return true;
  });

  ipcMain.handle("auth:clear", () => {
    writeStore({});
    if (worker) {
      worker.kill();
      worker = null;
    }
    return true;
  });

  ipcMain.handle("api:fetch", async (_e, opts: { path: string; method?: string; body?: unknown }) => {
    const token = readStore().token;
    const res = await fetch(`${API_URL}${opts.path}`, {
      method: opts.method || "GET",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: opts.body ? JSON.stringify(opts.body) : undefined,
    });
    const text = await res.text();
    let data: unknown = null;
    try {
      data = JSON.parse(text);
    } catch {
      data = text;
    }
    return { status: res.status, data };
  });

  ipcMain.handle("worker:rpc", async (_e, method: string, params: Record<string, unknown>) => {
    return rpc(method, params);
  });

  ipcMain.handle("shell:open", (_e, p: string) => shell.openPath(p));
  ipcMain.handle("shell:external", (_e, url: string) => shell.openExternal(url));

  ipcMain.handle("dialog:permissions", async () => {
    if (process.platform === "darwin") {
      await dialog.showMessageBox({
        type: "info",
        title: "Permissions required",
        message:
          "reenigne needs Screen Recording and Microphone access.\n\n" +
          "Open System Settings → Privacy & Security and enable both for reenigne, then restart the app.",
      });
    }
    return true;
  });
}

app.whenReady().then(() => {
  registerIpc();
  createWindow();
  createTray();
  if (!isDev()) {
    autoUpdater.checkForUpdatesAndNotify().catch(() => undefined);
  }
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});

app.on("before-quit", () => {
  if (worker) worker.kill();
});
