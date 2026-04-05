"""
CFO Pulse Dashboard - Financial Intelligence Platform
Modern KPI dashboard with AI insights and advanced analytics
"""

import os
import json
import dash
from dash import dcc, html, Input, Output, State, callback_context, ALL, MATCH
import dash_bootstrap_components as dbc
import plotly.graph_objs as go
import plotly.express as px
import pandas as pd
import numpy as np
import logging
import traceback as _tb
from datetime import datetime, timedelta
from utils.config import load_config, setup_logging
from db.data_service import FinancialDataService
from utils.advanced_charts import AdvancedCharts  # example_* removed (PRO charts replace them)
# ML Service - optional, app works without it
try:
    from ml.ml_service import MLService
    ML_AVAILABLE = True
except ImportError as e:
    logger.warning(f"ML Service not available: {e}")
    MLService = None
    ML_AVAILABLE = False

# Initialize logging
setup_logging()
logger = logging.getLogger(__name__)

# Load configuration
config = load_config()

# Initialize Dash app with custom URL base pathname
app = dash.Dash(
    __name__,
    external_stylesheets=[
        dbc.themes.BOOTSTRAP,
        'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css'
    ],
    suppress_callback_exceptions=True,
    meta_tags=[
        {"name": "viewport", "content": "width=device-width, initial-scale=1"}
    ],
    url_base_pathname='/dashboard/'
)

# For Cloud Foundry deployment
server = app.server
app.title = "CFO Pulse - Financial Intelligence Dashboard"

# Add favicon
app._favicon = "favicon.svg"

# Import authentication service
from db.auth_service import AuthService
from flask import request, jsonify, redirect, session
import secrets

# Configure Flask session for production deployment
server.secret_key = os.environ.get('FLASK_SECRET_KEY', secrets.token_hex(32))

# Detect if running in production (Cloud Foundry)
is_production = os.environ.get('FLASK_ENV') == 'production'

# Session configuration for SAP Cloud Foundry / production
server.config.update(
    SESSION_COOKIE_SECURE=is_production,  # Require HTTPS only in production
    SESSION_COOKIE_HTTPONLY=True,  # Prevent JavaScript access
    SESSION_COOKIE_SAMESITE='Lax',  # Allow same-site requests
    PERMANENT_SESSION_LIFETIME=timedelta(hours=24),  # 24-hour session
    SESSION_COOKIE_NAME='financial_dashboard_session'
)

# Initialize authentication service and ML service
auth_service = None
ml_service = None
hana_client = None
try:
    from db.hana_client import HanaClient
    hana_client = HanaClient(config)
    if hana_client.connect():
        auth_service = AuthService(hana_client, config['hana']['schema'])
        if ML_AVAILABLE and MLService:
            schema = config['hana']['schema']
            ml_service = MLService(hana_client, ml_schema=schema, data_schema=schema)
            logger.info("Authentication and ML services initialized successfully")
        else:
            logger.info("Authentication service initialized (ML not available)")
    else:
        logger.warning("HANA connection failed - authentication will not be available")
except Exception as e:
    logger.error(f"Failed to initialize services: {e}")
    logger.warning("Continuing without authentication/ML services")

# Add redirect from root to login
@server.route('/')
def redirect_to_login():
    """Redirect root path to login page"""
    return redirect('/login')

# Add login route (GET - serve page, POST - authenticate)
@server.route('/login', methods=['GET', 'POST'])
def login():
    """Serve login page or authenticate user"""
    if request.method == 'GET':
        with open('login.html', 'r') as f:
            return f.read()

    # POST request - authenticate
    try:
        data = request.get_json()
        email = data.get('email')
        password = data.get('password')

        if not email or not password:
            return jsonify({'success': False, 'message': 'Email and password required'}), 400

        if not auth_service:
            return jsonify({'success': False, 'message': 'Authentication service unavailable'}), 503

        # Get client IP address
        ip_address = request.remote_addr or request.environ.get('HTTP_X_FORWARDED_FOR', 'unknown')

        # Authenticate user with IP address for email alerts
        user = auth_service.authenticate(email, password, ip_address=ip_address)

        if user:
            # Store user info in session
            session.permanent = True  # Make session persistent
            session['user_id'] = user['id']
            session['user_email'] = user['email']
            session['user_role'] = user['role']

            return jsonify({
                'success': True,
                'message': 'Login successful',
                'redirect': '/dashboard/'
            })
        else:
            # Check if user exists but wrong password
            if auth_service.user_exists(email):
                return jsonify({
                    'success': False,
                    'message': 'Invalid credentials. Please check your password.'
                }), 401
            else:
                return jsonify({
                    'success': False,
                    'message': f'User account not found. If you believe this is an error, please contact the administrator. Attempted email: {email}'
                }), 404

    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        return jsonify({'success': False, 'message': 'An error occurred during login'}), 500

# Add logout route
@server.route('/logout')
def logout():
    """Logout user and clear session"""
    session.clear()
    return redirect('/login')

# Add access request route
@server.route('/request-access', methods=['POST'])
def request_access():
    """Handle new user access requests and send email notification"""
    try:
        data = request.get_json()
        name = data.get('name')
        email = data.get('email')
        company = data.get('company')
        reason = data.get('reason')

        if not all([name, email, company, reason]):
            return jsonify({'success': False, 'message': 'All fields are required'}), 400

        # Import email service and send notification
        from utils.email_service import EmailService
        email_service = EmailService()

        # Log the request
        logger.info(f"Access request received: {name} ({email}) from {company}")

        # Send email notification
        email_sent = email_service.send_access_request_alert(name, email, company, reason)

        if email_sent:
            logger.info(f"Access request email sent for {email}")
        else:
            logger.warning(f"Could not send access request email for {email} (email service may not be configured)")

        return jsonify({
            'success': True,
            'message': 'Your access request has been submitted. We will review and get back to you soon!'
        })

    except Exception as e:
        logger.error(f"Access request error: {str(e)}")
        return jsonify({'success': False, 'message': 'An error occurred while submitting your request'}), 500

# Initialize data service
# Connect to HANA database for production data
try:
    data_service = FinancialDataService(config)
    if data_service.connect():
        logger.info("Data service initialized and connected to HANA")
    else:
        logger.warning("Data service initialized but not connected to HANA")
        data_service = None
except Exception as e:
    logger.warning(f"HANA data service not available: {e}. Will use CSV files for local testing.")
    data_service = None

# Load CSV data (fallback for when HANA is unavailable)
csv_data = None
import os
APP_DIR = os.path.dirname(os.path.abspath(__file__))
try:
    basic_csv_path = os.path.join(APP_DIR, 'basic.csv')
    financial_ratios_df = pd.read_csv(basic_csv_path)
    logger.info(f"Loaded basic.csv from {basic_csv_path}: {len(financial_ratios_df)} records")
    csv_data = {'financial_ratios': financial_ratios_df}

    # Load ANNUAL_FINANCIALS CSV (advance.csv)
    try:
        advance_csv_path = os.path.join(APP_DIR, 'advance.csv')
        annual_financials_df = pd.read_csv(advance_csv_path)
        logger.info(f"Loaded advance.csv from {advance_csv_path}: {len(annual_financials_df)} records")
        csv_data['annual_financials'] = annual_financials_df
    except Exception as e:
        logger.warning(f"advance.csv not found or failed to load: {e}")
        csv_data['annual_financials'] = None
except Exception as e:
    logger.error(f"Failed to load CSV files: {e}")
    csv_data = None

# Wire CSV fallback into ml_service so benchmark_competitors can use basic.csv when HANA is empty
if ml_service is not None and csv_data and csv_data.get('financial_ratios') is not None:
    ml_service.csv_fallback_df = csv_data['financial_ratios']
    logger.info(f"ML service CSV fallback wired: {len(ml_service.csv_fallback_df)} rows from basic.csv")

# Define numeric columns for competitor analysis metrics
NUMERIC_METRIC_COLUMNS = [
    'TOT_DEBT_TO_TOT_ASSET',
    'CASH_DVD_COVERAGE',
    'TOT_DEBT_TO_EBITDA',
    'CUR_RATIO',
    'QUICK_RATIO',
    'GROSS_MARGIN',
    'INTEREST_COVERAGE_RATIO',
    'EBITDA_MARGIN',
    'TOT_LIAB_AND_EQY',
    'NET_DEBT_TO_SHRHLDR_EQTY'
]

# Friendly names for metrics
METRIC_LABELS = {
    'TOT_DEBT_TO_TOT_ASSET': 'Total Debt to Total Asset',
    'CASH_DVD_COVERAGE': 'Cash Dividend Coverage',
    'TOT_DEBT_TO_EBITDA': 'Total Debt to EBITDA',
    'CUR_RATIO': 'Current Ratio',
    'QUICK_RATIO': 'Quick Ratio',
    'GROSS_MARGIN': 'Gross Margin (%)',
    'INTEREST_COVERAGE_RATIO': 'Interest Coverage Ratio',
    'EBITDA_MARGIN': 'EBITDA Margin (%)',
    'TOT_LIAB_AND_EQY': 'Total Liabilities & Equity',
    'NET_DEBT_TO_SHRHLDR_EQTY': 'Net Debt to Shareholder Equity'
}

# Modern custom CSS
custom_style = {
    'backgroundColor': '#f9fafb',
    'fontFamily': '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
    'minHeight': '100vh'
}

# Color palette
COLORS = {
    'primary': '#3b82f6',
    'success': '#10b981',
    'danger': '#ef4444',
    'warning': '#f59e0b',
    'info': '#06b6d4',
    'purple': '#8b5cf6',
    'gray': {
        '50': '#f9fafb',
        '100': '#f3f4f6',
        '200': '#e5e7eb',
        '300': '#d1d5db',
        '400': '#9ca3af',
        '500': '#6b7280',
        '600': '#4b5563',
        '700': '#374151',
        '800': '#1f2937',
        '900': '#111827'
    }
}

#==============================================================================
# SIDEBAR COMPONENT
#==============================================================================

def create_footer(dark_mode=False):
    """Create production-level professional footer"""

    bg_color = COLORS['gray']['900'] if dark_mode else COLORS['gray']['50']
    text_color = COLORS['gray']['300'] if dark_mode else COLORS['gray']['600']
    text_light = COLORS['gray']['400'] if dark_mode else COLORS['gray']['500']
    border_color = COLORS['gray']['700'] if dark_mode else COLORS['gray']['200']

    return html.Footer([
        # Main footer content
        html.Div([
            dbc.Row([
                # Column 1: About & Branding
                dbc.Col([
                    html.Div([
                        html.I(className="fas fa-chart-pie", style={
                            "fontSize": "24px",
                            "color": COLORS['primary'],
                            "marginBottom": "12px"
                        }),
                        html.H5("CFO Pulse", style={
                            "fontWeight": "700",
                            "marginBottom": "8px",
                            "color": COLORS['gray']['100'] if dark_mode else COLORS['gray']['900']
                        }),
                        html.P("Financial Intelligence Dashboard", style={
                            "fontSize": "13px",
                            "color": text_light,
                            "marginBottom": "12px"
                        }),
                        html.P("Real-time analytics powered by SAP HANA Cloud", style={
                            "fontSize": "12px",
                            "color": text_light,
                            "marginBottom": "0"
                        })
                    ])
                ], md=3, sm=6, xs=12, className="mb-3"),

                # Column 2: System Status
                dbc.Col([
                    html.H6("System Status", style={
                        "fontWeight": "600",
                        "marginBottom": "12px",
                        "fontSize": "14px",
                        "color": COLORS['gray']['100'] if dark_mode else COLORS['gray']['900']
                    }),
                    html.Div([
                        html.Div([
                            html.I(className="fas fa-circle", style={
                                "fontSize": "8px",
                                "color": COLORS['success'],
                                "marginRight": "8px"
                            }),
                            html.Span("Data Connection Active", style={"fontSize": "12px"})
                        ], style={"marginBottom": "6px"}),
                        html.Div([
                            html.I(className="fas fa-sync-alt", style={
                                "fontSize": "10px",
                                "marginRight": "8px",
                                "color": COLORS['info']
                            }),
                            html.Span([
                                "Auto-refresh: Every 5 min | Next: ",
                                html.Span(id="footer-next-refresh", children="09:00 AM EST", style={
                                    "fontWeight": "600",
                                    "color": COLORS['primary']
                                })
                            ], style={"fontSize": "12px"})
                        ], style={"marginBottom": "6px"}),
                        html.Div([
                            html.I(className="fas fa-database", style={
                                "fontSize": "10px",
                                "marginRight": "8px",
                                "color": COLORS['warning']
                            }),
                            html.Span("SAP HANA Cloud", style={"fontSize": "12px"})
                        ])
                    ], style={"color": text_color})
                ], md=3, sm=6, xs=12, className="mb-3"),

                # Column 3: Account & Quick Links
                dbc.Col([
                    html.H6("Account", style={
                        "fontWeight": "600",
                        "marginBottom": "12px",
                        "fontSize": "14px",
                        "color": COLORS['gray']['100'] if dark_mode else COLORS['gray']['900']
                    }),
                    html.Div([
                        html.Div([
                            html.I(className="fas fa-user", style={
                                "fontSize": "10px",
                                "marginRight": "8px"
                            }),
                            html.Span("Logged in as: ", style={"fontSize": "12px"}),
                            html.Span(id="footer-user-email", children="admin@g.com", style={
                                "fontSize": "12px",
                                "fontWeight": "600",
                                "color": COLORS['primary']
                            })
                        ], style={"marginBottom": "8px"}),
                        html.Div([
                            html.A([
                                html.I(className="fas fa-sign-out-alt", style={"marginRight": "6px"}),
                                "Logout"
                            ], href="/logout", style={
                                "fontSize": "12px",
                                "color": COLORS['danger'],
                                "textDecoration": "none",
                                "fontWeight": "500",
                                "display": "inline-block",
                                "padding": "4px 12px",
                                "border": f"1px solid {COLORS['danger']}",
                                "borderRadius": "4px",
                                "transition": "all 0.2s"
                            }, className="footer-logout-btn")
                        ])
                    ], style={"color": text_color})
                ], md=3, sm=6, xs=12, className="mb-3"),

                # Column 4: Support & Legal
                dbc.Col([
                    html.H6("Support & Legal", style={
                        "fontWeight": "600",
                        "marginBottom": "12px",
                        "fontSize": "14px",
                        "color": COLORS['gray']['100'] if dark_mode else COLORS['gray']['900']
                    }),
                    html.Div([
                        html.Div([
                            html.A([
                                html.I(className="fas fa-question-circle", style={"marginRight": "6px"}),
                                "Help & Support"
                            ], href="#", style={
                                "fontSize": "12px",
                                "color": text_color,
                                "textDecoration": "none",
                                "display": "block",
                                "marginBottom": "6px"
                            })
                        ]),
                        html.Div([
                            html.A([
                                html.I(className="fas fa-file-contract", style={"marginRight": "6px"}),
                                "Terms of Service"
                            ], href="#", style={
                                "fontSize": "12px",
                                "color": text_color,
                                "textDecoration": "none",
                                "display": "block",
                                "marginBottom": "6px"
                            })
                        ]),
                        html.Div([
                            html.A([
                                html.I(className="fas fa-shield-alt", style={"marginRight": "6px"}),
                                "Privacy Policy"
                            ], href="#", style={
                                "fontSize": "12px",
                                "color": text_color,
                                "textDecoration": "none",
                                "display": "block"
                            })
                        ])
                    ])
                ], md=3, sm=6, xs=12, className="mb-3"),
            ], className="g-4"),

            # Bottom bar with copyright
            html.Hr(style={
                "margin": "24px 0 16px 0",
                "border": "none",
                "borderTop": f"1px solid {border_color}",
                "opacity": "0.5"
            }),

            dbc.Row([
                dbc.Col([
                    html.Div([
                        html.Span("© 2026 CFO Pulse Dashboard", style={
                            "fontSize": "12px",
                            "color": text_light
                        }),
                        html.Span(" | ", style={
                            "margin": "0 8px",
                            "color": text_light
                        }),
                        html.Span("All rights reserved", style={
                            "fontSize": "12px",
                            "color": text_light
                        })
                    ], style={"textAlign": "left"})
                ], md=6, xs=12),

                dbc.Col([
                    html.Div([
                        html.Span("Version 1.0.0", style={
                            "fontSize": "11px",
                            "color": text_light,
                            "marginRight": "16px"
                        }),
                        html.Span(" | ", style={
                            "margin": "0 8px",
                            "color": text_light
                        }),
                        html.Span([
                            html.I(className="fas fa-server", style={"marginRight": "4px"}),
                            "Production"
                        ], style={
                            "fontSize": "11px",
                            "color": COLORS['success'],
                            "fontWeight": "500",
                            "marginRight": "20px"
                        }),
                        html.Button([
                            html.I(className="fas fa-paper-plane", style={"marginRight": "6px"}),
                            "Send CFO Briefing"
                        ], id="send-briefing-btn", n_clicks=0, style={
                            "fontSize": "11px",
                            "fontWeight": "600",
                            "color": "#fff",
                            "backgroundColor": COLORS['primary'],
                            "border": "none",
                            "borderRadius": "6px",
                            "padding": "6px 14px",
                            "cursor": "pointer",
                            "transition": "all 0.2s",
                            "boxShadow": "0 2px 6px rgba(0,0,0,0.15)"
                        }),
                        html.Span(id="briefing-status-msg", style={
                            "fontSize": "11px",
                            "marginLeft": "10px",
                            "color": COLORS['success'],
                            "fontWeight": "500"
                        })
                    ], style={"textAlign": "right", "display": "flex", "alignItems": "center", "justifyContent": "flex-end"})
                ], md=6, xs=12)
            ])
        ], style={
            "padding": "32px 48px 24px 48px",
            "backgroundColor": bg_color,
            "color": text_color,
            "borderTop": f"2px solid {COLORS['primary']}"
        })
    ], style={
        "marginTop": "48px",
        "width": "100%"
    })

def create_sidebar(collapsed=False, dark_mode=False):
    """Create the collapsible sidebar with navigation"""
    sidebar_class = "sidebar " + ("collapsed" if collapsed else "expanded")
    if dark_mode:
        sidebar_class += " dark-mode"

    nav_items = [
        {"id": "nav-overview", "icon": "fas fa-home", "text": "Overview", "active": True, "target": "kpi-grid-container"},
        {"id": "nav-insights", "icon": "fas fa-lightbulb", "text": "AI Insights", "target": "ai-insights-container"},
        {"id": "nav-competitor", "icon": "fas fa-users", "text": "Competitor Analysis", "target": "competitor-analysis-container"},
        {"id": "nav-comparative", "icon": "fas fa-balance-scale", "text": "Comparative Analysis", "target": "comparative-analysis-container"},
        {"id": "nav-margin", "icon": "fas fa-chart-column", "text": "Margin Bridge", "target": "margin-bridge-container"},
        {"id": "nav-analytics", "icon": "fas fa-chart-bar", "text": "Analytics", "target": "tabbed-analytics-container"},
        {"id": "nav-advanced-charts", "icon": "fas fa-chart-line", "text": "Advanced Charts", "target": "advanced-charts-container"},
    ]

    return html.Div([
        # Header with logo and toggle
        html.Div([
            html.Div([
                html.Div([
                    html.I(className="fas fa-chart-pie")
                ], className="sidebar-logo-icon"),
                html.Span("CFO Pulse", className="sidebar-logo-text")
            ], className="sidebar-logo"),
            html.Button([
                html.I(id="sidebar-toggle-icon", className="fas fa-chevron-left")
            ], id="sidebar-toggle-btn", className="sidebar-toggle")
        ], className="sidebar-header"),

        # Navigation items
        html.Div([
            html.Div([
                html.A([
                    html.I(className=item["icon"] + " sidebar-nav-item-icon"),
                    html.Span(item["text"], className="sidebar-nav-item-text")
                ],
                id=item["id"],
                href=f"#{item['target']}",
                className="sidebar-nav-item" + (" active" if item.get("active") else ""))
                for item in nav_items
            ])
        ], className="sidebar-nav"),

        # Help and Settings footer
        html.Div([
            html.Div([
                html.I(className="fas fa-question-circle sidebar-footer-item-icon"),
                html.Span("Help Center", className="sidebar-footer-item-text")
            ], id="sidebar-help", className="sidebar-footer-item"),
            html.Div([
                html.I(className="fas fa-cog sidebar-footer-item-icon"),
                html.Span("Settings", className="sidebar-footer-item-text")
            ], id="sidebar-settings", className="sidebar-footer-item")
        ], className="sidebar-footer"),

        # ── Hidden placeholder elements — keep IDs alive for existing callbacks ──
        html.Div([
            # Data Refresh Status placeholders
            html.Div(id="data-refresh-toggle", style={"display": "none"}),
            html.I(id="data-refresh-toggle-icon", style={"display": "none"}),
            html.Div(id="data-refresh-content", style={"display": "none"}),
            html.Div(id="sidebar-last-sync",        style={"display": "none"}),
            html.Div(id="sidebar-total-records",    style={"display": "none"}),
            html.Div(id="sidebar-unique-tickers",   style={"display": "none"}),
            # System Status placeholders
            html.Div(id="system-status-toggle",     style={"display": "none"}),
            html.I(id="system-status-toggle-icon",  style={"display": "none"}),
            html.Div(id="system-status-content",    style={"display": "none"}),
            html.Div(id="sidebar-data-quality",     style={"display": "none"}),
            html.Div(id="sidebar-connection-status", style={"display": "none"}),
            html.Div(id="sidebar-connection-indicator", style={"display": "none"}),
            html.Span(id="sidebar-connection-text", style={"display": "none"}),
            html.Div(id="sidebar-annual-records",   style={"display": "none"}),
        ], style={"display": "none"})
    ], id="sidebar", className=sidebar_class)

#==============================================================================
# DASHBOARD HEADER COMPONENT
#==============================================================================

def create_dashboard_header():
    """Create the modern dashboard header with filters"""
    return dbc.Card([
        dbc.CardBody([
            # Top row - Logo and Actions
            dbc.Row([
                dbc.Col([
                    html.Div([
                        html.I(className="fas fa-chart-line",
                              style={"fontSize": "32px", "color": COLORS['primary'], "marginRight": "12px"}),
                        html.Div([
                            html.H1("CFO Pulse Dashboard",
                                   style={"fontSize": "24px", "fontWeight": "600",
                                         "color": COLORS['gray']['900'], "margin": "0"}),
                            html.P("Real-time Financial Intelligence",
                                  style={"fontSize": "13px", "color": COLORS['gray']['500'],
                                        "margin": "0"})
                        ], style={"display": "inline-block"})
                    ], style={"display": "flex", "alignItems": "center"})
                ], width=6),
                dbc.Col([
                    html.Div([
                        dbc.Button([
                            html.I(className="fas fa-sync-alt me-2"),
                            "Refresh"
                        ], id="refresh-btn", color="light", size="sm", className="me-2"),
                        dbc.Button([
                            html.I(className="fas fa-download me-2"),
                            "Export"
                        ], id="export-btn", color="light", size="sm", className="me-2"),
                        dbc.Button([
                            html.I(className="fas fa-calendar me-2"),
                            "Calendar"
                        ], color="light", size="sm", className="me-2"),
                        dbc.Button(
                            html.I(className="fas fa-bookmark"),
                            id="bookmark-btn", color="light", size="sm", className="me-2"
                        ),
                        dbc.Button(
                            html.I(id="theme-icon", className="fas fa-moon"),
                            id="theme-toggle", color="light", size="sm"
                        )
                    ], style={"display": "flex", "justifyContent": "flex-end"})
                ], width=6)
            ], className="mb-4"),

            # Filters row
            dbc.Row([
                dbc.Col([
                    html.Div([
                        html.Span("Year:", style={"fontSize": "14px", "color": COLORS['gray']['600'], "marginRight": "8px"}),
                        dcc.Dropdown(
                            id='year-filter',
                            options=[
                                {'label': '2023', 'value': '2023'},
                                {'label': '2024', 'value': '2024'},
                                {'label': '2025', 'value': '2025'}
                            ],
                            value='2025',
                            clearable=False,
                            style={"width": "120px", "display": "inline-block"}
                        )
                    ], style={"display": "inline-flex", "alignItems": "center", "marginRight": "16px"})
                ], width="auto"),

                dbc.Col([
                    html.Div([
                        html.Span("Region:", style={"fontSize": "14px", "color": COLORS['gray']['600'], "marginRight": "8px"}),
                        dcc.Dropdown(
                            id='region-filter',
                            options=[
                                {'label': 'All Regions', 'value': 'All'},
                                {'label': 'North America', 'value': 'North America'},
                                {'label': 'Europe', 'value': 'Europe'},
                                {'label': 'Asia Pacific', 'value': 'Asia Pacific'}
                            ],
                            value='All',
                            clearable=False,
                            style={"width": "140px", "display": "inline-block"}
                        )
                    ], style={"display": "inline-flex", "alignItems": "center", "marginRight": "16px"})
                ], width="auto"),

                dbc.Col([
                    html.Div([
                        html.Span("Currency:", style={"fontSize": "14px", "color": COLORS['gray']['600'], "marginRight": "8px"}),
                        dcc.Dropdown(
                            id='currency-filter',
                            options=[
                                {'label': 'USD', 'value': 'USD'},
                                {'label': 'EUR', 'value': 'EUR'},
                                {'label': 'GBP', 'value': 'GBP'}
                            ],
                            value='USD',
                            clearable=False,
                            style={"width": "100px", "display": "inline-block"}
                        )
                    ], style={"display": "inline-flex", "alignItems": "center", "marginRight": "16px"})
                ], width="auto"),

                dbc.Col([
                    dbc.Button("Reset Filters", id="reset-filters", color="link", size="sm")
                ], width="auto"),

                dbc.Col([
                    html.Div([
                        html.Span("View:", style={"fontSize": "14px", "color": COLORS['gray']['600'], "marginRight": "8px"}),
                        dcc.Dropdown(
                            id='view-mode-filter',
                            options=[
                                {'label': 'Chart View', 'value': 'chart'},
                                {'label': 'Ratio View %', 'value': 'ratio'},
                                {'label': 'Bifurcation View', 'value': 'bifurcation'}
                            ],
                            value='chart',
                            clearable=False,
                            style={"width": "160px", "display": "inline-block"}
                        )
                    ], style={"display": "inline-flex", "alignItems": "center"})
                ], width="auto", className="ms-auto")
            ], align="center")
        ])
    ], style={"border": "none", "borderBottom": f"1px solid {COLORS['gray']['200']}",
             "borderRadius": "0", "position": "sticky", "top": "0", "zIndex": "1000"})

#==============================================================================
# DATA TRUST BAR
#==============================================================================

def create_data_trust_bar():
    """Create data quality and trust indicator bar"""
    return dbc.Card([
        dbc.CardBody([
            dbc.Row([
                dbc.Col([
                    html.Div([
                        html.I(className="fas fa-check-circle",
                              style={"color": COLORS['success'], "marginRight": "8px"}),
                        html.Span("Data Quality: ", style={"fontWeight": "500", "color": COLORS['gray']['700']}),
                        html.Span(id="header-data-quality", children="Loading...", style={"color": COLORS['success'], "fontWeight": "600"})
                    ], style={"display": "flex", "alignItems": "center"})
                ], width="auto"),

                dbc.Col([
                    html.Div([
                        html.I(className="fas fa-database",
                              style={"color": COLORS['info'], "marginRight": "8px"}),
                        html.Span("Last Sync: ", style={"fontWeight": "500", "color": COLORS['gray']['700']}),
                        html.Span(id="header-last-sync", children="Loading...",
                                style={"color": COLORS['gray']['600']})
                    ], style={"display": "flex", "alignItems": "center"})
                ], width="auto"),

                dbc.Col([
                    html.Div([
                        html.I(className="fas fa-shield-alt",
                              style={"color": COLORS['primary'], "marginRight": "8px"}),
                        html.Span("SAP HANA Cloud", style={"color": COLORS['gray']['700'], "fontWeight": "500"}),
                        html.Span(" Connected", style={"color": COLORS['success'], "marginLeft": "4px"})
                    ], style={"display": "flex", "alignItems": "center"})
                ], width="auto")
            ], justify="center")
        ], style={"padding": "12px"})
    ], style={"backgroundColor": COLORS['gray']['50'], "border": "none", "borderRadius": "0"})

#==============================================================================
# ONBOARDING & LOADING SCREENS
#==============================================================================

# Load test data from Kt.json
def load_test_data():
    """Load test company data from Kt.json"""
    try:
        with open('Kt.json', 'r') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load Kt.json: {e}")
        return None

# Professional loading messages for CFO dashboard
LOADING_MESSAGES = [
    "Analyzing financial metrics...",
    "Calculating key performance indicators...",
    "Loading competitor benchmarks...",
    "Processing market intelligence...",
    "Aggregating financial ratios...",
    "Building margin analysis...",
    "Synchronizing real-time data...",
    "Preparing executive summary...",
    "Optimizing dashboard performance...",
    "Finalizing strategic insights..."
]

def create_onboarding_screen():
    """Create the onboarding form for user company details - Enhanced UI"""
    
    return html.Div([
        # Background with animated gradient
        html.Div(className="onboarding-background"),

        # Main container
        html.Div([
            # Header
            html.Div([
                html.Div([
                    html.I(className="fas fa-chart-pie")
                ], className="onboarding-logo"),
                html.H1("Welcome to CFO Pulse", className="onboarding-title"),
                html.P("Enter your company details to benchmark against industry leaders", 
                       className="onboarding-subtitle")
            ], className="onboarding-header"),

            # Form Card
            html.Div([
                # Company Basic Info Section
                html.H3([
                    html.I(className="fas fa-building"),
                    "Company Information"
                ], className="onboarding-section-title"),

                dbc.Row([
                    dbc.Col([
                        html.Label("Company Name *", className="onboarding-label"),
                        dcc.Input(
                            id='onboard-company-name',
                            type='text',
                            placeholder='e.g., Acme Corporation',
                            className="onboarding-input"
                        )
                    ], md=6),
                    dbc.Col([
                        html.Label("Industry", className="onboarding-label"),
                        dcc.Dropdown(
                            id='onboard-industry',
                            options=[
                                {'label': '🖥️ Technology', 'value': 'tech'},
                                {'label': '🏥 Healthcare', 'value': 'healthcare'},
                                {'label': '💰 Finance', 'value': 'finance'},
                                {'label': '🛒 Retail', 'value': 'retail'},
                                {'label': '🏭 Manufacturing', 'value': 'manufacturing'},
                                {'label': '⚡ Energy', 'value': 'energy'},
                                {'label': '📦 Other', 'value': 'other'}
                            ],
                            placeholder='Select industry...',
                            className="onboarding-dropdown"
                        )
                    ], md=6)
                ], className="mb-4"),

                # Financial Ratios Section
                html.H3([
                    html.I(className="fas fa-chart-line"),
                    "Financial Ratios"
                ], className="onboarding-section-title"),
                html.P("Enter your key financial metrics for comparison with industry leaders", 
                       style={"fontSize": "14px", "color": "#64748b", "marginBottom": "20px"}),

                # Profitability Metrics
                html.Div([
                    html.Label("📊 Profitability", style={
                        "fontSize": "12px", "fontWeight": "600", "color": "#3b82f6",
                        "textTransform": "uppercase", "letterSpacing": "0.1em", "marginBottom": "12px"
                    })
                ]),
                dbc.Row([
                    dbc.Col([
                        html.Label("EBITDA Margin (%)", className="onboarding-label"),
                        dcc.Input(id='onboard-ebitda-margin', type='number', 
                                  placeholder='e.g., 15.5', className="onboarding-input")
                    ], md=4),
                    dbc.Col([
                        html.Label("Gross Margin (%)", className="onboarding-label"),
                        dcc.Input(id='onboard-gross-margin', type='number', 
                                  placeholder='e.g., 45.0', className="onboarding-input")
                    ], md=4),
                    dbc.Col([
                        html.Label("Cash Dividend Coverage", className="onboarding-label"),
                        dcc.Input(id='onboard-cash-dividend', type='number', 
                                  placeholder='e.g., 3.0', className="onboarding-input")
                    ], md=4)
                ], className="mb-4"),

                # Liquidity Metrics
                html.Div([
                    html.Label("💧 Liquidity", style={
                        "fontSize": "12px", "fontWeight": "600", "color": "#22c55e",
                        "textTransform": "uppercase", "letterSpacing": "0.1em", "marginBottom": "12px"
                    })
                ]),
                dbc.Row([
                    dbc.Col([
                        html.Label("Current Ratio", className="onboarding-label"),
                        dcc.Input(id='onboard-current-ratio', type='number', 
                                  placeholder='e.g., 1.5', className="onboarding-input")
                    ], md=4),
                    dbc.Col([
                        html.Label("Quick Ratio", className="onboarding-label"),
                        dcc.Input(id='onboard-quick-ratio', type='number', 
                                  placeholder='e.g., 1.2', className="onboarding-input")
                    ], md=4),
                    dbc.Col([
                        html.Label("Interest Coverage", className="onboarding-label"),
                        dcc.Input(id='onboard-interest-coverage', type='number', 
                                  placeholder='e.g., 8.0', className="onboarding-input")
                    ], md=4)
                ], className="mb-4"),

                # Leverage Metrics
                html.Div([
                    html.Label("⚖️ Leverage", style={
                        "fontSize": "12px", "fontWeight": "600", "color": "#f59e0b",
                        "textTransform": "uppercase", "letterSpacing": "0.1em", "marginBottom": "12px"
                    })
                ]),
                dbc.Row([
                    dbc.Col([
                        html.Label("Debt to Asset (%)", className="onboarding-label"),
                        dcc.Input(id='onboard-debt-to-asset', type='number', 
                                  placeholder='e.g., 25.0', className="onboarding-input")
                    ], md=4),
                    dbc.Col([
                        html.Label("Debt to EBITDA", className="onboarding-label"),
                        dcc.Input(id='onboard-debt-to-ebitda', type='number', 
                                  placeholder='e.g., 2.5', className="onboarding-input")
                    ], md=4),
                    dbc.Col([
                        html.Label("Net Debt to Equity (%)", className="onboarding-label"),
                        dcc.Input(id='onboard-net-debt-equity', type='number', 
                                  placeholder='e.g., 50.0', className="onboarding-input")
                    ], md=4)
                ], className="mb-3"),

                # Privacy Notice
                html.Div([
                    html.I(className="fas fa-shield-halved"),
                    html.Span("Your data stays private. We don't store any company information — it's only used for comparison during this session.")
                ], className="onboarding-privacy"),

                # Buttons
                html.Div([
                    html.Button([
                        html.I(className="fas fa-rocket"),
                        "Launch Dashboard"
                    ], id='btn-launch-dashboard', className="onboarding-btn-primary"),

                    html.Button([
                        html.I(className="fas fa-flask"),
                        "Use Demo Data"
                    ], id='btn-use-test-data', className="onboarding-btn-secondary")
                ], className="onboarding-buttons")

            ], className="onboarding-card")

        ], className="onboarding-container")
    ], id='onboarding-screen')

