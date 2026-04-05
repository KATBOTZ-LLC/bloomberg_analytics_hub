"""
Data service layer for retrieving financial data from SAP HANA
Provides clean interface for dashboard queries
"""

import logging
import pandas as pd
from datetime import datetime, timedelta
from db.hana_client import HanaClient


class FinancialDataService:
    """Service for retrieving and processing financial data for dashboard"""

    def __init__(self, config):
        """Initialize data service with HANA client"""
        self.logger = logging.getLogger(__name__)
        self.hana_client = HanaClient(config)
        self.schema = config['hana']['schema']
        self.connected = False

        # Simple in-memory cache with TTL
        self._cache = {}
        self._cache_ttl = timedelta(minutes=1)  # Cache for 1 minute

    def connect(self):
        """Establish connection to HANA"""
        self.connected = self.hana_client.connect()
        return self.connected

    def close(self):
        """Close HANA connection"""
        if self.hana_client:
            self.hana_client.close()
            self.connected = False

    def _get_cached(self, key):
        """Get data from cache if not expired"""
        if key in self._cache:
            data, timestamp = self._cache[key]
            if datetime.now() - timestamp < self._cache_ttl:
                self.logger.debug(f"Cache hit for key: {key}")
                return data
            else:
                # Cache expired, remove it
                del self._cache[key]
                self.logger.debug(f"Cache expired for key: {key}")
        return None

    def _set_cached(self, key, data):
        """Store data in cache with timestamp"""
        self._cache[key] = (data, datetime.now())
        self.logger.debug(f"Cache set for key: {key}")

    def get_financial_ratios(self, limit=50):
        """
        Retrieve financial ratios data - latest records only

        Args:
            limit (int): Maximum number of records to retrieve (default 50, latest by inserted_at)

        Returns:
            pd.DataFrame: Financial ratios data (most recent records)
        """
        if not self.connected:
            self.logger.error("Not connected to HANA")
            return pd.DataFrame()

        # Check cache first
        cache_key = f"financial_ratios_{limit}"
        cached_data = self._get_cached(cache_key)
        if cached_data is not None:
            return cached_data

        cursor = None
        try:
            query = f"""
            SELECT
                "DATA_DATE",
                "TICKER",
                "IDENTIFIER_TYPE",
                "IDENTIFIER_VALUE",
                "ID_BB_GLOBAL",
                "TOT_DEBT_TO_TOT_ASSET",
                "CASH_DVD_COVERAGE",
                "TOT_DEBT_TO_EBITDA",
                "CUR_RATIO",
                "QUICK_RATIO",
                "GROSS_MARGIN",
                "INTEREST_COVERAGE_RATIO",
                "EBITDA_MARGIN",
                "TOT_LIAB_AND_EQY",
                "NET_DEBT_TO_SHRHLDR_EQTY",
                "INSERTED_AT"
            FROM "{self.schema}"."FINANCIAL_RATIOS"
            ORDER BY "INSERTED_AT" DESC
            LIMIT {limit}
            """

            cursor = self.hana_client.connection.cursor()
            cursor.execute(query)

            columns = [desc[0] for desc in cursor.description]
            data = cursor.fetchall()

            df = pd.DataFrame(data, columns=columns)
            self.logger.info(f"Retrieved {len(df)} financial ratio records")

            # HANA returns decimal.Decimal — convert numeric columns to float
            skip_cols = {'TICKER', 'IDENTIFIER_TYPE', 'IDENTIFIER_VALUE',
                         'ID_BB_GLOBAL', 'DATA_DATE', 'INSERTED_AT'}
            for col in df.columns:
                if col not in skip_cols:
                    try:
                        df[col] = pd.to_numeric(df[col])
                    except (ValueError, TypeError):
                        pass

            # Cache the result
            self._set_cached(cache_key, df)

            return df

        except Exception as e:
            self.logger.error(f"Error retrieving financial ratios: {str(e)}")
            return pd.DataFrame()
        finally:
            if cursor:
                cursor.close()

    def get_advanced_financials(self, tickers=None, limit=100):
        """
        Retrieve advanced financial data from FINANCIAL_DATA_ADVANCED

        Args:
            tickers (list): Optional list of tickers to filter by
            limit (int): Maximum number of records to retrieve

        Returns:
            pd.DataFrame: Advanced financial data
        """
        if not self.connected:
            self.logger.error("Not connected to HANA")
            return pd.DataFrame()

        cache_key = f"advanced_financials_{','.join(tickers) if tickers else 'all'}_{limit}"
        cached_data = self._get_cached(cache_key)
        if cached_data is not None:
            return cached_data

        cursor = None
        try:
            if tickers:
                placeholders = ', '.join(['?' for _ in tickers])
                query = f"""
                SELECT *
                FROM "{self.schema}"."FINANCIAL_DATA_ADVANCED"
                WHERE "TICKER" IN ({placeholders})
                ORDER BY "TICKER", "INSERTED_AT" DESC
                LIMIT {limit}
                """
                cursor = self.hana_client.connection.cursor()
                cursor.execute(query, tickers)
            else:
                query = f"""
                SELECT *
                FROM "{self.schema}"."FINANCIAL_DATA_ADVANCED"
                ORDER BY "INSERTED_AT" DESC
                LIMIT {limit}
                """
                cursor = self.hana_client.connection.cursor()
                cursor.execute(query)

            columns = [desc[0] for desc in cursor.description]
            data = cursor.fetchall()

            df = pd.DataFrame(data, columns=columns)
            self.logger.info(f"Retrieved {len(df)} advanced financial records")

            # HANA returns decimal.Decimal — convert numeric columns to float
            skip_cols = {'TICKER', 'IDENTIFIER_TYPE', 'IDENTIFIER_VALUE',
                         'ID_BB_COMPANY', 'ID_BB_GLOBAL', 'ID_BB_GLOBAL_COMPANY',
                         'FISCAL_YEAR_PERIOD', 'ACCOUNTING_STANDARD',
                         'DATA_DATE', 'INSERTED_AT'}
            for col in df.columns:
                if col not in skip_cols:
                    try:
                        df[col] = pd.to_numeric(df[col])
                    except (ValueError, TypeError):
                        pass

            self._set_cached(cache_key, df)
            return df

        except Exception as e:
            self.logger.error(f"Error retrieving advanced financials: {str(e)}")
            return pd.DataFrame()
        finally:
            if cursor:
                cursor.close()

    def get_ticker_list(self):
        """
        Get unique list of tickers from FINANCIAL_RATIOS table

        Returns:
            list: Unique ticker symbols
        """
        if not self.connected:
            return []

        cursor = None
        try:
            query = f"""
            SELECT DISTINCT "TICKER"
            FROM "{self.schema}"."FINANCIAL_RATIOS"
            WHERE "TICKER" IS NOT NULL
            ORDER BY "TICKER"
            """

            cursor = self.hana_client.connection.cursor()
            cursor.execute(query)
            tickers = [row[0] for row in cursor.fetchall()]

            return tickers

        except Exception as e:
            self.logger.error(f"Error retrieving ticker list: {str(e)}")
            return []
        finally:
            if cursor:
                cursor.close()

    def get_ticker_data(self, ticker):
        """
        Get all data for a specific ticker from FINANCIAL_RATIOS and FINANCIAL_DATA_ADVANCED

        Args:
            ticker (str): Stock ticker symbol

        Returns:
            dict: Dictionary with 'ratios' and 'advanced' DataFrames
        """
        if not self.connected:
            return {'ratios': pd.DataFrame(), 'advanced': pd.DataFrame()}

        cursor = None
        try:
            cursor = self.hana_client.connection.cursor()

            # Get ratios data
            ratios_query = f"""
            SELECT * FROM "{self.schema}"."FINANCIAL_RATIOS"
            WHERE "TICKER" = ?
            ORDER BY "INSERTED_AT" DESC
            """
            cursor.execute(ratios_query, [ticker])
            columns = [desc[0] for desc in cursor.description]
            ratios_df = pd.DataFrame(cursor.fetchall(), columns=columns)

            # Get advanced data
            advanced_query = f"""
            SELECT * FROM "{self.schema}"."FINANCIAL_DATA_ADVANCED"
            WHERE "TICKER" = ?
            ORDER BY "INSERTED_AT" DESC
            """
            cursor.execute(advanced_query, [ticker])
            columns = [desc[0] for desc in cursor.description]
            advanced_df = pd.DataFrame(cursor.fetchall(), columns=columns)

            return {
                'ratios': ratios_df,
                'advanced': advanced_df
            }

        except Exception as e:
            self.logger.error(f"Error retrieving ticker data: {str(e)}")
            return {'ratios': pd.DataFrame(), 'advanced': pd.DataFrame()}
        finally:
            if cursor:
                cursor.close()

    def get_summary_stats(self):
        """
        Get summary statistics for dashboard

        Returns:
            dict: Summary statistics
        """
        if not self.connected:
            return {}

        cursor = None
        try:
            cursor = self.hana_client.connection.cursor()

            # Count records in FINANCIAL_RATIOS table
            cursor.execute(f'SELECT COUNT(*) FROM "{self.schema}"."FINANCIAL_RATIOS"')
            ratios_count = cursor.fetchone()[0]

            # Get unique tickers
            cursor.execute(f'SELECT COUNT(DISTINCT "TICKER") FROM "{self.schema}"."FINANCIAL_RATIOS"')
            unique_tickers = cursor.fetchone()[0]

            # Get last update time
            cursor.execute(f'SELECT MAX("INSERTED_AT") FROM "{self.schema}"."FINANCIAL_RATIOS"')
            last_update = cursor.fetchone()[0]

            # Count advanced records
            cursor.execute(f'SELECT COUNT(*) FROM "{self.schema}"."FINANCIAL_DATA_ADVANCED"')
            advanced_count = cursor.fetchone()[0]

            return {
                'ratios_count': ratios_count,
                'advanced_count': advanced_count,
                'unique_tickers': unique_tickers,
                'last_update': last_update
            }

        except Exception as e:
            self.logger.error(f"Error retrieving summary stats: {str(e)}")
            return {}
        finally:
            if cursor:
                cursor.close()

    def get_dashboard_stats(self):
        """
        Get comprehensive dashboard statistics for sidebar display

        Returns:
            dict: Dashboard statistics including counts, data quality, timestamps
        """
        if not self.connected:
            return {
                'total_records': 0,
                'annual_records': 0,
                'unique_tickers': 0,
                'last_sync': None,
                'data_quality': 0.0,
                'connection_status': 'Disconnected'
            }

        cursor = None
        try:
            cursor = self.hana_client.connection.cursor()

            # Count records in FINANCIAL_RATIOS table
            cursor.execute(f'SELECT COUNT(*) FROM "{self.schema}"."FINANCIAL_RATIOS"')
            ratios_count = cursor.fetchone()[0]

            # Count records in ANNUAL_FINANCIALS_10K table
            try:
                cursor.execute(f'SELECT COUNT(*) FROM "{self.schema}"."ANNUAL_FINANCIALS_10K"')
                annual_count = cursor.fetchone()[0]
            except Exception:
                annual_count = 0

            # Get unique tickers
            cursor.execute(f'SELECT COUNT(DISTINCT "TICKER") FROM "{self.schema}"."FINANCIAL_RATIOS"')
            unique_tickers = cursor.fetchone()[0]

            # Get last update time (most recent insert)
            cursor.execute(f'SELECT MAX("INSERTED_AT") FROM "{self.schema}"."FINANCIAL_RATIOS"')
            last_sync = cursor.fetchone()[0]

            # Calculate data quality (percentage of non-null values in key columns)
            cursor.execute(f'''
                SELECT
                    COUNT(*) as total,
                    COUNT("TICKER") as ticker_count,
                    COUNT("GROSS_MARGIN") as gross_margin_count,
                    COUNT("EBITDA_MARGIN") as ebitda_margin_count,
                    COUNT("CUR_RATIO") as cur_ratio_count,
                    COUNT("QUICK_RATIO") as quick_ratio_count
                FROM "{self.schema}"."FINANCIAL_RATIOS"
            ''')
            quality_row = cursor.fetchone()
            if quality_row and quality_row[0] > 0:
                total = quality_row[0]
                filled_count = sum(quality_row[1:])
                total_possible = total * 5  # 5 key columns
                data_quality = (filled_count / total_possible) * 100 if total_possible > 0 else 0
            else:
                data_quality = 0.0

            return {
                'total_records': ratios_count,
                'annual_records': annual_count,
                'unique_tickers': unique_tickers,
                'last_sync': last_sync,
                'data_quality': round(data_quality, 1),
                'connection_status': 'Connected'
            }

        except Exception as e:
            self.logger.error(f"Error retrieving dashboard stats: {str(e)}")
            return {
                'total_records': 0,
                'annual_records': 0,
                'unique_tickers': 0,
                'last_sync': None,
                'data_quality': 0.0,
                'connection_status': 'Error'
            }
        finally:
            if cursor:
                cursor.close()

    def get_annual_financials(self, tickers=None):
        """
        Retrieve annual financial data from ANNUAL_FINANCIALS_10K table.
        Deduplicates to latest REPORT_DATE per (TICKER, FISCAL_YEAR).

        Args:
            tickers (list): Optional list of tickers to filter by

        Returns:
            pd.DataFrame: Annual financials data (one row per ticker per year)
        """
        if not self.connected:
            self.logger.error("Not connected to HANA")
            return pd.DataFrame()

        # Check cache first
        cache_key = f"annual_financials_{','.join(tickers) if tickers else 'all'}"
        cached_data = self._get_cached(cache_key)
        if cached_data is not None:
            return cached_data

        cursor = None
        try:
            # Subquery deduplicates: one row per (TICKER, FISCAL_YEAR) using latest REPORT_DATE
            if tickers:
                placeholders = ', '.join(['?' for _ in tickers])
                query = f"""
                SELECT A.*
                FROM "{self.schema}"."ANNUAL_FINANCIALS_10K" A
                INNER JOIN (
                    SELECT "TICKER", "FISCAL_YEAR", MAX("REPORT_DATE") AS "MAX_DATE"
                    FROM "{self.schema}"."ANNUAL_FINANCIALS_10K"
                    WHERE "TICKER" IN ({placeholders})
                    GROUP BY "TICKER", "FISCAL_YEAR"
                ) B ON A."TICKER" = B."TICKER"
                   AND A."FISCAL_YEAR" = B."FISCAL_YEAR"
                   AND A."REPORT_DATE" = B."MAX_DATE"
                ORDER BY A."TICKER", A."FISCAL_YEAR" DESC
                """
                cursor = self.hana_client.connection.cursor()
                cursor.execute(query, tickers)
            else:
                query = f"""
                SELECT A.*
                FROM "{self.schema}"."ANNUAL_FINANCIALS_10K" A
                INNER JOIN (
                    SELECT "TICKER", "FISCAL_YEAR", MAX("REPORT_DATE") AS "MAX_DATE"
                    FROM "{self.schema}"."ANNUAL_FINANCIALS_10K"
                    GROUP BY "TICKER", "FISCAL_YEAR"
                ) B ON A."TICKER" = B."TICKER"
                   AND A."FISCAL_YEAR" = B."FISCAL_YEAR"
                   AND A."REPORT_DATE" = B."MAX_DATE"
                ORDER BY A."TICKER", A."FISCAL_YEAR" DESC
                """
                cursor = self.hana_client.connection.cursor()
                cursor.execute(query)

            columns = [desc[0] for desc in cursor.description]
            data = cursor.fetchall()

            df = pd.DataFrame(data, columns=columns)
            self.logger.info(f"Retrieved {len(df)} annual financials records (deduped)")

            # HANA returns decimal.Decimal for DECIMAL columns — convert all to float
            skip_cols = {'TICKER', 'REPORT_DATE'}
            for col in df.columns:
                if col not in skip_cols:
                    try:
                        df[col] = pd.to_numeric(df[col])
                    except (ValueError, TypeError):
                        pass

            # Normalize monetary columns to millions for dashboard consistency
            # (FINANCIAL_RATIOS and FINANCIAL_DATA_ADVANCED already store in millions)
            money_cols = [
                'SALES_REV_TURN', 'GROSS_PROFIT', 'IS_OPER_INC', 'EBIT', 'EBITDA',
                'PRETAX_INC', 'NET_INCOME', 'IS_SGA_EXPENSE',
                'IS_DEPRECIATION_AND_AMORTIZATION', 'IS_INT_EXPENSE', 'IS_INC_TAX_EXP',
                'TOT_LIAB_AND_EQY', 'BS_CUR_LIAB', 'BS_LT_BORROW', 'BS_TOT_ASSET',
                'BS_SH_OUT', 'CF_FREE_CASH_FLOW', 'CF_CASH_FROM_OPER',
                'CF_CAP_EXPEND_PRPTY_ADD'
            ]
            for col in money_cols:
                if col in df.columns:
                    df[col] = df[col] / 1_000_000

            # Cache the result
            self._set_cached(cache_key, df)

            return df

        except Exception as e:
            self.logger.error(f"Error retrieving annual financials: {str(e)}")
            return pd.DataFrame()
        finally:
            if cursor:
                cursor.close()

    def get_comparison_data(self, tickers, metrics):
        """
        Get comparison data for multiple tickers and metrics

        Args:
            tickers (list): List of ticker symbols
            metrics (list): List of metric names

        Returns:
            pd.DataFrame: Comparison data
        """
        if not self.connected or not tickers or not metrics:
            return pd.DataFrame()

        cursor = None
        try:
            # Validate metrics against allowed columns to prevent SQL injection
            allowed_metrics = {
                'GROSS_MARGIN', 'EBITDA_MARGIN', 'CUR_RATIO', 'QUICK_RATIO',
                'TOT_DEBT_TO_TOT_ASSET', 'INTEREST_COVERAGE_RATIO', 'CASH_DVD_COVERAGE',
                'TOT_DEBT_TO_EBITDA', 'NET_DEBT_TO_SHRHLDR_EQTY', 'TOT_LIAB_AND_EQY'
            }

            # Filter metrics to only allowed ones
            safe_metrics = [m for m in metrics if m in allowed_metrics]
            if not safe_metrics:
                self.logger.warning("No valid metrics provided for comparison")
                return pd.DataFrame()

            # Build column list with proper quoting
            column_list = ', '.join([f'"{metric}"' for metric in safe_metrics])

            # Build parameterized query for tickers
            placeholders = ', '.join(['?' for _ in tickers])

            query = f"""
            SELECT
                "TICKER",
                {column_list}
            FROM "{self.schema}"."FINANCIAL_RATIOS"
            WHERE "TICKER" IN ({placeholders})
            """

            cursor = self.hana_client.connection.cursor()
            cursor.execute(query, tickers)

            columns = [desc[0] for desc in cursor.description]
            data = cursor.fetchall()

            df = pd.DataFrame(data, columns=columns)
            return df

        except Exception as e:
            self.logger.error(f"Error retrieving comparison data: {str(e)}")
            return pd.DataFrame()
        finally:
            if cursor:
                cursor.close()

    # =========================================================================
    # ACDOCA (Universal Journal) Methods
    # =========================================================================

    def get_acdoca_data(
        self,
        company_codes: list = None,
        year: int = None,
        periods: list = None,
        accounts: list = None,
        cost_centers: list = None,
        limit: int = 10000
    ):
        """
        Retrieve ACDOCA journal entries with filters

        Args:
            company_codes: List of company codes to filter
            year: Fiscal year
            periods: List of posting periods (1-12)
            accounts: List of GL accounts
            cost_centers: List of cost centers
            limit: Maximum records to return

        Returns:
            pd.DataFrame: ACDOCA data
        """
        if not self.connected:
            self.logger.error("Not connected to HANA")
            return pd.DataFrame()

        cursor = None
        try:
            # Build dynamic query with filters
            query = f"""
            SELECT
                "RBUKRS", "GJAHR", "BELNR", "DOCLN",
                "BLDAT", "BUDAT",
                "RACCT", "RCNTR", "PRCTR", "SEGMENT",
                "HSL", "RHCUR", "KSL", "RKCUR",
                "POPER", "DRCRK", "BLART",
                "SGTXT", "BKTXT"
            FROM "{self.schema}"."ACDOCA_SAMPLE"
            WHERE 1=1
            """
            params = []

            if company_codes:
                placeholders = ', '.join(['?' for _ in company_codes])
                query += f' AND "RBUKRS" IN ({placeholders})'
                params.extend(company_codes)

            if year:
                query += ' AND "GJAHR" = ?'
                params.append(year)

            if periods:
                placeholders = ', '.join(['?' for _ in periods])
                query += f' AND "POPER" IN ({placeholders})'
                params.extend(periods)

            if accounts:
                placeholders = ', '.join(['?' for _ in accounts])
                query += f' AND "RACCT" IN ({placeholders})'
                params.extend(accounts)

            if cost_centers:
                placeholders = ', '.join(['?' for _ in cost_centers])
                query += f' AND "RCNTR" IN ({placeholders})'
                params.extend(cost_centers)

            query += f' ORDER BY "BUDAT" DESC, "BELNR", "DOCLN" LIMIT {limit}'

            cursor = self.hana_client.connection.cursor()
            cursor.execute(query, params)

            columns = [desc[0] for desc in cursor.description]
            data = cursor.fetchall()

            df = pd.DataFrame(data, columns=columns)
            self.logger.info(f"Retrieved {len(df)} ACDOCA records")

            # Convert decimal columns
            for col in ['HSL', 'KSL']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col])

            return df

        except Exception as e:
            self.logger.error(f"Error retrieving ACDOCA data: {str(e)}")
            return pd.DataFrame()
        finally:
            if cursor:
                cursor.close()

    def get_acdoca_budget(
        self,
        company_codes: list = None,
        year: int = None,
        periods: list = None
    ):
        """
        Retrieve budget data

        Args:
            company_codes: List of company codes
            year: Fiscal year
            periods: List of periods

        Returns:
            pd.DataFrame: Budget data
        """
        if not self.connected:
            self.logger.error("Not connected to HANA")
            return pd.DataFrame()

        cursor = None
        try:
            query = f"""
            SELECT
                "RBUKRS", "GJAHR", "POPER",
                "RACCT", "RCNTR", "PRCTR", "SEGMENT",
                "HSL", "RHCUR", "KSL", "VERSION"
            FROM "{self.schema}"."ACDOCA_BUDGET"
            WHERE 1=1
            """
            params = []

            if company_codes:
                placeholders = ', '.join(['?' for _ in company_codes])
                query += f' AND "RBUKRS" IN ({placeholders})'
                params.extend(company_codes)

            if year:
                query += ' AND "GJAHR" = ?'
                params.append(year)

            if periods:
                placeholders = ', '.join(['?' for _ in periods])
                query += f' AND "POPER" IN ({placeholders})'
                params.extend(periods)

            cursor = self.hana_client.connection.cursor()
            cursor.execute(query, params)

            columns = [desc[0] for desc in cursor.description]
            data = cursor.fetchall()

            df = pd.DataFrame(data, columns=columns)
            self.logger.info(f"Retrieved {len(df)} budget records")

            for col in ['HSL', 'KSL']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col])

            return df

        except Exception as e:
            self.logger.error(f"Error retrieving budget data: {str(e)}")
            return pd.DataFrame()
        finally:
            if cursor:
                cursor.close()

    def get_acdoca_summary(
        self,
        company_codes: list = None,
        year: int = None,
        group_by: str = 'account'
    ):
        """
        Get aggregated ACDOCA summary

        Args:
            company_codes: List of company codes
            year: Fiscal year
            group_by: 'account', 'cost_center', 'profit_center', 'period'

        Returns:
            pd.DataFrame: Aggregated summary
        """
        if not self.connected:
            return pd.DataFrame()

        cursor = None
        try:
            # Determine grouping column
            group_col_map = {
                'account': '"RACCT"',
                'cost_center': '"RCNTR"',
                'profit_center': '"PRCTR"',
                'period': '"POPER"',
                'segment': '"SEGMENT"',
            }
            group_col = group_col_map.get(group_by, '"RACCT"')

            query = f"""
            SELECT
                {group_col} as "GROUP_KEY",
                SUM("HSL") as "TOTAL_LOCAL",
                SUM("KSL") as "TOTAL_USD",
                COUNT(*) as "LINE_COUNT",
                COUNT(DISTINCT "BELNR") as "DOC_COUNT"
            FROM "{self.schema}"."ACDOCA_SAMPLE"
            WHERE 1=1
            """
            params = []

            if company_codes:
                placeholders = ', '.join(['?' for _ in company_codes])
                query += f' AND "RBUKRS" IN ({placeholders})'
                params.extend(company_codes)

            if year:
                query += ' AND "GJAHR" = ?'
                params.append(year)

            query += f' GROUP BY {group_col} ORDER BY SUM("KSL") DESC'

            cursor = self.hana_client.connection.cursor()
            cursor.execute(query, params)

            columns = [desc[0] for desc in cursor.description]
            data = cursor.fetchall()

            df = pd.DataFrame(data, columns=columns)

            for col in ['TOTAL_LOCAL', 'TOTAL_USD']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col])

            return df

        except Exception as e:
            self.logger.error(f"Error retrieving ACDOCA summary: {str(e)}")
            return pd.DataFrame()
        finally:
            if cursor:
                cursor.close()

    def get_acdoca_pl_trend(
        self,
        company_codes: list = None,
        years: list = None
    ):
        """
        Get monthly P&L trend for charts

        Args:
            company_codes: List of company codes
            years: List of years

        Returns:
            pd.DataFrame: Monthly aggregated P&L data
        """
        if not self.connected:
            return pd.DataFrame()

        cursor = None
        try:
            query = f"""
            SELECT
                "GJAHR",
                "POPER",
                "RACCT",
                SUM("KSL") as "AMOUNT_USD"
            FROM "{self.schema}"."ACDOCA_SAMPLE"
            WHERE 1=1
            """
            params = []

            if company_codes:
                placeholders = ', '.join(['?' for _ in company_codes])
                query += f' AND "RBUKRS" IN ({placeholders})'
                params.extend(company_codes)

            if years:
                placeholders = ', '.join(['?' for _ in years])
                query += f' AND "GJAHR" IN ({placeholders})'
                params.extend(years)

            query += ' GROUP BY "GJAHR", "POPER", "RACCT" ORDER BY "GJAHR", "POPER"'

            cursor = self.hana_client.connection.cursor()
            cursor.execute(query, params)

            columns = [desc[0] for desc in cursor.description]
            data = cursor.fetchall()

            df = pd.DataFrame(data, columns=columns)

            if 'AMOUNT_USD' in df.columns:
                df['AMOUNT_USD'] = pd.to_numeric(df['AMOUNT_USD'])

            return df

        except Exception as e:
            self.logger.error(f"Error retrieving P&L trend: {str(e)}")
            return pd.DataFrame()
        finally:
            if cursor:
                cursor.close()

    def get_acdoca_stats(self):
        """
        Get ACDOCA statistics for dashboard sidebar

        Returns:
            dict: Statistics including record counts, date range, etc.
        """
        if not self.connected:
            return {
                'acdoca_records': 0,
                'budget_records': 0,
                'company_count': 0,
                'date_range': None,
            }

        cursor = None
        try:
            cursor = self.hana_client.connection.cursor()

            # ACDOCA record count
            cursor.execute(f'SELECT COUNT(*) FROM "{self.schema}"."ACDOCA_SAMPLE"')
            acdoca_count = cursor.fetchone()[0]

            # Budget record count
            try:
                cursor.execute(f'SELECT COUNT(*) FROM "{self.schema}"."ACDOCA_BUDGET"')
                budget_count = cursor.fetchone()[0]
            except:
                budget_count = 0

            # Company count
            cursor.execute(f'SELECT COUNT(DISTINCT "RBUKRS") FROM "{self.schema}"."ACDOCA_SAMPLE"')
            company_count = cursor.fetchone()[0]

            # Date range
            cursor.execute(f'SELECT MIN("BUDAT"), MAX("BUDAT") FROM "{self.schema}"."ACDOCA_SAMPLE"')
            date_row = cursor.fetchone()
            date_range = f"{date_row[0]} to {date_row[1]}" if date_row[0] else None

            return {
                'acdoca_records': acdoca_count,
                'budget_records': budget_count,
                'company_count': company_count,
                'date_range': date_range,
            }

        except Exception as e:
            self.logger.error(f"Error retrieving ACDOCA stats: {str(e)}")
            return {
                'acdoca_records': 0,
                'budget_records': 0,
                'company_count': 0,
                'date_range': None,
            }
        finally:
            if cursor:
                cursor.close()

    def get_ml_models_info(self):
        """Get information about trained ML models"""
        if not self.connected:
            return []

        cursor = None
        try:
            cursor = self.hana_client.connection.cursor()
            
            cursor.execute("""
                SELECT "MODEL_NAME", "MODEL_TYPE", "VERSION", 
                       "TRAINING_ROWS", "CREATED_AT"
                FROM "BLOOMBERG_ML"."ML_MODELS"
                WHERE "IS_ACTIVE" = 1
                ORDER BY "MODEL_NAME"
            """)
            
            columns = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()
            
            models = []
            for row in rows:
                models.append({
                    "name": row[0],
                    "type": row[1],
                    "version": row[2],
                    "training_rows": row[3],
                    "trained_at": row[4].strftime("%Y-%m-%d %H:%M") if row[4] else None
                })
            
            return models

        except Exception as e:
            self.logger.error(f"Error retrieving ML models: {str(e)}")
            return []
        finally:
            if cursor:
                cursor.close()

    def get_latest_training_run(self):
        """Get info about the latest ML training run"""
        if not self.connected:
            return None

        cursor = None
        try:
            cursor = self.hana_client.connection.cursor()
            
            cursor.execute("""
                SELECT "RUN_ID", "STATUS", "MODELS_TRAINED", 
                       "DATA_ROWS_USED", "START_TIME", "END_TIME"
                FROM "BLOOMBERG_ML"."ML_TRAINING_RUNS"
                ORDER BY "RUN_ID" DESC
                LIMIT 1
            """)
            
            row = cursor.fetchone()
            if row:
                return {
                    "run_id": row[0],
                    "status": row[1],
                    "models_trained": row[2],
                    "data_rows": row[3],
                    "started": row[4].strftime("%Y-%m-%d %H:%M") if row[4] else None,
                    "ended": row[5].strftime("%Y-%m-%d %H:%M") if row[5] else None
                }
            return None

        except Exception as e:
            self.logger.error(f"Error retrieving training run: {str(e)}")
            return None
        finally:
            if cursor:
                cursor.close()

