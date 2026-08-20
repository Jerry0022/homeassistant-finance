"""Constants for the Finance integration."""

DOMAIN = "finance_dashboard"
PLATFORMS = ["sensor", "number", "select"]

# Version — must match manifest.json and companion config.yaml
VERSION = "0.15.1"

# Panel
PANEL_URL_PATH = "finance-dashboard"
PANEL_TITLE = "Finance"
PANEL_ICON = "mdi:finance"
PANEL_COMPONENT_NAME = "finance-dashboard-panel"
PANEL_MODULE_PATH = f"/api/{DOMAIN}/static/finance-dashboard-panel.js?v={VERSION}"

# Storage keys — all sensitive data stored in HA .storage/
STORAGE_KEY_CREDENTIALS = f"{DOMAIN}_credentials"
STORAGE_KEY_TOKENS = f"{DOMAIN}_tokens"
STORAGE_KEY_AUDIT = f"{DOMAIN}_audit_log"
# Institution catalog cache — the /aspsps bank list.  Cached so the setup
# wizard still offers a bank list when Enable Banking is unreachable.
STORAGE_KEY_INSTITUTIONS = f"{DOMAIN}_institutions"

# Backoff after HTTP 429.  Enable Banking documents that background
# fetches should resume after 6 hours; blocking until midnight punished
# a 07:00 rate limit with a whole lost day.  Attended calls (PSU headers
# present) are exempt from the ASPSP 4/day rule entirely, so a 429 there
# is a transient upstream condition and gets a short pause instead.
RATE_LIMIT_BACKOFF_HOURS = 6
RATE_LIMIT_ATTENDED_BACKOFF_MINUTES = 15
# Catalog entries older than this are refreshed from the API on next open.
INSTITUTION_CACHE_TTL_HOURS = 24
STORAGE_VERSION = 1

# Enable Banking
ENABLEBANKING_BASE_URL = "https://api.enablebanking.com"
# Sandbox uses a different app registration
ENABLEBANKING_SANDBOX_URL = "https://api.enablebanking.com"
TOKEN_MAX_AGE_DAYS = 90  # Force re-auth after 90 days (our own policy)
SESSION_MAX_DAYS = 180  # Enable Banking session validity
SESSION_TIMEOUT_MINUTES = 30
ENABLEBANKING_RATE_LIMIT_DAILY = 4

# Transaction categorization
CATEGORY_HOUSING = "housing"
CATEGORY_FOOD = "food"
CATEGORY_TRANSPORT = "transport"
CATEGORY_INSURANCE = "insurance"
CATEGORY_SUBSCRIPTIONS = "subscriptions"
CATEGORY_LOANS = "loans"
CATEGORY_UTILITIES = "utilities"
CATEGORY_INCOME = "income"
CATEGORY_TRANSFERS = "transfers"
CATEGORY_OTHER = "other"

DEFAULT_CATEGORIES = [
    CATEGORY_HOUSING,
    CATEGORY_FOOD,
    CATEGORY_TRANSPORT,
    CATEGORY_INSURANCE,
    CATEGORY_SUBSCRIPTIONS,
    CATEGORY_LOANS,
    CATEGORY_UTILITIES,
    CATEGORY_INCOME,
    CATEGORY_TRANSFERS,
    CATEGORY_OTHER,
]

