# prompt: add a column called current_date to pitcher_baseball_savant and hitter_baseball_savant and push them to that google sheet in the tabs Pitching Trends Baseball Savant and Hitting Trends Baseball Savant respectively. Don't overwrite if there's data already there, put at the end

from datetime import date

# Add the current date column to the DataFrames
today = date.today().strftime("%Y-%m-%d")
pitcher_baseball_savant['current_date'] = today
hitter_baseball_savant['current_date'] = today

# Update the Google Sheets
def update_sheet(worksheet_name, df):
    worksheet = spreadsheet.worksheet(worksheet_name)
    # Get existing data to avoid overwriting
    existing_data = worksheet.get_all_values()

    # Convert the DataFrame to a list of lists
    new_data = df.values.tolist()

    # Append new data to the existing data
    updated_data = existing_data + new_data
    worksheet.update(f'A1', updated_data)


# Update the respective sheets with the new data
try:
  update_sheet('Pitching Trends Baseball Savant', pitcher_baseball_savant)
  update_sheet('Hitting Trends Baseball Savant', hitter_baseball_savant)
  print("Successfully updated the Google Sheets.")
except Exception as e:
  print(f"An error occurred while updating the Google Sheets: {e}")