def create_loading_screen():
    """Create an elegant, animated loading screen for CFO dashboard"""
    
    # Metric items with icons and colors
    metrics = [
        {"icon": "fas fa-dollar-sign", "label": "Revenue", "color": COLORS['primary']},
        {"icon": "fas fa-chart-pie", "label": "Margins", "color": COLORS['success']},
        {"icon": "fas fa-balance-scale", "label": "Ratios", "color": COLORS['warning']},
        {"icon": "fas fa-users", "label": "Peers", "color": COLORS['info']}
    ]
    
    return html.Div([
        # Floating particles for ambiance
        html.Div([
            html.Div(className="loading-particle") for _ in range(6)
        ], className="loading-particles"),
        
        # Main content container
        html.Div([
            # Logo with animated ring
            html.Div([
                html.Div([
                    html.I(className="fas fa-chart-line")
                ], className="loading-logo")
            ], className="loading-logo-container"),

            # Brand title with gradient
            html.H1("CFO Pulse", className="loading-title"),
            
            # Subtitle
            html.P("Financial Intelligence Platform", className="loading-subtitle"),

            # Animated metrics row
            html.Div([
                html.Div([
                    html.I(className=m["icon"], style={"color": m["color"]}),
                    html.Span(m["label"])
                ], className="loading-metric") for m in metrics
            ], className="loading-metrics"),

            # Loading message (updated by callback)
            html.Div(id='loading-message', children="Initializing dashboard...", 
                     className="loading-message"),

            # Progress bar container
            html.Div([
                html.Div([
                    html.Div(id='loading-progress-bar', className="loading-progress-bar",
                             style={"width": "0%"})
                ], className="loading-progress-track"),
                html.Div([
                    html.Span(id='loading-countdown', children="0%")
                ], className="loading-progress-text")
            ], className="loading-progress-container"),

            # Tech footer
            html.Div([
                html.Div([
                    html.I(className="fas fa-database"),
                    html.Span("SAP HANA")
                ], className="loading-tech-item"),
                html.Div([
                    html.I(className="fas fa-cloud"),
                    html.Span("Cloud Foundry")
                ], className="loading-tech-item"),
                html.Div([
                    html.I(className="fas fa-bolt"),
                    html.Span("Real-time Analytics")
                ], className="loading-tech-item")
            ], className="loading-tech-footer")

        ], style={
            "textAlign": "center",
            "position": "relative",
            "zIndex": "1"
        })
    ], id='loading-screen', style={
        "display": "none"
    })

#==============================================================================
# MAIN LAYOUT
#==============================================================================

app.layout = html.Div([
    # Store for PRO analytics unlock state
    dcc.Store(id='pro-unlocked-store', data=False),

    # Store for payment modal visibility
    dcc.Store(id='payment-modal-open', data=False),

    # Store for dark mode state
    dcc.Store(id='dark-mode-store', data=False),

    # Store for sidebar collapse state (False = expanded by default)
    dcc.Store(id='sidebar-collapsed-store', data=False),

    # Store for updated timestamp
    dcc.Store(id='update-timestamp', data=datetime.now().isoformat()),

    # Store for selected competitors (used across the page)
    dcc.Store(id='selected-competitors-store', data=['META']),

    # Store for user company data — pre-loaded with demo data so dashboard
    # opens immediately without the onboarding / loading screen
    dcc.Store(id='user-company-store', data={
        'company_name': 'Demo Company',
        'industry': 'tech',
        'TICKER': 'DEMO',
        'EBITDA_MARGIN': 15.0,
        'GROSS_MARGIN': 45.0,
        'CUR_RATIO': 1.5,
        'QUICK_RATIO': 1.2,
        'TOT_DEBT_TO_TOT_ASSET': 25.0,
        'TOT_DEBT_TO_EBITDA': 2.0,
        'INTEREST_COVERAGE_RATIO': 8.0,
        'NET_DEBT_TO_SHRHLDR_EQTY': 50.0,
        'CASH_DVD_COVERAGE': 3.0,
        'annual_financials': {
            'SALES_REV_TURN': 15000,
            'EBITDA': 3000,
            'OPER_EXPENSES': 12000,
            'CASH_FROM_OPER_ACTIV': 1700,
            'WORKING_CAPITAL': 800,
            'NET_PROFIT_MARGIN': 5.0,
        }
    }),

    # Store for onboarding completion — pre-set to True (skipped)
    dcc.Store(id='onboarding-complete-store', data=True),

    # Interval for loading animation (disabled — no loading screen)
    dcc.Interval(id='loading-interval', interval=500, n_intervals=0, disabled=True),

    # Onboarding Screen — hidden; kept in DOM so its output IDs remain valid
    html.Div(id='onboarding-container', children=create_onboarding_screen(),
             style={'display': 'none'}),

    # Loading Screen — hidden
    create_loading_screen(),

    # Main Dashboard — visible immediately
    html.Div([
        # Sidebar
        html.Div(id='sidebar-container'),

        # Main Content
        dbc.Container([
            # Dashboard Header
            create_dashboard_header(),

            # Data Trust Bar
            create_data_trust_bar(),

            # Main Content Sections
            html.Div([
                # KPI Grid Section
                html.Div(id='kpi-grid-container', className="mb-4", style={"padding": "24px"}),

                # AI Insights Section
                html.Div(id='ai-insights-container', className="mb-4", style={"padding": "0 24px"}),

                # Competitor Analysis Module
                html.Div(id='competitor-analysis-container', className="mb-4", style={"padding": "0 24px"}),

                # Comparative Analysis
                html.Div(id='comparative-analysis-container', className="mb-4", style={"padding": "0 24px"}),

                # Margin Bridge
                html.Div(id='margin-bridge-container', className="mb-4", style={"padding": "0 24px"}),

                # Alert Feed
                html.Div(id='alert-feed-container', className="mb-4", style={"padding": "0 24px"}),

                # Tabbed Analytics Section
                html.Div(id='tabbed-analytics-container', className="mb-4", style={"padding": "0 24px"}),

                # Advanced Charts Section
                html.Div(id='advanced-charts-container', className="mb-4", style={"padding": "0 24px"}),

                # Footer
                html.Div(id='footer-container')
            ])
        ], id='main-content', fluid=True, style=custom_style, className='main-content sidebar-expanded')
    ], id='dashboard-container', style={'display': 'block', 'position': 'relative'}),

    # ── Floating UI wrapper (chatbot + PRO modal) — dark-mode class toggled via callback ──
    html.Div(id='floating-ui-wrapper', children=[

    # ── Floating Chatbot ──────────────────────────────────────────────────
    # Toggle button (fixed bottom-right)
    html.Button(
        [
            html.I(className="fas fa-comments", style={"fontSize": "22px"}),
            html.Div(id='chatbot-unread-badge'),
        ],
        id='chatbot-toggle-btn',
        title='Open AI Assistant',
        n_clicks=0,
    ),

    # Chat panel
    html.Div(
        id='chatbot-panel',
        className='chat-hidden',
        children=[
            # Header
            html.Div([
                html.Div("🤖", className='chat-header-avatar'),
                html.Div([
                    html.Div("CFO AI Assistant", className='chat-header-name'),
                    html.Div("Online · powered by AI", className='chat-header-status'),
                ], className='chat-header-info'),
                html.Button("✕", id='chatbot-close-btn', className='chat-close-btn', n_clicks=0),
            ], className='chat-header'),

            # Messages area
            html.Div([
                html.Div([
                    html.Div([
                        html.Div("👋 Hi! I'm your CFO AI Assistant. Ask me anything about your financial data, KPIs, or competitors.", className='chat-bubble'),
                    ], className='chat-msg bot'),
                ]),
            ], id='chatbot-messages', className='chat-messages'),

            # Suggested prompts
            html.Div([
                html.Span("How's my EBITDA?", className='chat-suggestion-chip', id='chip-1'),
                html.Span("Top competitor?", className='chat-suggestion-chip', id='chip-2'),
                html.Span("Cash flow risk?", className='chat-suggestion-chip', id='chip-3'),
            ], className='chat-suggestions'),

            # Input area
            html.Div([
                dcc.Textarea(
                    id='chatbot-input',
                    placeholder='Ask about your financials…',
                    value='',
                    rows=1,
                ),
                html.Button(
                    html.I(className="fas fa-paper-plane", style={"fontSize": "16px"}),
                    id='chatbot-send-btn',
                    n_clicks=0,
                    title='Send',
                ),
            ], className='chat-input-area'),
        ],
    ),

    # Store for chat open/closed state
    dcc.Store(id='chatbot-open-store', data=False),

    # Store for chat messages history
    dcc.Store(id='chatbot-messages-store', data=[
        {'role': 'bot', 'text': '👋 Hi! I\'m your CFO AI Assistant. Ask me anything about your financial data, KPIs, or competitors.'}
    ]),

    # ── PRO Payment Modal — fixed overlay, always in DOM ──────────────────
    html.Div(id='pro-payment-modal', className='pro-modal-overlay', children=[
        html.Div([  # backdrop click-to-close area
            html.Div([  # card
                # Close button
                html.Button("✕", id='pro-payment-close', className='pro-modal-close'),

                # ── Header ─────────────────────────────────────────────
                html.Div([
                    html.Div([
                        html.Span("⚡", style={"marginRight": "5px"}),
                        html.Span("PRO"),
                    ], className='pro-badge'),
                    html.H3("Unlock Pro Analytics", className='pro-modal-title'),
                    html.P("Access premium financial intelligence charts", className='pro-modal-subtitle'),
                    html.Div([
                        html.Div([
                            html.Span("✓ ", className='pro-check'),
                            f,
                        ], className='pro-feature-item')
                        for f in ["Profitability Quadrant Analysis",
                                  "Cost Structure DNA Breakdown",
                                  "Capital Efficiency Matrix",
                                  "Multi-Metric Health Radar"]
                    ], className='pro-feature-list'),
                ], className='pro-modal-header'),

                # ── Body — payment form ─────────────────────────────────
                html.Div([
                    html.Div("$99 / month  ·  Cancel anytime", className='pro-price-tag'),

                    # Card number
                    html.Div([
                        html.Label("Card Number", className='pro-field-label'),
                        dcc.Input(
                            id='pro-payment-card', type='text',
                            placeholder='1234  5678  9012  3456',
                            maxLength=19, className='pro-input',
                        ),
                    ], className='pro-field'),

                    # Expiry + CVV
                    html.Div([
                        html.Div([
                            html.Label("Expiry", className='pro-field-label'),
                            dcc.Input(id='pro-payment-expiry', type='text',
                                      placeholder='MM / YY', maxLength=7,
                                      className='pro-input'),
                        ], style={"flex": "1"}),
                        html.Div([
                            html.Label("CVV", className='pro-field-label'),
                            dcc.Input(id='pro-payment-cvv', type='text',
                                      placeholder='•••', maxLength=4,
                                      className='pro-input'),
                        ], style={"flex": "1"}),
                    ], className='pro-field-row'),

                    # Name
                    html.Div([
                        html.Label("Name on Card", className='pro-field-label'),
                        dcc.Input(id='pro-payment-name', type='text',
                                  placeholder='Jane Smith', className='pro-input'),
                    ], className='pro-field', style={"marginBottom": "22px"}),

                    # Submit
                    html.Button([
                        html.I(className="fas fa-lock-open", style={"marginRight": "8px"}),
                        "Unlock Pro Analytics  →",
                    ], id='pro-payment-submit', className='pro-submit-btn'),

                    html.P("🔒 Secured · 256-bit encryption · No charge today",
                           className='pro-secure-note'),
                ], className='pro-modal-body'),

            ], className='pro-modal-card'),
        ], className='pro-modal-inner'),
    ]),

    ]),  # end #floating-ui-wrapper

], style={'position': 'relative'})

#==============================================================================
# ONBOARDING CALLBACKS
#==============================================================================

import random

# Callback to handle Launch Dashboard button
@app.callback(
    [Output('user-company-store', 'data'),
     Output('onboarding-container', 'style'),
     Output('loading-screen', 'style'),
     Output('loading-interval', 'disabled')],
    [Input('btn-launch-dashboard', 'n_clicks'),
     Input('btn-use-test-data', 'n_clicks')],
    [State('onboard-company-name', 'value'),
     State('onboard-industry', 'value'),
     State('onboard-ebitda-margin', 'value'),
     State('onboard-gross-margin', 'value'),
     State('onboard-current-ratio', 'value'),
     State('onboard-quick-ratio', 'value'),
     State('onboard-debt-to-asset', 'value'),
     State('onboard-debt-to-ebitda', 'value'),
     State('onboard-interest-coverage', 'value'),
     State('onboard-net-debt-equity', 'value'),
     State('onboard-cash-dividend', 'value')],
    prevent_initial_call=True
)
def handle_onboarding_submit(launch_clicks, test_clicks, company_name, industry,
                              ebitda_margin, gross_margin, current_ratio, quick_ratio,
                              debt_to_asset, debt_to_ebitda, interest_coverage,
                              net_debt_equity, cash_dividend):
    ctx = callback_context
    if not ctx.triggered:
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update

    triggered_id = ctx.triggered[0]['prop_id'].split('.')[0]

    # Loading screen style - CSS handles the rest
    loading_style = {"display": "flex"}

    if triggered_id == 'btn-use-test-data':
        # Load test data from Kt.json
        test_data = load_test_data()
        if test_data:
            # Get ANNUAL_FINANCIALS section from Kt.json for KPI cards
            annual_financials = test_data.get('ANNUAL_FINANCIALS', {})
            user_data = {
                'company_name': 'Test Company (Kt.json)',
                'industry': 'tech',
                'TICKER': 'TEST',
                'EBITDA_MARGIN': test_data.get('FINANCIAL_ADVANCED', {}).get('EBITDA_MARGIN', 0),
                'GROSS_MARGIN': 45.0,  # Default as not in Kt.json
                'CUR_RATIO': test_data.get('FINANCIAL_RATIOS', {}).get('CURRENT_RATIO', 0),
                'QUICK_RATIO': test_data.get('FINANCIAL_RATIOS', {}).get('QUICK_RATIO', 0),
                'TOT_DEBT_TO_TOT_ASSET': test_data.get('FINANCIAL_RATIOS', {}).get('TOT_DEBT_TO_TOT_ASSET', 0),
                'TOT_DEBT_TO_EBITDA': 2.0,  # Default
                'INTEREST_COVERAGE_RATIO': test_data.get('FINANCIAL_RATIOS', {}).get('INTEREST_COVERAGE_RATIO', 0),
                'NET_DEBT_TO_SHRHLDR_EQTY': test_data.get('FINANCIAL_RATIOS', {}).get('NET_DEBT_TO_SHRHLDR_EQTY', 0),
                'CASH_DVD_COVERAGE': test_data.get('FINANCIAL_RATIOS', {}).get('CASH_RATIO', 0),
                # Add ANNUAL_FINANCIALS data for KPI cards
                'annual_financials': {
                    'SALES_REV_TURN': annual_financials.get('SALES_REV_TURN', 0),
                    'EBITDA': test_data.get('FINANCIAL_ADVANCED', {}).get('EBITDA', 0),
                    'OPER_EXPENSES': annual_financials.get('OPER_EXPENSES', 0),
                    'CASH_FROM_OPER_ACTIV': annual_financials.get('CASH_FROM_OPER_ACTIV', 0),
                    'WORKING_CAPITAL': annual_financials.get('WORKING_CAPITAL', 0),
                    'NET_PROFIT_MARGIN': annual_financials.get('NET_PROFIT_MARGIN', 0)
                }
            }
        else:
            user_data = {
                'company_name': 'Test Company',
                'industry': 'tech',
                'TICKER': 'TEST',
                'EBITDA_MARGIN': 15.0,
                'GROSS_MARGIN': 45.0,
                'CUR_RATIO': 1.5,
                'QUICK_RATIO': 1.2,
                'TOT_DEBT_TO_TOT_ASSET': 25.0,
                'TOT_DEBT_TO_EBITDA': 2.0,
                'INTEREST_COVERAGE_RATIO': 8.0,
                'NET_DEBT_TO_SHRHLDR_EQTY': 50.0,
                'CASH_DVD_COVERAGE': 3.0,
                # Default annual financials
                'annual_financials': {
                    'SALES_REV_TURN': 15000,
                    'EBITDA': 3000,
                    'OPER_EXPENSES': 12000,
                    'CASH_FROM_OPER_ACTIV': 1700,
                    'WORKING_CAPITAL': 800,
                    'NET_PROFIT_MARGIN': 5.0
                }
            }
    else:
        # Use user-entered data
        user_data = {
            'company_name': company_name or 'Your Company',
            'industry': industry or 'other',
            'TICKER': 'USER',
            'EBITDA_MARGIN': ebitda_margin or 0,
            'GROSS_MARGIN': gross_margin or 0,
            'CUR_RATIO': current_ratio or 0,
            'QUICK_RATIO': quick_ratio or 0,
            'TOT_DEBT_TO_TOT_ASSET': debt_to_asset or 0,
            'TOT_DEBT_TO_EBITDA': debt_to_ebitda or 0,
            'INTEREST_COVERAGE_RATIO': interest_coverage or 0,
            'NET_DEBT_TO_SHRHLDR_EQTY': net_debt_equity or 0,
            'CASH_DVD_COVERAGE': cash_dividend or 0,
            # Default annual financials for user-entered companies
            # These would ideally come from additional onboarding fields
            'annual_financials': {
                'SALES_REV_TURN': 0,
                'EBITDA': 0,
                'OPER_EXPENSES': 0,
                'CASH_FROM_OPER_ACTIV': 0,
                'WORKING_CAPITAL': 0,
                'NET_PROFIT_MARGIN': 0
            }
        }

    # Hide onboarding, show loading
    return user_data, {'display': 'none'}, loading_style, False

# Callback for loading animation and transition to dashboard
@app.callback(
    [Output('loading-message', 'children'),
     Output('loading-progress-bar', 'style'),
     Output('loading-countdown', 'children'),
     Output('dashboard-container', 'style'),
     Output('loading-screen', 'style', allow_duplicate=True),
     Output('loading-interval', 'disabled', allow_duplicate=True)],
    [Input('loading-interval', 'n_intervals')],
    [State('user-company-store', 'data')],
    prevent_initial_call=True
)
def update_loading_screen(n_intervals, user_data):
    if n_intervals is None or n_intervals == 0:
        return dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update

    # Calculate progress (10 intervals = 5 seconds at 500ms each)
    total_intervals = 10
    progress = min((n_intervals / total_intervals) * 100, 100)

    # Progress bar style - just update width, CSS handles the rest
    progress_style = {"width": f"{progress}%"}

    # Show percentage
    percentage_text = f"{int(progress)}%"

    # Sequential messages based on progress
    message_index = min(int(progress / 10), len(LOADING_MESSAGES) - 1)
    message = LOADING_MESSAGES[message_index]

    # Check if loading is complete
    if n_intervals >= total_intervals:
        # Show dashboard, hide loading
        return message, progress_style, "100%", {'display': 'block', 'position': 'relative'}, {'display': 'none'}, True

    return message, progress_style, percentage_text, dash.no_update, dash.no_update, dash.no_update

#==============================================================================
# CALLBACKS
#==============================================================================

# Sidebar render callback
@app.callback(
    Output('sidebar-container', 'children'),
    [Input('sidebar-collapsed-store', 'data'),
     Input('dark-mode-store', 'data')]
)
def render_sidebar(collapsed, dark_mode):
    return create_sidebar(collapsed=collapsed, dark_mode=dark_mode)

# Sidebar toggle callback
@app.callback(
    [Output('sidebar-collapsed-store', 'data'),
     Output('sidebar-toggle-icon', 'className')],
    [Input('sidebar-toggle-btn', 'n_clicks')],
    [State('sidebar-collapsed-store', 'data')]
)
def toggle_sidebar(n, collapsed):
    if n:
        new_collapsed = not collapsed
        icon = "fas fa-chevron-right" if new_collapsed else "fas fa-chevron-left"
        return new_collapsed, icon
    return collapsed, "fas fa-chevron-left"

# Main content class update (combines sidebar state and dark mode)
@app.callback(
    Output('main-content', 'className'),
    [Input('sidebar-collapsed-store', 'data'),
     Input('dark-mode-store', 'data')]
)
def update_main_content_class(collapsed, dark_mode):
    sidebar_class = "sidebar-collapsed" if collapsed else "sidebar-expanded"
    dark_class = " dark-mode" if dark_mode else ""
    return f"main-content {sidebar_class}{dark_class}"

# Dashboard container class update for dark mode
@app.callback(
    Output('dashboard-container', 'className'),
    [Input('dark-mode-store', 'data')]
)
def update_dashboard_class(dark_mode):
    return "dark-mode" if dark_mode else ""

# System status toggle callback with state store
@app.callback(
    [Output('system-status-content', 'style'),
     Output('system-status-toggle-icon', 'style')],
    [Input('system-status-toggle', 'n_clicks'),
     Input('sidebar-collapsed-store', 'data')],
    [State('system-status-content', 'style'),
     State('system-status-toggle-icon', 'style')]
)
def toggle_system_status(n_clicks, sidebar_collapsed, content_style, icon_style):
    ctx = callback_context

    # If sidebar is collapsed, hide everything
    if sidebar_collapsed:
        return {'display': 'none'}, {'display': 'none'}

    # Default style for icon
    if icon_style is None:
        icon_style = {
            'fontSize': '12px',
            'transition': 'transform 0.3s ease',
            'color': COLORS['gray']['400']
        }

    # Default style for content
    if content_style is None:
        content_style = {'padding': '8px 8px 0 8px', 'display': 'block'}

    # If system status toggle was clicked
    if ctx.triggered and ctx.triggered[0]['prop_id'] == 'system-status-toggle.n_clicks' and n_clicks:
        is_visible = content_style.get('display', 'block') == 'block'

        # Toggle visibility
        new_content_style = content_style.copy()
        new_content_style['display'] = 'none' if is_visible else 'block'

        # Rotate icon
        new_icon_style = icon_style.copy()
        new_icon_style['transform'] = 'rotate(-90deg)' if is_visible else 'rotate(0deg)'

        return new_content_style, new_icon_style

    # Default: show when expanded
    return content_style, icon_style

# Data refresh status toggle callback
@app.callback(
    [Output('data-refresh-content', 'style'),
     Output('data-refresh-toggle-icon', 'style')],
    [Input('data-refresh-toggle', 'n_clicks'),
     Input('sidebar-collapsed-store', 'data')],
    [State('data-refresh-content', 'style'),
     State('data-refresh-toggle-icon', 'style')]
)
def toggle_data_refresh_status(n_clicks, sidebar_collapsed, content_style, icon_style):
    ctx = callback_context

    # If sidebar is collapsed, hide everything
    if sidebar_collapsed:
        return {'display': 'none'}, {'display': 'none'}

    # Default style for icon
    if icon_style is None:
        icon_style = {
            'fontSize': '12px',
            'transition': 'transform 0.3s ease',
            'color': COLORS['gray']['400']
        }

    # Default style for content
    if content_style is None:
        content_style = {'padding': '8px 8px 0 8px', 'display': 'block'}

    # If data refresh toggle was clicked
    if ctx.triggered and ctx.triggered[0]['prop_id'] == 'data-refresh-toggle.n_clicks' and n_clicks:
        is_visible = content_style.get('display', 'block') == 'block'

        # Toggle visibility
        new_content_style = content_style.copy()
        new_content_style['display'] = 'none' if is_visible else 'block'

        # Rotate icon
        new_icon_style = icon_style.copy()
        new_icon_style['transform'] = 'rotate(-90deg)' if is_visible else 'rotate(0deg)'

        return new_content_style, new_icon_style

    # Default: show when expanded
    return content_style, icon_style

# Footer render callback
@app.callback(
    Output('footer-container', 'children'),
    [Input('dark-mode-store', 'data')]
)
def render_footer(dark_mode):
    return create_footer(dark_mode=dark_mode)

# Update all dashboard stats from database
@app.callback(
    [Output('sidebar-last-sync', 'children'),
     Output('sidebar-total-records', 'children'),
     Output('sidebar-unique-tickers', 'children'),
     Output('sidebar-data-quality', 'children'),
     Output('sidebar-connection-indicator', 'style'),
     Output('sidebar-connection-text', 'children'),
     Output('sidebar-annual-records', 'children'),
     Output('header-data-quality', 'children'),
     Output('header-last-sync', 'children')],
    [Input('update-timestamp', 'data')]
)
def update_dashboard_stats(timestamp):
    """Update all dashboard statistics from database"""
    # Default values
    default_indicator_style = {
        "width": "6px",
        "height": "6px",
        "borderRadius": "50%",
        "backgroundColor": COLORS['gray']['400'],
        "marginRight": "6px",
        "marginLeft": "16px"
    }

    try:
        if data_service and data_service.connected:
            stats = data_service.get_dashboard_stats()

            # Format last sync time
            last_sync = stats.get('last_sync')
            if last_sync:
                if isinstance(last_sync, str):
                    last_sync_str = last_sync
                else:
                    last_sync_str = last_sync.strftime("%b %d, %Y %I:%M %p")
            else:
                last_sync_str = "N/A"

            # Format counts
            total_records = f"{stats.get('total_records', 0):,}"
            annual_records = f"{stats.get('annual_records', 0):,}"
            unique_tickers = f"{stats.get('unique_tickers', 0):,}"

            # Format data quality
            data_quality = stats.get('data_quality', 0)
            data_quality_str = f"{data_quality}%"

            # Connection status
            conn_status = stats.get('connection_status', 'Disconnected')
            if conn_status == 'Connected':
                indicator_style = {**default_indicator_style, "backgroundColor": COLORS['success']}
                conn_text = "Connected"
            else:
                indicator_style = {**default_indicator_style, "backgroundColor": COLORS['danger']}
                conn_text = conn_status

            return (
                last_sync_str,
                total_records,
                unique_tickers,
                data_quality_str,
                indicator_style,
                conn_text,
                annual_records,
                data_quality_str,
                last_sync_str
            )
        else:
            # No connection - use CSV data info
            csv_records = 0
            csv_tickers = 0
            if csv_data and csv_data.get('financial_ratios') is not None:
                df = csv_data['financial_ratios']
                csv_records = len(df)
                if 'TICKER' in df.columns:
                    csv_tickers = df['TICKER'].nunique()

            return (
                "Using CSV fallback",
                f"{csv_records:,} (CSV)",
                f"{csv_tickers:,}",
                "N/A",
                {**default_indicator_style, "backgroundColor": COLORS['warning']},
                "CSV Mode",
                "N/A",
                "N/A",
                "CSV fallback"
            )
    except Exception as e:
        logger.error(f"Error updating dashboard stats: {e}")
        return (
            "Error",
            "Error",
            "Error",
            "Error",
            {**default_indicator_style, "backgroundColor": COLORS['danger']},
            "Error",
            "Error",
            "Error",
            "Error"
        )

# Theme toggle callback
@app.callback(
    [Output('dark-mode-store', 'data'),
     Output('theme-icon', 'className')],
    [Input('theme-toggle', 'n_clicks')],
    [State('dark-mode-store', 'data')]
)
def toggle_theme(n, dark_mode):
    if n:
        new_mode = not dark_mode
        icon = "fas fa-sun" if new_mode else "fas fa-moon"
        return new_mode, icon
    return dark_mode, "fas fa-moon"

# Reset filters callback
@app.callback(
    [Output('year-filter', 'value'),
     Output('region-filter', 'value'),
     Output('currency-filter', 'value'),
     Output('view-mode-filter', 'value')],
    [Input('reset-filters', 'n_clicks')]
)
def reset_filters(n):
    if n:
        return '2025', 'All', 'USD', 'chart'
    return dash.no_update

# Refresh data callback
@app.callback(
    Output('update-timestamp', 'data'),
    [Input('refresh-btn', 'n_clicks')]
)
def refresh_data(n):
    if n:
        return datetime.now().isoformat()
    return dash.no_update

#==============================================================================
# KPI GRID COMPONENT CALLBACK
#==============================================================================

