"""
Interactive Financial Dashboard for Bloomberg HANA Data
Provides real-time visualization and analysis of financial metrics
"""

import os
import dash
from dash import dcc, html, Input, Output, State
import dash_bootstrap_components as dbc
import plotly.graph_objs as go
import plotly.express as px
import pandas as pd
import logging
from utils.config import load_config, setup_logging
from db.data_service import FinancialDataService

# Initialize logging
logger, log_file = setup_logging()
logger.info("Starting Financial Dashboard Application")

# Load configuration
config = load_config()

# Initialize data service
data_service = FinancialDataService(config)

# Connect to HANA with better error handling
try:
    if not data_service.connect():
        logger.error("Failed to connect to HANA database - check credentials and network connectivity")
        raise ConnectionError(
            "Cannot establish connection to HANA database. "
            "Please verify HANA_ADDRESS, HANA_PORT, HANA_USER, and HANA_PASSWORD environment variables."
        )
    logger.info("Successfully connected to HANA database")
except Exception as e:
    logger.error(f"Database connection error: {str(e)}")
    raise

# Initialize Dash app with Bootstrap theme
app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.BOOTSTRAP, dbc.icons.FONT_AWESOME],
    meta_tags=[
        {"name": "viewport", "content": "width=device-width, initial-scale=1"}
    ]
)

# For Cloud Foundry deployment
server = app.server
app.title = "Financial Analytics Dashboard"

# Custom CSS - ChatGPT-like theme
custom_style = {
    'backgroundColor': '#ffffff',
    'fontFamily': '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial',
}

# Dashboard Layout
app.layout = dbc.Container([
    # Header
    dbc.Row([
        dbc.Col([
            html.Div([
                html.H1([
                    html.I(className="fas fa-chart-line me-3", style={"color": "#000000"}),
                    "Financial Analytics Dashboard"
                ], style={"color": "#000000", "fontWeight": "600"}, className="mb-2"),
                html.P("Real-time Bloomberg financial data from SAP HANA",
                       style={"color": "#6b7280"})
            ], className="text-center my-4")
        ])
    ]),

    # Collapsible Metrics Section
    dbc.Row([
        dbc.Col([
            dbc.Button(
                [
                    html.I(className="fas fa-chart-bar me-2"),
                    "System Metrics",
                    html.I(id="metrics-toggle-icon", className="fas fa-chevron-down ms-2")
                ],
                id="collapse-metrics-button",
                className="mb-3",
                color="light",
                style={
                    "width": "100%",
                    "textAlign": "left",
                    "border": "1px solid #e5e7eb",
                    "color": "#1f2937",
                    "fontWeight": "500"
                },
            ),
            dbc.Collapse(
                [
                    # Row 1
                    dbc.Row([
                        dbc.Col([
                            dbc.Card([
                                dbc.CardBody([
                                    html.Div([
                                        html.I(className="fas fa-chart-bar fa-2x mb-2", style={"color": "#3b82f6"}),
                                        html.H3(id="ratios-count", className="mb-0", style={"color": "#1f2937"}),
                                        html.P("Basic Ratios Data", className="mb-0", style={"color": "#6b7280", "fontSize": "14px"}),
                                        html.Small(id="ratios-table-name", style={"color": "#9ca3af", "fontSize": "12px"})
                                    ], className="text-center")
                                ])
                            ], style={"border": "1px solid #e5e7eb"})
                        ], width=12, md=6, lg=3),

                        dbc.Col([
                            dbc.Card([
                                dbc.CardBody([
                                    html.Div([
                                        html.I(className="fas fa-database fa-2x mb-2", style={"color": "#10b981"}),
                                        html.H3(id="advanced-count", className="mb-0", style={"color": "#1f2937"}),
                                        html.P("Total Records", className="mb-0", style={"color": "#6b7280", "fontSize": "14px"}),
                                        html.Small(id="advanced-table-name", style={"color": "#9ca3af", "fontSize": "12px"})
                                    ], className="text-center")
                                ])
                            ], style={"border": "1px solid #e5e7eb"})
                        ], width=12, md=6, lg=3),

                        dbc.Col([
                            dbc.Card([
                                dbc.CardBody([
                                    html.Div([
                                        html.I(className="fas fa-layer-group fa-2x mb-2", style={"color": "#06b6d4"}),
                                        html.H3(id="total-records", className="mb-0", style={"color": "#1f2937"}),
                                        html.P("Total Data Points", className="mb-0", style={"color": "#6b7280", "fontSize": "14px"}),
                                        html.Small("All tables combined", style={"color": "#9ca3af", "fontSize": "12px"})
                                    ], className="text-center")
                                ])
                            ], style={"border": "1px solid #e5e7eb"})
                        ], width=12, md=6, lg=3),

                        dbc.Col([
                            dbc.Card([
                                dbc.CardBody([
                                    html.Div([
                                        html.I(className="fas fa-building fa-2x mb-2", style={"color": "#f59e0b"}),
                                        html.H3(id="unique-tickers", className="mb-0", style={"color": "#1f2937"}),
                                        html.P("Unique Companies", className="mb-0", style={"color": "#6b7280", "fontSize": "14px"}),
                                        html.Small("Tracked in database", style={"color": "#9ca3af", "fontSize": "12px"})
                                    ], className="text-center")
                                ])
                            ], style={"border": "1px solid #e5e7eb"})
                        ], width=12, md=6, lg=3),
                    ], className="mb-3"),

                    # Row 2
                    dbc.Row([
                        dbc.Col([
                            dbc.Card([
                                dbc.CardBody([
                                    html.Div([
                                        html.I(className="fas fa-clock fa-2x mb-2", style={"color": "#6b7280"}),
                                        html.H6(id="last-update", className="mb-0", style={"color": "#1f2937"}),
                                        html.P("Last Updated", className="mb-0", style={"color": "#6b7280", "fontSize": "14px"}),
                                        html.Small("Most recent data", style={"color": "#9ca3af", "fontSize": "12px"})
                                    ], className="text-center")
                                ])
                            ], style={"border": "1px solid #e5e7eb"})
                        ], width=12, md=6, lg=3),

                        dbc.Col([
                            dbc.Card([
                                dbc.CardBody([
                                    html.Div([
                                        html.I(className="fas fa-server fa-2x mb-2", style={"color": "#3b82f6"}),
                                        html.H6("SAP HANA Cloud", className="mb-0", style={"color": "#1f2937"}),
                                        html.P("Database Status", className="mb-0", style={"color": "#6b7280", "fontSize": "14px"}),
                                        html.Small(id="db-status", style={"color": "#10b981", "fontSize": "12px"})
                                    ], className="text-center")
                                ])
                            ], style={"border": "1px solid #e5e7eb"})
                        ], width=12, md=6, lg=3),

                        dbc.Col([
                            dbc.Card([
                                dbc.CardBody([
                                    html.Div([
                                        html.I(className="fas fa-sync fa-2x mb-2", style={"color": "#06b6d4"}),
                                        html.H6("Auto-Refresh", className="mb-0", style={"color": "#1f2937"}),
                                        html.P("Update Interval", className="mb-0", style={"color": "#6b7280", "fontSize": "14px"}),
                                        html.Small("Every 5 minutes", style={"color": "#9ca3af", "fontSize": "12px"})
                                    ], className="text-center")
                                ])
                            ], style={"border": "1px solid #e5e7eb"})
                        ], width=12, md=6, lg=3),

                        dbc.Col([
                            dbc.Card([
                                dbc.CardBody([
                                    html.Div([
                                        html.I(className="fas fa-cloud fa-2x mb-2", style={"color": "#10b981"}),
                                        html.H6("Cloud Foundry", className="mb-0", style={"color": "#1f2937"}),
                                        html.P("Deployment", className="mb-0", style={"color": "#6b7280", "fontSize": "14px"}),
                                        html.Small("Production Ready", style={"color": "#10b981", "fontSize": "12px"})
                                    ], className="text-center")
                                ])
                            ], style={"border": "1px solid #e5e7eb"})
                        ], width=12, md=6, lg=3),
                    ], className="mb-3"),
                ],
                id="collapse-metrics",
                is_open=False,
            ),
        ], width=12)
    ], className="mb-4"),

    # Main Content Tabs
    dbc.Card([
        dbc.CardHeader([
            dbc.Tabs([
                dbc.Tab(label="Overview", tab_id="overview",
                       label_style={"cursor": "pointer"}),
                dbc.Tab(label="Financial Ratios", tab_id="ratios",
                       label_style={"cursor": "pointer"}),
                dbc.Tab(label="Company Comparison", tab_id="comparison",
                       label_style={"cursor": "pointer"}),
                dbc.Tab(label="Data Explorer", tab_id="explorer",
                       label_style={"cursor": "pointer"}),
            ], id="tabs", active_tab="overview")
        ], className="section-header"),
        dbc.CardBody(id="tab-content", className="section-body p-4")
    ], className="shadow-sm mb-4 section-card"),

    # Footer
    dbc.Row([
        dbc.Col([
            html.Hr(),
            html.P([
                "Powered by SAP HANA Cloud | ",
                html.A("Bloomberg Data License", href="#", className="text-decoration-none"),
                " | Built with Plotly Dash"
            ], className="text-center text-muted small")
        ])
    ]),

    # Store components for data caching
    dcc.Store(id='ratios-data-store'),
    dcc.Store(id='advanced-data-store'),
    dcc.Store(id='ticker-list-store'),

    # Auto-refresh interval (every 5 minutes)
    dcc.Interval(
        id='interval-component',
        interval=5*60*1000,  # in milliseconds
        n_intervals=0
    )

], fluid=True, style=custom_style, className="dashboard-shell")


