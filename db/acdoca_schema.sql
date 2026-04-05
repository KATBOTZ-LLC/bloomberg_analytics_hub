-- ACDOCA Sample Tables for CFO Dashboard
-- SAP S/4HANA Universal Journal (Simplified Schema for Demo/Development)

-- =============================================================================
-- ACDOCA_SAMPLE: Main Journal Entry Table (Actuals)
-- =============================================================================
CREATE TABLE "{schema}"."ACDOCA_SAMPLE" (
    -- Document Identification
    "ID" INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    "RCLNT" NVARCHAR(3) DEFAULT '100',           -- Client
    "RBUKRS" NVARCHAR(4) NOT NULL,               -- Company Code
    "GJAHR" INTEGER NOT NULL,                     -- Fiscal Year
    "BELNR" NVARCHAR(10) NOT NULL,               -- Document Number
    "DOCLN" INTEGER NOT NULL,                     -- Line Item Number
    
    -- Dates
    "BLDAT" DATE,                                 -- Document Date
    "BUDAT" DATE NOT NULL,                        -- Posting Date
    "CPUDT" DATE,                                 -- Entry Date
    
    -- Account Assignment
    "RACCT" NVARCHAR(10) NOT NULL,               -- GL Account
    "RCNTR" NVARCHAR(10),                        -- Cost Center
    "PRCTR" NVARCHAR(10),                        -- Profit Center
    "RBUSA" NVARCHAR(4),                         -- Business Area
    "SEGMENT" NVARCHAR(10),                      -- Segment
    "KUNNR" NVARCHAR(10),                        -- Customer
    "LIFNR" NVARCHAR(10),                        -- Vendor
    
    -- Amounts
    "HSL" DECIMAL(17,2) NOT NULL,                -- Amount in Company Code Currency
    "RHCUR" NVARCHAR(5) NOT NULL,                -- Company Code Currency
    "TSL" DECIMAL(17,2),                         -- Amount in Transaction Currency
    "RTCUR" NVARCHAR(5),                         -- Transaction Currency
    "KSL" DECIMAL(17,2),                         -- Amount in Global Currency (USD)
    "RKCUR" NVARCHAR(5) DEFAULT 'USD',           -- Global Currency
    
    -- Period
    "POPER" INTEGER NOT NULL,                    -- Posting Period (1-12)
    "FISCYEARPER" NVARCHAR(7),                   -- Fiscal Year Period (2026001)
    
    -- Classification
    "DRCRK" NVARCHAR(1),                         -- Debit/Credit Indicator (S=Debit, H=Credit)
    "KOESSION" NVARCHAR(1),                      -- Account Type
    "BSCHL" NVARCHAR(2),                         -- Posting Key
    "BLART" NVARCHAR(2),                         -- Document Type
    
    -- Descriptive
    "SGTXT" NVARCHAR(50),                        -- Line Item Text
    "BKTXT" NVARCHAR(25),                        -- Document Header Text
    
    -- Metadata
    "INSERTED_AT" TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for common queries
CREATE INDEX "IDX_ACDOCA_COMPANY_PERIOD" ON "{schema}"."ACDOCA_SAMPLE" ("RBUKRS", "GJAHR", "POPER");
CREATE INDEX "IDX_ACDOCA_ACCOUNT" ON "{schema}"."ACDOCA_SAMPLE" ("RACCT");
CREATE INDEX "IDX_ACDOCA_COSTCENTER" ON "{schema}"."ACDOCA_SAMPLE" ("RCNTR");
CREATE INDEX "IDX_ACDOCA_PROFITCENTER" ON "{schema}"."ACDOCA_SAMPLE" ("PRCTR");
CREATE INDEX "IDX_ACDOCA_POSTING_DATE" ON "{schema}"."ACDOCA_SAMPLE" ("BUDAT");

-- =============================================================================
-- ACDOCA_BUDGET: Budget/Plan Data Table
-- =============================================================================
CREATE TABLE "{schema}"."ACDOCA_BUDGET" (
    "ID" INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    "RCLNT" NVARCHAR(3) DEFAULT '100',
    "RBUKRS" NVARCHAR(4) NOT NULL,               -- Company Code
    "GJAHR" INTEGER NOT NULL,                     -- Fiscal Year
    "POPER" INTEGER NOT NULL,                    -- Period (1-12)
    "RACCT" NVARCHAR(10) NOT NULL,               -- GL Account
    "RCNTR" NVARCHAR(10),                        -- Cost Center
    "PRCTR" NVARCHAR(10),                        -- Profit Center
    "SEGMENT" NVARCHAR(10),                      -- Segment
    "HSL" DECIMAL(17,2) NOT NULL,                -- Budget Amount (Company Currency)
    "RHCUR" NVARCHAR(5) NOT NULL,                -- Currency
    "KSL" DECIMAL(17,2),                         -- Budget Amount (Global Currency USD)
    "VERSION" NVARCHAR(10) DEFAULT 'BUDGET',     -- Plan Version
    "INSERTED_AT" TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX "IDX_BUDGET_COMPANY_PERIOD" ON "{schema}"."ACDOCA_BUDGET" ("RBUKRS", "GJAHR", "POPER");
CREATE INDEX "IDX_BUDGET_ACCOUNT" ON "{schema}"."ACDOCA_BUDGET" ("RACCT");

-- =============================================================================
-- GL_ACCOUNTS: Chart of Accounts Master Data
-- =============================================================================
CREATE TABLE "{schema}"."GL_ACCOUNTS" (
    "RACCT" NVARCHAR(10) PRIMARY KEY,            -- GL Account Number
    "ACCOUNT_NAME" NVARCHAR(100) NOT NULL,       -- Account Description
    "ACCOUNT_TYPE" NVARCHAR(20) NOT NULL,        -- Revenue, COGS, OpEx, Other, Tax, Asset, Liability, Equity
    "ACCOUNT_GROUP" NVARCHAR(50),                -- Account Grouping
    "FS_ITEM" NVARCHAR(20),                      -- Financial Statement Item (P&L, BS)
    "DEBIT_CREDIT" NVARCHAR(1),                  -- Normal Balance (D/C)
    "IS_ACTIVE" BOOLEAN DEFAULT TRUE
);

-- =============================================================================
-- COST_CENTERS: Cost Center Master Data
-- =============================================================================
CREATE TABLE "{schema}"."COST_CENTERS" (
    "RCNTR" NVARCHAR(10) PRIMARY KEY,            -- Cost Center
    "COST_CENTER_NAME" NVARCHAR(100) NOT NULL,   -- Description
    "PRCTR" NVARCHAR(10),                        -- Profit Center
    "RBUKRS" NVARCHAR(4),                        -- Company Code
    "DEPARTMENT" NVARCHAR(50),                   -- Department
    "MANAGER" NVARCHAR(100),                     -- Responsible Manager
    "IS_ACTIVE" BOOLEAN DEFAULT TRUE
);

-- =============================================================================
-- COMPANY_CODES: Company Code Master Data
-- =============================================================================
CREATE TABLE "{schema}"."COMPANY_CODES" (
    "RBUKRS" NVARCHAR(4) PRIMARY KEY,            -- Company Code
    "COMPANY_NAME" NVARCHAR(100) NOT NULL,       -- Company Name
    "RHCUR" NVARCHAR(5) NOT NULL,                -- Local Currency
    "COUNTRY" NVARCHAR(3),                       -- Country Code
    "REGION" NVARCHAR(20),                       -- Region (Americas, EMEA, APAC)
    "IS_ACTIVE" BOOLEAN DEFAULT TRUE
);

-- =============================================================================
-- FX_RATES: Exchange Rates for Currency Conversion
-- =============================================================================
CREATE TABLE "{schema}"."FX_RATES" (
    "ID" INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    "RATE_DATE" DATE NOT NULL,
    "FROM_CURRENCY" NVARCHAR(5) NOT NULL,
    "TO_CURRENCY" NVARCHAR(5) NOT NULL,
    "EXCHANGE_RATE" DECIMAL(15,6) NOT NULL,
    "RATE_TYPE" NVARCHAR(10) DEFAULT 'AVG'       -- AVG, SPOT, BUDGET
);

CREATE INDEX "IDX_FX_DATE_CURR" ON "{schema}"."FX_RATES" ("RATE_DATE", "FROM_CURRENCY", "TO_CURRENCY");