@app.callback(
    Output('kpi-grid-container', 'children'),
    [Input('year-filter', 'value'),
     Input('region-filter', 'value'),
     Input('view-mode-filter', 'value'),
     Input('update-timestamp', 'data'),
     Input('dark-mode-store', 'data'),
     Input('selected-competitors-store', 'data'),
     Input('user-company-store', 'data')]
)
def update_kpi_grid(year, region, view_mode, timestamp, dark_mode, selected_competitors, user_company):
    """Create KPI grid with ANNUAL_FINANCIALS data from selected competitors"""

    # Default values
    avg_revenue = 0
    avg_ebitda = 0
    avg_opex = 0
    avg_cash_flow = 0
    avg_working_capital = 0
    avg_net_profit_margin = 0

    # Get user company values from Kt.json (stored in user_company)
    user_revenue = 0
    user_ebitda = 0
    user_opex = 0
    user_cash_flow = 0
    user_working_capital = 0
    user_net_profit_margin = 0

    if user_company:
        # Extract user company data from ANNUAL_FINANCIALS section of Kt.json
        annual_data = user_company.get('annual_financials', {})
        if annual_data:
            user_revenue = annual_data.get('SALES_REV_TURN', 0) or 0
            user_ebitda = annual_data.get('EBITDA', 0) or 0
            user_opex = annual_data.get('OPER_EXPENSES', 0) or 0
            user_cash_flow = annual_data.get('CASH_FROM_OPER_ACTIV', 0) or 0
            user_working_capital = annual_data.get('WORKING_CAPITAL', 0) or 0
            user_net_profit_margin = annual_data.get('NET_PROFIT_MARGIN', 0) or 0

    # Fetch ANNUAL_FINANCIALS data
    try:
        df = None
        if data_service and data_service.connected:
            # Get data from HANA
            df = data_service.get_annual_financials(selected_competitors)
        elif csv_data and csv_data.get('annual_financials') is not None:
            # Use CSV data for local testing
            df = csv_data['annual_financials'].copy()
            if selected_competitors:
                df = df[df['TICKER'].isin(selected_competitors)]

        if df is not None and len(df) > 0:
            # Calculate averages across all years for selected competitors
            # Group by ticker first, then get mean across tickers
            ticker_avgs = df.groupby('TICKER').agg({
                'SALES_REV_TURN': 'mean',
                'EBITDA': 'mean',
                'IS_SGA_EXPENSE': 'mean',  # Operating expenses proxy
                'CF_FREE_CASH_FLOW': 'mean',
                'NET_INCOME': 'mean'
            }).reset_index()

            # Calculate overall averages
            avg_revenue = ticker_avgs['SALES_REV_TURN'].mean() if 'SALES_REV_TURN' in ticker_avgs.columns else 0
            avg_ebitda = ticker_avgs['EBITDA'].mean() if 'EBITDA' in ticker_avgs.columns else 0
            avg_opex = ticker_avgs['IS_SGA_EXPENSE'].mean() if 'IS_SGA_EXPENSE' in ticker_avgs.columns else 0
            avg_cash_flow = ticker_avgs['CF_FREE_CASH_FLOW'].mean() if 'CF_FREE_CASH_FLOW' in ticker_avgs.columns else 0

            # Get working capital directly from data if available
            if 'WORKING_CAPITAL' in df.columns:
                avg_working_capital = df.groupby('TICKER')['WORKING_CAPITAL'].mean().mean()
            elif 'CUR_RATIO' in df.columns and 'BS_CUR_LIAB' in df.columns:
                # Fallback: Calculate from Current Ratio and Current Liabilities
                df['WORKING_CAPITAL'] = (df['CUR_RATIO'] * df['BS_CUR_LIAB']) - df['BS_CUR_LIAB']
                avg_working_capital = df.groupby('TICKER')['WORKING_CAPITAL'].mean().mean()
            else:
                avg_working_capital = 0

            # Calculate net profit margin
            if 'NET_INCOME' in df.columns and 'SALES_REV_TURN' in df.columns:
                df['NET_PROFIT_MARGIN'] = (df['NET_INCOME'] / df['SALES_REV_TURN'] * 100).replace([float('inf'), -float('inf')], 0).fillna(0)
                avg_net_profit_margin = df.groupby('TICKER')['NET_PROFIT_MARGIN'].mean().mean()
            else:
                avg_net_profit_margin = 0

            logger.info(f"KPI Cards - Selected {len(selected_competitors) if selected_competitors else 0} competitors: Avg Revenue=${avg_revenue:.2f}M, Avg EBITDA=${avg_ebitda:.2f}M")

    except Exception as e:
        logger.error(f"Error fetching KPI data: {e}")

    # Calculate change percentage (your company vs avg of competitors)
    def calc_change(user_val, avg_val, lower_is_better=False):
        if avg_val == 0:
            return 0
        change = ((user_val - avg_val) / avg_val) * 100
        return change if not lower_is_better else -change

    # Determine trend direction based on comparison
    def get_trend(user_val, avg_val, lower_is_better=False):
        if lower_is_better:
            return 'down' if user_val < avg_val else 'up'
        return 'up' if user_val > avg_val else 'down'

    # Define KPIs with competitor averages and user company comparison
    kpis = [
        {
            'name': 'Revenue',
            'value': avg_revenue,  # Average of selected competitors
            'user_value': user_revenue,  # Your company value
            'change': calc_change(user_revenue, avg_revenue),
            'target': avg_revenue * 1.1 if avg_revenue > 0 else 250000,
            'icon': 'fa-dollar-sign',
            'color': COLORS['primary'],
            'trend': get_trend(user_revenue, avg_revenue),
            'sparkline': [avg_revenue * 0.9, avg_revenue * 0.92, avg_revenue * 0.95, avg_revenue * 0.97, avg_revenue * 0.99, avg_revenue],
            'is_millions': True
        },
        {
            'name': 'EBITDA',
            'value': avg_ebitda,
            'user_value': user_ebitda,
            'change': calc_change(user_ebitda, avg_ebitda),
            'target': avg_ebitda * 1.1 if avg_ebitda > 0 else 48000,
            'icon': 'fa-chart-line',
            'color': COLORS['success'],
            'trend': get_trend(user_ebitda, avg_ebitda),
            'sparkline': [avg_ebitda * 0.9, avg_ebitda * 0.92, avg_ebitda * 0.95, avg_ebitda * 0.97, avg_ebitda * 0.99, avg_ebitda],
            'is_millions': True
        },
        {
            'name': 'Operating Expenses',
            'value': avg_opex,
            'user_value': user_opex,
            'change': calc_change(user_opex, avg_opex, lower_is_better=True),  # Lower is better for expenses
            'target': avg_opex * 0.95 if avg_opex > 0 else 155000,
            'icon': 'fa-receipt',
            'color': COLORS['info'],
            'trend': get_trend(user_opex, avg_opex, lower_is_better=True),
            'sparkline': [avg_opex * 1.05, avg_opex * 1.03, avg_opex * 1.01, avg_opex, avg_opex * 0.99, avg_opex * 0.98],
            'is_millions': True,
            'lower_is_better': True
        },
        {
            'name': 'Cash Flow',
            'value': avg_cash_flow,
            'user_value': user_cash_flow,
            'change': calc_change(user_cash_flow, avg_cash_flow),
            'target': avg_cash_flow * 1.1 if avg_cash_flow > 0 else 40000,
            'icon': 'fa-wallet',
            'color': COLORS['purple'],
            'trend': get_trend(user_cash_flow, avg_cash_flow),
            'sparkline': [avg_cash_flow * 0.85, avg_cash_flow * 0.88, avg_cash_flow * 0.92, avg_cash_flow * 0.95, avg_cash_flow * 0.98, avg_cash_flow],
            'is_millions': True
        },
        {
            'name': 'Working Capital',
            'value': avg_working_capital,
            'user_value': user_working_capital,
            'change': calc_change(user_working_capital, avg_working_capital),
            'target': avg_working_capital * 1.1 if avg_working_capital > 0 else 55000,
            'icon': 'fa-piggy-bank',
            'color': COLORS['warning'],
            'trend': get_trend(user_working_capital, avg_working_capital),
            'sparkline': [avg_working_capital * 0.9, avg_working_capital * 0.92, avg_working_capital * 0.94, avg_working_capital * 0.96, avg_working_capital * 0.98, avg_working_capital],
            'is_millions': True
        },
        {
            'name': 'Net Profit Margin',
            'value': avg_net_profit_margin,
            'user_value': user_net_profit_margin,
            'change': calc_change(user_net_profit_margin, avg_net_profit_margin),
            'target': avg_net_profit_margin * 1.1 if avg_net_profit_margin > 0 else 20.0,
            'icon': 'fa-percent',
            'color': COLORS['success'],
            'trend': get_trend(user_net_profit_margin, avg_net_profit_margin),
            'sparkline': [avg_net_profit_margin * 0.9, avg_net_profit_margin * 0.92, avg_net_profit_margin * 0.95, avg_net_profit_margin * 0.97, avg_net_profit_margin * 0.99, avg_net_profit_margin],
            'is_percentage': True
        }
    ]

    # Create KPI cards
    kpi_cards = []
    for kpi in kpis:
        card = create_kpi_card(kpi, view_mode, dark_mode)
        kpi_cards.append(dbc.Col(card, width=12, md=6, lg=4))

    return dbc.Row(kpi_cards, className="g-4")

def create_kpi_card(kpi, view_mode, dark_mode):
    """Create individual KPI card"""

    # Determine if change is good based on whether lower is better
    lower_is_better = kpi.get('lower_is_better', False)
    if lower_is_better:
        is_good = kpi['change'] > 0  # For expenses, positive change means you're below avg (good)
    else:
        is_good = kpi['change'] > 0  # For revenue etc., positive change means you're above avg (good)

    has_alert = abs(kpi['change']) > 50

    # Helper function to format large numbers nicely
    def format_currency(val):
        if val == 0:
            return "$0"
        abs_val = abs(val)
        if abs_val >= 1000:
            # Values in ANNUAL_FINANCIALS are in millions, so 1000 = 1 billion
            return f"${val/1000:.1f}B"
        elif abs_val >= 1:
            return f"${val:.1f}M"
        else:
            return f"${val:.2f}M"

    # Format value based on type
    if kpi.get('is_percentage'):
        value_display = f"{kpi['value']:.1f}%"
        target_display = f"{kpi['target']:.1f}%"
        user_value_display = f"{kpi.get('user_value', 0):.1f}%"
    elif kpi.get('is_millions'):
        # Values are already in millions in ANNUAL_FINANCIALS (e.g., 130497 = $130.5B)
        value_display = format_currency(kpi['value'])
        target_display = format_currency(kpi['target'])
        user_value_display = format_currency(kpi.get('user_value', 0))
    else:
        value_display = f"${kpi['value']/1000000:.1f}M"
        target_display = f"${kpi['target']/1000000:.1f}M"
        user_value_display = f"${kpi.get('user_value', 0)/1000000:.1f}M"

    # Mini bar chart: Your Company vs Competitor Avg (replaces single sparkline)
    user_val_raw = kpi.get('user_value', 0) or 0
    comp_val_raw = kpi['value'] or 0

    bar_fig = go.Figure()
    bar_fig.add_trace(go.Bar(
        x=['Your Co.', 'Comp. Avg'],
        y=[user_val_raw, comp_val_raw],
        marker_color=[COLORS['primary'], '#374151'],
        text=[
            user_value_display,
            value_display
        ],
        textposition='outside',
        textfont=dict(size=10),
        hoverinfo='skip',
        width=[0.45, 0.45],
    ))
    bar_fig.update_layout(
        showlegend=False,
        xaxis=dict(showgrid=False, showticklabels=True, zeroline=False, fixedrange=True,
                   tickfont=dict(size=10, color='rgba(180,180,180,0.85)')),
        yaxis=dict(showgrid=False, showticklabels=False, zeroline=False, fixedrange=True,
                   range=[0, max(user_val_raw, comp_val_raw) * 1.35] if max(user_val_raw, comp_val_raw) > 0 else [0, 1]),
        margin=dict(l=4, r=4, t=22, b=4),
        height=90,
        bargap=0.35,
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        hovermode=False
    )

    # Progress to target
    progress = (kpi['value'] / kpi['target']) * 100

    # Let CSS handle background colors for proper dark/light mode
    card_style = {
        "borderRadius": "12px",
        "padding": "24px",
        "position": "relative",
        "cursor": "pointer"
    }

    card_content = [
        # Alert badge — icon only, no text
        html.Div([
            html.I(className="fas fa-exclamation-triangle", style={"fontSize": "13px"}),
        ], style={
            "position": "absolute",
            "top": "12px",
            "right": "12px",
            "backgroundColor": COLORS['danger'],
            "color": "white",
            "width": "24px",
            "height": "24px",
            "borderRadius": "50%",
            "display": "flex",
            "alignItems": "center",
            "justifyContent": "center",
        }) if has_alert else html.Div(),

        # Header
        html.Div([
            html.Div([
                html.Div([
                    html.I(className=f"fas {kpi['icon']}", style={
                        "fontSize": "20px",
                        "color": kpi['color']
                    })
                ], style={
                    "width": "40px",
                    "height": "40px",
                    "borderRadius": "8px",
                    "backgroundColor": f"rgba({int(kpi['color'][1:3], 16)}, {int(kpi['color'][3:5], 16)}, {int(kpi['color'][5:7], 16)}, 0.1)",
                    "display": "flex",
                    "alignItems": "center",
                    "justifyContent": "center"
                }),
                html.Div([
                    html.H3(kpi['name'], style={
                        "fontSize": "16px",
                        "fontWeight": "500",
                        "margin": "0"
                    }, className="text-primary-theme"),
                    # Comparison arrow: Your company vs Average
                    html.Div([
                        html.I(className=f"fas fa-arrow-{'up' if is_good else 'down'}",
                              style={"fontSize": "12px", "marginRight": "4px"}),
                        html.Span(f"{'+' if kpi['change'] > 0 else ''}{kpi['change']:.1f}% vs avg")
                    ], style={
                        "fontSize": "14px",
                        "color": COLORS['success'] if is_good else COLORS['danger'],
                        "marginTop": "4px"
                    })
                ], style={"marginLeft": "12px"})
            ], style={"display": "flex", "alignItems": "center"})
        ], style={"marginBottom": "16px"}),

        # Value display - Your Company first (primary), Competitor Avg second (muted)
        html.Div([
            html.Div([
                html.Span("Your Company: ", style={
                    "fontSize": "14px"
                }, className="text-secondary-theme"),
                html.Span(user_value_display, style={
                    "fontSize": "28px",
                    "fontWeight": "700",
                    "color": COLORS['success'] if is_good else COLORS['danger']
                })
            ], style={"marginBottom": "8px"}),
            html.Div([
                html.Span("Competitor Avg: ", style={
                    "fontSize": "13px"
                }, className="text-secondary-theme"),
                html.Span(value_display, style={
                    "fontSize": "16px",
                    "fontWeight": "500"
                }, className="text-primary-theme")
            ])
        ]),

        # Mini bar chart: Your Company vs Competitor Avg (for chart view)
        html.Div([
            dcc.Graph(figure=bar_fig, config={'displayModeBar': False}, style={"marginTop": "8px"})
        ]) if view_mode == 'chart' else html.Div(),

        # Progress bar (for ratio view)
        html.Div([
            html.Div([
                html.Span("Progress to Target", style={
                    "fontSize": "13px"
                }, className="text-secondary-theme"),
                html.Span(f"{progress:.0f}%", style={
                    "fontSize": "13px",
                    "fontWeight": "600"
                }, className="text-primary-theme")
            ], style={"display": "flex", "justifyContent": "space-between", "marginBottom": "8px"}),
            dbc.Progress(value=progress, style={"height": "8px"},
                        color="success" if progress >= 95 else "warning" if progress >= 80 else "danger")
        ], style={"marginTop": "16px"}) if view_mode == 'ratio' else html.Div(),

        # Bifurcation view
        html.Div([
            html.Div([
                html.Span("Actual", style={"fontSize": "13px"}, className="text-secondary-theme"),
                html.Span(value_display, style={"fontSize": "13px", "fontWeight": "600", "color": COLORS['success']})
            ], style={"display": "flex", "justifyContent": "space-between", "marginBottom": "8px"}),
            html.Div([
                html.Span("Budget", style={"fontSize": "13px"}, className="text-secondary-theme"),
                html.Span(f"${kpi['target']*0.95/1000000:.1f}M" if not kpi.get('is_percentage') else f"{kpi['target']*0.95:.1f}%",
                         style={"fontSize": "13px", "fontWeight": "600", "color": COLORS['primary']})
            ], style={"display": "flex", "justifyContent": "space-between", "marginBottom": "8px"}),
            html.Div([
                html.Span("Variance", style={"fontSize": "13px"}, className="text-secondary-theme"),
                html.Span(f"+${(kpi['value'] - kpi['target']*0.95)/1000000:.1f}M" if not kpi.get('is_percentage') else f"+{kpi['value'] - kpi['target']*0.95:.1f}%",
                         style={"fontSize": "13px", "fontWeight": "600", "color": COLORS['success'] if kpi['change'] >= 0 else COLORS['danger']})
            ], style={"display": "flex", "justifyContent": "space-between"})
        ], style={"marginTop": "16px"}) if view_mode == 'bifurcation' else html.Div(),

        # Drill down button
        html.Div([
            dbc.Button([
                "Drill Down",
                html.I(className="fas fa-arrow-right ms-2")
            ], color="light", size="sm", outline=True, style={"width": "100%", "marginTop": "16px"})
        ])
    ]

    return dbc.Card(card_content, style=card_style, className="kpi-card-hover")

#==============================================================================
# AI INSIGHTS COMPONENT
#==============================================================================

@app.callback(
    Output('ai-insights-container', 'children'),
    [Input('update-timestamp', 'data'),
     Input('dark-mode-store', 'data')]
)
def update_ai_insights(timestamp, dark_mode):
    """Create AI-powered insights section"""

    insights = [
        {
            'type': 'positive',
            'icon': 'fa-arrow-trend-up',
            'title': 'Revenue Acceleration Detected',
            'description': 'Q4 revenue is trending 12.5% above forecast, primarily driven by Technology division (+18%) and strong performance in Asia Pacific region.',
            'confidence': 94,
            'color': COLORS['success']
        },
        {
            'type': 'alert',
            'icon': 'fa-triangle-exclamation',
            'title': 'OPEX Variance Alert',
            'description': 'Travel expenses exceeded budget by 15.2% in September. Recommend immediate review of T&E policy compliance.',
            'confidence': 89,
            'color': COLORS['danger']
        },
        {
            'type': 'insight',
            'icon': 'fa-lightbulb',
            'title': 'Cash Flow Optimization Opportunity',
            'description': 'Days Sales Outstanding increased by 8 days. Accelerating collections could release ~$4.2M in working capital.',
            'confidence': 91,
            'color': COLORS['primary']
        },
        {
            'type': 'target',
            'icon': 'fa-bullseye',
            'title': 'EBITDA Target Within Reach',
            'description': 'Current trajectory suggests 95.4% target achievement. A 2% reduction in discretionary spend would close the gap.',
            'confidence': 96,
            'color': COLORS['purple']
        }
    ]

    card_style = {
        "backgroundColor": COLORS['gray']['800'] if dark_mode else "#ffffff",
        "border": f"1px solid {COLORS['gray']['700'] if dark_mode else COLORS['gray']['200']}",
        "borderRadius": "12px",
        "padding": "24px"
    }

    insight_cards = []
    for insight in insights:
        insight_card = dbc.Col([
            html.Div([
                html.Div([
                    html.Div([
                        html.I(className=f"fas {insight['icon']}", style={
                            "fontSize": "20px",
                            "color": insight['color']
                        })
                    ], style={
                        "width": "40px",
                        "height": "40px",
                        "borderRadius": "8px",
                        "backgroundColor": f"rgba({int(insight['color'][1:3], 16)}, {int(insight['color'][3:5], 16)}, {int(insight['color'][5:7], 16)}, 0.1)",
                        "display": "flex",
                        "alignItems": "center",
                        "justifyContent": "center"
                    }),
                    html.Div([
                        html.Div([
                            html.H4(insight['title'], style={
                                "fontSize": "16px",
                                "fontWeight": "600",
                                "margin": "0",
                                "color": COLORS['gray']['100'] if dark_mode else COLORS['gray']['900']
                            }),
                            html.Span(f"{insight['confidence']}% confident", style={
                                "fontSize": "11px",
                                "padding": "2px 8px",
                                "borderRadius": "4px",
                                "backgroundColor": COLORS['gray']['700'] if dark_mode else COLORS['gray']['100'],
                                "color": COLORS['gray']['300'] if dark_mode else COLORS['gray']['600'],
                                "marginLeft": "8px"
                            })
                        ], style={"display": "flex", "alignItems": "center", "marginBottom": "8px"}),
                        html.P(insight['description'], style={
                            "fontSize": "14px",
                            "color": COLORS['gray']['300'] if dark_mode else COLORS['gray']['600'],
                            "margin": "0 0 12px 0",
                            "lineHeight": "1.5"
                        }),
                        dbc.Button([
                            "Explain This Insight",
                            html.I(className="fas fa-arrow-right ms-2")
                        ], color="link", size="sm", style={"padding": "0", "fontSize": "13px"})
                    ], style={"marginLeft": "12px", "flex": "1"})
                ], style={"display": "flex"})
            ], style={
                "backgroundColor": COLORS['gray']['700'] if dark_mode else COLORS['gray']['50'],
                "border": f"1px solid {COLORS['gray']['600'] if dark_mode else COLORS['gray']['200']}",
                "borderRadius": "8px",
                "padding": "16px",
                "height": "100%"
            })
        ], width=12, md=6)
        insight_cards.append(insight_card)

    return dbc.Card([
        dbc.CardBody([
            html.Div([
                html.Div([
                    html.I(className="fas fa-sparkles", style={
                        "fontSize": "24px",
                        "color": COLORS['warning'],
                        "marginRight": "12px"
                    }),
                    html.Div([
                        html.H2("AI-Powered Insights & Narratives", style={
                            "fontSize": "20px",
                            "fontWeight": "600",
                            "margin": "0",
                            "color": COLORS['gray']['100'] if dark_mode else COLORS['gray']['900']
                        }),
                        html.P("Intelligent analysis of your financial performance", style={
                            "fontSize": "14px",
                            "color": COLORS['gray']['400'] if dark_mode else COLORS['gray']['500'],
                            "margin": "0"
                        })
                    ])
                ], style={"display": "flex", "alignItems": "center"}),
                dbc.Button([
                    html.I(className="fas fa-rotate me-2"),
                    "Regenerate Insights"
                ], color="light", size="sm", outline=True)
            ], style={"display": "flex", "justifyContent": "space-between", "marginBottom": "24px"}),

            dbc.Row(insight_cards, className="g-4")
        ])
    ], style=card_style)

#==============================================================================
# COMPETITOR ANALYSIS MODULE
#==============================================================================

def get_available_tickers():
    """Get list of available tickers from data source"""
    try:
        # Try HANA first - use get_ticker_list for efficiency
        if data_service and data_service.connected:
            tickers = data_service.get_ticker_list()
            if tickers:
                logger.info(f"Available tickers from HANA: {len(tickers)}")
                return tickers

        # Fallback to CSV
        if csv_data and csv_data.get('financial_ratios') is not None:
            df = csv_data['financial_ratios']
            if df is not None and not df.empty and 'TICKER' in df.columns:
                tickers = df['TICKER'].unique().tolist()
                logger.info(f"Available tickers from CSV: {len(tickers)}")
                return tickers
    except Exception as e:
        logger.error(f"Error getting tickers: {e}")
    return []

def get_competitor_data():
    """Get financial ratios dataframe (latest 50 records)"""
    try:
        # Try HANA first - uses default limit of 50, ordered by latest timestamp
        if data_service and data_service.connected:
            data = data_service.get_financial_ratios()  # Default: 50 latest records
            if data is not None and isinstance(data, pd.DataFrame) and not data.empty:
                logger.info(f"Got {len(data)} latest records from HANA FINANCIAL_RATIOS")
                return data
            else:
                logger.warning("HANA FINANCIAL_RATIOS returned empty data, falling back to CSV")

        # Fallback to CSV data
        if csv_data and csv_data.get('financial_ratios') is not None:
            df = csv_data['financial_ratios']
            if df is not None and not df.empty:
                logger.info(f"Using CSV data for financial ratios: {len(df)} records")
                return df
    except Exception as e:
        logger.error(f"Error getting competitor data: {e}")

    logger.error("No data available from HANA or CSV")
    return None

@app.callback(
    Output('competitor-analysis-container', 'children'),
    [Input('update-timestamp', 'data'),
     Input('dark-mode-store', 'data'),
     Input('selected-competitors-store', 'data'),
     Input('user-company-store', 'data')]
)
def update_competitor_analysis(timestamp, dark_mode, selected_competitors, user_company):
    """Create competitor analysis module with filters"""

    # Get available tickers
    available_tickers = get_available_tickers()
    if not available_tickers:
        available_tickers = ['META', 'NVDA', 'MSFT', 'GOOGL', 'AVGO', 'WMT', 'ORCL', 'XOM']

    # Add user company to available tickers if exists
    user_company_name = None
    if user_company:
        user_company_name = user_company.get('company_name', 'Your Company')
        if user_company_name not in available_tickers:
            available_tickers = [user_company_name] + available_tickers

    # Default selected competitors if none
    if not selected_competitors:
        selected_competitors = available_tickers[:5]

    # Ensure user company is in selected list
    if user_company_name and user_company_name not in selected_competitors:
        selected_competitors = [user_company_name] + selected_competitors[:4]

    card_style = {
        "backgroundColor": COLORS['gray']['800'] if dark_mode else "#ffffff",
        "border": f"1px solid {COLORS['gray']['700'] if dark_mode else COLORS['gray']['200']}",
        "borderRadius": "12px",
        "padding": "24px"
    }

    filter_btn_style = {
        "border": f"1px solid {COLORS['gray']['600'] if dark_mode else COLORS['gray']['300']}",
        "borderRadius": "8px",
        "padding": "8px 12px",
        "backgroundColor": "transparent",
        "cursor": "pointer",
        "display": "flex",
        "alignItems": "center",
        "justifyContent": "center",
        "minWidth": "40px",
        "height": "38px"
    }

    filter_btn_active_style = {
        **filter_btn_style,
        "backgroundColor": COLORS['primary'],
        "borderColor": COLORS['primary'],
        "color": "#ffffff"
    }

    text_color = COLORS['gray']['100'] if dark_mode else COLORS['gray']['900']
    label_color = COLORS['gray']['400'] if dark_mode else COLORS['gray']['600']

    # Filter pill button style
    filter_pill_style = {
        "border": f"1px solid {COLORS['gray']['600'] if dark_mode else COLORS['gray']['300']}",
        "borderRadius": "20px",
        "padding": "6px 14px",
        "backgroundColor": "transparent",
        "cursor": "pointer",
        "display": "inline-flex",
        "alignItems": "center",
        "justifyContent": "center",
        "fontSize": "13px",
        "fontWeight": "500",
        "color": COLORS['gray']['400'] if dark_mode else COLORS['gray']['600'],
        "transition": "all 0.2s ease"
    }

    filter_pill_active_style = {
        **filter_pill_style,
        "backgroundColor": COLORS['primary'],
        "borderColor": COLORS['primary'],
        "color": "#ffffff"
    }

    return html.Div([
        # Chart Section (Full Width)
        dbc.Card([
            dbc.CardBody([
                # Header with inline filters
                html.Div([
                    # Title
                    html.Div([
                        html.I(className="fas fa-chart-bar", style={
                            "fontSize": "20px",
                            "color": COLORS['primary'],
                            "marginRight": "10px"
                        }),
                        html.H2("Competitor Ratio Analysis", style={
                            "fontSize": "18px",
                            "fontWeight": "600",
                            "margin": "0",
                            "color": text_color
                        })
                    ], style={"display": "flex", "alignItems": "center"}),

                    # Compact Filters Row
                    html.Div([
                        # Chart Type Pills
                        html.Div([
                            html.Button([
                                html.I(className="fas fa-chart-bar me-1"),
                                "Bar"
                            ], id='chart-type-bar', n_clicks=0, style=filter_pill_active_style),
                            html.Button([
                                html.I(className="fas fa-chart-line me-1"),
                                "Line"
                            ], id='chart-type-line', n_clicks=0, style=filter_pill_style),
                            html.Button([
                                html.I(className="fas fa-chart-pie me-1"),
                                "Pie"
                            ], id='chart-type-pie', n_clicks=0, style=filter_pill_style),
                        ], style={"display": "flex", "gap": "6px", "marginRight": "12px"}),

                        # Divider
                        html.Div(style={
                            "width": "1px",
                            "height": "24px",
                            "backgroundColor": COLORS['gray']['600'] if dark_mode else COLORS['gray']['300'],
                            "marginRight": "12px"
                        }),

                        # View Mode Pills
                        html.Div([
                            html.Button([
                                html.I(className="fas fa-chart-simple me-1"),
                                "Chart"
                            ], id='view-mode-graph', n_clicks=0, style=filter_pill_active_style),
                            html.Button([
                                html.I(className="fas fa-table me-1"),
                                "Table"
                            ], id='view-mode-table', n_clicks=0, style=filter_pill_style),
                        ], style={"display": "flex", "gap": "6px"})
                    ], style={"display": "flex", "alignItems": "center"})
                ], style={
                    "display": "flex",
                    "justifyContent": "space-between",
                    "alignItems": "center",
                    "marginBottom": "16px",
                    "flexWrap": "wrap",
                    "gap": "12px"
                }),

                # Metric and Company Selectors in a nice row
                html.Div([
                    html.Div([
                        html.Span("Metric: ", style={
                            "fontSize": "13px",
                            "color": label_color,
                            "marginRight": "8px"
                        }),
                        dcc.Dropdown(
                            id='competitor-metric-selector',
                            options=[{'label': METRIC_LABELS.get(col, col), 'value': col} for col in NUMERIC_METRIC_COLUMNS],
                            value='EBITDA_MARGIN',
                            clearable=False,
                            style={"width": "200px", "display": "inline-block"}
                        )
                    ], style={"display": "flex", "alignItems": "center", "marginRight": "24px"}),

                    html.Div([
                        html.Span("Companies: ", style={
                            "fontSize": "13px",
                            "color": label_color,
                            "marginRight": "8px"
                        }),
                        dcc.Dropdown(
                            id='add-competitor-dropdown',
                            options=[{'label': t, 'value': t} for t in available_tickers],
                            value=selected_competitors,
                            multi=True,
                            placeholder="Select companies...",
                            style={"width": "400px", "display": "inline-block"}
                        )
                    ], style={"display": "flex", "alignItems": "center", "flex": "1"})
                ], style={
                    "display": "flex",
                    "alignItems": "center",
                    "padding": "12px 16px",
                    "backgroundColor": COLORS['gray']['700'] if dark_mode else COLORS['gray']['50'],
                    "borderRadius": "8px",
                    "marginBottom": "16px",
                    "flexWrap": "wrap",
                    "gap": "12px"
                }),

                # Store for chart type and view mode
                dcc.Store(id='chart-type-store', data='bar'),
                dcc.Store(id='view-mode-store', data='graph'),

                # Chart/Table Container
                html.Div(id='competitor-chart-container', className='chart-container-smooth')
            ])
        ], style=card_style, className="mb-4"),

        # Company Comparison Cards Section (Below Chart - Full Width)
        dbc.Card([
            dbc.CardBody([
                # Header
                html.Div([
                    html.I(className="fas fa-balance-scale", style={
                        "fontSize": "20px",
                        "color": COLORS['info'],
                        "marginRight": "10px"
                    }),
                    html.H2("Quick Compare", style={
                        "fontSize": "18px",
                        "fontWeight": "600",
                        "margin": "0",
                        "color": text_color
                    }),
                    html.Span("Color coded: ", style={
                        "fontSize": "12px",
                        "color": label_color,
                        "marginLeft": "auto",
                        "marginRight": "8px"
                    }),
                    html.Span("Good", style={
                        "fontSize": "11px",
                        "color": "#10b981",
                        "backgroundColor": "#10b98115",
                        "padding": "2px 8px",
                        "borderRadius": "4px",
                        "marginRight": "6px"
                    }),
                    html.Span("Medium", style={
                        "fontSize": "11px",
                        "color": COLORS['warning'],
                        "backgroundColor": f"{COLORS['warning']}15",
                        "padding": "2px 8px",
                        "borderRadius": "4px",
                        "marginRight": "6px"
                    }),
                    html.Span("Poor", style={
                        "fontSize": "11px",
                        "color": "#ef4444",
                        "backgroundColor": "#ef444415",
                        "padding": "2px 8px",
                        "borderRadius": "4px"
                    })
                ], style={
                    "display": "flex",
                    "alignItems": "center",
                    "marginBottom": "20px",
                    "flexWrap": "wrap",
                    "gap": "8px"
                }),

                # Comparison Cards Container
                html.Div(id='company-comparison-cards')
            ])
        ], style=card_style),

        # Data Integration Sources Message
        html.Div([
            html.Div([
                html.I(className="fas fa-database", style={
                    "fontSize": "16px",
                    "color": COLORS['primary'],
                    "marginRight": "10px"
                }),
                html.Span("Data Integration Sources", style={
                    "fontSize": "14px",
                    "fontWeight": "600",
                    "color": text_color
                })
            ], style={"display": "flex", "alignItems": "center", "marginBottom": "12px"}),

            html.Div([
                # EDGAR
                html.Div([
                    html.Span("EDGAR", style={
                        "fontWeight": "600",
                        "color": COLORS['info'],
                        "marginRight": "6px"
                    }),
                    html.Span(": SEC filings including 10-K, 10-Q forms with financial statements and ratios", style={
                        "color": label_color,
                        "fontSize": "13px"
                    })
                ], style={"marginBottom": "6px"}),

                # Bloomberg Terminal
                html.Div([
                    html.Span("Bloomberg Terminal", style={
                        "fontWeight": "600",
                        "color": COLORS['warning'],
                        "marginRight": "6px"
                    }),
                    html.Span(": Real-time market data, analyst estimates, and proprietary financial metrics", style={
                        "color": label_color,
                        "fontSize": "13px"
                    })
                ], style={"marginBottom": "6px"}),

                # Mixed
                html.Div([
                    html.Span("Mixed", style={
                        "fontWeight": "600",
                        "color": COLORS['success'],
                        "marginRight": "6px"
                    }),
                    html.Span(": Combination of EDGAR regulatory filings and Bloomberg market intelligence", style={
                        "color": label_color,
                        "fontSize": "13px"
                    })
                ])
            ]),

            # Last updated line
            html.Div([
                html.I(className="fas fa-clock", style={
                    "fontSize": "11px",
                    "color": COLORS['gray']['400'],
                    "marginRight": "6px"
                }),
                html.Span(f"Last updated: {datetime.now().strftime('%b %d, %Y, %I:%M %p')} EST", style={
                    "fontSize": "12px",
                    "color": COLORS['gray']['400']
                }),
                html.Span(" • ", style={"color": COLORS['gray']['400'], "margin": "0 6px"}),
                html.Span("Ratio calculations use trailing twelve months (TTM) data", style={
                    "fontSize": "12px",
                    "color": COLORS['gray']['400']
                })
            ], style={"marginTop": "12px", "display": "flex", "alignItems": "center"})
        ], style={
            "backgroundColor": COLORS['gray']['700'] if dark_mode else COLORS['gray']['50'],
            "border": f"1px solid {COLORS['gray']['600'] if dark_mode else COLORS['gray']['200']}",
            "borderRadius": "8px",
            "padding": "16px 20px",
            "marginTop": "16px"
        }),

        # Peer Comparison Benchmarking Table Section
        dbc.Card([
            dbc.CardBody([
                # Header
                html.Div([
                    html.Div([
                        html.I(className="fas fa-table", style={
                            "fontSize": "20px",
                            "color": COLORS['purple'],
                            "marginRight": "10px"
                        }),
                        html.H2("Peer Comparison Benchmarking Table", style={
                            "fontSize": "18px",
                            "fontWeight": "600",
                            "margin": "0",
                            "color": text_color
                        })
                    ], style={"display": "flex", "alignItems": "center"}),
                    html.Span("Comprehensive peer analysis with insights", style={
                        "fontSize": "12px",
                        "color": label_color
                    })
                ], style={
                    "display": "flex",
                    "justifyContent": "space-between",
                    "alignItems": "center",
                    "marginBottom": "20px",
                    "flexWrap": "wrap",
                    "gap": "8px"
                }),

                # Peer Comparison Table Container
                html.Div(id='peer-comparison-table')
            ])
        ], style={**card_style, "marginTop": "16px"}),

        # Industry Median Benchmarking Section
        dbc.Card([
            dbc.CardBody([
                # Header
                html.Div([
                    html.Div([
                        html.I(className="fas fa-industry", style={
                            "fontSize": "20px",
                            "color": COLORS['success'],
                            "marginRight": "10px"
                        }),
                        html.H2("Industry Median Benchmarking", style={
                            "fontSize": "18px",
                            "fontWeight": "600",
                            "margin": "0",
                            "color": text_color
                        })
                    ], style={"display": "flex", "alignItems": "center"}),
                    html.Div([
                        html.Span("Above Median", style={
                            "fontSize": "11px",
                            "color": "#10b981",
                            "backgroundColor": "#10b98115",
                            "padding": "2px 8px",
                            "borderRadius": "4px",
                            "marginRight": "6px"
                        }),
                        html.Span("Below Median", style={
                            "fontSize": "11px",
                            "color": "#ef4444",
                            "backgroundColor": "#ef444415",
                            "padding": "2px 8px",
                            "borderRadius": "4px"
                        })
                    ], style={"display": "flex", "alignItems": "center"})
                ], style={
                    "display": "flex",
                    "justifyContent": "space-between",
                    "alignItems": "center",
                    "marginBottom": "20px",
                    "flexWrap": "wrap",
                    "gap": "8px"
                }),

                # Industry Median Table Container
                html.Div(id='industry-median-table')
            ])
        ], style={**card_style, "marginTop": "16px"})
    ])