# Callbacks for tab content
@app.callback(
    Output("tab-content", "children"),
    Input("tabs", "active_tab"),
    State("ratios-data-store", "data"),
    State("advanced-data-store", "data"),
    State("ticker-list-store", "data")
)
def render_tab_content(active_tab, ratios_data, advanced_data, ticker_list):
    """Render content based on active tab"""

    if active_tab == "overview":
        return render_overview_tab()
    elif active_tab == "ratios":
        return render_ratios_tab()
    elif active_tab == "comparison":
        return render_comparison_tab(ticker_list)
    elif active_tab == "explorer":
        return render_explorer_tab()

    return html.Div("Select a tab")


def render_overview_tab():
    """Render overview dashboard"""
    return dbc.Container([
        # Row 1: Distribution and Heatmap
        dbc.Row([
            dbc.Col([
                dcc.Graph(id='ratio-distribution-chart')
            ], width=12, md=6),
            dbc.Col([
                dcc.Graph(id='metrics-heatmap')
            ], width=12, md=6)
        ]),
        # Row 2: Margin Analysis
        dbc.Row([
            dbc.Col([
                dcc.Graph(id='margin-analysis-chart')
            ], width=12)
        ], className="mt-4"),
        # Row 3: Liquidity and Leverage
        dbc.Row([
            dbc.Col([
                dcc.Graph(id='liquidity-analysis-chart')
            ], width=12, md=6),
            dbc.Col([
                dcc.Graph(id='leverage-analysis-chart')
            ], width=12, md=6)
        ], className="mt-4"),
        # Row 4: Profitability Metrics
        dbc.Row([
            dbc.Col([
                dcc.Graph(id='profitability-scatter-chart')
            ], width=12, md=6),
            dbc.Col([
                dcc.Graph(id='top-performers-chart')
            ], width=12, md=6)
        ], className="mt-4"),
        # Row 5: Growth and Valuation
        dbc.Row([
            dbc.Col([
                dcc.Graph(id='growth-metrics-chart')
            ], width=12, md=6),
            dbc.Col([
                dcc.Graph(id='cash-flow-chart')
            ], width=12, md=6)
        ], className="mt-4")
    ], fluid=True)


def render_ratios_tab():
    """Render competitor ratio analysis"""
    return dbc.Container([
        # Header section with company selector
        dbc.Row([
            dbc.Col([
                html.H3("Competitor Ratio Analysis", className="mb-1"),
                html.P("Compare your company with industry competitors", className="text-muted")
            ], width=12, md=6),
            dbc.Col([
                html.Label("Add Competitors to Compare:", className="fw-bold mb-2"),
                dcc.Dropdown(
                    id='competitor-selector',
                    placeholder="Select companies to compare...",
                    multi=True,
                    className="mb-3"
                )
            ], width=12, md=6)
        ], className="mb-4"),

        # Your company summary cards
        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.H6("Your Company", className="text-muted mb-2"),
                        html.H4(id="your-company-name", className="text-primary mb-0", style={"fontWeight": "bold"})
                    ])
                ], className="shadow-sm")
            ], width=12, md=3),
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.Small("EBITDA Margin", className="text-muted d-block"),
                        html.H4(id="your-company-ebitda", className="mb-0")
                    ])
                ], className="shadow-sm")
            ], width=12, md=3),
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.Small("Current Ratio", className="text-muted d-block"),
                        html.H4(id="your-company-current", className="mb-0")
                    ])
                ], className="shadow-sm")
            ], width=12, md=3),
            dbc.Col([
                dbc.Card([
                    dbc.CardBody([
                        html.Small("Gross Margin", className="text-muted d-block"),
                        html.H4(id="your-company-gross", className="mb-0")
                    ])
                ], className="shadow-sm")
            ], width=12, md=3),
        ], className="mb-4"),

        # Comparison charts
        dbc.Row([
            dbc.Col([
                dcc.Graph(id='competitor-comparison-bar')
            ], width=12, md=6),
            dbc.Col([
                dcc.Graph(id='competitor-radar-chart')
            ], width=12, md=6)
        ], className="mb-4"),

        # Dynamic metric visualization section
        dbc.Row([
            dbc.Col([
                html.H5("Dynamic Metric Analysis", className="mb-3"),
                html.P("Select a metric and visualization type to explore the data", className="text-muted mb-3")
            ], width=12)
        ]),
        dbc.Row([
            dbc.Col([
                html.Label("Select Metric:", className="fw-bold mb-2"),
                dcc.Dropdown(
                    id='dynamic-metric-selector',
                    options=[
                        {'label': 'EBITDA Margin', 'value': 'EBITDA_MARGIN'},
                        {'label': 'Current Ratio', 'value': 'CUR_RATIO'},
                        {'label': 'Quick Ratio', 'value': 'QUICK_RATIO'},
                        {'label': 'Gross Margin', 'value': 'GROSS_MARGIN'},
                        {'label': 'Interest Coverage', 'value': 'INTEREST_COVERAGE_RATIO'},
                        {'label': 'Debt to Asset', 'value': 'TOT_DEBT_TO_TOT_ASSET'},
                        {'label': 'Net Debt to Equity', 'value': 'NET_DEBT_TO_SHRHLDR_EQTY'},
                        {'label': 'Debt to EBITDA', 'value': 'TOT_DEBT_TO_EBITDA'}
                    ],
                    value='EBITDA_MARGIN',
                    className="mb-3"
                )
            ], width=12, md=4),
            dbc.Col([
                html.Label("Chart Type:", className="fw-bold mb-2"),
                dcc.Dropdown(
                    id='dynamic-chart-type',
                    options=[
                        {'label': 'Histogram', 'value': 'histogram'},
                        {'label': 'Pie Chart', 'value': 'pie'},
                        {'label': 'Line Chart', 'value': 'line'}
                    ],
                    value='histogram',
                    className="mb-3"
                )
            ], width=12, md=4)
        ], className="mb-3"),
        dbc.Row([
            dbc.Col([
                dcc.Graph(id='dynamic-metric-chart')
            ], width=12)
        ], className="mb-4"),

        # Detailed comparison table
        dbc.Row([
            dbc.Col([
                html.H5("Detailed Metrics Comparison", className="mb-3"),
                html.Div(id='competitor-comparison-table')
            ], width=12)
        ], className="mb-4"),

        # Industry benchmark
        dbc.Row([
            dbc.Col([
                dcc.Graph(id='industry-benchmark-chart')
            ], width=12)
        ], className="mb-4"),

        # Industry Median Benchmarking Table
        dbc.Row([
            dbc.Col([
                html.H5("Industry Median Benchmarking", className="mb-3"),
                html.Div(id='industry-median-table')
            ], width=12)
        ], className="mb-4"),

        # Z-Score Credit Risk Analysis and Stacked EBITDA
        dbc.Row([
            dbc.Col([
                html.H5("Z-Score Credit Risk Analysis", className="mb-3"),
                html.Div(id='zscore-risk-table')
            ], width=12, md=6),
            dbc.Col([
                dcc.Graph(id='stacked-ebitda-chart')
            ], width=12, md=6)
        ])
    ], fluid=True)


def render_comparison_tab(ticker_list):
    """Render company comparison view"""
    ticker_options = [{'label': t, 'value': t} for t in (ticker_list or [])]

    return dbc.Container([
        dbc.Row([
            dbc.Col([
                html.H5("Select Companies to Compare:"),
                dcc.Dropdown(
                    id='comparison-tickers-dropdown',
                    options=ticker_options,
                    multi=True,
                    placeholder="Select 2-5 companies...",
                    className="mb-3"
                )
            ], width=12, md=8),
            dbc.Col([
                html.H5("Select Metric:"),
                dcc.Dropdown(
                    id='comparison-metric-dropdown',
                    options=[
                        {'label': 'Gross Margin', 'value': 'GROSS_MARGIN'},
                        {'label': 'EBITDA Margin', 'value': 'EBITDA_MARGIN'},
                        {'label': 'Current Ratio', 'value': 'CUR_RATIO'},
                        {'label': 'Quick Ratio', 'value': 'QUICK_RATIO'},
                    ],
                    value='GROSS_MARGIN',
                    className="mb-3"
                )
            ], width=12, md=4)
        ]),
        dbc.Row([
            dbc.Col([
                dcc.Graph(id='comparison-chart')
            ], width=12)
        ])
    ], fluid=True)


