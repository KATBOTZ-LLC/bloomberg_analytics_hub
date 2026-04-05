#!/usr/bin/env python3
"""
Demo: Advanced Chart Visualizations
Run this to see all the advanced chart types in action
"""

import dash
from dash import dcc, html
import dash_bootstrap_components as dbc
from utils.advanced_charts import (
    AdvancedCharts,
    example_waterfall,
    example_sankey,
    example_heatmap,
    example_treemap,
    example_funnel
)

# Initialize Dash app
app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])

# Create charts
waterfall = example_waterfall()
sankey = example_sankey()
heatmap = example_heatmap()
treemap = example_treemap()
funnel = example_funnel()

# Get responsive config
charts = AdvancedCharts()
config = charts.create_responsive_config()

# Layout
app.layout = dbc.Container([
    html.H1("Advanced Chart Visualizations Demo", className="my-4"),

    html.P("Professional financial charts with responsive design", className="lead mb-5"),

    # Waterfall Chart
    dbc.Card([
        dbc.CardHeader(html.H4("1. Waterfall Chart - Revenue Bridge Analysis")),
        dbc.CardBody([
            html.P("Perfect for showing how values change from one period to another. "
                  "Great for variance analysis and explaining revenue/profit changes."),
            dcc.Graph(figure=waterfall, config=config, style={'height': '450px'})
        ])
    ], className="mb-4"),

    # Sankey Diagram
    dbc.Card([
        dbc.CardHeader(html.H4("2. Sankey Diagram - Flow Analysis")),
        dbc.CardBody([
            html.P("Shows flow of revenue/costs through different channels. "
                  "Ideal for understanding distribution patterns."),
            dcc.Graph(figure=sankey, config=config, style={'height': '550px'})
        ])
    ], className="mb-4"),

    # Heatmap
    dbc.Card([
        dbc.CardHeader(html.H4("3. Heatmap - Performance Matrix")),
        dbc.CardBody([
            html.P("Visualizes performance scores across products and time periods. "
                  "Quick way to spot high/low performers."),
            dcc.Graph(figure=heatmap, config=config, style={'height': '450px'})
        ])
    ], className="mb-4"),

    # Treemap
    dbc.Card([
        dbc.CardHeader(html.H4("4. Treemap - Hierarchical Breakdown")),
        dbc.CardBody([
            html.P("Shows proportional distribution in a space-efficient way. "
                  "Perfect for revenue/cost breakdowns."),
            dcc.Graph(figure=treemap, config=config, style={'height': '550px'})
        ])
    ], className="mb-4"),

    # Funnel Chart
    dbc.Card([
        dbc.CardHeader(html.H4("5. Funnel Chart - Conversion Analysis")),
        dbc.CardBody([
            html.P("Tracks conversion rates through stages. "
                  "Ideal for sales pipelines and customer journeys."),
            dcc.Graph(figure=funnel, config=config, style={'height': '450px'})
        ])
    ], className="mb-4"),

    # Usage Instructions
    dbc.Card([
        dbc.CardHeader(html.H4("How to Use in Your Dashboard")),
        dbc.CardBody([
            html.H5("Step 1: Import the charts"),
            html.Pre("""from utils.advanced_charts import AdvancedCharts

charts = AdvancedCharts()""", style={'background': '#f8f9fa', 'padding': '10px'}),

            html.H5("Step 2: Create a chart", className="mt-3"),
            html.Pre("""# Example: Waterfall chart
categories = ['Start', 'Increase', 'Decrease', 'End']
values = [1000, 500, -200, 0]
values[-1] = sum(values[:-1])  # Calculate total

fig = charts.create_waterfall_chart(categories, values, "My Analysis")""",
                    style={'background': '#f8f9fa', 'padding': '10px'}),

            html.H5("Step 3: Add to your layout", className="mt-3"),
            html.Pre("""dcc.Graph(
    figure=fig,
    config=charts.create_responsive_config(),
    style={'height': '450px'}
)""", style={'background': '#f8f9fa', 'padding': '10px'}),

            html.H5("Available Chart Types:", className="mt-4"),
            html.Ul([
                html.Li([html.Strong("Waterfall: "), "Revenue bridges, variance analysis"]),
                html.Li([html.Strong("Sankey: "), "Flow analysis, distribution patterns"]),
                html.Li([html.Strong("Heatmap: "), "Performance matrices, correlations"]),
                html.Li([html.Strong("Treemap: "), "Hierarchical breakdowns, proportions"]),
                html.Li([html.Strong("Sunburst: "), "Multi-level hierarchies"]),
                html.Li([html.Strong("Funnel: "), "Conversion analysis, pipelines"]),
                html.Li([html.Strong("3D Surface: "), "Complex relationships (advanced)"]),
            ])
        ])
    ], className="mb-4"),

    html.Footer([
        html.Hr(),
        html.P("All charts are responsive and export-ready. "
              "Click the camera icon to download as PNG.",
              className="text-muted text-center")
    ])

], fluid=True)

if __name__ == '__main__':
    print("\n" + "="*70)
    print("ADVANCED CHARTS DEMO")
    print("="*70)
    print("\nStarting demo server...")
    print("Open your browser to: http://127.0.0.1:8050")
    print("\nPress Ctrl+C to stop the server")
    print("="*70 + "\n")

    app.run_server(debug=True, port=8050)
