# ACDOCA Integration Guide

## Overview

This document describes the ACDOCA (SAP S/4HANA Universal Journal) integration for the CFO Dashboard. ACDOCA is the central financial data table in S/4HANA, combining FI (Financial Accounting) and CO (Controlling) postings into a single source of truth.

## What is ACDOCA?

**ACDOCA** = **AC**counting **DOC**ument **A**ctuals

In SAP S/4HANA, ACDOCA replaces the traditional split between:
- BKPF/BSEG (FI documents)
- COEP/COBK (CO documents)
- FAGLFLEXA (New GL)

All financial postings now flow into ACDOCA, making it THE source for:
- General Ledger reporting
- Cost Center accounting
- Profit Center accounting
- Segment reporting
- Management accounting

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    CFO Dashboard                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │ P&L Summary │  │ Cost Center │  │ Actual vs Budget    │  │
│  │   Charts    │  │  Analysis   │  │    Variance         │  │
│  └──────┬──────┘  └──────┬──────┘  └──────────┬──────────┘  │
│         │                │                     │              │
│         └────────────────┼─────────────────────┘              │
│                          │                                    │
│                 ┌────────▼────────┐                          │
│                 │ ACDOCA Analytics│                          │
│                 │     Engine      │                          │
│                 └────────┬────────┘                          │
└──────────────────────────┼───────────────────────────────────┘
                           │
              ┌────────────▼────────────┐
              │      Data Service       │
              │  get_acdoca_data()      │
              │  get_acdoca_budget()    │
              │  get_acdoca_summary()   │
              └────────────┬────────────┘
                           │
              ┌────────────▼────────────┐
              │      SAP HANA Cloud     │
              │  ┌──────────────────┐   │
              │  │  ACDOCA_SAMPLE   │   │
              │  │  ACDOCA_BUDGET   │   │
              │  │  GL_ACCOUNTS     │   │
              │  │  COST_CENTERS    │   │
              │  │  COMPANY_CODES   │   │
              │  └──────────────────┘   │
              └─────────────────────────┘
```

## Table Schema

### ACDOCA_SAMPLE (Journal Entries)

| Column | Type | Description |
|--------|------|-------------|
| RBUKRS | NVARCHAR(4) | Company Code |
| GJAHR | INTEGER | Fiscal Year |
| BELNR | NVARCHAR(10) | Document Number |
| DOCLN | INTEGER | Line Item |
| BUDAT | DATE | Posting Date |
| RACCT | NVARCHAR(10) | GL Account |
| RCNTR | NVARCHAR(10) | Cost Center |
| PRCTR | NVARCHAR(10) | Profit Center |
| SEGMENT | NVARCHAR(10) | Segment |
| HSL | DECIMAL(17,2) | Amount (Local Currency) |
| RHCUR | NVARCHAR(5) | Local Currency |
| KSL | DECIMAL(17,2) | Amount (Global Currency USD) |
| POPER | INTEGER | Posting Period (1-12) |
| DRCRK | NVARCHAR(1) | Debit/Credit (S/H) |
| BLART | NVARCHAR(2) | Document Type |
| SGTXT | NVARCHAR(50) | Line Item Text |

### ACDOCA_BUDGET (Plan Data)

| Column | Type | Description |
|--------|------|-------------|
| RBUKRS | NVARCHAR(4) | Company Code |
| GJAHR | INTEGER | Fiscal Year |
| POPER | INTEGER | Period |
| RACCT | NVARCHAR(10) | GL Account |
| RCNTR | NVARCHAR(10) | Cost Center |
| HSL | DECIMAL(17,2) | Budget Amount |
| VERSION | NVARCHAR(10) | Plan Version |

## Sample Data Generator

The `acdoca_generator.py` script creates realistic journal entries for development and testing.

### Usage

```bash
# Generate 24 months of data to CSV
python data/acdoca_generator.py --months 24 --output data/acdoca_sample.csv

# Generate and load directly to HANA
python data/acdoca_generator.py --months 24 --load-hana
```

### Data Characteristics

- **Companies**: 3 (US, Germany, Singapore)
- **Currencies**: USD, EUR, SGD
- **Accounts**: Full P&L chart of accounts (Revenue, COGS, OpEx, etc.)
- **Cost Centers**: 18 across Sales, Marketing, R&D, Operations, Finance, HR
- **Seasonality**: Built-in monthly patterns (Q4 peak, summer slowdown)
- **Growth**: 12% YoY growth applied
- **Volume**: ~20K entries per month (realistic enterprise volume)

### Generated Scenarios

1. **Revenue Recognition**: Product, Service, Subscription, Licensing
2. **Cost of Goods Sold**: Materials, Labor, Overhead
3. **Operating Expenses**: Personnel, Facilities, S&M, R&D, G&A, D&A
4. **Other Income/Expense**: Interest, FX gains/losses
5. **Tax Provision**: 25% effective rate

## Analytics Features

### P&L Summary

```python
from utils.acdoca_analytics import ACDOCAAnalytics

