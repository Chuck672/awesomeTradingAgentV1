const { app, BrowserWindow, protocol } = require('electron');
const path = require('path');
const fs = require('fs');

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
  protocol.interceptFileProtocol('app', (request, callback) => {
    const url = request.url.substr(7);    /* all urls start with 'app://' */
    let p = path.normalize(path.join(__dirname, 'out', url));
    if (!fs.existsSync(p)) {
      p = path.normalize(path.join(__dirname, 'out', 'index.html'));
    }
    callback({ path: p });
  }, (error) => {
    if (error) console.error('Failed to register protocol');
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