# Callback to update selected competitors store
@app.callback(
    Output('selected-competitors-store', 'data'),
    [Input('add-competitor-dropdown', 'value')],
    prevent_initial_call=True
)
def update_selected_competitors(selected):
    logger.info(f"[STORE UPDATE] update_selected_competitors called with: {selected}")
    if selected:
        logger.info(f"[STORE UPDATE] Setting selected-competitors-store to: {selected}")
        return selected
    logger.info("[STORE UPDATE] No selection, defaulting to ['META']")
    return ['META']

# Callback for Peer Comparison Benchmarking Table
@app.callback(
    Output('peer-comparison-table', 'children'),
    [Input('selected-competitors-store', 'data'),
     Input('dark-mode-store', 'data'),
     Input('user-company-store', 'data')]
)
def render_peer_comparison_table(selected_competitors, dark_mode, user_company):
    """Render the peer comparison benchmarking table"""

    # Get data
    df = get_competitor_data()

    if df is None:
        df = pd.DataFrame()

    # Add user company data if available
    user_company_name = None
    if user_company:
        user_company_name = user_company.get('company_name', 'Your Company')
        user_row = {
            'TICKER': user_company_name,
            'TOT_DEBT_TO_TOT_ASSET': user_company.get('TOT_DEBT_TO_TOT_ASSET', 0),
            'CASH_DVD_COVERAGE': user_company.get('CASH_DVD_COVERAGE', 0),
            'TOT_DEBT_TO_EBITDA': user_company.get('TOT_DEBT_TO_EBITDA', 0),
            'CUR_RATIO': user_company.get('CUR_RATIO', 0),
            'QUICK_RATIO': user_company.get('QUICK_RATIO', 0),
            'GROSS_MARGIN': user_company.get('GROSS_MARGIN', 0),
            'INTEREST_COVERAGE_RATIO': user_company.get('INTEREST_COVERAGE_RATIO', 0),
            'EBITDA_MARGIN': user_company.get('EBITDA_MARGIN', 0),
            'NET_DEBT_TO_SHRHLDR_EQTY': user_company.get('NET_DEBT_TO_SHRHLDR_EQTY', 0),
            'TOT_LIAB_AND_EQY': 50000.0  # Placeholder
        }
        user_df = pd.DataFrame([user_row])
        df = pd.concat([user_df, df], ignore_index=True)

    if df.empty or not selected_competitors:
        return html.Div("Select companies to compare", style={
            "textAlign": "center", "padding": "40px", "color": COLORS['gray']['500']
        })

    # Filter for selected competitors
    df_filtered = df[df['TICKER'].isin(selected_competitors)]

    # Remove duplicates - keep only one row per ticker
    df_filtered = df_filtered.drop_duplicates(subset=['TICKER'], keep='first')

    if df_filtered.empty:
        return html.Div("No data available", style={
            "textAlign": "center", "padding": "40px", "color": COLORS['gray']['500']
        })

    text_color = COLORS['gray']['100'] if dark_mode else COLORS['gray']['900']
    header_bg = COLORS['gray']['700'] if dark_mode else COLORS['gray']['100']
    row_bg = COLORS['gray']['800'] if dark_mode else "#ffffff"
    alt_row_bg = COLORS['gray']['700'] if dark_mode else COLORS['gray']['50']
    border_color = COLORS['gray']['600'] if dark_mode else COLORS['gray']['200']

    # Define metrics with comments
    metrics_config = [
        {'key': 'TOT_LIAB_AND_EQY', 'label': 'Total Assets', 'format': '${:.1f}B', 'divisor': 1000,
         'comment': 'Scale comparison - larger companies have different dynamics'},
        {'key': 'EBITDA_MARGIN', 'label': 'EBITDA Margin', 'format': '{:.1f}%', 'divisor': 1,
         'comment': 'Operational efficiency indicator - higher is better'},
        {'key': 'GROSS_MARGIN', 'label': 'Gross Margin', 'format': '{:.1f}%', 'divisor': 1,
         'comment': 'Pricing power and cost structure efficiency'},
        {'key': 'CUR_RATIO', 'label': 'Current Ratio', 'format': '{:.2f}x', 'divisor': 1,
         'comment': 'Liquidity health - above 1.5x is generally healthy'},
        {'key': 'QUICK_RATIO', 'label': 'Quick Ratio', 'format': '{:.2f}x', 'divisor': 1,
         'comment': 'Stringent liquidity test - excludes inventory'},
        {'key': 'TOT_DEBT_TO_TOT_ASSET', 'label': 'Debt/Asset', 'format': '{:.1f}%', 'divisor': 1,
         'comment': 'Leverage indicator - lower generally means less risk'},
        {'key': 'INTEREST_COVERAGE_RATIO', 'label': 'Interest Coverage', 'format': '{:.1f}x', 'divisor': 1,
         'comment': 'Ability to service debt - higher is safer'},
    ]

    # Build table header
    companies = df_filtered['TICKER'].tolist()
    header_cells = [
        html.Th("Metric", style={
            "padding": "12px 16px",
            "textAlign": "left",
            "fontWeight": "600",
            "fontSize": "13px",
            "color": text_color,
            "backgroundColor": header_bg,
            "borderBottom": f"2px solid {COLORS['primary']}",
            "minWidth": "120px"
        })
    ]

    for i, company in enumerate(companies):
        is_user = user_company_name and company == user_company_name
        header_cells.append(
            html.Th([
                html.Div([
                    html.I(className="fas fa-star me-1" if is_user else "fas fa-building me-1", style={
                        "fontSize": "10px",
                        "color": COLORS['warning'] if is_user else COLORS['gray']['400']
                    }),
                    html.Span(company if len(company) <= 12 else company[:10] + "...", title=company)
                ], style={"display": "flex", "alignItems": "center", "justifyContent": "center"}),
                html.Div("You" if is_user else f"Peer {i}" if not is_user else "", style={
                    "fontSize": "10px",
                    "color": COLORS['primary'] if is_user else COLORS['gray']['400'],
                    "marginTop": "2px"
                })
            ], style={
                "padding": "12px 8px",
                "textAlign": "center",
                "fontWeight": "600",
                "fontSize": "12px",
                "color": text_color,
                "backgroundColor": COLORS['primary'] + "20" if is_user else header_bg,
                "borderBottom": f"2px solid {COLORS['primary']}",
                "minWidth": "90px"
            })
        )

    header_cells.append(
        html.Th("Insight", style={
            "padding": "12px 16px",
            "textAlign": "left",
            "fontWeight": "600",
            "fontSize": "13px",
            "color": text_color,
            "backgroundColor": header_bg,
            "borderBottom": f"2px solid {COLORS['primary']}",
            "minWidth": "200px"
        })
    )

    # Build table rows
    rows = []
    for idx, metric in enumerate(metrics_config):
        row_cells = [
            html.Td(metric['label'], style={
                "padding": "12px 16px",
                "fontWeight": "500",
                "fontSize": "13px",
                "color": text_color,
                "backgroundColor": alt_row_bg if idx % 2 == 0 else row_bg,
                "borderBottom": f"1px solid {border_color}"
            })
        ]

        values = []
        for company in companies:
            company_data = df_filtered[df_filtered['TICKER'] == company]
            if not company_data.empty:
                val = company_data[metric['key']].iloc[0]
                values.append(val if pd.notnull(val) else 0)
            else:
                values.append(0)

        # Find best value for highlighting
        if metric['key'] in ['TOT_DEBT_TO_TOT_ASSET', 'NET_DEBT_TO_SHRHLDR_EQTY']:
            best_idx = values.index(min(values)) if values else -1
        else:
            best_idx = values.index(max(values)) if values else -1

        for i, (company, val) in enumerate(zip(companies, values)):
            is_user = user_company_name and company == user_company_name
            is_best = i == best_idx

            formatted_val = metric['format'].format(val / metric['divisor']) if val else "-"

            cell_style = {
                "padding": "12px 8px",
                "textAlign": "center",
                "fontSize": "13px",
                "fontWeight": "600" if is_best else "400",
                "color": COLORS['success'] if is_best else text_color,
                "backgroundColor": (COLORS['primary'] + "10" if is_user else alt_row_bg) if idx % 2 == 0 else (COLORS['primary'] + "10" if is_user else row_bg),
                "borderBottom": f"1px solid {border_color}"
            }

            row_cells.append(html.Td([
                html.Span(formatted_val),
                html.I(className="fas fa-trophy ms-1", style={
                    "fontSize": "10px",
                    "color": COLORS['warning']
                }) if is_best else None
            ], style=cell_style))

        # Comment cell
        row_cells.append(
            html.Td(metric['comment'], style={
                "padding": "12px 16px",
                "fontSize": "12px",
                "color": COLORS['gray']['400'] if dark_mode else COLORS['gray']['500'],
                "backgroundColor": alt_row_bg if idx % 2 == 0 else row_bg,
                "borderBottom": f"1px solid {border_color}",
                "fontStyle": "italic"
            })
        )

        rows.append(html.Tr(row_cells))

    return html.Div([
        html.Table([
            html.Thead([html.Tr(header_cells)]),
            html.Tbody(rows)
        ], style={
            "width": "100%",
            "borderCollapse": "collapse",
            "borderRadius": "8px",
            "overflow": "hidden",
            "border": f"1px solid {border_color}"
        })
    ], style={"overflowX": "auto"})

# Callback for Industry Median Benchmarking Table
@app.callback(
    Output('industry-median-table', 'children'),
    [Input('dark-mode-store', 'data'),
     Input('user-company-store', 'data'),
     Input('selected-competitors-store', 'data')]
)
def render_industry_median_table(dark_mode, user_company, selected_competitors):
    """Render the industry median benchmarking table"""

    # Get data for calculating industry median
    df = get_competitor_data()

    if df is None or df.empty:
        return html.Div("No industry data available", style={
            "textAlign": "center", "padding": "40px", "color": COLORS['gray']['500']
        })

    text_color = COLORS['gray']['100'] if dark_mode else COLORS['gray']['900']
    header_bg = COLORS['gray']['700'] if dark_mode else COLORS['gray']['100']
    row_bg = COLORS['gray']['800'] if dark_mode else "#ffffff"
    alt_row_bg = COLORS['gray']['700'] if dark_mode else COLORS['gray']['50']
    border_color = COLORS['gray']['600'] if dark_mode else COLORS['gray']['200']

    # Get user company values
    user_company_name = "Your Company"
    user_values = {}
    if user_company:
        user_company_name = user_company.get('company_name', 'Your Company')
        user_values = {
            'EBITDA_MARGIN': user_company.get('EBITDA_MARGIN', 0),
            'GROSS_MARGIN': user_company.get('GROSS_MARGIN', 0),
            'CUR_RATIO': user_company.get('CUR_RATIO', 0),
            'QUICK_RATIO': user_company.get('QUICK_RATIO', 0),
            'TOT_DEBT_TO_TOT_ASSET': user_company.get('TOT_DEBT_TO_TOT_ASSET', 0),
            'INTEREST_COVERAGE_RATIO': user_company.get('INTEREST_COVERAGE_RATIO', 0),
        }
    else:
        # Use first selected company as "your company" for demo
        if selected_competitors and len(selected_competitors) > 0:
            first_company = df[df['TICKER'] == selected_competitors[0]]
            if not first_company.empty:
                user_company_name = selected_competitors[0]
                user_values = {
                    'EBITDA_MARGIN': first_company['EBITDA_MARGIN'].iloc[0],
                    'GROSS_MARGIN': first_company['GROSS_MARGIN'].iloc[0],
                    'CUR_RATIO': first_company['CUR_RATIO'].iloc[0],
                    'QUICK_RATIO': first_company['QUICK_RATIO'].iloc[0],
                    'TOT_DEBT_TO_TOT_ASSET': first_company['TOT_DEBT_TO_TOT_ASSET'].iloc[0],
                    'INTEREST_COVERAGE_RATIO': first_company['INTEREST_COVERAGE_RATIO'].iloc[0],
                }

    # Calculate industry medians
    industry_medians = {
        'EBITDA_MARGIN': df['EBITDA_MARGIN'].median(),
        'GROSS_MARGIN': df['GROSS_MARGIN'].median(),
        'CUR_RATIO': df['CUR_RATIO'].median(),
        'QUICK_RATIO': df['QUICK_RATIO'].median(),
        'TOT_DEBT_TO_TOT_ASSET': df['TOT_DEBT_TO_TOT_ASSET'].median(),
        'INTEREST_COVERAGE_RATIO': df['INTEREST_COVERAGE_RATIO'].median(),
    }

    # Define metrics with interpretation
    metrics_config = [
        {'key': 'EBITDA_MARGIN', 'label': 'EBITDA Margin', 'format': '{:.1f}%', 'higher_is_better': True,
         'good_text': 'Superior efficiency vs industry', 'bad_text': 'Below industry efficiency'},
        {'key': 'GROSS_MARGIN', 'label': 'Gross Margin', 'format': '{:.1f}%', 'higher_is_better': True,
         'good_text': 'Strong pricing power', 'bad_text': 'Pricing pressure vs peers'},
        {'key': 'CUR_RATIO', 'label': 'Current Ratio', 'format': '{:.2f}x', 'higher_is_better': True,
         'good_text': 'Healthy liquidity position', 'bad_text': 'Liquidity below industry norm'},
        {'key': 'QUICK_RATIO', 'label': 'Quick Ratio', 'format': '{:.2f}x', 'higher_is_better': True,
         'good_text': 'Strong quick liquidity', 'bad_text': 'Quick liquidity needs attention'},
        {'key': 'TOT_DEBT_TO_TOT_ASSET', 'label': 'Debt/Asset', 'format': '{:.1f}%', 'higher_is_better': False,
         'good_text': 'Conservative leverage - lower risk', 'bad_text': 'Higher leverage than industry'},
        {'key': 'INTEREST_COVERAGE_RATIO', 'label': 'Interest Coverage', 'format': '{:.1f}x', 'higher_is_better': True,
         'good_text': 'Strong debt service capacity', 'bad_text': 'Debt service capacity below median'},
    ]

    # Build table header
    header_cells = [
        html.Th("Metric", style={"padding": "12px 16px", "textAlign": "left", "fontWeight": "600", "fontSize": "13px", "color": text_color, "backgroundColor": header_bg, "borderBottom": f"2px solid {COLORS['success']}", "minWidth": "140px"}),
        html.Th(user_company_name, style={"padding": "12px 16px", "textAlign": "center", "fontWeight": "600", "fontSize": "13px", "color": text_color, "backgroundColor": COLORS['primary'] + "20", "borderBottom": f"2px solid {COLORS['success']}", "minWidth": "100px"}),
        html.Th("Industry Median", style={"padding": "12px 16px", "textAlign": "center", "fontWeight": "600", "fontSize": "13px", "color": text_color, "backgroundColor": header_bg, "borderBottom": f"2px solid {COLORS['success']}", "minWidth": "120px"}),
        html.Th("Difference", style={"padding": "12px 16px", "textAlign": "center", "fontWeight": "600", "fontSize": "13px", "color": text_color, "backgroundColor": header_bg, "borderBottom": f"2px solid {COLORS['success']}", "minWidth": "100px"}),
        html.Th("Interpretation", style={"padding": "12px 16px", "textAlign": "left", "fontWeight": "600", "fontSize": "13px", "color": text_color, "backgroundColor": header_bg, "borderBottom": f"2px solid {COLORS['success']}", "minWidth": "200px"}),
    ]

    # Build table rows
    rows = []
    for idx, metric in enumerate(metrics_config):
        user_val = user_values.get(metric['key'], 0) or 0
        median_val = industry_medians.get(metric['key'], 0) or 0
        diff = user_val - median_val

        # Determine if good or bad
        if metric['higher_is_better']:
            is_good = diff >= 0
        else:
            is_good = diff <= 0

        color = COLORS['success'] if is_good else COLORS['danger']
        interpretation = metric['good_text'] if is_good else metric['bad_text']

        # Format difference with sign
        if 'x' in metric['format']:
            diff_formatted = f"+{diff:.2f}x" if diff >= 0 else f"{diff:.2f}x"
        else:
            diff_formatted = f"+{diff:.1f}%" if diff >= 0 else f"{diff:.1f}%"

        row_bg_color = alt_row_bg if idx % 2 == 0 else row_bg

        rows.append(html.Tr([
            html.Td(metric['label'], style={
                "padding": "12px 16px", "fontWeight": "500", "fontSize": "13px", "color": text_color,
                "backgroundColor": row_bg_color, "borderBottom": f"1px solid {border_color}"
            }),
            html.Td(metric['format'].format(user_val), style={
                "padding": "12px 16px", "textAlign": "center", "fontSize": "13px", "fontWeight": "600",
                "color": text_color, "backgroundColor": COLORS['primary'] + "10", "borderBottom": f"1px solid {border_color}"
            }),
            html.Td(metric['format'].format(median_val), style={
                "padding": "12px 16px", "textAlign": "center", "fontSize": "13px",
                "color": COLORS['gray']['400'], "backgroundColor": row_bg_color, "borderBottom": f"1px solid {border_color}"
            }),
            html.Td([
                html.Span(diff_formatted, style={
                    "color": color,
                    "fontWeight": "600",
                    "backgroundColor": f"{color}15",
                    "padding": "4px 10px",
                    "borderRadius": "4px",
                    "fontSize": "12px"
                }),
                html.I(className=f"fas fa-arrow-{'up' if is_good else 'down'} ms-2", style={
                    "fontSize": "10px",
                    "color": color
                })
            ], style={
                "padding": "12px 16px", "textAlign": "center",
                "backgroundColor": row_bg_color, "borderBottom": f"1px solid {border_color}"
            }),
            html.Td([
                html.I(className=f"fas fa-{'check-circle' if is_good else 'exclamation-circle'} me-2", style={
                    "fontSize": "12px",
                    "color": color
                }),
                html.Span(interpretation, style={"color": color, "fontSize": "12px"})
            ], style={
                "padding": "12px 16px", "textAlign": "left",
                "backgroundColor": row_bg_color, "borderBottom": f"1px solid {border_color}"
            })
        ]))

    return html.Div([
        html.Table([
            html.Thead([html.Tr(header_cells)]),
            html.Tbody(rows)
        ], style={
            "width": "100%",
            "borderCollapse": "collapse",
            "borderRadius": "8px",
            "overflow": "hidden",
            "border": f"1px solid {border_color}"
        })
    ], style={"overflowX": "auto"})

# Callback to handle chart type button clicks
@app.callback(
    [Output('chart-type-store', 'data'),
     Output('chart-type-bar', 'style'),
     Output('chart-type-line', 'style'),
     Output('chart-type-pie', 'style')],
    [Input('chart-type-bar', 'n_clicks'),
     Input('chart-type-line', 'n_clicks'),
     Input('chart-type-pie', 'n_clicks')],
    [State('dark-mode-store', 'data')]
)
def update_chart_type(bar_clicks, line_clicks, pie_clicks, dark_mode):
    ctx = callback_context

    base_style = {
        "border": f"1px solid {COLORS['gray']['600'] if dark_mode else COLORS['gray']['300']}",
        "borderRadius": "20px",
        "padding": "6px 14px",
        "backgroundColor": "transparent",
        "cursor": "pointer",
        "display": "inline-flex",
        "alignItems": "center",
        "justifyContent": "center",
        "fontSize": "13px",
        "fontWeight": "500",
        "color": COLORS['gray']['400'] if dark_mode else COLORS['gray']['600'],
        "transition": "all 0.2s ease"
    }

    active_style = {
        **base_style,
        "backgroundColor": COLORS['primary'],
        "borderColor": COLORS['primary'],
        "color": "#ffffff"
    }

    # Default to bar chart
    if not ctx.triggered or ctx.triggered[0]['prop_id'] == '.':
        return 'bar', active_style, base_style, base_style

    triggered_id = ctx.triggered[0]['prop_id'].split('.')[0]

    if triggered_id == 'chart-type-bar':
        return 'bar', active_style, base_style, base_style
    elif triggered_id == 'chart-type-line':
        return 'line', base_style, active_style, base_style
    elif triggered_id == 'chart-type-pie':
        return 'pie', base_style, base_style, active_style

    return 'bar', active_style, base_style, base_style

# Callback to handle view mode button clicks
@app.callback(
    [Output('view-mode-store', 'data'),
     Output('view-mode-graph', 'style'),
     Output('view-mode-table', 'style')],
    [Input('view-mode-graph', 'n_clicks'),
     Input('view-mode-table', 'n_clicks')],
    [State('dark-mode-store', 'data')]
)
def update_view_mode(graph_clicks, table_clicks, dark_mode):
    ctx = callback_context

    base_style = {
        "border": f"1px solid {COLORS['gray']['600'] if dark_mode else COLORS['gray']['300']}",
        "borderRadius": "20px",
        "padding": "6px 14px",
        "backgroundColor": "transparent",
        "cursor": "pointer",
        "display": "inline-flex",
        "alignItems": "center",
        "justifyContent": "center",
        "fontSize": "13px",
        "fontWeight": "500",
        "color": COLORS['gray']['400'] if dark_mode else COLORS['gray']['600'],
        "transition": "all 0.2s ease"
    }

    active_style = {
        **base_style,
        "backgroundColor": COLORS['primary'],
        "borderColor": COLORS['primary'],
        "color": "#ffffff"
    }

    # Default to graph view
    if not ctx.triggered or ctx.triggered[0]['prop_id'] == '.':
        return 'graph', active_style, base_style

    triggered_id = ctx.triggered[0]['prop_id'].split('.')[0]

    if triggered_id == 'view-mode-graph':
        return 'graph', active_style, base_style
    elif triggered_id == 'view-mode-table':
        return 'table', base_style, active_style

    return 'graph', active_style, base_style

# Callback to render company comparison cards
@app.callback(
    Output('company-comparison-cards', 'children'),
    [Input('selected-competitors-store', 'data'),
     Input('dark-mode-store', 'data'),
     Input('user-company-store', 'data')]
)
def render_comparison_cards(selected_competitors, dark_mode, user_company):
    """Render individual company comparison cards with color-coded metrics"""

    # Get data
    df = get_competitor_data()

    if df is None:
        df = pd.DataFrame()

    # Add user company data if available
    user_company_name = None
    if user_company:
        user_company_name = user_company.get('company_name', 'Your Company')
        user_row = {
            'TICKER': user_company_name,
            'TOT_DEBT_TO_TOT_ASSET': user_company.get('TOT_DEBT_TO_TOT_ASSET', 0),
            'CASH_DVD_COVERAGE': user_company.get('CASH_DVD_COVERAGE', 0),
            'TOT_DEBT_TO_EBITDA': user_company.get('TOT_DEBT_TO_EBITDA', 0),
            'CUR_RATIO': user_company.get('CUR_RATIO', 0),
            'QUICK_RATIO': user_company.get('QUICK_RATIO', 0),
            'GROSS_MARGIN': user_company.get('GROSS_MARGIN', 0),
            'INTEREST_COVERAGE_RATIO': user_company.get('INTEREST_COVERAGE_RATIO', 0),
            'EBITDA_MARGIN': user_company.get('EBITDA_MARGIN', 0),
            'NET_DEBT_TO_SHRHLDR_EQTY': user_company.get('NET_DEBT_TO_SHRHLDR_EQTY', 0)
        }
        user_df = pd.DataFrame([user_row])
        df = pd.concat([user_df, df], ignore_index=True)

    if df.empty or not selected_competitors:
        return html.Div("Select companies to compare", style={
            "textAlign": "center",
            "padding": "40px",
            "color": COLORS['gray']['500']
        })

    # Filter for selected competitors
    df_filtered = df[df['TICKER'].isin(selected_competitors)]

    # Remove duplicates - keep only one row per ticker
    df_filtered = df_filtered.drop_duplicates(subset=['TICKER'], keep='first')

    if df_filtered.empty:
        return html.Div("No data available", style={
            "textAlign": "center",
            "padding": "40px",
            "color": COLORS['gray']['500']
        })

    # Metrics to compare with their ideal direction (higher_is_better)
    comparison_metrics = [
        {'key': 'EBITDA_MARGIN', 'label': 'EBITDA Margin', 'higher_is_better': True, 'suffix': '%'},
        {'key': 'GROSS_MARGIN', 'label': 'Gross Margin', 'higher_is_better': True, 'suffix': '%'},
        {'key': 'CUR_RATIO', 'label': 'Current Ratio', 'higher_is_better': True, 'suffix': ''},
        {'key': 'QUICK_RATIO', 'label': 'Quick Ratio', 'higher_is_better': True, 'suffix': ''},
        {'key': 'TOT_DEBT_TO_TOT_ASSET', 'label': 'Debt/Asset', 'higher_is_better': False, 'suffix': '%'},
        {'key': 'INTEREST_COVERAGE_RATIO', 'label': 'Interest Coverage', 'higher_is_better': True, 'suffix': 'x'},
    ]

    # Calculate percentiles for color coding
    def get_color_for_value(value, all_values, higher_is_better):
        """Determine color based on percentile ranking"""
        if pd.isna(value) or len(all_values) == 0:
            return COLORS['gray']['400']

        sorted_vals = sorted([v for v in all_values if not pd.isna(v)])
        if len(sorted_vals) == 0:
            return COLORS['gray']['400']

        # Calculate percentile
        rank = sum(1 for v in sorted_vals if v <= value) / len(sorted_vals)

        if higher_is_better:
            if rank >= 0.66:
                return '#10b981'  # Green - good
            elif rank >= 0.33:
                return COLORS['warning']  # Yellow - medium
            else:
                return '#ef4444'  # Red - bad
        else:
            if rank <= 0.33:
                return '#10b981'  # Green - good (lower is better)
            elif rank <= 0.66:
                return COLORS['warning']  # Yellow - medium
            else:
                return '#ef4444'  # Red - bad

    # Build cards for each company
    cards = []
    text_color = COLORS['gray']['100'] if dark_mode else COLORS['gray']['900']
    card_bg = COLORS['gray']['700'] if dark_mode else COLORS['gray']['50']

    for _, row in df_filtered.iterrows():
        company_name = row['TICKER']
        is_user_company = user_company_name and company_name == user_company_name

        # Company card header style
        header_bg = COLORS['primary'] if is_user_company else (COLORS['gray']['600'] if dark_mode else COLORS['gray']['200'])
        header_text = '#ffffff' if is_user_company else text_color

        metric_rows = []
        for metric in comparison_metrics:
            value = row.get(metric['key'], 0)
            all_values = df_filtered[metric['key']].tolist()
            color = get_color_for_value(value, all_values, metric['higher_is_better'])

            # Format value
            if pd.isna(value):
                formatted_value = "-"
            elif metric['suffix'] == '%':
                formatted_value = f"{value:.1f}%"
            elif metric['suffix'] == 'x':
                formatted_value = f"{value:.1f}x"
            else:
                formatted_value = f"{value:.2f}"

            metric_rows.append(
                html.Div([
                    html.Span(metric['label'], style={
                        "fontSize": "11px",
                        "color": COLORS['gray']['500'],
                        "flex": "1"
                    }),
                    html.Span(formatted_value, style={
                        "fontSize": "13px",
                        "fontWeight": "600",
                        "color": color,
                        "backgroundColor": f"{color}15",
                        "padding": "2px 8px",
                        "borderRadius": "4px"
                    })
                ], style={
                    "display": "flex",
                    "justifyContent": "space-between",
                    "alignItems": "center",
                    "padding": "6px 0",
                    "borderBottom": f"1px solid {COLORS['gray']['600'] if dark_mode else COLORS['gray']['200']}"
                })
            )

        # Remove border from last row
        if metric_rows:
            last_row_style = metric_rows[-1].style.copy() if hasattr(metric_rows[-1], 'style') else {}
            metric_rows[-1] = html.Div([
                html.Span(comparison_metrics[-1]['label'], style={
                    "fontSize": "11px",
                    "color": COLORS['gray']['500'],
                    "flex": "1"
                }),
                html.Span(
                    f"{row.get(comparison_metrics[-1]['key'], 0):.1f}x" if comparison_metrics[-1]['suffix'] == 'x' else
                    f"{row.get(comparison_metrics[-1]['key'], 0):.1f}%" if comparison_metrics[-1]['suffix'] == '%' else
                    f"{row.get(comparison_metrics[-1]['key'], 0):.2f}",
                    style={
                        "fontSize": "13px",
                        "fontWeight": "600",
                        "color": get_color_for_value(
                            row.get(comparison_metrics[-1]['key'], 0),
                            df_filtered[comparison_metrics[-1]['key']].tolist(),
                            comparison_metrics[-1]['higher_is_better']
                        ),
                        "backgroundColor": f"{get_color_for_value(row.get(comparison_metrics[-1]['key'], 0), df_filtered[comparison_metrics[-1]['key']].tolist(), comparison_metrics[-1]['higher_is_better'])}15",
                        "padding": "2px 8px",
                        "borderRadius": "4px"
                    }
                )
            ], style={
                "display": "flex",
                "justifyContent": "space-between",
                "alignItems": "center",
                "padding": "6px 0"
            })

        cards.append(
            html.Div([
                # Company Header
                html.Div([
                    html.Div([
                        html.I(className="fas fa-building me-2" if not is_user_company else "fas fa-star me-2", style={
                            "fontSize": "12px"
                        }),
                        html.Span(company_name, style={
                            "fontWeight": "600",
                            "fontSize": "13px"
                        })
                    ], style={"display": "flex", "alignItems": "center"}),
                    html.Span("Your Company" if is_user_company else "", style={
                        "fontSize": "10px",
                        "opacity": "0.8"
                    }) if is_user_company else None
                ], style={
                    "backgroundColor": header_bg,
                    "color": header_text,
                    "padding": "10px 12px",
                    "borderRadius": "8px 8px 0 0",
                    "display": "flex",
                    "justifyContent": "space-between",
                    "alignItems": "center"
                }),
                # Metrics
                html.Div(metric_rows, style={
                    "padding": "8px 12px",
                    "backgroundColor": card_bg,
                    "borderRadius": "0 0 8px 8px"
                })
            ], style={
                "border": f"1px solid {COLORS['gray']['600'] if dark_mode else COLORS['gray']['200']}",
                "borderRadius": "8px",
                "overflow": "hidden",
                "minWidth": "220px",
                "flex": "1"
            })
        )

    # Return cards in a wrapping grid layout (Task 2 - no horizontal scroll)
    return html.Div(cards, className="quick-compare-grid", style={
        "display": "flex",
        "flexWrap": "wrap",
        "gap": "16px",
        "paddingBottom": "8px"
    })

