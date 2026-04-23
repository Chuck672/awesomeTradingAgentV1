const { app, BrowserWindow, Menu } = require('electron');
const path = require('path');
const { spawn, exec } = require('child_process');
const os = require('os');

let mainWindow;
let pythonProcess = null;

function startBackend() {
  // Start the Python backend process.
  // In production, you would point to a bundled executable (like main.exe from PyInstaller).
  // In development, it points to the python script.
  const isProd = !process.defaultApp && !/[\\/]electron-prebuilt[\\/]/.test(process.execPath) && !/[\\/]electron[\\/]/.test(process.execPath);
  
  if (isProd) {
    const backendPath = path.join(process.resourcesPath, 'backend', 'main.exe');
    pythonProcess = spawn(backendPath, [], { detached: false });
  } else {
    const backendPath = path.join(__dirname, '..', '..', 'backend', 'main.py');
    pythonProcess = spawn('python', ['-m', 'backend.main'], { 
      cwd: path.join(__dirname, '..', '..'),
      detached: false 
    });
  }

  pythonProcess.stdout.on('data', (data) => {
    console.log(`Backend stdout: ${data}`);
  });

  pythonProcess.stderr.on('data', (data) => {
    console.error(`Backend stderr: ${data}`);
  });

  pythonProcess.on('close', (code) => {
    console.log(`Backend process exited with code ${code}`);
    pythonProcess = null;
  });

  pythonProcess.on('error', (err) => {
    console.error(`Failed to start backend: ${err}`);
  });
}

function createMenu() {
  const template = [
    {
      label: '文件',
      submenu: [
        { role: 'quit', label: '退出' }
      ]
    },
    {
      label: '工具',
      submenu: [
        { 
          label: '数据缺口检测与自动回补',
          click: () => {
            const http = require('http');
            const req = http.request({
              hostname: '127.0.0.1',
              port: 8000,
              path: '/api/broker/reconcile/force?timeframe=M1',
              method: 'POST'
            }, (res) => {
              const { dialog } = require('electron');
              dialog.showMessageBox(mainWindow, {
                type: 'info',
                title: '扫描已启动',
                message: '已通知后台开始深度扫描和自动回补数据缺口。您可以在前端图表右上角进度条观察进度。'
              });
            });
            req.on('error', (e) => {
              const { dialog } = require('electron');
              dialog.showErrorBox('错误', '无法连接到后台服务: ' + e.message);
            });
            req.end();
          }
        }
      ]
    },
    {
      label: '视图',
      submenu: [
        { role: 'reload', label: '刷新页面' },
        { role: 'forceReload', label: '强制刷新' },
        { type: 'separator' },
        { role: 'toggledevtools', label: '切换开发者工具' },
        { type: 'separator' },
        { role: 'resetZoom', label: '重置缩放' },
        { role: 'zoomIn', label: '放大' },
        { role: 'zoomOut', label: '缩小' },
        { type: 'separator' },
        { role: 'togglefullscreen', label: '切换全屏' }
      ]
    }
  ];

  const menu = Menu.buildFromTemplate(template);
  Menu.setApplicationMenu(menu);
}

function createWindow() {
  mainWindow = new BrowserWindow({
    title: 'Awesome Chart V3',
    width: 1280,
    height: 800,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      preload: path.join(__dirname, 'preload.js')
    }
  });

  const isProd = !process.defaultApp && !/[\\/]electron-prebuilt[\\/]/.test(process.execPath) && !/[\\/]electron[\\/]/.test(process.execPath);

  if (isProd) {
    mainWindow.loadFile(path.join(__dirname, '..', 'out', 'index.html'));
  } else {
    // In development, use Next.js dev server
    mainWindow.loadURL('http://localhost:3000');
    // mainWindow.webContents.openDevTools();
  }

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

// Ensure the python process and its children are killed correctly
function killBackendProcess() {
  if (pythonProcess && pythonProcess.pid) {
    console.log('Terminating Python backend process tree...');
    if (os.platform() === 'win32') {
      exec(`taskkill /pid ${pythonProcess.pid} /T /F`, (err, stdout, stderr) => {
        if (err) {
          console.error(`Error killing backend: ${err}`);
        }
      });
    } else {
      // Use negative pid to kill the process group
      process.kill(-pythonProcess.pid);
    }
  }
}

app.whenReady().then(() => {
  createMenu();
  startBackend();
  createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('before-quit', () => {
  killBackendProcess();
});

// Also handle unexpected crashes
process.on('uncaughtException', () => {
  killBackendProcess();
  process.exit(1);
});
process.on('SIGINT', () => {
  killBackendProcess();
  process.exit();
});
process.on('SIGTERM', () => {
  killBackendProcess();
  process.exit();
});
