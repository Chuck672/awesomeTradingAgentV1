import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime
from PyQt6.QtWidgets import QMessageBox

def connect_to_mt5(config):
    if not mt5.initialize():
        QMessageBox.critical(None, "Error", "MT5 initialization failed")
        mt5.shutdown()
        return False
    
    try:
        authorized = mt5.login(config["username"], config["password"], config["server"])
        if not authorized:
            QMessageBox.critical(None, "Error", f"Failed to connect to trade account. Error code: {mt5.last_error()}")
            mt5.shutdown()
            return False
        
        QMessageBox.information(None, "Success", "Successfully connected to MT5 account")
        return True
    except Exception as e:
        QMessageBox.critical(None, "Error", f"Connection error: {str(e)}")
        mt5.shutdown()
        return False

def get_daily_results(start_date, end_date):
    try:
        deals = mt5.history_deals_get(start_date, end_date)
        if deals is None or len(deals) == 0:
            return pd.DataFrame(columns=['profit', 'trades', 'winning_trades', 'withdrawals', 'rebates', 'deposits'])
        
        df = pd.DataFrame(list(deals), columns=deals[0]._asdict().keys())
        
        # Separate trading deals and balance operations
        trading_df = df[df['symbol'] != ''].copy()
        balance_df = df[df['symbol'] == ''].copy()
        
        trading_df['time'] = pd.to_datetime(trading_df['time'], unit='s')
        trading_df['date'] = trading_df['time'].dt.date
        
        # Filter out trades outside the date range
        trading_df = trading_df[
            (trading_df['date'] >= start_date.date()) & 
            (trading_df['date'] <= end_date.date())
        ]
        
        trading_df['profit'] = trading_df['profit'] + trading_df['commission'] + trading_df['swap']
        
        balance_df['time'] = pd.to_datetime(balance_df['time'], unit='s')
        balance_df['date'] = balance_df['time'].dt.date
        
        # Filter balance operations to date range
        balance_df = balance_df[
            (balance_df['date'] >= start_date.date()) & 
            (balance_df['date'] <= end_date.date())
        ]
        
        # Calculate daily trading results
        daily_trades = trading_df[trading_df['type'] == 0].groupby('date')['position_id'].nunique()
        daily_profits = trading_df.groupby('date')['profit'].sum()
        
        # Create daily results DataFrame
        daily_results = pd.DataFrame({
            'profit': daily_profits,
            'trades': daily_trades,
            'withdrawals': 0.0,
            'rebates': 0.0,
            'deposits': 0.0
        })
        
        # Process balance operations
        for _, row in balance_df.iterrows():
            date = row['date']
            if date not in daily_results.index:
                daily_results.loc[date] = {'profit': 0, 'trades': 0, 'withdrawals': 0, 'rebates': 0, 'deposits': 0}
            
            if 'D-INTARB' in str(row['comment']):  # Rebate
                daily_results.loc[date, 'rebates'] += row['profit']
            elif 'W-' in str(row['comment']):  # Withdrawal
                daily_results.loc[date, 'withdrawals'] += row['profit']
            elif 'D-' in str(row['comment']) and row['profit'] > 0:  # Deposit
                daily_results.loc[date, 'deposits'] += row['profit']
        
        # Calculate winning trades
        position_profits = trading_df.groupby('position_id')['profit'].sum()
        winning_positions = position_profits[position_profits > 0].index
        daily_winners = trading_df[
            (trading_df['position_id'].isin(winning_positions)) & 
            (trading_df['type'] == 0)
        ].groupby('date')['position_id'].nunique()
        
        daily_results['winning_trades'] = daily_winners
        daily_results = daily_results.fillna(0)
        
        return daily_results
        
    except Exception as e:
        print(f"Error in get_daily_results: {str(e)}")
        return pd.DataFrame(columns=['profit', 'trades', 'winning_trades', 'withdrawals', 'rebates', 'deposits']) 