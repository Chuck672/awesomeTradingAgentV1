import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon
import os
from gui.calendar_window import TradingCalendarWindow
from gui.login_dialog import MT5LoginDialog
from utils.mt5_utils import connect_to_mt5

def main():
    app = QApplication(sys.argv)
    
    # Set application icon
    icon_path = os.path.join(os.path.dirname(__file__), 'assets', 'mt5_icon.ico')
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    
    # Show login dialog first
    login_dialog = MT5LoginDialog()
    credentials = login_dialog.get_credentials()
    
    if credentials and connect_to_mt5(credentials):
        window = TradingCalendarWindow()
        window.show()
        sys.exit(app.exec())
    else:
        sys.exit()

if __name__ == '__main__':
    main() 