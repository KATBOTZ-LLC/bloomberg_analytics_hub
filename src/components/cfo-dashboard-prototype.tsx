"use client";

import { useEffect, useMemo, useRef, useState, type MouseEvent } from "react";
import Image from "next/image";
import { AreaClosed, Bar, LinePath } from "@visx/shape";
import { scaleBand, scaleLinear } from "@visx/scale";
import { curveMonotoneX, curveStep } from "@visx/curve";
import { AxisBottom, AxisLeft } from "@visx/axis";
import { GridColumns, GridRows } from "@visx/grid";
import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

import styles from "./cfo-dashboard-prototype.module.css";
import {
  chartTypes,
  competitors,
  currencies,
  dashboardSections,
  displayModes,
  metrics,
  regions,
  viewModes,
  years,
  type DashboardSection,
  type Tile,
  type TileUnit,
} from "@/data/mock-dashboard";
import { WebGLBackdrop } from "./webgl-backdrop";

function cx(...classes: Array<string | false | null | undefined>) {
  return classes.filter(Boolean).join(" ");
}

type Year = (typeof years)[number];
type Region = (typeof regions)[number];
type Currency = (typeof currencies)[number];
type ViewFilter = (typeof viewModes)[number];
type ChartType = (typeof chartTypes)[number];
type DisplayMode = (typeof displayModes)[number];
type Metric = (typeof metrics)[number];
type CompanyTicker = string;

type ViewMode = "horizontal" | "vertical" | "grid" | "focus";

type ComparisonLine = {
  id: string;
  label: string;
  series: number[];
  color: string;
  dashed?: boolean;
};

type DerivedTile = Tile & {
  currency: Currency;
  series: number[];
  secondarySeries?: number[];
  comparisonSeries?: ComparisonLine[];
  valueLabel: string;
  deltaLabel: string;
  tableRows: Array<{ period: string; value: string; secondary?: string }>;
};

type ChartTooltipPayload = {
  x: number;
  y: number;
  period: string;
  value: string;
  series: string;
};

type RagResponse = {
  answer: string;
  filing?: {
    ticker: string;
    companyName: string;
    form: string;
    filingDate: string;
    filingUrl: string;
  };
  snippets?: string[];
  model?: string;
};

type AgentMessage = {
  id: string;
  role: "assistant" | "user";
  text: string;
  model?: string;
  filing?: RagResponse["filing"];
  snippets?: string[];
};

const sectionViewModes: Array<{ mode: ViewMode; label: string }> = [
  { mode: "horizontal", label: "Horizontal" },
  { mode: "vertical", label: "Vertical" },
  { mode: "grid", label: "Grid" },
  { mode: "focus", label: "Dynamic Focus" },
];

const currencyRates: Record<Currency, number> = {
  USD: 1,
  EUR: 0.92,
  GBP: 0.79,
  INR: 83.2,
};

const currencySymbols: Record<Currency, string> = {
  USD: "$",
  EUR: "€",
  GBP: "£",
  INR: "₹",
};

const yearFactors: Record<Year, number> = {
  "2023": 0.92,
  "2024": 0.97,
  "2025": 1,
  "2026": 1.06,
};

const regionFactors: Record<Region, number> = {
  "All Regions": 1,
  "North America": 1.07,
  Europe: 0.96,
  "Asia Pacific": 1.03,
  "Latin America": 0.93,
};

const metricFactors: Record<Metric, number> = {
  EBITDA_MARGIN: 1.04,
  TOT_DEBT_TO_EBITDA: 0.96,
  CUR_RATIO: 1.01,
  CASH_DVD_COVERAGE: 1.03,
  INTEREST_COVERAGE_RATIO: 1.05,
  NET_DEBT_TO_SHRHLDR_EQTY: 0.95,
};

const sectionFactors: Record<string, number> = {
  overview: 1,
  "competitor-analysis": 1.02,
  "comparative-analysis": 0.99,
  "margin-bridge": 1.03,
  "advanced-charts": 1.01,
};

const modeClassMap: Record<ViewMode, string> = {
  horizontal: styles.modeHorizontal,
  vertical: styles.modeVertical,
  grid: styles.modeGrid,
  focus: styles.modeFocus,
};

const chartWidth = 360;
const chartHeight = 186;
const plotMargin = { top: 14, right: 14, bottom: 30, left: 42 };
const plotInnerWidth = chartWidth - plotMargin.left - plotMargin.right;
const plotInnerHeight = chartHeight - plotMargin.top - plotMargin.bottom;

const tableauPalette = {
  blue: "#8EB3D9",
  orange: "#F28E2B",
  green: "#59A14F",
  red: "#E15759",
  purple: "#B07AA1",
  grid: "rgba(92, 108, 146, 0.2)",
  axis: "rgba(82, 98, 132, 0.72)",
  tick: "rgba(70, 86, 118, 0.82)",
  plotFill: "rgba(255, 255, 255, 0.52)",
};

const compareLinePalette = [
  "#8EB3D9",
  "#F28E2B",
  "#59A14F",
  "#B07AA1",
  "#E15759",
  "#76B7B2",
  "#EDC949",
];

function getInitialSectionModes() {
  return dashboardSections.reduce<Record<string, ViewMode>>((acc, section) => {
    acc[section.id] = "grid";
    return acc;
  }, {});
}

function getInitialFocusMap() {
  return dashboardSections.reduce<Record<string, string[]>>((acc, section) => {
    acc[section.id] = section.tiles[0] ? [section.tiles[0].id] : [];
    return acc;
  }, {});
}

function stableHash(value: string) {
  let hash = 0;
  for (let i = 0; i < value.length; i += 1) {
    hash = (hash << 5) - hash + value.charCodeAt(i);
    hash |= 0;
  }
  return Math.abs(hash);
}

function formatValue(value: number, unit: TileUnit, currency: Currency) {
  if (unit === "currency") {
    const localized = value * currencyRates[currency];
    const precision = Math.abs(localized) >= 100 ? 0 : 1;
    return `${currencySymbols[currency]}${localized.toLocaleString("en-US", {
      minimumFractionDigits: precision,
      maximumFractionDigits: precision,
    })}`;
  }

  if (unit === "percent") return `${value.toFixed(1)}%`;
  if (unit === "ratio") return `${value.toFixed(2)}x`;
  if (unit === "days") return `${Math.round(value)} days`;
  return `${Math.round(value)} / 100`;
}

function toDeltaLabel(start: number, end: number, unit: TileUnit, currency: Currency) {
  const delta = end - start;
  const prefix = delta >= 0 ? "+" : "";

  if (unit === "currency") {
    const converted = delta * currencyRates[currency];
    return `${prefix}${currencySymbols[currency]}${converted.toFixed(Math.abs(converted) >= 100 ? 0 : 1)}`;
  }

  if (unit === "percent") return `${prefix}${delta.toFixed(1)} pp`;
  if (unit === "ratio") return `${prefix}${delta.toFixed(2)}x`;
  if (unit === "days") return `${prefix}${Math.round(delta)} days`;
  return `${prefix}${Math.round(delta)} score`;
}

function transformSeries(params: {
  tile: Tile;
  sectionId: string;
  series: number[];
  year: Year;
  region: Region;
  metric: Metric;
  selectedCompetitors: CompanyTicker[];
  viewFilter: ViewFilter;
  tickerSeed?: string;
}) {
  const { tile, sectionId, series, year, region, metric, selectedCompetitors, viewFilter, tickerSeed } = params;

  const seed = stableHash(tile.id + sectionId + (tickerSeed ?? ""));
  const seedJitter = ((seed % 11) - 5) / 120;
  const competitorFactor = 1 + (selectedCompetitors.length - 1) * 0.011;
  const viewFactor = viewFilter === "chart" ? 1 : viewFilter === "ratio" ? 0.985 : 1.035;

  const baseFactor =
    yearFactors[year] *
    regionFactors[region] *
    metricFactors[metric] *
    sectionFactors[sectionId] *
    competitorFactor *
    viewFactor;

  return series.map((value, index) => {
    const motion = Math.sin((index + 1) * 0.9 + seed * 0.003) * 0.014;
    const drift = 1 + motion + seedJitter;
    const factor = baseFactor * drift;

    if (tile.kind === "waterfall") {
      const sign = value >= 0 ? 1 : -1;
      return sign * Math.abs(value) * factor;
    }

    return value * factor;
  });
}

function periodsFor(length: number) {
  return Array.from({ length }, (_, index) => `Q${index + 1}`);
}

function buildTableRows(tile: Tile, series: number[], secondary: number[] | undefined, currency: Currency) {
  const periods = periodsFor(series.length);
  return periods.map((period, index) => ({
    period,
    value: formatValue(series[index], tile.unit, currency),
    secondary: secondary ? formatValue(secondary[index] ?? secondary[secondary.length - 1], tile.unit, currency) : undefined,
  }));
}

function chartData(series: number[]) {
  return series.map((value, index) => ({ x: index, y: value }));
}

function clampNumber(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max);
}

function indexFromPointer(
  event: MouseEvent<SVGRectElement>,
  points: number,
) {
  const rect = event.currentTarget.getBoundingClientRect();
  const ratio = rect.width > 0 ? (event.clientX - rect.left) / rect.width : 0;
  const index = Math.round(ratio * (points - 1));
  return clampNumber(index, 0, Math.max(points - 1, 0));
}

function localYFromPointer(event: MouseEvent<SVGRectElement>) {
  const rect = event.currentTarget.getBoundingClientRect();
  if (rect.height <= 0) return 0;
  const ratio = (event.clientY - rect.top) / rect.height;
  return clampNumber(ratio * chartHeight, 0, chartHeight);
}

