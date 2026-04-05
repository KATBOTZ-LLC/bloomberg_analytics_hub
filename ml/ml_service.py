"""
ML Service - Load and use trained ML models from HANA
Provides interface for dashboard to get ML predictions and insights
"""

import logging
import json
import io
import joblib
import numpy as np
import pandas as pd
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)


class MLService:
    """Service for loading and using ML models from HANA"""
    
    def __init__(self, hana_client, ml_schema: str = None, data_schema: str = None):
        """
        Initialize ML service with HANA client
        
        Args:
            hana_client: HANA connection client
            ml_schema: Schema for ML models (defaults to BLOOMBERG_DATA)
            data_schema: Schema for financial data (defaults to BLOOMBERG_DATA)
        """
        self.hana_client = hana_client
        # Use provided schemas or default to BLOOMBERG_DATA for both
        self.schema = ml_schema or "BLOOMBERG_DATA"
        self.data_schema = data_schema or "BLOOMBERG_DATA"
        self._model_cache = {}
        # Optional CSV fallback DataFrame — set from app.py after csv_data loads
        self.csv_fallback_df = None
        logger.info(f"MLService initialized with ML schema: {self.schema}, Data schema: {self.data_schema}")
        
    def get_active_models(self) -> List[Dict]:
        """Get list of all active ML models"""
        try:
            cursor = self.hana_client.connection.cursor()
            cursor.execute(f"""
                SELECT "MODEL_ID", "MODEL_NAME", "MODEL_TYPE", "VERSION", 
                       "TRAINING_ROWS", "CREATED_AT"
                FROM "{self.schema}"."ML_MODELS"
                WHERE "IS_ACTIVE" = 1
                ORDER BY "MODEL_NAME"
            """)
            
            columns = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()
            
            models = []
            for row in rows:
                models.append({
                    "model_id": row[0],
                    "name": row[1],
                    "type": row[2],
                    "version": row[3],
                    "training_rows": row[4],
                    "trained_at": row[5].strftime("%Y-%m-%d %H:%M") if row[5] else None
                })
            logger.info(f"Found {len(models)} active ML models")
            return models
            
        except Exception as e:
            logger.error(f"Error getting active models: {e}")
            return []
    
    def load_model(self, model_name: str) -> Tuple[Any, Any, List[str], Dict]:
        """
        Load a model from HANA.
        Returns: (model, scaler, feature_columns, metrics)
        """
        # Check cache first
        if model_name in self._model_cache:
            logger.debug(f"Model {model_name} loaded from cache")
            return self._model_cache[model_name]
            
        try:
            cursor = self.hana_client.connection.cursor()
            cursor.execute(f"""
                SELECT "MODEL_BLOB", "SCALER_BLOB", "FEATURE_COLUMNS", "METRICS"
                FROM "{self.schema}"."ML_MODELS"
                WHERE "MODEL_NAME" = ? AND "IS_ACTIVE" = 1
            """, (model_name,))
            
            row = cursor.fetchone()
            if not row:
                logger.warning(f"No active model found: {model_name} in schema {self.schema}")
                return None, None, [], {}
            
            model_bytes, scaler_bytes, features_json, metrics_json = row
            
            # Deserialize model
            model_buffer = io.BytesIO(model_bytes)
            model = joblib.load(model_buffer)
            
            # Deserialize scaler if present
            scaler = None
            if scaler_bytes:
                scaler_buffer = io.BytesIO(scaler_bytes)
                scaler = joblib.load(scaler_buffer)
            
            feature_columns = json.loads(features_json) if features_json else []
            metrics = json.loads(metrics_json) if metrics_json else {}
            
            # Cache the loaded model
            self._model_cache[model_name] = (model, scaler, feature_columns, metrics)
            
            logger.info(f"Loaded model: {model_name} with {len(feature_columns)} features")
            return model, scaler, feature_columns, metrics
            
        except Exception as e:
            # Downgrade to WARNING for known "table not found" — it's expected when
            # ML_MODELS hasn't been deployed yet; don't flood the log with ERROR.
            msg = str(e)
            if "ML_MODELS" in msg or "table not found" in msg.lower() or "invalid table name" in msg.lower():
                logger.warning(f"ML_MODELS table unavailable ({model_name}): model will run in fallback mode")
            else:
                logger.error(f"Error loading model {model_name}: {e}")
            return None, None, [], {}
    
    def get_cluster_labels(self, model_name: str) -> List[Dict]:
        """Get cluster labels for a clustering model"""
        try:
            cursor = self.hana_client.connection.cursor()
            cursor.execute(f"""
                SELECT cl."CLUSTER_ID", cl."CLUSTER_LABEL", cl."SAMPLE_COUNT", cl."AVG_HEALTH_SCORE"
                FROM "{self.schema}"."ML_CLUSTER_LABELS" cl
                JOIN "{self.schema}"."ML_MODELS" m ON cl."MODEL_ID" = m."MODEL_ID"
                WHERE m."MODEL_NAME" = ? AND m."IS_ACTIVE" = 1
                ORDER BY cl."CLUSTER_ID"
            """, (model_name,))
            
            rows = cursor.fetchall()
            return [
                {
                    "cluster_id": row[0],
                    "label": row[1],
                    "sample_count": row[2],
                    "avg_health_score": float(row[3]) if row[3] else 0
                }
                for row in rows
            ]
            
        except Exception as e:
            logger.error(f"Error getting cluster labels: {e}")
            return []
    
    def get_company_data(self, tickers: List[str] = None) -> pd.DataFrame:
        """Get latest financial data for specified companies"""
        try:
            cursor = self.hana_client.connection.cursor()
            
            # First get all data from latest date
            query = f"""
                SELECT * FROM "{self.data_schema}"."FINANCIAL_RATIOS"
                WHERE "DATA_DATE" = (SELECT MAX("DATA_DATE") FROM "{self.data_schema}"."FINANCIAL_RATIOS")
            """
            cursor.execute(query)
            
            columns = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()
            
            df = pd.DataFrame(rows, columns=columns)
            logger.info(f"Loaded {len(df)} rows from FINANCIAL_RATIOS")

            # If HANA table is empty, use CSV fallback immediately
            if df.empty and self.csv_fallback_df is not None:
                logger.info("get_company_data: FINANCIAL_RATIOS empty, using CSV fallback")
                return self._filter_csv_fallback(self.csv_fallback_df, tickers)
            
            # Convert Decimal to float
            for col in df.columns:
                if df[col].dtype == object:
                    try:
                        df[col] = pd.to_numeric(df[col], errors='ignore')
                    except:
                        pass
            
            # Normalize ticker column - remove " US Equity" suffix if present
            if 'TICKER' in df.columns:
                df['TICKER'] = df['TICKER'].str.replace(' US Equity', '', regex=False)
                logger.debug(f"Available tickers: {df['TICKER'].unique().tolist()[:10]}")
            
            # Deduplicate by TICKER - keep first row per ticker
            if 'TICKER' in df.columns:
                df = df.drop_duplicates(subset=['TICKER'], keep='first')
                logger.info(f"After deduplication: {len(df)} unique tickers")
            
            # Filter by tickers if provided
            if tickers and 'TICKER' in df.columns:
                # Normalize input tickers - filter out non-ticker values (like company names)
                normalized_tickers = []
                for t in tickers:
                    t_clean = t.replace(' US Equity', '')
                    # Only include if it looks like a valid ticker (all caps, reasonable length)
                    if t_clean.isupper() and len(t_clean) <= 5:
                        normalized_tickers.append(t_clean)
                
                if not normalized_tickers:
                    logger.warning(f"No valid tickers in input: {tickers}")
                    return df  # Return all data if no valid tickers
                
                df_filtered = df[df['TICKER'].isin(normalized_tickers)]
                logger.info(f"Filtered to {len(df_filtered)} rows for tickers: {normalized_tickers[:5]}")

                # Log which tickers weren't found
                found_tickers = df_filtered['TICKER'].unique().tolist()
                missing = [t for t in normalized_tickers if t not in found_tickers]
                if missing:
                    logger.warning(f"Tickers not found in HANA data: {missing}")

                # If filtered result is empty, try CSV fallback for those tickers
                if df_filtered.empty and self.csv_fallback_df is not None:
                    logger.info("Filtered HANA result empty — falling back to CSV for requested tickers")
                    return self._filter_csv_fallback(self.csv_fallback_df, tickers)

                return df_filtered
            
            return df
            
        except Exception as e:
            logger.error(f"Error getting company data: {e}")
            if self.csv_fallback_df is not None:
                logger.info("get_company_data: HANA error, falling back to CSV data")
                return self._filter_csv_fallback(self.csv_fallback_df, tickers)
            return pd.DataFrame()
    
    def _filter_csv_fallback(self, df: pd.DataFrame, tickers: List[str] = None) -> pd.DataFrame:
        """Filter and return CSV fallback data, applying same normalisation as HANA path."""
        df = df.copy()
        if 'TICKER' in df.columns:
            df['TICKER'] = df['TICKER'].str.replace(' US Equity', '', regex=False)
            df = df.drop_duplicates(subset=['TICKER'], keep='first')
        if tickers and 'TICKER' in df.columns:
            normalized = [t.replace(' US Equity', '').strip() for t in tickers
                          if t.replace(' US Equity', '').strip().isupper()
                          and len(t.replace(' US Equity', '').strip()) <= 5]
            if normalized:
                df = df[df['TICKER'].isin(normalized)]
        # Convert numeric columns
        for col in df.columns:
            if df[col].dtype == object:
                df[col] = pd.to_numeric(df[col], errors='ignore')
        logger.info(f"CSV fallback returned {len(df)} rows")
        return df

    def get_advanced_data(self, tickers: List[str] = None) -> pd.DataFrame:
        """Get advanced financial data"""
        try:
            cursor = self.hana_client.connection.cursor()
            
            query = f"""
                SELECT * FROM "{self.data_schema}"."FINANCIAL_DATA_ADVANCED"
                ORDER BY "DATA_DATE" DESC
            """
            cursor.execute(query)
            
            columns = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()
            
            df = pd.DataFrame(rows, columns=columns)
            logger.info(f"Loaded {len(df)} rows from FINANCIAL_DATA_ADVANCED")
            
            if tickers and 'TICKER' in df.columns:
                df = df[df['TICKER'].isin(tickers)]
                logger.info(f"Filtered to {len(df)} rows for tickers")
            
            # Convert Decimal to float
            for col in df.columns:
                if df[col].dtype == object:
                    try:
                        df[col] = pd.to_numeric(df[col], errors='ignore')
                    except:
                        pass
            
            return df
            
        except Exception as e:
            logger.error(f"Error getting advanced data: {e}")
            return pd.DataFrame()
    
    def _analyze_ratios_without_model(self, df: pd.DataFrame) -> Dict:
        """
        Return ACTUAL ratio values (not normalised 0-100 scores) so the UI
        can compare My Company vs Industry Average truthfully.

        ratio_scores dict stores the raw values (e.g. GROSS_MARGIN = 74.99),
        not an artificial 0-100 score — which was the root cause of the
        'everything shows 100%' bug.
        """
        # Priority fields — must exist in FINANCIAL_RATIOS; extend with any other numeric columns
        PRIORITY_FIELDS = [
            'PROF_MARGIN', 'GROSS_MARGIN', 'EBITDA_MARGIN', 'OPER_MARGIN',
            'RETURN_ON_ASSET', 'RETURN_COM_EQY',
            'CUR_RATIO', 'QUICK_RATIO',
            'TOT_DEBT_TO_TOT_ASSET', 'TOT_DEBT_TO_EBITDA', 'TOT_DEBT_TO_COM_EQY',
            'NET_DEBT_TO_SHRHLDR_EQTY', 'INTEREST_COVERAGE_RATIO',
            'ASSET_TURNOVER', 'TOT_DEBT_TO_TOT_EQY',
        ]
        # Use ALL numeric columns so we never miss a field that exists in HANA
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        non_id_cols  = [c for c in numeric_cols if c not in ('ID',)]
        # Merge: priority fields first (if present), then any extras
        available = [f for f in PRIORITY_FIELDS if f in df.columns]
        available += [c for c in non_id_cols if c not in available and c not in ('ID',)]

        if not available:
            logger.warning("No ratio metrics available in data")
            return {"error": "No metrics", "companies": []}

        results = []
        for _, row in df.iterrows():
            ticker = row.get('TICKER', 'Unknown')
            raw_ratios = {}
            for field in available:
                val = row.get(field)
                # Always store a float — None/NaN become 0.0 so downstream code is safe
                raw_ratios[field] = float(val) if pd.notna(val) else 0.0

            # Simple health label based on gross margin as proxy
            gm = raw_ratios.get('GROSS_MARGIN') or 0
            health = ('Excellent' if gm >= 60
                      else 'Good'  if gm >= 40
                      else 'Fair'  if gm >= 20
                      else 'Weak')

            results.append({
                'ticker': ticker,
                'cluster': 0,
                'health_label': health,
                'ratio_scores': raw_ratios,   # ← raw values, not 0-100 scores
                'overall_score': gm,
            })

        logger.info(f"Analyzed {len(results)} companies (raw-value mode)")
        return {
            "companies": results,
            "features": available,
            "model_metrics": {"mode": "raw_values"},
        }

    # ==================== RATIO ANALYZER ====================
    def analyze_ratios(self, tickers: List[str]) -> Dict:
        """
        Analyze financial ratios for given companies.
        Returns cluster assignments and health scores.
        """
        logger.info(f"analyze_ratios called with tickers: {tickers}")
        
        # Get data first
        df = self.get_company_data(tickers)
        if df.empty:
            logger.warning(f"No data found for tickers: {tickers}")
            return {"error": "No data", "companies": []}
        
        # Try to load model
        model, scaler, features, metrics = self.load_model('ratio_analyzer')
        
        # If no model, use data-only analysis
        if model is None:
            logger.info("Ratio analyzer model not loaded, using data-only mode")
            return self._analyze_ratios_without_model(df)
        
        # Get cluster labels
        cluster_labels = self.get_cluster_labels('ratio_analyzer')
        label_map = {c['cluster_id']: c['label'] for c in cluster_labels}
        
        results = []
        available_features = [f for f in features if f in df.columns]
        
        if not available_features:
            logger.warning("No matching features in data, falling back to data-only mode")
            return self._analyze_ratios_without_model(df)
        
        for _, row in df.iterrows():
            ticker = row.get('TICKER', 'Unknown')
            
            # Prepare features
            X = row[available_features].fillna(0).values.reshape(1, -1)
            X = np.array([[float(x) for x in X[0]]])
            
            try:
                if scaler:
                    X_scaled = scaler.transform(X)
                else:
                    X_scaled = X
                
                # Get cluster and health score
                if hasattr(model, 'kmeans'):
                    cluster = model.kmeans.predict(X_scaled)[0]
                    health_label = label_map.get(cluster, 'Unknown')
                else:
                    cluster = 0
                    health_label = 'N/A'
                
                # Calculate individual ratio scores
                ratio_scores = {}
                for feat in available_features:
                    val = float(row[feat]) if pd.notna(row[feat]) else 0
                    # Normalize to 0-100 scale (simplified)
                    ratio_scores[feat] = min(100, max(0, val * 10)) if val > 0 else 50
                
                results.append({
                    'ticker': ticker,
                    'cluster': int(cluster),
                    'health_label': health_label,
                    'ratio_scores': ratio_scores,
                    'overall_score': np.mean(list(ratio_scores.values()))
                })
                
            except Exception as e:
                logger.error(f"Error analyzing {ticker}: {e}")
                results.append({
                    'ticker': ticker,
                    'cluster': -1,
                    'health_label': 'Error',
                    'ratio_scores': {},
                    'overall_score': 0
                })
        
        logger.info(f"Analyzed {len(results)} companies with ML model")
        return {
            "companies": results,
            "cluster_labels": cluster_labels,
            "features": available_features,
            "model_metrics": metrics
        }
    
    # ==================== ANOMALY DETECTOR ====================
    def detect_anomalies(self, tickers: List[str]) -> Dict:
        """
        Detect anomalies in financial metrics.
        Returns anomaly scores for each company/metric.
        """
        logger.info(f"detect_anomalies called with tickers: {tickers}")
        
        df = self.get_company_data(tickers)
        if df.empty:
            return {"error": "No data", "companies": []}
        
        model, scaler, features, metrics = self.load_model('anomaly_detector')
        
        # If model not loaded, use statistical fallback
        if model is None:
            logger.info("Anomaly detector model not loaded, using statistical fallback")
            return self._detect_anomalies_fallback(df)
        
        results = []
        available_features = [f for f in features if f in df.columns]
        
        if not available_features:
            return self._detect_anomalies_fallback(df)
        
        for _, row in df.iterrows():
            ticker = row.get('TICKER', 'Unknown')
            
            X = row[available_features].fillna(0).values.reshape(1, -1)
            X = np.array([[float(x) for x in X[0]]])
            
            try:
                if scaler:
                    X_scaled = scaler.transform(X)
                else:
                    X_scaled = X
                
                # Get anomaly score from isolation forest
                if hasattr(model, 'iso_forest'):
                    anomaly_score = -model.iso_forest.decision_function(X_scaled)[0]
                    is_anomaly = model.iso_forest.predict(X_scaled)[0] == -1
                else:
                    anomaly_score = 0
                    is_anomaly = False
                
                # Per-metric anomaly scores
                metric_scores = {}
                for i, feat in enumerate(available_features):
                    val = X[0][i]
                    metric_scores[feat] = {
                        'value': float(val),
                        'score': min(5, abs(anomaly_score))
                    }
                
                results.append({
                    'ticker': ticker,
                    'anomaly_score': float(anomaly_score),
                    'is_anomaly': bool(is_anomaly),
                    'metric_scores': metric_scores
                })
                
            except Exception as e:
                logger.error(f"Error detecting anomalies for {ticker}: {e}")
        
        logger.info(f"Detected anomalies for {len(results)} companies")
        return {
            "companies": results,
            "features": available_features,
            "threshold": metrics.get('threshold', 0)
        }
    
    def _detect_anomalies_fallback(self, df: pd.DataFrame) -> Dict:
        """Statistical fallback for anomaly detection"""
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        features = [c for c in numeric_cols if c not in ['ID', 'DATA_DATE']][:8]
        
        results = []
        for _, row in df.iterrows():
            ticker = row.get('TICKER', 'Unknown')
            metric_scores = {}
            total_score = 0
            
            for feat in features:
                val = float(row[feat]) if pd.notna(row[feat]) else 0
                col_mean = df[feat].mean()
                col_std = df[feat].std()
                if col_std > 0:
                    z_score = abs(val - col_mean) / col_std
                    score = min(5, z_score)
                else:
                    score = 0
                metric_scores[feat] = {'value': val, 'score': score}
                total_score += score
            
            avg_score = total_score / len(features) if features else 0
            results.append({
                'ticker': ticker,
                'anomaly_score': avg_score,
                'is_anomaly': avg_score > 2.5,
                'metric_scores': metric_scores
            })
        
        return {"companies": results, "features": features, "threshold": 2.5}
    
    # ==================== COMPETITOR BENCHMARK ====================
    def benchmark_competitors(self, tickers: List[str], target_ticker: str = None) -> Dict:
        """
        Benchmark companies against each other.
        Returns similarity scores and rankings.
        Falls back gracefully when requested tickers aren't in FINANCIAL_RATIOS.
        """
        logger.info(f"benchmark_competitors called with tickers: {tickers}, target: {target_ticker}")

        # ── Step 1: try filtered data, escalating fallbacks ────────────────────
        df = self.get_company_data(tickers)
        logger.info(f"benchmark_competitors STEP1: get_company_data(tickers) → {len(df)} rows")

        if df.empty:
            logger.warning("benchmark_competitors STEP1b: filtered empty, retrying with all FINANCIAL_RATIOS data")
            df = self.get_company_data(None)
            logger.info(f"benchmark_competitors STEP1b result: {len(df)} rows")

        if df.empty and self.csv_fallback_df is not None:
            logger.warning("benchmark_competitors STEP1c: HANA empty, using full CSV fallback")
            df = self._filter_csv_fallback(self.csv_fallback_df, None)
            logger.info(f"benchmark_competitors STEP1c CSV result: {len(df)} rows")

        if df.empty:
            logger.error("benchmark_competitors: no data from HANA or CSV — giving up")
            return {"error": "No data", "companies": []}

        logger.info(f"benchmark_competitors: csv_fallback_df is {'set' if self.csv_fallback_df is not None else 'None'}")

        logger.info(f"benchmark_competitors: working with {len(df)} rows, tickers={df['TICKER'].unique().tolist() if 'TICKER' in df.columns else 'N/A'}")

        # ── Step 2: resolve target ticker ────────────────────────────────────
        available_tickers = df['TICKER'].unique().tolist() if 'TICKER' in df.columns else []
        if target_ticker is None and tickers:
            target_ticker = tickers[0]

        # If target not in actual data, use first available
        if target_ticker not in available_tickers:
            if available_tickers:
                logger.warning(f"Target {target_ticker} not in data, using {available_tickers[0]} instead")
                target_ticker = available_tickers[0]
            else:
                return {"error": "No tickers found in FINANCIAL_RATIOS", "companies": []}

        # ── Step 3: resolve features ──────────────────────────────────────────
        model, scaler, features, metrics = self.load_model('competitor_benchmark')
        if model is None:
            logger.info("Competitor benchmark model not loaded, using data-driven approach")

        # Prefer key financial ratio columns; fall back to any numeric
        PREFERRED_FEATURES = [
            'GROSS_MARGIN', 'EBITDA_MARGIN', 'OPER_MARGIN', 'PROF_MARGIN',
            'RETURN_ON_ASSET', 'RETURN_COM_EQY',
            'CUR_RATIO', 'QUICK_RATIO',
            'TOT_DEBT_TO_TOT_ASSET', 'TOT_DEBT_TO_EBITDA',
        ]
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        non_id_cols  = [c for c in numeric_cols if c not in ('ID', 'DATA_DATE')]

        if features:
            available_features = [f for f in features if f in df.columns]
        else:
            available_features = [c for c in PREFERRED_FEATURES if c in df.columns]
            if not available_features:
                available_features = non_id_cols[:10]

        if not available_features:
            logger.warning("benchmark_competitors: no numeric features available, using all numeric cols")
            available_features = non_id_cols[:10]

        logger.info(f"benchmark_competitors: using features={available_features}")

        # ── Step 4: compute benchmark ─────────────────────────────────────────
        target_row  = df[df['TICKER'] == target_ticker]
        target_data = np.array([float(v) for v in target_row[available_features].fillna(0).values[0]])

        results = []
        for _, row in df.iterrows():
            ticker = row.get('TICKER', 'Unknown')
            try:
                X = np.array([float(v) for v in row[available_features].fillna(0).values])

                # Cosine similarity
                norm_X  = np.linalg.norm(X)
                norm_tgt = np.linalg.norm(target_data)
                if norm_X > 0 and norm_tgt > 0:
                    similarity = float(np.dot(X, target_data) / (norm_X * norm_tgt))
                else:
                    similarity = 1.0 if ticker == target_ticker else 0.0

                # Per-metric comparison
                metric_comparison = {}
                for i, feat in enumerate(available_features):
                    target_val  = float(target_data[i])
                    company_val = float(X[i])
                    pct_diff = ((company_val - target_val) / abs(target_val) * 100) if target_val != 0 else 0.0
                    metric_comparison[feat] = {
                        'value':        company_val,
                        'target_value': target_val,
                        'pct_diff':     round(pct_diff, 2),
                        'status':       'above' if pct_diff > 5 else ('below' if pct_diff < -5 else 'similar'),
                    }

                results.append({
                    'ticker':            ticker,
                    'similarity':        round(similarity, 4),
                    'is_target':         ticker == target_ticker,
                    'metric_comparison': metric_comparison,
                })
            except Exception as e:
                logger.error(f"benchmark_competitors: error for {ticker}: {e}")

        if not results:
            logger.error("benchmark_competitors: results list is empty after processing")
            return {"error": "Benchmark computation failed", "companies": []}

        results.sort(key=lambda x: x['similarity'], reverse=True)
        logger.info(f"benchmark_competitors: returning {len(results)} companies, target={target_ticker}")
        return {
            "target":    target_ticker,
            "companies": results,
            "features":  available_features,
        }
    
    # ==================== FORECASTER ====================
    def _get_annual_historicals(self, tickers: List[str] = None) -> pd.DataFrame:
        """
        Query ANNUAL_FINANCIALS_10K and aggregate quarterly rows into annual figures.
        Revenue / EBITDA / Net Income are summed per fiscal year.
        Margin metrics are averaged per fiscal year.
        """
        try:
            cursor = self.hana_client.connection.cursor()

            # Normalise tickers - strip ' US Equity' suffix, keep only valid symbols
            if tickers:
                normalized = []
                for t in tickers:
                    t_clean = t.replace(' US Equity', '').strip()
                    if t_clean.isupper() and len(t_clean) <= 5:
                        normalized.append(t_clean)
                if not normalized:
                    normalized = [t.replace(' US Equity', '').strip() for t in tickers]

                placeholders = ', '.join(['?' for _ in normalized])
                query = f"""
                    SELECT "TICKER", "FISCAL_YEAR",
                           SUM("SALES_REV_TURN")  AS "SALES_REV_TURN",
                           SUM("EBITDA")           AS "EBITDA",
                           SUM("NET_INCOME")       AS "NET_INCOME",
                           AVG("EBITDA_MARGIN")    AS "EBITDA_MARGIN",
                           AVG("GROSS_MARGIN")     AS "GROSS_MARGIN"
                    FROM "{self.data_schema}"."ANNUAL_FINANCIALS_10K"
                    WHERE "TICKER" IN ({placeholders})
                    GROUP BY "TICKER", "FISCAL_YEAR"
                    ORDER BY "TICKER", "FISCAL_YEAR"
                """
                cursor.execute(query, normalized)
            else:
                query = f"""
                    SELECT "TICKER", "FISCAL_YEAR",
                           SUM("SALES_REV_TURN")  AS "SALES_REV_TURN",
                           SUM("EBITDA")           AS "EBITDA",
                           SUM("NET_INCOME")       AS "NET_INCOME",
                           AVG("EBITDA_MARGIN")    AS "EBITDA_MARGIN",
                           AVG("GROSS_MARGIN")     AS "GROSS_MARGIN"
                    FROM "{self.data_schema}"."ANNUAL_FINANCIALS_10K"
                    GROUP BY "TICKER", "FISCAL_YEAR"
                    ORDER BY "TICKER", "FISCAL_YEAR"
                """
                cursor.execute(query)

            columns = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()
            df = pd.DataFrame(rows, columns=columns)

            for col in ['SALES_REV_TURN', 'EBITDA', 'NET_INCOME', 'EBITDA_MARGIN', 'GROSS_MARGIN']:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors='coerce')

            logger.info(
                f"ANNUAL_FINANCIALS_10K: {len(df)} annual records, "
                f"{df['TICKER'].nunique() if not df.empty else 0} companies"
            )
            return df

        except Exception as e:
            logger.error(f"Error fetching annual historicals: {e}")
            return pd.DataFrame()

    def _compute_cagr_forecast(self, series_vals: list, series_years: list) -> Dict:
        """
        Given a list of annual values and their fiscal years, compute CAGR-based
        1Y and 2Y projections.  Blends long-term CAGR with recent 2-year trend.
        Returns a dict with historical, current, forecast_1y, forecast_2y, growth_rate, cagr.
        """
        if len(series_vals) < 1:
            return {}

        current = float(series_vals[-1])
        current_year = int(series_years[-1])
        hist_dict = {int(y): float(v) for y, v in zip(series_years, series_vals)}

        if len(series_vals) == 1:
            return {
                'historical': hist_dict,
                'current': current,
                'current_year': current_year,
                'forecast_1y': current * 1.05,
                'forecast_2y': current * 1.1025,
                'growth_rate': 0.05,
                'cagr': 0.05,
            }

        # Long-term CAGR
        oldest = float(series_vals[0])
        n_years = len(series_vals) - 1
        if oldest > 0 and current > 0 and n_years > 0:
            cagr = (current / oldest) ** (1.0 / n_years) - 1
            cagr = max(-0.40, min(0.60, cagr))
        else:
            cagr = 0.05

        # Recent 2-year trend (more responsive)
        if len(series_vals) >= 3:
            recent_base = float(series_vals[-3])
            if recent_base > 0 and current > 0:
                recent_cagr = (current / recent_base) ** (1.0 / 2) - 1
                recent_cagr = max(-0.40, min(0.70, recent_cagr))
                # Blend 60% recent + 40% long-term
                growth_rate = 0.60 * recent_cagr + 0.40 * cagr
            else:
                growth_rate = cagr
        else:
            growth_rate = cagr

        return {
            'historical': hist_dict,
            'current': current,
            'current_year': current_year,
            'forecast_1y': current * (1 + growth_rate),
            'forecast_2y': current * (1 + growth_rate) ** 2,
            'growth_rate': growth_rate,
            'cagr': cagr,
        }

    def get_forecasts(self, tickers: List[str]) -> Dict:
        """
        Get financial forecasts for all provided companies.

        Uses ANNUAL_FINANCIALS_10K (multi-year quarterly data aggregated to annual)
        to compute a per-company CAGR-based projection.  Falls back to the snapshot
        tables if historical data is unavailable.

        Fixes addressed:
        - No company cap: all tickers are processed (not just top 5)
        - Per-company growth rate derived from real historical CAGR (no flat 5%)
        - Returns historical series so the chart can split actual vs projected
        """
        logger.info(f"get_forecasts called with tickers: {tickers}")

        # ── Primary path: multi-year annual history ──────────────────────────
        hist_df = self._get_annual_historicals(tickers)

        if not hist_df.empty:
            forecast_metrics = ['SALES_REV_TURN', 'EBITDA', 'NET_INCOME',
                                 'EBITDA_MARGIN', 'GROSS_MARGIN']

            results = []
            all_years = sorted(hist_df['FISCAL_YEAR'].unique())

            # Normalise tickers for matching
            normalized_tickers = [t.replace(' US Equity', '').strip() for t in tickers]

            for ticker in normalized_tickers:
                ticker_hist = hist_df[hist_df['TICKER'] == ticker].sort_values('FISCAL_YEAR')
                if ticker_hist.empty:
                    logger.warning(f"No annual history for ticker: {ticker}")
                    continue

                ticker_forecasts = {}
                for metric in forecast_metrics:
                    if metric not in ticker_hist.columns:
                        continue
                    valid = ticker_hist[['FISCAL_YEAR', metric]].dropna()
                    if valid.empty:
                        continue
                    vals = valid[metric].tolist()
                    years = valid['FISCAL_YEAR'].tolist()
                    fc = self._compute_cagr_forecast(vals, years)
                    if fc:
                        ticker_forecasts[metric] = fc

                if ticker_forecasts:
                    results.append({
                        'ticker': ticker,
                        'forecasts': ticker_forecasts,
                        'historical_years': [int(y) for y in ticker_hist['FISCAL_YEAR'].tolist()],
                    })

            if results:
                logger.info(f"Generated CAGR forecasts for {len(results)} companies")
                return {
                    "companies": results,
                    "all_years": [int(y) for y in all_years],
                    "metrics": forecast_metrics,
                    "mode": "cagr_historical",
                }

        # ── Fallback: snapshot tables (single data point per ticker) ─────────
        logger.warning("Annual history unavailable — falling back to snapshot data")
        df = self.get_advanced_data(tickers)
        if df.empty:
            df = self.get_company_data(tickers)
        if df.empty:
            return {"error": "No data", "companies": []}

        snapshot_metrics = ['SALES_REV_TURN', 'NET_INCOME', 'EBITDA',
                            'CF_FREE_CASH_FLOW', 'EBITDA_MARGIN', 'GROSS_MARGIN']
        available_metrics = [m for m in snapshot_metrics if m in df.columns]

        if not available_metrics:
            return {"error": "No forecast metrics", "companies": []}

        results = []
        for ticker in tickers:
            t_clean = ticker.replace(' US Equity', '').strip()
            row = df[df['TICKER'] == t_clean].head(1)
            if row.empty:
                continue

            ticker_forecasts = {}
            for metric in available_metrics:
                current_val = float(row[metric].iloc[0]) if pd.notna(row[metric].iloc[0]) else 0
                # Without history use a modest 5 % default but make it clear it is a fallback
                growth_rate = 0.05
                ticker_forecasts[metric] = {
                    'historical': {},
                    'current': current_val,
                    'current_year': 2024,
                    'forecast_1y': current_val * (1 + growth_rate),
                    'forecast_2y': current_val * (1 + growth_rate) ** 2,
                    'growth_rate': growth_rate,
                    'cagr': growth_rate,
                }

            results.append({'ticker': t_clean, 'forecasts': ticker_forecasts})

        logger.info(f"Generated snapshot forecasts for {len(results)} companies")
        return {
            "companies": results,
            "metrics": available_metrics,
            "mode": "snapshot_fallback",
        }
    
    # ==================== SCENARIO SIMULATOR ====================
    # META real historical financials (2020-2024) used as reference dataset
    META_HISTORICAL = {
        'years':         [2020,   2021,    2022,    2023,    2024],
        'revenue':       [85965,  117929,  116609,  134902,  164500],   # $M
        'gross_profit':  [69273,  97322,   88134,   114451,  141218],
        'ebitda':        [29528,  47440,   40489,   58998,   80765],
        'net_income':    [29146,  39370,   23200,   39098,   62360],
        'gross_margin':  [80.6,   82.5,    75.6,    84.8,    85.9],
        'ebitda_margin': [34.3,   40.2,    34.7,    43.7,    49.1],
        'net_margin':    [33.9,   33.4,    19.9,    29.0,    37.9],
    }

    def _get_meta_base_data(self) -> dict:
        """Return META annual historical data — from HANA if usable, else hardcoded reference.

        HANA stores revenue in raw dollars; we scale to $M so the reference dataset
        (also in $M) can be used interchangeably.  We also de-duplicate by fiscal year
        (taking the latest row per year) so repeated quarterly snapshots don't collapse
        the CAGR to zero.
        """
        try:
            cursor = self.hana_client.connection.cursor()
            # Pull one row per fiscal year (latest snapshot for that year)
            cursor.execute(f"""
                SELECT "FISCAL_YEAR",
                       LAST_VALUE("SALES_REV_TURN") OVER (PARTITION BY "FISCAL_YEAR" ORDER BY "REPORT_DATE") AS "REV",
                       LAST_VALUE("GROSS_PROFIT")   OVER (PARTITION BY "FISCAL_YEAR" ORDER BY "REPORT_DATE") AS "GP",
                       LAST_VALUE("EBITDA")          OVER (PARTITION BY "FISCAL_YEAR" ORDER BY "REPORT_DATE") AS "EBITDA",
                       LAST_VALUE("NET_INCOME")      OVER (PARTITION BY "FISCAL_YEAR" ORDER BY "REPORT_DATE") AS "NI",
                       LAST_VALUE("GROSS_MARGIN")    OVER (PARTITION BY "FISCAL_YEAR" ORDER BY "REPORT_DATE") AS "GM",
                       LAST_VALUE("EBITDA_MARGIN")   OVER (PARTITION BY "FISCAL_YEAR" ORDER BY "REPORT_DATE") AS "EM",
                       LAST_VALUE("PROF_MARGIN")     OVER (PARTITION BY "FISCAL_YEAR" ORDER BY "REPORT_DATE") AS "PM"
                FROM "{self.data_schema}"."ANNUAL_FINANCIALS_10K"
                WHERE "TICKER" = 'META'
                ORDER BY "FISCAL_YEAR" ASC
            """)
            rows = cursor.fetchall()

            if rows and len(rows) >= 2:
                def _safe_int_year(val):
                    """Convert HANA FISCAL_YEAR to plain Python int.
                    Handles int, float, Decimal, and date-strings like '2024-01-01'."""
                    try:
                        return int(str(val)[:4])
                    except Exception:
                        return None

                def _scale(v):
                    """Convert raw dollars → $M; handle None."""
                    val = float(v or 0)
                    return round(val / 1e6, 1) if val > 1e8 else round(val, 1)

                # Deduplicate: window function returns multiple rows per FISCAL_YEAR.
                # Keep the LAST row per year (already ordered ASC so last = latest snapshot).
                seen_years = {}
                for r in rows:
                    y = _safe_int_year(r[0])
                    if y is not None:
                        seen_years[y] = r  # overwrites → keeps last row per year
                dedup_rows = [seen_years[y] for y in sorted(seen_years)]

                if len(dedup_rows) < 2:
                    raise ValueError("Not enough distinct years from HANA")

                years = [_safe_int_year(r[0]) for r in dedup_rows]
                rev_list = [_scale(r[1]) for r in dedup_rows]

                # Sanity-check: CAGR must be non-zero (> 0.5 % p.a.) to be useful
                if rev_list[0] > 0 and rev_list[-1] != rev_list[0]:
                    logger.info(f"META from HANA ANNUAL_FINANCIALS_10K: {len(dedup_rows)} distinct years")
                    return {
                        'years':         years,
                        'revenue':       rev_list,
                        'gross_profit':  [_scale(r[2]) for r in dedup_rows],
                        'ebitda':        [_scale(r[3]) for r in dedup_rows],
                        'net_income':    [_scale(r[4]) for r in dedup_rows],
                        'gross_margin':  [float(str(r[5] or 0)) for r in dedup_rows],
                        'ebitda_margin': [float(str(r[6] or 0)) for r in dedup_rows],
                        'net_margin':    [float(str(r[7] or 0)) for r in dedup_rows],
                    }

        except Exception as e:
            logger.warning(f"Could not fetch META from HANA: {e} — using reference dataset")

        logger.info("META: using hardcoded reference dataset")
        return dict(self.META_HISTORICAL)

    def simulate_scenarios(self, ticker: str = 'META', what_if_params: Dict = None) -> Dict:
        """
        Scenario Simulator using META as reference dataset.

        Returns
        -------
        dict with keys:
          historical        – actual yearly financials (Scenario 1 – solid line)
          projection_base   – extrapolated trend from last known year (Scenario 1 – dashed)
          projection_whatif – user-adjusted projection        (Scenario 2 – dashed orange)
          years_hist        – x-axis labels for historical
          years_proj        – x-axis labels for projected (2025-2027)
          base_revenue, base_margin – latest actuals
        """
        logger.info(f"simulate_scenarios called (META reference, what_if={what_if_params})")

        hist = self._get_meta_base_data()

        # ── Coerce all hist values to plain Python types ──────────────
        # Defensive cast — HANA may return Decimal, numpy, or string types
        def _to_float(v, fallback=0.0):
            try:
                return float(v) if v is not None else fallback
            except Exception:
                return fallback

        def _to_int_year(v, fallback=2024):
            try:
                return int(str(v)[:4])
            except Exception:
                return fallback

        hist = {
            'years':         [_to_int_year(y) for y in hist.get('years', [])],
            'revenue':       [_to_float(v) for v in hist.get('revenue', [])],
            'gross_profit':  [_to_float(v) for v in hist.get('gross_profit', [])],
            'ebitda':        [_to_float(v) for v in hist.get('ebitda', [])],
            'net_income':    [_to_float(v) for v in hist.get('net_income', [])],
            'gross_margin':  [_to_float(v) for v in hist.get('gross_margin', [])],
            'ebitda_margin': [_to_float(v) for v in hist.get('ebitda_margin', [])],
            'net_margin':    [_to_float(v) for v in hist.get('net_margin', [])],
        }
        logger.info(f"simulate_scenarios: hist years={hist['years']}, rev_len={len(hist['revenue'])}")

        # ── Derive average growth rates from history ──────────────────
        rev = hist['revenue']
        n   = len(rev)
        avg_rev_growth = ((rev[-1] / rev[0]) ** (1 / (n - 1)) - 1) if (rev and rev[0]) else 0.12

        margins_ebitda = hist['ebitda_margin'] or [34.3]
        avg_margin     = sum(margins_ebitda) / len(margins_ebitda)
        last_margin    = _to_float(margins_ebitda[-1], 49.1)
        last_revenue   = _to_float(rev[-1] if rev else 164500, 164500)

        # Defensively ensure last year is a plain int
        last_year  = _to_int_year(hist['years'][-1] if hist['years'] else 2024, 2024)
        proj_years = [last_year + i for i in range(1, 4)]  # 2025, 2026, 2027

        # ── Scenario 1: base trend projection ─────────────────────────
        base_proj_revenue = []
        base_proj_ebitda  = []
        base_proj_net     = []
        r = last_revenue
        for _ in proj_years:
            r = r * (1 + avg_rev_growth)
            base_proj_revenue.append(round(r, 1))
            base_proj_ebitda.append(round(r * last_margin / 100, 1))
            base_proj_net.append(round(r * hist['net_margin'][-1] / 100, 1))

        # ── Scenario 2: what-if projection ────────────────────────────
        if what_if_params is None:
            what_if_params = {}

        rev_growth_adj   = what_if_params.get('revenue_growth', avg_rev_growth * 100) / 100
        cost_change_pct  = what_if_params.get('cost_change', 0) / 100       # e.g. -5 → cost drops 5 %
        margin_adj_pct   = what_if_params.get('margin_adj', 0)               # direct % point addition

        # Cost change affects margin inversely
        whatif_margin = last_margin - (cost_change_pct * 100) + margin_adj_pct

        whatif_proj_revenue = []
        whatif_proj_ebitda  = []
        whatif_proj_net     = []
        r = last_revenue
        for _ in proj_years:
            r = r * (1 + rev_growth_adj)
            whatif_proj_revenue.append(round(r, 1))
            whatif_proj_ebitda.append(round(r * whatif_margin / 100, 1))
            whatif_proj_net.append(round(r * (hist['net_margin'][-1] + margin_adj_pct) / 100, 1))

        logger.info(f"Scenario sim complete: base_rev_growth={avg_rev_growth:.1%}, whatif={what_if_params}")
        # Ensure all years are plain Python ints (HANA may return numpy/Decimal types)
        safe_years_hist = [int(y) for y in hist['years']]
        safe_years_proj = [int(y) for y in proj_years]

        return {
            "ticker": "META",
            "source": "META Reference Dataset",
            "years_hist":  safe_years_hist,
            "years_proj":  safe_years_proj,
            "historical": {
                "revenue":       [float(v) for v in hist['revenue']],
                "ebitda":        [float(v) for v in hist['ebitda']],
                "net_income":    [float(v) for v in hist['net_income']],
                "gross_margin":  [float(v) for v in hist['gross_margin']],
                "ebitda_margin": [float(v) for v in hist['ebitda_margin']],
                "net_margin":    [float(v) for v in hist['net_margin']],
            },
            "projection_base": {
                "revenue":    [float(v) for v in base_proj_revenue],
                "ebitda":     [float(v) for v in base_proj_ebitda],
                "net_income": [float(v) for v in base_proj_net],
            },
            "projection_whatif": {
                "revenue":    [float(v) for v in whatif_proj_revenue],
                "ebitda":     [float(v) for v in whatif_proj_ebitda],
                "net_income": [float(v) for v in whatif_proj_net],
            },
            "base_revenue":    float(last_revenue),
            "base_margin":     float(last_margin),
            "avg_rev_growth":  float(round(avg_rev_growth * 100, 2)),
            "what_if_params":  what_if_params,
            # legacy scenario list (kept for backward compat)
            "scenarios": [
                {"name": "Current Trend",   "revenue": base_proj_revenue[0],   "margin": last_margin,   "profit": base_proj_ebitda[0]},
                {"name": "What-if Year 1",  "revenue": whatif_proj_revenue[0], "margin": whatif_margin, "profit": whatif_proj_ebitda[0]},
            ],
        }

    # ==================== GOAL TRACKER ====================
    def track_goals(self, tickers: List[str], goals: List[Dict] = None) -> Dict:
        """
        Track progress towards financial goals.
        """
        logger.info(f"track_goals called with tickers: {tickers}")
        
        df = self.get_company_data(tickers)
        if df.empty:
            return {"error": "No data", "companies": []}
        
        # Default goals if none provided
        if goals is None:
            goals = [
                {"metric": "GROSS_MARGIN", "target": 40, "label": "Gross Margin > 40%"},
                {"metric": "CUR_RATIO", "target": 1.5, "label": "Current Ratio > 1.5"},
                {"metric": "EBITDA_MARGIN", "target": 20, "label": "EBITDA Margin > 20%"},
                {"metric": "TOT_DEBT_TO_TOT_ASSET", "target": 50, "label": "Debt/Asset < 50%", "inverse": True},
            ]
        
        results = []
        for _, row in df.iterrows():
            ticker = row.get('TICKER', 'Unknown')
            
            goal_progress = []
            for goal in goals:
                metric = goal['metric']
                target = goal['target']
                inverse = goal.get('inverse', False)
                
                current_val = float(row.get(metric, 0)) if pd.notna(row.get(metric)) else 0
                
                if inverse:
                    # Lower is better (e.g., debt ratio)
                    progress = min(100, max(0, (target - current_val + target) / target * 50)) if target > 0 else 50
                    on_track = current_val <= target
                else:
                    # Higher is better
                    progress = min(100, (current_val / target * 100)) if target > 0 else 0
                    on_track = current_val >= target
                
                goal_progress.append({
                    'label': goal['label'],
                    'metric': metric,
                    'current': current_val,
                    'target': target,
                    'progress': progress,
                    'on_track': on_track
                })
            
            results.append({
                'ticker': ticker,
                'goals': goal_progress
            })
        
        logger.info(f"Tracked goals for {len(results)} companies")
        return {
            "companies": results,
            "goal_definitions": goals
        }
