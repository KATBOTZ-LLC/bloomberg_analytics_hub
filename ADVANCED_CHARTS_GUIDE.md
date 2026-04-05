# Advanced Charts Integration Guide

## 🎨 Available Chart Types

### 1. **Waterfall Chart** - Revenue/Profit Bridges
Perfect for showing how values change from one period to another.

**Use Cases:**
- Revenue bridge from Q1 to Q2
- Profit variance analysis
- Cost breakdown changes
- Budget vs Actual analysis

**Example:**
```python
from utils.advanced_charts import AdvancedCharts

charts = AdvancedCharts()

categories = ['Q1 Revenue', 'Sales Growth', 'Price Increase',
              'Volume Decrease', 'New Products', 'Q2 Revenue']
values = [1000000, 150000, 80000, -50000, 120000, 0]
values[-1] = sum(values[:-1])  # Calculate final total

fig = charts.create_waterfall_chart(categories, values, "Revenue Bridge Q1 to Q2")
```

---

### 2. **Sankey Diagram** - Flow Analysis
Shows how revenue/costs flow through different channels.

**Use Cases:**
- Revenue distribution by product and region
- Cost allocation flow
- Customer journey paths
- Resource allocation

**Example:**
```python
labels = ['Total Revenue', 'Product A', 'Product B',
          'North Region', 'South Region']

sources = [0, 0, 1, 2]  # From indices
targets = [1, 2, 3, 4]  # To indices
values = [500, 300, 500, 300]

fig = charts.create_sankey_diagram(sources, targets, values, labels,
                                   "Revenue Flow Analysis")
```

---

### 3. **Heatmap** - Performance Matrix
Visualizes performance scores across dimensions.

**Use Cases:**
- Product performance by quarter
- Regional sales performance
- Correlation matrices
- Risk assessments

**Example:**
```python
# Performance scores (%)
data = [
    [95, 87, 92, 78],  # Product A by quarters
    [88, 91, 85, 82],  # Product B by quarters
    [76, 82, 88, 91]   # Product C by quarters
]

x_labels = ['Q1', 'Q2', 'Q3', 'Q4']
y_labels = ['Product A', 'Product B', 'Product C']

fig = charts.create_heatmap(data, x_labels, y_labels,
                            "Quarterly Performance")
```

---

### 4. **Treemap** - Hierarchical Breakdown
Shows proportional distribution in a space-efficient way.

**Use Cases:**
- Revenue breakdown by division
- Cost structure analysis
- Market share distribution
- Portfolio composition

**Example:**
```python
labels = ['Total', 'Products', 'Services',
          'Product A', 'Product B', 'Service X', 'Service Y']
parents = ['', 'Total', 'Total',
           'Products', 'Products', 'Services', 'Services']
values = [0, 0, 0, 500, 300, 400, 350]

fig = charts.create_treemap(labels, parents, values,
                            "Revenue Distribution")
```

---

### 5. **Sunburst Chart** - Multi-Level Hierarchies
Similar to treemap but radial layout.

**Use Cases:**
- Multi-level organizational view
- Nested budget breakdowns
- Directory structures
- Complex category analysis

**Example:**
```python
# Same data as treemap
fig = charts.create_sunburst(labels, parents, values,
                             "Hierarchical View")
```

---

### 6. **Funnel Chart** - Conversion Analysis
Tracks conversion rates through stages.

**Use Cases:**
- Sales pipeline
- Customer journey
- Application process
- Multi-step workflows

**Example:**
```python
stages = ['Leads', 'Qualified', 'Proposal', 'Negotiation', 'Closed Won']
values = [1000, 650, 380, 210, 150]

fig = charts.create_funnel_chart(stages, values, "Sales Pipeline")
```

---

### 7. **3D Surface** - Complex Relationships (Advanced)
For advanced multi-dimensional analysis.

**Use Cases:**
- Revenue by price and volume
- Risk/return surfaces
- Optimization scenarios
- Statistical modeling

**Example:**
```python
import numpy as np

x = np.linspace(0, 10, 50)
y = np.linspace(0, 10, 50)
z = np.outer(np.sin(x), np.cos(y))

fig = charts.create_3d_surface(x, y, z, "Performance Surface")
```

---

## 🚀 Quick Start

### 1. View the Demo

```bash
python3 demo_advanced_charts.py
```

Then open: http://127.0.0.1:8050

### 2. Integration into Main Dashboard

Add to your existing `app.py`:

```python
from utils.advanced_charts import AdvancedCharts

# Initialize charts
advanced_charts = AdvancedCharts(colors=COLORS)

# In your layout, add a new section:
html.Div([
    dbc.Card([
        dbc.CardHeader("Revenue Bridge Analysis"),
        dbc.CardBody([
            dcc.Graph(
                figure=advanced_charts.create_waterfall_chart(
                    categories=['Q1', 'Growth', 'Q2'],
                    values=[1000, 200, 0],
                    title="Revenue Bridge"
                ),
                config=advanced_charts.create_responsive_config(),
                style={'height': '450px'}
            )
        ])
    ])
], className="mb-4")
```

