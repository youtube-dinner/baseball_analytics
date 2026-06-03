import pandas as pd
import unicodedata
import re

# Function to standardize strings
def standardize_string(s):
    """
    Normalize a string by:
      - Removing trailing 'Jr.' or 'Jr' (case-insensitive)
      - Removing trailing roman numeral suffixes (II, III, IV, or V)
      - Removing accents
      - Converting to lowercase
    """
    # Remove trailing 'Jr.' or 'Jr' if present
    s = re.sub(r'\s+Jr\.?$', '', s, flags=re.IGNORECASE)
    # Remove trailing roman numeral suffixes (II, III, IV, or V)
    s = re.sub(r'\s+(II|III|IV|V)$', '', s, flags=re.IGNORECASE)
    # Normalize the string by removing accents and converting to ASCII
    normalized = unicodedata.normalize("NFKD", s)
    ascii_str = normalized.encode("ASCII", "ignore").decode("utf-8")
    return ascii_str.lower()

# Columns to standardize
pitcher_columns_to_standardize = ["bb_percent", "meatball_percent", "whiff_percent"]
hitter_columns_to_standardize = ["barrel_batted_rate", "oz_swing_percent", "meatball_swing_percent"]

# Standardization function for numerical columns
def standardize_numeric(df, columns):
    for col in columns:
        df[col] = pd.to_numeric(df[col], errors='coerce')
        mean_val = df[col].mean()
        std_val = df[col].std()
        df[col + '_std'] = (df[col] - mean_val) / std_val

# Apply standardization to pitcher_baseball_savant
standardize_numeric(pitcher_baseball_savant, pitcher_columns_to_standardize)
pitcher_baseball_savant['player_name'] = pitcher_baseball_savant['first_name'].astype(str) + " " + pitcher_baseball_savant['last_name'].astype(str)
pitcher_baseball_savant['player_name_standard'] = pitcher_baseball_savant['player_name'].apply(standardize_string)

# Apply standardization to hitter_baseball_savant
standardize_numeric(hitter_baseball_savant, hitter_columns_to_standardize)
hitter_baseball_savant['player_name'] = hitter_baseball_savant['first_name'].astype(str) + " " + hitter_baseball_savant['last_name'].astype(str)
hitter_baseball_savant['player_name_standard'] = hitter_baseball_savant['player_name'].apply(standardize_string)

# Apply standardization to pitcher_2024_data
standardize_numeric(pitcher_2024_data, pitcher_columns_to_standardize)
pitcher_2024_data['player_name'] = pitcher_2024_data['first_name'].astype(str) + " " + pitcher_2024_data['last_name'].astype(str)
pitcher_2024_data['player_name_standard'] = pitcher_2024_data['player_name'].apply(standardize_string)

# Apply standardization to hitter_2024_data
standardize_numeric(hitter_2024_data, hitter_columns_to_standardize)
hitter_2024_data['player_name'] = hitter_2024_data['first_name'].astype(str) + " " + hitter_2024_data['last_name'].astype(str)
hitter_2024_data['player_name_standard'] = hitter_2024_data['player_name'].apply(standardize_string)
