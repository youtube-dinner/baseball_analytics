# Define the list of columns to display
columns_to_display = [
    'Player', 'Position', 'Status', 'FPts', 'FP/G',
    'GP', 'AB_per_Game',
    'hitter_score', 'batters_eye_score',
    'barrel_batted_rate', 'oz_swing_percent', 'meatball_swing_percent', 'hitter_score_2024', 'batters_eye_score_2024',
    'barrel_batted_rate_2024', 'oz_swing_percent_2024', 'meatball_swing_percent_2024'
]

import numpy as np
import pandas as pd

# Keep only desired columns
df_to_write = all_players_hitters_joined[columns_to_display].copy()

# ✅ Filter rows where hitter_score is present (not NaN/inf/empty)
hs_numeric = pd.to_numeric(df_to_write['hitter_score'], errors='coerce')
df_to_write = df_to_write[hs_numeric.notna() & np.isfinite(hs_numeric)]

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

# Open or create the worksheet "Hitter Analytics"
worksheet_title = "Hitter Analytics"
try:
    worksheet = spreadsheet.worksheet(worksheet_title)
except gspread.exceptions.WorksheetNotFound:
    worksheet = spreadsheet.add_worksheet(title=worksheet_title, rows="1000", cols="20")

# Clear any existing data and write the new data starting at A1
worksheet.clear()
worksheet.update(values=data, range_name="A1")
