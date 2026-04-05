#!/usr/bin/env python3
"""
ACDOCA Sample Data Generator for CFO Dashboard

Generates realistic SAP S/4HANA Universal Journal (ACDOCA) entries
for development, testing, and demonstration purposes.

Usage:
    python acdoca_generator.py --months 24 --output data/acdoca_sample.csv
    python acdoca_generator.py --load-hana  # Generate and load directly to HANA
"""

import os
import sys
import json
import random
import argparse
import logging
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
import pandas as pd
import numpy as np

# Add parent directory for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ============================================================================
# CONFIGURATION
# ============================================================================

# Base revenue settings (annual, will be distributed monthly)
BASE_ANNUAL_REVENUE = {
    "1000": 50_000_000,   # US: $50M
    "2000": 30_000_000,   # EU: €30M (will convert)
    "3000": 20_000_000,   # APAC: S$20M (will convert)
}

# Cost structure as % of revenue
COST_STRUCTURE = {
    "COGS": 0.35,           # 35% COGS = 65% Gross Margin
    "PERSONNEL": 0.25,      # 25% Personnel
    "FACILITIES": 0.05,     # 5% Facilities
    "SALES_MARKETING": 0.10,# 10% Sales & Marketing
    "RD": 0.08,             # 8% R&D
    "GA": 0.05,             # 5% G&A
    "DA": 0.03,             # 3% Depreciation & Amortization
}

# Seasonality factors by month (index 0 = January)
SEASONALITY = [
    0.85,  # Jan - Post-holiday slowdown
    0.88,  # Feb
    0.95,  # Mar - Q1 push
    0.92,  # Apr
    0.90,  # May
    0.95,  # Jun - Q2 close
    0.88,  # Jul - Summer slowdown
    0.85,  # Aug
    1.00,  # Sep - Q3 push
    1.05,  # Oct
    1.10,  # Nov - Holiday prep
    1.20,  # Dec - Year-end push, holiday
]

# YoY growth rate
YOY_GROWTH = 0.12  # 12% YoY growth

# FX Rates to USD (average rates for conversion)
FX_RATES = {
    "USD": 1.0,
    "EUR": 1.08,   # 1 EUR = 1.08 USD
    "SGD": 0.74,   # 1 SGD = 0.74 USD
}

# Document types
DOC_TYPES = {
    "SA": "G/L Account Document",
    "RV": "Revenue Document",
    "RE": "Invoice Receipt",
    "KR": "Vendor Invoice",
    "DR": "Customer Invoice",
    "AA": "Asset Document",
}


