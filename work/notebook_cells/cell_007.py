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
# Function to Compute and Standardize Scores
# ----------------------------------------
def compute_command_and_pitching_scores(df,
                                        bb_std_col="bb_percent_std",
                                        meatball_std_col="meatball_percent_std",
                                        whiff_std_col="whiff_percent_std"):
    """
    Given a DataFrame with standardized bb, meatball, and whiff percentages,
    compute the command score and pitching score with z-score standardization.
    It returns a copy of the DataFrame with new columns added.

    The calculations are:
      - command_score_raw = -1 * (meatball_std + bb_std)
      - command_score: z-score normalization of command_score_raw
      - pitching_score_raw = command_score + whiff_std
      - pitching_score: z-score normalization of pitching_score_raw
    """
    df = df.copy()

    # Calculate command score raw and standardize it
    df['command_score_raw'] = -1 * (df[meatball_std_col] + df[bb_std_col])
    mean_command = df['command_score_raw'].mean()
    std_command  = df['command_score_raw'].std()
    df['command_score'] = (df['command_score_raw'] - mean_command) / std_command
    df.drop(columns=['command_score_raw'], inplace=True)

    # Calculate pitching score raw and standardize it
    df['pitching_score_raw'] = df['command_score'] + df[whiff_std_col]
    mean_pitching = df['pitching_score_raw'].mean()
    std_pitching  = df['pitching_score_raw'].std()
    df['pitching_score'] = (df['pitching_score_raw'] - mean_pitching) / std_pitching
    df.drop(columns=['pitching_score_raw'], inplace=True)

    # Optional: Round all standardized and score columns to 2 decimals
    std_columns   = [col for col in df.columns if col.endswith('_std')]
    score_columns = ['command_score', 'pitching_score']
    cols_to_round = list(set(std_columns + score_columns))
    df[cols_to_round] = df[cols_to_round].round(2)

    return df

# ----------------------------------------
# Apply Score Computation to Both Datasets
# ----------------------------------------
# Assume pitcher_baseball_savant and pitcher_2024_data DataFrames are already defined.
pitcher_baseball_savant = compute_command_and_pitching_scores(pitcher_baseball_savant)
pitcher_2024_data      = compute_command_and_pitching_scores(pitcher_2024_data)

# ----------------------------------------
# Plotting (using the processed pitcher_baseball_savant)
# ----------------------------------------
# Scatterplot 1: bb_percent_std vs meatball_percent_std
fig1 = px.scatter(
    pitcher_baseball_savant,
    x="bb_percent_std",
    y="meatball_percent_std",
    hover_name="player_name",
    hover_data={
        "bb_percent": True,
        "meatball_percent": True,
        "bb_percent_std": False,
        "meatball_percent_std": False
    },
    title="Scatterplot of bb_percent_std vs meatball_percent_std"
)
fig1.show()

# Scatterplot 2: command_score vs whiff_percent_std
fig2 = px.scatter(
    pitcher_baseball_savant,
    x="command_score",
    y="whiff_percent_std",
    hover_name="player_name",
    hover_data={
        "whiff_percent": True,
        "meatball_percent": True,
        "bb_percent": True,
        "command_score": False,
        "whiff_percent_std": False
    },
    title="Scatterplot: Command Score vs Whiff Percent (Standardized)"
)
fig2.update_layout(width=600, height=600)
fig2.show()


# ----------------------------------------
# Calculate IP_per_Game for pitcher_baseball_savant
# ----------------------------------------
pitcher_baseball_savant['IP_per_Game'] = (
    pd.to_numeric(pitcher_baseball_savant['p_formatted_ip'], errors='coerce') /
    pd.to_numeric(pitcher_baseball_savant['p_game'], errors='coerce')
).round(1)

# ----------------------------------------
# Prepare 2024 Data for Merging
# ----------------------------------------
# Create a standardized player name for merging in the 2024 dataset
pitcher_2024_data['player_name'] = (
    pitcher_2024_data['first_name'].astype(str) + " " +
    pitcher_2024_data['last_name'].astype(str)
)
pitcher_2024_data['player_name_standard'] = (
    pitcher_2024_data['player_name'].apply(standardize_string)
)

# Select and rename the necessary columns with a _2024 suffix for clarity
cols_to_join = ['player_name_standard', 'pitching_score', 'command_score',
                'whiff_percent', 'bb_percent', 'meatball_percent']
pitcher_2024_subset = pitcher_2024_data[cols_to_join].copy()
pitcher_2024_subset.rename(columns={
    'pitching_score': 'pitching_score_2024',
    'command_score': 'command_score_2024',
    'whiff_percent': 'whiff_percent_2024',
    'bb_percent': 'bb_percent_2024',
    'meatball_percent': 'meatball_percent_2024'
}, inplace=True)

# ----------------------------------------
# Standardize Player Names in current_roster, all_players, and streaming_pitchers
# ----------------------------------------
for df in (current_roster, all_players, streaming_pitchers):
    df['Player_standard'] = df['Player'].astype(str).apply(standardize_string)

# ----------------------------------------
# Filter for Pitchers in Roster and Free Agents
# ----------------------------------------
current_roster_pitchers = current_roster[current_roster['Eligible'].isin(['SP', 'RP'])].copy()
all_players_pitchers = all_players[all_players['Position'].isin(['SP', 'RP'])].copy()

# ----------------------------------------
# 10. RENAME STATS IN current_roster_pitchers
# ----------------------------------------
rename_dict = {
    'AB':'IP', 'H':'W', 'R':'L', '1B':'SV', '2B':'BS', '3B':'HLD', 'HR':'CG',
    'RBI':'H', 'BB':'ER', 'SO':'BB', 'SB':'K', 'CS':'ERA', 'HBP':'BK',
    'SH':'NH', 'GIDP':'PG', 'GP':'QA3'
}
current_roster_pitchers.rename(columns=rename_dict, inplace=True)

# ----------------------------------------
# Merge 2024 Data and baseball savant data onto Free Agents, Roster, and Streaming DataFrames
# ----------------------------------------
# For free agents:
all_players_pitchers_joined = pd.merge(
    all_players_pitchers,
    pitcher_baseball_savant,
    how='left',
    left_on='Player_standard',
    right_on='player_name_standard'
)
all_players_pitchers_joined = pd.merge(
    all_players_pitchers_joined,
    pitcher_2024_subset,
    how='left',
    left_on='Player_standard',
    right_on='player_name_standard'
)

# For current roster pitchers, ensure pitcher_baseball_savant has proper naming columns first:
pitcher_baseball_savant['player_name'] = (
    pitcher_baseball_savant['first_name'].astype(str) + " " +
    pitcher_baseball_savant['last_name'].astype(str)
)
pitcher_baseball_savant['player_name_standard'] = pitcher_baseball_savant['player_name'].apply(standardize_string)
current_roster_pitchers_joined = pd.merge(
    current_roster_pitchers,
    pitcher_baseball_savant,
    how='left',
    left_on='Player_standard',
    right_on='player_name_standard'
)
current_roster_pitchers_joined = pd.merge(
    current_roster_pitchers_joined,
    pitcher_2024_subset,
    how='left',
    left_on='Player_standard',
    right_on='player_name_standard'
)

# For streaming pitchers:
streaming_pitchers_joined = pd.merge(
    streaming_pitchers,
    pitcher_baseball_savant,
    how='left',
    left_on='Player_standard',
    right_on='player_name_standard'
)
streaming_pitchers_joined = pd.merge(
    streaming_pitchers_joined,
    pitcher_2024_subset,
    how='left',
    left_on='Player_standard',
    right_on='player_name_standard'
)
