# Define the threshold for filtering
threshold = 30

# For pitcher_baseball_savant: convert 'ab' to numeric and filter with .loc, then create an explicit copy
pitcher_baseball_savant['ab'] = pd.to_numeric(pitcher_baseball_savant['ab'], errors='coerce')
pitcher_baseball_savant = pitcher_baseball_savant.loc[pitcher_baseball_savant['ab'] >= threshold].copy()

# For hitter_baseball_savant: convert 'ab' to numeric and filter similarly
hitter_baseball_savant['ab'] = pd.to_numeric(hitter_baseball_savant['ab'], errors='coerce')
hitter_baseball_savant = hitter_baseball_savant.loc[hitter_baseball_savant['ab'] >= threshold].copy()


# Optionally, verify by printing out a few rows from each filtered dataframe.
print("Filtered Pitcher Baseball Savant (ab >= 30):")
print(pitcher_baseball_savant.head(), "\n")

print("Filtered Hitter Baseball Savant (ab >= 30):")
print(hitter_baseball_savant.head())