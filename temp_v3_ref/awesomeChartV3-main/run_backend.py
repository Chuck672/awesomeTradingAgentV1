import sys
import os

# Ensure the root directory is in the path
if getattr(sys, 'frozen', False):
    # If the application is run as a bundle, the PyInstaller bootloader
    # extends the sys.path to include the bundle directory.
    pass
else:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.main import app
import uvicorn

if __name__ == "__main__":
    if getattr(sys, 'frozen', False):
        # Disable reload when running from the compiled executable
        uvicorn.run(app, host="127.0.0.1", port=8000)
    else:
        uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=True)