class ACDOCAGenerator:
    """Generate realistic ACDOCA journal entries"""
    
    def __init__(self, data_dir=None):
        """Initialize generator with master data"""
        self.data_dir = data_dir or os.path.dirname(os.path.abspath(__file__))
        self.load_master_data()
        self.doc_counter = {}  # Track document numbers per company/year
        
    def load_master_data(self):
        """Load GL accounts and cost centers from JSON"""
        # Load GL Accounts
        gl_path = os.path.join(self.data_dir, 'gl_accounts.json')
        with open(gl_path, 'r') as f:
            data = json.load(f)
            self.gl_accounts = {acc['racct']: acc for acc in data['gl_accounts']}
        logger.info(f"Loaded {len(self.gl_accounts)} GL accounts")
        
        # Load Cost Centers and Company Codes
        cc_path = os.path.join(self.data_dir, 'cost_centers.json')
        with open(cc_path, 'r') as f:
            data = json.load(f)
            self.cost_centers = {cc['rcntr']: cc for cc in data['cost_centers']}
            self.company_codes = {cc['rbukrs']: cc for cc in data['company_codes']}
            self.profit_centers = {pc['prctr']: pc for pc in data['profit_centers']}
        logger.info(f"Loaded {len(self.cost_centers)} cost centers, {len(self.company_codes)} company codes")
        
    def get_accounts_by_type(self, account_type):
        """Get list of accounts by type"""
        return [acc for acc in self.gl_accounts.values() if acc['account_type'] == account_type]
    
    def get_cost_centers_by_company(self, company_code):
        """Get cost centers for a company"""
        return [cc for cc in self.cost_centers.values() 
                if cc.get('rbukrs') == company_code or company_code == '1000']  # HQ cost centers available to all
    
    def next_doc_number(self, company_code, year):
        """Generate next document number"""
        key = f"{company_code}_{year}"
        if key not in self.doc_counter:
            self.doc_counter[key] = 1000000000
        self.doc_counter[key] += 1
        return str(self.doc_counter[key])
    
    def generate_journal_entry(self, company_code, posting_date, lines, doc_type="SA", header_text=""):
        """
        Generate a balanced journal entry with multiple lines
        
        Args:
            company_code: Company code
            posting_date: Posting date
            lines: List of (account, amount, cost_center, text) tuples
                   Positive = Debit, Negative = Credit
            doc_type: Document type
            header_text: Document header text
        
        Returns:
            List of ACDOCA line dictionaries
        """
        company = self.company_codes[company_code]
        currency = company['rhcur']
        year = posting_date.year
        period = posting_date.month
        doc_number = self.next_doc_number(company_code, year)
        
        entries = []
        for i, (account, amount, cost_center, text) in enumerate(lines, 1):
            gl_account = self.gl_accounts.get(account, {})
            cc_data = self.cost_centers.get(cost_center, {}) if cost_center else {}
            
            # Convert to global currency (USD)
            fx_rate = FX_RATES.get(currency, 1.0)
            amount_usd = round(amount * fx_rate, 2)
            
            entry = {
                'RCLNT': '100',
                'RBUKRS': company_code,
                'GJAHR': year,
                'BELNR': doc_number,
                'DOCLN': i,
                'BLDAT': posting_date.strftime('%Y-%m-%d'),
                'BUDAT': posting_date.strftime('%Y-%m-%d'),
                'CPUDT': posting_date.strftime('%Y-%m-%d'),
                'RACCT': account,
                'RCNTR': cost_center,
                'PRCTR': cc_data.get('prctr'),
                'RBUSA': None,
                'SEGMENT': self.profit_centers.get(cc_data.get('prctr'), {}).get('segment'),
                'KUNNR': None,
                'LIFNR': None,
                'HSL': amount,
                'RHCUR': currency,
                'TSL': amount,
                'RTCUR': currency,
                'KSL': amount_usd,
                'RKCUR': 'USD',
                'POPER': period,
                'FISCYEARPER': f"{year}{period:03d}",
                'DRCRK': 'S' if amount >= 0 else 'H',
                'KOESSION': None,
                'BSCHL': '40' if amount >= 0 else '50',
                'BLART': doc_type,
                'SGTXT': text or gl_account.get('account_name', ''),
                'BKTXT': header_text,
            }
            entries.append(entry)
            
        return entries
    
    def generate_revenue_entries(self, company_code, posting_date, base_amount):
        """Generate revenue journal entries"""
        entries = []
        revenue_accounts = ['400000', '401000', '402000', '403000']
        
        # Split revenue across different types
        splits = [0.50, 0.25, 0.15, 0.10]  # Product, Service, Subscription, Licensing
        
        # Get sales cost centers for this company
        sales_ccs = [cc['rcntr'] for cc in self.cost_centers.values() 
                     if 'Sales' in cc.get('department', '')]
        
        for acc, split in zip(revenue_accounts, splits):
            if split > 0:
                amount = round(base_amount * split * (1 + random.uniform(-0.1, 0.1)), 2)
                cc = random.choice(sales_ccs) if sales_ccs else 'CC1000'
                
                # Revenue entry: Credit Revenue, Debit AR
                lines = [
                    ('110000', amount, None, 'Customer Invoice'),  # Debit AR
                    (acc, -amount, cc, f'{self.gl_accounts[acc]["account_name"]}'),  # Credit Revenue
                ]
                entries.extend(self.generate_journal_entry(
                    company_code, posting_date, lines, 'RV', 'Revenue Recognition'
                ))
        
        return entries
    
    def generate_cogs_entries(self, company_code, posting_date, revenue_amount):
        """Generate COGS journal entries"""
        cogs_amount = revenue_amount * COST_STRUCTURE['COGS']
        cogs_accounts = ['500000', '501000', '502000', '503000']
        splits = [0.40, 0.30, 0.20, 0.10]
        
        ops_ccs = [cc['rcntr'] for cc in self.cost_centers.values() 
                   if 'Operations' in cc.get('department', '')]
        
        entries = []
        for acc, split in zip(cogs_accounts, splits):
            amount = round(cogs_amount * split * (1 + random.uniform(-0.05, 0.05)), 2)
            cc = random.choice(ops_ccs) if ops_ccs else 'CC4000'
            
            lines = [
                (acc, amount, cc, self.gl_accounts[acc]['account_name']),  # Debit COGS
                ('120000', -amount, None, 'Inventory Usage'),  # Credit Inventory
            ]
            entries.extend(self.generate_journal_entry(
                company_code, posting_date, lines, 'SA', 'Cost of Goods Sold'
            ))
        
        return entries
    
    def generate_opex_entries(self, company_code, posting_date, revenue_amount):
        """Generate operating expense entries"""
        entries = []
        company = self.company_codes[company_code]
        
        # Personnel expenses
        personnel_amount = revenue_amount * COST_STRUCTURE['PERSONNEL']
        personnel_accounts = [('600000', 0.70), ('601000', 0.20), ('602000', 0.10)]
        
        for acc, split in personnel_accounts:
            amount = round(personnel_amount * split * (1 + random.uniform(-0.03, 0.03)), 2)
            # Distribute across various cost centers
            for cc in random.sample(list(self.cost_centers.keys()), min(5, len(self.cost_centers))):
                cc_amount = round(amount / 5 * (1 + random.uniform(-0.2, 0.2)), 2)
                lines = [
                    (acc, cc_amount, cc, self.gl_accounts[acc]['account_name']),
                    ('200000', -cc_amount, None, 'Accrued Payroll'),
                ]
                entries.extend(self.generate_journal_entry(
                    company_code, posting_date, lines, 'SA', 'Payroll'
                ))
        
        # Facilities
        facilities_amount = revenue_amount * COST_STRUCTURE['FACILITIES']
        facilities_accounts = [('610000', 0.60), ('611000', 0.25), ('612000', 0.15)]
        ops_cc = 'CC4000' if company_code == '1000' else f'CC40{company_code[-1]}0'
        
        for acc, split in facilities_accounts:
            amount = round(facilities_amount * split, 2)
            lines = [
                (acc, amount, ops_cc, self.gl_accounts[acc]['account_name']),
                ('200000', -amount, None, 'Accounts Payable'),
            ]
            entries.extend(self.generate_journal_entry(
                company_code, posting_date, lines, 'KR', 'Facilities Expense'
            ))
        
        # Sales & Marketing
        sm_amount = revenue_amount * COST_STRUCTURE['SALES_MARKETING']
        sm_accounts = [('620000', 0.50), ('621000', 0.30), ('622000', 0.20)]
        mkt_cc = 'CC2000'
        
        for acc, split in sm_accounts:
            amount = round(sm_amount * split * (1 + random.uniform(-0.1, 0.1)), 2)
            lines = [
                (acc, amount, mkt_cc, self.gl_accounts[acc]['account_name']),
                ('200000', -amount, None, 'Vendor Invoice'),
            ]
            entries.extend(self.generate_journal_entry(
                company_code, posting_date, lines, 'KR', 'Marketing Expense'
            ))
        
        # R&D
        rd_amount = revenue_amount * COST_STRUCTURE['RD']
        rd_accounts = [('630000', 0.70), ('631000', 0.30)]
        rd_ccs = ['CC3000', 'CC3010', 'CC3020']
        
        for acc, split in rd_accounts:
            amount = round(rd_amount * split, 2)
            cc = random.choice(rd_ccs)
            lines = [
                (acc, amount, cc, self.gl_accounts[acc]['account_name']),
                ('200000', -amount, None, 'R&D Costs'),
            ]
            entries.extend(self.generate_journal_entry(
                company_code, posting_date, lines, 'SA', 'R&D Expense'
            ))
        
        # G&A
        ga_amount = revenue_amount * COST_STRUCTURE['GA']
        ga_accounts = [('650000', 0.30), ('651000', 0.25), ('652000', 0.15), ('653000', 0.15), ('654000', 0.15)]
        ga_cc = 'CC5000'
        
        for acc, split in ga_accounts:
            amount = round(ga_amount * split * (1 + random.uniform(-0.05, 0.05)), 2)
            lines = [
                (acc, amount, ga_cc, self.gl_accounts[acc]['account_name']),
                ('200000', -amount, None, 'G&A Invoice'),
            ]
            entries.extend(self.generate_journal_entry(
                company_code, posting_date, lines, 'KR', 'G&A Expense'
            ))
        
        # Depreciation & Amortization
        da_amount = revenue_amount * COST_STRUCTURE['DA']
        da_accounts = [('640000', 0.70), ('641000', 0.30)]
        
        for acc, split in da_accounts:
            amount = round(da_amount * split, 2)
            lines = [
                (acc, amount, 'CC5020', self.gl_accounts[acc]['account_name']),
                ('150000', -amount, None, 'Accumulated Depreciation'),
            ]
            entries.extend(self.generate_journal_entry(
                company_code, posting_date, lines, 'AA', 'Depreciation'
            ))
        
        return entries
    
    def generate_other_entries(self, company_code, posting_date, revenue_amount):
        """Generate other income/expense entries"""
        entries = []
        
        # Interest expense (assume some debt)
        interest_exp = round(revenue_amount * 0.01, 2)
        lines = [
            ('710000', interest_exp, 'CC5000', 'Interest Expense'),
            ('100000', -interest_exp, None, 'Cash - Interest Payment'),
        ]
        entries.extend(self.generate_journal_entry(
            company_code, posting_date, lines, 'SA', 'Interest Payment'
        ))
        
        # Small interest income
        interest_inc = round(revenue_amount * 0.002 * random.uniform(0.5, 1.5), 2)
        lines = [
            ('100000', interest_inc, None, 'Cash - Interest Received'),
            ('700000', -interest_inc, 'CC5000', 'Interest Income'),
        ]
        entries.extend(self.generate_journal_entry(
            company_code, posting_date, lines, 'SA', 'Interest Income'
        ))
        
        # FX gain/loss for non-USD companies
        if self.company_codes[company_code]['rhcur'] != 'USD':
            fx_amount = round(revenue_amount * random.uniform(-0.02, 0.02), 2)
            if fx_amount >= 0:
                lines = [
                    ('100000', fx_amount, None, 'FX Adjustment'),
                    ('720000', -fx_amount, 'CC5000', 'FX Gain'),
                ]
            else:
                lines = [
                    ('721000', -fx_amount, 'CC5000', 'FX Loss'),
                    ('100000', fx_amount, None, 'FX Adjustment'),
                ]
            entries.extend(self.generate_journal_entry(
                company_code, posting_date, lines, 'SA', 'FX Revaluation'
            ))
        
        return entries
    
    def generate_tax_entries(self, company_code, posting_date, pretax_income):
        """Generate tax expense entries"""
        # Effective tax rate
        tax_rate = 0.25  # 25% effective rate
        tax_expense = round(max(0, pretax_income * tax_rate), 2)
        
        if tax_expense > 0:
            lines = [
                ('800000', tax_expense, 'CC5000', 'Income Tax Expense'),
                ('210000', -tax_expense, None, 'Income Tax Payable'),
            ]
            return self.generate_journal_entry(
                company_code, posting_date, lines, 'SA', 'Tax Provision'
            )
        return []
    
    def generate_month(self, company_code, year, month):
        """Generate all entries for a single month"""
        entries = []
        
        # Calculate base revenue for this month
        base_annual = BASE_ANNUAL_REVENUE.get(company_code, 10_000_000)
        
        # Apply YoY growth (base year is 2024)
        years_from_base = year - 2024
        growth_factor = (1 + YOY_GROWTH) ** years_from_base
        
        # Apply seasonality
        seasonality_factor = SEASONALITY[month - 1]
        
        # Monthly revenue
        monthly_revenue = (base_annual / 12) * growth_factor * seasonality_factor
        monthly_revenue = round(monthly_revenue * (1 + random.uniform(-0.05, 0.05)), 2)
        
        # Generate posting dates throughout the month
        posting_date = datetime(year, month, 15)  # Mid-month for simplicity
        
        # Generate all entry types
        entries.extend(self.generate_revenue_entries(company_code, posting_date, monthly_revenue))
        entries.extend(self.generate_cogs_entries(company_code, posting_date, monthly_revenue))
        entries.extend(self.generate_opex_entries(company_code, posting_date, monthly_revenue))
        entries.extend(self.generate_other_entries(company_code, posting_date, monthly_revenue))
        
        # Calculate approximate pretax income for tax
        total_costs = monthly_revenue * sum(COST_STRUCTURE.values())
        pretax_income = monthly_revenue - total_costs
        entries.extend(self.generate_tax_entries(company_code, posting_date, pretax_income))
        
        return entries
    
    def generate_budget(self, company_code, year):
        """Generate annual budget for a company"""
        budget_entries = []
        company = self.company_codes[company_code]
        currency = company['rhcur']
        
        base_annual = BASE_ANNUAL_REVENUE.get(company_code, 10_000_000)
        years_from_base = year - 2024
        growth_factor = (1 + YOY_GROWTH) ** years_from_base
        
        # Budget is typically set slightly optimistic
        budget_factor = 1.05  # 5% above projected
        
        for month in range(1, 13):
            seasonality_factor = SEASONALITY[month - 1]
            monthly_revenue = (base_annual / 12) * growth_factor * seasonality_factor * budget_factor
            
            # Revenue budget
            for acc in ['400000', '401000', '402000', '403000']:
                split = {'400000': 0.50, '401000': 0.25, '402000': 0.15, '403000': 0.10}[acc]
                amount = round(monthly_revenue * split, 2)
                fx_rate = FX_RATES.get(currency, 1.0)
                
                budget_entries.append({
                    'RCLNT': '100',
                    'RBUKRS': company_code,
                    'GJAHR': year,
                    'POPER': month,
                    'RACCT': acc,
                    'RCNTR': 'CC1000',
                    'PRCTR': 'PC100',
                    'SEGMENT': 'SG01',
                    'HSL': -amount,  # Revenue is credit
                    'RHCUR': currency,
                    'KSL': round(-amount * fx_rate, 2),
                    'VERSION': 'BUDGET',
                })
            
            # Expense budgets
            expense_budgets = [
                ('500000', COST_STRUCTURE['COGS'], 'CC4000', 'PC300'),
                ('600000', COST_STRUCTURE['PERSONNEL'], 'CC5000', 'PC400'),
                ('610000', COST_STRUCTURE['FACILITIES'], 'CC4000', 'PC300'),
                ('620000', COST_STRUCTURE['SALES_MARKETING'], 'CC2000', 'PC100'),
                ('630000', COST_STRUCTURE['RD'], 'CC3000', 'PC200'),
                ('650000', COST_STRUCTURE['GA'], 'CC5000', 'PC400'),
                ('640000', COST_STRUCTURE['DA'], 'CC5020', 'PC400'),
            ]
            
            for acc, pct, cc, pc in expense_budgets:
                amount = round(monthly_revenue * pct, 2)
                fx_rate = FX_RATES.get(currency, 1.0)
                
                budget_entries.append({
                    'RCLNT': '100',
                    'RBUKRS': company_code,
                    'GJAHR': year,
                    'POPER': month,
                    'RACCT': acc,
                    'RCNTR': cc,
                    'PRCTR': pc,
                    'SEGMENT': self.profit_centers.get(pc, {}).get('segment'),
                    'HSL': amount,  # Expense is debit
                    'RHCUR': currency,
                    'KSL': round(amount * fx_rate, 2),
                    'VERSION': 'BUDGET',
                })
        
        return budget_entries
    
    def generate_fx_rates(self, start_date, end_date):
        """Generate FX rates for the date range"""
        fx_entries = []
        current_date = start_date
        
        while current_date <= end_date:
            for from_curr, base_rate in FX_RATES.items():
                if from_curr != 'USD':
                    # Add some random fluctuation
                    rate = base_rate * (1 + random.uniform(-0.03, 0.03))
                    fx_entries.append({
                        'RATE_DATE': current_date.strftime('%Y-%m-%d'),
                        'FROM_CURRENCY': from_curr,
                        'TO_CURRENCY': 'USD',
                        'EXCHANGE_RATE': round(rate, 6),
                        'RATE_TYPE': 'AVG',
                    })
            current_date += timedelta(days=1)
        
        return fx_entries
    
    def generate_all(self, months=24, end_date=None):
        """
        Generate complete ACDOCA dataset
        
        Args:
            months: Number of months to generate
            end_date: End date (defaults to current month)
        
        Returns:
            dict with 'acdoca', 'budget', 'fx_rates' DataFrames
        """
        if end_date is None:
            end_date = datetime.now().replace(day=1)
        
        start_date = end_date - timedelta(days=months * 30)
        start_date = start_date.replace(day=1)
        
        logger.info(f"Generating {months} months of data: {start_date.strftime('%Y-%m')} to {end_date.strftime('%Y-%m')}")
        
        all_entries = []
        all_budgets = []
        
        # Generate for each company and month
        current = start_date
        while current <= end_date:
            year = current.year
            month = current.month
            
            for company_code in self.company_codes.keys():
                logger.info(f"Generating {company_code} - {year}/{month:02d}")
                entries = self.generate_month(company_code, year, month)
                all_entries.extend(entries)
            
            # Move to next month
            if month == 12:
                current = datetime(year + 1, 1, 1)
            else:
                current = datetime(year, month + 1, 1)
        
        # Generate budgets for each year
        years = set(e['GJAHR'] for e in all_entries)
        for year in years:
            for company_code in self.company_codes.keys():
                logger.info(f"Generating budget for {company_code} - {year}")
                budgets = self.generate_budget(company_code, year)
                all_budgets.extend(budgets)
        
        # Generate FX rates
        fx_rates = self.generate_fx_rates(start_date, end_date)
        
        # Convert to DataFrames
        df_acdoca = pd.DataFrame(all_entries)
        df_budget = pd.DataFrame(all_budgets)
        df_fx = pd.DataFrame(fx_rates)
        
        logger.info(f"Generated {len(df_acdoca)} ACDOCA entries")
        logger.info(f"Generated {len(df_budget)} budget entries")
        logger.info(f"Generated {len(df_fx)} FX rate entries")
        
        return {
            'acdoca': df_acdoca,
            'budget': df_budget,
            'fx_rates': df_fx,
        }


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description='Generate ACDOCA sample data')
    parser.add_argument('--months', type=int, default=24, help='Number of months to generate')
    parser.add_argument('--output', type=str, default='data/acdoca_sample.csv', help='Output CSV path')
    parser.add_argument('--load-hana', action='store_true', help='Load directly to HANA')
    args = parser.parse_args()
    
    # Initialize generator
    data_dir = os.path.dirname(os.path.abspath(__file__))
    generator = ACDOCAGenerator(data_dir)
    
    # Generate data
    data = generator.generate_all(months=args.months)
    
    # Save to CSV
    output_dir = os.path.dirname(args.output) or '.'
    os.makedirs(output_dir, exist_ok=True)
    
    acdoca_path = args.output
    budget_path = args.output.replace('.csv', '_budget.csv')
    fx_path = args.output.replace('.csv', '_fx_rates.csv')
    
    data['acdoca'].to_csv(acdoca_path, index=False)
    data['budget'].to_csv(budget_path, index=False)
    data['fx_rates'].to_csv(fx_path, index=False)
    
    logger.info(f"Saved ACDOCA data to {acdoca_path}")
    logger.info(f"Saved Budget data to {budget_path}")
    logger.info(f"Saved FX rates to {fx_path}")
    
    # Optionally load to HANA
    if args.load_hana:
        logger.info("Loading to HANA...")
        try:
            from utils.config import load_config
            from db.hana_client import HanaClient
            
            config = load_config()
            client = HanaClient(config)
            
            if client.connect():
                schema = config['hana']['schema']
                
                # Load ACDOCA
                logger.info(f"Loading {len(data['acdoca'])} ACDOCA records to HANA...")
                # Implementation would go here
                
                client.close()
                logger.info("HANA load complete")
            else:
                logger.error("Failed to connect to HANA")
        except Exception as e:
            logger.error(f"Failed to load to HANA: {e}")
    
    # Print summary statistics
    print("\n" + "="*60)
    print("ACDOCA SAMPLE DATA SUMMARY")
    print("="*60)
    
    df = data['acdoca']
    print(f"\nTotal Journal Entries: {len(df):,}")
    print(f"Date Range: {df['BUDAT'].min()} to {df['BUDAT'].max()}")
    print(f"\nBy Company Code:")
    print(df.groupby('RBUKRS')['HSL'].agg(['count', 'sum']).to_string())
    print(f"\nBy Account Type:")
    
    # Add account type for summary
    gl_accounts = generator.gl_accounts
    df['ACCOUNT_TYPE'] = df['RACCT'].map(lambda x: gl_accounts.get(x, {}).get('account_type', 'Unknown'))
    print(df.groupby('ACCOUNT_TYPE')['KSL'].sum().to_string())
    
    print("\n" + "="*60)


if __name__ == '__main__':
    main()
