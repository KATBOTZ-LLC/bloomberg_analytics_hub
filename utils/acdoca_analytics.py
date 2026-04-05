"""
ACDOCA Analytics Module

Provides financial analytics calculations on ACDOCA data:
- P&L aggregation
- Balance Sheet calculations
- Actual vs Budget variance
- Cost center analysis
- Trend analysis
"""

import pandas as pd
import numpy as np
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class ACDOCAAnalytics:
    """Analytics engine for ACDOCA data"""
    
    # Account type mappings for P&L aggregation
    PL_STRUCTURE = {
        'Revenue': {
            'accounts': ['400000', '401000', '402000', '403000'],
            'sign': -1,  # Credits are stored as negative
            'order': 1,
        },
        'Contra Revenue': {
            'accounts': ['410000'],
            'sign': 1,
            'order': 2,
        },
        'COGS': {
            'accounts': ['500000', '501000', '502000', '503000', '504000'],
            'sign': 1,
            'order': 3,
        },
        'Personnel': {
            'accounts': ['600000', '601000', '602000'],
            'sign': 1,
            'order': 4,
        },
        'Facilities': {
            'accounts': ['610000', '611000', '612000'],
            'sign': 1,
            'order': 5,
        },
        'Sales & Marketing': {
            'accounts': ['620000', '621000', '622000'],
            'sign': 1,
            'order': 6,
        },
        'R&D': {
            'accounts': ['630000', '631000'],
            'sign': 1,
            'order': 7,
        },
        'D&A': {
            'accounts': ['640000', '641000'],
            'sign': 1,
            'order': 8,
        },
        'G&A': {
            'accounts': ['650000', '651000', '652000', '653000', '654000'],
            'sign': 1,
            'order': 9,
        },
        'Interest Income': {
            'accounts': ['700000', '701000'],
            'sign': -1,
            'order': 10,
        },
        'Interest Expense': {
            'accounts': ['710000'],
            'sign': 1,
            'order': 11,
        },
        'FX Gain/Loss': {
            'accounts': ['720000', '721000'],
            'sign': 1,  # Net effect
            'order': 12,
        },
        'Tax Expense': {
            'accounts': ['800000', '801000'],
            'sign': 1,
            'order': 13,
        },
    }
    
    def __init__(self, df_acdoca: pd.DataFrame = None, df_budget: pd.DataFrame = None):
        """
        Initialize analytics with data
        
        Args:
            df_acdoca: ACDOCA actuals DataFrame
            df_budget: Budget DataFrame
        """
        self.df_acdoca = df_acdoca
        self.df_budget = df_budget
    
    def set_data(self, df_acdoca: pd.DataFrame, df_budget: pd.DataFrame = None):
        """Set or update the data"""
        self.df_acdoca = df_acdoca
        self.df_budget = df_budget
    
    def get_pl_summary(
        self,
        company_codes: List[str] = None,
        year: int = None,
        periods: List[int] = None,
        currency: str = 'USD'
    ) -> pd.DataFrame:
        """
        Generate P&L summary
        
        Args:
            company_codes: Filter by company codes
            year: Fiscal year
            periods: List of periods (1-12)
            currency: 'USD' for global, 'LOCAL' for company currency
        
        Returns:
            DataFrame with P&L line items
        """
        if self.df_acdoca is None or self.df_acdoca.empty:
            return pd.DataFrame()
        
        df = self.df_acdoca.copy()
        
        # Apply filters
        if company_codes:
            df = df[df['RBUKRS'].isin(company_codes)]
        if year:
            df = df[df['GJAHR'] == year]
        if periods:
            df = df[df['POPER'].isin(periods)]
        
        # Use appropriate amount column
        amount_col = 'KSL' if currency == 'USD' else 'HSL'
        
        # Aggregate by account
        account_totals = df.groupby('RACCT')[amount_col].sum().to_dict()
        
        # Build P&L structure
        pl_data = []
        for category, config in self.PL_STRUCTURE.items():
            total = sum(
                account_totals.get(acc, 0) * config['sign']
                for acc in config['accounts']
            )
            pl_data.append({
                'Category': category,
                'Amount': total,
                'Order': config['order'],
            })
        
        df_pl = pd.DataFrame(pl_data)
        df_pl = df_pl.sort_values('Order')
        
        # Calculate derived metrics
        revenue = df_pl[df_pl['Category'] == 'Revenue']['Amount'].sum()
        contra_rev = df_pl[df_pl['Category'] == 'Contra Revenue']['Amount'].sum()
        net_revenue = revenue - contra_rev
        
        cogs = df_pl[df_pl['Category'] == 'COGS']['Amount'].sum()
        gross_profit = net_revenue - cogs
        
        opex_categories = ['Personnel', 'Facilities', 'Sales & Marketing', 'R&D', 'D&A', 'G&A']
        total_opex = df_pl[df_pl['Category'].isin(opex_categories)]['Amount'].sum()
        
        ebitda = gross_profit - (total_opex - df_pl[df_pl['Category'] == 'D&A']['Amount'].sum())
        ebit = gross_profit - total_opex
        
        interest_net = (
            df_pl[df_pl['Category'] == 'Interest Expense']['Amount'].sum() -
            df_pl[df_pl['Category'] == 'Interest Income']['Amount'].sum()
        )
        fx = df_pl[df_pl['Category'] == 'FX Gain/Loss']['Amount'].sum()
        
        ebt = ebit - interest_net - fx
        tax = df_pl[df_pl['Category'] == 'Tax Expense']['Amount'].sum()
        net_income = ebt - tax
        
        # Add calculated rows
        calculated = [
            {'Category': 'Net Revenue', 'Amount': net_revenue, 'Order': 2.5},
            {'Category': 'Gross Profit', 'Amount': gross_profit, 'Order': 3.5},
            {'Category': 'Total OpEx', 'Amount': total_opex, 'Order': 9.5},
            {'Category': 'EBITDA', 'Amount': ebitda, 'Order': 9.6},
            {'Category': 'EBIT', 'Amount': ebit, 'Order': 9.7},
            {'Category': 'EBT', 'Amount': ebt, 'Order': 12.5},
            {'Category': 'Net Income', 'Amount': net_income, 'Order': 14},
        ]
        
        df_pl = pd.concat([df_pl, pd.DataFrame(calculated)], ignore_index=True)
        df_pl = df_pl.sort_values('Order').reset_index(drop=True)
        
        # Add margins
        if net_revenue != 0:
            df_pl['Margin %'] = (df_pl['Amount'] / net_revenue * 100).round(1)
        else:
            df_pl['Margin %'] = 0
        
        return df_pl[['Category', 'Amount', 'Margin %']]
    
    def get_actual_vs_budget(
        self,
        company_codes: List[str] = None,
        year: int = None,
        periods: List[int] = None
    ) -> pd.DataFrame:
        """
        Compare actuals to budget
        
        Returns:
            DataFrame with Actual, Budget, Variance columns
        """
        if self.df_acdoca is None or self.df_budget is None:
            return pd.DataFrame()
        
        df_act = self.df_acdoca.copy()
        df_bud = self.df_budget.copy()
        
        # Apply filters
        if company_codes:
            df_act = df_act[df_act['RBUKRS'].isin(company_codes)]
            df_bud = df_bud[df_bud['RBUKRS'].isin(company_codes)]
        if year:
            df_act = df_act[df_act['GJAHR'] == year]
            df_bud = df_bud[df_bud['GJAHR'] == year]
        if periods:
            df_act = df_act[df_act['POPER'].isin(periods)]
            df_bud = df_bud[df_bud['POPER'].isin(periods)]
        
        # Aggregate actuals by account
        act_totals = df_act.groupby('RACCT')['KSL'].sum()
        bud_totals = df_bud.groupby('RACCT')['KSL'].sum()
        
        # Build comparison by P&L category
        comparison = []
        for category, config in self.PL_STRUCTURE.items():
            actual = sum(act_totals.get(acc, 0) * config['sign'] for acc in config['accounts'])
            budget = sum(bud_totals.get(acc, 0) * config['sign'] for acc in config['accounts'])
            variance = actual - budget
            variance_pct = (variance / budget * 100) if budget != 0 else 0
            
            comparison.append({
                'Category': category,
                'Actual': actual,
                'Budget': budget,
                'Variance': variance,
                'Variance %': round(variance_pct, 1),
                'Order': config['order'],
            })
        
        df_comp = pd.DataFrame(comparison)
        df_comp = df_comp.sort_values('Order')
        
        return df_comp[['Category', 'Actual', 'Budget', 'Variance', 'Variance %']]
    
    def get_cost_center_analysis(
        self,
        company_codes: List[str] = None,
        year: int = None,
        periods: List[int] = None,
        top_n: int = 10
    ) -> pd.DataFrame:
        """
        Analyze spending by cost center
        
        Returns:
            DataFrame with cost center totals
        """
        if self.df_acdoca is None:
            return pd.DataFrame()
        
        df = self.df_acdoca.copy()
        
        # Filter for expense accounts only (5xxxxx, 6xxxxx, 7xxxxx)
        expense_accounts = [acc for acc in df['RACCT'].unique() 
                          if acc.startswith(('5', '6', '7'))]
        df = df[df['RACCT'].isin(expense_accounts)]
        
        # Apply filters
        if company_codes:
            df = df[df['RBUKRS'].isin(company_codes)]
        if year:
            df = df[df['GJAHR'] == year]
        if periods:
            df = df[df['POPER'].isin(periods)]
        
        # Aggregate by cost center
        cc_totals = df.groupby('RCNTR').agg({
            'KSL': 'sum',
            'BELNR': 'nunique',  # Document count
        }).reset_index()
        
        cc_totals.columns = ['Cost Center', 'Total Spend (USD)', 'Document Count']
        cc_totals = cc_totals.sort_values('Total Spend (USD)', ascending=False)
        
        # Calculate percentage of total
        total_spend = cc_totals['Total Spend (USD)'].sum()
        cc_totals['% of Total'] = (cc_totals['Total Spend (USD)'] / total_spend * 100).round(1)
        
        return cc_totals.head(top_n)
    
    def get_monthly_trend(
        self,
        metric: str = 'Revenue',
        company_codes: List[str] = None,
        years: List[int] = None
    ) -> pd.DataFrame:
        """
        Get monthly trend for a metric
        
        Args:
            metric: P&L category name
            company_codes: Filter by company
            years: List of years to include
        
        Returns:
            DataFrame with monthly values
        """
        if self.df_acdoca is None:
            return pd.DataFrame()
        
        df = self.df_acdoca.copy()
        
        # Apply filters
        if company_codes:
            df = df[df['RBUKRS'].isin(company_codes)]
        if years:
            df = df[df['GJAHR'].isin(years)]
        
        # Get accounts for the metric
        config = self.PL_STRUCTURE.get(metric)
        if not config:
            return pd.DataFrame()
        
        df = df[df['RACCT'].isin(config['accounts'])]
        
        # Aggregate by year/month
        monthly = df.groupby(['GJAHR', 'POPER'])['KSL'].sum().reset_index()
        monthly['Amount'] = monthly['KSL'] * config['sign']
        monthly['Period'] = monthly.apply(
            lambda x: f"{int(x['GJAHR'])}-{int(x['POPER']):02d}", axis=1
        )
        
        return monthly[['Period', 'GJAHR', 'POPER', 'Amount']]
    
    def get_yoy_comparison(
        self,
        year: int,
        company_codes: List[str] = None,
        periods: List[int] = None
    ) -> pd.DataFrame:
        """
        Compare current year to prior year
        
        Returns:
            DataFrame with YoY comparison
        """
        if self.df_acdoca is None:
            return pd.DataFrame()
        
        prior_year = year - 1
        
        # Get P&L for both years
        current = self.get_pl_summary(company_codes, year, periods)
        prior = self.get_pl_summary(company_codes, prior_year, periods)
        
        if current.empty or prior.empty:
            return pd.DataFrame()
        
        # Merge
        merged = current.merge(prior, on='Category', suffixes=('_CY', '_PY'), how='left')
        merged['YoY Change'] = merged['Amount_CY'] - merged['Amount_PY']
        merged['YoY %'] = ((merged['Amount_CY'] / merged['Amount_PY'] - 1) * 100).round(1)
        merged['YoY %'] = merged['YoY %'].fillna(0)
        
        return merged[['Category', 'Amount_CY', 'Amount_PY', 'YoY Change', 'YoY %']]
    
    def get_kpis(
        self,
        company_codes: List[str] = None,
        year: int = None,
        periods: List[int] = None
    ) -> Dict:
        """
        Calculate key financial KPIs
        
        Returns:
            Dictionary of KPI values
        """
        pl = self.get_pl_summary(company_codes, year, periods)
        
        if pl.empty:
            return {}
        
        def get_amount(category):
            row = pl[pl['Category'] == category]
            return row['Amount'].iloc[0] if not row.empty else 0
        
        revenue = get_amount('Net Revenue')
        gross_profit = get_amount('Gross Profit')
        ebitda = get_amount('EBITDA')
        ebit = get_amount('EBIT')
        net_income = get_amount('Net Income')
        
        return {
            'Revenue': revenue,
            'Gross Profit': gross_profit,
            'Gross Margin %': round(gross_profit / revenue * 100, 1) if revenue else 0,
            'EBITDA': ebitda,
            'EBITDA Margin %': round(ebitda / revenue * 100, 1) if revenue else 0,
            'EBIT': ebit,
            'EBIT Margin %': round(ebit / revenue * 100, 1) if revenue else 0,
            'Net Income': net_income,
            'Net Margin %': round(net_income / revenue * 100, 1) if revenue else 0,
        }


# Convenience function for quick analysis
def analyze_acdoca(df_acdoca: pd.DataFrame, df_budget: pd.DataFrame = None) -> ACDOCAAnalytics:
    """Create an analytics instance with data loaded"""
    return ACDOCAAnalytics(df_acdoca, df_budget)
