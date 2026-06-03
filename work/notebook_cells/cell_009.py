# Define the list of columns to display
columns_to_display = [
    'Player', 'Position', 'Status', 'FPts', 'FP/G',
    'p_game', 'IP_per_Game', 'p_era', 'pitching_score', 'command_score',
    'whiff_percent', 'bb_percent', 'meatball_percent', 'pitching_score_2024', 'command_score_2024',
    'whiff_percent_2024', 'bb_percent_2024', 'meatball_percent_2024'
]

import numpy as np
import pandas as pd

# Create a DataFrame with only the desired columns
df_to_write = all_players_pitchers_joined[columns_to_display].copy()

# ✅ Keep only rows where pitching_score is present (not NaN/inf/blank)
ps_numeric = pd.to_numeric(df_to_write['pitching_score'], errors='coerce')
df_to_write = df_to_write[ps_numeric.notna() & np.isfinite(ps_numeric)]

# Replace infinite and NaN values so they're JSON‐compliant
df_to_write = df_to_write.replace([np.inf, -np.inf], np.nan).fillna("")

# Convert to list of lists (header + rows)
data = [df_to_write.columns.tolist()] + df_to_write.values.tolist()

# Authenticate and open your spreadsheet
import gspread
from google.auth import default

creds, _ = default()
gc = gspread.authorize(creds)

spreadsheet_name = "Fantasy Baseball 2025"
spreadsheet = gc.open(spreadsheet_name)

# Open or create the worksheet "Pitcher Analytics"
worksheet_title = "Pitcher Analytics"
try:
    worksheet = spreadsheet.worksheet(worksheet_title)
except gspread.exceptions.WorksheetNotFound:
    worksheet = spreadsheet.add_worksheet(title=worksheet_title, rows="1000", cols="20")

# Clear any existing data and write the new data starting at A1
worksheet.clear()
worksheet.update(values=data, range_name="A1")
