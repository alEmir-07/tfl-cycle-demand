"""Project-wide settings and paths."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
FIGURES = ROOT / "reports" / "figures"
DB_PATH = PROCESSED / "tfl_cycles.db"

BUCKET = "https://s3-eu-west-1.amazonaws.com/cycling.data.tfl.gov.uk/"

# 12 complete months: 1 Jun 2025 - 31 May 2026 (latest data TfL had published as of Nov 2026).
# Since 2022 TfL publishes fortnightly extracts, not weekly.
JOURNEY_FILES = [
    "421JourneyDataExtract01Jun2025-15Jun2025.csv",
    "422JourneyDataExtract15Jun2025-30Jun2025.csv",
    "423JourneyDataExtract01Jul2025-15Jul2025.csv",
    "424JourneyDataExtract16Jul2025-31Jul2025.csv",
    "425JourneyDataExtract01Aug2025-15Aug2025.csv",
    "426JourneyDataExtract16Aug2025-31Aug2025.csv",
    "427JourneyDataExtract01Sep2025-15Sep2025.csv",
    "428JourneyDataExtract16Sep2025-30Sep2025.csv",
    "429JourneyDataExtract01Oct2025-15Oct2025.csv",
    "430JourneyDataExtract16Oct2025-31Oct2025.csv",
    "431JourneyDataExtract01Nov2025-15Nov2025.csv",
    "432JourneyDataExtract16Nov2025-30Nov2025.csv",
    "433JourneyDataExtract01Dec2025-15Dec2025.csv",
    "434JourneyDataExtract16Dec2025-31Dec2025.csv",
    "435JourneyDataExtract01Jan2026-15Jan2026.csv",
    "436JourneyDataExtract16Jan2026-31Jan2026.csv",
    "437JourneyDataExtract01Feb2026-14Feb2026.csv",
    "438JourneyDataExtract15Feb2026-28Feb2026.csv",
    "439JourneyDataExtract01Mar2026-15Mar2026.csv",
    "440JourneyDataExtract15Mar2026-31Mar2026.csv",
    "441JourneyDataExtract01Apr2026-15Apr2026.csv",
    "442JourneyDataExtract16Apr2026-30Apr2026.csv",
    "443JourneyDataExtract01May2026-16May2026.csv",
    "444JourneyDataExtract17May2026-31May2026.csv",
]
START_DATE = "2025-06-01"
END_DATE = "2026-05-31"

# Central London (Trafalgar Sq) - weather is close to uniform across the docking network
LONDON_LAT, LONDON_LON = 51.5074, -0.1278

# Cleaning thresholds
MIN_DURATION_S = 60            # under 1 minute: false starts / immediate re-docks
MAX_DURATION_S = 3 * 60 * 60   # over 3 hours: lost, stolen or mis-docked bikes

N_STATIONS = 40                # model the top-40 busiest start stations
TEST_START = "2026-04-01"      # train Jun 2025 - Mar 2026, test Apr-May 2026