function formatAxisTick(value: number) {
  const abs = Math.abs(value);
  if (abs >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (abs >= 1_000) return `${(value / 1_000).toFixed(1)}k`;
  if (abs >= 100) return `${Math.round(value)}`;
  if (abs >= 10) return value.toFixed(1);
  return value.toFixed(2);
}

function quarterTickLabel(value: number) {
  const q = Math.round(value) + 1;
  return `Q${q}`;
}

function resolveCurve(chartType: ChartType) {
  return chartType === "step" ? curveStep : curveMonotoneX;
}

type ChartBaseProps = {
  tile: DerivedTile;
  chartType: ChartType;
  onTooltipChange: (payload: ChartTooltipPayload | null) => void;
};

function TrendChart({ tile, chartType, onTooltipChange }: ChartBaseProps) {
  const { series, currency, unit } = tile;
  const data = chartData(series);
  const curve = resolveCurve(chartType);
  const min = Math.min(...series);
  const max = Math.max(...series);
  const domainMin = min === max ? min - 1 : min * 0.94;
  const domainMax = min === max ? max + 1 : max * 1.06;
  const gradientId = `${tile.id}-g`;

  const xScale = scaleLinear<number>({
    domain: [0, Math.max(series.length - 1, 1)],
    range: [plotMargin.left, chartWidth - plotMargin.right],
  });
  const yScale = scaleLinear<number>({
    domain: [domainMin, domainMax],
    range: [chartHeight - plotMargin.bottom, plotMargin.top],
  });

  const showTooltip = (x: number, y: number, index: number, value: number, label = "Primary") => {
    onTooltipChange({
      x,
      y: Math.max(18, y - 12),
      period: `Q${index + 1}`,
      value: formatValue(value, unit, currency),
      series: label,
    });
  };

  if (chartType === "bar") {
    const band = scaleBand<string>({
      domain: data.map((d) => `${d.x}`),
      range: [plotMargin.left, chartWidth - plotMargin.right],
      padding: 0.38,
    });

    return (
      <svg
        viewBox={`0 0 ${chartWidth} ${chartHeight}`}
        className={styles.chartSvg}
        aria-label="trend chart"
        onMouseLeave={() => onTooltipChange(null)}
      >
        <rect x={plotMargin.left} y={plotMargin.top} width={plotInnerWidth} height={plotInnerHeight} fill={tableauPalette.plotFill} rx={10} />
        <GridRows scale={yScale} left={plotMargin.left} width={plotInnerWidth} numTicks={4} stroke={tableauPalette.grid} strokeDasharray="2,4" />
        {data.map((point) => {
          const x = band(`${point.x}`) ?? 0;
          const y = yScale(point.y) ?? 0;
          const height = Math.max(2, chartHeight - plotMargin.bottom - y);
          return (
            <Bar
              key={`trend-bar-${point.x}`}
              x={x}
              y={y}
              width={band.bandwidth()}
              height={height}
              rx={8}
              fill={`rgba(78, 121, 167, ${0.52 + point.x * 0.05})`}
              onMouseMove={() => showTooltip(x + band.bandwidth() * 0.5, y, point.x, point.y)}
              onMouseLeave={() => onTooltipChange(null)}
            />
          );
        })}
        <AxisBottom
          top={chartHeight - plotMargin.bottom}
          scale={xScale}
          numTicks={Math.min(series.length, 6)}
          tickFormat={(value) => quarterTickLabel(Number(value))}
          stroke={tableauPalette.axis}
          tickStroke={tableauPalette.axis}
          tickLabelProps={() => ({ fill: tableauPalette.tick, fontSize: 10, textAnchor: "middle", dy: "0.55em" })}
        />
        <AxisLeft
          left={plotMargin.left}
          scale={yScale}
          numTicks={4}
          tickFormat={(value) => formatAxisTick(Number(value))}
          stroke={tableauPalette.axis}
          tickStroke={tableauPalette.axis}
          tickLabelProps={() => ({ fill: tableauPalette.tick, fontSize: 10, textAnchor: "end", dx: "-0.35em", dy: "0.3em" })}
        />
      </svg>
    );
  }

  return (
    <svg
      viewBox={`0 0 ${chartWidth} ${chartHeight}`}
      className={styles.chartSvg}
      aria-label="trend chart"
      onMouseLeave={() => onTooltipChange(null)}
    >
      <rect x={plotMargin.left} y={plotMargin.top} width={plotInnerWidth} height={plotInnerHeight} fill={tableauPalette.plotFill} rx={10} />
      <GridRows scale={yScale} left={plotMargin.left} width={plotInnerWidth} numTicks={4} stroke={tableauPalette.grid} strokeDasharray="2,4" />
      <GridColumns scale={xScale} top={plotMargin.top} height={plotInnerHeight} numTicks={Math.min(series.length, 6)} stroke="rgba(78, 92, 126, 0.08)" />

      <defs>
        <linearGradient id={gradientId} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor="rgba(78, 121, 167, 0.33)" />
          <stop offset="100%" stopColor="rgba(78, 121, 167, 0.03)" />
        </linearGradient>
      </defs>

      {chartType === "area" ? (
        <AreaClosed
          data={data}
          x={(d) => xScale(d.x) ?? 0}
          y={(d) => yScale(d.y) ?? 0}
          yScale={yScale}
          stroke={tableauPalette.blue}
          strokeWidth={2.3}
          fill={`url(#${gradientId})`}
          curve={curve}
        />
      ) : null}

      {chartType === "scatter" ? null : (
        <LinePath
          data={data}
          x={(d) => xScale(d.x) ?? 0}
          y={(d) => yScale(d.y) ?? 0}
          curve={curve}
          stroke={tableauPalette.blue}
          strokeWidth={2.4}
        />
      )}

      {data.map((point) => {
        const x = xScale(point.x) ?? 0;
        const y = yScale(point.y) ?? 0;
        return (
          <circle
            key={`trend-dot-${point.x}`}
            cx={x}
            cy={y}
            r="2.6"
            fill="rgba(237, 240, 250, 1)"
            stroke={tableauPalette.blue}
            strokeWidth="1.4"
            onMouseMove={() => showTooltip(x, y, point.x, point.y)}
            onMouseLeave={() => onTooltipChange(null)}
          />
        );
      })}

      <rect
        x={plotMargin.left}
        y={plotMargin.top}
        width={plotInnerWidth}
        height={plotInnerHeight}
        fill="transparent"
        onMouseMove={(event) => {
          const index = indexFromPointer(event, series.length);
          const value = series[index] ?? series[series.length - 1] ?? 0;
          const x = xScale(index) ?? 0;
          const y = yScale(value) ?? 0;
          showTooltip(x, y, index, value);
        }}
        onMouseLeave={() => onTooltipChange(null)}
      />

      <AxisBottom
        top={chartHeight - plotMargin.bottom}
        scale={xScale}
        numTicks={Math.min(series.length, 6)}
        tickFormat={(value) => quarterTickLabel(Number(value))}
        stroke={tableauPalette.axis}
        tickStroke={tableauPalette.axis}
        tickLabelProps={() => ({ fill: tableauPalette.tick, fontSize: 10, textAnchor: "middle", dy: "0.55em" })}
      />
      <AxisLeft
        left={plotMargin.left}
        scale={yScale}
        numTicks={4}
        tickFormat={(value) => formatAxisTick(Number(value))}
        stroke={tableauPalette.axis}
        tickStroke={tableauPalette.axis}
        tickLabelProps={() => ({ fill: tableauPalette.tick, fontSize: 10, textAnchor: "end", dx: "-0.35em", dy: "0.3em" })}
      />
    </svg>
  );
}

function BarChart({ tile, onTooltipChange }: Omit<ChartBaseProps, "chartType">) {
  const { series, unit, currency } = tile;
  const data = chartData(series);
  const max = Math.max(...series, 1);
  const categories = data.map((d) => `Q${d.x + 1}`);

  const xScale = scaleBand<string>({
    domain: categories,
    range: [plotMargin.left, chartWidth - plotMargin.right],
    padding: 0.32,
  });
  const yScale = scaleLinear<number>({
    domain: [0, max * 1.08],
    range: [chartHeight - plotMargin.bottom, plotMargin.top],
  });

  return (
    <svg
      viewBox={`0 0 ${chartWidth} ${chartHeight}`}
      className={styles.chartSvg}
      aria-label="bar chart"
      onMouseLeave={() => onTooltipChange(null)}
    >
      <rect x={plotMargin.left} y={plotMargin.top} width={plotInnerWidth} height={plotInnerHeight} fill={tableauPalette.plotFill} rx={10} />
      <GridRows scale={yScale} left={plotMargin.left} width={plotInnerWidth} numTicks={4} stroke={tableauPalette.grid} strokeDasharray="2,4" />

      {data.map((point) => {
        const category = `Q${point.x + 1}`;
        const x = xScale(category) ?? 0;
        const y = yScale(point.y) ?? 0;
        const height = Math.max(2, chartHeight - plotMargin.bottom - y);
        return (
          <Bar
            key={`bar-${point.x}`}
            x={x}
            y={y}
            width={xScale.bandwidth()}
            height={height}
            rx={10}
            fill={`rgba(78, 121, 167, ${0.4 + point.x * 0.08})`}
            onMouseMove={() =>
              onTooltipChange({
                x: x + xScale.bandwidth() * 0.5,
                y,
                period: category,
                value: formatValue(point.y, unit, currency),
                series: "Primary",
              })
            }
            onMouseLeave={() => onTooltipChange(null)}
          />
        );
      })}

      <AxisBottom
        top={chartHeight - plotMargin.bottom}
        scale={xScale}
        stroke={tableauPalette.axis}
        tickStroke={tableauPalette.axis}
        tickLabelProps={() => ({ fill: tableauPalette.tick, fontSize: 10, textAnchor: "middle", dy: "0.55em" })}
      />
      <AxisLeft
        left={plotMargin.left}
        scale={yScale}
        numTicks={4}
        tickFormat={(value) => formatAxisTick(Number(value))}
        stroke={tableauPalette.axis}
        tickStroke={tableauPalette.axis}
        tickLabelProps={() => ({ fill: tableauPalette.tick, fontSize: 10, textAnchor: "end", dx: "-0.35em", dy: "0.3em" })}
      />
    </svg>
  );
}

function WaterfallChart({ tile, onTooltipChange }: Omit<ChartBaseProps, "chartType">) {
  const { series, unit, currency } = tile;
  const bars = series.reduce<Array<{ index: number; start: number; end: number; delta: number }>>((acc, value, index) => {
    const start = index === 0 ? 0 : acc[index - 1].end;
    const end = start + value;
    return [...acc, { index, start, end, delta: value }];
  }, []);

  const extent = bars.flatMap((bar) => [bar.start, bar.end]);
  const min = Math.min(...extent, 0);
  const max = Math.max(...extent, 1);

  const xScale = scaleBand<string>({
    domain: bars.map((bar) => `Q${bar.index + 1}`),
    range: [plotMargin.left, chartWidth - plotMargin.right],
    padding: 0.34,
  });
  const yScale = scaleLinear<number>({
    domain: [min * 1.08, max * 1.08],
    range: [chartHeight - plotMargin.bottom, plotMargin.top],
  });

  return (
    <svg
      viewBox={`0 0 ${chartWidth} ${chartHeight}`}
      className={styles.chartSvg}
      aria-label="waterfall chart"
      onMouseLeave={() => onTooltipChange(null)}
    >
      <rect x={plotMargin.left} y={plotMargin.top} width={plotInnerWidth} height={plotInnerHeight} fill={tableauPalette.plotFill} rx={10} />
      <GridRows scale={yScale} left={plotMargin.left} width={plotInnerWidth} numTicks={4} stroke={tableauPalette.grid} strokeDasharray="2,4" />
      <line x1={plotMargin.left} x2={chartWidth - plotMargin.right} y1={yScale(0)} y2={yScale(0)} stroke={tableauPalette.axis} strokeWidth={1} />

      {bars.map((bar, index) => {
        if (index === 0) return null;
        const prev = bars[index - 1];
        const x1 = (xScale(`Q${prev.index + 1}`) ?? 0) + xScale.bandwidth();
        const x2 = xScale(`Q${bar.index + 1}`) ?? 0;
        const y = yScale(prev.end);
        return <line key={`wf-connector-${bar.index}`} x1={x1} x2={x2} y1={y} y2={y} stroke="rgba(96, 111, 148, 0.46)" strokeDasharray="3,3" />;
      })}

      {bars.map((bar) => {
        const period = `Q${bar.index + 1}`;
        const x = xScale(period) ?? 0;
        const yTop = yScale(Math.max(bar.start, bar.end)) ?? 0;
        const yBottom = yScale(Math.min(bar.start, bar.end)) ?? 0;
        return (
          <Bar
            key={`wf-${bar.index}`}
            x={x}
            y={yTop}
            width={xScale.bandwidth()}
            height={Math.max(4, yBottom - yTop)}
            rx={9}
            fill={bar.delta >= 0 ? "rgba(89, 161, 79, 0.68)" : "rgba(225, 87, 89, 0.65)"}
            onMouseMove={() =>
              onTooltipChange({
                x: x + xScale.bandwidth() * 0.5,
                y: yTop,
                period,
                value: formatValue(bar.delta, unit, currency),
                series: bar.delta >= 0 ? "Increase" : "Decrease",
              })
            }
            onMouseLeave={() => onTooltipChange(null)}
          />
        );
      })}

      <AxisBottom
        top={chartHeight - plotMargin.bottom}
        scale={xScale}
        stroke={tableauPalette.axis}
        tickStroke={tableauPalette.axis}
        tickLabelProps={() => ({ fill: tableauPalette.tick, fontSize: 10, textAnchor: "middle", dy: "0.55em" })}
      />
      <AxisLeft
        left={plotMargin.left}
        scale={yScale}
        numTicks={4}
        tickFormat={(value) => formatAxisTick(Number(value))}
        stroke={tableauPalette.axis}
        tickStroke={tableauPalette.axis}
        tickLabelProps={() => ({ fill: tableauPalette.tick, fontSize: 10, textAnchor: "end", dx: "-0.35em", dy: "0.3em" })}
      />
    </svg>
  );
}

function CompareChart({ tile, chartType, onTooltipChange }: ChartBaseProps) {
  const { series, secondarySeries, unit, currency } = tile;
  const comparisonLines = tile.comparisonSeries?.length
    ? tile.comparisonSeries
    : [
        { id: `${tile.id}-primary`, label: "Primary", series, color: tableauPalette.blue },
        ...(secondarySeries
          ? [{ id: `${tile.id}-secondary`, label: "Peer", series: secondarySeries, color: tableauPalette.orange, dashed: true }]
          : []),
      ];

  if (comparisonLines.length < 2 && !secondarySeries) {
    return <TrendChart tile={tile} chartType={chartType} onTooltipChange={onTooltipChange} />;
  }

  const visibleLines = comparisonLines.slice(0, 6);
  const seriesLength = Math.max(...visibleLines.map((line) => line.series.length), 1);
  const allValues = visibleLines.flatMap((line) => line.series);
  const min = Math.min(...allValues);
  const max = Math.max(...allValues);
  const domainMin = min === max ? min - 1 : min * 0.94;
  const domainMax = min === max ? max + 1 : max * 1.06;
  const gradientId = `${tile.id}-compare-g`;
  const primaryData = chartData(visibleLines[0]?.series ?? series);
  const curve = resolveCurve(chartType);

  const xScale = scaleLinear<number>({
    domain: [0, Math.max(seriesLength - 1, 1)],
    range: [plotMargin.left, chartWidth - plotMargin.right],
  });
  const yScale = scaleLinear<number>({
    domain: [domainMin, domainMax],
    range: [chartHeight - plotMargin.bottom, plotMargin.top],
  });

  const showTooltip = (
    x: number,
    y: number,
    index: number,
    value: number,
    seriesLabel: string,
  ) => {
    onTooltipChange({
      x,
      y: Math.max(18, y - 12),
      period: `Q${index + 1}`,
      value: formatValue(value, unit, currency),
      series: seriesLabel,
    });
  };

  if (chartType === "bar") {
    const categories = Array.from({ length: seriesLength }, (_, index) => `Q${index + 1}`);
    const xGroupScale = scaleBand<string>({
      domain: categories,
      range: [plotMargin.left, chartWidth - plotMargin.right],
      padding: 0.24,
    });
    const xInnerScale = scaleBand<string>({
      domain: visibleLines.map((line) => line.id),
      range: [0, xGroupScale.bandwidth()],
      padding: 0.18,
    });

    return (
      <svg
        viewBox={`0 0 ${chartWidth} ${chartHeight}`}
        className={styles.chartSvg}
        aria-label="comparison bar chart"
        onMouseLeave={() => onTooltipChange(null)}
      >
        <rect x={plotMargin.left} y={plotMargin.top} width={plotInnerWidth} height={plotInnerHeight} fill={tableauPalette.plotFill} rx={10} />
        <GridRows scale={yScale} left={plotMargin.left} width={plotInnerWidth} numTicks={4} stroke={tableauPalette.grid} strokeDasharray="2,4" />

        {categories.map((category, categoryIndex) => {
          const groupX = xGroupScale(category) ?? 0;
          return visibleLines.map((line) => {
            const value = line.series[categoryIndex] ?? line.series[line.series.length - 1] ?? 0;
            const x = groupX + (xInnerScale(line.id) ?? 0);
            const y = yScale(value) ?? 0;
            const barHeight = Math.max(2, chartHeight - plotMargin.bottom - y);

            return (
              <Bar
                key={`${line.id}-${category}`}
                x={x}
                y={y}
                width={xInnerScale.bandwidth()}
                height={barHeight}
                rx={6}
                fill={line.color}
                onMouseMove={() =>
                  showTooltip(
                    x + xInnerScale.bandwidth() * 0.5,
                    y,
                    categoryIndex,
                    value,
                    line.label,
                  )
                }
                onMouseLeave={() => onTooltipChange(null)}
              />
            );
          });
        })}

        <g transform={`translate(${plotMargin.left + 4}, ${plotMargin.top + 5})`}>
          {visibleLines.slice(0, 4).map((line, index) => (
            <g key={`legend-bar-${line.id}`} transform={`translate(${index * 78}, 0)`}>
              <rect x={0} y={0} width={9} height={9} rx={2} fill={line.color} />
              <text x={13} y={8} fontSize={10} fill={tableauPalette.tick}>
                {line.label}
              </text>
            </g>
          ))}
        </g>

        <AxisBottom
          top={chartHeight - plotMargin.bottom}
          scale={xGroupScale}
          stroke={tableauPalette.axis}
          tickStroke={tableauPalette.axis}
          tickLabelProps={() => ({ fill: tableauPalette.tick, fontSize: 10, textAnchor: "middle", dy: "0.55em" })}
        />
        <AxisLeft
          left={plotMargin.left}
          scale={yScale}
          numTicks={4}
          tickFormat={(value) => formatAxisTick(Number(value))}
          stroke={tableauPalette.axis}
          tickStroke={tableauPalette.axis}
          tickLabelProps={() => ({ fill: tableauPalette.tick, fontSize: 10, textAnchor: "end", dx: "-0.35em", dy: "0.3em" })}
        />
      </svg>
    );
  }

  return (
    <svg
      viewBox={`0 0 ${chartWidth} ${chartHeight}`}
      className={styles.chartSvg}
      aria-label="comparison chart"
      onMouseLeave={() => onTooltipChange(null)}
    >
      <rect x={plotMargin.left} y={plotMargin.top} width={plotInnerWidth} height={plotInnerHeight} fill={tableauPalette.plotFill} rx={10} />
      <GridRows scale={yScale} left={plotMargin.left} width={plotInnerWidth} numTicks={4} stroke={tableauPalette.grid} strokeDasharray="2,4" />
      <GridColumns scale={xScale} top={plotMargin.top} height={plotInnerHeight} numTicks={Math.min(seriesLength, 6)} stroke="rgba(78, 92, 126, 0.08)" />

      <defs>
        <linearGradient id={gradientId} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0%" stopColor="rgba(78, 121, 167, 0.3)" />
          <stop offset="100%" stopColor="rgba(78, 121, 167, 0.03)" />
        </linearGradient>
      </defs>

      {chartType === "area" ? (
        <AreaClosed
          data={primaryData}
          x={(d) => xScale(d.x) ?? 0}
          y={(d) => yScale(d.y) ?? 0}
          yScale={yScale}
          stroke={visibleLines[0]?.color ?? tableauPalette.blue}
          strokeWidth={2.3}
          fill={`url(#${gradientId})`}
          curve={curve}
        />
      ) : null}

      {visibleLines.map((line) => {
        const lineData = chartData(line.series);
        return (
          <g key={`${tile.id}-${line.id}`}>
            {chartType === "scatter" ? null : (
              <LinePath
                data={lineData}
                x={(d) => xScale(d.x) ?? 0}
                y={(d) => yScale(d.y) ?? 0}
                stroke={line.color}
                strokeWidth={2.1}
                strokeDasharray={line.dashed ? "5 4" : undefined}
                curve={curve}
              />
            )}
            {lineData.map((point) => {
              const x = xScale(point.x) ?? 0;
              const y = yScale(point.y) ?? 0;
              return (
                <circle
                  key={`${line.id}-dot-${point.x}`}
                  cx={x}
                  cy={y}
                  r={2.1}
                  fill={line.color}
                  onMouseMove={() => showTooltip(x, y, point.x, point.y, line.label)}
                  onMouseLeave={() => onTooltipChange(null)}
                />
              );
            })}
          </g>
        );
      })}

      <rect
        x={plotMargin.left}
        y={plotMargin.top}
        width={plotInnerWidth}
        height={plotInnerHeight}
        fill="transparent"
        onMouseMove={(event) => {
          const index = indexFromPointer(event, seriesLength);
          const pointerY = localYFromPointer(event);

          const firstLine = visibleLines[0];
          let closestLine = firstLine;
          let closestValue = firstLine
            ? firstLine.series[index] ?? firstLine.series[firstLine.series.length - 1] ?? 0
            : 0;
          let closestDistance = Math.abs((yScale(closestValue) ?? 0) - pointerY);

          visibleLines.forEach((line) => {
            const value = line.series[index] ?? line.series[line.series.length - 1] ?? 0;
            const distance = Math.abs((yScale(value) ?? 0) - pointerY);
            if (distance < closestDistance) {
              closestLine = line;
              closestValue = value;
              closestDistance = distance;
            }
          });

          const x = xScale(index) ?? 0;
          const y = yScale(closestValue) ?? 0;
          showTooltip(x, y, index, closestValue, closestLine?.label ?? "Series");
        }}
        onMouseLeave={() => onTooltipChange(null)}
      />

      <g transform={`translate(${plotMargin.left + 4}, ${plotMargin.top + 5})`}>
        {visibleLines.slice(0, 4).map((line, index) => (
          <g key={`legend-${line.id}`} transform={`translate(${index * 78}, 0)`}>
            <rect x={0} y={0} width={9} height={9} rx={2} fill={line.color} />
            <text x={13} y={8} fontSize={10} fill={tableauPalette.tick}>
              {line.label}
            </text>
          </g>
        ))}
      </g>

      <AxisBottom
        top={chartHeight - plotMargin.bottom}
        scale={xScale}
        numTicks={Math.min(seriesLength, 6)}
        tickFormat={(value) => quarterTickLabel(Number(value))}
        stroke={tableauPalette.axis}
        tickStroke={tableauPalette.axis}
        tickLabelProps={() => ({ fill: tableauPalette.tick, fontSize: 10, textAnchor: "middle", dy: "0.55em" })}
      />
      <AxisLeft
        left={plotMargin.left}
        scale={yScale}
        numTicks={4}
        tickFormat={(value) => formatAxisTick(Number(value))}
        stroke={tableauPalette.axis}
        tickStroke={tableauPalette.axis}
        tickLabelProps={() => ({ fill: tableauPalette.tick, fontSize: 10, textAnchor: "end", dx: "-0.35em", dy: "0.3em" })}
      />
    </svg>
  );
}

function TileChart({
  tile,
  chartType,
  onTooltipChange,
}: {
  tile: DerivedTile;
  chartType: ChartType;
  onTooltipChange: (payload: ChartTooltipPayload | null) => void;
}) {
  if (tile.kind === "bar") return <BarChart tile={tile} onTooltipChange={onTooltipChange} />;
  if (tile.kind === "waterfall") return <WaterfallChart tile={tile} onTooltipChange={onTooltipChange} />;
  if (tile.kind === "compare") return <CompareChart tile={tile} chartType={chartType} onTooltipChange={onTooltipChange} />;
  return <TrendChart tile={tile} chartType={chartType} onTooltipChange={onTooltipChange} />;
}

function TileTable({ tile }: { tile: DerivedTile }) {
  return (
    <div className={styles.tableWrap}>
      <table className={styles.miniTable}>
        <thead>
          <tr>
            <th>Period</th>
            <th>Primary</th>
            {tile.secondarySeries ? <th>Secondary</th> : null}
          </tr>
        </thead>
        <tbody>
          {tile.tableRows.slice(-6).map((row) => (
            <tr key={`${tile.id}-${row.period}`}>
              <td>{row.period}</td>
              <td>{row.value}</td>
              {tile.secondarySeries ? <td>{row.secondary}</td> : null}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function TileCard({
  tile,
  displayMode,
  chartType,
  onFocus,
}: {
  tile: DerivedTile;
  displayMode: DisplayMode;
  chartType: ChartType;
  onFocus?: (id: string) => void;
}) {
  const [tooltip, setTooltip] = useState<ChartTooltipPayload | null>(null);
  const tooltipRef = useRef<HTMLDivElement | null>(null);
  const chartHostRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!tooltipRef.current) return;
    const tooltipNode = tooltipRef.current;
    const host = chartHostRef.current;

    if (!host || !tooltip) {
      gsap.to(tooltipNode, {
        autoAlpha: 0,
        scale: 0.97,
        duration: 0.14,
        ease: "power2.out",
        overwrite: "auto",
      });
      return;
    }

    const hostWidth = host.clientWidth || chartWidth;
    const hostHeight = host.clientHeight || 178;

    const offsetX = (tooltip.x / chartWidth) * hostWidth;
    const offsetY = (tooltip.y / chartHeight) * hostHeight;

    const tooltipX = Math.min(Math.max(offsetX + 10, 10), Math.max(hostWidth - 172, 10));
    const tooltipY = Math.min(Math.max(offsetY - 18, 10), Math.max(hostHeight - 62, 10));

    gsap.to(tooltipNode, {
      autoAlpha: 1,
      x: tooltipX,
      y: tooltipY,
      scale: 1,
      duration: 0.16,
      ease: "power3.out",
      overwrite: "auto",
    });
  }, [tooltip]);

  return (
    <article data-dashboard-tile="true" className={styles.tileCard} aria-label={tile.title}>
      <div className={styles.tileTop}>
        <div className={styles.tileTitles}>
          <p className={styles.tileSubtitle}>{tile.subtitle}</p>
          <h4 className={styles.tileTitle}>{tile.title}</h4>
        </div>
        <div className={styles.tileMetrics}>
          <strong className={styles.tileValue}>{tile.valueLabel}</strong>
          <span className={styles.tileDelta}>{tile.deltaLabel}</span>
        </div>
      </div>

      <div className={styles.tileBody}>
        {displayMode === "graph" || displayMode === "split" ? (
          <div className={styles.chartHost} ref={chartHostRef}>
            <TileChart tile={tile} chartType={chartType} onTooltipChange={setTooltip} />
            <div ref={tooltipRef} className={styles.chartTooltip}>
              <span className={styles.chartTooltipSeries}>{tooltip?.series}</span>
              <strong>{tooltip?.value}</strong>
              <small>{tooltip?.period}</small>
            </div>
          </div>
        ) : null}

        {displayMode === "table" || displayMode === "split" ? (
          <TileTable tile={tile} />
        ) : null}
      </div>

      <div className={styles.tileFooter}>
        <div className={styles.tagRow}>
          {(tile.tags ?? []).map((tag) => (
            <span key={`${tile.id}-${tag}`} className={styles.tagPill}>
              {tag}
            </span>
          ))}
        </div>
        {onFocus ? (
          <button type="button" className={styles.focusAction} onClick={() => onFocus(tile.id)}>
            Focus Tile
          </button>
        ) : null}
      </div>
    </article>
  );
}

function SectionBlock({
  section,
  tiles,
  mode,
  displayMode,
  chartType,
  focusIds,
  onModeChange,
  onFocusToggle,
  onFocusInsert,
  onFocusRemove,
  registerSection,
  isActive,
}: {
  section: DashboardSection;
  tiles: DerivedTile[];
  mode: ViewMode;
  displayMode: DisplayMode;
  chartType: ChartType;
  focusIds: string[];
  onModeChange: (mode: ViewMode) => void;
  onFocusToggle: (tileId: string) => void;
  onFocusInsert: (tileId: string, targetIndex: number) => void;
  onFocusRemove: (tileId: string) => void;
  registerSection: (id: string, node: HTMLElement | null) => void;
  isActive: boolean;
}) {
  const [dragTileId, setDragTileId] = useState<string | null>(null);
  const [dragTarget, setDragTarget] = useState<string | null>(null);
  const tileMap = useMemo(() => new Map(tiles.map((tile) => [tile.id, tile])), [tiles]);

  const focusedTiles = useMemo(() => {
    const selected = focusIds
      .map((id) => tileMap.get(id))
      .filter((tile): tile is DerivedTile => Boolean(tile));
    return selected.length ? selected : tiles.slice(0, 1);
  }, [focusIds, tileMap, tiles]);

  const railTiles = useMemo(
    () => tiles.filter((tile) => !focusedTiles.some((focusTile) => focusTile.id === tile.id)),
    [tiles, focusedTiles],
  );

  const handleDragStart = (tileId: string) => {
    setDragTileId(tileId);
  };

  const handleDragEnd = () => {
    setDragTileId(null);
    setDragTarget(null);
  };

  return (
    <section
      id={section.id}
      data-section-card="true"
      className={cx(styles.sectionPanel, isActive && styles.sectionPanelActive)}
      ref={(node) => registerSection(section.id, node)}
    >
      <header className={styles.sectionHeader}>
        <div className={styles.sectionTitleWrap}>
          <h3 className={styles.sectionTitle}>{section.title}</h3>
          <p className={styles.sectionDescription}>{section.description}</p>
        </div>

        <div className={styles.sectionControls}>
          <div className={styles.modePicker}>
            {sectionViewModes.map((option) => (
                <button
                  key={`${section.id}-${option.mode}`}
                  type="button"
                  className={cx(styles.modeButton, mode === option.mode && styles.modeButtonActive)}
                  onClick={() => onModeChange(option.mode)}
                  aria-pressed={mode === option.mode}
                >
                {option.label}
              </button>
            ))}
          </div>
        </div>
      </header>

      {mode === "focus" ? (
        <div className={styles.focusLayout}>
          <div
            className={cx(styles.focusRail, dragTarget === "rail" && styles.focusDropActive)}
            onDragOver={(event) => {
              event.preventDefault();
              setDragTarget("rail");
            }}
            onDragLeave={() => setDragTarget((prev) => (prev === "rail" ? null : prev))}
            onDrop={(event) => {
              event.preventDefault();
              if (dragTileId) {
                onFocusRemove(dragTileId);
              }
              setDragTarget(null);
              setDragTileId(null);
            }}
          >
            <div className={styles.focusRailHint}>Drop Here To Remove From Focus</div>
            {railTiles.map((tile) => (
              <button
                key={`rail-${section.id}-${tile.id}`}
                className={styles.focusRailButton}
                type="button"
                onClick={() => onFocusToggle(tile.id)}
                draggable
                onDragStart={() => handleDragStart(tile.id)}
                onDragEnd={handleDragEnd}
              >
                {tile.title}
              </button>
            ))}
          </div>

          <div className={styles.focusStage}>
            {focusedTiles.map((tile, index) => (
              <div
                key={`focus-slot-${tile.id}`}
                className={cx(styles.focusSlot, dragTarget === `slot-${index}` && styles.focusDropActive)}
                onDragOver={(event) => {
                  event.preventDefault();
                  setDragTarget(`slot-${index}`);
                }}
                onDragLeave={() => setDragTarget((prev) => (prev === `slot-${index}` ? null : prev))}
                onDrop={(event) => {
                  event.preventDefault();
                  if (dragTileId) {
                    onFocusInsert(dragTileId, index);
                  }
                  setDragTileId(null);
                  setDragTarget(null);
                }}
              >
                <div draggable onDragStart={() => handleDragStart(tile.id)} onDragEnd={handleDragEnd} className={styles.focusDraggableCard}>
                  <TileCard
                    key={`focus-${tile.id}`}
                    tile={tile}
                    displayMode={displayMode}
                    chartType={chartType}
                    onFocus={onFocusToggle}
                  />
                </div>
              </div>
            ))}
            <div
              className={cx(styles.focusStageDropEnd, dragTarget === "slot-end" && styles.focusDropActive)}
              onDragOver={(event) => {
                event.preventDefault();
                setDragTarget("slot-end");
              }}
              onDragLeave={() => setDragTarget((prev) => (prev === "slot-end" ? null : prev))}
              onDrop={(event) => {
                event.preventDefault();
                if (dragTileId) {
                  onFocusInsert(dragTileId, focusedTiles.length);
                }
                setDragTileId(null);
                setDragTarget(null);
              }}
            >
              Drag Tile Here To Add To Focus
            </div>
          </div>
        </div>
      ) : (
        <div className={`${styles.tilesLayout} ${modeClassMap[mode]}`}>
          {tiles.map((tile) => (
            <TileCard key={`${section.id}-${tile.id}`} tile={tile} displayMode={displayMode} chartType={chartType} />
          ))}
        </div>
      )}
    </section>
  );
}

function CompanyViz({
  ticker,
  series,
  currency,
  chartType,
  displayMode,
}: {
  ticker: string;
  series: number[];
  currency: Currency;
  chartType: ChartType;
  displayMode: DisplayMode;
}) {
  const [tooltip, setTooltip] = useState<ChartTooltipPayload | null>(null);
  const localWidth = 336;
  const localHeight = 170;
  const localMargin = { top: 14, right: 12, bottom: 28, left: 42 };
  const localInnerWidth = localWidth - localMargin.left - localMargin.right;
  const localInnerHeight = localHeight - localMargin.top - localMargin.bottom;
  const data = chartData(series);
  const curve = resolveCurve(chartType);
  const min = Math.min(...series);
  const max = Math.max(...series);
  const yMin = min === max ? min - 1 : min * 0.94;
  const yMax = min === max ? max + 1 : max * 1.06;
  const gradientId = `${ticker.toLowerCase()}-company-area`;

  const xScale = scaleLinear<number>({
    domain: [0, Math.max(series.length - 1, 1)],
    range: [localMargin.left, localWidth - localMargin.right],
  });
  const yScale = scaleLinear<number>({
    domain: [yMin, yMax],
    range: [localHeight - localMargin.bottom, localMargin.top],
  });

  return (
    <article className={styles.companyCard}>
      <div className={styles.companyCardTop}>
        <strong>{ticker}</strong>
        <span>{formatValue(series[series.length - 1], "currency", currency)}</span>
      </div>
      {displayMode === "table" ? (
        <div className={styles.companyTableWrap}>
          <table className={styles.companyMiniTable}>
            <thead>
              <tr>
                <th>Quarter</th>
                <th>Value</th>
              </tr>
            </thead>
            <tbody>
              {series.slice(-6).map((value, index) => (
                <tr key={`${ticker}-row-${index}`}>
                  <td>{`Q${series.length - 5 + index}`}</td>
                  <td>{formatValue(value, "currency", currency)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className={styles.companyChartHost}>
          <svg viewBox={`0 0 ${localWidth} ${localHeight}`} className={styles.companySvg} aria-label={`${ticker} visualization`}>
            <rect x={localMargin.left} y={localMargin.top} width={localInnerWidth} height={localInnerHeight} rx={10} fill="rgba(255,255,255,0.52)" />
            <GridRows scale={yScale} left={localMargin.left} width={localInnerWidth} numTicks={4} stroke="rgba(92, 108, 143, 0.2)" strokeDasharray="2,4" />

            <defs>
              <linearGradient id={gradientId} x1="0" x2="0" y1="0" y2="1">
                <stop offset="0%" stopColor="rgba(78, 121, 167, 0.36)" />
                <stop offset="100%" stopColor="rgba(78, 121, 167, 0.02)" />
              </linearGradient>
            </defs>

            {chartType === "bar"
              ? (() => {
                  const band = scaleBand<string>({
                    domain: data.map((point) => `${point.x}`),
                    range: [localMargin.left, localWidth - localMargin.right],
                    padding: 0.34,
                  });

                  return data.map((point) => {
                    const x = band(`${point.x}`) ?? 0;
                    const y = yScale(point.y) ?? 0;
                    const height = Math.max(2, localHeight - localMargin.bottom - y);

                    return (
                      <Bar
                        key={`${ticker}-bar-${point.x}`}
                        x={x}
                        y={y}
                        width={band.bandwidth()}
                        height={height}
                        rx={8}
                        fill={`rgba(78, 121, 167, ${0.44 + point.x * 0.05})`}
                        onMouseMove={() =>
                          setTooltip({
                            x: x + band.bandwidth() * 0.5,
                            y,
                            period: `Q${point.x + 1}`,
                            value: formatValue(point.y, "currency", currency),
                            series: ticker,
                          })
                        }
                        onMouseLeave={() => setTooltip(null)}
                      />
                    );
                  });
                })()
              : (
                <>
                  {chartType === "area" ? (
                    <AreaClosed
                      data={data}
                      x={(d) => xScale(d.x) ?? 0}
                      y={(d) => yScale(d.y) ?? 0}
                      yScale={yScale}
                      fill={`url(#${gradientId})`}
                      stroke={tableauPalette.blue}
                      strokeWidth={2}
                      curve={curve}
                    />
                  ) : null}
                  {chartType === "scatter" ? null : (
                    <LinePath
                      data={data}
                      x={(d) => xScale(d.x) ?? 0}
                      y={(d) => yScale(d.y) ?? 0}
                      curve={curve}
                      stroke={tableauPalette.blue}
                      strokeWidth={2.1}
                    />
                  )}
                  {data.map((point) => {
                    const x = xScale(point.x) ?? 0;
                    const y = yScale(point.y) ?? 0;
                    return (
                      <circle
                        key={`${ticker}-dot-${point.x}`}
                        cx={x}
                        cy={y}
                        r={2.2}
                        fill="rgba(240,245,255,0.94)"
                        stroke={tableauPalette.blue}
                        strokeWidth={1.2}
                      />
                    );
                  })}
                  <rect
                    x={localMargin.left}
                    y={localMargin.top}
                    width={localInnerWidth}
                    height={localInnerHeight}
                    fill="transparent"
                    onMouseMove={(event) => {
                      const index = indexFromPointer(event, series.length);
                      const value = series[index] ?? series[series.length - 1] ?? 0;
                      const x = xScale(index) ?? 0;
                      const y = yScale(value) ?? 0;

                      setTooltip({
                        x,
                        y,
                        period: `Q${index + 1}`,
                        value: formatValue(value, "currency", currency),
                        series: ticker,
                      });
                    }}
                    onMouseLeave={() => setTooltip(null)}
                  />
                </>
              )}

            <AxisBottom
              top={localHeight - localMargin.bottom}
              scale={xScale}
              numTicks={Math.min(series.length, 6)}
              tickFormat={(value) => quarterTickLabel(Number(value))}
              stroke={tableauPalette.axis}
              tickStroke={tableauPalette.axis}
              tickLabelProps={() => ({ fill: tableauPalette.tick, fontSize: 10, textAnchor: "middle", dy: "0.45em" })}
            />
            <AxisLeft
              left={localMargin.left}
              scale={yScale}
              numTicks={4}
              tickFormat={(value) => formatAxisTick(Number(value))}
              stroke={tableauPalette.axis}
              tickStroke={tableauPalette.axis}
              tickLabelProps={() => ({ fill: tableauPalette.tick, fontSize: 10, textAnchor: "end", dx: "-0.35em", dy: "0.3em" })}
            />
          </svg>

          <div
            className={styles.companyTooltip}
            style={{
              opacity: tooltip ? 1 : 0,
              left: tooltip ? `${clampNumber((tooltip.x / localWidth) * 100, 8, 82)}%` : "0%",
              top: tooltip ? `${clampNumber((tooltip.y / localHeight) * 100 - 12, 10, 74)}%` : "0%",
            }}
          >
            <span>{tooltip?.period}</span>
            <strong>{tooltip?.value}</strong>
          </div>
        </div>
      )}

      {displayMode === "split" ? (
        <div className={styles.companyTableWrap}>
          <table className={styles.companyMiniTable}>
            <thead>
              <tr>
                <th>Quarter</th>
                <th>Value</th>
              </tr>
            </thead>
            <tbody>
              {series.slice(-4).map((value, index) => (
                <tr key={`${ticker}-split-row-${index}`}>
                  <td>{`Q${series.length - 3 + index}`}</td>
                  <td>{formatValue(value, "currency", currency)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </article>
  );
}

export function CfoDashboardPrototype() {
  const rootRef = useRef<HTMLDivElement | null>(null);
  const sectionRefs = useRef<Record<string, HTMLElement | null>>({});

  const [year, setYear] = useState<Year>("2025");
  const [region, setRegion] = useState<Region>("All Regions");
  const [currency, setCurrency] = useState<Currency>("USD");
  const [viewFilter, setViewFilter] = useState<ViewFilter>("chart");
  const [chartType, setChartType] = useState<ChartType>("line");
  const [displayMode, setDisplayMode] = useState<DisplayMode>("graph");
  const [metric, setMetric] = useState<Metric>("EBITDA_MARGIN");
  const [searchText, setSearchText] = useState("");
  const [timestamp, setTimestamp] = useState<Date | null>(null);

  const [selectedCompetitors, setSelectedCompetitors] = useState<CompanyTicker[]>(["META", "AAPL", "MSFT"]);
  const [customCompetitors, setCustomCompetitors] = useState<CompanyTicker[]>([]);
  const [customTicker, setCustomTicker] = useState("");
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [activeSectionId, setActiveSectionId] = useState<string>(dashboardSections[0]?.id ?? "overview");
  const [compareCompanyCount, setCompareCompanyCount] = useState(4);
  const [showCompareCompanies, setShowCompareCompanies] = useState(true);
  const [companyViewMode, setCompanyViewMode] = useState<"grid" | "dynamic">("grid");
  const [companyFocus, setCompanyFocus] = useState<string[]>(["META", "AAPL", "MSFT"]);
  const [companyDragTicker, setCompanyDragTicker] = useState<string | null>(null);
  const [companyDragTarget, setCompanyDragTarget] = useState<string | null>(null);
  const [overviewWindow, setOverviewWindow] = useState<6 | 8>(8);
  const [marginBridgeMode, setMarginBridgeMode] = useState<"conservative" | "balanced" | "aggressive">("balanced");
  const [advancedBias, setAdvancedBias] = useState<"balanced" | "upside" | "defensive">("balanced");

  const [agentTicker, setAgentTicker] = useState("META");
  const [agentInput, setAgentInput] = useState("");
  const [agentOpen, setAgentOpen] = useState(false);
  const [agentLoading, setAgentLoading] = useState(false);
  const [agentMessages, setAgentMessages] = useState<AgentMessage[]>([]);
  const kaiButtonRef = useRef<HTMLButtonElement | null>(null);
  const kaiPanelRef = useRef<HTMLDivElement | null>(null);
  const controlPanelRef = useRef<HTMLDivElement | null>(null);
  const snapLockRef = useRef(false);
  const agentListRef = useRef<HTMLDivElement | null>(null);

  const [sectionModes, setSectionModes] = useState<Record<string, ViewMode>>(() => getInitialSectionModes());
  const [focusBySection, setFocusBySection] = useState<Record<string, string[]>>(() => getInitialFocusMap());

  const [visibleSections, setVisibleSections] = useState<string[]>(dashboardSections.map((section) => section.id));

  const availableCompetitors = useMemo(() => {
    const merged = [...competitors, ...customCompetitors];
    return merged.filter((ticker, index) => merged.indexOf(ticker) === index);
  }, [customCompetitors]);

  useEffect(() => {
    gsap.registerPlugin(ScrollTrigger);
  }, []);

  useEffect(() => {
    setCompanyFocus((prev) => {
      const filtered = prev.filter((ticker) => selectedCompetitors.includes(ticker));
      if (filtered.length) return filtered;
      return selectedCompetitors[0] ? [selectedCompetitors[0]] : [];
    });
  }, [selectedCompetitors]);

  useEffect(() => {
    const tick = () => setTimestamp(new Date());
    tick();
    const interval = window.setInterval(tick, 45_000);
    return () => window.clearInterval(interval);
  }, []);

  useEffect(() => {
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduceMotion) return;

    const ctx = gsap.context(() => {
      gsap.from("[data-header='true']", {
        opacity: 0,
        y: 16,
        duration: 0.7,
        ease: "power2.out",
      });

      gsap.from("[data-sidebar='true']", {
        opacity: 0,
        x: -18,
        duration: 0.7,
        ease: "power2.out",
      });

      gsap.utils.toArray<HTMLElement>("[data-section-card='true']").forEach((node) => {
        gsap.from(node, {
          opacity: 0,
          y: 24,
          duration: 0.65,
          ease: "power2.out",
          scrollTrigger: {
            trigger: node,
            start: "top 84%",
            toggleActions: "play none none reverse",
          },
        });
      });
    }, rootRef);

    return () => ctx.revert();
  }, []);

  useEffect(() => {
    if (!controlPanelRef.current) return;
    gsap.fromTo(
      controlPanelRef.current,
      { autoAlpha: 0, y: 9 },
      { autoAlpha: 1, y: 0, duration: 0.24, ease: "power2.out", overwrite: "auto" },
    );
  }, [activeSectionId]);

  useEffect(() => {
    if (!agentListRef.current || !agentOpen) return;
    const node = agentListRef.current;
    node.scrollTo({ top: node.scrollHeight, behavior: "smooth" });
  }, [agentMessages, agentOpen]);

  useEffect(() => {
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduceMotion) return;

    const ctx = gsap.context(() => {
      gsap.fromTo(
        "[data-dashboard-tile='true']",
        { opacity: 0.72, y: 8, scale: 0.992 },
        {
          opacity: 1,
          y: 0,
          scale: 1,
          duration: 0.45,
          stagger: 0.01,
          ease: "power2.out",
          overwrite: "auto",
        },
      );
    }, rootRef);

    return () => ctx.revert();
  }, [
    year,
    region,
    currency,
    viewFilter,
    chartType,
    displayMode,
    metric,
    selectedCompetitors,
    sectionModes,
    focusBySection,
    searchText,
    overviewWindow,
    compareCompanyCount,
    showCompareCompanies,
    marginBridgeMode,
    advancedBias,
  ]);

  const preparedSections = useMemo(() => {
    const query = searchText.trim().toLowerCase();
    const bridgeMultiplier =
      marginBridgeMode === "conservative" ? 0.9 : marginBridgeMode === "aggressive" ? 1.12 : 1;
    const advancedMultiplier =
      advancedBias === "upside" ? 1.08 : advancedBias === "defensive" ? 0.94 : 1;

    return dashboardSections
      .filter((section) => visibleSections.includes(section.id))
      .map((section) => {
        const tiles = section.tiles
          .filter((tile) => {
            if (!query) return true;
            return (
              tile.title.toLowerCase().includes(query) ||
              tile.subtitle.toLowerCase().includes(query) ||
              section.title.toLowerCase().includes(query)
            );
          })
          .map((tile) => {
            let series = transformSeries({
              tile,
              sectionId: section.id,
              series: tile.baseSeries,
              year,
              region,
              metric,
              selectedCompetitors,
              viewFilter,
            });

            let secondarySeries = tile.secondarySeries
              ? transformSeries({
                  tile,
                  sectionId: section.id,
                  series: tile.secondarySeries,
                  year,
                  region,
                  metric,
                  selectedCompetitors,
                  viewFilter,
                })
              : undefined;

            if (section.id === "margin-bridge") {
              series = series.map((value) => value * bridgeMultiplier);
              secondarySeries = secondarySeries?.map((value) => value * bridgeMultiplier);
            }

            if (section.id === "advanced-charts") {
              series = series.map((value) => value * advancedMultiplier);
              secondarySeries = secondarySeries?.map((value) => value * advancedMultiplier);
            }

            if (section.id === "overview" && overviewWindow === 6) {
              series = series.slice(-6);
              secondarySeries = secondarySeries?.slice(-6);
            }

            const first = series[0] ?? 0;
            const last = series[series.length - 1] ?? first;
            const companyCompareLines =
              tile.kind === "compare" && showCompareCompanies
                ? selectedCompetitors.slice(0, compareCompanyCount).map((ticker, index) => {
                    const hash = stableHash(`${section.id}-${tile.id}-${ticker}`);
                    const base = secondarySeries ?? series;
                    const drift = 0.92 + (hash % 19) / 100;
                    const tickerSeries = base.map((value, pointIndex) => {
                      const motion = 1 + Math.sin((pointIndex + 1) * 0.85 + hash * 0.006) * 0.023;
                      return value * drift * motion;
                    });

                    return {
                      id: `${tile.id}-${ticker}`,
                      label: ticker,
                      series: tickerSeries,
                      color: compareLinePalette[(index + 2) % compareLinePalette.length],
                    } satisfies ComparisonLine;
                  })
                : [];

            const comparisonSeries =
              tile.kind === "compare"
                ? [
                    {
                      id: `${tile.id}-base`,
                      label: "Base",
                      series,
                      color: compareLinePalette[0],
                    },
                    ...(secondarySeries
                      ? [
                          {
                            id: `${tile.id}-peer`,
                            label: selectedCompetitors[0] ? `${selectedCompetitors[0]} Peer` : "Peer Benchmark",
                            series: secondarySeries,
                            color: compareLinePalette[1],
                            dashed: true,
                          } satisfies ComparisonLine,
                        ]
                      : []),
                    ...companyCompareLines,
                  ]
                : undefined;

            return {
              ...tile,
              currency,
              series,
              secondarySeries,
              comparisonSeries,
              valueLabel: formatValue(last, tile.unit, currency),
              deltaLabel: toDeltaLabel(first, last, tile.unit, currency),
              tableRows: buildTableRows(tile, series, secondarySeries, currency),
              tags: tile.tags ?? ["Filtered", year, region],
            } satisfies DerivedTile;
          });

        return {
          ...section,
          tiles,
        };
      })
      .filter((section) => section.tiles.length > 0);
  }, [
    visibleSections,
    searchText,
    year,
    region,
    metric,
    selectedCompetitors,
    viewFilter,
    currency,
    overviewWindow,
    compareCompanyCount,
    showCompareCompanies,
    marginBridgeMode,
    advancedBias,
  ]);

  useEffect(() => {
    if (!preparedSections.length) return;
    if (!preparedSections.some((section) => section.id === activeSectionId)) {
      setActiveSectionId(preparedSections[0].id);
    }
  }, [preparedSections, activeSectionId]);

  useEffect(() => {
    if (!preparedSections.length) return;

    let snapTimer: number | undefined;

    const getNodes = () =>
      preparedSections
        .map((section) => ({ id: section.id, node: sectionRefs.current[section.id] }))
        .filter((item): item is { id: string; node: HTMLElement } => Boolean(item.node));

    const onScroll = () => {
      const nodes = getNodes();
      if (!nodes.length) return;

      const viewportCenter = window.innerHeight / 2;
      let closest = nodes[0];
      let minDistance = Number.POSITIVE_INFINITY;

      nodes.forEach((entry) => {
        const rect = entry.node.getBoundingClientRect();
        const center = rect.top + rect.height / 2;
        const distance = Math.abs(center - viewportCenter);
        if (distance < minDistance) {
          minDistance = distance;
          closest = entry;
        }
      });

      setActiveSectionId((prev) => (prev === closest.id ? prev : closest.id));

      if (snapLockRef.current) return;
      window.clearTimeout(snapTimer);
      snapTimer = window.setTimeout(() => {
        const rect = closest.node.getBoundingClientRect();
        const sectionCenter = rect.top + rect.height / 2;
        const distance = Math.abs(sectionCenter - viewportCenter);
        if (distance < window.innerHeight * 0.44) {
          snapLockRef.current = true;
          closest.node.scrollIntoView({ behavior: "smooth", block: "center" });
          window.setTimeout(() => {
            snapLockRef.current = false;
          }, 560);
        }
      }, 110);
    };

    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      window.removeEventListener("scroll", onScroll);
      window.clearTimeout(snapTimer);
    };
  }, [preparedSections]);

  const companyVisuals = useMemo(() => {
    const base = [180, 195, 212, 207, 226, 238, 249, 264];
    return selectedCompetitors.map((ticker) => {
      const factor = 1 + (stableHash(ticker) % 17) / 140;
      const series = transformSeries({
        tile: {
          id: `company-${ticker}`,
          title: ticker,
          subtitle: "Company trace",
          kind: "trend",
          unit: "currency",
          baseSeries: base,
        },
        sectionId: "competitor-analysis",
        series: base,
        year,
        region,
        metric,
        selectedCompetitors,
        viewFilter,
        tickerSeed: ticker,
      }).map((v) => v * factor);

      return { ticker, series };
    });
  }, [selectedCompetitors, year, region, metric, viewFilter]);

  const companyVisualMap = useMemo(
    () => new Map(companyVisuals.map((item) => [item.ticker, item])),
    [companyVisuals],
  );

  const focusedCompanyVisuals = useMemo(
    () =>
      companyFocus
        .map((ticker) => companyVisualMap.get(ticker))
        .filter((item): item is { ticker: string; series: number[] } => Boolean(item)),
    [companyFocus, companyVisualMap],
  );

  const companyRailVisuals = useMemo(
    () => companyVisuals.filter((item) => !companyFocus.includes(item.ticker)),
    [companyVisuals, companyFocus],
  );

  const dashboardContext = useMemo(
    () => ({
      year,
      region,
      currency,
      viewFilter,
      metric,
      chartType,
      displayMode,
      selectedCompetitors,
      activeSectionId,
      compareCompanyCount,
      showCompareCompanies,
      overviewWindow,
      marginBridgeMode,
      advancedBias,
      timestamp: timestamp?.toISOString() ?? null,
      sectionTitles: preparedSections.map((section) => section.title),
      sectionSnapshots: preparedSections.map((section) => ({
        id: section.id,
        title: section.title,
        tiles: section.tiles.slice(0, 3).map((tile) => ({
          title: tile.title,
          value: tile.valueLabel,
          delta: tile.deltaLabel,
        })),
      })),
    }),
    [
      year,
      region,
      currency,
      viewFilter,
      metric,
      chartType,
      displayMode,
      selectedCompetitors,
      activeSectionId,
      compareCompanyCount,
      showCompareCompanies,
      overviewWindow,
      marginBridgeMode,
      advancedBias,
      timestamp,
      preparedSections,
    ],
  );

  const requestRag = async (params: {
    mode: "summary" | "qa";
    ticker: string;
    question?: string | null;
  }) => {
    const { mode, ticker, question } = params;
    const normalizedTicker = ticker.trim().toUpperCase();
    if (!normalizedTicker) {
      throw new Error("Ticker is required.");
    }

    if (mode === "qa" && !question?.trim()) {
      throw new Error("Question is required.");
    }

    const response = await fetch("/api/rag", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        mode,
        ticker: normalizedTicker,
        question: mode === "qa" ? question?.trim() : null,
        dashboardContext,
      }),
    });

    const payload = (await response.json()) as RagResponse & { error?: string };
    if (!response.ok) {
      throw new Error(payload.error ?? "RAG request failed");
    }

    return payload;
  };

  const runAgentRequest = async (mode: "summary" | "qa") => {
    const ticker = agentTicker.trim().toUpperCase();
    const question = agentInput.trim();
    const userText = mode === "summary" ? `Summarize latest 10-K for ${ticker}` : question;
    if (!ticker || (mode === "qa" && !question)) return;

    const userMessage: AgentMessage = {
      id: `${Date.now()}-user`,
      role: "user",
      text: userText,
    };
    setAgentMessages((prev) => [...prev, userMessage]);
    setAgentLoading(true);

    try {
      const payload = await requestRag({
        mode,
        ticker,
        question: mode === "qa" ? question : null,
      });

      setAgentMessages((prev) => [
        ...prev,
        {
          id: `${Date.now()}-assistant`,
          role: "assistant",
          text: payload.answer,
          model: payload.model,
          filing: payload.filing,
          snippets: payload.snippets,
        },
      ]);
    } catch (error) {
      setAgentMessages((prev) => [
        ...prev,
        {
          id: `${Date.now()}-assistant-error`,
          role: "assistant",
          text: error instanceof Error ? error.message : "Unable to generate response.",
        },
      ]);
    } finally {
      setAgentLoading(false);
      if (mode === "qa") {
        setAgentInput("");
      }
    }
  };

  const toggleAgentPanel = () => {
    if (kaiButtonRef.current) {
      gsap.fromTo(
        kaiButtonRef.current,
        { rotate: 0 },
        { rotate: 360, duration: 0.7, ease: "power3.out", overwrite: "auto" },
      );
    }
    setAgentOpen((prev) => !prev);
  };

  const toggleCompetitor = (value: CompanyTicker) => {
    setSelectedCompetitors((prev) => {
      if (prev.includes(value)) {
        const next = prev.filter((item) => item !== value);
        return next.length ? next : [prev[0] ?? value];
      }
      return [...prev, value];
    });
  };

  const addCustomTicker = () => {
    const normalized = customTicker.trim().toUpperCase().replace(/[^A-Z.]/g, "");
    if (!normalized) return;
    setCustomCompetitors((prev) => (prev.includes(normalized) ? prev : [...prev, normalized]));
    setSelectedCompetitors((prev) => (prev.includes(normalized) ? prev : [...prev, normalized]));
    setCustomTicker("");
  };

  const resetFilters = () => {
    setYear("2025");
    setRegion("All Regions");
    setCurrency("USD");
    setViewFilter("chart");
    setChartType("line");
    setDisplayMode("graph");
    setMetric("EBITDA_MARGIN");
    setSelectedCompetitors(["META", "AAPL", "MSFT"]);
    setCustomCompetitors([]);
    setCompareCompanyCount(4);
    setShowCompareCompanies(true);
    setCompanyViewMode("grid");
    setCompanyFocus(["META", "AAPL", "MSFT"]);
    setOverviewWindow(8);
    setMarginBridgeMode("balanced");
    setAdvancedBias("balanced");
    setSearchText("");
    setVisibleSections(dashboardSections.map((section) => section.id));
    setSectionModes(getInitialSectionModes());
    setFocusBySection(getInitialFocusMap());
    setTimestamp(new Date());
  };

  const setModeForSection = (sectionId: string, mode: ViewMode) => {
    setSectionModes((prev) => ({ ...prev, [sectionId]: mode }));
    if (mode === "focus") {
      setFocusBySection((prev) => {
        if (prev[sectionId]?.length) return prev;
        const fallback = dashboardSections.find((section) => section.id === sectionId)?.tiles[0]?.id;
        return { ...prev, [sectionId]: fallback ? [fallback] : [] };
      });
    }
  };

  const toggleFocus = (sectionId: string, tileId: string) => {
    setFocusBySection((prev) => {
      const current = prev[sectionId] ?? [];
      if (current.includes(tileId)) {
        return {
          ...prev,
          [sectionId]: [tileId, ...current.filter((id) => id !== tileId)],
        };
      }
      return { ...prev, [sectionId]: [tileId, ...current] };
    });
  };

  const insertFocusTile = (sectionId: string, tileId: string, targetIndex: number) => {
    setFocusBySection((prev) => {
      const current = (prev[sectionId] ?? []).filter((id) => id !== tileId);
      const boundedIndex = clampNumber(targetIndex, 0, current.length);
      current.splice(boundedIndex, 0, tileId);
      return { ...prev, [sectionId]: current.length ? current : [tileId] };
    });
  };

  const removeFocusTile = (sectionId: string, tileId: string) => {
    setFocusBySection((prev) => {
      const current = prev[sectionId] ?? [];
      const next = current.filter((id) => id !== tileId);
      if (next.length) return { ...prev, [sectionId]: next };
      const fallback = dashboardSections.find((section) => section.id === sectionId)?.tiles[0]?.id;
      return { ...prev, [sectionId]: fallback ? [fallback] : [] };
    });
  };

  const insertCompanyFocus = (ticker: string, targetIndex: number) => {
    setCompanyFocus((prev) => {
      const current = prev.filter((item) => selectedCompetitors.includes(item) && item !== ticker);
      const boundedIndex = clampNumber(targetIndex, 0, current.length);
      current.splice(boundedIndex, 0, ticker);
      return current.length ? current : [ticker];
    });
  };

  const removeCompanyFocus = (ticker: string) => {
    setCompanyFocus((prev) => {
      const current = prev.filter((item) => selectedCompetitors.includes(item));
      const next = current.filter((item) => item !== ticker);
      if (next.length) return next;
      const fallback = selectedCompetitors.find((item) => item !== ticker) ?? selectedCompetitors[0];
      return fallback ? [fallback] : [];
    });
  };

  const handleCompanyDragStart = (ticker: string) => {
    setCompanyDragTicker(ticker);
  };

  const handleCompanyDragEnd = () => {
    setCompanyDragTicker(null);
    setCompanyDragTarget(null);
  };

  const registerSection = (id: string, node: HTMLElement | null) => {
    sectionRefs.current[id] = node;
  };

  return (
    <div className={cx(styles.shell, sidebarCollapsed && styles.shellCentered)} ref={rootRef}>
      <WebGLBackdrop />
      {sidebarCollapsed ? (
        <button
          type="button"
          className={styles.sidebarDockToggle}
          aria-label="Open controls panel"
          onClick={() => setSidebarCollapsed(false)}
        >
          <span />
          <span />
          <span />
        </button>
      ) : null}

      <div className={cx(styles.layout, sidebarCollapsed && styles.layoutSidebarCollapsed)}>
        <aside className={cx(styles.sidebar, sidebarCollapsed && styles.sidebarCollapsed)} data-sidebar="true">
          <button
            type="button"
            className={styles.sidebarToggle}
            aria-label="Close controls panel"
            onClick={() => setSidebarCollapsed((prev) => !prev)}
          >
            <span />
            <span />
            <span />
          </button>
          <h2 className={styles.controlsTitle}>Controls</h2>

          <div className={styles.sidebarGroup}>
            <p className={styles.groupLabel}>Global Filters</p>
            <div className={styles.sidebarFilterGrid}>
              <label className={styles.filterControl}>
                <span className={styles.filterLabel}>Year</span>
                <select value={year} onChange={(event) => setYear(event.target.value as Year)} className={styles.selectInput}>
                  {years.map((value) => <option key={`year-side-${value}`} value={value}>{value}</option>)}
                </select>
              </label>
              <label className={styles.filterControl}>
                <span className={styles.filterLabel}>Region</span>
                <select value={region} onChange={(event) => setRegion(event.target.value as Region)} className={styles.selectInput}>
                  {regions.map((value) => <option key={`region-side-${value}`} value={value}>{value}</option>)}
                </select>
              </label>
              <label className={styles.filterControl}>
                <span className={styles.filterLabel}>Currency</span>
                <select value={currency} onChange={(event) => setCurrency(event.target.value as Currency)} className={styles.selectInput}>
                  {currencies.map((value) => <option key={`currency-side-${value}`} value={value}>{value}</option>)}
                </select>
              </label>
              <label className={styles.filterControl}>
                <span className={styles.filterLabel}>Metric</span>
                <select value={metric} onChange={(event) => setMetric(event.target.value as Metric)} className={styles.selectInput}>
                  {metrics.map((value) => <option key={`metric-side-${value}`} value={value}>{value}</option>)}
                </select>
              </label>
            </div>
            <label className={styles.filterControl}>
              <span className={styles.filterLabel}>Search Tile</span>
              <input
                value={searchText}
                onChange={(event) => setSearchText(event.target.value)}
                className={styles.searchInput}
                placeholder="Search title or section"
              />
            </label>
            <div className={styles.controlStrip}>
              <span className={styles.filterLabel}>Chart Type</span>
              <div className={styles.segmented}>
                {chartTypes.map((value) => (
                  <button
                    key={`chart-global-${value}`}
                    type="button"
                    className={cx(styles.segmentedButton, chartType === value && styles.segmentedButtonActive)}
                    onClick={() => setChartType(value)}
                  >
                    {value}
                  </button>
                ))}
              </div>
            </div>
            <div className={styles.controlStrip}>
              <span className={styles.filterLabel}>Display Mode</span>
              <div className={styles.segmented}>
                {displayModes.map((value) => (
                  <button
                    key={`display-global-${value}`}
                    type="button"
                    className={cx(styles.segmentedButton, displayMode === value && styles.segmentedButtonActive)}
                    onClick={() => setDisplayMode(value)}
                  >
                    {value}
                  </button>
                ))}
              </div>
            </div>
            <button type="button" className={styles.resetButton} onClick={resetFilters}>
              Reset Filters
            </button>
          </div>

          <div className={styles.sidebarGroup}>
            <p className={styles.groupLabel}>Company Visualizer</p>
            <p className={styles.ragMeta}>Activate companies for visualizer and compare overlays.</p>
            <div className={styles.chipWrap}>
              {availableCompetitors.map((ticker) => (
                <button
                  key={`company-chip-${ticker}`}
                  type="button"
                  className={cx(styles.competitorChip, selectedCompetitors.includes(ticker) && styles.competitorChipActive)}
                  onClick={() => toggleCompetitor(ticker)}
                >
                  {ticker}
                </button>
              ))}
            </div>
            <div className={styles.customTickerRow}>
              <input
                value={customTicker}
                onChange={(event) => setCustomTicker(event.target.value)}
                placeholder="Add ticker"
                className={styles.searchInput}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    event.preventDefault();
                    addCustomTicker();
                  }
                }}
              />
              <button type="button" className={styles.actionButton} onClick={addCustomTicker}>
                Add
              </button>
            </div>
            <label className={styles.checkboxLabel}>
              <input type="checkbox" checked={showCompareCompanies} onChange={(event) => setShowCompareCompanies(event.target.checked)} />
              <span>Enable in compare charts</span>
            </label>
            <label className={styles.filterControl}>
              <span className={styles.filterLabel}>Overlay Count</span>
              <select value={compareCompanyCount} onChange={(event) => setCompareCompanyCount(Number(event.target.value))} className={styles.selectInput}>
                <option value={2}>2 companies</option>
                <option value={4}>4 companies</option>
                <option value={6}>6 companies</option>
              </select>
            </label>
          </div>

          <div className={styles.sidebarGroup} ref={controlPanelRef}>
            <p className={styles.groupLabel}>Section-Specific Controls</p>
            <div key={activeSectionId} className={styles.sectionControlPanel}>
              {activeSectionId === "overview" ? (
                <>
                  <label className={styles.filterControl}>
                    <span className={styles.filterLabel}>Overview Window</span>
                    <select value={overviewWindow} onChange={(event) => setOverviewWindow(Number(event.target.value) as 6 | 8)} className={styles.selectInput}>
                      <option value={8}>Last 8 Quarters</option>
                      <option value={6}>Last 6 Quarters</option>
                    </select>
                  </label>
                  <label className={styles.filterControl}>
                    <span className={styles.filterLabel}>View Lens</span>
                    <select value={viewFilter} onChange={(event) => setViewFilter(event.target.value as ViewFilter)} className={styles.selectInput}>
                      {viewModes.map((value) => <option key={`view-side-${value}`} value={value}>{value}</option>)}
                    </select>
                  </label>
                </>
              ) : null}

              {activeSectionId === "competitor-analysis" ? (
                <>
                  <label className={styles.filterControl}>
                    <span className={styles.filterLabel}>View Lens</span>
                    <select value={viewFilter} onChange={(event) => setViewFilter(event.target.value as ViewFilter)} className={styles.selectInput}>
                      {viewModes.map((value) => <option key={`competitor-view-${value}`} value={value}>{value}</option>)}
                    </select>
                  </label>
                  <p className={styles.ragMeta}>Active peers: {selectedCompetitors.join(", ")}</p>
                </>
              ) : null}

              {activeSectionId === "comparative-analysis" ? (
                <>
                  <label className={styles.filterControl}>
                    <span className={styles.filterLabel}>Company Line Count</span>
                    <select value={compareCompanyCount} onChange={(event) => setCompareCompanyCount(Number(event.target.value))} className={styles.selectInput}>
                      <option value={2}>2 companies</option>
                      <option value={4}>4 companies</option>
                      <option value={6}>6 companies</option>
                    </select>
                  </label>
                  <p className={styles.ragMeta}>Use Company Visualizer controls to activate/deactivate peers.</p>
                </>
              ) : null}

              {activeSectionId === "margin-bridge" ? (
                <label className={styles.filterControl}>
                  <span className={styles.filterLabel}>Bridge Intensity</span>
                  <select value={marginBridgeMode} onChange={(event) => setMarginBridgeMode(event.target.value as "conservative" | "balanced" | "aggressive")} className={styles.selectInput}>
                    <option value="conservative">Conservative</option>
                    <option value="balanced">Balanced</option>
                    <option value="aggressive">Aggressive</option>
                  </select>
                </label>
              ) : null}

              {activeSectionId === "advanced-charts" ? (
                <>
                  <label className={styles.filterControl}>
                    <span className={styles.filterLabel}>Scenario Bias</span>
                    <select value={advancedBias} onChange={(event) => setAdvancedBias(event.target.value as "balanced" | "upside" | "defensive")} className={styles.selectInput}>
                      <option value="balanced">Balanced</option>
                      <option value="upside">Upside</option>
                      <option value="defensive">Defensive</option>
                    </select>
                  </label>
                  <div className={styles.segmented}>
                    {chartTypes.map((value) => (
                      <button
                        key={`chart-side-${value}`}
                        type="button"
                        className={cx(styles.segmentedButton, chartType === value && styles.segmentedButtonActive)}
                        onClick={() => setChartType(value)}
                      >
                        {value}
                      </button>
                    ))}
                  </div>
                </>
              ) : null}
            </div>
          </div>

        </aside>

        <main className={cx(styles.main, sidebarCollapsed && styles.mainCentered)}>
          <section className={styles.boardTitleSection} data-header="true">
            <h1 className={styles.boardTitle} data-board-title="true">
              CFO&apos;s Operations Board
            </h1>
          </section>

          <section className={styles.companySection}>
            <header className={styles.companySectionHeader}>
              <h3>Company Visualizer</h3>
              <div className={styles.companySectionControls}>
                <p>{selectedCompetitors.length} companies active</p>
                <div className={styles.segmented}>
                  {(["grid", "dynamic"] as const).map((mode) => (
                    <button
                      key={`company-mode-${mode}`}
                      type="button"
                      className={cx(styles.segmentedButton, companyViewMode === mode && styles.segmentedButtonActive)}
                      onClick={() => setCompanyViewMode(mode)}
                    >
                      {mode}
                    </button>
                  ))}
                </div>
              </div>
            </header>
            {companyViewMode === "dynamic" ? (
              <div className={styles.focusLayout}>
                <div
                  className={cx(styles.focusRail, companyDragTarget === "company-rail" && styles.focusDropActive)}
                  onDragOver={(event) => {
                    event.preventDefault();
                    setCompanyDragTarget("company-rail");
                  }}
                  onDragLeave={() =>
                    setCompanyDragTarget((prev) => (prev === "company-rail" ? null : prev))
                  }
                  onDrop={(event) => {
                    event.preventDefault();
                    if (companyDragTicker) {
                      removeCompanyFocus(companyDragTicker);
                    }
                    setCompanyDragTicker(null);
                    setCompanyDragTarget(null);
                  }}
                >
                  <div className={styles.focusRailHint}>Drop Here To Remove From Focus</div>
                  {companyRailVisuals.map((item) => (
                    <button
                      key={`company-rail-${item.ticker}`}
                      type="button"
                      className={styles.focusRailButton}
                      draggable
                      onClick={() => insertCompanyFocus(item.ticker, focusedCompanyVisuals.length)}
                      onDragStart={() => handleCompanyDragStart(item.ticker)}
                      onDragEnd={handleCompanyDragEnd}
                    >
                      {item.ticker}
                    </button>
                  ))}
                </div>

                <div className={styles.companyDynamicStage}>
                  {focusedCompanyVisuals.map((item, index) => (
                    <div
                      key={`company-slot-${item.ticker}`}
                      className={cx(
                        styles.focusSlot,
                        companyDragTarget === `company-slot-${index}` && styles.focusDropActive,
                      )}
                      onDragOver={(event) => {
                        event.preventDefault();
                        setCompanyDragTarget(`company-slot-${index}`);
                      }}
                      onDragLeave={() =>
                        setCompanyDragTarget((prev) =>
                          prev === `company-slot-${index}` ? null : prev,
                        )
                      }
                      onDrop={(event) => {
                        event.preventDefault();
                        if (companyDragTicker) {
                          insertCompanyFocus(companyDragTicker, index);
                        }
                        setCompanyDragTicker(null);
                        setCompanyDragTarget(null);
                      }}
                    >
                      <div
                        draggable
                        onDragStart={() => handleCompanyDragStart(item.ticker)}
                        onDragEnd={handleCompanyDragEnd}
                        className={styles.focusDraggableCard}
                      >
                        <CompanyViz
                          key={`company-viz-dynamic-${item.ticker}`}
                          ticker={item.ticker}
                          series={item.series}
                          currency={currency}
                          chartType={chartType}
                          displayMode={displayMode}
                        />
                      </div>
                    </div>
                  ))}
                  <div
                    className={cx(
                      styles.focusStageDropEnd,
                      companyDragTarget === "company-slot-end" && styles.focusDropActive,
                    )}
                    onDragOver={(event) => {
                      event.preventDefault();
                      setCompanyDragTarget("company-slot-end");
                    }}
                    onDragLeave={() =>
                      setCompanyDragTarget((prev) =>
                        prev === "company-slot-end" ? null : prev,
                      )
                    }
                    onDrop={(event) => {
                      event.preventDefault();
                      if (companyDragTicker) {
                        insertCompanyFocus(companyDragTicker, focusedCompanyVisuals.length);
                      }
                      setCompanyDragTicker(null);
                      setCompanyDragTarget(null);
                    }}
                  >
                    Drag Company Here To Add To Focus
                  </div>
                </div>
              </div>
            ) : (
              <div className={styles.companyGrid}>
                {companyVisuals.map((item) => (
                  <CompanyViz
                    key={`company-viz-${item.ticker}`}
                    ticker={item.ticker}
                    series={item.series}
                    currency={currency}
                    chartType={chartType}
                    displayMode={displayMode}
                  />
                ))}
              </div>
            )}
          </section>

          <div className={styles.statusBar}>
            <div className={styles.statusItem}><span>Data Quality</span><strong>98.4%</strong></div>
            <div className={styles.statusItem}>
              <span>Last Sync</span>
              <strong>
                {timestamp
                  ? timestamp.toLocaleTimeString([], {
                      hour: "2-digit",
                      minute: "2-digit",
                      second: "2-digit",
                    })
                  : "Syncing..."}
              </strong>
            </div>
            <div className={styles.statusItem}><span>Source</span><strong>Mock SAP S/4HANA Layer</strong></div>
            <div className={styles.statusItem}><span>Active Peers</span><strong>{selectedCompetitors.join(", ")}</strong></div>
          </div>

          {preparedSections.map((section) => (
            <SectionBlock
              key={`section-${section.id}`}
              section={section}
              tiles={section.tiles}
              mode={sectionModes[section.id] ?? "grid"}
              displayMode={displayMode}
              chartType={chartType}
              focusIds={focusBySection[section.id] ?? []}
              onModeChange={(mode) => setModeForSection(section.id, mode)}
              onFocusToggle={(tileId) => toggleFocus(section.id, tileId)}
              onFocusInsert={(tileId, targetIndex) => insertFocusTile(section.id, tileId, targetIndex)}
              onFocusRemove={(tileId) => removeFocusTile(section.id, tileId)}
              registerSection={registerSection}
              isActive={activeSectionId === section.id}
            />
          ))}
        </main>
      </div>

      <div className={styles.kaiDock}>
        <button
          ref={kaiButtonRef}
          type="button"
          className={styles.kaiTrigger}
          onClick={toggleAgentPanel}
          aria-label="Open KAI assistant"
        >
          <Image src="/images/KAI.png" alt="KAI assistant" width={74} height={74} className={styles.kaiAvatar} />
          <span className={styles.kaiGlow} />
        </button>

        <div
          ref={kaiPanelRef}
          className={cx(styles.kaiPanel, agentOpen && styles.kaiPanelOpen)}
        >
          <header className={styles.kaiHeader}>
            <h4 className={styles.kaiTitle}>K.A.I</h4>
            <button type="button" className={styles.kaiClose} onClick={() => setAgentOpen(false)}>
              Close
            </button>
          </header>

          <div className={styles.kaiControls}>
            <label className={styles.filterControl}>
              <span className={styles.filterLabel}>Ticker</span>
              <input
                value={agentTicker}
                onChange={(event) => setAgentTicker(event.target.value.toUpperCase())}
                className={styles.searchInput}
                placeholder="AAPL"
              />
            </label>
          </div>

          <div className={styles.kaiMessages} ref={agentListRef}>
            {agentMessages.map((message) => (
              <article
                key={message.id}
                className={`${styles.kaiMessage} ${message.role === "user" ? styles.kaiUserMessage : styles.kaiAssistantMessage}`}
              >
                <p>{message.text}</p>
                {message.filing ? (
                  <a href={message.filing.filingUrl} target="_blank" rel="noreferrer" className={styles.ragLink}>
                    {message.filing.ticker} {message.filing.form} · {message.filing.filingDate}
                  </a>
                ) : null}
                {message.model ? <span className={styles.kaiMeta}>{message.model}</span> : null}
                {message.snippets?.length ? (
                  <ul className={styles.ragSnippetList}>
                    {message.snippets.slice(0, 2).map((snippet, index) => (
                      <li key={`${message.id}-snippet-${index}`} className={styles.ragSnippetItem}>
                        {snippet}
                      </li>
                    ))}
                  </ul>
                ) : null}
              </article>
            ))}
            {agentLoading ? <p className={styles.kaiLoading}>Analyzing latest filing and dashboard context…</p> : null}
          </div>

          <div className={styles.kaiComposer}>
            <textarea
              value={agentInput}
              onChange={(event) => setAgentInput(event.target.value)}
              className={styles.ragTextarea}
              placeholder="Ask a question that combines the 10-K and dashboard signals"
              onKeyDown={(event) => {
                if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
                  event.preventDefault();
                  void runAgentRequest("qa");
                }
              }}
            />
            <div className={styles.kaiActions}>
              <button
                type="button"
                className={styles.actionButton}
                disabled={agentLoading}
                onClick={() => void runAgentRequest("summary")}
              >
                Summarize 10-K
              </button>
              <button
                type="button"
                className={styles.actionButton}
                disabled={agentLoading || !agentInput.trim()}
                onClick={() => void runAgentRequest("qa")}
              >
                Ask KAI
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
