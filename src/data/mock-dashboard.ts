export type TileKind = "trend" | "bar" | "waterfall" | "compare";
export type TileUnit = "currency" | "percent" | "ratio" | "days" | "score";

export type Tile = {
  id: string;
  title: string;
  subtitle: string;
  kind: TileKind;
  unit: TileUnit;
  baseSeries: number[];
  secondarySeries?: number[];
  tags?: string[];
};

export type DashboardSection = {
  id: string;
  title: string;
  description: string;
  tiles: Tile[];
};

export const years = ["2023", "2024", "2025", "2026"] as const;
export const regions = ["All Regions", "North America", "Europe", "Asia Pacific", "Latin America"] as const;
export const currencies = ["USD", "EUR", "GBP", "INR"] as const;
export const viewModes = ["chart", "ratio", "bifurcation"] as const;
export const chartTypes = ["line", "bar", "area", "step", "scatter"] as const;
export const displayModes = ["graph", "table", "split"] as const;

export const metrics = [
  "EBITDA_MARGIN",
  "TOT_DEBT_TO_EBITDA",
  "CUR_RATIO",
  "CASH_DVD_COVERAGE",
  "INTEREST_COVERAGE_RATIO",
  "NET_DEBT_TO_SHRHLDR_EQTY",
] as const;

export const competitors = ["META", "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "TSLA", "ORCL"] as const;

export const dashboardSections: DashboardSection[] = [
  {
    id: "overview",
    title: "Overview",
    description: "Core ratio trends aligned to year, region, and currency selections.",
    tiles: [
      {
        id: "ov-1",
        title: "Current Ratio Trend",
        subtitle: "Liquidity health",
        kind: "trend",
        unit: "ratio",
        baseSeries: [1.34, 1.38, 1.42, 1.45, 1.51, 1.55, 1.6, 1.66],
      },
      {
        id: "ov-2",
        title: "Cash Bucket Allocation",
        subtitle: "Operating vs reserve",
        kind: "bar",
        unit: "currency",
        baseSeries: [122, 98, 110, 132, 104, 88],
      },
      {
        id: "ov-3",
        title: "Debt Service Slope",
        subtitle: "Leverage trajectory",
        kind: "trend",
        unit: "ratio",
        baseSeries: [2.3, 2.24, 2.15, 2.04, 1.93, 1.84, 1.75, 1.62],
      },
      {
        id: "ov-4",
        title: "Net Debt vs Equity",
        subtitle: "Balance pressure",
        kind: "compare",
        unit: "percent",
        baseSeries: [58, 54, 52, 49, 47, 43],
        secondarySeries: [42, 44, 46, 49, 53, 56],
      },
    ],
  },
  {
    id: "competitor-analysis",
    title: "Competitor Analysis",
    description: "Peer-relative positions driven by competitor and metric selection.",
    tiles: [
      {
        id: "ca-1",
        title: "EBITDA Margin Rank",
        subtitle: "Selected peer basket",
        kind: "bar",
        unit: "percent",
        baseSeries: [31, 29, 27, 25, 24, 21],
      },
      {
        id: "ca-2",
        title: "Revenue Growth Gap",
        subtitle: "You vs peers",
        kind: "compare",
        unit: "percent",
        baseSeries: [14, 15, 13, 16, 18, 19, 21],
        secondarySeries: [11, 12, 12, 13, 15, 16, 16],
      },
      {
        id: "ca-3",
        title: "Free Cash Flow Drift",
        subtitle: "Rolling 8 quarters",
        kind: "trend",
        unit: "currency",
        baseSeries: [180, 194, 206, 198, 215, 229, 244, 261],
      },
      {
        id: "ca-4",
        title: "Similarity Stress Score",
        subtitle: "Cluster resilience",
        kind: "trend",
        unit: "score",
        baseSeries: [72, 74, 73, 76, 78, 80, 83, 86],
      },
    ],
  },
  {
    id: "comparative-analysis",
    title: "Comparative Analysis",
    description: "Direct side-by-side ratio and cash conversion comparisons.",
    tiles: [
      {
        id: "cmp-1",
        title: "Current Ratio vs Quick Ratio",
        subtitle: "Liquidity pair",
        kind: "compare",
        unit: "ratio",
        baseSeries: [1.4, 1.42, 1.44, 1.48, 1.5, 1.52],
        secondarySeries: [1.1, 1.12, 1.14, 1.16, 1.18, 1.2],
      },
      {
        id: "cmp-2",
        title: "Interest Coverage Curve",
        subtitle: "Debt safety",
        kind: "trend",
        unit: "ratio",
        baseSeries: [6.8, 7.1, 7.4, 7.2, 7.6, 7.9, 8.2, 8.6],
      },
      {
        id: "cmp-3",
        title: "Working Capital Bridge",
        subtitle: "Variance waterfall",
        kind: "waterfall",
        unit: "currency",
        baseSeries: [16, -8, 13, -4, 9, 12],
      },
      {
        id: "cmp-4",
        title: "Cash Dividend Coverage",
        subtitle: "Payout sustainability",
        kind: "bar",
        unit: "ratio",
        baseSeries: [2.2, 2.4, 2.5, 2.8, 3.0, 3.2],
      },
    ],
  },
  {
    id: "margin-bridge",
    title: "Margin Bridge",
    description: "Margin movement and cost pressure decomposition.",
    tiles: [
      {
        id: "mb-1",
        title: "Gross to EBITDA Bridge",
        subtitle: "Margin walk",
        kind: "waterfall",
        unit: "percent",
        baseSeries: [9, -4, -3, 2, 3, 4],
      },
      {
        id: "mb-2",
        title: "Operating Expense Spread",
        subtitle: "Cost profile",
        kind: "bar",
        unit: "percent",
        baseSeries: [36, 34, 31, 29, 27, 25],
      },
      {
        id: "mb-3",
        title: "Margin Volatility",
        subtitle: "8-quarter pulse",
        kind: "trend",
        unit: "percent",
        baseSeries: [18.2, 18.6, 18.1, 18.9, 19.3, 19.1, 19.8, 20.2],
      },
      {
        id: "mb-4",
        title: "Margin vs Peer Median",
        subtitle: "Relative spread",
        kind: "compare",
        unit: "percent",
        baseSeries: [18.4, 18.7, 19.0, 19.2, 19.7, 20.2],
        secondarySeries: [17.2, 17.3, 17.5, 17.8, 18.0, 18.3],
      },
    ],
  },
  {
    id: "advanced-charts",
    title: "Advanced Charts",
    description: "High-context exploratory views for scenario stress and strategy review.",
    tiles: [
      {
        id: "ad-1",
        title: "Scenario Cash Profile",
        subtitle: "Base / optimistic / downside",
        kind: "compare",
        unit: "currency",
        baseSeries: [220, 236, 248, 264, 279, 296],
        secondarySeries: [188, 196, 205, 211, 218, 224],
      },
      {
        id: "ad-2",
        title: "Capital Efficiency Index",
        subtitle: "Composite signal",
        kind: "trend",
        unit: "score",
        baseSeries: [62, 64, 65, 67, 70, 74, 78, 82],
      },
      {
        id: "ad-3",
        title: "Stress Delta Waterfall",
        subtitle: "Macro shock impact",
        kind: "waterfall",
        unit: "currency",
        baseSeries: [-9, -6, -3, 4, 7, 11],
      },
      {
        id: "ad-4",
        title: "ROIC Distribution",
        subtitle: "Peer quantiles",
        kind: "bar",
        unit: "percent",
        baseSeries: [7, 9, 11, 13, 15, 18],
      },
    ],
  },
];