analytics = ACDOCAAnalytics(df_acdoca, df_budget)
pl = analytics.get_pl_summary(
    company_codes=['1000'],
    year=2025,
    periods=[1, 2, 3]  # Q1
)
```

Output:
| Category | Amount | Margin % |
|----------|--------|----------|
| Revenue | 12,500,000 | 100.0 |
| COGS | 4,375,000 | 35.0 |
| Gross Profit | 8,125,000 | 65.0 |
| ... | ... | ... |
| Net Income | 1,875,000 | 15.0 |

### Actual vs Budget Variance

```python
variance = analytics.get_actual_vs_budget(
    company_codes=['1000'],
    year=2025,
    periods=[1, 2, 3]
)
```

Output:
| Category | Actual | Budget | Variance | Variance % |
|----------|--------|--------|----------|------------|
| Revenue | 12,500,000 | 13,000,000 | -500,000 | -3.8% |
| COGS | 4,375,000 | 4,550,000 | 175,000 | 3.8% |

### Cost Center Analysis

```python
cc_analysis = analytics.get_cost_center_analysis(
    company_codes=['1000'],
    year=2025,
    top_n=10
)
```

### KPIs

```python
kpis = analytics.get_kpis(company_codes=['1000'], year=2025)
# Returns: Revenue, Gross Margin %, EBITDA, EBITDA Margin %, Net Income, etc.
```

## Dashboard Integration

### New Tabs (Planned)

1. **GL Analysis**: P&L waterfall, account drill-down
2. **Cost Center View**: Spend by department with trends
3. **Actual vs Budget**: Variance analysis with RAG indicators
4. **Journal Explorer**: Search and filter individual postings

### Data Service Methods

```python
# In app.py callbacks:
from db.data_service import FinancialDataService

# Get ACDOCA data
df = data_service.get_acdoca_data(
    company_codes=['1000'],
    year=2025,
    periods=[1, 2, 3]
)

# Get budget
budget = data_service.get_acdoca_budget(company_codes=['1000'], year=2025)

# Get summary by cost center
summary = data_service.get_acdoca_summary(group_by='cost_center')
```

## Production Integration (Future)

For production S/4HANA integration:

### CDS Views

- `I_GLAccountLineItem` - GL line items
- `I_JournalEntry` - Journal entries
- `I_OperationalAcctgDocItem` - Operational postings

### Integration Options

1. **OData Services**: Real-time API access
2. **SAP SLT**: Delta replication to HANA Cloud
3. **SAP ODP**: Operational Data Provisioning
4. **SAP BW Bridge**: If BW is in the landscape

### Example OData Extraction

```python
# Future implementation
from api.s4hana_connector import S4HANAConnector

connector = S4HANAConnector(config)
df = connector.extract_acdoca(
    company_code='1000',
    fiscal_year=2025,
    delta_mode=True  # Only new/changed records
)
```

## Files Added

```
bloomberg_analytics_hub/
├── db/
│   └── acdoca_schema.sql           # Table DDL
├── data/
│   ├── gl_accounts.json            # Chart of accounts
│   ├── cost_centers.json           # Cost center master
│   └── acdoca_generator.py         # Sample data generator
├── utils/
│   └── acdoca_analytics.py         # Analytics calculations
└── documentation/
    └── ACDOCA_INTEGRATION.md       # This file
```

## Next Steps

1. [ ] Generate sample data and load to HANA Cloud
2. [ ] Add ACDOCA tabs to dashboard UI
3. [ ] Implement Actual vs Budget variance charts
4. [ ] Add cost center drill-down
5. [ ] Create GL account hierarchy view
6. [ ] Add export to Excel functionality
7. [ ] Implement YoY comparison charts

## References

- [SAP S/4HANA Universal Journal](https://help.sap.com/docs/SAP_S4HANA_ON-PREMISE/8308e6d301d54584a33cd04a9861b0a6/54a99fa88e9a4b4f8f0bbff84c0b8bca.html)
- [ACDOCA Table Documentation](https://www.se80.co.uk/saptables/a/acdo/acdoca.htm)
- [SAP BTP Integration](https://help.sap.com/docs/btp)
