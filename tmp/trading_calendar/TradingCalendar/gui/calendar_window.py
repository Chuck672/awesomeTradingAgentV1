from PyQt6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                           QLabel, QComboBox, QGridLayout, QPushButton)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
import calendar
from datetime import datetime
import MetaTrader5 as mt5
import pandas as pd
from utils.mt5_utils import get_daily_results

class TradingCalendarWindow(QMainWindow):
    COLORS = {
        'BACKGROUND': '#1E1E1E',  # Dark background
        'PADDING': '#2D2D2D',     # Slightly lighter for empty cells
        'WEEKEND': '#2D2D2D',     # Same as padding for consistency
        'PROFIT': '#1E3B1E',      # Dark green for profit
        'LOSS': '#3B1E1E',        # Dark red for loss
        'NO_TRADE': '#2D2D2D',    # Regular cell background
        'TEXT': '#FFFFFF',        # White text
        'HEADER_BG': '#1E1E1E',   # Header background
        'BORDER': '#3D3D3D'       # Cell borders
    }

    def __init__(self):
        super().__init__()
        self.setWindowTitle("MT5 Trading Calendar")
        self.setMinimumSize(1000, 800)
        
        # Set window background color
        self.setStyleSheet(f"""
            QMainWindow {{
                background-color: {self.COLORS['BACKGROUND']};
            }}
            QLabel {{
                color: {self.COLORS['TEXT']};
            }}
            QComboBox {{
                background-color: {self.COLORS['PADDING']};
                color: {self.COLORS['TEXT']};
                border: 1px solid {self.COLORS['BORDER']};
                padding: 5px;
            }}
            QSpinBox {{
                background-color: {self.COLORS['PADDING']};
                color: {self.COLORS['TEXT']};
                border: 1px solid {self.COLORS['BORDER']};
                padding: 5px;
            }}
        """)
        
        # Initialize date
        self.current_date = datetime.now()
        
        # Create central widget and layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        # Create summary bar
        self.create_summary_bar(layout)
        
        # Create controls
        self.create_controls(layout)
        
        # Create calendar grid
        self.create_calendar_grid(layout)
        
        # Update calendar
        self.update_calendar()

    def create_summary_bar(self, parent_layout):
        summary_layout = QHBoxLayout()
        summary_layout.setSpacing(5)
        summary_layout.setContentsMargins(0, 0, 0, 5)
        
        # Create summary labels with placeholder text
        self.month_pl_label = QLabel("Month P&L: $0.00")
        self.win_rate_label = QLabel("Win Rate: 0%")
        self.total_trades_label = QLabel("Total Trades: 0")
        self.avg_daily_label = QLabel("Avg Daily: $0.00")
        self.withdrawal_label = QLabel("Withdrawal: $0.00")
        self.deposit_label = QLabel("Deposit: $0.00")  # New label
        self.rebate_label = QLabel("Rebate: $0.00")
        
        # Style labels
        summary_style = """
            QLabel {
                color: white;
                padding: 2px 8px;
                background-color: #2D2D2D;
                border: 1px solid #3D3D3D;
                border-radius: 2px;
                font-size: 11px;
                min-height: 15px;
                max-height: 15px;
            }
        """
        for label in [self.month_pl_label, self.win_rate_label, self.total_trades_label, 
                     self.avg_daily_label, self.withdrawal_label, self.deposit_label, 
                     self.rebate_label]:
            label.setStyleSheet(summary_style)
        
        # Add all labels to layout
        summary_layout.addWidget(self.month_pl_label)
        summary_layout.addWidget(self.win_rate_label)
        summary_layout.addWidget(self.total_trades_label)
        summary_layout.addWidget(self.avg_daily_label)
        summary_layout.addWidget(self.withdrawal_label)
        summary_layout.addWidget(self.deposit_label)
        summary_layout.addWidget(self.rebate_label)
        summary_layout.addStretch()
        
        parent_layout.addLayout(summary_layout)

    def update_summary(self, daily_results):
        if daily_results.empty:
            return
            
        print("\nDebug - Update Summary Input:")
        print(daily_results)
        
        # Calculate summary statistics
        total_pl = daily_results['profit'].sum()
        total_trades = int(daily_results['trades'].sum())
        trading_days = len(daily_results[daily_results['trades'] > 0])
        
        print(f"\nDebug - Calculations:")
        print(f"Total P&L: ${total_pl:.2f}")
        print(f"Total Trades: {total_trades}")
        print(f"Trading Days: {trading_days}")
        
        # Calculate win rate
        winning_trades = daily_results['winning_trades'].sum()
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        
        # Calculate average daily P&L using only trading days
        avg_daily = total_pl / trading_days if trading_days > 0 else 0
        
        # Get totals for the month
        total_withdrawals = abs(daily_results['withdrawals'].sum())
        total_deposits = daily_results['deposits'].sum()
        total_rebates = daily_results['rebates'].sum()
        
        print(f"Avg Daily: ${avg_daily:.2f}")
        print(f"Withdrawals: ${total_withdrawals:.2f}")
        print(f"Deposits: ${total_deposits:.2f}")
        print(f"Rebates: ${total_rebates:.2f}")
        
        # Update labels
        self.month_pl_label.setText(f"Month P&L: ${total_pl:.2f}")
        self.win_rate_label.setText(f"Win Rate: {win_rate:.1f}%")
        self.total_trades_label.setText(f"Total Trades: {total_trades}")
        self.avg_daily_label.setText(f"Avg Daily: ${avg_daily:.2f}")
        self.withdrawal_label.setText(f"Withdrawal: ${total_withdrawals:.2f}")
        self.deposit_label.setText(f"Deposit: ${total_deposits:.2f}")
        self.rebate_label.setText(f"Rebate: ${total_rebates:.2f}")

    def get_withdrawals(self, start_date, end_date):
        try:
            deals = mt5.history_deals_get(start_date, end_date)
            if deals is None or len(deals) == 0:
                return 0.0
            
            df = pd.DataFrame(list(deals), columns=deals[0]._asdict().keys())
            # Get only withdrawal operations (type 6 with negative profit)
            withdrawals = df[(df['type'] == 6) & (df['profit'] < 0)]['profit'].sum()
            return withdrawals
        except Exception as e:
            print(f"Failed to fetch withdrawals: {str(e)}")
            return 0.0

    def create_controls(self, parent_layout):
        controls_layout = QHBoxLayout()
        
        # Year controls
        year_layout = QHBoxLayout()
        prev_year_btn = QPushButton("<")
        next_year_btn = QPushButton(">")
        self.year_label = QLabel(str(self.current_date.year))
        
        # Style the year controls
        for btn in [prev_year_btn, next_year_btn]:
            btn.setFixedWidth(30)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #2D2D2D;
                    color: white;
                    border: 1px solid #3D3D3D;
                    padding: 5px;
                }
                QPushButton:hover {
                    background-color: #3D3D3D;
                }
            """)
        
        self.year_label.setStyleSheet("""
            QLabel {
                color: white;
                padding: 5px 15px;
                background-color: #2D2D2D;
                border: 1px solid #3D3D3D;
            }
        """)
        
        # Connect year button signals
        prev_year_btn.clicked.connect(self.previous_year)
        next_year_btn.clicked.connect(self.next_year)
        
        year_layout.addWidget(QLabel("Year:"))
        year_layout.addWidget(prev_year_btn)
        year_layout.addWidget(self.year_label)
        year_layout.addWidget(next_year_btn)
        
        # Month combo
        month_label = QLabel("Month:")
        self.month_combo = QComboBox()
        self.month_combo.addItems(list(calendar.month_name)[1:])
        self.month_combo.setCurrentIndex(self.current_date.month - 1)
        self.month_combo.currentIndexChanged.connect(self.update_calendar)
        
        # Add to layout with spacing
        controls_layout.addLayout(year_layout)
        controls_layout.addSpacing(20)
        controls_layout.addWidget(month_label)
        controls_layout.addWidget(self.month_combo)
        controls_layout.addStretch()
        
        parent_layout.addLayout(controls_layout)

    def create_calendar_grid(self, parent_layout):
        self.calendar_grid = QGridLayout()
        self.calendar_grid.setSpacing(1)
        
        # Add day headers
        days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        for i, day in enumerate(days):
            label = QLabel(day)
            label.setFont(QFont("Arial", 10, QFont.Weight.Bold))
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setStyleSheet(f"""
                background-color: {self.COLORS['HEADER_BG']};
                border: 1px solid {self.COLORS['BORDER']};
                padding: 5px;
            """)
            self.calendar_grid.addWidget(label, 0, i)
        
        # Create calendar cells
        self.cells = []
        for row in range(6):
            row_cells = []
            for col in range(7):
                cell = QLabel()
                cell.setAlignment(Qt.AlignmentFlag.AlignCenter)
                cell.setStyleSheet(f"""
                    background-color: {self.COLORS['NO_TRADE']};
                    border: 1px solid {self.COLORS['BORDER']};
                    padding: 5px;
                """)
                cell.setMinimumSize(100, 80)
                self.calendar_grid.addWidget(cell, row + 1, col)
                row_cells.append(cell)
            self.cells.append(row_cells)
        
        parent_layout.addLayout(self.calendar_grid)

    def update_calendar(self):
        year = int(self.year_label.text())
        month = self.month_combo.currentIndex() + 1
        
        # Clear all cells first
        for row in self.cells:
            for cell in row:
                cell.setText("")
                cell.setStyleSheet(f"""
                    background-color: {self.COLORS['PADDING']};
                    border: 1px solid {self.COLORS['BORDER']};
                    color: {self.COLORS['TEXT']};
                """)
        
        # Get calendar data
        start_date = datetime(year, month, 1)
        # Add one day to include the last day of the month
        end_date = datetime(year, month, calendar.monthrange(year, month)[1], 23, 59, 59)
        daily_results = get_daily_results(start_date, end_date)
        
        # Update summary bar
        self.update_summary(daily_results)
        
        # Get calendar matrix
        cal = calendar.monthcalendar(year, month)
        
        # Update cells
        for i, week in enumerate(cal):
            for j, day in enumerate(week):
                cell = self.cells[i][j]
                
                if day == 0:
                    cell.setText("")
                    cell.setStyleSheet(f"""
                        background-color: {self.COLORS['PADDING']};
                        border: 1px solid {self.COLORS['BORDER']};
                        color: {self.COLORS['TEXT']};
                    """)
                    continue
                
                date = datetime(year, month, day).date()
                profit = daily_results.loc[date, 'profit'] if date in daily_results.index else 0.0
                trades = daily_results.loc[date, 'trades'] if date in daily_results.index else 0
                
                # Set background color
                if date.weekday() >= 5:  # Weekend
                    color = self.COLORS['WEEKEND']
                elif profit > 0:
                    color = self.COLORS['PROFIT']
                elif profit < 0:
                    color = self.COLORS['LOSS']
                else:
                    color = self.COLORS['NO_TRADE']
                
                # Set text with exact decimal for profit only
                if trades > 0:
                    text = f"{day}\n${profit:.2f}\n{int(trades)} trade{'s' if trades != 1 else ''}"
                else:
                    text = str(day)
                
                cell.setText(text)
                cell.setStyleSheet(f"""
                    background-color: {color};
                    border: 1px solid {self.COLORS['BORDER']};
                    color: {self.COLORS['TEXT']};
                """)

    def previous_year(self):
        current_year = int(self.year_label.text())
        self.year_label.setText(str(current_year - 1))
        self.update_calendar()

    def next_year(self):
        current_year = int(self.year_label.text())
        self.year_label.setText(str(current_year + 1))
        self.update_calendar() 