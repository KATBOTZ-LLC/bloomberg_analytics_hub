"""
Advanced Visualization Components
Professional chart types for financial dashboards
"""

import plotly.graph_objs as go
import plotly.express as px
import pandas as pd
import numpy as np


class AdvancedCharts:
    """Collection of advanced, responsive chart templates"""

    def __init__(self, colors=None):
        """Initialize with color scheme"""
        self.colors = colors or {
            'primary': '#0066cc',
            'success': '#10b981',
            'warning': '#f59e0b',
            'danger': '#ef4444',
            'info': '#3b82f6',
            'gray': {
                '50': '#f9fafb',
                '100': '#f3f4f6',
                '200': '#e5e7eb',
                '300': '#d1d5db',
                '400': '#9ca3af',
                '500': '#6b7280',
                '600': '#4b5563',
                '700': '#374151',
                '800': '#1f2937'
            }
        }

    def create_waterfall_chart(self, categories, values, title="Waterfall Analysis"):
        """
        Create a waterfall chart for variance analysis

        Args:
            categories: List of category names
            values: List of values (positive/negative changes)
            title: Chart title

        Returns:
            plotly figure
        """
        # Calculate cumulative values
        cumulative = []
        running_total = 0
        for val in values:
            cumulative.append(running_total)
            running_total += val

        # Determine colors (green for positive, red for negative)
        colors_list = [self.colors['success'] if v >= 0 else self.colors['danger'] for v in values]

        fig = go.Figure()

        # Add waterfall bars
        fig.add_trace(go.Waterfall(
            name="",
            orientation="v",
            measure=["relative"] * (len(categories) - 1) + ["total"],
            x=categories,
            y=values,
            text=[f"${v:,.0f}" for v in values],
            textposition="outside",
            connector={"line": {"color": self.colors['gray']['400'], "width": 2, "dash": "dot"}},
            increasing={"marker": {"color": self.colors['success']}},
            decreasing={"marker": {"color": self.colors['danger']}},
            totals={"marker": {"color": self.colors['primary']}}
        ))

        fig.update_layout(
            title=title,
            showlegend=False,
            height=400,
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)',
            font=dict(color=self.colors['gray']['600'], size=12),
            xaxis=dict(
                title="",
                showgrid=False
            ),
            yaxis=dict(
                title="Value ($)",
                gridcolor=self.colors['gray']['200']
            ),
            margin=dict(l=50, r=50, t=80, b=50)
        )

        return fig

    def create_sankey_diagram(self, sources, targets, values, labels, title="Flow Analysis"):
        """
        Create a Sankey diagram for flow visualization

        Args:
            sources: List of source node indices
            targets: List of target node indices
            values: List of flow values
            labels: List of node labels
            title: Chart title

        Returns:
            plotly figure
        """
        # Create color palette for nodes
        node_colors = [self.colors['primary'], self.colors['info'],
                      self.colors['success'], self.colors['warning'],
                      self.colors['danger']] * (len(labels) // 5 + 1)

        fig = go.Figure(data=[go.Sankey(
            node=dict(
                pad=15,
                thickness=20,
                line=dict(color="white", width=2),
                label=labels,
                color=node_colors[:len(labels)]
            ),
            link=dict(
                source=sources,
                target=targets,
                value=values,
                color=[f"rgba(0, 102, 204, 0.3)"] * len(sources)
            )
        )])

        fig.update_layout(
            title=title,
            height=500,
            font=dict(size=12, color=self.colors['gray']['600']),
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)',
            margin=dict(l=20, r=20, t=60, b=20)
        )

        return fig

    def create_heatmap(self, data, x_labels, y_labels, title="Heatmap Analysis"):
        """
        Create a heatmap for correlation or performance matrix

        Args:
            data: 2D array of values
            x_labels: Labels for x-axis
            y_labels: Labels for y-axis
            title: Chart title

        Returns:
            plotly figure
        """
        fig = go.Figure(data=go.Heatmap(
            z=data,
            x=x_labels,
            y=y_labels,
            colorscale=[
                [0, self.colors['danger']],
                [0.5, self.colors['warning']],
                [1, self.colors['success']]
            ],
            text=[[f"{val:.1f}%" for val in row] for row in data],
            texttemplate="%{text}",
            textfont={"size": 10},
            hoverongaps=False,
            showscale=True,
            colorbar=dict(
                title="Score",
                ticksuffix="%"
            )
        ))

        fig.update_layout(
            title=title,
            height=400,
            xaxis=dict(title="", side="bottom"),
            yaxis=dict(title=""),
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)',
            font=dict(color=self.colors['gray']['600'], size=12),
            margin=dict(l=100, r=50, t=80, b=50)
        )

        return fig

    def create_3d_surface(self, x_data, y_data, z_data, title="3D Performance Surface"):
        """
        Create a 3D surface chart

        Args:
            x_data: X-axis data
            y_data: Y-axis data
            z_data: Z-axis data (2D array)
            title: Chart title

        Returns:
            plotly figure
        """
        fig = go.Figure(data=[go.Surface(
            x=x_data,
            y=y_data,
            z=z_data,
            colorscale=[
                [0, self.colors['danger']],
                [0.3, self.colors['warning']],
                [0.7, self.colors['info']],
                [1, self.colors['success']]
            ],
            showscale=True,
            colorbar=dict(title="Value")
        )])

        fig.update_layout(
            title=title,
            height=600,
            scene=dict(
                xaxis=dict(title="X Axis", gridcolor=self.colors['gray']['300']),
                yaxis=dict(title="Y Axis", gridcolor=self.colors['gray']['300']),
                zaxis=dict(title="Performance", gridcolor=self.colors['gray']['300']),
                bgcolor='rgba(0,0,0,0)'
            ),
            paper_bgcolor='rgba(0,0,0,0)',
            font=dict(color=self.colors['gray']['600'], size=12),
            margin=dict(l=0, r=0, t=50, b=0)
        )

        return fig

    def create_treemap(self, labels, parents, values, title="Hierarchical Breakdown"):
        """
        Create a treemap for hierarchical data

        Args:
            labels: List of labels
            parents: List of parent labels
            values: List of values
            title: Chart title

        Returns:
            plotly figure
        """
        fig = go.Figure(go.Treemap(
            labels=labels,
            parents=parents,
            values=values,
            text=[f"{v:,.0f}" for v in values],
            textposition="middle center",
            marker=dict(
                colorscale=[
                    [0, self.colors['info']],
                    [0.5, self.colors['primary']],
                    [1, self.colors['success']]
                ],
                line=dict(width=2, color='white')
            )
        ))

        fig.update_layout(
            title=title,
            height=500,
            paper_bgcolor='rgba(0,0,0,0)',
            font=dict(color=self.colors['gray']['600'], size=12),
            margin=dict(l=20, r=20, t=60, b=20)
        )

        return fig

    def create_sunburst(self, labels, parents, values, title="Hierarchical Sunburst"):
        """
        Create a sunburst chart for hierarchical data

        Args:
            labels: List of labels
            parents: List of parent labels
            values: List of values
            title: Chart title

        Returns:
            plotly figure
        """
        fig = go.Figure(go.Sunburst(
            labels=labels,
            parents=parents,
            values=values,
            branchvalues="total",
            marker=dict(
                colorscale=[
                    [0, self.colors['primary']],
                    [0.5, self.colors['info']],
                    [1, self.colors['success']]
                ],
                line=dict(width=2, color='white')
            )
        ))

        fig.update_layout(
            title=title,
            height=500,
            paper_bgcolor='rgba(0,0,0,0)',
            font=dict(color=self.colors['gray']['600'], size=12),
            margin=dict(l=20, r=20, t=60, b=20)
        )

        return fig

    def create_funnel_chart(self, stages, values, title="Conversion Funnel"):
        """
        Create a funnel chart for conversion analysis

        Args:
            stages: List of stage names
            values: List of values for each stage
            title: Chart title

        Returns:
            plotly figure
        """
        fig = go.Figure(go.Funnel(
            y=stages,
            x=values,
            textposition="inside",
            textinfo="value+percent initial",
            marker=dict(
                color=[self.colors['primary'], self.colors['info'],
                       self.colors['success'], self.colors['warning']][:len(stages)]
            ),
            connector=dict(line=dict(color=self.colors['gray']['400'], width=2))
        ))

        fig.update_layout(
            title=title,
            height=400,
            paper_bgcolor='rgba(0,0,0,0)',
            font=dict(color=self.colors['gray']['600'], size=12),
            margin=dict(l=150, r=50, t=80, b=50)
        )

        return fig

    def create_responsive_config(self):
        """
        Create configuration for responsive charts

        Returns:
            dict: Plotly config for responsive charts
        """
        return {
            'responsive': True,
            'displayModeBar': True,
            'displaylogo': False,
            'modeBarButtonsToRemove': ['pan2d', 'lasso2d', 'select2d'],
            'toImageButtonOptions': {
                'format': 'png',
                'filename': 'chart_export',
                'height': 800,
                'width': 1200,
                'scale': 2
            }
        }


