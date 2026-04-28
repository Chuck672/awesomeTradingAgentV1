const { app, BrowserWindow, protocol } = require('electron');
const path = require('path');
const fs = require('fs');

// IMPORTANT: Must be called before app is ready
protocol.registerSchemesAsPrivileged([
  { scheme: 'app', privileges: { secure: true, standard: true, supportFetchAPI: true, bypassCSP: true } }
]);

function createWindow() {
  const win = new BrowserWindow({
    width: 1280,
    height: 800,
    webPreferences: {
      nodeIntegration: true,
      contextIsolation: false,
    },
  });

  const isDev = !app.isPackaged;
  if (isDev) {
    win.loadURL('http://localhost:3000');
  } else {
    // Next.js static export paths
    win.loadURL('app://-/index.html');
  }
}

app.whenReady().then(() => {
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

  createWindow();
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow();
  }
});
