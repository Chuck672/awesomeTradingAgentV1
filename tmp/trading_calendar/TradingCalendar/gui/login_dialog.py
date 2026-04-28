from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
                           QLineEdit, QComboBox, QPushButton)
from PyQt6.QtCore import Qt
from config.mt5_accounts import MT5_ACCOUNTS

class MT5LoginDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("MT5 Account Login")
        self.setModal(True)
        self.credentials = None
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout()
        
        # Account Selection
        account_layout = QHBoxLayout()
        account_label = QLabel("Account:")
        self.account_combo = QComboBox()
        self.account_combo.addItems(MT5_ACCOUNTS.keys())
        self.account_combo.currentTextChanged.connect(self.update_account_info)
        account_layout.addWidget(account_label)
        account_layout.addWidget(self.account_combo)
        
        # Account Info Display
        self.account_info = QLabel()
        
        # Password Input
        password_layout = QHBoxLayout()
        password_label = QLabel("Password:")
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        password_layout.addWidget(password_label)
        password_layout.addWidget(self.password_input)
        
        # Buttons
        button_layout = QHBoxLayout()
        login_button = QPushButton("Login")
        cancel_button = QPushButton("Cancel")
        login_button.clicked.connect(self.accept)
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(login_button)
        button_layout.addWidget(cancel_button)
        
        # Add all layouts
        layout.addLayout(account_layout)
        layout.addWidget(self.account_info)
        layout.addLayout(password_layout)
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
        self.update_account_info()

    def update_account_info(self):
        account_name = self.account_combo.currentText()
        account = MT5_ACCOUNTS[account_name]
        info_text = f"Username: {account['username']}\nServer: {account['server']}"
        self.account_info.setText(info_text)

    def get_credentials(self):
        if self.exec() == QDialog.DialogCode.Accepted:
            account_name = self.account_combo.currentText()
            account = MT5_ACCOUNTS[account_name]
            return {
                "username": account["username"],
                "password": self.password_input.text(),
                "server": account["server"]
            }
        return None 