# Categorization rules — keyword-based auto-detection
# These are default patterns; users can customize via UI
CATEGORIZATION_RULES = {
    CATEGORY_HOUSING: [
        "miete",
        "rent",
        "wohnung",
        "hausgeld",
        "nebenkosten",
    ],
    CATEGORY_FOOD: [
        "rewe",
        "edeka",
        "aldi",
        "lidl",
        "hellofresh",
        "lieferando",
        "uber eats",
        "supermarkt",
        "lebensmittel",
        "restaurant",
    ],
    CATEGORY_TRANSPORT: [
        "deutschland ticket",
        "deutschlandticket",
        "db ",
        "bahn",
        "tankstelle",
        "shell",
        "aral",
        "uber",
        "taxi",
    ],
    CATEGORY_INSURANCE: [
        "versicherung",
        "insurance",
        "haftpflicht",
        "rechtsschutz",
        "krankenversicherung",
        "tk ",
        "aok",
        "barmer",
    ],
    CATEGORY_SUBSCRIPTIONS: [
        "netflix",
        "spotify",
        "amazon prime",
        "disney",
        "xbox",
        "google one",
        "icloud",
        "youtube premium",
    ],
    CATEGORY_LOANS: [
        "kredit",
        "tilgung",
        "darlehen",
        "loan",
        "finanzierung",
    ],
    CATEGORY_UTILITIES: [
        "strom",
        "gas",
        "wasser",
        "fernwärme",
        "telekom",
        "vodafone",
        "o2",
        "rundfunkbeitrag",
        "gez",
    ],
    CATEGORY_INCOME: [
        "gehalt",
        "lohn",
        "salary",
        "vergütung",
        "überweisung",
    ],
    CATEGORY_TRANSFERS: [
        "umbuchung",
        "übertrag",
        "transfer",
        "sparplan",
    ],
}

# Services
SERVICE_REFRESH_ACCOUNTS = "refresh_accounts"
SERVICE_REFRESH_TRANSACTIONS = "refresh_transactions"
SERVICE_CATEGORIZE = "categorize_transactions"
SERVICE_GET_BALANCE = "get_balance"
SERVICE_GET_SUMMARY = "get_monthly_summary"
SERVICE_SET_BUDGET_LIMIT = "set_budget_limit"
SERVICE_EXPORT_CSV = "export_csv"

# Audit log
AUDIT_EVENT_AUTH = "authentication"
AUDIT_EVENT_TOKEN_REFRESH = "token_refresh"
AUDIT_EVENT_DATA_ACCESS = "data_access"
AUDIT_EVENT_CONFIG_CHANGE = "config_change"
AUDIT_EVENT_ERROR = "error"
AUDIT_MAX_ENTRIES = 1000

# Transfer chain detection
TRANSFER_AMOUNT_TOLERANCE = 0.50  # EUR tolerance for fee differences
TRANSFER_TIME_WINDOW_DAYS = 3  # ±days for date matching
TRANSFER_REFUND_WINDOW_DAYS = 14  # Lookback for refund matching
TRANSFER_AUTO_CONFIDENCE = 0.60  # Auto-link threshold (0.0-1.0)
STORAGE_KEY_TRANSFER_OVERRIDES = f"{DOMAIN}_transfer_overrides"

# Refund keywords — transaction text must contain one for refund detection
REFUND_KEYWORDS = [
    "storno",
    "gutschrift",
    "refund",
    "rueckzahlung",
    "rückzahlung",
    "erstattung",
    "retoure",
    "reversal",
    "chargeback",
]

# Household model
SPLIT_MODEL_POOLED_EQUAL = "pooled_equal"
SPLIT_MODEL_EQUAL = "equal"
SPLIT_MODEL_PROPORTIONAL = "proportional"
SPLIT_MODEL_CUSTOM = "custom"

SPLIT_MODELS = [
    SPLIT_MODEL_POOLED_EQUAL,
    SPLIT_MODEL_EQUAL,
    SPLIT_MODEL_PROPORTIONAL,
    SPLIT_MODEL_CUSTOM,
]

# The household spreadsheet this integration replaces uses the pooled model:
# shared costs are paid from the POOLED net income, the remainder is split
# equally, and each person then pays their own individual fixed costs.
DEFAULT_SPLIT_MODEL = SPLIT_MODEL_POOLED_EQUAL

# Budget plan — the migrated spreadsheet model (cost positions + income plan).
# Amounts live in HA .storage/ only; never in git.
STORAGE_KEY_BUDGET_PLAN = f"{DOMAIN}_budget_plan"

