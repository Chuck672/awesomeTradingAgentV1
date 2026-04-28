const { app, BrowserWindow, protocol } = require('electron');
const path = require('path');
const fs = require('fs');
const { spawn } = require('child_process');

// IMPORTANT: Must be called before app is ready
protocol.registerSchemesAsPrivileged([
  { scheme: 'app', privileges: { secure: true, standard: true, supportFetchAPI: true, bypassCSP: true } }
]);

let backendProcess = null;
let mainWindow = null;
let splashWindow = null;

function startBackendAndCreateWindow() {
  const isDev = !app.isPackaged;
  let backendPath;
  let args = [];
  
  if (isDev) {
    backendPath = 'python';
    args = [path.join(__dirname, '..', 'run_backend.py')];
  } else {
    backendPath = path.join(process.resourcesPath, 'extraResources', 'api-server.exe');
  }

  console.log(`Starting backend: ${backendPath} ${args.join(' ')}`);
  backendProcess = spawn(backendPath, args, {
    detached: false,
    stdio: 'pipe'
  });

  // Track if backend is ready
  let isReady = false;

  backendProcess.stdout.on('data', (data) => {
    const out = data.toString();
    console.log(`Backend: ${out}`);
    
    // Look for Uvicorn startup message
    if (!isReady && out.includes('Uvicorn running on http://0.0.0.0:8123')) {
      isReady = true;
      console.log('Backend is ready! Creating window now.');
      createWindow();
    }
  });

  backendProcess.stderr.on('data', (data) => {
    console.error(`Backend Error: ${data.toString()}`);
  });

  backendProcess.on('close', (code) => {
    console.log(`Backend process exited with code ${code}`);
  });
  
  // Fallback: if we don't see the exact ready string within 15 seconds, just start the UI anyway
  setTimeout(() => {
    if (!isReady) {
      console.log('Backend startup timeout (15s). Attempting to load UI anyway as fallback.');
      isReady = true;
      createWindow();
    }
  }, 15000);
}

function createSplashWindow() {
  splashWindow = new BrowserWindow({
    width: 400,
    height: 300,
    transparent: true,
    frame: false,
    alwaysOnTop: true,
    webPreferences: { nodeIntegration: true, contextIsolation: false }
  });
  splashWindow.loadFile(path.join(__dirname, 'splash.html'));
}

function createWindow() {
  if (mainWindow) return;
  
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    title: "AwesomeTradingAgentV1",
    show: false, // hide until ready to prevent white flash
    webPreferences: {
      nodeIntegration: true,
      contextIsolation: false,
    },
  });

  mainWindow.once('ready-to-show', () => {
    if (splashWindow) {
      splashWindow.close();
      splashWindow = null;
    }
    mainWindow.show();
  });

  const isDev = !app.isPackaged;
  if (isDev) {
    mainWindow.loadURL('http://localhost:3000');
  } else {
    // Next.js static export paths
    mainWindow.loadURL('app://-/index.html');
  }
}

app.whenReady().then(() => {
  // Create splash screen first
  createSplashWindow();

  // Start the Python backend first, window will be created when backend is ready
  startBackendAndCreateWindow();

  // Register custom protocol to bypass file:// absolute path issues
  protocol.registerFileProtocol('app', (request, callback) => {
    let url = request.url.substr(7);    /* all urls start with 'app://' */
    // If there is a trailing slash or empty, point it to index.html
    if (!url || url === '' || url === '-' || url === '-/') {
      url = 'index.html';
    } else if (url.startsWith('-/')) {
      url = url.substr(2);
    }
    
    // Strip query parameters or hash from url before checking file existence
    const qIndex = url.indexOf('?');
    const hIndex = url.indexOf('#');
    const cutoff = Math.min(qIndex > -1 ? qIndex : url.length, hIndex > -1 ? hIndex : url.length);
    url = url.substring(0, cutoff);

    let p = path.normalize(path.join(__dirname, 'out', url));
    
    // Support Next.js routing (e.g., /about -> /out/about.html)
    if (!fs.existsSync(p)) {
      if (fs.existsSync(p + '.html')) {
        p = p + '.html';
      } else {
        p = path.normalize(path.join(__dirname, 'out', 'index.html'));
      }
    }
    callback({ path: p });
  });
});

app.on('window-all-closed', () => {
  if (backendProcess) {
    backendProcess.kill();
  }
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('will-quit', () => {
  if (backendProcess) {
    backendProcess.kill();
  }
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0 && backendProcess) {
    createWindow();
  }
});