def render_explorer_tab():
    """Render data explorer with table view"""
    return dbc.Container([
        dbc.Row([
            dbc.Col([
                html.H5("Data Table:"),
                dcc.Dropdown(
                    id='explorer-table-dropdown',
                    options=[
                        {'label': 'Financial Ratios', 'value': 'ratios'}
                    ],
                    value='ratios',
                    className="mb-3"
                )
            ], width=12, md=6),
            dbc.Col([
                html.H5("Records to Display:"),
                dcc.Slider(
                    id='explorer-limit-slider',
                    min=10,
                    max=100,
                    step=10,
                    value=50,
                    marks={i: str(i) for i in range(10, 101, 10)},
                    className="mb-3"
                )
            ], width=12, md=6)
        ]),
        dbc.Row([
            dbc.Col([
                html.Div(id='explorer-table-container')
            ], width=12)
        ])
    ], fluid=True)


# Callback to update summary cards
@app.callback(
    [Output("ratios-count", "children"),
     Output("ratios-table-name", "children"),
     Output("advanced-count", "children"),
     Output("advanced-table-name", "children"),
     Output("total-records", "children"),
     Output("unique-tickers", "children"),
     Output("last-update", "children"),
     Output("db-status", "children")],
    Input('interval-component', 'n_intervals')
)
def update_summary_cards(n):
    """Update summary statistics cards with data from FINANCIAL_RATIOS table"""
    stats = data_service.get_summary_stats()

    # Get counts from ratios table
    ratios_count = stats.get('ratios_count', 0)
    total = ratios_count
    tickers = stats.get('unique_tickers', 0)
    last_update = stats.get('last_update', 'N/A')

    # Format last update timestamp
    if last_update != 'N/A' and last_update:
        last_update = pd.to_datetime(last_update).strftime('%Y-%m-%d %H:%M')

    # Database status
    db_status = "✓ Connected" if data_service.connected else "✗ Disconnected"

    return (
        f"{ratios_count:,}",
        "Basic Ratios Data",
        f"{ratios_count:,}",
        "FINANCIAL_RATIOS table",
        f"{total:,}",
        f"{tickers:,}",
        str(last_update),
        db_status
    )


# Callback to load data into stores
@app.callback(
    [Output('ratios-data-store', 'data'),
     Output('advanced-data-store', 'data'),
     Output('ticker-list-store', 'data')],
    Input('interval-component', 'n_intervals')
)
def load_data(n):
    """Load data from HANA and store in browser"""
    ratios_df = data_service.get_financial_ratios(limit=200)
    advanced_df = data_service.get_advanced_financials(limit=200)
    tickers = data_service.get_ticker_list()

    return (
        ratios_df.to_dict('records') if not ratios_df.empty else [],
        advanced_df.to_dict('records') if not advanced_df.empty else [],
        tickers
    )


# Callback for ratio distribution chart
@app.callback(
    Output('ratio-distribution-chart', 'figure'),
    Input('ratios-data-store', 'data')
)
def update_ratio_distribution(data):
    """Create distribution chart for key ratios"""
    if not data or len(data) == 0:
        return go.Figure().add_annotation(
            text="No financial ratio data available",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False,
            font=dict(size=14, color="gray")
        )

    df = pd.DataFrame(data)

    fig = go.Figure()

    metrics = ['CUR_RATIO', 'QUICK_RATIO', 'GROSS_MARGIN', 'EBITDA_MARGIN']
    colors = ['#3498db', '#2ecc71', '#f39c12', '#e74c3c']

    for metric, color in zip(metrics, colors):
        if metric in df.columns:
            fig.add_trace(go.Box(
                y=df[metric].dropna(),
                name=metric.replace('_', ' ').title(),
                marker_color=color
            ))

    fig.update_layout(
        title="Distribution of Key Financial Ratios",
        yaxis_title="Value",
        height=400,
        showlegend=True,
        template="plotly_white"
    )

    return fig


# Callback for metrics heatmap
@app.callback(
    Output('metrics-heatmap', 'figure'),
    Input('ratios-data-store', 'data')
)
def update_metrics_heatmap(data):
    """Create correlation heatmap for metrics"""
    if not data or len(data) == 0:
        return go.Figure().add_annotation(
            text="No data available for correlation heatmap",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False,
            font=dict(size=14, color="gray")
        )

    df = pd.DataFrame(data)

    numeric_cols = ['CUR_RATIO', 'QUICK_RATIO', 'GROSS_MARGIN',
                   'EBITDA_MARGIN', 'TOT_DEBT_TO_TOT_ASSET']

    available_cols = [col for col in numeric_cols if col in df.columns]

    if not available_cols or len(available_cols) < 2:
        return go.Figure().add_annotation(
            text="Insufficient metrics for correlation analysis",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False,
            font=dict(size=14, color="gray")
        )

    corr_matrix = df[available_cols].corr()

    fig = go.Figure(data=go.Heatmap(
        z=corr_matrix.values,
        x=[col.replace('_', ' ') for col in corr_matrix.columns],
        y=[col.replace('_', ' ') for col in corr_matrix.index],
        colorscale='RdBu',
        zmid=0,
        text=corr_matrix.values,
        texttemplate='%{text:.2f}',
        textfont={"size": 10}
    ))

    fig.update_layout(
        title="Metric Correlation Heatmap",
        height=400,
        template="plotly_white"
    )

    return fig


# Callback for margin analysis
@app.callback(
    Output('margin-analysis-chart', 'figure'),
    Input('ratios-data-store', 'data')
)
def update_margin_analysis(data):
    """Create margin analysis chart"""
    if not data or len(data) == 0:
        return go.Figure().add_annotation(
            text="No margin data available",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False,
            font=dict(size=14, color="gray")
        )

    df = pd.DataFrame(data)

    if 'TICKER' not in df.columns or 'GROSS_MARGIN' not in df.columns:
        return go.Figure().add_annotation(
            text="Missing required columns for margin analysis",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False,
            font=dict(size=14, color="gray")
        )

    # Get top 10 companies by gross margin
    top_companies = df.nlargest(10, 'GROSS_MARGIN')

    fig = go.Figure()

    if 'GROSS_MARGIN' in df.columns:
        fig.add_trace(go.Bar(
            x=top_companies['TICKER'],
            y=top_companies['GROSS_MARGIN'],
            name='Gross Margin',
            marker_color='#3498db'
        ))

    if 'EBITDA_MARGIN' in df.columns:
        fig.add_trace(go.Bar(
            x=top_companies['TICKER'],
            y=top_companies['EBITDA_MARGIN'],
            name='EBITDA Margin',
            marker_color='#2ecc71'
        ))

    fig.update_layout(
        title="Top 10 Companies by Margins",
        xaxis_title="Company",
        yaxis_title="Margin (%)",
        barmode='group',
        height=400,
        template="plotly_white"
    )

    return fig


# Callback for liquidity analysis chart
@app.callback(
    Output('liquidity-analysis-chart', 'figure'),
    [Input('ratios-data-store', 'data'),
     Input('advanced-data-store', 'data')]
)
def update_liquidity_analysis(ratios_data, advanced_data):
    """Create liquidity analysis chart comparing current and quick ratios"""
    if not ratios_data or len(ratios_data) == 0:
        return go.Figure().add_annotation(
            text="No liquidity data available",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False,
            font=dict(size=14, color="gray")
        )

    df = pd.DataFrame(ratios_data)

    if 'TICKER' not in df.columns or 'CUR_RATIO' not in df.columns:
        return go.Figure().add_annotation(
            text="Missing required columns for liquidity analysis",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False,
            font=dict(size=14, color="gray")
        )

    # Get top 15 companies by current ratio
    top_companies = df.nlargest(15, 'CUR_RATIO')

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=top_companies['TICKER'],
        y=top_companies['CUR_RATIO'],
        mode='markers+lines',
        name='Current Ratio',
        marker=dict(size=10, color='#3498db'),
        line=dict(width=2, color='#3498db')
    ))

    if 'QUICK_RATIO' in df.columns:
        fig.add_trace(go.Scatter(
            x=top_companies['TICKER'],
            y=top_companies['QUICK_RATIO'],
            mode='markers+lines',
            name='Quick Ratio',
            marker=dict(size=10, color='#e74c3c'),
            line=dict(width=2, color='#e74c3c')
        ))

    # Add reference line at 1.0 (minimum healthy liquidity)
    fig.add_hline(y=1.0, line_dash="dash", line_color="gray",
                  annotation_text="Minimum Healthy Level")

    fig.update_layout(
        title="Liquidity Analysis - Current vs Quick Ratio",
        xaxis_title="Company",
        yaxis_title="Ratio",
        height=400,
        template="plotly_white",
        hovermode='x unified'
    )

    return fig