# Cost position ownership: a position belongs to a person by NAME, or is shared.
# Ownership is a property of the position, not of the account it is debited from.
OWNER_SHARED = "__shared__"

# Cost position kinds
POSITION_KIND_FIXED = "fixed"  # a recurring fixed debit
POSITION_KIND_BUFFER = "buffer"  # budgeted variable cost: units x unit price
POSITION_KINDS = [POSITION_KIND_FIXED, POSITION_KIND_BUFFER]

# Demo mode
SERVICE_TOGGLE_DEMO = "toggle_demo"

# Budget plan services
SERVICE_IMPORT_SPREADSHEET = "import_spreadsheet"
SERVICE_GET_TRANSFER_PLAN = "get_transfer_plan"
SERVICE_SET_COST_POSITION = "set_cost_position"
SERVICE_DELETE_COST_POSITION = "delete_cost_position"

# Transfer plan — a pass-through account must net to zero. Tolerance in EUR
# absorbs rounding across per-person shares.
TRANSFER_PLAN_ZERO_TOLERANCE = 0.02

# Benchmark metrics — which planned cost categories form the numerator of each
# comparison against the German average. Mirrors the spreadsheet's definitions:
# housing counted rent plus utilities together, food counted both buffers.
BENCHMARK_METRIC_SOURCES = {
    "housing": [CATEGORY_HOUSING, CATEGORY_UTILITIES],
    "food": [CATEGORY_FOOD],
    "loans": [CATEGORY_LOANS],
    "insurance": [CATEGORY_INSURANCE],
    "transport": [CATEGORY_TRANSPORT],
}

# Water consumption cannot be derived from banking data — only the utility
# statement knows it. Kept as a manual option so the spreadsheet's water
# comparison survives the migration. Value is a multiple of the German average.
OPT_WATER_RATIO = "water_consumption_ratio"
DEFAULT_WATER_BENCHMARK = 1.0

# Balance selection. Enable Banking returns ISO 20022 balance-type codes, not
# the GoCardless camelCase names. A priority list built from camelCase names
# never matches a real response and silently falls through to "whichever
# balance the bank listed first" — which can be an expected or forward-available
# balance rather than the booked one. Both spellings are listed so demo data
# (camelCase) and live data (ISO) resolve identically.
BALANCE_TYPE_PRIORITY = [
    "CLBD",  # closing booked — the authoritative booked balance
    "closingBooked",
    "ITBD",  # interim booked
    "interimBooked",
    "CLAV",  # closing available
    "closingAvailable",
    "ITAV",  # interim available
    "interimAvailable",
    "OPBD",  # opening booked
    "PRCD",  # previously closed booked
    "XPCD",  # expected
    "FWAV",  # forward available
    "VALU",  # value date
    "OTHR",
    "INFO",
]

# Daily scheduled refresh. Exactly one live fetch per day: a quarter of the
# 4/day/ASPSP budget, leaving three manual refreshes. Not polling — a single
# fixed-time trigger.
OPT_DAILY_REFRESH = "daily_refresh_enabled"
OPT_DAILY_REFRESH_HOUR = "daily_refresh_hour"
OPT_DAILY_REFRESH_MINUTE = "daily_refresh_minute"
DEFAULT_DAILY_REFRESH = True
DEFAULT_DAILY_REFRESH_HOUR = 6
DEFAULT_DAILY_REFRESH_MINUTE = 30

# Attended refresh on panel open.  Opening the dashboard IS a user session,
# so the call carries PSU headers and is exempt from the unattended 4/day cap
# (PSD2 RTS Art. 36(5)(b)).  Fires at most once per panel mount and only when
# the cache is older than the threshold — a user action, never an interval.
OPT_AUTO_REFRESH_ON_OPEN = "auto_refresh_on_open"
OPT_AUTO_REFRESH_MAX_AGE_MINUTES = "auto_refresh_max_age_minutes"
DEFAULT_AUTO_REFRESH_ON_OPEN = True
DEFAULT_AUTO_REFRESH_MAX_AGE_MINUTES = 60
