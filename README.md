# Finance Dashboard for Home Assistant

**Your personal finance command center — right inside Home Assistant.**

[![Version](https://img.shields.io/badge/version-0.4.0-blue?style=flat-square)](https://github.com/Jerry0022/homeassistant-finance/releases)
[![License](https://img.shields.io/badge/license-MIT-green?style=flat-square)](LICENSE)
[![HACS](https://img.shields.io/badge/HACS-compatible-orange?style=flat-square)](https://hacs.xyz)
[![CI](https://img.shields.io/github/actions/workflow/status/Jerry0022/homeassistant-finance/validate.yml?style=flat-square&label=CI)](https://github.com/Jerry0022/homeassistant-finance/actions)
[![HA](https://img.shields.io/badge/Home%20Assistant-2024.1+-41BDF5?style=flat-square&logo=homeassistant&logoColor=white)](https://www.home-assistant.io)

**Version: 0.4.0**

<!-- TODO: Add screenshot of the Finance Dashboard sidebar panel -->

## Table of Contents

- [What is this?](#-what-is-this)
- [Features](#-features)
- [Getting Started](#-getting-started)
- [How to Use](#-how-to-use)
- [Architecture](#-architecture)
- [Security](#-security)
- [Contributing](#-contributing)
- [License](#-license)

## 💡 What is this?

Finance Dashboard connects your bank accounts to Home Assistant via [GoCardless Open Banking](https://gocardless.com/bank-account-data/), giving you a real-time overview of balances, transactions, and household budgets. Track spending across multiple people, auto-categorize transactions, and see where your money goes — all from your HA dashboard, with banking-grade security.

## ✨ Features

- 🏦 **Live Banking Data** — Connect 2400+ European banks via GoCardless Open Banking API
- 📊 **Auto-Categorization** — Transactions are automatically classified (housing, food, transport, subscriptions, etc.)
- 👥 **Multi-Person Households** — Configurable budget split models for any number of household members
- 🔒 **Banking-Grade Security** — Fernet encryption, token rotation, session timeouts, full audit trail
- 📱 **Sidebar Panel** — Dedicated finance overview accessible from the HA sidebar
- 🎴 **Lovelace Card** — Compact balance widget for any dashboard
- 🔄 **Companion Add-on** — One-click installation with automatic updates
- 🌍 **Multilingual** — English and German translations included
- 🤖 **HA Automations** — Expose services for balance checks, transaction refresh, and monthly summaries

## 🚀 Getting Started

### Prerequisites

- Home Assistant 2024.1 or newer
- A free [GoCardless Bank Account Data](https://bankaccountdata.gocardless.com) API account
- A supported European bank (2400+ institutions across 31 countries)

### Installation via HACS (Recommended)

1. Open HACS in Home Assistant
2. Go to **Integrations** → **Custom Repositories**
3. Add `https://github.com/Jerry0022/homeassistant-finance` as an **Integration**
4. Install **Finance Dashboard**
5. Restart Home Assistant

### Installation via Companion Add-on

1. Add this repository URL to your Home Assistant add-on store
2. Install the **Finance Dashboard** add-on
3. Start the add-on — it automatically installs the integration
4. Restart Home Assistant when prompted

### Manual Installation

1. Copy `custom_components/finance_dashboard/` to your HA `config/custom_components/` directory
2. Copy `www/community/finance-dashboard/` to your HA `config/www/community/` directory
3. Restart Home Assistant

## 📖 How to Use

### 1. Get GoCardless API Keys

1. Sign up at [GoCardless Bank Account Data](https://bankaccountdata.gocardless.com)
2. Create a new set of API keys (Secret ID + Secret Key)
3. The free tier supports up to 50 bank connections

### 2. Configure the Integration

1. Go to **Settings** → **Devices & Services** → **Add Integration**
2. Search for **Finance Dashboard**
3. Enter your GoCardless Secret ID and Secret Key
4. Follow the prompts to link your bank account

### 3. View Your Finances

- **Sidebar**: Click the Finance Dashboard icon in the HA sidebar for the full overview
- **Lovelace Card**: Add a `custom:finance-dashboard-card` to any dashboard

```yaml
type: custom:finance-dashboard-card
show_transactions: true
max_transactions: 5
```

### 4. Use in Automations

```yaml
# Refresh transactions daily
automation:
  - alias: "Daily Finance Refresh"
    trigger:
      - platform: time
        at: "08:00:00"
    action:
      - service: finance_dashboard.refresh_transactions
```

## 🏗 Architecture

```
┌─────────────────────────────────────────────────┐
│                 Home Assistant                   │
│                                                  │
│  ┌──────────────┐  ┌─────────────────────────┐  │
│  │  Sidebar      │  │  Lovelace Card          │  │
│  │  Panel (JS)   │  │  (JS Web Component)     │  │
│  └──────┬───────┘  └──────────┬──────────────┘  │
│         │     HTTP API         │                 │
│  ┌──────┴──────────────────────┴──────────────┐  │
│  │         Finance Dashboard Integration       │  │
│  │  ┌──────────┐ ┌────────────┐ ┌──────────┐  │  │
│  │  │ Manager  │ │ Categorizer│ │ Cred Mgr │  │  │
│  │  └────┬─────┘ └────────────┘ └──┬───────┘  │  │
│  │       │                          │          │  │
│  │  ┌────┴──────────────────────────┴───────┐  │  │
│  │  │       GoCardless API Client           │  │  │
│  │  └────────────────┬──────────────────────┘  │  │
│  └───────────────────┼─────────────────────────┘  │
│                      │                            │
│  ┌───────────────────┼─────────────────────────┐  │
│  │  Companion Add-on │ (Payload Installer)     │  │
│  └───────────────────┘                         │  │
└──────────────────────┼─────────────────────────┘
                       │ HTTPS
              ┌────────┴────────┐
              │  GoCardless API  │
              │  (Open Banking)  │
              └────────┬────────┘
                       │ PSD2
              ┌────────┴────────┐
              │   Your Bank      │
              └─────────────────┘
```

## 🔒 Security

Finance Dashboard follows banking-grade security practices:

| Layer | Protection |
|-------|-----------|
| **Credential Storage** | Fernet symmetric encryption (AES-128-CBC + HMAC) in HA `.storage/` |
| **Token Management** | Auto-rotation before expiry, forced re-auth after 90 days |
| **Session Security** | 30-minute inactivity timeout |
| **Data Display** | IBANs masked to last 4 digits in all API responses |
| **Audit Trail** | Every credential operation logged (event type + timestamp only) |
| **API Security** | All endpoints require HA Bearer token authentication |
| **Git Safety** | `.gitignore` blocks all runtime data, credentials, and tokens |
| **Network** | HTTPS-only communication with GoCardless; no telemetry |

**No financial data is ever stored in git, logs, or configuration files.**

## 🤝 Contributing

Contributions are welcome! Please note the strict security requirements — any PR that could leak financial data will be rejected.

1. Fork the repository
2. Create a feature branch (`feat/42-your-feature`)
3. Run validation: `python scripts/bump_versions.py --check`
4. Submit a Pull Request

## 📄 License

[MIT](LICENSE) — Copyright (c) 2026 Jerry0022