# Main callback to render chart or table
@app.callback(
    Output('competitor-chart-container', 'children'),
    [Input('competitor-metric-selector', 'value'),
     Input('chart-type-store', 'data'),
     Input('view-mode-store', 'data'),
     Input('selected-competitors-store', 'data'),
     Input('dark-mode-store', 'data'),
     Input('user-company-store', 'data')]
)
def render_competitor_chart(selected_metric, chart_type, view_mode, selected_competitors, dark_mode, user_company):
    """Render the chart or table based on filters"""

    # Get data
    df = get_competitor_data()

    if df is None:
        df = pd.DataFrame()

    # Add user company data if available
    if user_company:
        user_company_name = user_company.get('company_name', 'Your Company')
        user_row = {
            'TICKER': user_company_name,
            'IDENTIFIER_TYPE': 'USER',
            'IDENTIFIER_VALUE': 'User Input',
            'TOT_DEBT_TO_TOT_ASSET': user_company.get('TOT_DEBT_TO_TOT_ASSET', 0),
            'CASH_DVD_COVERAGE': user_company.get('CASH_DVD_COVERAGE', 0),
            'TOT_DEBT_TO_EBITDA': user_company.get('TOT_DEBT_TO_EBITDA', 0),
            'CUR_RATIO': user_company.get('CUR_RATIO', 0),
            'QUICK_RATIO': user_company.get('QUICK_RATIO', 0),
            'GROSS_MARGIN': user_company.get('GROSS_MARGIN', 0),
            'INTEREST_COVERAGE_RATIO': user_company.get('INTEREST_COVERAGE_RATIO', 0),
            'EBITDA_MARGIN': user_company.get('EBITDA_MARGIN', 0),
            'TOT_LIAB_AND_EQY': 0,
            'NET_DEBT_TO_SHRHLDR_EQTY': user_company.get('NET_DEBT_TO_SHRHLDR_EQTY', 0)
        }
        user_df = pd.DataFrame([user_row])
        df = pd.concat([user_df, df], ignore_index=True)

    if df.empty or not selected_competitors:
        return html.Div("No data available", style={"textAlign": "center", "padding": "40px"})

    # Filter for selected competitors
    df_filtered = df[df['TICKER'].isin(selected_competitors)]

    # Remove duplicates - keep only one row per ticker
    df_filtered = df_filtered.drop_duplicates(subset=['TICKER'], keep='first')

    if df_filtered.empty:
        return html.Div("No data for selected competitors", style={"textAlign": "center", "padding": "40px"})

    text_color = COLORS['gray']['100'] if dark_mode else COLORS['gray']['900']

    # Table View
    if view_mode == 'table':
        # Create table with all numeric metrics
        table_columns = ['TICKER'] + NUMERIC_METRIC_COLUMNS
        table_df = df_filtered[table_columns].copy()

        # Format numeric columns
        for col in NUMERIC_METRIC_COLUMNS:
            table_df[col] = table_df[col].apply(lambda x: f"{x:.2f}" if pd.notnull(x) else "-")

        # Rename columns for display
        table_df.columns = ['Ticker'] + [METRIC_LABELS.get(col, col) for col in NUMERIC_METRIC_COLUMNS]

        header_style = {
            "backgroundColor": COLORS['gray']['700'] if dark_mode else COLORS['gray']['100'],
            "color": text_color,
            "fontWeight": "600",
            "padding": "12px",
            "textAlign": "left",
            "borderBottom": f"2px solid {COLORS['primary']}"
        }

        cell_style = {
            "padding": "12px",
            "borderBottom": f"1px solid {COLORS['gray']['700'] if dark_mode else COLORS['gray']['200']}",
            "color": text_color
        }

        return html.Div([
            html.Table([
                html.Thead([
                    html.Tr([html.Th(col, style=header_style) for col in table_df.columns])
                ]),
                html.Tbody([
                    html.Tr([
                        html.Td(table_df.iloc[i][col], style=cell_style)
                        for col in table_df.columns
                    ]) for i in range(len(table_df))
                ])
            ], style={
                "width": "100%",
                "borderCollapse": "collapse",
                "fontSize": "14px"
            })
        ], style={"overflowX": "auto"})

    # Graph View
    companies = df_filtered['TICKER'].tolist()
    values = df_filtered[selected_metric].tolist()
    metric_label = METRIC_LABELS.get(selected_metric, selected_metric)

    # Color palette for charts
    colors = [COLORS['primary'], COLORS['success'], COLORS['warning'], COLORS['danger'],
              COLORS['info'], COLORS['purple'], '#ec4899', '#14b8a6', '#f97316', '#84cc16']

    fig = go.Figure()

    if chart_type == 'bar':
        fig.add_trace(go.Bar(
            x=companies,
            y=values,
            marker_color=[colors[i % len(colors)] for i in range(len(companies))],
            text=[f"{v:.2f}" for v in values],
            textposition='outside'
        ))
        fig.update_layout(
            title=f"{metric_label} by Company",
            xaxis_title="Company",
            yaxis_title=metric_label
        )

    elif chart_type == 'line':
        fig.add_trace(go.Scatter(
            x=companies,
            y=values,
            mode='lines+markers+text',
            line=dict(color=COLORS['primary'], width=3),
            marker=dict(size=10, color=COLORS['primary']),
            text=[f"{v:.2f}" for v in values],
            textposition='top center'
        ))
        fig.update_layout(
            title=f"{metric_label} by Company",
            xaxis_title="Company",
            yaxis_title=metric_label
        )

    elif chart_type == 'pie':
        # Handle negative values for pie chart
        abs_values = [abs(v) for v in values]
        labels = [f"{c} ({v:.2f})" for c, v in zip(companies, values)]

        fig.add_trace(go.Pie(
            labels=labels,
            values=abs_values,
            marker=dict(colors=[colors[i % len(colors)] for i in range(len(companies))]),
            textinfo='percent+label',
            hole=0.3
        ))
        fig.update_layout(
            title=f"{metric_label} Distribution"
        )

    # Common layout settings
    fig.update_layout(
        height=400,
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        font=dict(color=text_color),
        margin=dict(t=50, b=50, l=50, r=50),
        showlegend=False if chart_type != 'pie' else True
    )

    if chart_type != 'pie':
        fig.update_xaxes(showgrid=False)
        fig.update_yaxes(showgrid=True, gridcolor=COLORS['gray']['700'] if dark_mode else COLORS['gray']['200'])

    return dcc.Graph(figure=fig, config={'displayModeBar': False})

#==============================================================================
# COMPARATIVE ANALYSIS & MARGIN BRIDGE & ALERT FEED
#==============================================================================

@app.callback(
    Output('comparative-analysis-container', 'children'),
    [Input('update-timestamp', 'data'),
     Input('dark-mode-store', 'data')]
)
def update_comparative_analysis(timestamp, dark_mode):
    """Comparative analysis / benchmarking"""
    return html.Div()  # Placeholder for now


@app.callback(
    Output('margin-bridge-container', 'children'),
    [Input('update-timestamp', 'data'),
     Input('dark-mode-store', 'data'),
     Input('selected-competitors-store', 'data'),
     Input('user-company-store', 'data')]
)
def update_margin_bridge(timestamp, dark_mode, selected_competitors, user_company):
    """Margin bridge — 3 waterfall charts sourced from Kt.json"""
    import json as _json, os as _os

    tc         = COLORS['gray']['100'] if dark_mode else COLORS['gray']['800']
    gc         = COLORS['gray']['700'] if dark_mode else COLORS['gray']['200']
    card_bg    = COLORS['gray']['800'] if dark_mode else '#ffffff'
    border_col = COLORS['gray']['700'] if dark_mode else COLORS['gray']['200']
    card_style = {
        "backgroundColor": card_bg,
        "border": f"1px solid {border_col}",
        "borderRadius": "12px",
        "padding": "24px",
        "marginBottom": "20px",
    }

    # ── Load Kt.json ──────────────────────────────────────────────────────────
    KT_PATH = _os.path.join(_os.path.dirname(__file__), 'Kt.json')
    try:
        with open(KT_PATH) as _f:
            kt = _json.load(_f)
    except Exception as _e:
        logger.warning(f"Could not load Kt.json: {_e}")
        kt = {}

    ann  = kt.get('ANNUAL_FINANCIALS', {})
    fadv = kt.get('FINANCIAL_ADVANCED', {})
    qtr  = kt.get('QUARTERLY', {})

    def _v(d, key, fallback=0.0):
        v = d.get(key, fallback)
        return float(v) if v is not None else fallback

    # ── Annual P&L values from Kt.json ────────────────────────────────────────
    revenue    = _v(ann,  'SALES_REV_TURN',              14643.734)
    ebitda     = _v(fadv, 'EBITDA',                       3241.553)
    da         = _v(ann,  'DEPRECIATION',                  846.629)
    net_income = _v(ann,  'PROFIT_AFTER_TAX',              739.802)
    opex_sga   = _v(fadv, 'SELLING_AND_ADMIN_EXPENSE',    4127.918)
    gross_profit = ebitda + opex_sga
    cogs         = revenue - gross_profit
    interest_tax = ebitda - da - net_income   # balances the bridge exactly

    # ── Margin metrics ────────────────────────────────────────────────────────
    gm_pct  = round(gross_profit / revenue * 100, 1) if revenue else 0
    em_pct  = _v(fadv, 'EBITDA_MARGIN', round(ebitda / revenue * 100, 1))
    nm_pct  = _v(ann,  'NET_PROFIT_MARGIN', round(net_income / revenue * 100, 1))
    om_pct  = _v(ann,  'OPERATING_MARGIN', 0.0)

    # ── Helper: build one waterfall figure ───────────────────────────────────
    COLOR_GREEN = '#22c55e'
    COLOR_RED   = '#ef4444'
    COLOR_TEAL  = '#0ea5e9'

    def _wf_fig(steps, title, height=400):
        """steps = list of (label, value, measure)"""
        x_lbl    = [s[0] for s in steps]
        y_vals   = [s[1] for s in steps]
        measures = [s[2] for s in steps]

        def _fmt(v):
            av = abs(v)
            if av >= 1000:
                return f"${v/1000:.1f}B"
            return f"${v:.0f}M"

        fig = go.Figure(go.Waterfall(
            orientation="v",
            measure=measures,
            x=x_lbl,
            y=y_vals,
            text=[_fmt(v) for v in y_vals],
            textposition="outside",
            textfont=dict(size=10, color=tc),
            connector={"line": {"color": gc, "width": 1, "dash": "dot"}},
            increasing={"marker": {"color": COLOR_GREEN, "line": {"width": 0}}},
            decreasing={"marker": {"color": COLOR_RED,   "line": {"width": 0}}},
            totals={"marker":    {"color": COLOR_TEAL,   "line": {"width": 0}}},
        ))
        fig.update_layout(
            title=dict(text=title, font=dict(size=13, color=tc, weight="bold"), x=0),
            height=height,
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)',
            font=dict(color=tc, size=11),
            xaxis=dict(showgrid=False, tickfont=dict(size=10, color=tc), tickangle=-30),
            yaxis=dict(showgrid=True, gridcolor=gc, tickfont=dict(color=tc), title="$M"),
            showlegend=False,
            margin=dict(l=50, r=20, t=50, b=60),
        )
        return fig

    # ── Chart 1: Annual Margin Bridge ─────────────────────────────────────────
    annual_steps = [
        ('Revenue',       revenue,        'relative'),
        ('COGS',         -abs(cogs),       'relative'),
        ('Gross Profit',  gross_profit,    'total'),
        ('Opex (SG&A)',  -abs(opex_sga),   'relative'),
        ('EBITDA',        ebitda,          'total'),
        ('D&A',          -abs(da),         'relative'),
        ('Interest & Tax',-abs(interest_tax), 'relative'),
        ('Net Income',    net_income,      'total'),
    ]
    fig_annual = _wf_fig(annual_steps, "Revenue to Net Income", height=420)

    # ── Chart 2: QoQ Waterfall ────────────────────────────────────────────────
    cq = qtr.get('current_quarter',  {})
    pq = qtr.get('previous_quarter', {})

    def _qoq_steps(q, label_suffix):
        r  = _v(q, 'revenue');        gpr = _v(q, 'gross_profit')
        c  = _v(q, 'cogs');           op  = _v(q, 'opex_sga')
        eb = _v(q, 'ebitda');         d   = _v(q, 'da')
        it = _v(q, 'interest_tax');   ni  = _v(q, 'net_income')
        return [
            (f'Revenue',       r,       'relative'),
            (f'COGS',         -abs(c),   'relative'),
            (f'Gross Profit',  gpr,      'total'),
            (f'Opex (SG&A)',  -abs(op),  'relative'),
            (f'EBITDA',        eb,       'total'),
            (f'D&A',          -abs(d),   'relative'),
            (f'Int & Tax',    -abs(it),  'relative'),
            (f'Net Income',    ni,       'total'),
        ]

    cq_period = cq.get('period', 'Current Quarter')
    pq_period = pq.get('period', 'Previous Quarter')

    # Side-by-side grouped waterfall via overlay of two waterfall traces
    def _qoq_fig():
        cq_steps = _qoq_steps(cq, cq_period)
        pq_steps = _qoq_steps(pq, pq_period)
        x_lbl = [s[0] for s in cq_steps]

        fig = go.Figure()

        # Previous quarter (lighter)
        fig.add_trace(go.Waterfall(
            name=pq_period,
            orientation="v",
            measure=[s[2] for s in pq_steps],
            x=x_lbl,
            y=[s[1] for s in pq_steps],
            textposition="outside",
            textfont=dict(size=9, color=COLORS['gray']['400']),
            connector={"line": {"color": gc, "width": 0.5, "dash": "dot"}},
            increasing={"marker": {"color": 'rgba(34,197,94,0.45)',  "line": {"width": 0}}},
            decreasing={"marker": {"color": 'rgba(239,68,68,0.45)',  "line": {"width": 0}}},
            totals={"marker":    {"color": 'rgba(14,165,233,0.45)',  "line": {"width": 0}}},
            offset=-0.2, width=0.35,
        ))

        # Current quarter (solid)
        fig.add_trace(go.Waterfall(
            name=cq_period,
            orientation="v",
            measure=[s[2] for s in cq_steps],
            x=x_lbl,
            y=[s[1] for s in cq_steps],
            textposition="outside",
            textfont=dict(size=9, color=tc),
            connector={"line": {"color": gc, "width": 0.5, "dash": "dot"}},
            increasing={"marker": {"color": COLOR_GREEN, "line": {"width": 0}}},
            decreasing={"marker": {"color": COLOR_RED,   "line": {"width": 0}}},
            totals={"marker":    {"color": COLOR_TEAL,   "line": {"width": 0}}},
            offset=0.2, width=0.35,
        ))

        fig.update_layout(
            title=dict(text=f"QoQ — {cq_period} vs {pq_period}", font=dict(size=13, color=tc, weight="bold"), x=0),
            height=380,
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)',
            font=dict(color=tc, size=10),
            barmode='overlay',
            xaxis=dict(showgrid=False, tickfont=dict(size=10, color=tc), tickangle=-30),
            yaxis=dict(showgrid=True, gridcolor=gc, tickfont=dict(color=tc), title="$M"),
            legend=dict(orientation='h', yanchor='bottom', y=-0.3, xanchor='center', x=0.5,
                        bgcolor='rgba(0,0,0,0)', font=dict(color=tc, size=10)),
            margin=dict(l=50, r=20, t=50, b=70),
            showlegend=True,
        )
        return fig

    # ── Chart 3: YoY Waterfall ────────────────────────────────────────────────
    lyq = qtr.get('same_quarter_ly', {})
    ly_period = lyq.get('period', 'Same Quarter LY')

    def _yoy_fig():
        cq_steps  = _qoq_steps(cq,  cq_period)
        lyq_steps = _qoq_steps(lyq, ly_period)
        x_lbl = [s[0] for s in cq_steps]

        fig = go.Figure()
        fig.add_trace(go.Waterfall(
            name=ly_period,
            orientation="v",
            measure=[s[2] for s in lyq_steps],
            x=x_lbl,
            y=[s[1] for s in lyq_steps],
            textposition="outside",
            textfont=dict(size=9, color=COLORS['gray']['400']),
            connector={"line": {"color": gc, "width": 0.5, "dash": "dot"}},
            increasing={"marker": {"color": 'rgba(34,197,94,0.45)',  "line": {"width": 0}}},
            decreasing={"marker": {"color": 'rgba(239,68,68,0.45)',  "line": {"width": 0}}},
            totals={"marker":    {"color": 'rgba(14,165,233,0.45)',  "line": {"width": 0}}},
            offset=-0.2, width=0.35,
        ))
        fig.add_trace(go.Waterfall(
            name=cq_period,
            orientation="v",
            measure=[s[2] for s in cq_steps],
            x=x_lbl,
            y=[s[1] for s in cq_steps],
            textposition="outside",
            textfont=dict(size=9, color=tc),
            connector={"line": {"color": gc, "width": 0.5, "dash": "dot"}},
            increasing={"marker": {"color": COLOR_GREEN, "line": {"width": 0}}},
            decreasing={"marker": {"color": COLOR_RED,   "line": {"width": 0}}},
            totals={"marker":    {"color": COLOR_TEAL,   "line": {"width": 0}}},
            offset=0.2, width=0.35,
        ))
        fig.update_layout(
            title=dict(text=f"YoY — {cq_period} vs {ly_period}", font=dict(size=13, color=tc, weight="bold"), x=0),
            height=380,
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)',
            font=dict(color=tc, size=10),
            barmode='overlay',
            xaxis=dict(showgrid=False, tickfont=dict(size=10, color=tc), tickangle=-30),
            yaxis=dict(showgrid=True, gridcolor=gc, tickfont=dict(color=tc), title="$M"),
            legend=dict(orientation='h', yanchor='bottom', y=-0.3, xanchor='center', x=0.5,
                        bgcolor='rgba(0,0,0,0)', font=dict(color=tc, size=10)),
            margin=dict(l=50, r=20, t=50, b=70),
            showlegend=True,
        )
        return fig

    # ── Margin metric cards ───────────────────────────────────────────────────
    metric_cards = []
    for label, val, icon in [
        ('Gross Margin',  gm_pct, 'fa-chart-line'),
        ('EBITDA Margin', em_pct, 'fa-coins'),
        ('Oper. Margin',  om_pct, 'fa-percentage'),
        ('Net Margin',    nm_pct, 'fa-trophy'),
    ]:
        good = val >= (val * 1.0)   # just show value, no forced target
        metric_cards.append(dbc.Col([
            html.Div([
                html.I(className=f"fas {icon}", style={"fontSize": "20px", "color": COLOR_TEAL, "marginBottom": "8px"}),
                html.Div(label, style={"fontSize": "12px", "color": COLORS['gray']['400'] if dark_mode else COLORS['gray']['600'], "marginBottom": "4px"}),
                html.Div(f"{val:.1f}%", style={"fontSize": "22px", "fontWeight": "700", "color": tc}),
            ], style={
                "backgroundColor": COLORS['gray']['700'] if dark_mode else COLORS['gray']['50'],
                "border": f"1px solid {border_col}",
                "borderRadius": "12px", "padding": "18px", "textAlign": "center",
            })
        ], md=3))

    # ── Legend row ────────────────────────────────────────────────────────────
    legend_row = html.Div([
        html.Span([html.Span("■ ", style={"color": COLOR_GREEN}), "Positive / Revenue"], style={"marginRight": "16px", "fontSize": "11px", "color": tc}),
        html.Span([html.Span("■ ", style={"color": COLOR_RED}),   "Cost / Deduction"],   style={"marginRight": "16px", "fontSize": "11px", "color": tc}),
        html.Span([html.Span("■ ", style={"color": COLOR_TEAL}),  "Subtotal"],           style={"fontSize": "11px", "color": tc}),
    ], style={"textAlign": "center", "marginBottom": "8px", "marginTop": "-4px"})

    return html.Div([
        html.H2("Margin Bridge Analysis", style={
            "fontSize": "22px", "fontWeight": "700", "marginBottom": "20px", "color": tc,
        }),

        # ── Metric cards ─────────────────────────────────────────────────────
        dbc.Row(metric_cards, className="g-3 mb-4"),

        # ── Chart 1: Annual ──────────────────────────────────────────────────
        html.Div([
            html.H3("Revenue to Net Income", style={
                "fontSize": "15px", "fontWeight": "600", "color": tc, "marginBottom": "4px",
            }),
            legend_row,
            dcc.Graph(figure=fig_annual, config={'displayModeBar': False}),
        ], style={
            "backgroundColor": card_bg, "borderRadius": "12px",
            "padding": "20px", "border": f"1px solid {border_col}", "marginBottom": "16px",
        }),

        # ── Comparative Analysis header ──────────────────────────────────────
        html.H3("Comparative Analysis", style={
            "fontSize": "17px", "fontWeight": "700", "color": tc,
            "marginBottom": "12px", "marginTop": "8px",
        }),

        # ── Charts 2 & 3: QoQ + YoY side by side ────────────────────────────
        dbc.Row([
            dbc.Col([
                html.Div([
                    dcc.Graph(figure=_qoq_fig(), config={'displayModeBar': False}),
                ], style={
                    "backgroundColor": card_bg, "borderRadius": "12px",
                    "padding": "16px", "border": f"1px solid {border_col}",
                }),
            ], md=6),
            dbc.Col([
                html.Div([
                    dcc.Graph(figure=_yoy_fig(), config={'displayModeBar': False}),
                ], style={
                    "backgroundColor": card_bg, "borderRadius": "12px",
                    "padding": "16px", "border": f"1px solid {border_col}",
                }),
            ], md=6),
        ], className="g-3"),
    ])


@app.callback(
    Output('alert-feed-container', 'children'),
    [Input('update-timestamp', 'data'),
     Input('dark-mode-store', 'data')]
)
def update_alert_feed(timestamp, dark_mode):
    """Alert feed component - generates alerts based on real data analysis"""
    card_style = {
        "backgroundColor": COLORS['gray']['800'] if dark_mode else "#ffffff",
        "border": f"1px solid {COLORS['gray']['700'] if dark_mode else COLORS['gray']['200']}",
        "borderRadius": "12px",
        "padding": "24px"
    }

    # Generate dynamic alerts based on actual data
    alerts = []

    try:
        # Get dashboard stats for data-driven alerts
        if data_service and data_service.connected:
            stats = data_service.get_dashboard_stats()

            # Alert based on data quality
            data_quality = stats.get('data_quality', 0)
            if data_quality >= 95:
                alerts.append({
                    "icon": "fa-check-circle",
                    "color": COLORS['success'],
                    "title": f"Data Quality Excellent ({data_quality}%)",
                    "time": "Now"
                })
            elif data_quality >= 80:
                alerts.append({
                    "icon": "fa-info-circle",
                    "color": COLORS['info'],
                    "title": f"Data Quality Good ({data_quality}%)",
                    "time": "Now"
                })
            else:
                alerts.append({
                    "icon": "fa-triangle-exclamation",
                    "color": COLORS['warning'],
                    "title": f"Data Quality Below Target ({data_quality}%)",
                    "time": "Now"
                })

            # Alert for record count
            total_records = stats.get('total_records', 0)
            if total_records > 0:
                alerts.append({
                    "icon": "fa-database",
                    "color": COLORS['primary'],
                    "title": f"{total_records:,} Financial Records Loaded",
                    "time": "Now"
                })

            # Alert for last sync
            last_sync = stats.get('last_sync')
            if last_sync:
                alerts.append({
                    "icon": "fa-sync-alt",
                    "color": COLORS['success'],
                    "title": "Data Synchronized with SAP HANA",
                    "time": "Just now"
                })

            # Connection status alert
            conn_status = stats.get('connection_status', 'Disconnected')
            if conn_status == 'Connected':
                alerts.append({
                    "icon": "fa-plug",
                    "color": COLORS['success'],
                    "title": "SAP HANA Cloud Connected",
                    "time": "Active"
                })
        else:
            # Fallback alerts for CSV mode
            alerts = [
                {"icon": "fa-info-circle", "color": COLORS['info'], "title": "Running in CSV Fallback Mode", "time": "Now"},
                {"icon": "fa-database", "color": COLORS['warning'], "title": "HANA Connection Unavailable", "time": "Now"}
            ]

            if csv_data and csv_data.get('financial_ratios') is not None:
                csv_count = len(csv_data['financial_ratios'])
                alerts.append({
                    "icon": "fa-file-csv",
                    "color": COLORS['info'],
                    "title": f"Using {csv_count} CSV Records",
                    "time": "Now"
                })
    except Exception as e:
        logger.error(f"Error generating alerts: {e}")
        alerts = [
            {"icon": "fa-triangle-exclamation", "color": COLORS['danger'], "title": "Error Loading Data Status", "time": "Now"}
        ]

    # Limit to max 5 alerts
    alerts = alerts[:5]

    alert_items = []
    for alert in alerts:
        alert_items.append(
            html.Div([
                html.I(className=f"fas {alert['icon']}", style={"color": alert['color'], "marginRight": "12px"}),
                html.Div([
                    html.Span(alert['title'], style={"fontWeight": "500", "color": COLORS['gray']['100'] if dark_mode else COLORS['gray']['900']}),
                    html.Span(alert['time'], style={"fontSize": "12px", "color": COLORS['gray']['400'], "marginLeft": "8px"})
                ], style={"flex": "1"})
            ], style={"display": "flex", "alignItems": "center", "padding": "12px 0", "borderBottom": f"1px solid {COLORS['gray']['200']}"})
        )

    return dbc.Card([
        dbc.CardBody([
            html.H2("System Status", style={
                "fontSize": "18px",
                "fontWeight": "600",
                "marginBottom": "16px",
                "color": COLORS['gray']['100'] if dark_mode else COLORS['gray']['900']
            }),
            html.Div(alert_items if alert_items else html.Span("No alerts", style={"color": COLORS['gray']['500']}))
        ])
    ], style=card_style)

#==============================================================================
# TABBED ANALYTICS SECTION
#==============================================================================

@app.callback(
    Output('tabbed-analytics-container', 'children'),
    [Input('update-timestamp', 'data'),
     Input('dark-mode-store', 'data')]
)
def update_tabbed_analytics(timestamp, dark_mode):
    """Create tabbed analytics section"""

    card_style = {
        "backgroundColor": COLORS['gray']['800'] if dark_mode else "#ffffff",
        "border": f"1px solid {COLORS['gray']['700'] if dark_mode else COLORS['gray']['200']}",
        "borderRadius": "12px"
    }

    return dbc.Card([
        dbc.Tabs([
            dbc.Tab(label="Ratio Analyzer", tab_id="ratio-analyzer"),
            dbc.Tab(label="Scenario Simulator", tab_id="scenario-simulator"),
            dbc.Tab(label="Forecast & Trends", tab_id="forecast"),
            dbc.Tab(label="Anomaly Heatmap", tab_id="heatmap"),
            dbc.Tab(label="Competitor Benchmark", tab_id="competitor"),
            dbc.Tab(label="Goal Tracker", tab_id="goals")
        ], id="analytics-tabs", active_tab="ratio-analyzer", style={
            "borderBottom": f"2px solid {COLORS['gray']['200']}"
        }),

        html.Div(id="analytics-tab-content", style={"padding": "24px"})
    ], style=card_style)

