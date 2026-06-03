import pandas as pd
import plotly.express as px
import re
import unicodedata
import numpy as np
import gspread
from google.colab import auth
from google.auth import default

# ----------------------------------------
# Helper Function to Standardize Strings
# ----------------------------------------
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

# ----------------------------------------
# Function to Compute and Standardize Batter Scores
# ----------------------------------------
def compute_batters_scores(df,
                           oz_swing_col="oz_swing_percent",
                           meatball_col="meatball_swing_percent",
                           barrel_col="barrel_batted_rate"):
    """
    Given a DataFrame with raw hitter metrics, compute and standardize:
      - oz_take: defined as 100 - oz_swing_percent
      - Standardized values for:
           oz_take (oz_take_std) and meatball_swing_percent (meatball_swing_std)

      - batters_eye_score_raw: the sum of oz_take_std and meatball_swing_std,
        which is then standardized to yield batters_eye_score.

      - Standardized barrel_batted_rate (barrel_std)

      - hitter_score_raw: the sum of batters_eye_score and barrel_std,
        which is then standardized to yield hitter_score.

      Finally, all standardized and score columns are rounded to 2 decimals.
    """
    df = df.copy()

    # Calculate oz_take as 100 - oz_swing_percent
    df['oz_take'] = 100 - df[oz_swing_col]
    df['oz_take_std'] = (df['oz_take'] - df['oz_take'].mean()) / df['oz_take'].std()

    # Standardize meatball_swing_percent
    df['meatball_swing_std'] = (df[meatball_col] - df[meatball_col].mean()) / df[meatball_col].std()

    # Compute batters_eye_score_raw and then standardize it
    df['batters_eye_score_raw'] = df['oz_take_std'] + df['meatball_swing_std']
    mean_eye = df['batters_eye_score_raw'].mean()
    std_eye = df['batters_eye_score_raw'].std()
    df['batters_eye_score'] = (df['batters_eye_score_raw'] - mean_eye) / std_eye
    df.drop(columns=['batters_eye_score_raw'], inplace=True)

    # Standardize barrel_batted_rate
    df['barrel_std'] = (df[barrel_col] - df[barrel_col].mean()) / df[barrel_col].std()

    # Compute hitter_score_raw and then standardize it
    df['hitter_score_raw'] = df['batters_eye_score'] + df['barrel_std']
    mean_hitter = df['hitter_score_raw'].mean()
    std_hitter = df['hitter_score_raw'].std()
    df['hitter_score'] = (df['hitter_score_raw'] - mean_hitter) / std_hitter
    df.drop(columns=['hitter_score_raw'], inplace=True)

    # Optional: Round standardized and score columns to 2 decimals
    std_columns   = [col for col in df.columns if col.endswith('_std')]
    score_columns = ['batters_eye_score', 'hitter_score']
    cols_to_round = list(set(std_columns + score_columns))
    df[cols_to_round] = df[cols_to_round].round(2)

    return df

# ----------------------------------------
# Apply Score Computation to Both Datasets
# ----------------------------------------
# Assume hitter_baseball_savant and hitter_2024_data DataFrames are already defined.
hitter_baseball_savant = compute_batters_scores(hitter_baseball_savant)
hitter_2024_data      = compute_batters_scores(hitter_2024_data)

# ----------------------------------------
# Plotting (using the processed hitter_baseball_savant)
# ----------------------------------------
# Scatterplot 1: oz_take_std vs. meatball_swing_std
fig1 = px.scatter(
    hitter_baseball_savant,
    x="oz_take_std",
    y="meatball_swing_std",
    hover_name="player_name",
    hover_data={
        "oz_swing_percent": True,
        "meatball_swing_percent": True,
        "oz_take_std": False,
        "meatball_swing_std": False
    },
    title="Scatterplot of oz_take_std vs. meatball_swing_std"
)
fig1.show()