# Callback for leverage analysis chart
@app.callback(
    Output('leverage-analysis-chart', 'figure'),
    Input('ratios-data-store', 'data')
)
def update_leverage_analysis(data):
    """Create leverage analysis chart showing debt ratios"""
    if not data or len(data) == 0:
        return go.Figure().add_annotation(
            text="No leverage data available",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False,
            font=dict(size=14, color="gray")
        )

    df = pd.DataFrame(data)

    if 'TICKER' not in df.columns or 'TOT_DEBT_TO_TOT_ASSET' not in df.columns:
        return go.Figure().add_annotation(
            text="Missing required columns for leverage analysis",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False,
            font=dict(size=14, color="gray")
        )

    # Filter and sort by debt to asset ratio
    df_clean = df[df['TOT_DEBT_TO_TOT_ASSET'].notna()].copy()
    top_leveraged = df_clean.nlargest(15, 'TOT_DEBT_TO_TOT_ASSET')

    fig = go.Figure()

    fig.add_trace(go.Bar(
        x=top_leveraged['TICKER'],
        y=top_leveraged['TOT_DEBT_TO_TOT_ASSET'],
        name='Debt to Asset Ratio',
        marker_color='#e74c3c',
        text=top_leveraged['TOT_DEBT_TO_TOT_ASSET'].round(2),
        textposition='auto'
    ))

    # Add reference line at 0.5 (50% debt ratio)
    fig.add_hline(y=0.5, line_dash="dash", line_color="orange",
                  annotation_text="Moderate Leverage (50%)")

    fig.update_layout(
        title="Financial Leverage - Debt to Asset Ratio",
        xaxis_title="Company",
        yaxis_title="Debt to Asset Ratio",
        height=400,
        template="plotly_white",
        showlegend=False
    )

    return fig


# Callback for profitability scatter chart
@app.callback(
    Output('profitability-scatter-chart', 'figure'),
    [Input('ratios-data-store', 'data'),
     Input('advanced-data-store', 'data')]
)
def update_profitability_scatter(ratios_data, advanced_data):
    """Create scatter plot comparing gross margin vs EBITDA margin"""
    if not ratios_data or len(ratios_data) == 0:
        return go.Figure().add_annotation(
            text="No profitability data available",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False,
            font=dict(size=14, color="gray")
        )

    df = pd.DataFrame(ratios_data)

    if 'GROSS_MARGIN' not in df.columns or 'EBITDA_MARGIN' not in df.columns:
        return go.Figure().add_annotation(
            text="Missing required columns for profitability analysis",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False,
            font=dict(size=14, color="gray")
        )

    # Filter out NaN values
    df_clean = df[df['GROSS_MARGIN'].notna() & df['EBITDA_MARGIN'].notna()].copy()

    if len(df_clean) == 0:
        return go.Figure().add_annotation(
            text="No complete profitability data available",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False,
            font=dict(size=14, color="gray")
        )

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=df_clean['GROSS_MARGIN'],
        y=df_clean['EBITDA_MARGIN'],
        mode='markers',
        marker=dict(
            size=10,
            color=df_clean['CUR_RATIO'] if 'CUR_RATIO' in df_clean.columns else '#3498db',
            colorscale='Viridis',
            showscale=True,
            colorbar=dict(title="Current<br>Ratio")
        ),
        text=df_clean['TICKER'],
        hovertemplate='<b>%{text}</b><br>Gross Margin: %{x:.2f}%<br>EBITDA Margin: %{y:.2f}%<extra></extra>'
    ))

    fig.update_layout(
        title="Profitability Analysis - Gross Margin vs EBITDA Margin",
        xaxis_title="Gross Margin (%)",
        yaxis_title="EBITDA Margin (%)",
        height=400,
        template="plotly_white"
    )

    return fig


# Callback for top performers chart
@app.callback(
    Output('top-performers-chart', 'figure'),
    Input('ratios-data-store', 'data')
)
def update_top_performers(data):
    """Create chart showing top performers by interest coverage ratio"""
    if not data or len(data) == 0:
        return go.Figure().add_annotation(
            text="No performance data available",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False,
            font=dict(size=14, color="gray")
        )

    df = pd.DataFrame(data)

    if 'TICKER' not in df.columns or 'INTEREST_COVERAGE_RATIO' not in df.columns:
        return go.Figure().add_annotation(
            text="Missing required columns for performance analysis",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False,
            font=dict(size=14, color="gray")
        )

    # Filter and get top 10 by interest coverage ratio
    df_clean = df[df['INTEREST_COVERAGE_RATIO'].notna()].copy()

    if len(df_clean) == 0:
        return go.Figure().add_annotation(
            text="No interest coverage data available",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False,
            font=dict(size=14, color="gray")
        )

    # Cap extreme values for better visualization
    df_clean['INTEREST_COVERAGE_RATIO_CAPPED'] = df_clean['INTEREST_COVERAGE_RATIO'].clip(upper=50)
    top_performers = df_clean.nlargest(10, 'INTEREST_COVERAGE_RATIO_CAPPED')

    fig = go.Figure()

    fig.add_trace(go.Bar(
        x=top_performers['TICKER'],
        y=top_performers['INTEREST_COVERAGE_RATIO_CAPPED'],
        marker=dict(
            color=top_performers['INTEREST_COVERAGE_RATIO_CAPPED'],
            colorscale='Greens',
            showscale=False
        ),
        text=top_performers['INTEREST_COVERAGE_RATIO_CAPPED'].round(2),
        textposition='auto',
        hovertemplate='<b>%{x}</b><br>Interest Coverage: %{y:.2f}x<extra></extra>'
    ))

    fig.update_layout(
        title="Top Performers - Interest Coverage Ratio",
        xaxis_title="Company",
        yaxis_title="Interest Coverage Ratio (x)",
        height=400,
        template="plotly_white",
        showlegend=False
    )

    return fig


# Callback for growth metrics chart
@app.callback(
    Output('growth-metrics-chart', 'figure'),
    Input('advanced-data-store', 'data')
)
def update_growth_metrics(data):
    """Create chart showing sales and net income growth - NOT AVAILABLE"""
    return go.Figure().add_annotation(
        text="Growth metrics not available in current schema",
        xref="paper", yref="paper",
        x=0.5, y=0.5, showarrow=False,
        font=dict(size=14, color="gray")
    )


# Callback for cash flow chart
@app.callback(
    Output('cash-flow-chart', 'figure'),
    Input('advanced-data-store', 'data')
)
def update_cash_flow_chart(data):
    """Create chart showing free cash flow - NOT AVAILABLE"""
    return go.Figure().add_annotation(
        text="Cash flow metrics not available in current schema",
        xref="paper", yref="paper",
        x=0.5, y=0.5, showarrow=False,
        font=dict(size=14, color="gray")
    )


# Populate competitor dropdown with all tickers except your company
@app.callback(
    Output('competitor-selector', 'options'),
    Input('ticker-list-store', 'data')
)
def populate_competitor_dropdown(tickers):
    """Populate dropdown with all available tickers from HANA"""
    if not tickers:
        return []
    # Exclude "KATB" (your company) from the list
    competitors = [t for t in tickers if t != 'KATB']
    return [{'label': ticker, 'value': ticker} for ticker in competitors]


# Update your company metrics (always show KatBotz/first ticker)
@app.callback(
    [Output('your-company-name', 'children'),
     Output('your-company-ebitda', 'children'),
     Output('your-company-current', 'children'),
     Output('your-company-gross', 'children')],
    Input('ratios-data-store', 'data')
)
def update_your_company_metrics(data):
    """Display your company metrics from HANA"""
    if not data or len(data) == 0:
        return "Your Company", "N/A", "N/A", "N/A"

    df = pd.DataFrame(data)

    # Get data for your company (KATB ticker or first in list)
    your_company = df[df['TICKER'] == 'KATB'] if 'KATB' in df['TICKER'].values else df.head(1)

    if your_company.empty:
        return "Your Company", "N/A", "N/A", "N/A"

    company_name = your_company['TICKER'].iloc[0]
    ebitda = your_company['EBITDA_MARGIN'].iloc[0] if 'EBITDA_MARGIN' in your_company.columns else 0
    current = your_company['CUR_RATIO'].iloc[0] if 'CUR_RATIO' in your_company.columns else 0
    gross = your_company['GROSS_MARGIN'].iloc[0] if 'GROSS_MARGIN' in your_company.columns else 0

    return (
        company_name,
        f"{ebitda:.1f}%" if pd.notna(ebitda) else "N/A",
        f"{current:.2f}" if pd.notna(current) else "N/A",
        f"{gross:.1f}%" if pd.notna(gross) else "N/A"
    )