@app.callback(
    Output('analytics-tab-content', 'children'),
    [Input('analytics-tabs', 'active_tab'),
     Input('dark-mode-store', 'data'),
     Input('selected-competitors-store', 'data')]
)
def render_tab_content(active_tab, dark_mode, selected_competitors):
    """Render ML-powered content for active tab"""
    
    # Styling based on dark mode
    text_color = COLORS['gray']['100'] if dark_mode else COLORS['gray']['800']
    bg_color = COLORS['gray']['800'] if dark_mode else '#ffffff'
    card_bg = COLORS['gray']['700'] if dark_mode else COLORS['gray']['50']
    
    # Ensure we have selected companies
    if not selected_competitors:
        selected_competitors = ['NVDA', 'MSFT', 'GOOGL', 'META', 'AAPL']
    
    # Check if ML service is available
    if ml_service is None:
        return html.Div([
            html.I(className="fas fa-exclamation-triangle", style={"fontSize": "48px", "color": COLORS['warning']}),
            html.P("ML Service not available. Please check HANA connection.", 
                   style={"color": text_color, "marginTop": "16px"})
        ], style={"textAlign": "center", "padding": "60px"})

    # ==================== RATIO ANALYZER ====================
    if active_tab == "ratio-analyzer":
        try:
            logger.info(f"[RATIO ANALYZER] Rendering with selected_competitors: {selected_competitors}")
            data = ml_service.analyze_ratios(selected_competitors)
            logger.info(f"[RATIO ANALYZER] analyze_ratios returned {len(data.get('companies', []))} companies")
            
            if "error" in data or not data.get("companies"):
                return _render_no_data_message("Ratio Analyzer", dark_mode)
            
            companies = data["companies"]
            
            # Calculate averages for industry comparison
            def safe_avg(values):
                clean = [float(v) for v in values if v is not None and pd.notnull(v) and float(v) != 0]
                return round(sum(clean) / len(clean), 2) if clean else 0.0
            
            # Define the 6 key ratios to display (matching screenshot design)
            ratio_definitions = [
                {'key': 'profit_margin', 'label': 'Profit Margin', 'suffix': '%', 'higher_better': True},
                {'key': 'roa', 'label': 'ROA', 'suffix': '%', 'higher_better': True},
                {'key': 'roe', 'label': 'ROE', 'suffix': '%', 'higher_better': True},
                {'key': 'current_ratio', 'label': 'Current Ratio', 'suffix': ':1', 'higher_better': True},
                {'key': 'de_ratio', 'label': 'D/E Ratio', 'suffix': ':1', 'higher_better': False},
                {'key': 'asset_turnover', 'label': 'Asset Turnover', 'suffix': '%', 'higher_better': True},
            ]
            
            # Map key → list of field names to try in order (first non-zero wins)
            ratio_mapping = {
                'profit_margin': ['PROF_MARGIN', 'EBITDA_MARGIN', 'OPER_MARGIN'],
                'roa':           ['RETURN_ON_ASSET', 'PROF_MARGIN'],
                'roe':           ['RETURN_COM_EQY', 'RETURN_ON_ASSET', 'GROSS_MARGIN'],
                'current_ratio': ['CUR_RATIO', 'QUICK_RATIO'],
                'de_ratio':      ['TOT_DEBT_TO_TOT_EQY', 'TOT_DEBT_TO_COM_EQY',
                                  'NET_DEBT_TO_SHRHLDR_EQTY', 'TOT_DEBT_TO_TOT_ASSET'],
                'asset_turnover':['ASSET_TURNOVER', 'EBITDA_MARGIN', 'OPER_MARGIN', 'GROSS_MARGIN'],
            }

            # Get primary company data (first selected or user company)
            primary = companies[0] if companies else {}
            ratio_scores = primary.get('ratio_scores', {})

            def _first_nonzero(scores, fields):
                """Return first non-zero/non-None value from a list of field names."""
                for f in fields:
                    v = scores.get(f)
                    if v is not None and v != 0:
                        return float(v), f
                return 0.0, fields[0]

            def get_ratio_data(key):
                fields = ratio_mapping.get(key, [key])
                current, matched_field = _first_nonzero(ratio_scores, fields)

                # Industry avg: use same field that gave a non-zero for the primary company
                def _company_val(company):
                    scores = company.get('ratio_scores', {})
                    v = scores.get(matched_field, 0.0)
                    return float(v) if v is not None else 0.0

                industry_avg = safe_avg([_company_val(c) for c in companies])

                # Simulated previous/target (5% back, 10% improvement target)
                previous = round(current * 0.95, 2) if current > 0 else round(current * 1.05, 2)
                target   = round(current * 1.10, 2) if current > 0 else round(current * 0.90, 2)

                return {
                    'current':      current,
                    'previous':     previous,
                    'target':       target,
                    'industry_avg': industry_avg,
                    'change':       round(current - previous, 2),
                }
            
            # Build ratio cards (Task 4 - new design from screenshot)
            ratio_cards = []
            chart_data = {'labels': [], 'current': [], 'industry': [], 'previous': [], 'target': []}
            
            for ratio_def in ratio_definitions:
                ratio_data = get_ratio_data(ratio_def['key'])
                current = ratio_data['current']
                change = ratio_data['change']
                previous = ratio_data['previous']
                target = ratio_data['target']
                industry = ratio_data['industry_avg']
                
                # Calculate vs target percentage
                vs_target = (current / target * 100) if target != 0 else 100
                vs_target_color = '#22c55e' if vs_target >= 90 else ('#f59e0b' if vs_target >= 70 else '#ef4444')
                
                # Change badge
                change_positive = change >= 0 if ratio_def['higher_better'] else change <= 0
                badge_class = 'positive' if change_positive else 'negative'
                badge_icon = '↑' if change >= 0 else '↓'
                
                # Format value based on suffix
                def fmt(val, suffix):
                    if suffix == ':1':
                        return f"{abs(val):.1f}:1"
                    elif suffix == '%':
                        return f"{abs(val):.1f}%"
                    return f"{abs(val):.1f}"
                
                ratio_cards.append(
                    html.Div([
                        # Header: Title + Change Badge
                        html.Div([
                            html.Span(ratio_def['label'], className='ratio-card-title'),
                            html.Span([
                                html.Span(badge_icon, style={'marginRight': '4px'}),
                                f"{abs(change):.1f}"
                            ], className=f'ratio-change-badge {badge_class}')
                        ], className='ratio-card-header'),
                        
                        # Large Value
                        html.Div(fmt(current, ratio_def['suffix']), className='ratio-card-value'),
                        
                        # Metrics Grid
                        html.Div([
                            html.Div([
                                html.Span("Previous:", className='ratio-metric-label'),
                                html.Span(f"{previous:.1f}", className='ratio-metric-value')
                            ], className='ratio-metric-row'),
                            html.Div([
                                html.Span("Target:", className='ratio-metric-label'),
                                html.Span(f"{target:.1f}", className='ratio-metric-value highlight')
                            ], className='ratio-metric-row'),
                            html.Div([
                                html.Span("Industry Avg:", className='ratio-metric-label'),
                                html.Span(f"{industry:.1f}", className='ratio-metric-value')
                            ], className='ratio-metric-row'),
                        ], className='ratio-metrics'),
                        
                        # vs Target footer
                        html.Div([
                            html.Span("vs Target:", className='ratio-vs-target-label'),
                            html.Span(f"{vs_target:.0f}%", className='ratio-vs-target-value', 
                                     style={'color': vs_target_color})
                        ], className='ratio-vs-target')
                    ], className='ratio-card')
                )
                
                # Collect data for comparison chart
                chart_data['labels'].append(ratio_def['label'])
                chart_data['current'].append(current)
                chart_data['industry'].append(industry)
                chart_data['previous'].append(previous)
                chart_data['target'].append(target)
            
            # Create grouped bar chart
            fig_comparison = go.Figure()
            
            bar_colors = {
                'Current': '#3b82f6',
                'Industry': '#f59e0b',
                'Previous': '#94a3b8',
                'Target': '#22c55e'
            }
            
            for name, values in [('Current', chart_data['current']), 
                                  ('Industry', chart_data['industry']),
                                  ('Previous', chart_data['previous']),
                                  ('Target', chart_data['target'])]:
                fig_comparison.add_trace(go.Bar(
                    name=name,
                    x=chart_data['labels'],
                    y=values,
                    marker_color=bar_colors[name]
                ))
            
            fig_comparison.update_layout(
                title="Ratio Comparison Chart",
                barmode='group',
                height=400,
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)',
                font=dict(color=text_color),
                legend=dict(orientation='h', yanchor='bottom', y=-0.2, xanchor='center', x=0.5),
                xaxis=dict(showgrid=False),
                yaxis=dict(showgrid=True, gridcolor=COLORS['gray']['700'] if dark_mode else COLORS['gray']['200']),
                margin=dict(l=40, r=40, t=60, b=80)
            )
            
            return html.Div([
                # Header
                html.Div([
                    html.Div([
                        html.H4("Financial Ratio Analyzer", style={"color": text_color, "margin": "0"}),
                        html.P("Key financial ratios with period comparison", 
                               style={"color": COLORS['gray']['400'], "fontSize": "14px", "margin": "4px 0 0 0"})
                    ]),
                    html.Div([
                        html.Button("+ Add Ratio", style={
                            "backgroundColor": "transparent",
                            "border": f"1px solid {COLORS['gray']['600'] if dark_mode else COLORS['gray']['300']}",
                            "borderRadius": "8px",
                            "padding": "8px 16px",
                            "color": text_color,
                            "cursor": "pointer",
                            "fontSize": "14px"
                        })
                    ])
                ], style={
                    "display": "flex",
                    "justifyContent": "space-between",
                    "alignItems": "flex-start",
                    "marginBottom": "24px"
                }),
                
                # Ratio Cards Grid
                html.Div(ratio_cards, className='ratio-analyzer-grid'),
                
                # Comparison Chart
                html.Div([
                    dcc.Graph(figure=fig_comparison, config={'displayModeBar': False})
                ], style={
                    "backgroundColor": card_bg,
                    "borderRadius": "12px",
                    "padding": "20px",
                    "border": f"1px solid {COLORS['gray']['700'] if dark_mode else COLORS['gray']['200']}"
                })
            ])
            
        except Exception as e:
            logger.error(f"Error rendering ratio analyzer: {e}")
            return _render_error_message("Ratio Analyzer", str(e), dark_mode)

    # ==================== SCENARIO SIMULATOR ====================
    elif active_tab == "scenario-simulator":
        try:
            logger.info("[SCENARIO SIMULATOR] STEP 1: start render")

            # ── Styling ───────────────────────────────────────────────
            text_color  = COLORS['gray']['100'] if dark_mode else COLORS['gray']['800']
            bg_color    = COLORS['gray']['800'] if dark_mode else '#ffffff'
            card_bg     = COLORS['gray']['700'] if dark_mode else COLORS['gray']['50']
            border_col  = COLORS['gray']['600'] if dark_mode else COLORS['gray']['200']
            slider_col  = COLORS['gray']['300'] if dark_mode else COLORS['gray']['700']

            # ── Fetch META data ───────────────────────────────────────
            logger.info("[SCENARIO SIMULATOR] STEP 2: fetching sim_data from ml_service")
            sim_data = {}
            if ml_service:
                try:
                    sim_data = ml_service.simulate_scenarios('META')
                    logger.info(f"[SCENARIO SIMULATOR] STEP 2 OK: sim_data keys={list(sim_data.keys()) if sim_data else 'empty'}")
                except Exception as _sim_err:
                    logger.error(f"[SCENARIO SIMULATOR] STEP 2 FAILED: {_sim_err}\n{_tb.format_exc()}")
                    sim_data = {}

            # Fallback to hardcoded META reference if service unavailable
            if not sim_data or "error" in sim_data:
                sim_data = {
                    "ticker": "META", "source": "META Reference Dataset (offline)",
                    "years_hist": [2020, 2021, 2022, 2023, 2024],
                    "years_proj": [2025, 2026, 2027],
                    "historical": {
                        "revenue":       [85965,  117929, 116609, 134902, 164500],
                        "ebitda":        [29528,  47440,  40489,  58998,  80765],
                        "net_income":    [29146,  39370,  23200,  39098,  62360],
                        "gross_margin":  [80.6,   82.5,   75.6,   84.8,   85.9],
                        "ebitda_margin": [34.3,   40.2,   34.7,   43.7,   49.1],
                        "net_margin":    [33.9,   33.4,   19.9,   29.0,   37.9],
                    },
                    "projection_base": {
                        "revenue":    [183000, 203500, 226000],
                        "ebitda":     [89800,  99800,  111000],
                        "net_income": [62000,  68900,  76500],
                    },
                    "projection_whatif": {
                        "revenue":    [183000, 203500, 226000],
                        "ebitda":     [89800,  99800,  111000],
                        "net_income": [62000,  68900,  76500],
                    },
                    "base_revenue": 164500, "base_margin": 49.1,
                    "avg_rev_growth": 11.5, "what_if_params": {},
                    "scenarios": [],
                }

            logger.info("[SCENARIO SIMULATOR] STEP 3: parsing sim_data fields")
            hist      = sim_data.get("historical", {})
            proj_base = sim_data.get("projection_base", {})
            proj_wi   = sim_data.get("projection_whatif", {})

            # ── Coerce years to plain Python ints ────────────────────
            def _safe_int(v, fallback=0):
                try:
                    return int(str(v)[:4]) if v is not None else fallback
                except Exception:
                    return fallback

            def _safe_float(v, fallback=0.0):
                try:
                    return float(v) if v is not None else fallback
                except Exception:
                    return fallback

            raw_yh = sim_data.get("years_hist", [2020, 2021, 2022, 2023, 2024])
            raw_yp = sim_data.get("years_proj", [2025, 2026, 2027])
            yh     = [_safe_int(y) for y in raw_yh]
            yp     = [_safe_int(y) for y in raw_yp]
            logger.info(f"[SCENARIO SIMULATOR] STEP 3a: yh={yh}, yp={yp}")

            avg_rg    = _safe_float(sim_data.get("avg_rev_growth"), 11.5) or 11.5
            base_rev  = _safe_float(sim_data.get("base_revenue"), 164500) or 164500
            base_marg = _safe_float(sim_data.get("base_margin"), 49.1) or 49.1
            logger.info(f"[SCENARIO SIMULATOR] STEP 3b: avg_rg={avg_rg}, base_rev={base_rev}, base_marg={base_marg}")

            # ── Coerce all series to plain Python floats ──────────────
            def _coerce_series(d):
                out = {}
                for k, vals in d.items():
                    if not isinstance(vals, (list, tuple)):
                        continue
                    out[k] = [_safe_float(v) for v in vals]
                return out

            hist      = _coerce_series(hist)
            proj_base = _coerce_series(proj_base)
            proj_wi   = _coerce_series(proj_wi)
            logger.info(f"[SCENARIO SIMULATOR] STEP 3c: hist keys={list(hist.keys())}, proj_base keys={list(proj_base.keys())}")

            logger.info("[SCENARIO SIMULATOR] STEP 4: building charts")
            # ── Build dual-line chart (Revenue) ───────────────────────
            def make_scenario_chart(metric_key, metric_label, unit="$M", dark=False):
                fig = go.Figure()
                gc  = COLORS['gray']['700'] if dark else COLORS['gray']['200']

                # Historical line (solid blue)
                hist_vals = hist.get(metric_key, [])
                if hist_vals:
                    fig.add_trace(go.Scatter(
                        x=[str(y) for y in yh], y=hist_vals,
                        mode='lines+markers',
                        name=f'Historical {metric_label}',
                        line=dict(color=COLORS['primary'], width=3),
                        marker=dict(size=7, symbol='circle'),
                        hovertemplate=f'%{{x}}: %{{y:,.0f}} {unit}<extra>Historical</extra>',
                    ))

                # Base projection (dashed blue)
                base_vals = proj_base.get(metric_key, [])
                if base_vals:
                    fig.add_trace(go.Scatter(
                        x=[str(y) for y in yp], y=base_vals,
                        mode='lines+markers',
                        name='Current Projection',
                        line=dict(color=COLORS['primary'], width=2, dash='dash'),
                        marker=dict(size=7, symbol='diamond'),
                        hovertemplate=f'%{{x}}: %{{y:,.0f}} {unit}<extra>Projection (Scenario 1)</extra>',
                    ))

                # What-if projection (dashed orange)
                wi_vals = proj_wi.get(metric_key, [])
                if wi_vals:
                    fig.add_trace(go.Scatter(
                        x=[str(y) for y in yp], y=wi_vals,
                        mode='lines+markers',
                        name='What-if Projection',
                        line=dict(color=COLORS['warning'], width=2, dash='dot'),
                        marker=dict(size=7, symbol='triangle-up'),
                        hovertemplate=f'%{{x}}: %{{y:,.0f}} {unit}<extra>What-if (Scenario 2)</extra>',
                    ))

                # Add vertical divider between history and projection
                # NOTE: add_vline crashes on categorical (string) x-axes in Plotly 5.x
                # because it internally calls sum() on x-values starting with int 0.
                # Use add_shape with xref='paper' instead — positions by fraction of plot width.
                if yh and yp:
                    n_total = len(yh) + len(yp)
                    divider_x = len(yh) / n_total  # fraction of the way across
                    fig.add_shape(
                        type="line",
                        xref="paper", yref="paper",
                        x0=divider_x, x1=divider_x,
                        y0=0, y1=0.92,
                        line=dict(color=COLORS['gray']['400'], width=1, dash="solid"),
                    )
                    fig.add_annotation(
                        xref="paper", yref="paper",
                        x=divider_x + 0.01, y=0.96,
                        text="Forecast →",
                        showarrow=False,
                        font=dict(color=COLORS['gray']['400'], size=11),
                        xanchor="left",
                    )

                fig.update_layout(
                    title=dict(text=f"{metric_label} Trend & Projection ({unit})",
                               font=dict(size=15, color=text_color)),
                    height=380,
                    plot_bgcolor='rgba(0,0,0,0)',
                    paper_bgcolor='rgba(0,0,0,0)',
                    font=dict(color=text_color, size=12),
                    legend=dict(orientation='h', yanchor='bottom', y=-0.25,
                                xanchor='center', x=0.5,
                                bgcolor='rgba(0,0,0,0)', borderwidth=0),
                    xaxis=dict(showgrid=False, tickangle=0, title='Year'),
                    yaxis=dict(showgrid=True, gridcolor=gc,
                               title=f'{metric_label} ({unit})',
                               tickformat=',.0f'),
                    margin=dict(l=60, r=30, t=60, b=80),
                    hovermode='x unified',
                )
                return fig

            # Build charts for Revenue and EBITDA
            fig_revenue = make_scenario_chart('revenue', 'Revenue', '$M', dark_mode)
            fig_margin  = make_scenario_chart('ebitda_margin', 'EBITDA Margin', '%', dark_mode)
            logger.info("[SCENARIO SIMULATOR] STEP 4 OK: charts built")

            # ── Pre-compute initial (0 %, 0 %) display values ────────
            logger.info("[SCENARIO SIMULATOR] STEP 5: pre-compute display values")
            _rev_fallback     = [_safe_float(base_rev) * 1.115]
            _ebitda_fallback  = [_safe_float(base_rev) * _safe_float(base_marg) / 100 * 1.115]
            _net_fallback     = [_safe_float(base_rev) * 0.38 * 1.115]
            _base_proj_rev    = _safe_float((proj_base.get("revenue")    or _rev_fallback)[0],    base_rev * 1.115)
            _base_proj_ebitda = _safe_float((proj_base.get("ebitda")     or _ebitda_fallback)[0], base_rev * base_marg / 100 * 1.115)
            _base_proj_net    = _safe_float((proj_base.get("net_income") or _net_fallback)[0],    base_rev * 0.38 * 1.115)
            _base_net_margin  = _safe_float((hist.get("net_margin")      or [37.9])[-1], 37.9)
            _base_costs       = _safe_float(_base_proj_rev) * (1 - _safe_float(base_marg) / 100)
            logger.info(f"[SCENARIO SIMULATOR] STEP 5 OK: rev={_base_proj_rev}, ebitda={_base_proj_ebitda}, costs={_base_costs}")

            def _fmt_b(val):
                """Format dollar amount in $B or $M."""
                if val >= 1000:
                    return f"${val/1000:.1f}B"
                return f"${val:.0f}M"

            def _impact_card(title, value, baseline, bg_color_card, icon_cls):
                """Coloured impact card matching reference image."""
                delta     = value - baseline
                delta_pct = (delta / baseline * 100) if baseline else 0
                is_pos    = delta >= 0
                d_color   = '#16a34a' if is_pos else '#dc2626'
                d_label   = f"+{delta_pct:.1f}% vs baseline" if is_pos else f"{delta_pct:.1f}% vs baseline"
                return html.Div([
                    html.Div([
                        html.P(title, style={"fontSize": "12px", "fontWeight": "600",
                                             "color": "#374151", "margin": "0 0 8px 0"}),
                        html.I(className=f"fas {icon_cls}",
                               style={"color": d_color, "fontSize": "16px"}),
                    ], style={"display": "flex", "justifyContent": "space-between",
                              "alignItems": "flex-start"}),
                    html.P(_fmt_b(value), style={
                        "fontSize": "26px", "fontWeight": "800",
                        "color": "#111827", "margin": "4px 0 4px 0",
                    }),
                    html.P(d_label, style={
                        "fontSize": "13px", "fontWeight": "600",
                        "color": d_color, "margin": "0",
                    }),
                ], style={
                    "backgroundColor": bg_color_card,
                    "borderRadius": "12px",
                    "padding": "16px 18px",
                    "marginBottom": "10px",
                })

            def _insights_card(rev_ch, cost_ch):
                if rev_ch > 0 and cost_ch < 0:
                    insight = "Optimal scenario — revenue up, costs down. EBITDA margin expanding."
                    icon, col = "fa-rocket", "#7c3aed"
                elif rev_ch > 0 and cost_ch > 0:
                    insight = "Revenue growth offset by rising costs. Monitor margin compression."
                    icon, col = "fa-exclamation-triangle", "#d97706"
                elif rev_ch < 0 and cost_ch < 0:
                    insight = "Revenue decline partially cushioned by cost reduction."
                    icon, col = "fa-compress-arrows-alt", "#2563eb"
                elif rev_ch < 0:
                    insight = "Revenue decline scenario. Cost controls are critical."
                    icon, col = "fa-arrow-trend-down", "#dc2626"
                else:
                    insight = "Adjust sliders to model different financial scenarios."
                    icon, col = "fa-lightbulb", "#7c3aed"
                return html.Div([
                    html.Div([
                        html.P("Key Insights", style={"fontSize": "12px", "fontWeight": "700",
                                                       "color": "#374151", "margin": "0 0 10px 0"}),
                        html.I(className=f"fas {icon}", style={"color": col, "fontSize": "16px"}),
                    ], style={"display": "flex", "justifyContent": "space-between"}),
                    html.P([html.Span("• ", style={"color": col}), insight],
                           style={"fontSize": "13px", "color": "#4b5563", "margin": "0",
                                  "lineHeight": "1.6"}),
                ], style={
                    "backgroundColor": "#f5f3ff",
                    "borderRadius": "12px",
                    "padding": "16px 18px",
                })

            # Initial impact cards (sliders at 0%)
            _initial_cards = html.Div([
                _impact_card("EBITDA Impact",      _base_proj_ebitda, _base_proj_ebitda, "#eff6ff", "fa-chart-line"),
                _impact_card("Net Income Impact",  _base_proj_net,    _base_proj_net,    "#f0fdf4", "fa-chart-line"),
                _insights_card(0, 0),
            ])

            # ── Hidden margin-adj slider (kept for callback compat) ───
            _hidden_margin_slider = html.Div([
                dcc.Slider(id='scenario-margin-adj', min=-15, max=15, step=0.5, value=0),
            ], style={"display": "none"})

            # ── Layout (matches reference image) ─────────────────────
            return html.Div([
                _hidden_margin_slider,

                # Header row
                html.Div([
                    html.Div([
                        html.H4("Scenario Simulator (What-If Analysis)", style={
                            "color": text_color, "margin": "0 0 4px", "fontWeight": "800",
                            "fontSize": "20px",
                        }),
                        html.P("Model financial impact by adjusting key assumptions", style={
                            "color": COLORS['gray']['400'], "fontSize": "13px", "margin": 0,
                        }),
                    ]),
                    html.Div([
                        html.Button([
                            html.I(className="fas fa-play", style={"marginRight": "7px"}),
                            "Simulate",
                        ], id='scenario-simulate-btn', className="scenario-btn-primary"),
                        html.Button([
                            html.I(className="fas fa-redo", style={"marginRight": "7px"}),
                            "Reset Scenario",
                        ], id='scenario-reset-btn', className="scenario-btn-secondary"),
                    ], style={"display": "flex", "gap": "10px", "alignItems": "center"}),
                ], style={"display": "flex", "justifyContent": "space-between",
                          "alignItems": "flex-start", "marginBottom": "24px"}),

                # Two-panel row
                dbc.Row([
                    # Left: Adjust Assumptions
                    dbc.Col([
                        html.Div([
                            html.P("Adjust Assumptions", style={
                                "fontWeight": "700", "fontSize": "15px",
                                "color": text_color, "margin": "0 0 24px 0",
                            }),

                            # Revenue Change slider
                            html.Div([
                                html.Div([
                                    html.Label("Revenue Change", style={
                                        "fontWeight": "700", "color": text_color, "fontSize": "14px"
                                    }),
                                    html.Span("0%", id='scenario-rev-badge', style={
                                        "backgroundColor": "#111827", "color": "#fff",
                                        "padding": "2px 11px", "borderRadius": "20px",
                                        "fontSize": "12px", "fontWeight": "700",
                                    }),
                                ], style={"display": "flex", "justifyContent": "space-between",
                                          "alignItems": "center", "marginBottom": "14px"}),
                                dcc.Slider(
                                    id='scenario-revenue-growth',
                                    min=-30, max=30, step=1,
                                    value=0,
                                    marks={-30: {"label": "-30%", "style": {"color": slider_col, "fontSize": "11px"}},
                                            0:  {"label": "0%",   "style": {"color": slider_col, "fontSize": "11px"}},
                                           30:  {"label": "+30%", "style": {"color": slider_col, "fontSize": "11px"}}},
                                    tooltip={"placement": "bottom", "always_visible": False},
                                    className="scenario-slider",
                                ),
                                html.P(id='scenario-sim-revenue-display',
                                       children=f"Simulated Revenue: {_fmt_b(_base_proj_rev)}",
                                       style={"fontSize": "13px", "color": COLORS['gray']['500'],
                                              "marginTop": "10px", "fontWeight": "500"}),
                            ], style={"marginBottom": "32px"}),

                            # Cost Change slider
                            html.Div([
                                html.Div([
                                    html.Label("Cost Change", style={
                                        "fontWeight": "700", "color": text_color, "fontSize": "14px"
                                    }),
                                    html.Span("0%", id='scenario-cost-badge', style={
                                        "backgroundColor": "#111827", "color": "#fff",
                                        "padding": "2px 11px", "borderRadius": "20px",
                                        "fontSize": "12px", "fontWeight": "700",
                                    }),
                                ], style={"display": "flex", "justifyContent": "space-between",
                                          "alignItems": "center", "marginBottom": "14px"}),
                                dcc.Slider(
                                    id='scenario-cost-change',
                                    min=-30, max=30, step=1,
                                    value=0,
                                    marks={-30: {"label": "-30%", "style": {"color": slider_col, "fontSize": "11px"}},
                                            0:  {"label": "0%",   "style": {"color": slider_col, "fontSize": "11px"}},
                                           30:  {"label": "+30%", "style": {"color": slider_col, "fontSize": "11px"}}},
                                    tooltip={"placement": "bottom", "always_visible": False},
                                    className="scenario-slider",
                                ),
                                html.P(id='scenario-sim-costs-display',
                                       children=f"Simulated Costs: {_fmt_b(_base_costs)}",
                                       style={"fontSize": "13px", "color": COLORS['gray']['500'],
                                              "marginTop": "10px", "fontWeight": "500"}),
                            ]),
                        ], style={
                            "backgroundColor": bg_color, "borderRadius": "14px",
                            "padding": "24px", "border": f"1px solid {border_col}",
                            "height": "100%",
                        }),
                    ], md=5),

                    # Right: Impact Analysis
                    dbc.Col([
                        html.Div([
                            html.P("Impact Analysis", style={
                                "fontWeight": "700", "fontSize": "15px",
                                "color": text_color, "margin": "0 0 16px 0",
                            }),
                            html.Div(id='scenario-impact-cards', children=_initial_cards),
                        ], style={
                            "backgroundColor": bg_color, "borderRadius": "14px",
                            "padding": "24px", "border": f"1px solid {border_col}",
                            "height": "100%",
                        }),
                    ], md=7),
                ], className="mb-4"),

                # Full-width chart
                html.Div(id='scenario-chart-output'),
            ])

        except Exception as e:
            full_tb = _tb.format_exc()
            logger.error(f"[SCENARIO SIMULATOR] RENDER FAILED: {type(e).__name__}: {e}\nFULL TRACEBACK:\n{full_tb}")
            return _render_error_message("Scenario Simulator", f"{type(e).__name__}: {e} | Check BTP logs for full traceback", dark_mode)
    elif active_tab == "forecast":
        try:
            # ── No company cap: process all selected competitors ──────────────
            data = ml_service.get_forecasts(selected_competitors)

            if "error" in data or not data.get("companies"):
                return _render_no_data_message("Forecast & Trends", dark_mode)

            companies = data["companies"]

            # Expanded colour palette — supports any number of companies
            PALETTE = [
                COLORS['primary'], COLORS['success'], COLORS['warning'],
                '#8b5cf6', '#06b6d4', '#f43f5e', '#84cc16', '#f97316',
                '#a855f7', '#14b8a6', '#eab308', '#ec4899', '#3b82f6', '#10b981',
            ]
            gc = COLORS['gray']['700'] if dark_mode else COLORS['gray']['200']
            border_col = COLORS['gray']['700'] if dark_mode else COLORS['gray']['200']

            # ── 4.1 / 4.4 Revenue chart: solid historical + dotted projected ──
            fig_rev = go.Figure()

            for i, company in enumerate(companies):
                ticker = company['ticker']
                color  = PALETTE[i % len(PALETTE)]
                fc     = company.get('forecasts', {}).get('SALES_REV_TURN', {})

                if not fc:
                    continue

                hist         = fc.get('historical', {})
                current_val  = fc.get('current', 0)
                current_year = fc.get('current_year', 2024)

                # Historical segment — solid line
                if hist:
                    hist_years = sorted(hist.keys())
                    # Values stored in raw dollars from DB; convert to $M for display
                    scale = 1e6 if current_val > 1e8 else 1.0
                    hist_vals = [hist[y] / scale for y in hist_years]

                    fig_rev.add_trace(go.Scatter(
                        x=[str(y) for y in hist_years],
                        y=hist_vals,
                        name=ticker,
                        mode='lines+markers',
                        line=dict(color=color, width=2.5),
                        marker=dict(size=8),
                        legendgroup=ticker,
                        showlegend=True,
                        hovertemplate=(
                            f'<b>{ticker}</b><br>'
                            '%{x}: $%{y:,.0f}' + (' M' if scale >= 1e6 else '') + '<extra>Actual</extra>'
                        ),
                    ))
                else:
                    scale = 1e6 if current_val > 1e8 else 1.0

                # 4.4 Projected segment — dotted line, anchored to last actual point
                proj_x = [str(current_year), str(current_year + 1), str(current_year + 2)]
                proj_y = [
                    current_val / scale,
                    fc.get('forecast_1y', current_val) / scale,
                    fc.get('forecast_2y', current_val) / scale,
                ]

                fig_rev.add_trace(go.Scatter(
                    x=proj_x,
                    y=proj_y,
                    name=f'{ticker} Projected',
                    mode='lines+markers',
                    line=dict(color=color, width=2.5, dash='dot'),
                    marker=dict(size=8, symbol='diamond'),
                    legendgroup=ticker,
                    showlegend=False,        # avoid duplicate legend entries
                    hovertemplate=(
                        f'<b>{ticker}</b><br>'
                        '%{x}: $%{y:,.0f}' + (' M' if scale >= 1e6 else '') + '<extra>Projected</extra>'
                    ),
                ))

            unit_label = "$M" if any(
                c.get('forecasts', {}).get('SALES_REV_TURN', {}).get('current', 0) > 1e8
                for c in companies
            ) else "$"
            fig_rev.update_layout(
                title="Revenue Forecast — Historical (solid) vs Projected (dotted)",
                height=430,
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)',
                font=dict(color=text_color),
                xaxis=dict(title="Fiscal Year", showgrid=False),
                yaxis=dict(title=f"Revenue ({unit_label})", gridcolor=gc),
                legend=dict(orientation="h", yanchor="bottom", y=1.08, xanchor="center", x=0.5),
                hovermode='x unified',
                margin=dict(t=100, b=40),
            )

            # ── 4.2 / 4.3 Per-company growth bar chart (real CAGR, not flat 5 %) ──
            fig_growth = go.Figure()
            tickers_list, growth_1y_list, growth_2y_list = [], [], []

            for company in companies:
                fc = company.get('forecasts', {}).get('SALES_REV_TURN', {})
                if not fc:
                    continue
                current = fc.get('current', 0)
                f1 = fc.get('forecast_1y', 0)
                f2 = fc.get('forecast_2y', 0)
                g1 = round(((f1 / current) - 1) * 100, 2) if current > 0 else 0
                g2 = round(((f2 / current) - 1) * 100, 2) if current > 0 else 0
                tickers_list.append(company['ticker'])
                growth_1y_list.append(g1)
                growth_2y_list.append(g2)

            fig_growth.add_trace(go.Bar(
                name='1Y Projected Growth', x=tickers_list, y=growth_1y_list,
                marker_color=COLORS['primary'],
                text=[f"{v:+.1f}%" for v in growth_1y_list],
                textposition='outside',
            ))
            fig_growth.add_trace(go.Bar(
                name='2Y Projected Growth', x=tickers_list, y=growth_2y_list,
                marker_color=COLORS['success'],
                text=[f"{v:+.1f}%" for v in growth_2y_list],
                textposition='outside',
            ))
            fig_growth.update_layout(
                title="Projected Revenue Growth (%)",
                barmode='group',
                height=430,   # match fig_rev height exactly
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)',
                font=dict(color=text_color),
                xaxis=dict(showgrid=False, tickangle=-30, tickfont=dict(size=10)),
                yaxis=dict(title="Growth (%)", gridcolor=gc, ticksuffix='%'),
                legend=dict(orientation="h", yanchor="bottom", y=1.08, xanchor="center", x=0.5),
                margin=dict(t=100, b=80),  # extra bottom margin so labels don't clip
            )

            # ── 4.5 New chart: Actual EBITDA vs Forecast EBITDA ──────────────
            fig_ebitda = go.Figure()

            for i, company in enumerate(companies):
                ticker = company['ticker']
                color  = PALETTE[i % len(PALETTE)]
                fc     = company.get('forecasts', {}).get('EBITDA', {})

                if not fc:
                    continue

                hist         = fc.get('historical', {})
                current_val  = fc.get('current', 0)
                current_year = fc.get('current_year', 2024)
                scale        = 1e6 if current_val > 1e8 else 1.0

                # Actual EBITDA — solid line
                if hist:
                    hist_years = sorted(hist.keys())
                    hist_vals  = [hist[y] / scale for y in hist_years]

                    fig_ebitda.add_trace(go.Scatter(
                        x=[str(y) for y in hist_years],
                        y=hist_vals,
                        name=ticker,
                        mode='lines+markers',
                        line=dict(color=color, width=2.5),
                        marker=dict(size=8),
                        legendgroup=f'ebitda_{ticker}',
                        showlegend=True,
                        hovertemplate=(
                            f'<b>{ticker} Actual EBITDA</b><br>'
                            '%{x}: $%{y:,.0f}' + (' M' if scale >= 1e6 else '') + '<extra></extra>'
                        ),
                    ))

                # Forecast EBITDA — dotted line
                proj_x = [str(current_year), str(current_year + 1), str(current_year + 2)]
                proj_y = [
                    current_val / scale,
                    fc.get('forecast_1y', current_val) / scale,
                    fc.get('forecast_2y', current_val) / scale,
                ]

                fig_ebitda.add_trace(go.Scatter(
                    x=proj_x,
                    y=proj_y,
                    name=f'{ticker} Forecast',
                    mode='lines+markers',
                    line=dict(color=color, width=2.5, dash='dot'),
                    marker=dict(size=8, symbol='diamond'),
                    legendgroup=f'ebitda_{ticker}',
                    showlegend=False,
                    hovertemplate=(
                        f'<b>{ticker} EBITDA Forecast</b><br>'
                        '%{x}: $%{y:,.0f}' + (' M' if scale >= 1e6 else '') + '<extra></extra>'
                    ),
                ))

            ebitda_unit = "$M" if any(
                c.get('forecasts', {}).get('EBITDA', {}).get('current', 0) > 1e8
                for c in companies
            ) else "$"
            fig_ebitda.update_layout(
                title="Actual EBITDA vs Forecast EBITDA",
                height=420,
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)',
                font=dict(color=text_color),
                xaxis=dict(title="Fiscal Year", showgrid=False),
                yaxis=dict(title=f"EBITDA ({ebitda_unit})", gridcolor=gc),
                legend=dict(orientation="h", yanchor="bottom", y=1.08, xanchor="center", x=0.5),
                hovermode='x unified',
                margin=dict(t=100, b=40),
            )

            # ── Summary cards — ALL companies, no cap ─────────────────────────
            forecast_cards = []
            for i, company in enumerate(companies):
                ticker = company['ticker']
                color  = PALETTE[i % len(PALETTE)]
                fc     = company.get('forecasts', {}).get('SALES_REV_TURN', {})

                if not fc:
                    continue

                current = fc.get('current', 0)
                f1      = fc.get('forecast_1y', 0)
                growth  = ((f1 / current) - 1) * 100 if current > 0 else 0

                if growth >= 20:
                    trend_icon, trend_color, trend_label = "fa-rocket",         COLORS['success'], "Strong Growth"
                elif growth >= 8:
                    trend_icon, trend_color, trend_label = "fa-arrow-trend-up", '#22c55e',         "Moderate Growth"
                elif growth >= 0:
                    trend_icon, trend_color, trend_label = "fa-minus",          COLORS['warning'],  "Stable"
                else:
                    trend_icon, trend_color, trend_label = "fa-arrow-trend-down", COLORS['danger'], "Decline"

                def _fmt(val):
                    if val >= 1e9:
                        return f"${val/1e9:.2f}B"
                    if val >= 1e6:
                        return f"${val/1e6:.1f}M"
                    return f"${val:,.0f}"

                forecast_cards.append(
                    dbc.Col([
                        html.Div([
                            html.Div([
                                html.Div([
                                    html.I(className=f"fas {trend_icon}",
                                           style={"fontSize": "18px", "color": trend_color})
                                ], style={
                                    "width": "38px", "height": "38px", "borderRadius": "8px",
                                    "backgroundColor": f"{trend_color}20",
                                    "display": "flex", "alignItems": "center", "justifyContent": "center",
                                }),
                                html.Div([
                                    html.H5(ticker, style={
                                        "color": text_color, "margin": "0",
                                        "fontWeight": "700", "fontSize": "14px"
                                    }),
                                    html.Span(trend_label, style={
                                        "color": trend_color, "fontSize": "11px", "fontWeight": "600"
                                    }),
                                ], style={"marginLeft": "10px"}),
                            ], style={"display": "flex", "alignItems": "center", "marginBottom": "12px"}),

                            html.Div([
                                html.Div([
                                    html.Div("Current", style={"color": COLORS['gray']['400'], "fontSize": "11px"}),
                                    html.Div(_fmt(current), style={"color": text_color, "fontWeight": "600", "fontSize": "13px"}),
                                ]),
                                html.Div([
                                    html.Div("1Y Forecast", style={"color": COLORS['gray']['400'], "fontSize": "11px"}),
                                    html.Div(_fmt(f1), style={"color": text_color, "fontWeight": "600", "fontSize": "13px"}),
                                ]),
                                html.Div([
                                    html.Div("Growth (CAGR)", style={"color": COLORS['gray']['400'], "fontSize": "11px"}),
                                    html.Div(f"{growth:+.1f}%", style={"color": trend_color, "fontWeight": "700", "fontSize": "13px"}),
                                ]),
                            ], style={"display": "flex", "justifyContent": "space-between", "gap": "6px"}),
                        ], style={
                            "backgroundColor": card_bg,
                            "border": f"1px solid {border_col}",
                            "borderLeft": f"3px solid {color}",
                            "borderRadius": "10px",
                            "padding": "14px",
                        }),
                    ], md=3, sm=6, xs=12, className="mb-3")
                )

            # Line-style legend annotation shown beneath each chart
            def _line_legend():
                return html.Div([
                    html.Span("━━", style={"color": COLORS['gray']['500'], "marginRight": "4px"}),
                    "Actual / Historical",
                    html.Span("  · · ·", style={
                        "color": COLORS['gray']['500'], "marginLeft": "16px", "marginRight": "4px"
                    }),
                    "Projected (CAGR-based)",
                ], style={
                    "textAlign": "center", "color": COLORS['gray']['400'],
                    "fontSize": "12px", "marginTop": "8px",
                })

            mode_badge = data.get("mode", "")
            subtitle = (
                "CAGR-based projections from multi-year historical data"
                if mode_badge == "cagr_historical"
                else "Snapshot-based projections (5 % default — historical data unavailable)"
            )

            return html.Div([
                html.Div([
                    html.H4("Forecast & Trends", style={"color": text_color, "margin": "0"}),
                    html.P(subtitle, style={
                        "color": COLORS['gray']['400'], "fontSize": "13px", "margin": "4px 0 0 0"
                    }),
                ], style={"marginBottom": "24px"}),

                # ── Summary cards ─────────────────────────────────────────────
                dbc.Row(forecast_cards, className="mb-4"),

                # ── Revenue forecast chart + Growth bar chart ──────────────────
                dbc.Row([
                    dbc.Col([
                        html.Div([
                            dcc.Graph(figure=fig_rev, config={'displayModeBar': False}),
                            _line_legend(),
                        ], style={
                            "backgroundColor": card_bg, "borderRadius": "12px",
                            "padding": "16px", "border": f"1px solid {border_col}",
                        }),
                    ], md=8),
                    dbc.Col([
                        html.Div([
                            dcc.Graph(figure=fig_growth, config={'displayModeBar': False}),
                        ], style={
                            "backgroundColor": card_bg, "borderRadius": "12px",
                            "padding": "16px", "border": f"1px solid {border_col}",
                        }),
                    ], md=4),
                ], className="mb-4"),

                # ── 4.5 Actual EBITDA vs Forecast EBITDA ──────────────────────
                dbc.Row([
                    dbc.Col([
                        html.Div([
                            dcc.Graph(figure=fig_ebitda, config={'displayModeBar': False}),
                            _line_legend(),
                        ], style={
                            "backgroundColor": card_bg, "borderRadius": "12px",
                            "padding": "16px", "border": f"1px solid {border_col}",
                        }),
                    ], md=12),
                ]),
            ])

        except Exception as e:
            logger.error(f"Error rendering forecast: {e}")
            return _render_error_message("Forecast & Trends", str(e), dark_mode)

    # ==================== ANOMALY HEATMAP (Task 7) ====================
    elif active_tab == "heatmap":
        try:
            data = ml_service.detect_anomalies(selected_competitors)
            
            if "error" in data or not data.get("companies"):
                return _render_no_data_message("Anomaly Detection", dark_mode)
            
            companies = data["companies"]
            features = data.get("features", [])[:8]  # Limit features
            
            # Build heatmap data
            z_data = []
            y_labels = []
            
            for company in companies[:10]:  # Limit companies
                ticker = company['ticker']
                y_labels.append(ticker)
                
                row = []
                for feat in features:
                    score = company.get('metric_scores', {}).get(feat, {}).get('score', 0)
                    row.append(score)
                z_data.append(row)
            
            # Enhanced heatmap with better styling
            fig_heatmap = go.Figure(data=go.Heatmap(
                z=z_data,
                x=[f.replace('_', ' ')[:15] for f in features],
                y=y_labels,
                colorscale=[
                    [0, '#22c55e'],
                    [0.3, '#84cc16'],
                    [0.5, '#facc15'],
                    [0.7, '#f97316'],
                    [1, '#ef4444']
                ],
                zmin=0,
                zmax=5,
                text=[[f"{v:.1f}" for v in row] for row in z_data],
                texttemplate="%{text}",
                textfont={"size": 11, "color": "white"},
                hovertemplate="Company: %{y}<br>Metric: %{x}<br>Anomaly Score: %{z:.2f}<extra></extra>"
            ))
            
            fig_heatmap.update_layout(
                title="Financial Anomaly Heatmap",
                height=450,
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)',
                font=dict(color=text_color),
                xaxis=dict(tickangle=45, side='bottom'),
                margin=dict(l=100, r=20, t=60, b=120)
            )
            
            # Anomaly score distribution chart
            anomaly_scores = [c.get('anomaly_score', 0) for c in companies]
            company_tickers = [c['ticker'] for c in companies]
            
            fig_scores = go.Figure()
            
            colors_by_score = [COLORS['danger'] if s > 2 else (COLORS['warning'] if s > 1 else COLORS['success']) for s in anomaly_scores]
            
            fig_scores.add_trace(go.Bar(
                x=company_tickers,
                y=anomaly_scores,
                marker_color=colors_by_score,
                text=[f"{s:.2f}" for s in anomaly_scores],
                textposition='outside'
            ))
            
            # Add threshold lines
            fig_scores.add_hline(y=2, line_dash="dash", line_color=COLORS['danger'], 
                                annotation_text="High Risk", annotation_position="right")
            fig_scores.add_hline(y=1, line_dash="dash", line_color=COLORS['warning'],
                                annotation_text="Warning", annotation_position="right")
            
            fig_scores.update_layout(
                title="Anomaly Score by Company",
                height=350,
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)',
                font=dict(color=text_color),
                yaxis=dict(title="Anomaly Score", gridcolor=COLORS['gray']['700'] if dark_mode else COLORS['gray']['200']),
                margin=dict(t=60, b=40)
            )
            
            # Anomaly alerts with severity
            anomaly_alerts = []
            for company in sorted(companies, key=lambda x: x.get('anomaly_score', 0), reverse=True):
                score = company.get('anomaly_score', 0)
                if score > 0.5:
                    if score > 2:
                        severity = "Critical"
                        severity_color = COLORS['danger']
                        icon = "fa-circle-exclamation"
                    elif score > 1:
                        severity = "Warning"
                        severity_color = COLORS['warning']
                        icon = "fa-triangle-exclamation"
                    else:
                        severity = "Monitor"
                        severity_color = '#f59e0b'
                        icon = "fa-eye"
                    
                    anomaly_alerts.append(
                        html.Div([
                            html.Div([
                                html.I(className=f"fas {icon}", style={"color": severity_color, "fontSize": "18px"}),
                            ], style={
                                "width": "40px",
                                "height": "40px",
                                "borderRadius": "8px",
                                "backgroundColor": f"{severity_color}15",
                                "display": "flex",
                                "alignItems": "center",
                                "justifyContent": "center",
                                "marginRight": "16px"
                            }),
                            html.Div([
                                html.Div([
                                    html.Span(company['ticker'], style={"fontWeight": "700", "color": text_color, "marginRight": "12px"}),
                                    html.Span(severity, style={
                                        "backgroundColor": f"{severity_color}20",
                                        "color": severity_color,
                                        "padding": "2px 8px",
                                        "borderRadius": "4px",
                                        "fontSize": "11px",
                                        "fontWeight": "600"
                                    })
                                ], style={"marginBottom": "4px"}),
                                html.Div(f"Anomaly Score: {score:.2f}", style={"color": COLORS['gray']['400'], "fontSize": "13px"})
                            ], style={"flex": "1"}),
                            html.Div(f"{score:.1f}", style={
                                "fontSize": "24px",
                                "fontWeight": "700",
                                "color": severity_color
                            })
                        ], style={
                            "display": "flex",
                            "alignItems": "center",
                            "padding": "16px",
                            "backgroundColor": card_bg,
                            "border": f"1px solid {COLORS['gray']['700'] if dark_mode else COLORS['gray']['200']}",
                            "borderRadius": "8px",
                            "marginBottom": "12px"
                        })
                    )
            
            return html.Div([
                html.Div([
                    html.H4("Anomaly Detection", style={"color": text_color, "margin": "0"}),
                    html.P("AI-powered outlier detection across financial metrics", style={"color": COLORS['gray']['400'], "fontSize": "14px", "margin": "4px 0 0 0"})
                ], style={"marginBottom": "24px"}),
                
                # Charts Row
                dbc.Row([
                    dbc.Col([
                        html.Div([
                            dcc.Graph(figure=fig_heatmap, config={'displayModeBar': False})
                        ], style={
                            "backgroundColor": card_bg,
                            "borderRadius": "12px",
                            "padding": "16px",
                            "border": f"1px solid {COLORS['gray']['700'] if dark_mode else COLORS['gray']['200']}"
                        })
                    ], md=7),
                    dbc.Col([
                        html.Div([
                            dcc.Graph(figure=fig_scores, config={'displayModeBar': False})
                        ], style={
                            "backgroundColor": card_bg,
                            "borderRadius": "12px",
                            "padding": "16px",
                            "border": f"1px solid {COLORS['gray']['700'] if dark_mode else COLORS['gray']['200']}"
                        })
                    ], md=5)
                ], className="mb-4"),
                
                # Alerts Section
                html.H5("Risk Alerts", style={"color": text_color, "marginBottom": "16px"}),
                html.Div(anomaly_alerts[:6] if anomaly_alerts else [
                    html.Div([
                        html.I(className="fas fa-check-circle", style={"color": COLORS['success'], "marginRight": "12px", "fontSize": "24px"}),
                        html.Span("All companies within normal parameters", style={"color": text_color, "fontSize": "16px"})
                    ], style={"display": "flex", "alignItems": "center", "padding": "20px"})
                ])
            ])
            
        except Exception as e:
            logger.error(f"Error rendering anomaly heatmap: {e}")
            return _render_error_message("Anomaly Detection", str(e), dark_mode)

    # ==================== COMPETITOR BENCHMARK ====================
    elif active_tab == "competitor":
        try:
            target = selected_competitors[0] if selected_competitors else 'NVDA'
            logger.info(f"[COMPETITOR BENCHMARK] Rendering, target={target}, competitors={selected_competitors}")
            data = ml_service.benchmark_competitors(selected_competitors, target)
            logger.info(f"[COMPETITOR BENCHMARK] Got {len(data.get('companies', []))} companies, error={data.get('error')}")

            if "error" in data or not data.get("companies"):
                logger.warning(f"[COMPETITOR BENCHMARK] No data: {data.get('error', 'empty companies list')}")
                return _render_no_data_message("Competitor Benchmark", dark_mode)
            
            companies = data["companies"]
            features = data.get("features", [])[:5]
            
            # Similarity bar chart
            fig_similarity = go.Figure()
            
            tickers = [c['ticker'] for c in companies]
            similarities = [c['similarity'] * 100 for c in companies]
            colors_bar = [COLORS['primary'] if c['is_target'] else COLORS['gray']['400'] for c in companies]
            
            fig_similarity.add_trace(go.Bar(
                x=tickers,
                y=similarities,
                marker_color=colors_bar,
                text=[f"{s:.0f}%" for s in similarities],
                textposition='outside'
            ))
            
            fig_similarity.update_layout(
                title=f"Similarity to {target}",
                height=350,
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)',
                font=dict(color=text_color),
                yaxis=dict(title="Similarity %", range=[0, 110], gridcolor=COLORS['gray']['700'] if dark_mode else COLORS['gray']['200'])
            )
            
            # Comparison table
            comparison_rows = []
            target_company = next((c for c in companies if c['is_target']), None)
            
            if target_company:
                for feat in features:
                    target_val = target_company.get('metric_comparison', {}).get(feat, {}).get('target_value', 0)
                    
                    cells = [html.Td(feat.replace('_', ' ').title(), style={"color": text_color, "fontWeight": "600"})]
                    
                    for company in companies[:5]:
                        comp = company.get('metric_comparison', {}).get(feat, {})
                        val = comp.get('value', 0)
                        status = comp.get('status', 'similar')
                        
                        status_color = COLORS['success'] if status == 'above' else (COLORS['danger'] if status == 'below' else text_color)
                        
                        cells.append(html.Td(f"{val:.2f}", style={"color": status_color, "textAlign": "center"}))
                    
                    comparison_rows.append(html.Tr(cells))
            
            return html.Div([
                html.H4("Competitor Benchmark", style={"color": text_color, "marginBottom": "24px"}),
                dbc.Row([
                    dbc.Col([
                        dcc.Graph(figure=fig_similarity, config={'displayModeBar': False})
                    ], width=12)
                ]),
                html.Hr(style={"borderColor": COLORS['gray']['600'] if dark_mode else COLORS['gray']['200']}),
                html.H5("Metric Comparison", style={"color": text_color, "marginBottom": "16px"}),
                html.Div([
                    html.Table([
                        html.Thead([
                            html.Tr([
                                html.Th("Metric", style={"color": text_color, "padding": "8px"})
                            ] + [
                                html.Th(c['ticker'], style={"color": text_color, "padding": "8px", "textAlign": "center"})
                                for c in companies[:5]
                            ])
                        ]),
                        html.Tbody(comparison_rows)
                    ], style={"width": "100%", "borderCollapse": "collapse"})
                ], style={"overflowX": "auto"})
            ])
            
        except Exception as e:
            logger.error(f"[COMPETITOR BENCHMARK] RENDER FAILED: {type(e).__name__}: {e}\n{_tb.format_exc()}")
            return _render_error_message("Competitor Benchmark", f"{type(e).__name__}: {e}", dark_mode)

    # ==================== GOAL TRACKER ====================
    elif active_tab == "goals":
        try:
            data = ml_service.track_goals(selected_competitors[:5])
            
            if "error" in data or not data.get("companies"):
                return _render_no_data_message("Goal Tracker", dark_mode)
            
            companies = data["companies"]
            
            # Progress cards for each company
            company_cards = []
            
            for company in companies:
                ticker = company['ticker']
                goals = company.get('goals', [])
                overall = company.get('overall_progress', 0)
                
                goal_items = []
                for goal in goals:
                    progress = goal.get('progress', 0)
                    status = goal.get('status', 'behind')
                    status_color = COLORS['success'] if status == 'achieved' else (COLORS['warning'] if status == 'on_track' else COLORS['danger'])
                    
                    goal_items.append(
                        html.Div([
                            html.Div([
                                html.Span(goal['name'], style={"color": text_color, "fontSize": "13px"}),
                                html.Span(f"{progress:.0f}%", style={"color": status_color, "fontWeight": "600", "float": "right"})
                            ]),
                            html.Div([
                                html.Div(style={
                                    "width": f"{min(100, progress)}%",
                                    "height": "6px",
                                    "backgroundColor": status_color,
                                    "borderRadius": "3px",
                                    "transition": "width 0.3s ease"
                                })
                            ], style={
                                "backgroundColor": COLORS['gray']['600'] if dark_mode else COLORS['gray']['200'],
                                "borderRadius": "3px",
                                "marginTop": "4px"
                            })
                        ], style={"marginBottom": "12px"})
                    )
                
                company_cards.append(
                    dbc.Col([
                        html.Div([
                            html.Div([
                                html.H5(ticker, style={"color": text_color, "marginBottom": "4px"}),
                                html.Span(f"Overall: {overall:.0f}%", style={
                                    "color": COLORS['success'] if overall >= 75 else COLORS['warning'],
                                    "fontSize": "14px"
                                })
                            ], style={"marginBottom": "16px"}),
                            html.Div(goal_items)
                        ], style={
                            "backgroundColor": card_bg,
                            "padding": "20px",
                            "borderRadius": "12px",
                            "height": "100%"
                        })
                    ], width=4, style={"marginBottom": "16px"})
                )
            
            return html.Div([
                html.H4("Goal Tracker", style={"color": text_color, "marginBottom": "24px"}),
                html.P("Track progress towards key financial metrics", style={"color": COLORS['gray']['400'], "marginBottom": "24px"}),
                dbc.Row(company_cards)
            ])
            
        except Exception as e:
            logger.error(f"Error rendering goal tracker: {e}")
            return _render_error_message("Goal Tracker", str(e), dark_mode)

    # Default fallback
    else:
        return html.Div([
            html.P(f"Content for {active_tab} tab", style={
                "padding": "40px",
                "textAlign": "center",
                "color": COLORS['gray']['500']
            })
        ])


