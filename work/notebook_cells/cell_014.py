# Define the list of columns to display
columns_to_display = [
    'Player', 'Eligible', 'Status', 'Fantasy Points', 'Average Fantasy Points per Game',
    'GP', 'AB_per_Game',
    'hitter_score', 'batters_eye_score',
    'barrel_batted_rate', 'oz_swing_percent', 'meatball_swing_percent', 'hitter_score_2024', 'batters_eye_score_2024',
    'barrel_batted_rate_2024', 'oz_swing_percent_2024', 'meatball_swing_percent_2024'
]

# Create a DataFrame with only the desired columns
df_to_write = current_roster_hitters_joined[columns_to_display]

# Replace problematic float values (inf, -inf, NaN) with empty strings
import numpy as np
df_to_write = df_to_write.replace([np.inf, -np.inf], np.nan).fillna("")

# Convert the DataFrame to a list of lists, including the header as the first row
data = [df_to_write.columns.tolist()] + df_to_write.values.tolist()

# Import gspread and authenticate (assuming you've already run your auth code)
import gspread
from google.auth import default

creds, _ = default()
gc = gspread.authorize(creds)

# Open the spreadsheet (make sure the name matches exactly)
spreadsheet_name = "Fantasy Baseball 2025"
spreadsheet = gc.open(spreadsheet_name)

# Open (or create) the worksheet "Current Roster - Pitchers"
worksheet_title = "Current Roster - Hitters"
try:
    worksheet = spreadsheet.worksheet(worksheet_title)
except gspread.exceptions.WorksheetNotFound:
    # Create worksheet if it doesn't exist (with a reasonable number of rows and columns)
    worksheet = spreadsheet.add_worksheet(title=worksheet_title, rows="1000", cols="20")

# Clear the worksheet (delete any existing data)
worksheet.clear()

# Update the worksheet: using named arguments to specify values and range_name (starting at A1)
worksheet.update(values=data, range_name="A1")