# Update comparison bar chart based on selected competitors
@app.callback(
    Output('competitor-comparison-bar', 'figure'),
    [Input('competitor-selector', 'value'),
     Input('ratios-data-store', 'data')]
)
def update_competitor_bar_chart(selected_competitors, data):
    """Create bar chart comparing EBITDA margins"""
    if not data or len(data) == 0:
        return go.Figure().add_annotation(
            text="No data available",
            xref="paper", yref="paper", x=0.5, y=0.5,
            showarrow=False, font=dict(size=14, color="gray")
        )

    df = pd.DataFrame(data)

    # Start with your company
    companies = ['KATB'] if 'KATB' in df['TICKER'].values else [df['TICKER'].iloc[0]]

    # Add selected competitors
    if selected_competitors:
        companies.extend(selected_competitors)

    # Filter data for these companies
    comparison_df = df[df['TICKER'].isin(companies)]

    if comparison_df.empty or 'EBITDA_MARGIN' not in comparison_df.columns:
        return go.Figure().add_annotation(
            text="EBITDA Margin data not available",
            xref="paper", yref="paper", x=0.5, y=0.5,
            showarrow=False, font=dict(size=14, color="gray")
        )

    # Get latest value for each company
    latest_data = comparison_df.groupby('TICKER')['EBITDA_MARGIN'].first().reset_index()

    # Create colors - your company in blue, others in gray
    colors = ['#0ea5e9' if ticker == companies[0] else '#64748b'
              for ticker in latest_data['TICKER']]

    fig = go.Figure(data=[
        go.Bar(
            x=latest_data['TICKER'],
            y=latest_data['EBITDA_MARGIN'],
            marker_color=colors,
            text=[f"{v:.1f}%" if pd.notna(v) else "N/A" for v in latest_data['EBITDA_MARGIN']],
            textposition='auto',
        )
    ])

    fig.update_layout(
        title="EBITDA Margin Comparison",
        xaxis_title="Company",
        yaxis_title="EBITDA Margin (%)",
        height=350,
        plot_bgcolor='white',
        paper_bgcolor='white',
        font=dict(color='#334155'),
        xaxis=dict(gridcolor='#e2e8f0'),
        yaxis=dict(gridcolor='#e2e8f0'),
        showlegend=False
    )

    return fig


# Update radar chart
@app.callback(
    Output('competitor-radar-chart', 'figure'),
    [Input('competitor-selector', 'value'),
     Input('ratios-data-store', 'data')]
)
def update_competitor_radar(selected_competitors, data):
    """Create radar chart for multi-metric comparison"""
    if not data or len(data) == 0:
        return go.Figure().add_annotation(
            text="No data available",
            xref="paper", yref="paper", x=0.5, y=0.5,
            showarrow=False, font=dict(size=14, color="gray")
        )

    df = pd.DataFrame(data)

    # Metrics available in FINANCIAL_RATIOS
    metrics = ['EBITDA_MARGIN', 'CUR_RATIO', 'GROSS_MARGIN', 'INTEREST_COVERAGE_RATIO']
    metric_labels = ['EBITDA Margin', 'Current Ratio', 'Gross Margin', 'Interest Coverage']

    # Normalize function
    def normalize(value, metric):
        if pd.isna(value):
            return 0
        scales = {
            'EBITDA_MARGIN': 30,
            'CUR_RATIO': 3,
            'GROSS_MARGIN': 50,
            'INTEREST_COVERAGE_RATIO': 15
        }
        return min((value / scales.get(metric, 1)) * 100, 100)

    fig = go.Figure()

    # Your company
    your_company = df[df['TICKER'] == 'KATB'] if 'KATB' in df['TICKER'].values else df.head(1)
    if not your_company.empty:
        your_values = [normalize(your_company[m].iloc[0], m) for m in metrics]
        fig.add_trace(go.Scatterpolar(
            r=your_values + [your_values[0]],
            theta=metric_labels + [metric_labels[0]],
            fill='toself',
            name=your_company['TICKER'].iloc[0],
            line_color='#0ea5e9'
        ))

    # Add selected competitors
    if selected_competitors:
        colors = ['#22c55e', '#f59e0b', '#ef4444', '#8b5cf6']
        for idx, ticker in enumerate(selected_competitors[:4]):  # Max 4 competitors
            comp_data = df[df['TICKER'] == ticker]
            if not comp_data.empty:
                comp_values = [normalize(comp_data[m].iloc[0], m) for m in metrics]
                fig.add_trace(go.Scatterpolar(
                    r=comp_values + [comp_values[0]],
                    theta=metric_labels + [metric_labels[0]],
                    fill='toself',
                    name=ticker,
                    line_color=colors[idx % len(colors)],
                    opacity=0.6
                ))

    fig.update_layout(
        polar=dict(
            radialaxis=dict(visible=True, range=[0, 100], gridcolor='#e2e8f0'),
            angularaxis=dict(gridcolor='#e2e8f0')
        ),
        title="Performance Radar - Multi-Metric Comparison",
        height=350,
        plot_bgcolor='white',
        paper_bgcolor='white',
        font=dict(color='#334155'),
        showlegend=True
    )

    return fig


# Update comparison table
@app.callback(
    Output('competitor-comparison-table', 'children'),
    [Input('competitor-selector', 'value'),
     Input('ratios-data-store', 'data')]
)
def update_comparison_table(selected_competitors, data):
    """Create detailed comparison table from HANA data"""
    if not data or len(data) == 0:
        return html.P("No data available", className="text-muted")

    df = pd.DataFrame(data)

    # Start with your company
    companies = ['KATB'] if 'KATB' in df['TICKER'].values else [df['TICKER'].iloc[0]]

    # Add selected competitors
    if selected_competitors:
        companies.extend(selected_competitors)

    # Filter data
    comparison_df = df[df['TICKER'].isin(companies)]

    if comparison_df.empty:
        return html.P("No companies selected for comparison", className="text-muted")

    # Metrics from FINANCIAL_RATIOS table
    metrics = ['TOT_DEBT_TO_TOT_ASSET', 'EBITDA_MARGIN', 'CUR_RATIO', 'QUICK_RATIO', 'GROSS_MARGIN', 'INTEREST_COVERAGE_RATIO']
    metric_labels = ['Debt to Asset', 'EBITDA Margin (%)', 'Current Ratio', 'Quick Ratio', 'Gross Margin (%)', 'Interest Coverage']

    # Create table header with dynamic companies
    header_cells = [html.Th("Metric", style={"backgroundColor": "#f8fafc"})] + [
        html.Th(ticker, style={"color": "#0ea5e9" if ticker == companies[0] else "#64748b", "fontWeight": "bold", "backgroundColor": "#f8fafc"})
        for ticker in companies
    ]
    table_header = [html.Thead(html.Tr(header_cells))]

    # Helper function for color coding
    def get_cell_color(value, your_value, metric_name):
        if pd.isna(value) or pd.isna(your_value):
            return "#f1f5f9", "#64748b"  # light gray bg, gray text

        # For metrics where higher is better
        higher_is_better = ['EBITDA_MARGIN', 'CUR_RATIO', 'QUICK_RATIO', 'GROSS_MARGIN', 'INTEREST_COVERAGE_RATIO']

        if metric_name in higher_is_better:
            diff_pct = ((value - your_value) / abs(your_value)) * 100 if your_value != 0 else 0
        else:  # Lower is better (debt ratios)
            diff_pct = ((your_value - value) / abs(your_value)) * 100 if your_value != 0 else 0

        # Return background color and text color
        if diff_pct >= 20:
            return "#d1fae5", "#059669"  # strong green bg, dark green text
        elif diff_pct >= 10:
            return "#d1fae5", "#10b981"  # green bg, green text
        elif diff_pct >= 5:
            return "#d1fae5", "#34d399"  # light green bg, light green text
        elif diff_pct >= 0:
            return "#fef3c7", "#d97706"  # yellow bg, orange text
        elif diff_pct >= -10:
            return "#fed7aa", "#fb923c"  # light orange bg, orange text
        elif diff_pct >= -20:
            return "#fed7aa", "#f97316"  # orange bg, dark orange text
        else:
            return "#fecaca", "#dc2626"  # red bg, dark red text

    rows = []
    for metric, label in zip(metrics, metric_labels):
        if metric not in comparison_df.columns:
            continue

        row_cells = [html.Td(label, style={"fontWeight": "500", "backgroundColor": "#f8fafc"})]

        # Get your company's value for this metric
        your_company_data = comparison_df[comparison_df['TICKER'] == companies[0]]
        your_value = your_company_data[metric].iloc[0] if not your_company_data.empty else None

        for ticker in companies:
            ticker_data = comparison_df[comparison_df['TICKER'] == ticker]
            if not ticker_data.empty and metric in ticker_data.columns:
                value = ticker_data[metric].iloc[0]
                if pd.notna(value):
                    if ticker == companies[0]:
                        # Your company - blue style
                        cell_style = {"color": "#0ea5e9", "fontWeight": "bold", "backgroundColor": "#f0f9ff"}
                    else:
                        # Competitor - color coded
                        bg_color, text_color = get_cell_color(value, your_value, metric)
                        cell_style = {"backgroundColor": bg_color, "color": text_color, "fontWeight": "500"}
                    row_cells.append(html.Td(f"{value:.2f}", style=cell_style))
                else:
                    row_cells.append(html.Td("N/A", className="text-muted", style={"backgroundColor": "#f1f5f9"}))
            else:
                row_cells.append(html.Td("N/A", className="text-muted", style={"backgroundColor": "#f1f5f9"}))

        rows.append(html.Tr(row_cells))

    table_body = [html.Tbody(rows)]

    return dbc.Table(
        table_header + table_body,
        bordered=True,
        hover=True,
        responsive=True,
        striped=True,
        className="mb-0"
    )


