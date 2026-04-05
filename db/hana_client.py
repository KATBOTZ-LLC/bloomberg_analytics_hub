"""
SAP HANA database client for storing Bloomberg financial data
Enhanced with ingestion logging capabilities
"""

import datetime
import logging
import json

# Import SAP HANA Python client
try:
    from hdbcli import dbapi
    HDBCLI_AVAILABLE = True
except ImportError:
    HDBCLI_AVAILABLE = False
    logging.warning("hdbcli package not installed. SAP HANA integration will not work.")
    logging.warning("Install using: pip install hdbcli")

class HanaClient:
    """Client for interacting with SAP HANA database."""

    def __init__(self, config):
        """
        Initialize the SAP HANA client with configuration.

        Args:
            config (dict): Configuration parameters
        """
        self.logger = logging.getLogger(__name__)

        if not HDBCLI_AVAILABLE:
            self.logger.error("hdbcli package not installed. Cannot use SAP HANA integration.")
            raise ImportError("hdbcli package not installed")

        # Set HANA connection parameters
        self.address = config['hana']['address']
        self.port = config['hana']['port']
        self.user = config['hana']['user']
        self.password = config['hana']['password']
        self.schema = config['hana']['schema']

        # Connection will be set later
        self.connection = None

        # Define table schemas for different data types
        self.table_schemas = {
            'FINANCIAL_RATIOS': """
                CREATE TABLE "{schema}"."{table}" (
                    "ID" INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                    "DATA_DATE" DATE,
                    "TICKER" NVARCHAR(50),
                    "IDENTIFIER_TYPE" NVARCHAR(20),
                    "IDENTIFIER_VALUE" NVARCHAR(100),
                    "ID_BB_GLOBAL" NVARCHAR(100),
                    "TOT_DEBT_TO_TOT_ASSET" DECIMAL(18,6),
                    "CASH_DVD_COVERAGE" DECIMAL(18,6),
                    "TOT_DEBT_TO_EBITDA" DECIMAL(18,6),
                    "CUR_RATIO" DECIMAL(18,6),
                    "QUICK_RATIO" DECIMAL(18,6),
                    "GROSS_MARGIN" DECIMAL(18,6),
                    "INTEREST_COVERAGE_RATIO" DECIMAL(18,6),
                    "EBITDA_MARGIN" DECIMAL(18,6),
                    "TOT_LIAB_AND_EQY" DECIMAL(18,6),
                    "NET_DEBT_TO_SHRHLDR_EQTY" DECIMAL(18,6),
                    "INSERTED_AT" TIMESTAMP
                )
            """,
            'FINANCIAL_DATA_ADVANCED': """
                CREATE TABLE "{schema}"."{table}" (
                    "ID" INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                    "DATA_DATE" DATE,
                    "TICKER" NVARCHAR(50),
                    "IDENTIFIER_TYPE" NVARCHAR(20),
                    "IDENTIFIER_VALUE" NVARCHAR(100),
                    "BS_CURR_RENTAL_EXPENSE" DECIMAL(18,6),
                    "FISCAL_YEAR_PERIOD" NVARCHAR(20),
                    "ACCOUNTING_STANDARD" NVARCHAR(50),
                    "OTHER_NONOP_INCOME_LOSS" DECIMAL(18,6),
                    "NONOP_INCOME_LOSS" DECIMAL(18,6),
                    "NI_INCLUDING_MINORITY_INT_RATIO" DECIMAL(18,6),
                    "INCOME_LOSS_FROM_AFFILIATES" DECIMAL(18,6),
                    "OTHER_OPERATING_EXPENSES_RATIO" DECIMAL(18,6),
                    "ZAKAT_EXPENSES_OTHER_RESRV_CHARG" DECIMAL(18,6),
                    "ID_BB_COMPANY" NVARCHAR(100),
                    "ID_BB_GLOBAL" NVARCHAR(100),
                    "ID_BB_GLOBAL_COMPANY" NVARCHAR(100),
                    "IS_NET_ABNORMAL_ITEMS" DECIMAL(18,6),
                    "IS_SGA_EXPENSE" DECIMAL(18,6),
                    "IS_CURRENT_INCOME_TAX_BENEFIT" DECIMAL(18,6),
                    "IS_DEFERRED_INCOME_TAX_BENEFIT" DECIMAL(18,6),
                    "EXTRAORD_ITEMS_ACCOUNTING_CHANGS" DECIMAL(18,6),
                    "IS_SH_PRO_EQY_MT_INV_NET_OF_TAX" DECIMAL(18,6),
                    "IS_DISCONTINUED_OPERATIONS" DECIMAL(18,6),
                    "IS_TAX_VALN_ALLOWNCE_CREDITS" DECIMAL(18,6),
                    "IS_SELLING_EXPENSES" DECIMAL(18,6),
                    "IS_SALES_AND_SERVICES_REVENUES" DECIMAL(18,6),
                    "IS_FINANCING_REVENUE" DECIMAL(18,6),
                    "IS_OTHER_REVENUE" DECIMAL(18,6),
                    "IS_COG_AND_SERVICES_SOLD" DECIMAL(18,6),
                    "IS_COST_OF_FINANCING_REVENUE" DECIMAL(18,6),
                    "IS_DA_COST_OF_REVENUE_GAAP" DECIMAL(18,6),
                    "IS_GENERAL_AND_ADMINISTRATIVE" DECIMAL(18,6),
                    "IS_RESEARCH_AND_DEVELOPMENT" DECIMAL(18,6),
                    "IS_DEPRECIATION_AND_AMORTIZATION" DECIMAL(18,6),
                    "IS_OPER_EXPENSES_RD_GAAP" DECIMAL(18,6),
                    "IS_OTHER_INVESTMENT_INCOME_LOSS" DECIMAL(18,6),
                    "SALES_REV_TURN" DECIMAL(18,6),
                    "IS_INT_INC" DECIMAL(18,6),
                    "IS_COGS_TO_FE_AND_PP_AND_G" DECIMAL(18,6),
                    "IS_OPERATING_EXPN" DECIMAL(18,6),
                    "IS_OPER_INC" DECIMAL(18,6),
                    "IS_INT_EXPENSE" DECIMAL(18,6),
                    "IS_FOREIGN_EXCH_LOSS" DECIMAL(18,6),
                    "IS_INC_TAX_EXP" DECIMAL(18,6),
                    "IS_INC_BEF_XO_ITEM" DECIMAL(18,6),
                    "MIN_NONCONTROL_INTEREST_CREDITS" DECIMAL(18,6),
                    "NET_INCOME" DECIMAL(18,6),
                    "IS_TOT_CASH_PFD_DVD" DECIMAL(18,6),
                    "IS_TOT_CASH_COM_DVD" DECIMAL(18,6),
                    "IS_AVG_NUM_SH_FOR_EPS" DECIMAL(18,6),
                    "IS_EPS" DECIMAL(18,6),
                    "IS_SH_FOR_DILUTED_EPS" DECIMAL(18,6),
                    "IS_DILUTED_EPS" DECIMAL(18,6),
                    "IS_EARN_BEF_XO_ITEMS_PER_SH" DECIMAL(18,6),
                    "IS_PERSONNEL_EXP" DECIMAL(18,6),
                    "IS_DEPR_EXP" DECIMAL(18,6),
                    "IS_EXPORT_SALES" DECIMAL(18,6),
                    "IS_CAP_INT_EXP" DECIMAL(18,6),
                    "IS_BASIC_EPS_CONT_OPS" DECIMAL(18,6),
                    "IS_OTHER_OPER_INC" DECIMAL(18,6),
                    "CUR_PROFIT_JAPAN" DECIMAL(18,6),
                    "IS_DIL_EPS_CONT_OPS" DECIMAL(18,6),
                    "IS_DIL_EPS_BEF_XO" DECIMAL(18,6),
                    "OTHER_ADJUSTMENTS" DECIMAL(18,6),
                    "IS_PROVISION_DOUBTFUL_ACCOUNTS" DECIMAL(18,6),
                    "IS_NET_INTEREST_EXPENSE" DECIMAL(18,6),
                    "PRETAX_INC" DECIMAL(18,6),
                    "EBIT" DECIMAL(18,6),
                    "EBITDA" DECIMAL(18,6),
                    "EQY_DPS" DECIMAL(18,6),
                    "OPER_MARGIN" DECIMAL(18,6),
                    "GROSS_MARGIN" DECIMAL(18,6),
                    "EBITDA_MARGIN" DECIMAL(18,6),
                    "XO_GL_NET_OF_TAX" DECIMAL(18,6),
                    "PROF_MARGIN" DECIMAL(18,6),
                    "EARN_FOR_COMMON" DECIMAL(18,6),
                    "GROSS_PROFIT" DECIMAL(18,6),
                    "ACTUAL_SALES_PER_EMPL" DECIMAL(18,6),
                    "EBITA" DECIMAL(18,6),
                    "SALES_GROWTH" DECIMAL(18,6),
                    "CUR_RATIO" DECIMAL(18,6),
                    "QUICK_RATIO" DECIMAL(18,6),
                    "QUICK_RATIO_3Y_GEO_GRWTH" DECIMAL(18,6),
                    "TOT_DEBT_TO_COM_EQY" DECIMAL(18,6),
                    "WORKING_CAPITAL" DECIMAL(18,6),
                    "CF_FREE_CASH_FLOW" DECIMAL(18,6),
                    "NET_INC_GROWTH" DECIMAL(18,6),
                    "INSERTED_AT" TIMESTAMP
                )
            """,
            'ANNUAL_FINANCIALS_10K': """
                CREATE TABLE "{schema}"."{table}" (
                    "ID" INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                    "REPORT_DATE" DATE,
                    "FISCAL_YEAR" INTEGER,
                    "TICKER" NVARCHAR(50),
                    "SALES_REV_TURN" DECIMAL(18,6),
                    "GROSS_PROFIT" DECIMAL(18,6),
                    "IS_OPER_INC" DECIMAL(18,6),
                    "EBIT" DECIMAL(18,6),
                    "EBITDA" DECIMAL(18,6),
                    "PRETAX_INC" DECIMAL(18,6),
                    "NET_INCOME" DECIMAL(18,6),
                    "IS_EPS" DECIMAL(18,6),
                    "IS_DILUTED_EPS" DECIMAL(18,6),
                    "IS_SGA_EXPENSE" DECIMAL(18,6),
                    "IS_DEPRECIATION_AND_AMORTIZATION" DECIMAL(18,6),
                    "IS_INT_EXPENSE" DECIMAL(18,6),
                    "IS_INC_TAX_EXP" DECIMAL(18,6),
                    "TOT_LIAB_AND_EQY" DECIMAL(18,6),
                    "BS_CUR_LIAB" DECIMAL(18,6),
                    "BS_LT_BORROW" DECIMAL(18,6),
                    "BS_TOT_ASSET" DECIMAL(18,6),
                    "BS_SH_OUT" DECIMAL(18,6),
                    "CF_FREE_CASH_FLOW" DECIMAL(18,6),
                    "CF_CASH_FROM_OPER" DECIMAL(18,6),
                    "CF_CAP_EXPEND_PRPTY_ADD" DECIMAL(18,6),
                    "GROSS_MARGIN" DECIMAL(18,6),
                    "EBITDA_MARGIN" DECIMAL(18,6),
                    "OPER_MARGIN" DECIMAL(18,6),
                    "PROF_MARGIN" DECIMAL(18,6),
                    "CUR_RATIO" DECIMAL(18,6),
                    "QUICK_RATIO" DECIMAL(18,6),
                    "TOT_DEBT_TO_TOT_ASSET" DECIMAL(18,6),
                    "TOT_DEBT_TO_EBITDA" DECIMAL(18,6),
                    "INTEREST_COVERAGE_RATIO" DECIMAL(18,6),
                    "RETURN_ON_ASSET" DECIMAL(18,6),
                    "RETURN_COM_EQY" DECIMAL(18,6)
                )
            """,
            'INGESTION_LOGS': """
                CREATE TABLE "{schema}"."{table}" (
                    "RUN_ID" NVARCHAR(50) PRIMARY KEY,
                    "START_TIME" TIMESTAMP,
                    "END_TIME" TIMESTAMP,
                    "STATUS" NVARCHAR(20),
                    "RECORDS_FETCHED" INTEGER,
                    "RECORDS_INSERTED" INTEGER,
                    "RECORDS_FAILED" INTEGER,
                    "ERROR_MESSAGE" NVARCHAR(5000),
                    "BLOOMBERG_API_RESPONSE_TIME_MS" INTEGER,
                    "HANA_INSERT_TIME_MS" INTEGER,
                    "TRIGGERED_BY" NVARCHAR(50),
                    "DATA_SOURCE" NVARCHAR(100),
                    "EXECUTION_DETAILS" NCLOB
                )
            """,
            'USERS': """
                CREATE TABLE "{schema}"."{table}" (
                    "ID" INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                    "EMAIL" NVARCHAR(255) UNIQUE NOT NULL,
                    "PASSWORD_ENCRYPTED" NVARCHAR(500) NOT NULL,
                    "FULL_NAME" NVARCHAR(255),
                    "ROLE" NVARCHAR(50) DEFAULT 'USER',
                    "IS_ACTIVE" BOOLEAN DEFAULT TRUE,
                    "CREATED_AT" TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    "LAST_LOGIN" TIMESTAMP,
                    "LOGIN_ATTEMPTS" INTEGER DEFAULT 0
                )
            """
        }

    def connect(self):
        """
        Establish a connection to SAP HANA database.

        Returns:
            bool: True if connection successful, False otherwise
        """
        try:
            self.connection = dbapi.connect(
                address=self.address,
                port=int(self.port),
                user=self.user,
                password=self.password
            )

            self.logger.info("Connected to SAP HANA at %s:%s", self.address, self.port)
            return True

        except Exception as e:
            self.logger.error("Failed to connect to SAP HANA: %s", str(e))
            return False

    def close(self):
        """Close the connection to SAP HANA database."""
        if self.connection:
            self.connection.close()
            self.logger.info("Closed connection to SAP HANA")
            self.connection = None

    def create_schema_if_not_exists(self, schema_name):
        """
        Create a schema in SAP HANA if it doesn't exist.

        Args:
            schema_name (str): The schema name to create

        Returns:
            bool: True if successful, False otherwise
        """
        if not self.connection:
            self.logger.error("No connection to SAP HANA. Cannot create schema.")
            return False

        try:
            cursor = self.connection.cursor()

            # Check if schema exists
            cursor.execute("""
            SELECT COUNT(*) FROM SYS.SCHEMAS WHERE SCHEMA_NAME = ?
            """, [schema_name])

            schema_exists = cursor.fetchone()[0] > 0

            if not schema_exists:
                cursor.execute(f"""
                CREATE SCHEMA "{schema_name}"
                """)
                self.logger.info(f'Created schema "{schema_name}"')
            else:
                self.logger.debug(f'Schema "{schema_name}" already exists')

            cursor.close()
            return True

        except Exception as e:
            self.logger.error(f"Error creating schema: {str(e)}")
            return False

    def create_table(self, schema_name, table_name):
        """
        Create a table in SAP HANA for storing the Bloomberg data.

        Args:
            schema_name (str): The schema name in SAP HANA
            table_name (str): The table name to create

        Returns:
            bool: True if successful, False otherwise
        """
        if not self.connection:
            self.logger.error("No connection to SAP HANA. Cannot create table.")
            return False

        try:
            cursor = self.connection.cursor()

            # First check if table exists
            cursor.execute("""
            SELECT COUNT(*) FROM SYS.TABLES
            WHERE SCHEMA_NAME = ? AND TABLE_NAME = ?
            """, [schema_name, table_name])

            table_exists = cursor.fetchone()[0] > 0

            if not table_exists:
                # Determine which table schema to use
                if table_name.upper() in ('FINANCIAL_DATA_ADVANCED', 'FINANCIAL_ADVANCED'):
                    create_table_sql = self.table_schemas['FINANCIAL_DATA_ADVANCED'].format(
                        schema=schema_name, table=table_name)
                elif table_name.upper() == 'ANNUAL_FINANCIALS_10K':
                    create_table_sql = self.table_schemas['ANNUAL_FINANCIALS_10K'].format(
                        schema=schema_name, table=table_name)
                elif table_name.upper() == 'INGESTION_LOGS':
                    create_table_sql = self.table_schemas['INGESTION_LOGS'].format(
                        schema=schema_name, table=table_name)
                elif table_name.upper() == 'USERS':
                    create_table_sql = self.table_schemas['USERS'].format(
                        schema=schema_name, table=table_name)
                else:
                    # Default to basic financial ratios schema
                    create_table_sql = self.table_schemas['FINANCIAL_RATIOS'].format(
                        schema=schema_name, table=table_name)

                cursor.execute(create_table_sql)
                self.logger.info(f'Created table "{schema_name}"."{table_name}"')
            else:
                self.logger.debug(f'Table "{schema_name}"."{table_name}" already exists')

            cursor.close()
            return True

        except Exception as e:
            self.logger.error(f"Error creating HANA table: {str(e)}")
            return False

    def insert_data(self, df, schema_name, table_name):
        """
        Insert data from DataFrame to SAP HANA table.

        Args:
            df (DataFrame): The pandas DataFrame containing Bloomberg data
            schema_name (str): The schema name in SAP HANA
            table_name (str): The table name to insert into

        Returns:
            int: The number of rows inserted
        """
        if not self.connection:
            self.logger.error("No connection to SAP HANA. Cannot insert data.")
            return 0

        try:
            cursor = self.connection.cursor()
            rows_inserted = 0
            timestamp = datetime.datetime.now()

            # Get column metadata for the table
            cursor.execute("""
            SELECT COLUMN_NAME FROM SYS.TABLE_COLUMNS
            WHERE SCHEMA_NAME = ? AND TABLE_NAME = ?
            AND COLUMN_NAME != 'ID'
            ORDER BY POSITION
            """, [schema_name, table_name])

            columns = [row[0] for row in cursor.fetchall()]

            # Process the Bloomberg API response DataFrame
            for index, row in df.iterrows():
                try:
                    # Extract identifier info
                    ticker = row.get('ticker', '')
                    identifier_type = row.get('identifierType', '')
                    identifier_value = row.get('identifierValue', '')

                    # Build the insert SQL dynamically based on available columns
                    column_names = []
                    placeholders = []
                    values = []

                    # Always add the common columns
                    column_names.extend(['"TICKER"', '"IDENTIFIER_TYPE"', '"IDENTIFIER_VALUE"', '"INSERTED_AT"'])
                    placeholders.extend(['?', '?', '?', '?'])
                    values.extend([ticker, identifier_type, identifier_value, timestamp])

                    # Add available data fields
                    for column in columns:
                        if column not in ['TICKER', 'IDENTIFIER_TYPE', 'IDENTIFIER_VALUE', 'TIMESTAMP']:
                            field_name = column  # Column names in HANA are typically uppercase
                            field_value = self._extract_value(row, field_name)

                            if field_value is not None:
                                column_names.append(f'"{column}"')
                                placeholders.append('?')
                                values.append(field_value)

                    # Construct and execute SQL
                    insert_sql = f"""
                    INSERT INTO "{schema_name}"."{table_name}" (
                        {", ".join(column_names)}
                    ) VALUES ({", ".join(placeholders)})
                    """

                    cursor.execute(insert_sql, values)
                    rows_inserted += 1

                except Exception as row_error:
                    self.logger.warning(f"Error inserting row {index}: {str(row_error)}")
                    continue

            self.connection.commit()
            cursor.close()

            self.logger.info(f'Inserted {rows_inserted} rows into "{schema_name}"."{table_name}"')
            return rows_inserted

        except Exception as e:
            self.logger.error(f"Error inserting data to HANA: {str(e)}")
            return 0

    def _extract_value(self, row, field_name):
        """
        Helper method to extract field values from Bloomberg data.

        Args:
            row: DataFrame row
            field_name: Field name to extract

        Returns:
            Value or None if not found
        """
        # Direct access
        if field_name in row:
            return row[field_name]

        # Try with case-insensitive lookup
        for key in row.keys():
            if key.upper() == field_name.upper():
                return row[key]

        # Try nested dictionaries (common in Bloomberg responses)
        if 'data' in row and isinstance(row['data'], dict):
            for key in row['data'].keys():
                if key.upper() == field_name.upper():
                    return row['data'][key]

        # Try looking in a 'fields' or 'values' dictionary
        for container in ['fields', 'values', 'results']:
            if container in row and isinstance(row[container], dict):
                for key in row[container].keys():
                    if key.upper() == field_name.upper():
                        return row[container][key]

        # Not found
        return None

    # ========== INGESTION LOGGING METHODS ==========

    def log_ingestion_start(self, run_id, triggered_by='MANUAL', data_source='BLOOMBERG_BASIC'):
        """
        Log the start of an ingestion run.

        Args:
            run_id (str): Unique identifier for this ingestion run
            triggered_by (str): How the ingestion was triggered (MANUAL, SCHEDULED, API)
            data_source (str): Data source identifier

        Returns:
            bool: True if successful, False otherwise
        """
        if not self.connection:
            self.logger.error("No connection to HANA. Cannot log ingestion start.")
            return False

        try:
            cursor = self.connection.cursor()
            start_time = datetime.datetime.now()

            insert_sql = f"""
            INSERT INTO "{self.schema}"."INGESTION_LOGS" (
                "RUN_ID", "START_TIME", "STATUS", "TRIGGERED_BY", "DATA_SOURCE"
            ) VALUES (?, ?, ?, ?, ?)
            """

            cursor.execute(insert_sql, [run_id, start_time, 'RUNNING', triggered_by, data_source])
            self.connection.commit()
            cursor.close()

            self.logger.info(f"Logged ingestion start for run_id: {run_id}")
            return True

        except Exception as e:
            self.logger.error(f"Error logging ingestion start: {str(e)}")
            return False

    def log_ingestion_end(self, run_id, status, records_fetched, records_inserted,
                          records_failed=0, error_message=None, api_time_ms=0,
                          hana_time_ms=0, execution_details=None):
        """
        Log the end of an ingestion run with results.

        Args:
            run_id (str): Unique identifier for this ingestion run
            status (str): Final status (SUCCESS, FAILED, PARTIAL)
            records_fetched (int): Number of records fetched from Bloomberg
            records_inserted (int): Number of records successfully inserted
            records_failed (int): Number of records that failed to insert
            error_message (str): Error message if any
            api_time_ms (int): Bloomberg API response time in milliseconds
            hana_time_ms (int): HANA insert time in milliseconds
            execution_details (dict): Additional execution details as JSON

        Returns:
            bool: True if successful, False otherwise
        """
        if not self.connection:
            self.logger.error("No connection to HANA. Cannot log ingestion end.")
            return False

        try:
            cursor = self.connection.cursor()
            end_time = datetime.datetime.now()

            # Convert execution details to JSON string
            details_json = json.dumps(execution_details) if execution_details else None

            update_sql = f"""
            UPDATE "{self.schema}"."INGESTION_LOGS"
            SET "END_TIME" = ?,
                "STATUS" = ?,
                "RECORDS_FETCHED" = ?,
                "RECORDS_INSERTED" = ?,
                "RECORDS_FAILED" = ?,
                "ERROR_MESSAGE" = ?,
                "BLOOMBERG_API_RESPONSE_TIME_MS" = ?,
                "HANA_INSERT_TIME_MS" = ?,
                "EXECUTION_DETAILS" = ?
            WHERE "RUN_ID" = ?
            """

            cursor.execute(update_sql, [
                end_time, status, records_fetched, records_inserted, records_failed,
                error_message, api_time_ms, hana_time_ms, details_json, run_id
            ])

            self.connection.commit()
            cursor.close()

            self.logger.info(f"Logged ingestion end for run_id: {run_id} with status: {status}")
            return True

        except Exception as e:
            self.logger.error(f"Error logging ingestion end: {str(e)}")
            return False

    def get_last_ingestion_status(self):
        """
        Get the status of the last ingestion run.

        Returns:
            dict: Dictionary containing last ingestion details or None
        """
        if not self.connection:
            self.logger.error("No connection to HANA. Cannot get ingestion status.")
            return None

        try:
            cursor = self.connection.cursor()

            query = f"""
            SELECT
                "RUN_ID",
                "START_TIME",
                "END_TIME",
                "STATUS",
                "RECORDS_FETCHED",
                "RECORDS_INSERTED",
                "RECORDS_FAILED",
                "ERROR_MESSAGE",
                "TRIGGERED_BY",
                "DATA_SOURCE"
            FROM "{self.schema}"."INGESTION_LOGS"
            ORDER BY "START_TIME" DESC
            LIMIT 1
            """

            cursor.execute(query)
            row = cursor.fetchone()
            cursor.close()

            if row:
                return {
                    'run_id': row[0],
                    'start_time': str(row[1]) if row[1] else None,
                    'end_time': str(row[2]) if row[2] else None,
                    'status': row[3],
                    'records_fetched': row[4],
                    'records_inserted': row[5],
                    'records_failed': row[6],
                    'error_message': row[7],
                    'triggered_by': row[8],
                    'data_source': row[9]
                }
            else:
                return None

        except Exception as e:
            self.logger.error(f"Error getting last ingestion status: {str(e)}")
            return None

    def get_ingestion_history(self, limit=10):
        """
        Get the history of ingestion runs.

        Args:
            limit (int): Number of records to retrieve

        Returns:
            list: List of dictionaries containing ingestion history
        """
        if not self.connection:
            self.logger.error("No connection to HANA. Cannot get ingestion history.")
            return []

        try:
            cursor = self.connection.cursor()

            query = f"""
            SELECT
                "RUN_ID",
                "START_TIME",
                "END_TIME",
                "STATUS",
                "RECORDS_FETCHED",
                "RECORDS_INSERTED",
                "RECORDS_FAILED",
                "TRIGGERED_BY",
                "DATA_SOURCE"
            FROM "{self.schema}"."INGESTION_LOGS"
            ORDER BY "START_TIME" DESC
            LIMIT {limit}
            """

            cursor.execute(query)
            rows = cursor.fetchall()
            cursor.close()

            history = []
            for row in rows:
                history.append({
                    'run_id': row[0],
                    'start_time': str(row[1]) if row[1] else None,
                    'end_time': str(row[2]) if row[2] else None,
                    'status': row[3],
                    'records_fetched': row[4],
                    'records_inserted': row[5],
                    'records_failed': row[6],
                    'triggered_by': row[7],
                    'data_source': row[8]
                })

            return history

        except Exception as e:
            self.logger.error(f"Error getting ingestion history: {str(e)}")
            return []

    def check_duplicate(self, row_data, schema_name, table_name):
        """
        Check if a record already exists in the database (exact match on all fields).

        Args:
            row_data (dict): Row data to check
            schema_name (str): Schema name
            table_name (str): Table name

        Returns:
            bool: True if duplicate exists, False otherwise
        """
        if not self.connection:
            return False

        try:
            cursor = self.connection.cursor()

            # Build WHERE clause for all non-ID, non-TIMESTAMP fields
            where_conditions = []
            params = []

            for key, value in row_data.items():
                if key.upper() not in ['ID', 'TIMESTAMP']:
                    if value is None:
                        where_conditions.append(f'"{key.upper()}" IS NULL')
                    else:
                        where_conditions.append(f'"{key.upper()}" = ?')
                        params.append(value)

            where_clause = " AND ".join(where_conditions)

            query = f"""
            SELECT COUNT(*) FROM "{schema_name}"."{table_name}"
            WHERE {where_clause}
            """

            cursor.execute(query, params)
            count = cursor.fetchone()[0]
            cursor.close()

            return count > 0

        except Exception as e:
            self.logger.error(f"Error checking duplicate: {str(e)}")
            return False

    def get_total_records(self, schema_name, table_name):
        """
        Get total number of records in the table.

        Args:
            schema_name (str): Schema name
            table_name (str): Table name

        Returns:
            int: Total number of records
        """
        if not self.connection:
            return 0

        try:
            cursor = self.connection.cursor()

            query = f"""
            SELECT COUNT(*) FROM "{schema_name}"."{table_name}"
            """

            cursor.execute(query)
            count = cursor.fetchone()[0]
            cursor.close()

            return count

        except Exception as e:
            self.logger.error(f"Error getting total records: {str(e)}")
            return 0

    def insert_data_with_duplicate_check(self, df, schema_name, table_name):
        """
        Insert data from DataFrame to SAP HANA table with duplicate checking.
        Skips exact duplicate rows.

        Args:
            df (DataFrame): The pandas DataFrame containing Bloomberg data
            schema_name (str): The schema name in SAP HANA
            table_name (str): The table name to insert into

        Returns:
            tuple: (rows_inserted, rows_skipped)
        """
        if not self.connection:
            self.logger.error("No connection to SAP HANA. Cannot insert data.")
            return 0, 0

        try:
            cursor = self.connection.cursor()
            rows_inserted = 0
            rows_skipped = 0
            timestamp = datetime.datetime.now()

            # Get column metadata for the table
            cursor.execute("""
            SELECT COLUMN_NAME FROM SYS.TABLE_COLUMNS
            WHERE SCHEMA_NAME = ? AND TABLE_NAME = ?
            AND COLUMN_NAME != 'ID'
            ORDER BY POSITION
            """, [schema_name, table_name])

            columns = [row[0] for row in cursor.fetchall()]

            # Get count before insertion
            count_before = self.get_total_records(schema_name, table_name)

            # Process the Bloomberg API response DataFrame
            for index, row in df.iterrows():
                try:
                    # Extract identifier info
                    ticker = row.get('ticker', '')
                    identifier_type = row.get('identifierType', '')
                    identifier_value = row.get('identifierValue', '')

                    # Build row data dictionary for duplicate check
                    row_data = {
                        'TICKER': ticker,
                        'IDENTIFIER_TYPE': identifier_type,
                        'IDENTIFIER_VALUE': identifier_value
                    }

                    # Add available data fields to row_data
                    for column in columns:
                        if column not in ['TICKER', 'IDENTIFIER_TYPE', 'IDENTIFIER_VALUE', 'TIMESTAMP']:
                            field_value = self._extract_value(row, column)
                            row_data[column] = field_value

                    # Check for duplicate
                    if self.check_duplicate(row_data, schema_name, table_name):
                        rows_skipped += 1
                        self.logger.debug(f"Skipping duplicate record for {ticker}")
                        continue

                    # Build the insert SQL dynamically based on available columns
                    column_names = []
                    placeholders = []
                    values = []

                    # Always add the common columns
                    column_names.extend(['"TICKER"', '"IDENTIFIER_TYPE"', '"IDENTIFIER_VALUE"', '"INSERTED_AT"'])
                    placeholders.extend(['?', '?', '?', '?'])
                    values.extend([ticker, identifier_type, identifier_value, timestamp])

                    # Add available data fields
                    for column in columns:
                        if column not in ['TICKER', 'IDENTIFIER_TYPE', 'IDENTIFIER_VALUE', 'TIMESTAMP']:
                            field_value = self._extract_value(row, column)

                            if field_value is not None:
                                column_names.append(f'"{column}"')
                                placeholders.append('?')
                                values.append(field_value)

                    # Construct and execute SQL
                    insert_sql = f"""
                    INSERT INTO "{schema_name}"."{table_name}" (
                        {", ".join(column_names)}
                    ) VALUES ({", ".join(placeholders)})
                    """

                    cursor.execute(insert_sql, values)
                    rows_inserted += 1

                except Exception as row_error:
                    self.logger.warning(f"Error inserting row {index}: {str(row_error)}")
                    continue

            self.connection.commit()
            cursor.close()

            # Get count after insertion
            count_after = self.get_total_records(schema_name, table_name)
            new_entries = count_after - count_before

            self.logger.info(f'Inserted {rows_inserted} rows, skipped {rows_skipped} duplicates. New entries: {new_entries}')

            return rows_inserted, rows_skipped, new_entries

        except Exception as e:
            self.logger.error(f"Error inserting data to HANA: {str(e)}")
            return 0, 0, 0