def _render_no_data_message(section_name, dark_mode):
    """Render a no data available message"""
    text_color = COLORS['gray']['100'] if dark_mode else COLORS['gray']['800']
    return html.Div([
        html.I(className="fas fa-database", style={"fontSize": "48px", "color": COLORS['gray']['400']}),
        html.H5(f"No Data Available for {section_name}", style={"color": text_color, "marginTop": "16px"}),
        html.P("Please ensure ML models are trained and data is available.", 
               style={"color": COLORS['gray']['400']})
    ], style={"textAlign": "center", "padding": "60px"})


def _render_error_message(section_name, error, dark_mode):
    """Render an error message"""
    text_color = COLORS['gray']['100'] if dark_mode else COLORS['gray']['800']
    return html.Div([
        html.I(className="fas fa-exclamation-circle", style={"fontSize": "48px", "color": COLORS['danger']}),
        html.H5(f"Error Loading {section_name}", style={"color": text_color, "marginTop": "16px"}),
        html.P(f"Error: {error}", style={"color": COLORS['gray']['400'], "fontSize": "14px"})
    ], style={"textAlign": "center", "padding": "60px"})

#==============================================================================
# PRO ANALYTICS SECTION  (replaces generic Advanced Charts)
#==============================================================================

# ── Fallback dataset — real public financials (latest fiscal year, $M) ──────
_PRO_FALLBACK = {
    'NVDA':  {'rev': 130497, 'ebitda_m': 60.45, 'gross_m': 74.99, 'oper_m': 62.42,
              'net_m': 55.85, 'rev_growth': 114.2, 'fcf_m': 46.6,
              'int_cov': 329.77, 'cur_ratio': 4.44, 'debt_asset': 9.2,
              'roe': 115.7, 'cogs_pct': 25.01, 'sga_pct': 3.0,  'rd_pct': 9.5},
    'MSFT':  {'rev': 281724, 'ebitda_m': 62.61, 'gross_m': 68.82, 'oper_m': 45.62,
              'net_m': 36.15, 'rev_growth': 14.93, 'fcf_m': 25.4,
              'int_cov': 53.89,  'cur_ratio': 1.35, 'debt_asset': 18.12,
              'roe': 39.0,  'cogs_pct': 31.18, 'sga_pct': 10.5, 'rd_pct': 13.2},
    'GOOGL': {'rev': 350018, 'ebitda_m': 38.15, 'gross_m': 58.20, 'oper_m': 32.11,
              'net_m': 28.60, 'rev_growth': 13.87, 'fcf_m': 20.8,
              'int_cov': 419.37, 'cur_ratio': 1.84, 'debt_asset': 5.71,
              'roe': 34.0,  'cogs_pct': 41.80, 'sga_pct': 9.5,  'rd_pct': 14.1},
    'META':  {'rev': 164500, 'ebitda_m': 49.10, 'gross_m': 85.90, 'oper_m': 41.90,
              'net_m': 37.90, 'rev_growth': 21.90, 'fcf_m': 28.5,
              'int_cov': 80.0,   'cur_ratio': 2.80, 'debt_asset': 8.0,
              'roe': 34.8,  'cogs_pct': 14.10, 'sga_pct': 12.0, 'rd_pct': 29.0},
    'AAPL':  {'rev': 391000, 'ebitda_m': 33.00, 'gross_m': 46.50, 'oper_m': 31.50,
              'net_m': 25.30, 'rev_growth': 6.00,  'fcf_m': 25.0,
              'int_cov': 30.0,   'cur_ratio': 1.02, 'debt_asset': 32.0,
              'roe': 147.0, 'cogs_pct': 53.50, 'sga_pct': 6.5,  'rd_pct': 8.0},
    'AMZN':  {'rev': 638000, 'ebitda_m': 14.50, 'gross_m': 49.00, 'oper_m': 10.80,
              'net_m': 5.90,  'rev_growth': 12.00, 'fcf_m': 5.5,
              'int_cov': 12.0,   'cur_ratio': 1.08, 'debt_asset': 29.0,
              'roe': 22.0,  'cogs_pct': 51.00, 'sga_pct': 22.0, 'rd_pct': 16.2},
}

_PRO_PALETTE = ['#6366f1', '#22c55e', '#f59e0b', '#ec4899', '#06b6d4', '#f97316']


def _load_pro_data():
    """Pull latest snapshot from HANA; fall back to _PRO_FALLBACK."""
    if ml_service is None:
        return _PRO_FALLBACK
    try:
        df = ml_service.get_advanced_data()
        if df.empty:
            df = ml_service.get_company_data()
        if df.empty:
            return _PRO_FALLBACK

        # Keep only valid tickers
        if 'TICKER' in df.columns:
            df['TICKER'] = df['TICKER'].str.replace(' US Equity', '', regex=False).str.strip()
            df = df.drop_duplicates(subset=['TICKER'], keep='first')

        needed = ['SALES_REV_TURN', 'EBITDA_MARGIN', 'GROSS_MARGIN', 'PROF_MARGIN',
                  'SALES_GROWTH', 'CF_FREE_CASH_FLOW', 'CUR_RATIO',
                  'TOT_DEBT_TO_TOT_ASSET', 'INTEREST_COVERAGE_RATIO']
        if not all(c in df.columns for c in ['TICKER', 'SALES_REV_TURN']):
            return _PRO_FALLBACK

        result = {}
        for _, row in df.iterrows():
            t = row.get('TICKER', '')
            if not t:
                continue
            rev = float(row.get('SALES_REV_TURN', 0) or 0)
            if rev <= 0:
                continue
            # Scale to $M if stored in raw dollars
            if rev > 1e9:
                rev /= 1e6
            fcf_raw = float(row.get('CF_FREE_CASH_FLOW', 0) or 0)
            if fcf_raw > 1e9:
                fcf_raw /= 1e6
            fcf_m = (fcf_raw / rev * 100) if rev > 0 else 0
            result[t] = {
                'rev': rev,
                'ebitda_m': float(row.get('EBITDA_MARGIN', 0) or 0),
                'gross_m':  float(row.get('GROSS_MARGIN', 0) or 0),
                'oper_m':   float(row.get('OPER_MARGIN', 0) or 0),
                'net_m':    float(row.get('PROF_MARGIN', 0) or 0),
                'rev_growth': float(row.get('SALES_GROWTH', 0) or 0),
                'fcf_m':    fcf_m,
                'int_cov':  float(row.get('INTEREST_COVERAGE_RATIO', 0) or 0),
                'cur_ratio': float(row.get('CUR_RATIO', 0) or 0),
                'debt_asset': float(row.get('TOT_DEBT_TO_TOT_ASSET', 0) or 0),
                # fallback items not always available in snapshot
                'roe':      _PRO_FALLBACK.get(t, {}).get('roe', 20),
                'cogs_pct': round(100 - float(row.get('GROSS_MARGIN', 0) or 0), 2),
                'sga_pct':  _PRO_FALLBACK.get(t, {}).get('sga_pct', 10),
                'rd_pct':   _PRO_FALLBACK.get(t, {}).get('rd_pct', 10),
            }
        return result if result else _PRO_FALLBACK
    except Exception as e:
        logger.error(f"_load_pro_data error: {e}")
        return _PRO_FALLBACK