# Dynamic metric visualization callback
@app.callback(
    Output('dynamic-metric-chart', 'figure'),
    [Input('dynamic-metric-selector', 'value'),
     Input('dynamic-chart-type', 'value'),
     Input('competitor-selector', 'value'),
     Input('ratios-data-store', 'data')]
)
def update_dynamic_metric_chart(metric, chart_type, selected_competitors, data):
    """Create dynamic chart based on selected metric and chart type"""
    if not data or len(data) == 0 or not metric:
        return go.Figure().add_annotation(
            text="No data available",
            xref="paper", yref="paper", x=0.5, y=0.5,
            showarrow=False, font=dict(size=14, color="gray")
        )

    df = pd.DataFrame(data)

    # Get your company ticker
    your_ticker = 'KATB' if 'KATB' in df['TICKER'].values else df['TICKER'].iloc[0]

    # Filter for selected companies
    companies = [your_ticker]
    if selected_competitors:
        companies.extend(selected_competitors)

    filtered_df = df[df['TICKER'].isin(companies)]

    if filtered_df.empty or metric not in filtered_df.columns:
        return go.Figure().add_annotation(
            text=f"{metric} data not available",
            xref="paper", yref="paper", x=0.5, y=0.5,
            showarrow=False, font=dict(size=14, color="gray")
        )

    # Get metric label
    metric_labels = {
        'EBITDA_MARGIN': 'EBITDA Margin (%)',
        'CUR_RATIO': 'Current Ratio',
        'QUICK_RATIO': 'Quick Ratio',
        'GROSS_MARGIN': 'Gross Margin (%)',
        'INTEREST_COVERAGE_RATIO': 'Interest Coverage Ratio',
        'TOT_DEBT_TO_TOT_ASSET': 'Debt to Asset Ratio',
        'NET_DEBT_TO_SHRHLDR_EQTY': 'Net Debt to Equity',
        'TOT_DEBT_TO_EBITDA': 'Debt to EBITDA'
    }
    metric_label = metric_labels.get(metric, metric)

    # Get your company's value for comparison
    your_value = filtered_df[filtered_df['TICKER'] == your_ticker][metric].iloc[0] if your_ticker in filtered_df['TICKER'].values else None

    # Color coding function: green if better than your company, yellow/red if worse
    def get_performance_color(value, your_val, metric_name):
        if pd.isna(value) or pd.isna(your_val):
            return '#94a3b8'  # gray for N/A

        # For metrics where higher is better
        higher_is_better = ['EBITDA_MARGIN', 'CUR_RATIO', 'QUICK_RATIO', 'GROSS_MARGIN', 'INTEREST_COVERAGE_RATIO']

        if metric_name in higher_is_better:
            diff_pct = ((value - your_val) / abs(your_val)) * 100 if your_val != 0 else 0
        else:  # Lower is better (debt ratios)
            diff_pct = ((your_val - value) / abs(your_val)) * 100 if your_val != 0 else 0

        # Color scale: dark red (worse) -> yellow -> light green -> dark green (better)
        if diff_pct >= 20:
            return '#059669'  # strong green
        elif diff_pct >= 10:
            return '#10b981'  # green
        elif diff_pct >= 5:
            return '#34d399'  # light green
        elif diff_pct >= 0:
            return '#fbbf24'  # yellow
        elif diff_pct >= -10:
            return '#fb923c'  # light orange
        elif diff_pct >= -20:
            return '#f97316'  # orange
        else:
            return '#dc2626'  # dark red

    fig = go.Figure()

    if chart_type == 'histogram':
        # Group by ticker and get first value
        chart_data = filtered_df.groupby('TICKER')[metric].first().reset_index()

        colors = [get_performance_color(row[metric], your_value, metric) if row['TICKER'] != your_ticker
                  else '#0ea5e9' for _, row in chart_data.iterrows()]

        fig.add_trace(go.Bar(
            x=chart_data['TICKER'],
            y=chart_data[metric],
            marker_color=colors,
            text=[f"{v:.2f}" if pd.notna(v) else "N/A" for v in chart_data[metric]],
            textposition='auto',
            hovertemplate='<b>%{x}</b><br>' + metric_label + ': %{y:.2f}<extra></extra>'
        ))

        fig.update_layout(
            title=f"{metric_label} - Histogram Comparison",
            xaxis_title="Company",
            yaxis_title=metric_label,
            height=450,
            plot_bgcolor='white',
            paper_bgcolor='white',
            font=dict(color='#334155'),
            xaxis=dict(gridcolor='#e2e8f0'),
            yaxis=dict(gridcolor='#e2e8f0'),
            showlegend=False,
            transition={'duration': 500}
        )

    elif chart_type == 'pie':
        # Group by ticker and get first value
        chart_data = filtered_df.groupby('TICKER')[metric].first().reset_index()
        chart_data = chart_data[chart_data[metric].notna()]

        colors = [get_performance_color(row[metric], your_value, metric) if row['TICKER'] != your_ticker
                  else '#0ea5e9' for _, row in chart_data.iterrows()]

        fig.add_trace(go.Pie(
            labels=chart_data['TICKER'],
            values=chart_data[metric],
            marker=dict(colors=colors),
            textinfo='label+percent',
            hovertemplate='<b>%{label}</b><br>' + metric_label + ': %{value:.2f}<br>Percent: %{percent}<extra></extra>'
        ))

        fig.update_layout(
            title=f"{metric_label} - Distribution",
            height=450,
            plot_bgcolor='white',
            paper_bgcolor='white',
            font=dict(color='#334155'),
            transition={'duration': 500}
        )

    elif chart_type == 'line':
        # Group by ticker and get first value, sort by value
        chart_data = filtered_df.groupby('TICKER')[metric].first().reset_index()
        chart_data = chart_data.sort_values(metric)

        colors = [get_performance_color(row[metric], your_value, metric) if row['TICKER'] != your_ticker
                  else '#0ea5e9' for _, row in chart_data.iterrows()]

        fig.add_trace(go.Scatter(
            x=chart_data['TICKER'],
            y=chart_data[metric],
            mode='lines+markers',
            line=dict(color='#64748b', width=2),
            marker=dict(
                size=12,
                color=colors,
                line=dict(width=2, color='white')
            ),
            text=[f"{v:.2f}" if pd.notna(v) else "N/A" for v in chart_data[metric]],
            hovertemplate='<b>%{x}</b><br>' + metric_label + ': %{y:.2f}<extra></extra>'
        ))

        fig.update_layout(
            title=f"{metric_label} - Trend Line",
            xaxis_title="Company (sorted by value)",
            yaxis_title=metric_label,
            height=450,
            plot_bgcolor='white',
            paper_bgcolor='white',
            font=dict(color='#334155'),
            xaxis=dict(gridcolor='#e2e8f0'),
            yaxis=dict(gridcolor='#e2e8f0'),
            showlegend=False,
            transition={'duration': 500}
        )

    return fig