# Example usage functions

def example_waterfall():
    """Example: Revenue waterfall from Q1 to Q2"""
    charts = AdvancedCharts()

    categories = ['Q1 Revenue', 'Sales Growth', 'Price Increase',
                  'Volume Decrease', 'New Products', 'Q2 Revenue']
    values = [1000000, 150000, 80000, -50000, 120000, 0]

    # Calculate final value
    values[-1] = sum(values[:-1])

    return charts.create_waterfall_chart(categories, values, "Revenue Bridge Q1 to Q2")


def example_sankey():
    """Example: Revenue flow analysis"""
    charts = AdvancedCharts()

    labels = ['Total Revenue', 'Product A', 'Product B', 'Product C',
              'North', 'South', 'East', 'West']

    sources = [0, 0, 0, 1, 1, 2, 2, 3, 3]
    targets = [1, 2, 3, 4, 5, 6, 7, 4, 5]
    values = [500, 300, 200, 300, 200, 150, 150, 100, 100]

    return charts.create_sankey_diagram(sources, targets, values, labels,
                                       "Revenue Flow by Product and Region")


def example_heatmap():
    """Example: Product performance by region"""
    charts = AdvancedCharts()

    # Sample data: performance scores
    data = [
        [95, 87, 92, 78, 85],
        [88, 91, 85, 82, 90],
        [76, 82, 88, 91, 87],
        [92, 85, 79, 88, 94]
    ]

    x_labels = ['Q1', 'Q2', 'Q3', 'Q4', 'YTD']
    y_labels = ['Product A', 'Product B', 'Product C', 'Product D']

    return charts.create_heatmap(data, x_labels, y_labels,
                                 "Product Performance by Quarter")


def example_treemap():
    """Example: Revenue breakdown"""
    charts = AdvancedCharts()

    labels = ['Total', 'Products', 'Services', 'Product A', 'Product B',
              'Product C', 'Service X', 'Service Y']
    parents = ['', 'Total', 'Total', 'Products', 'Products', 'Products',
               'Services', 'Services']
    values = [0, 0, 0, 500, 300, 200, 400, 350]

    return charts.create_treemap(labels, parents, values, "Revenue Distribution")


def example_funnel():
    """Example: Sales funnel"""
    charts = AdvancedCharts()

    stages = ['Leads', 'Qualified', 'Proposal', 'Negotiation', 'Closed Won']
    values = [1000, 650, 380, 210, 150]

    return charts.create_funnel_chart(stages, values, "Sales Conversion Funnel")