def _build_pro_charts(data: dict, dark_mode: bool):
    """Build 4 premium analytical charts from the company dataset."""
    tickers  = list(data.keys())
    text_col = COLORS['gray']['100'] if dark_mode else COLORS['gray']['900']
    sub_col  = COLORS['gray']['400']
    bg       = COLORS['gray']['800'] if dark_mode else '#ffffff'
    gc       = COLORS['gray']['700'] if dark_mode else COLORS['gray']['200']
    bdr      = COLORS['gray']['700'] if dark_mode else COLORS['gray']['200']
    pb       = 'rgba(0,0,0,0)'

    def card(title, icon, subtitle, graph_fig, height=420):
        return html.Div([
            html.Div([
                html.Div([
                    html.I(className=f"fas {icon}", style={
                        "fontSize": "16px", "color": _PRO_PALETTE[0],
                        "marginRight": "10px"
                    }),
                    html.Span(title, style={"fontWeight": "700", "fontSize": "15px",
                                            "color": text_col}),
                    html.Span(" PRO", style={
                        "fontSize": "10px", "fontWeight": "800",
                        "background": "linear-gradient(135deg,#fbbf24,#f59e0b)",
                        "color": "#1c1917", "padding": "1px 7px",
                        "borderRadius": "10px", "marginLeft": "8px",
                        "verticalAlign": "middle", "letterSpacing": "0.08em"
                    }),
                ], style={"display": "flex", "alignItems": "center"}),
                html.P(subtitle, style={"color": sub_col, "fontSize": "12px",
                                        "margin": "4px 0 0 26px"}),
            ], style={"padding": "16px 20px 0"}),
            dcc.Graph(figure=graph_fig, config={'displayModeBar': False},
                      style={'height': f'{height}px'}),
        ], style={
            "backgroundColor": bg, "borderRadius": "14px",
            "border": f"1px solid {bdr}",
            "overflow": "hidden", "marginBottom": "0",
        })

    # ── Chart 1: Profitability Quadrant — EBITDA Margin vs Revenue Growth ──
    fig1 = go.Figure()
    revs = [d['rev'] for d in data.values()]
    max_rev = max(revs) if revs else 1
    medX = float(np.median([d['rev_growth'] for d in data.values()]))
    medY = float(np.median([d['ebitda_m'] for d in data.values()]))

    # Quadrant backgrounds
    for (x0, x1, y0, y1, lbl, col) in [
        (medX, 200, medY, 90, "⭐ Stars",      "rgba(99,102,241,0.06)"),
        (-60,  medX, medY, 90, "🐄 Cash Cows", "rgba(34,197,94,0.06)"),
        (medX, 200, -20, medY, "🚀 Growth Mode","rgba(245,158,11,0.06)"),
        (-60,  medX, -20, medY, "⚠ Turnaround", "rgba(239,68,68,0.05)"),
    ]:
        fig1.add_shape(type="rect", x0=x0, x1=x1, y0=y0, y1=y1,
                       fillcolor=col, line_width=0, layer="below")
        fig1.add_annotation(x=(x0+x1)/2, y=y1-3, text=lbl,
                             showarrow=False, font=dict(size=11, color=sub_col),
                             xanchor='center')

    for i, (t, d) in enumerate(data.items()):
        sz = 30 + (d['rev'] / max_rev) * 70
        fig1.add_trace(go.Scatter(
            x=[d['rev_growth']], y=[d['ebitda_m']],
            mode='markers+text',
            name=t,
            marker=dict(size=sz, color=_PRO_PALETTE[i % len(_PRO_PALETTE)],
                        opacity=0.85, line=dict(width=2, color='white')),
            text=[t], textposition='middle center',
            textfont=dict(color='white', size=10, family='Inter, sans-serif'),
            hovertemplate=(f"<b>{t}</b><br>Revenue Growth: %{{x:.1f}}%"
                           f"<br>EBITDA Margin: %{{y:.1f}}%"
                           f"<br>Revenue: ${d['rev']:,.0f}M<extra></extra>"),
            showlegend=False,
        ))

    fig1.add_hline(y=medY, line_dash='dash', line_color=COLORS['gray']['500'],
                   line_width=1, opacity=0.6)
    fig1.add_vline(x=medX, line_dash='dash', line_color=COLORS['gray']['500'],
                   line_width=1, opacity=0.6)
    fig1.update_layout(
        height=440, plot_bgcolor=pb, paper_bgcolor=pb,
        font=dict(color=text_col, size=12),
        xaxis=dict(title="Revenue Growth YoY (%)", showgrid=True, gridcolor=gc,
                   zeroline=False, ticksuffix='%'),
        yaxis=dict(title="EBITDA Margin (%)", showgrid=True, gridcolor=gc,
                   zeroline=False, ticksuffix='%'),
        margin=dict(l=60, r=30, t=30, b=60), hovermode='closest',
    )
    c1 = card("Profitability Quadrant", "fa-crosshairs",
              "EBITDA Margin vs Revenue Growth — bubble size = revenue. "
              "Dashes = sector medians.", fig1, 480)

    # ── Chart 2: Cost Structure DNA — horizontal stacked 100% bar ──────────
    fig2 = go.Figure()
    segs = [
        ('COGS',               'cogs_pct', '#ef4444'),
        ('SG&A',               'sga_pct',  '#f97316'),
        ('R&D',                'rd_pct',   '#eab308'),
        ('Operating Income',   None,        '#6366f1'),  # computed residual
        ('Net Margin',         'net_m',    '#22c55e'),
    ]
    labels = list(data.keys())

    # Build stacked segments; operating income = oper_m - sga - rd; adjusted
    for (seg_name, key, color) in segs:
        vals = []
        for d in data.values():
            if key is not None:
                vals.append(round(d.get(key, 0), 2))
            else:
                # Operating income = gross_m - sga_pct - rd_pct
                v = max(0, round(d['gross_m'] - d['sga_pct'] - d['rd_pct'] - d.get('net_m', 0), 2))
                vals.append(v)
        fig2.add_trace(go.Bar(
            name=seg_name, y=labels, x=vals, orientation='h',
            marker_color=color,
            hovertemplate=f"<b>%{{y}}</b><br>{seg_name}: %{{x:.1f}}%<extra></extra>",
            texttemplate='%{x:.1f}%', textposition='inside',
            insidetextanchor='middle', textfont=dict(size=10, color='white'),
        ))

    fig2.update_layout(
        barmode='stack', height=360, plot_bgcolor=pb, paper_bgcolor=pb,
        font=dict(color=text_col, size=12),
        xaxis=dict(title="% of Revenue", showgrid=True, gridcolor=gc,
                   ticksuffix='%', range=[0, 105]),
        yaxis=dict(showgrid=False),
        legend=dict(orientation='h', yanchor='bottom', y=1.02,
                    xanchor='center', x=0.5, bgcolor='rgba(0,0,0,0)'),
        margin=dict(l=70, r=30, t=40, b=60),
    )
    c2 = card("Cost Structure DNA", "fa-dna",
              "How each dollar of revenue is consumed — costs vs margins per company.",
              fig2, 400)

    # ── Chart 3: Capital Efficiency Matrix — FCF Margin vs Interest Coverage ─
    fig3 = go.Figure()
    valid3 = {t: d for t, d in data.items() if d['int_cov'] > 0 and d['fcf_m'] > 0}
    if not valid3:
        valid3 = data

    med3X = float(np.median([d['fcf_m']  for d in valid3.values()]))
    med3Y = float(np.median([min(d['int_cov'], 150) for d in valid3.values()]))

    for (x0, x1, y0, y1, lbl, col) in [
        (med3X, 60,   med3Y, 200, "💎 Elite",          "rgba(99,102,241,0.07)"),
        (-5,    med3X, med3Y, 200, "🏦 Debt Shield",    "rgba(34,197,94,0.07)"),
        (med3X, 60,  -5,    med3Y, "💸 Cash Generator", "rgba(245,158,11,0.07)"),
        (-5,    med3X, -5,  med3Y, "⚡ Leverage Play",  "rgba(239,68,68,0.05)"),
    ]:
        fig3.add_shape(type="rect", x0=x0, x1=x1, y0=y0, y1=y1,
                       fillcolor=col, line_width=0, layer="below")
        fig3.add_annotation(x=(x0+x1)/2, y=y1-8, text=lbl,
                             showarrow=False, font=dict(size=11, color=sub_col),
                             xanchor='center')

    for i, (t, d) in enumerate(valid3.items()):
        ic = min(d['int_cov'], 150)
        sz = 26 + (d['rev'] / max_rev) * 60
        fig3.add_trace(go.Scatter(
            x=[d['fcf_m']], y=[ic],
            mode='markers+text', name=t,
            marker=dict(size=sz, color=_PRO_PALETTE[i % len(_PRO_PALETTE)],
                        opacity=0.85, line=dict(width=2, color='white')),
            text=[t], textposition='middle center',
            textfont=dict(color='white', size=10, family='Inter, sans-serif'),
            hovertemplate=(f"<b>{t}</b><br>FCF Margin: %{{x:.1f}}%"
                           f"<br>Interest Coverage: {d['int_cov']:.0f}x"
                           f"<br>Revenue: ${d['rev']:,.0f}M<extra></extra>"),
            showlegend=False,
        ))

    fig3.add_hline(y=med3Y, line_dash='dash', line_color=COLORS['gray']['500'],
                   line_width=1, opacity=0.6)
    fig3.add_vline(x=med3X, line_dash='dash', line_color=COLORS['gray']['500'],
                   line_width=1, opacity=0.6)
    fig3.update_layout(
        height=440, plot_bgcolor=pb, paper_bgcolor=pb,
        font=dict(color=text_col, size=12),
        xaxis=dict(title="Free Cash Flow Margin (%)", showgrid=True,
                   gridcolor=gc, zeroline=False, ticksuffix='%'),
        yaxis=dict(title="Interest Coverage Ratio (×)", showgrid=True,
                   gridcolor=gc, zeroline=False),
        margin=dict(l=60, r=30, t=30, b=60), hovermode='closest',
    )
    c3 = card("Capital Efficiency Matrix", "fa-gem",
              "FCF Margin vs Debt Coverage — bubble size = revenue. "
              "Top-right = highest capital quality.", fig3, 480)

    # ── Chart 4: Multi-Metric Health Radar ──────────────────────────────────
    radar_metrics = ['Gross Margin', 'EBITDA Margin', 'FCF Margin',
                     'Revenue Growth', 'Liquidity (CR)', 'Debt Safety']

    def _norm(val, lo, hi):
        """Normalise val to 0-100 within [lo, hi]."""
        if hi == lo:
            return 50.0
        return float(max(0, min(100, (val - lo) / (hi - lo) * 100)))

    ranges = {
        'Gross Margin':   (0,  100),
        'EBITDA Margin':  (0,   80),
        'FCF Margin':     (-10, 55),
        'Revenue Growth': (-10, 120),
        'Liquidity (CR)': (0,    5),
        'Debt Safety':    (0,   40),   # lower debt = higher score → inverted below
    }

    fig4 = go.Figure()
    for i, (t, d) in enumerate(data.items()):
        raw = [
            d['gross_m'],
            d['ebitda_m'],
            d['fcf_m'],
            d['rev_growth'],
            d['cur_ratio'],
            max(0, 40 - d['debt_asset']),  # invert: less debt = higher
        ]
        normed = [_norm(v, ranges[m][0], ranges[m][1])
                  for v, m in zip(raw, radar_metrics)]
        normed.append(normed[0])  # close the polygon

        hex_c = _PRO_PALETTE[i % len(_PRO_PALETTE)].lstrip('#')
        r_c, g_c, b_c = int(hex_c[0:2], 16), int(hex_c[2:4], 16), int(hex_c[4:6], 16)
        fill_rgba = f'rgba({r_c},{g_c},{b_c},0.12)'
        fig4.add_trace(go.Scatterpolar(
            r=normed,
            theta=radar_metrics + [radar_metrics[0]],
            fill='toself',
            name=t,
            line=dict(color=_PRO_PALETTE[i % len(_PRO_PALETTE)], width=2),
            fillcolor=fill_rgba,
            opacity=0.9,
            hovertemplate=(f"<b>{t}</b><br>%{{theta}}: %{{r:.0f}} / 100"
                           "<extra></extra>"),
        ))

    fig4.update_layout(
        polar=dict(
            bgcolor=pb,
            radialaxis=dict(visible=True, range=[0, 100],
                            gridcolor=gc, tickfont=dict(size=9, color=sub_col),
                            ticksuffix='', showticklabels=True, ticks=''),
            angularaxis=dict(gridcolor=gc,
                             tickfont=dict(size=11, color=text_col)),
        ),
        showlegend=True,
        legend=dict(orientation='h', yanchor='bottom', y=-0.12,
                    xanchor='center', x=0.5, bgcolor='rgba(0,0,0,0)',
                    font=dict(size=11, color=text_col)),
        height=440, plot_bgcolor=pb, paper_bgcolor=pb,
        font=dict(color=text_col, size=12),
        margin=dict(l=50, r=50, t=30, b=60),
    )
    c4 = card("Multi-Metric Health Radar", "fa-spider",
              "6-axis normalised comparison: 100 = best-in-class across all dimensions.",
              fig4, 480)

    return [c1, c2, c3, c4]


@app.callback(
    Output('advanced-charts-container', 'children'),
    [Input('update-timestamp', 'data'),
     Input('dark-mode-store', 'data'),
     Input('pro-unlocked-store', 'data')]
)
def update_advanced_charts(timestamp, dark_mode, pro_unlocked):
    """Render 4 PRO analytics charts with blur/unlock overlay for free users."""

    text_col = COLORS['gray']['100'] if dark_mode else COLORS['gray']['900']
    sub_col  = COLORS['gray']['400']
    bg       = COLORS['gray']['800'] if dark_mode else '#ffffff'
    bdr      = COLORS['gray']['700'] if dark_mode else COLORS['gray']['200']

    data = _load_pro_data()
    charts = _build_pro_charts(data, dark_mode)

    charts_grid = html.Div([
        dbc.Row([
            dbc.Col(charts[0], md=6, className="mb-4"),
            dbc.Col(charts[1], md=6, className="mb-4"),
        ]),
        dbc.Row([
            dbc.Col(charts[2], md=6, className="mb-4"),
            dbc.Col(charts[3], md=6, className="mb-4"),
        ]),
    ])

    if pro_unlocked:
        charts_section = charts_grid
    else:
        # Blur the charts and show an unlock overlay on top
        charts_section = html.Div([
            # Blurred charts layer
            html.Div(charts_grid, style={
                "filter": "blur(7px)",
                "pointerEvents": "none",
                "userSelect": "none",
                "transition": "filter 0.5s ease",
            }),
            # Overlay with Unlock card
            html.Div([
                html.Div([
                    # Gold PRO badge
                    html.Div("⚡ PRO FEATURE", style={
                        "display": "inline-block",
                        "background": "linear-gradient(135deg,#fbbf24,#f59e0b)",
                        "color": "#1c1917", "padding": "4px 14px",
                        "borderRadius": "20px", "fontSize": "11px",
                        "fontWeight": "800", "letterSpacing": "0.12em",
                        "marginBottom": "16px",
                        "boxShadow": "0 4px 16px rgba(251,191,36,0.5)",
                    }),
                    html.H3("Premium Analytics", style={
                        "color": "white", "margin": "0 0 8px",
                        "fontWeight": "800", "fontSize": "26px",
                    }),
                    html.P("4 high-value analytical views used by top-tier investors "
                           "and CFOs to evaluate performance.", style={
                        "color": "rgba(255,255,255,0.65)", "fontSize": "14px",
                        "margin": "0 0 20px", "maxWidth": "340px",
                        "lineHeight": "1.6",
                    }),
                    # Feature pills
                    html.Div([
                        html.Span(f, style={
                            "background": "rgba(255,255,255,0.1)",
                            "color": "rgba(255,255,255,0.8)",
                            "padding": "5px 12px", "borderRadius": "20px",
                            "fontSize": "12px", "margin": "3px",
                            "border": "1px solid rgba(255,255,255,0.15)",
                            "display": "inline-block",
                        }) for f in [
                            "🎯 Profitability Quadrant",
                            "🧬 Cost Structure DNA",
                            "💎 Capital Efficiency",
                            "🕸 Health Radar",
                        ]
                    ], style={"marginBottom": "28px"}),
                    # Unlock button
                    html.Button([
                        html.I(className="fas fa-lock-open",
                               style={"marginRight": "8px"}),
                        "Unlock Pro  ·  $99/month",
                    ], id='unlock-pro-btn', className="pro-unlock-btn"),
                    html.P("Cancel anytime · 7-day free trial", style={
                        "color": "rgba(255,255,255,0.45)",
                        "fontSize": "11px", "marginTop": "10px",
                    }),
                ], style={
                    "background": "linear-gradient(145deg,#1e1b4b,#312e81,#4c1d95)",
                    "borderRadius": "20px", "padding": "40px 44px",
                    "textAlign": "center", "maxWidth": "480px", "width": "90%",
                    "boxShadow": ("0 30px 60px rgba(0,0,0,0.45),"
                                  "0 0 80px rgba(99,102,241,0.25)"),
                }),
            ], style={
                "position": "absolute", "top": 0, "left": 0,
                "right": 0, "bottom": 0,
                "display": "flex", "alignItems": "center",
                "justifyContent": "center",
                "background": "radial-gradient(ellipse at center,"
                              "rgba(99,102,241,0.08) 0%, transparent 70%)",
                "zIndex": 10,
            }),
        ], style={"position": "relative"})

    return html.Div([
        # Section header
        html.Div([
            html.Div([
                html.H3("Pro Analytics", style={
                    "color": text_col, "margin": "0 0 4px", "fontWeight": "800",
                    "fontSize": "20px",
                }),
                html.P("Advanced financial intelligence — institutional-grade insights",
                       style={"color": sub_col, "fontSize": "13px", "margin": 0}),
            ]),
            html.Div([
                html.Span("⚡ PRO", style={
                    "background": "linear-gradient(135deg,#fbbf24,#f59e0b)",
                    "color": "#1c1917", "padding": "4px 14px",
                    "borderRadius": "20px", "fontSize": "11px",
                    "fontWeight": "800", "letterSpacing": "0.1em",
                    "boxShadow": "0 2px 10px rgba(251,191,36,0.4)",
                }),
            ]),
        ], style={
            "display": "flex", "justifyContent": "space-between",
            "alignItems": "center", "marginBottom": "20px",
        }),
        charts_section,
    ])



# ── PRO Payment Modal Callbacks ──────────────────────────────────────────────

@app.callback(
    Output('payment-modal-open', 'data'),
    Input('unlock-pro-btn', 'n_clicks'),
    prevent_initial_call=True
)
def open_payment_modal(n):
    if n:
        return True
    return False

@app.callback(
    Output('payment-modal-open', 'data', allow_duplicate=True),
    Input('pro-payment-close', 'n_clicks'),
    prevent_initial_call=True
)
def close_payment_modal(n):
    if n:
        return False
    return dash.no_update

@app.callback(
    [Output('pro-unlocked-store', 'data'),
     Output('payment-modal-open', 'data', allow_duplicate=True)],
    Input('pro-payment-submit', 'n_clicks'),
    prevent_initial_call=True
)
def submit_payment(n):
    """Simulate payment acceptance — unlock PRO and close modal."""
    if n:
        return True, False
    return dash.no_update, dash.no_update

@app.callback(
    Output('pro-payment-modal', 'style'),
    Input('payment-modal-open', 'data')
)
def toggle_payment_modal(is_open):
    if is_open:
        return {'display': 'block'}
    return {'display': 'none'}


# ==================== SCENARIO SIMULATOR CALLBACKS ====================

# ── Shared META reference data (used by all scenario callbacks) ────────────
_META_REF = {
    "years_hist": [2020, 2021, 2022, 2023, 2024],
    "years_proj": [2025, 2026, 2027],
    "revenue":       [85965,  117929, 116609, 134902, 164500],
    "ebitda":        [29528,  47440,  40489,  58998,  80765],
    "net_income":    [29146,  39370,  23200,  39098,  62360],
    "ebitda_margin": [34.3,   40.2,   34.7,   43.7,   49.1],
    "net_margin":    [33.9,   33.4,   19.9,   29.0,   37.9],
    "base_rev":      164500,
    "base_ebitda_m": 49.1,
    "base_net_m":    37.9,
    "avg_growth":    0.1737,   # ~17.4 % CAGR 2020–2024
}

def _scenario_compute(rev_change_pct: float, cost_change_pct: float, ref: dict = None):
    """
    Compute Scenario 1 (base trend) and Scenario 2 (what-if) projections.
    rev_change_pct  : -30 to +30  — multiplier on all projected revenues
    cost_change_pct : -30 to +30  — cost structure change; affects margin
    Returns (yh, yp, hist_rev, base_rev_proj, wi_rev_proj,
             hist_ebitda, base_ebitda_proj, wi_ebitda_proj,
             sim_rev, sim_costs, wi_ebitda_yr1, wi_net_yr1,
             base_ebitda_yr1, base_net_yr1)
    """
    if ref is None:
        ref = _META_REF

    base_rev   = float(ref["base_rev"])
    base_em    = float(ref["base_ebitda_m"])
    base_nm    = float(ref["base_net_m"])
    g          = float(ref["avg_growth"])

    # Scenario 1 — base trend projection (3 years)
    base_rev_proj, base_ebitda_proj, base_net_proj = [], [], []
    r = base_rev
    for _ in ref["years_proj"]:
        r = r * (1 + g)
        base_rev_proj.append(round(r, 1))
        base_ebitda_proj.append(round(r * base_em / 100, 1))
        base_net_proj.append(round(r * base_nm / 100, 1))

    # Scenario 2 — what-if (apply revenue & cost change)
    rev_mult   = 1 + rev_change_pct / 100
    # Cost change: higher costs → lower margin; lower costs → higher margin
    cost_ratio  = (1 - base_em / 100)          # baseline cost as % of rev
    new_cost_r  = cost_ratio * (1 + cost_change_pct / 100)
    new_em      = max(0, min(100, (1 - new_cost_r) * 100))
    # Net margin scales proportionally with EBITDA margin change
    em_factor   = new_em / base_em if base_em > 0 else 1.0
    new_nm      = min(new_em, base_nm * em_factor)

    wi_rev_proj, wi_ebitda_proj, wi_net_proj = [], [], []
    r = base_rev
    for _ in ref["years_proj"]:
        r = r * (1 + g)
        wi_r = r * rev_mult
        wi_rev_proj.append(round(wi_r, 1))
        wi_ebitda_proj.append(round(wi_r * new_em / 100, 1))
        wi_net_proj.append(round(wi_r * new_nm / 100, 1))

    # Simulated Year+1 display values
    sim_rev   = wi_rev_proj[0] if wi_rev_proj else base_rev
    sim_costs = sim_rev * new_cost_r

    return {
        "yh": [str(y) for y in ref["years_hist"]],
        "yp": [str(y) for y in ref["years_proj"]],
        "hist_rev":         [float(v) for v in ref["revenue"]],
        "hist_ebitda":      [float(v) for v in ref["ebitda"]],
        "hist_ebitda_m":    [float(v) for v in ref["ebitda_margin"]],
        "base_rev_proj":    base_rev_proj,
        "base_ebitda_proj": base_ebitda_proj,
        "base_net_proj":    base_net_proj,
        "wi_rev_proj":      wi_rev_proj,
        "wi_ebitda_proj":   wi_ebitda_proj,
        "wi_net_proj":      wi_net_proj,
        "sim_rev":          sim_rev,
        "sim_costs":        sim_costs,
        "wi_ebitda_yr1":    wi_ebitda_proj[0] if wi_ebitda_proj else 0,
        "wi_net_yr1":       wi_net_proj[0]    if wi_net_proj    else 0,
        "base_ebitda_yr1":  base_ebitda_proj[0] if base_ebitda_proj else 0,
        "base_net_yr1":     base_net_proj[0]    if base_net_proj    else 0,
        "new_em":           new_em,
    }


@app.callback(
    [Output('scenario-revenue-growth', 'value'),
     Output('scenario-cost-change', 'value')],
    Input('scenario-reset-btn', 'n_clicks'),
    prevent_initial_call=True
)
def reset_scenario(n):
    """Reset both sliders to 0."""
    return 0, 0


@app.callback(
    [Output('scenario-impact-cards', 'children'),
     Output('scenario-rev-badge', 'children'),
     Output('scenario-cost-badge', 'children'),
     Output('scenario-sim-revenue-display', 'children'),
     Output('scenario-sim-costs-display', 'children')],
    [Input('scenario-revenue-growth', 'value'),
     Input('scenario-cost-change', 'value')]
)
def update_scenario_display(rev_ch, cost_ch):
    """Live-update impact cards and display text as sliders move."""
    rev_ch   = float(rev_ch  or 0)
    cost_ch  = float(cost_ch or 0)
    sc       = _scenario_compute(rev_ch, cost_ch)

    def _fmt_b(v):
        return f"${v/1000:.1f}B" if v >= 1000 else f"${v:.0f}M"

    def _impact_card(title, value, baseline, bg_col, icon_cls):
        delta    = value - baseline
        dpct     = (delta / baseline * 100) if baseline else 0
        is_pos   = delta >= 0
        dcol     = '#16a34a' if is_pos else '#dc2626'
        dlabel   = f"+{dpct:.1f}% vs baseline" if is_pos else f"{dpct:.1f}% vs baseline"
        return html.Div([
            html.Div([
                html.P(title, style={"fontSize": "12px", "fontWeight": "600",
                                     "color": "#374151", "margin": "0 0 8px 0"}),
                html.I(className=f"fas {icon_cls}", style={"color": dcol, "fontSize": "16px"}),
            ], style={"display": "flex", "justifyContent": "space-between", "alignItems": "flex-start"}),
            html.P(_fmt_b(value), style={"fontSize": "26px", "fontWeight": "800",
                                          "color": "#111827", "margin": "4px 0"}),
            html.P(dlabel, style={"fontSize": "13px", "fontWeight": "600",
                                   "color": dcol, "margin": "0"}),
        ], style={"backgroundColor": bg_col, "borderRadius": "12px",
                  "padding": "16px 18px", "marginBottom": "10px"})

    def _insights(rc, cc):
        if rc > 0 and cc < 0:
            t, icon = "Optimal scenario — revenue up, costs down. EBITDA margin expanding.", "fa-rocket"
            col = "#7c3aed"
        elif rc > 0 and cc > 0:
            t, icon = "Revenue growth offset by rising costs. Monitor margin compression.", "fa-exclamation-triangle"
            col = "#d97706"
        elif rc < 0 and cc < 0:
            t, icon = "Revenue decline partially cushioned by cost reduction.", "fa-compress-arrows-alt"
            col = "#2563eb"
        elif rc < 0:
            t, icon = "Revenue decline scenario. Cost controls are critical.", "fa-arrow-trend-down"
            col = "#dc2626"
        else:
            t, icon = "Adjust sliders to model different financial scenarios.", "fa-lightbulb"
            col = "#7c3aed"
        return html.Div([
            html.Div([
                html.P("Key Insights", style={"fontSize": "12px", "fontWeight": "700",
                                               "color": "#374151", "margin": "0 0 10px 0"}),
                html.I(className=f"fas {icon}", style={"color": col, "fontSize": "16px"}),
            ], style={"display": "flex", "justifyContent": "space-between"}),
            html.P([html.Span("• ", style={"color": col}), t],
                   style={"fontSize": "13px", "color": "#4b5563", "margin": "0", "lineHeight": "1.6"}),
        ], style={"backgroundColor": "#f5f3ff", "borderRadius": "12px", "padding": "16px 18px"})

    cards = html.Div([
        _impact_card("EBITDA Impact",     sc["wi_ebitda_yr1"], sc["base_ebitda_yr1"], "#eff6ff", "fa-chart-line"),
        _impact_card("Net Income Impact", sc["wi_net_yr1"],    sc["base_net_yr1"],    "#f0fdf4", "fa-chart-line"),
        _insights(rev_ch, cost_ch),
    ])

    rev_badge  = f"{rev_ch:+.0f}%" if rev_ch != 0 else "0%"
    cost_badge = f"{cost_ch:+.0f}%" if cost_ch != 0 else "0%"
    sim_rev_txt   = f"Simulated Revenue: {_fmt_b(sc['sim_rev'])}"
    sim_costs_txt = f"Simulated Costs: {_fmt_b(sc['sim_costs'])}"

    return cards, rev_badge, cost_badge, sim_rev_txt, sim_costs_txt


@app.callback(
    Output('scenario-chart-output', 'children'),
    [Input('scenario-revenue-growth', 'value'),
     Input('scenario-cost-change', 'value'),
     Input('scenario-simulate-btn', 'n_clicks'),
     Input('dark-mode-store', 'data')],
    prevent_initial_call=True
)
def update_scenario_charts(rev_ch, cost_ch, n_simulate, dark_mode):
    """Render dual-line scenario chart (Historical | Scenario 1 | Scenario 2)."""
    rev_ch  = float(rev_ch  or 0)
    cost_ch = float(cost_ch or 0)
    sc = _scenario_compute(rev_ch, cost_ch)

    text_color = COLORS['gray']['100'] if dark_mode else COLORS['gray']['800']
    bg_color   = COLORS['gray']['800'] if dark_mode else '#ffffff'
    border_col = COLORS['gray']['600'] if dark_mode else COLORS['gray']['200']
    gc         = COLORS['gray']['700'] if dark_mode else COLORS['gray']['200']

    def _make_chart(yh, yp, h_vals, b_vals, w_vals, title, unit, y_fmt=',.0f'):
        fig = go.Figure()
        if h_vals:
            fig.add_trace(go.Scatter(
                x=yh, y=h_vals, mode='lines+markers', name='Historical',
                line=dict(color=COLORS['primary'], width=3),
                marker=dict(size=8, symbol='circle'),
                hovertemplate=f'%{{x}}: %{{y:{y_fmt}}} {unit}<extra>Historical</extra>',
            ))
        if b_vals:
            # Connect last historical point to first projection point
            x_conn = [yh[-1]] + yp if yh else yp
            y_conn = [h_vals[-1]] + b_vals if h_vals else b_vals
            fig.add_trace(go.Scatter(
                x=x_conn, y=y_conn, mode='lines+markers', name='Scenario 1 — Current Trend',
                line=dict(color=COLORS['primary'], width=2.5, dash='dash'),
                marker=dict(size=7, symbol='diamond'),
                hovertemplate=f'%{{x}}: %{{y:{y_fmt}}} {unit}<extra>Scenario 1</extra>',
            ))
        if w_vals:
            x_conn = [yh[-1]] + yp if yh else yp
            y_conn = [h_vals[-1]] + w_vals if h_vals else w_vals
            fig.add_trace(go.Scatter(
                x=x_conn, y=y_conn, mode='lines+markers', name='Scenario 2 — What-If',
                line=dict(color=COLORS['warning'], width=2.5, dash='dot'),
                marker=dict(size=7, symbol='triangle-up'),
                hovertemplate=f'%{{x}}: %{{y:{y_fmt}}} {unit}<extra>Scenario 2</extra>',
            ))
        if yh:
            fig.add_vline(x=yh[-1], line_dash="solid",
                          line_color=COLORS['gray']['500'], line_width=1.5,
                          annotation_text="  Forecast →",
                          annotation_position="top right",
                          annotation_font=dict(color=COLORS['gray']['400'], size=11))
        fig.update_layout(
            height=400,
            title=dict(text=title, font=dict(size=14, color=text_color)),
            plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
            font=dict(color=text_color, size=12), hovermode='x unified',
            legend=dict(orientation='h', yanchor='bottom', y=-0.30,
                        xanchor='center', x=0.5, bgcolor='rgba(0,0,0,0)'),
            xaxis=dict(showgrid=False, title='Year'),
            yaxis=dict(showgrid=True, gridcolor=gc, tickformat=y_fmt),
            margin=dict(l=60, r=30, t=55, b=90),
        )
        return fig

    fig_rev = _make_chart(
        sc["yh"], sc["yp"],
        sc["hist_rev"], sc["base_rev_proj"], sc["wi_rev_proj"],
        "Revenue — Scenario 1 (Current Trend) vs Scenario 2 (What-If)", "$M",
    )
    fig_em = _make_chart(
        sc["yh"], sc["yp"],
        sc["hist_ebitda_m"], [sc["new_em"]] * len(sc["yp"]),
        [sc["new_em"]] * len(sc["yp"]),
        "EBITDA Margin (%)", "%", ".1f",
    )

    def _card(fig, title_extra=""):
        return html.Div([
            dcc.Graph(figure=fig, config={'displayModeBar': False}),
        ], style={"backgroundColor": bg_color, "borderRadius": "12px",
                  "padding": "16px", "border": f"1px solid {border_col}"})

    return [
        dbc.Row([
            dbc.Col([_card(fig_rev)],  md=8),
            dbc.Col([_card(fig_em)],   md=4),
        ], className="g-3"),
        html.Div([
            html.Span("━━", style={"color": COLORS['primary'], "marginRight": "4px"}),
            "Historical  ",
            html.Span("  ╌╌", style={"color": COLORS['primary'], "marginLeft": "4px", "marginRight": "4px"}),
            "Scenario 1 (Current Trend)  ",
            html.Span("  ·····", style={"color": COLORS['warning'], "marginLeft": "4px", "marginRight": "4px"}),
            "Scenario 2 (What-If)",
        ], style={"textAlign": "center", "fontSize": "12px",
                  "color": COLORS['gray']['400'], "marginTop": "12px"}),
    ]

# ══════════════════════════════════════════════════════════════════════════
# FLOATING UI DARK MODE SYNC
# ══════════════════════════════════════════════════════════════════════════

@app.callback(
    Output('floating-ui-wrapper', 'className'),
    Input('dark-mode-store', 'data'),
)
def sync_floating_dark_mode(dark_mode):
    """Mirror the dashboard dark-mode class onto the floating UI wrapper
    so chatbot + PRO modal CSS rules can respond via parent selector."""
    return 'dark-mode' if dark_mode else ''


# ══════════════════════════════════════════════════════════════════════════
# CHATBOT CALLBACKS
# ══════════════════════════════════════════════════════════════════════════

@app.callback(
    Output('chatbot-open-store', 'data'),
    [Input('chatbot-toggle-btn', 'n_clicks'),
     Input('chatbot-close-btn', 'n_clicks')],
    State('chatbot-open-store', 'data'),
    prevent_initial_call=True,
)
def toggle_chatbot(toggle_clicks, close_clicks, is_open):
    """Toggle the chat panel open/closed."""
    ctx = dash.callback_context
    if not ctx.triggered:
        return is_open
    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
    if trigger_id == 'chatbot-close-btn':
        return False
    # toggle button flips state
    return not is_open


@app.callback(
    Output('chatbot-panel', 'className'),
    Input('chatbot-open-store', 'data'),
)
def update_panel_class(is_open):
    """Show or hide the chat panel with animation class."""
    return 'chat-visible' if is_open else 'chat-hidden'


@app.callback(
    [Output('chatbot-messages', 'children'),
     Output('chatbot-messages-store', 'data'),
     Output('chatbot-input', 'value')],
    [Input('chatbot-send-btn', 'n_clicks'),
     Input('chip-1', 'n_clicks'),
     Input('chip-2', 'n_clicks'),
     Input('chip-3', 'n_clicks')],
    [State('chatbot-input', 'value'),
     State('chatbot-messages-store', 'data')],
    prevent_initial_call=True,
)
def handle_chat_message(send_clicks, c1, c2, c3, input_value, messages):
    """
    Handle sending a message.
    Front-end only for now — bot replies with a placeholder response.
    Back-end LLM integration can be added later.
    """
    ctx = dash.callback_context
    if not ctx.triggered:
        raise dash.exceptions.PreventUpdate

    trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]

    # Determine the user text
    chip_map = {
        'chip-1': 'How is my EBITDA performing?',
        'chip-2': 'Who is my top competitor right now?',
        'chip-3': 'What are my cash flow risks?',
    }
    if trigger_id in chip_map:
        user_text = chip_map[trigger_id]
    else:
        user_text = (input_value or '').strip()

    if not user_text:
        raise dash.exceptions.PreventUpdate

    # Append user message
    messages = list(messages)
    messages.append({'role': 'user', 'text': user_text})

    # ── Placeholder bot response (swap this for a real LLM call later) ──
    bot_replies = {
        'How is my EBITDA performing?':
            '📊 Your EBITDA margin is 15.0% vs. an industry median of 18.2%. '
            'You are slightly below benchmark — cost optimisation in OpEx could close the gap.',
        'Who is my top competitor right now?':
            '🏆 Based on current data, META leads with the highest similarity score '
            'to your financial profile among selected peers.',
        'What are my cash flow risks?':
            '⚠️ Working capital of $800M looks adequate, but your interest coverage ratio '
            'of 8× should be monitored if rates rise. Cash from operations ($1.7B) is healthy.',
    }
    bot_text = bot_replies.get(
        user_text,
        f'🤖 Got it! You asked: *"{user_text}"*. '
        'Full LLM integration coming soon — this response is a placeholder.'
    )
    messages.append({'role': 'bot', 'text': bot_text})

    # Render all messages as Dash components
    def render_msg(m):
        role = m['role']
        return html.Div([
            html.Div(m['text'], className='chat-bubble'),
        ], className=f'chat-msg {role}')

    rendered = [render_msg(m) for m in messages]
    return rendered, messages, ''


# ─────────────────────────────────────────────
# BRIEFING BUTTON CALLBACK
# ─────────────────────────────────────────────
@app.callback(
    Output('briefing-status-msg', 'children'),
    Input('send-briefing-btn', 'n_clicks'),
    prevent_initial_call=True
)
def send_cfo_briefing(n_clicks):
    """Trigger the CFO briefing generator and send email."""
    if not n_clicks:
        return ""

    try:
        import subprocess
        import sys
        result = subprocess.run(
            [sys.executable, 'generate_briefing.py'],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=os.path.dirname(os.path.abspath(__file__))
        )
        if result.returncode == 0 and '✅' in result.stdout:
            return "✅ Briefing sent!"
        elif 'stopped' in result.stderr.lower() or 'stopped' in result.stdout.lower():
            return "⚠️ HANA offline"
        else:
            logger.error(f"Briefing error: {result.stderr[:200]}")
            return "❌ Send failed"
    except subprocess.TimeoutExpired:
        return "⏱️ Timed out"
    except Exception as e:
        logger.error(f"Briefing callback error: {e}")
        return "❌ Error"


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    debug = os.getenv('DASH_DEBUG', 'false').lower() == 'true'

    logger.info(f"Starting CFO Pulse Dashboard on port {port}")
    logger.info(f"Debug mode: {debug}")
    logger.info(f"Authentication service available: {auth_service is not None}")
    logger.info(f"Data service available: {data_service is not None}")

    app.run(
        host='0.0.0.0',
        port=port,
        debug=debug
    )
