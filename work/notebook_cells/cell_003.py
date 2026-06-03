import pandas as pd
import gspread
from google.colab import auth
from google.auth import default

# Authenticate and authorize access to your Google account
auth.authenticate_user()
creds, _ = default()
gc = gspread.authorize(creds)

# Open the spreadsheet by its name
spreadsheet_name = 'Fantasy Baseball 2025'
try:
    spreadsheet = gc.open(spreadsheet_name)
except Exception as e:
    print(f"Error accessing spreadsheet {spreadsheet_name}: {e}")
    raise

def get_sheet_df(sheet_name):
    """
    Get data from a worksheet, using the first row as the header.
    """
    worksheet = spreadsheet.worksheet(sheet_name)
    data = worksheet.get_all_values()
    if not data:
        raise ValueError(f"No data found in worksheet '{sheet_name}'")
    df = pd.DataFrame(data[1:], columns=data[0])
    return df

def get_current_roster_df(sheet_name):
    """
    Get data from the Current Roster worksheet.
    Drops the first row so that row 2 becomes the header.
    """
    worksheet = spreadsheet.worksheet(sheet_name)
    data = worksheet.get_all_values()
    if len(data) < 2:
        raise ValueError(f"Not enough rows in worksheet '{sheet_name}' to skip the first row.")
    df = pd.DataFrame(data[2:], columns=data[1])
    return df

# Read each worksheet into a DataFrame
try:
    pitcher_baseball_savant = get_sheet_df('Pitcher Baseball Savant')
    hitter_baseball_savant = get_sheet_df('Hitter Baseball Savant')
    all_players = get_sheet_df('All Players')
    current_roster = get_current_roster_df('Current Roster')
    streaming_pitchers = get_sheet_df('Streamers')
    pitcher_2024_data = get_sheet_df('Pitcher 2024 Data')
    hitter_2024_data = get_sheet_df('Hitter 2024 Data')
except Exception as e:
    print("An error occurred while reading the sheets:", e)
    raise

# Display the first few rows of each DataFrame to verify
print("Pitcher Baseball Savant:")
print(pitcher_baseball_savant.head(), "\n")

print("Hitter Baseball Savant:")
print(hitter_baseball_savant.head(), "\n")

print("All Players:")
print(all_players.head(), "\n")

print("Current Roster:")
print(current_roster.head(), "\n")

print("Streamers (streaming_pitchers):")
print(streaming_pitchers.head(), "\n")

print("Pitcher 2024 Data:")
print(pitcher_2024_data.head(), "\n")

print("Hitter 2024 Data:")
print(hitter_2024_data.head())
