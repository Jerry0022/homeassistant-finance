"""Constants for the Finance Dashboard integration."""

DOMAIN = "finance_dashboard"
PLATFORMS = ["sensor", "number", "select"]

# Version — must match manifest.json and companion config.yaml
VERSION = "0.4.0"

# Panel
PANEL_URL = "/finance-dashboard"
PANEL_TITLE = "Finance Dashboard"
PANEL_ICON = "mdi:finance"
PANEL_MODULE_PATH = (
    f"/api/{DOMAIN}/static/finance-dashboard-panel.js?v={VERSION}"
)

# Storage keys — all sensitive data stored in HA .storage/
STORAGE_KEY_CREDENTIALS = f"{DOMAIN}_credentials"
STORAGE_KEY_TOKENS = f"{DOMAIN}_tokens"
STORAGE_KEY_AUDIT = f"{DOMAIN}_audit_log"
STORAGE_VERSION = 1

# GoCardless / Nordigen
GOCARDLESS_BASE_URL = "https://bankaccountdata.gocardless.com/api/v2"
TOKEN_REFRESH_INTERVAL_HOURS = 23  # Refresh before 24h expiry
TOKEN_MAX_AGE_DAYS = 90  # Force re-auth after 90 days
SESSION_TIMEOUT_MINUTES = 30

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
        "miete", "rent", "wohnung", "hausgeld", "nebenkosten",
    ],
    CATEGORY_FOOD: [
        "rewe", "edeka", "aldi", "lidl", "hellofresh", "lieferando",
        "uber eats", "supermarkt", "lebensmittel", "restaurant",
    ],
    CATEGORY_TRANSPORT: [
        "deutschland ticket", "deutschlandticket", "db ", "bahn",
        "tankstelle", "shell", "aral", "uber", "taxi",
    ],
    CATEGORY_INSURANCE: [
        "versicherung", "insurance", "haftpflicht", "rechtsschutz",
        "krankenversicherung", "tk ", "aok", "barmer",
    ],
    CATEGORY_SUBSCRIPTIONS: [
        "netflix", "spotify", "amazon prime", "disney", "xbox",
        "google one", "icloud", "youtube premium",
    ],
    CATEGORY_LOANS: [
        "kredit", "tilgung", "darlehen", "loan", "finanzierung",
    ],
    CATEGORY_UTILITIES: [
        "strom", "gas", "wasser", "fernwärme", "telekom",
        "vodafone", "o2", "rundfunkbeitrag", "gez",
    ],
    CATEGORY_INCOME: [
        "gehalt", "lohn", "salary", "vergütung", "überweisung",
    ],
    CATEGORY_TRANSFERS: [
        "umbuchung", "übertrag", "transfer", "sparplan",
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

# Household model
DEFAULT_SPLIT_MODEL = "proportional"  # proportional, equal, custom