---

## 📊 Responsive Configuration

All charts include responsive configuration:

```python
config = charts.create_responsive_config()

# Features:
# - Auto-resize to container
# - Display mode bar for interactions
# - Export to PNG (high resolution)
# - Zoom, pan, reset capabilities
# - Clean download filename
```

---

## 🎨 Customization

### Custom Colors

```python
custom_colors = {
    'primary': '#0066cc',
    'success': '#10b981',
    'warning': '#f59e0b',
    'danger': '#ef4444',
    'info': '#3b82f6',
    # ... more colors
}

charts = AdvancedCharts(colors=custom_colors)
```

### Chart Heights

```python
# Make charts taller for more detail
dcc.Graph(figure=fig, style={'height': '600px'})

# Make charts compact
dcc.Graph(figure=fig, style={'height': '350px'})
```

### Dark Mode Support

Charts automatically use transparent backgrounds, so they work with dark mode!

---

## 💡 Best Practices

### 1. Choose the Right Chart

| Data Type | Best Chart |
|-----------|------------|
| Change over time | Waterfall |
| Flow/distribution | Sankey |
| Matrix comparisons | Heatmap |
| Hierarchical breakdown | Treemap/Sunburst |
| Conversion rates | Funnel |
| 3D relationships | 3D Surface |

### 2. Keep It Simple

- Don't use more than 7-10 categories in waterfall charts
- Limit Sankey diagrams to 2-3 levels
- Use heatmaps for up to 10x10 matrices
- Treemaps work best with 2-3 hierarchy levels

### 3. Label Clearly

- Use descriptive titles
- Add units ($, %, etc.)
- Format large numbers (1.5M instead of 1500000)
- Include tooltips for details

### 4. Performance

- For large datasets, consider data aggregation
- Use responsive config for auto-sizing
- Set reasonable height limits

---

## 🔧 Integration Examples

### Add Waterfall to Existing Dashboard

```python
# In app.py, add to your layout:

html.Div([
    html.H3("Revenue Analysis", className="mb-3"),

    dbc.Row([
        # Existing chart (keep as is)
        dbc.Col([
            dcc.Graph(figure=existing_revenue_chart)
        ], width=6),

        # New waterfall chart
        dbc.Col([
            dcc.Graph(
                figure=advanced_charts.create_waterfall_chart(
                    categories=revenue_categories,
                    values=revenue_changes,
                    title="Revenue Bridge"
                ),
                config=advanced_charts.create_responsive_config()
            )
        ], width=6)
    ])
], className="mb-4")
```

### Add to Tabbed Section

```python
dbc.Tabs([
    dbc.Tab(label="Overview", children=[
        # Existing overview content
    ]),

    dbc.Tab(label="Advanced Analytics", children=[
        html.Div([
            # Waterfall
            dcc.Graph(figure=waterfall_fig),

            # Heatmap
            dcc.Graph(figure=heatmap_fig),

            # Sankey
            dcc.Graph(figure=sankey_fig)
        ])
    ])
])
```

---

## 📱 Mobile Responsive

All charts are mobile-responsive:

```python
# The responsive config ensures charts:
# - Auto-resize on mobile devices
# - Maintain aspect ratio
# - Show appropriate toolbar
# - Enable touch interactions

config = charts.create_responsive_config()
```

---

## 📥 Export Features

Users can export charts:
1. Click camera icon on chart
2. Downloads high-res PNG (1200x800, 2x scale)
3. Filename: `chart_export.png`

To customize:

```python
config = {
    'toImageButtonOptions': {
        'format': 'png',
        'filename': 'revenue_analysis_2026',
        'height': 1000,
        'width': 1600,
        'scale': 2
    }
}
```

---

## 🎯 Real-World Use Cases

### 1. Executive Dashboard
- **Waterfall**: YoY revenue change
- **Treemap**: Revenue by division
- **Heatmap**: Regional performance

### 2. Financial Analysis
- **Waterfall**: Profit bridge
- **Sankey**: Cost flow
- **Funnel**: Lead-to-cash

### 3. Product Analytics
- **Heatmap**: Product performance matrix
- **Treemap**: Market share
- **Sunburst**: Category hierarchy

---

## 🐛 Troubleshooting

### Charts Not Displaying

```python
# Make sure to import:
from utils.advanced_charts import AdvancedCharts

# Initialize before use:
charts = AdvancedCharts()
```

### Responsive Not Working

```python
# Use the config:
dcc.Graph(
    figure=fig,
    config=charts.create_responsive_config()  # Don't forget this!
)
```

### Colors Not Matching

```python
# Pass your COLORS dict:
charts = AdvancedCharts(colors=COLORS)
```

---

## ✅ Summary

- ✅ 7 advanced chart types ready to use
- ✅ All responsive and mobile-friendly
- ✅ Export-ready (PNG download)
- ✅ Dark mode compatible
- ✅ Easy integration with existing dashboard
- ✅ Professional financial styling

Run the demo to see them all in action:
```bash
python3 demo_advanced_charts.py
```