# Update industry benchmark chart
@app.callback(
    Output('industry-benchmark-chart', 'figure'),
    [Input('competitor-selector', 'value'),
     Input('ratios-data-store', 'data')]
)
def update_industry_benchmark(selected_competitors, data):
    """Create industry benchmark chart"""
    if not data or len(data) == 0:
        return go.Figure().add_annotation(
            text="No data available",
            xref="paper", yref="paper", x=0.5, y=0.5,
            showarrow=False, font=dict(size=14, color="gray")
        )

    df = pd.DataFrame(data)

    # Your company
    your_company = df[df['TICKER'] == 'KATB'] if 'KATB' in df['TICKER'].values else df.head(1)

    if your_company.empty:
        return go.Figure().add_annotation(
            text="Your company data not found",
            xref="paper", yref="paper", x=0.5, y=0.5,
            showarrow=False, font=dict(size=14, color="gray")
        )

    # Calculate industry median from all companies in database
    metrics = ['EBITDA_MARGIN', 'CUR_RATIO', 'QUICK_RATIO', 'GROSS_MARGIN', 'INTEREST_COVERAGE_RATIO']
    metric_labels = ['EBITDA Margin', 'Current Ratio', 'Quick Ratio', 'Gross Margin', 'Interest Coverage']

    your_values = []
    median_values = []

    for metric in metrics:
        if metric in your_company.columns:
            your_val = your_company[metric].iloc[0]
            your_values.append(your_val if pd.notna(your_val) else 0)

            # Calculate median from all companies
            median_val = df[metric].median()
            median_values.append(median_val if pd.notna(median_val) else 0)
        else:
            your_values.append(0)
            median_values.append(0)

    fig = go.Figure()

    fig.add_trace(go.Bar(
        name='Your Company',
        x=metric_labels,
        y=your_values,
        marker_color='#0ea5e9',
        text=[f"{v:.1f}" for v in your_values],
        textposition='auto',
    ))

    fig.add_trace(go.Bar(
        name='Industry Median',
        x=metric_labels,
        y=median_values,
        marker_color='#22c55e',
        text=[f"{v:.1f}" for v in median_values],
        textposition='auto',
    ))

    fig.update_layout(
        title="Your Company vs Industry Median",
        xaxis_title="Metric",
        yaxis_title="Value",
        height=400,
        plot_bgcolor='white',
        paper_bgcolor='white',
        font=dict(color='#334155'),
        xaxis=dict(gridcolor='#e2e8f0'),
        yaxis=dict(gridcolor='#e2e8f0'),
        barmode='group',
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )

    return fig


# Industry Median Benchmarking Table
@app.callback(
    Output('industry-median-table', 'children'),
    [Input('competitor-selector', 'value'),
     Input('ratios-data-store', 'data')]
)
def update_industry_median_table(selected_competitors, data):
    """Create industry median benchmarking table"""
    if not data or len(data) == 0:
        return html.P("No data available", className="text-muted")

    df = pd.DataFrame(data)

    # Your company
    your_ticker = 'KATB' if 'KATB' in df['TICKER'].values else df['TICKER'].iloc[0]
    your_company = df[df['TICKER'] == your_ticker]

    if your_company.empty:
        return html.P("Your company data not found", className="text-muted")

    # Metrics for benchmarking
    metrics_config = [
        ('EBITDA_MARGIN', 'EBITDA Margin', '%', True),  # higher is better
        ('CUR_RATIO', 'Current Ratio', '', True),
        ('QUICK_RATIO', 'Quick Ratio', '', True),
        ('GROSS_MARGIN', 'Gross Margin', '%', True),
        ('TOT_DEBT_TO_TOT_ASSET', 'Debt/Asset', '', False)  # lower is better
    ]

    # Table header
    header_cells = [
        html.Th("Metric", style={"backgroundColor": "#f8fafc", "fontWeight": "bold"}),
        html.Th("Your Company", style={"backgroundColor": "#f8fafc", "fontWeight": "bold"}),
        html.Th("Industry Median", style={"backgroundColor": "#f8fafc", "fontWeight": "bold"}),
        html.Th("Difference", style={"backgroundColor": "#f8fafc", "fontWeight": "bold"}),
        html.Th("Interpretation", style={"backgroundColor": "#f8fafc", "fontWeight": "bold"})
    ]
    table_header = [html.Thead(html.Tr(header_cells))]

    rows = []
    for metric, label, unit, higher_better in metrics_config:
        if metric not in df.columns:
            continue

        your_val = your_company[metric].iloc[0] if not your_company.empty else None
        median_val = df[metric].median()

        if pd.notna(your_val) and pd.notna(median_val):
            diff = your_val - median_val
            diff_str = f"+{diff:.2f}{unit}" if diff > 0 else f"{diff:.2f}{unit}"

            # Interpretation
            if higher_better:
                if diff > 0:
                    interp = "Above median - positive"
                    color_style = {"backgroundColor": "#d1fae5", "color": "#059669"}
                else:
                    interp = "Below median - needs improvement"
                    color_style = {"backgroundColor": "#fecaca", "color": "#dc2626"}
            else:  # lower is better
                if diff < 0:
                    interp = "Below median - positive"
                    color_style = {"backgroundColor": "#d1fae5", "color": "#059669"}
                else:
                    interp = "Above median - needs improvement"
                    color_style = {"backgroundColor": "#fecaca", "color": "#dc2626"}

            rows.append(html.Tr([
                html.Td(label, style={"fontWeight": "500", "backgroundColor": "#f8fafc"}),
                html.Td(f"{your_val:.2f}{unit}", style={"backgroundColor": "#f0f9ff", "color": "#0ea5e9", "fontWeight": "bold"}),
                html.Td(f"{median_val:.2f}{unit}", style={"backgroundColor": "#fafafa"}),
                html.Td(diff_str, style=color_style),
                html.Td(interp, style=color_style)
            ]))

    table_body = [html.Tbody(rows)]

    return dbc.Table(
        table_header + table_body,
        bordered=True,
        hover=True,
        responsive=True,
        striped=True,
        className="mb-0"
    )


# Z-Score Credit Risk Analysis Table
@app.callback(
    Output('zscore-risk-table', 'children'),
    [Input('competitor-selector', 'value'),
     Input('ratios-data-store', 'data')]
)
def update_zscore_table(selected_competitors, data):
    """Create Z-Score credit risk analysis table"""
    if not data or len(data) == 0:
        return html.P("No data available", className="text-muted")

    df = pd.DataFrame(data)

    # Get your company ticker
    your_ticker = 'KATB' if 'KATB' in df['TICKER'].values else df['TICKER'].iloc[0]

    # Filter for selected companies
    companies = [your_ticker]
    if selected_competitors:
        companies.extend(selected_competitors[:4])  # Limit to 5 total

    filtered_df = df[df['TICKER'].isin(companies)]

    # Calculate simplified Z-Score (using available metrics)
    def calculate_zscore(row):
        """Simplified Z-Score calculation using available ratios"""
        # Z = 1.2*WC/TA + 1.4*RE/TA + 3.3*EBIT/TA + 0.6*ME/TL + 1.0*Sales/TA
        # Using available proxies from FINANCIAL_RATIOS
        try:
            cur_ratio = row.get('CUR_RATIO', 2.0)
            ebitda_margin = row.get('EBITDA_MARGIN', 15.0) / 100
            debt_to_asset = row.get('TOT_DEBT_TO_TOT_ASSET', 0.5)

            # Simplified calculation (demonstration)
            score = (1.5 * cur_ratio) + (3.0 * ebitda_margin) + (2.0 * (1 - debt_to_asset))
            return max(0, min(score, 5.0))  # Cap between 0 and 5
        except:
            return 2.5  # Default mid-range score

    z_scores = []
    for ticker in companies:
        ticker_data = filtered_df[filtered_df['TICKER'] == ticker]
        if not ticker_data.empty:
            score = calculate_zscore(ticker_data.iloc[0])
            z_scores.append({'TICKER': ticker, 'Z_SCORE': score})

    if not z_scores:
        return html.P("Unable to calculate Z-Scores", className="text-muted")

    # Risk categories
    def get_risk_category(score):
        if score >= 3.0:
            return "Safe", "#d1fae5", "#059669"
        elif score >= 1.8:
            return "Grey Zone", "#fef3c7", "#d97706"
        else:
            return "Distress", "#fecaca", "#dc2626"

    # Table header
    header_cells = [
        html.Th("Company", style={"backgroundColor": "#f8fafc", "fontWeight": "bold"}),
        html.Th("Z-Score", style={"backgroundColor": "#f8fafc", "fontWeight": "bold"}),
        html.Th("Risk Category", style={"backgroundColor": "#f8fafc", "fontWeight": "bold"})
    ]
    table_header = [html.Thead(html.Tr(header_cells))]

    rows = []
    for item in z_scores:
        ticker = item['TICKER']
        score = item['Z_SCORE']
        category, bg_color, text_color = get_risk_category(score)

        is_your_company = (ticker == your_ticker)

        company_style = {"backgroundColor": "#f0f9ff", "color": "#0ea5e9", "fontWeight": "bold"} if is_your_company else {"backgroundColor": "#fafafa"}

        company_label = html.Div([
            html.Span(ticker),
            html.Br(),
            html.Small("You", style={"color": "#0ea5e9", "fontSize": "0.75rem"}) if is_your_company else html.Span()
        ])

        rows.append(html.Tr([
            html.Td(company_label, style=company_style),
            html.Td(f"{score:.1f}", style={"backgroundColor": bg_color, "color": text_color, "fontWeight": "bold"}),
            html.Td(category, style={"backgroundColor": bg_color, "color": text_color, "fontWeight": "500"})
        ]))

    table_body = [html.Tbody(rows)]

    # Add legend
    legend = html.Div([
        html.Small([
            html.Span("Risk Levels: ", style={"fontWeight": "bold"}),
            html.Span("Safe: > 3.0", style={"color": "#059669", "marginRight": "10px"}),
            html.Span("Grey: 1.8–3.0", style={"color": "#d97706", "marginRight": "10px"}),
            html.Span("Distress: < 1.8", style={"color": "#dc2626"})
        ], className="text-muted mt-2 d-block")
    ])

    return html.Div([
        dbc.Table(
            table_header + table_body,
            bordered=True,
            hover=True,
            responsive=True,
            striped=True,
            className="mb-2"
        ),
        legend
    ])


