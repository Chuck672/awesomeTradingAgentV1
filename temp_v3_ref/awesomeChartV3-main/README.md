# Awesome Chart V3 📈

Awesome Chart V3 (formerly Order Flow Chart) is a high-performance, professional-grade trading charting desktop application built by **QuantLogicLab**. It seamlessly integrates real-time market data from MetaTrader 5 (MT5) with powerful analytical tools, offering a robust environment for technical analysis, order flow tracking, and historical replay.

## ✨ Key Features

### 🚀 Ultra-Fast Data Engine
- **Multi-Broker Support:** Connects directly to any MetaTrader 5 (MT5) terminal. Supports dynamic broker configuration and physical sandbox isolation for data.
- **Dual-Layer Database:** 
  - **Hot Data (DuckDB):** Blazing fast columnar database for real-time querying and recent history.
  - **Cold Data (Parquet):** Highly compressed archival storage for deep historical data (up to 3+ years), managed silently in the background.
- **Zero-Gap Reliability:** Advanced `Catch-up` and `Overlap` mechanisms guarantee 100% data continuity across server reboots, network disconnections, and weekend market closures.

### 📊 Advanced Charting & Custom Indicators
Built on top of Lightweight Charts with extensive custom Canvas 2D rendering:
- **Trend Exhaustion:** Advanced dual-period Williams %R indicator with real-time Overbought/Oversold Box warnings and Reversal Break (Triangle) signals.
- **MSB Zigzag:** Market Structure Break Zigzag lines with customizable pivot points, highlighting BoS (Break of Structure) and ChoCh (Change of Character).
- **Volume Profile & Order Flow:** 
  - **Visible Range Volume Profile (VRVP):** Dynamically calculates volume distribution on the visible screen.
  - **Session Volume Profile (SVP):** Automatically splits and analyzes volume by trading sessions.
  - **Order Flow Footprint (Bubble):** Visualizes intra-candle tick volume deltas.
- **Bar Replay (Backtesting):** Jump to any historical point and play back the market candle-by-candle with adjustable speeds.

### 🛠 Professional Desktop App Experience
- **Standalone Executable:** Packaged as a native Windows `.exe` application via Electron and PyInstaller. No local Python or Node.js environment required for end-users!
- **Auto-managed Backend:** The Python FastAPI backend runs silently in the background and is automatically managed (started and killed) by the Electron frontend.
- **Native Menus & Shortcuts:** Native application menus, zooming, developer tools, and full-screen support.
- **Customizable Interface:** Fully responsive multi-chart grid layout with Dark/Light themes.

## 🏗 Tech Stack

- **Frontend:** Next.js (React), Tailwind CSS, Lightweight Charts, Electron, electron-builder.
- **Backend:** FastAPI (Python), Uvicorn, asyncio, PyInstaller.
- **Data Layer:** DuckDB, Parquet, SQLite (Metadata).
- **Data Source:** MetaTrader 5 Python API.

## ⚙️ Development Setup

### Prerequisites
1. Python 3.10+
2. Node.js 18+
3. A running MetaTrader 5 Terminal on your local machine.

### Backend Setup (Development)
```bash
# Clone the repository
git clone https://github.com/Chuck672/awesomeChartV3.git
cd awesomeChartV3

# Install dependencies
cd backend
pip install -r requirements.txt # (Ensure all dependencies like fastapi, uvicorn, MetaTrader5 are installed)

# Run the backend locally
cd ..
python run_backend.py
```

### Frontend Setup (Development)
```bash
cd frontend
npm install
npm run dev
```
Open `http://localhost:3000` in your browser.

## 📦 Packaging for Windows (.exe)

Awesome Chart V3 can be compiled into a single Windows Setup executable. 

### 1. Build the Python Backend
We use PyInstaller to compile the FastAPI backend into a standalone directory:
```bash
# From the project root (awesomeChartV3)
pip install pyinstaller
pyinstaller --noconfirm --onedir --windowed --distpath backend/dist --workpath backend/build --name main --version-file version.txt --collect-submodules backend --collect-all uvicorn --collect-all fastapi run_backend.py
```

### 2. Build the Electron Desktop App
Electron-builder is used to package the Next.js static export along with the compiled Python backend.
```bash
cd frontend
npm install
npm run electron:build
```
The final installer will be generated in `frontend/dist_electron/AwesomeChartV3 Setup 3.1.0-beta.exe`.

## 👨‍💻 Author
**QuantLogicLab**

## 📄 License
Copyright (c) QuantLogicLab. All rights reserved.