# Scatterplot 2: batters_eye_score vs. barrel_std
fig2 = px.scatter(
    hitter_baseball_savant,
    x="batters_eye_score",
    y="barrel_std",
    hover_name="player_name",
    hover_data={
        "barrel_batted_rate": True,
        "meatball_swing_percent": True,
        "oz_swing_percent": True,
        "batters_eye_score": False,
        "barrel_std": False
    },
    title="Scatterplot: Batters' Eye Score vs. Barrel (Standardized)"
)
fig2.update_layout(width=600, height=600)
fig2.show()

# ----------------------------------------
# Prepare 2024 Data for Merging (Hitters)
# ----------------------------------------
# Create a standardized player name for merging in the 2024 hitter dataset
hitter_2024_data['player_name'] = (
    hitter_2024_data['first_name'].astype(str) + " " +
    hitter_2024_data['last_name'].astype(str)
)
hitter_2024_data['player_name_standard'] = hitter_2024_data['player_name'].apply(standardize_string)

# Select and rename the necessary columns with a _2024 suffix for clarity.
# Here we assume that the hitter dataset contains:
#   - hitter_score and batters_eye_score (computed via compute_batters_scores)
#   - barrel_batted_rate, oz_swing_percent, and meatball_swing_percent (the raw metrics)
cols_to_join = ['player_name_standard', 'hitter_score', 'batters_eye_score',
                'barrel_batted_rate', 'oz_swing_percent', 'meatball_swing_percent']
hitter_2024_subset = hitter_2024_data[cols_to_join].copy()
hitter_2024_subset.rename(columns={
    'hitter_score': 'hitter_score_2024',
    'batters_eye_score': 'batters_eye_score_2024',
    'barrel_batted_rate': 'barrel_batted_rate_2024',
    'oz_swing_percent': 'oz_swing_percent_2024',
    'meatball_swing_percent': 'meatball_swing_percent_2024'
}, inplace=True)

# ----------------------------------------
# Standardize Player Names in current_roster, all_players, and streaming_hitters
# ----------------------------------------
for df in (current_roster, all_players):
    df['Player_standard'] = df['Player'].astype(str).apply(standardize_string)

# ----------------------------------------
# Filter for Hitters in Roster and Free Agents
# ----------------------------------------
# Instead of filtering for pitchers (i.e. 'SP', 'RP'), we filter them out to create hitter datasets.
current_roster_hitters = current_roster[~current_roster['Eligible'].isin(['SP', 'RP'])].copy()
all_players_hitters = all_players[~all_players['Position'].isin(['SP', 'RP'])].copy()

# ----------------------------------------
# Merge 2024 Data and hitter_baseball_savant Data onto Free Agents and Roster DataFrames (Hitters)
# ----------------------------------------

# For free agents:
all_players_hitters_joined = pd.merge(
    all_players_hitters,
    hitter_baseball_savant,
    how='left',
    left_on='Player_standard',
    right_on='player_name_standard'
)
all_players_hitters_joined = pd.merge(
    all_players_hitters_joined,
    hitter_2024_subset,
    how='left',
    left_on='Player_standard',
    right_on='player_name_standard'
)

# For current roster hitters, ensure hitter_baseball_savant has proper naming columns first:
hitter_baseball_savant['player_name'] = (
    hitter_baseball_savant['first_name'].astype(str) + " " +
    hitter_baseball_savant['last_name'].astype(str)
)
hitter_baseball_savant['player_name_standard'] = hitter_baseball_savant['player_name'].apply(standardize_string)

current_roster_hitters_joined = pd.merge(
    current_roster_hitters,
    hitter_baseball_savant,
    how='left',
    left_on='Player_standard',
    right_on='player_name_standard'
)
current_roster_hitters_joined = pd.merge(
    current_roster_hitters_joined,
    hitter_2024_subset,
    how='left',
    left_on='Player_standard',
    right_on='player_name_standard'
)