# Stacked EBITDA Margin Chart (Horizontal Bar Chart)
@app.callback(
    Output('stacked-ebitda-chart', 'figure'),
    [Input('competitor-selector', 'value'),
     Input('ratios-data-store', 'data')]
)
def update_stacked_ebitda_chart(selected_competitors, data):
    """Create horizontal stacked bar chart for EBITDA margins"""
    if not data or len(data) == 0:
        return go.Figure().add_annotation(
            text="No data available",
            xref="paper", yref="paper", x=0.5, y=0.5,
            showarrow=False, font=dict(size=14, color="gray")
        )

    df = pd.DataFrame(data)

    # Get your company ticker
    your_ticker = 'KATB' if 'KATB' in df['TICKER'].values else df['TICKER'].iloc[0]

    # Filter for selected companies
    companies = [your_ticker]
    if selected_competitors:
        companies.extend(selected_competitors[:5])  # Limit to 6 total

    filtered_df = df[df['TICKER'].isin(companies)]

    if filtered_df.empty or 'EBITDA_MARGIN' not in filtered_df.columns:
        return go.Figure().add_annotation(
            text="EBITDA Margin data not available",
            xref="paper", yref="paper", x=0.5, y=0.5,
            showarrow=False, font=dict(size=14, color="gray")
        )

    # Get latest value for each company and sort
    chart_data = filtered_df.groupby('TICKER')['EBITDA_MARGIN'].first().reset_index()
    chart_data = chart_data.sort_values('EBITDA_MARGIN', ascending=True)

    # Get your company's value
    your_value = chart_data[chart_data['TICKER'] == your_ticker]['EBITDA_MARGIN'].iloc[0] if your_ticker in chart_data['TICKER'].values else None

    # Color code based on performance
    colors = []
    for _, row in chart_data.iterrows():
        if row['TICKER'] == your_ticker:
            colors.append('#0ea5e9')  # Blue for your company
        elif pd.notna(your_value):
            diff_pct = ((row['EBITDA_MARGIN'] - your_value) / abs(your_value)) * 100
            if diff_pct >= 10:
                colors.append('#059669')  # Strong green
            elif diff_pct >= 5:
                colors.append('#10b981')  # Green
            elif diff_pct >= 0:
                colors.append('#34d399')  # Light green
            elif diff_pct >= -10:
                colors.append('#fb923c')  # Orange
            else:
                colors.append('#dc2626')  # Red
        else:
            colors.append('#64748b')  # Gray

    fig = go.Figure()

    fig.add_trace(go.Bar(
        y=chart_data['TICKER'],
        x=chart_data['EBITDA_MARGIN'],
        orientation='h',
        marker_color=colors,
        text=[f"{v:.1f}%" if pd.notna(v) else "N/A" for v in chart_data['EBITDA_MARGIN']],
        textposition='auto',
        hovertemplate='<b>%{y}</b><br>EBITDA Margin: %{x:.2f}%<extra></extra>'
    ))

    fig.update_layout(
        title="EBITDA Margin - Horizontal Comparison",
        xaxis_title="EBITDA Margin (%)",
        yaxis_title="",
        height=400,
        plot_bgcolor='white',
        paper_bgcolor='white',
        font=dict(color='#334155'),
        xaxis=dict(gridcolor='#e2e8f0'),
        yaxis=dict(gridcolor='#e2e8f0'),
        showlegend=False,
        margin=dict(l=100)
    )

    return fig


# Callback for explorer table
@app.callback(
    Output('explorer-table-container', 'children'),
    [Input('explorer-table-dropdown', 'value'),
     Input('explorer-limit-slider', 'value')]
)
def update_explorer_table(table_type, limit):
    """Update data explorer table"""
    if table_type == 'ratios':
        df = data_service.get_financial_ratios(limit=limit)
    else:
        df = data_service.get_advanced_financials(limit=limit)

    if df is None or df.empty or len(df) == 0:
        return html.Div("No data available", className="text-center text-muted")

    # Create table
    return dbc.Table.from_dataframe(
        df.head(limit),
        striped=True,
        bordered=True,
        hover=True,
        responsive=True,
        size='sm',
        className='table-sm'
    )


# Callback for ratios detail chart
@app.callback(
    Output('ratios-detail-chart', 'figure'),
    [Input('ratios-ticker-dropdown', 'value'),
     Input('ratios-metric-dropdown', 'value')],
    State('ratios-data-store', 'data')
)
def update_ratios_detail_chart(ticker, metric, data):
    """Update detailed ratio chart for selected ticker and metric"""
    if not data or not ticker or not metric:
        return go.Figure().add_annotation(
            text="Please select a company and metric",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False,
            font=dict(size=14, color="gray")
        )

    df = pd.DataFrame(data)
    ticker_data = df[df['TICKER'] == ticker]

    if ticker_data.empty or metric not in ticker_data.columns:
        return go.Figure().add_annotation(
            text=f"No data available for {ticker}",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False,
            font=dict(size=14, color="gray")
        )

    fig = go.Figure()
    fig.add_trace(go.Indicator(
        mode="number+gauge",
        value=ticker_data[metric].iloc[0] if not pd.isna(ticker_data[metric].iloc[0]) else 0,
        title={'text': f"{ticker} - {metric.replace('_', ' ').title()}"},
        gauge={'axis': {'range': [None, df[metric].max() * 1.2]},
               'bar': {'color': "#3498db"}}
    ))

    fig.update_layout(height=400, template="plotly_white")
    return fig


# Callback for comparison chart
@app.callback(
    Output('comparison-chart', 'figure'),
    [Input('comparison-tickers-dropdown', 'value'),
     Input('comparison-metric-dropdown', 'value')],
    State('ratios-data-store', 'data')
)
def update_comparison_chart(tickers, metric, data):
    """Update company comparison chart"""
    if not data or not tickers or not metric:
        return go.Figure().add_annotation(
            text="Please select 2-5 companies and a metric to compare",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False,
            font=dict(size=14, color="gray")
        )

    if len(tickers) < 2:
        return go.Figure().add_annotation(
            text="Please select at least 2 companies",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False,
            font=dict(size=14, color="gray")
        )

    df = pd.DataFrame(data)
    comparison_data = df[df['TICKER'].isin(tickers)]

    if comparison_data.empty or metric not in comparison_data.columns:
        return go.Figure().add_annotation(
            text="No data available for selected companies",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False,
            font=dict(size=14, color="gray")
        )

    # Group by ticker and get latest value
    latest_data = comparison_data.groupby('TICKER')[metric].first().reset_index()

    fig = go.Figure(data=[
        go.Bar(
            x=latest_data['TICKER'],
            y=latest_data[metric],
            marker_color='#3498db',
            text=latest_data[metric].round(2),
            textposition='auto'
        )
    ])

    fig.update_layout(
        title=f"Company Comparison - {metric.replace('_', ' ').title()}",
        xaxis_title="Company",
        yaxis_title=metric.replace('_', ' ').title(),
        height=400,
        template="plotly_white",
        showlegend=False
    )
    return fig


# Callback for collapsible metrics section
@app.callback(
    [Output("collapse-metrics", "is_open"),
     Output("metrics-toggle-icon", "className")],
    [Input("collapse-metrics-button", "n_clicks")],
    [State("collapse-metrics", "is_open")],
)
def toggle_metrics(n, is_open):
    if n:
        if is_open:
            return False, "fas fa-chevron-down ms-2"
        else:
            return True, "fas fa-chevron-up ms-2"
    return is_open, "fas fa-chevron-down ms-2"


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    debug = os.getenv('DASH_DEBUG', 'false').lower() == 'true'
    app.run_server(
        host='0.0.0.0',
        port=port,
        debug=debug
    )
