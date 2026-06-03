import numpy as np
import gspread
from google.auth import default

# Define the list of columns to display
columns_to_display = [
    'Player', 'Team', 'Opponent', 'Position', 'Status', 'FPts', 'FP/G',
    'p_game', 'IP_per_Game', 'ERA', 'pitching_score', 'command_score',
    'whiff_percent', 'bb_percent', 'meatball_percent', 'pitching_score_2024', 'command_score_2024',
    'whiff_percent_2024', 'bb_percent_2024', 'meatball_percent_2024'
]

# Subset the joined DataFrame
df_to_write = streaming_pitchers_joined[columns_to_display]

# Replace infinite and NaN values so they're JSON‐compliant
df_to_write = df_to_write.replace([np.inf, -np.inf], np.nan).fillna("")

# Convert to list of lists (header + rows)
data = [df_to_write.columns.tolist()] + df_to_write.values.tolist()

# Authenticate (if not already) and open your spreadsheet
creds, _ = default()
gc = gspread.authorize(creds)

spreadsheet_name = "Fantasy Baseball 2025"
spreadsheet = gc.open(spreadsheet_name)

# Open or create the worksheet "Streaming Pitcher Analytics"
worksheet_title = "Streaming Pitcher Analytics"
try:
    worksheet = spreadsheet.worksheet(worksheet_title)
except gspread.exceptions.WorksheetNotFound:
    worksheet = spreadsheet.add_worksheet(title=worksheet_title, rows="1000", cols="20")

# Clear any existing data and write the new data starting at A1
worksheet.clear()
worksheet.update(values=data, range_name="A1")
