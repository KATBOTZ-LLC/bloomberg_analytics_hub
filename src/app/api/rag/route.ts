import { NextResponse } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type RagMode = "summary" | "qa";

type RagRequestBody = {
  mode?: RagMode;
  ticker?: string;
  question?: string | null;
  dashboardContext?: unknown;
};

type TickerDirectoryItem = {
  cik_str: number;
  ticker: string;
  title: string;
};

type SubmissionsResponse = {
  filings?: {
    recent?: {
      form?: string[];
      accessionNumber?: string[];
      primaryDocument?: string[];
      filingDate?: string[];
      reportDate?: string[];
    };
  };
};

type FilingMatch = {
  ticker: string;
  companyName: string;
  cik: string;
  form: string;
  filingDate: string;
  reportDate?: string;
  filingUrl: string;
  text: string;
};

type ChunkScore = {
  index: number;
  chunk: string;
  score: number;
};

const SEC_TICKER_DIRECTORY_URL = "https://www.sec.gov/files/company_tickers.json";
const SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions";
const SEC_ARCHIVES_URL = "https://www.sec.gov/Archives/edgar/data";
const DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434";
const DEFAULT_OLLAMA_MODEL = "mistral";

function normalizeTicker(input: string) {
  return input.trim().toUpperCase().replace(/[^A-Z.]/g, "");
}

function secHeaders() {
  return {
    "User-Agent": process.env.SEC_USER_AGENT ?? "CFO Dashboard Prototype (support@katbotz.local)",
    "Accept-Encoding": "gzip, deflate",
    Accept: "application/json, text/html;q=0.9,*/*;q=0.8",
    Host: "www.sec.gov",
  } as Record<string, string>;
}

async function fetchWithTimeout(url: string, init?: RequestInit, timeoutMs = 30000) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  try {
    return await fetch(url, { ...init, signal: controller.signal, cache: "no-store" });
  } finally {
    clearTimeout(timer);
  }
}

function padCik(cik: number | string) {
  return String(cik).padStart(10, "0");
}

function normalizeDashboardContext(context: unknown) {
  if (!context || typeof context !== "object") return "No dashboard context provided.";

  try {
    const value = context as Record<string, unknown>;
    const sectionSnapshots = Array.isArray(value.sectionSnapshots)
      ? value.sectionSnapshots
          .slice(0, 6)
          .map((section) => {
            if (!section || typeof section !== "object") return null;
            const safeSection = section as Record<string, unknown>;
            const title = typeof safeSection.title === "string" ? safeSection.title : "Section";
            const tiles = Array.isArray(safeSection.tiles)
              ? safeSection.tiles
                  .slice(0, 3)
                  .map((tile) => {
                    if (!tile || typeof tile !== "object") return null;
                    const safeTile = tile as Record<string, unknown>;
                    const tileTitle = typeof safeTile.title === "string" ? safeTile.title : "Tile";
                    const tileValue = typeof safeTile.value === "string" ? safeTile.value : "n/a";
                    const tileDelta = typeof safeTile.delta === "string" ? safeTile.delta : "n/a";
                    return `${tileTitle}: ${tileValue} (${tileDelta})`;
                  })
                  .filter((item): item is string => Boolean(item))
              : [];

            return `${title} -> ${tiles.join(" | ")}`;
          })
          .filter((item): item is string => Boolean(item))
      : [];

    const selectedCompetitors = Array.isArray(value.selectedCompetitors)
      ? value.selectedCompetitors.filter((item): item is string => typeof item === "string").join(", ")
      : "";

    const lines = [
      `year=${String(value.year ?? "n/a")}`,
      `region=${String(value.region ?? "n/a")}`,
      `currency=${String(value.currency ?? "n/a")}`,
      `view=${String(value.viewFilter ?? "n/a")}`,
      `metric=${String(value.metric ?? "n/a")}`,
      `chartType=${String(value.chartType ?? "n/a")}`,
      `displayMode=${String(value.displayMode ?? "n/a")}`,
      `selectedCompetitors=${selectedCompetitors || "none"}`,
    ];

    if (sectionSnapshots.length) {
      lines.push("sectionSnapshots=");
      lines.push(...sectionSnapshots);
    }

    return lines.join("\n");
  } catch {
    return "Dashboard context provided but could not be normalized.";
  }
}

function cleanText(input: string) {
  const withoutScripts = input
    .replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, " ")
    .replace(/<style\b[^<]*(?:(?!<\/style>)<[^<]*)*<\/style>/gi, " ")
    .replace(/<noscript\b[^<]*(?:(?!<\/noscript>)<[^<]*)*<\/noscript>/gi, " ")
    .replace(/<!--([\s\S]*?)-->/g, " ")
    .replace(/<\/p>/gi, "\n")
    .replace(/<br\s*\/?\s*>/gi, "\n")
    .replace(/<[^>]+>/g, " ");

  const decoded = withoutScripts
    .replace(/&nbsp;/gi, " ")
    .replace(/&amp;/gi, "&")
    .replace(/&lt;/gi, "<")
    .replace(/&gt;/gi, ">")
    .replace(/&quot;/gi, '"')
    .replace(/&#39;/gi, "'")
    .replace(/&#x2F;/gi, "/")
    .replace(/&#x27;/gi, "'")
    .replace(/&#(\d+);/g, (_, code) => String.fromCharCode(Number(code)));

  return decoded.replace(/\s+/g, " ").trim();
}

function chunkText(text: string, chunkSize = 2000, overlap = 260) {
  if (text.length <= chunkSize) return [text];

  const chunks: string[] = [];
  let cursor = 0;
  while (cursor < text.length) {
    const end = Math.min(cursor + chunkSize, text.length);
    const chunk = text.slice(cursor, end).trim();
    if (chunk) chunks.push(chunk);
    if (end >= text.length) break;
    cursor = Math.max(0, end - overlap);
  }

  return chunks;
}

function tokenize(text: string) {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, " ")
    .split(/\s+/)
    .filter((token) => token.length > 2);
}

function rankChunks(chunks: string[], query: string, limit = 5) {
  const terms = tokenize(query);
  if (!terms.length) return chunks.slice(0, limit);

  const scored: ChunkScore[] = chunks.map((chunk, index) => {
    const hay = chunk.toLowerCase();
    const score = terms.reduce((acc, term) => acc + (hay.match(new RegExp(`\\b${term}\\b`, "g"))?.length ?? 0), 0);
    return { index, chunk, score };
  });

  return scored
    .sort((a, b) => b.score - a.score || a.index - b.index)
    .slice(0, limit)
    .map((item) => item.chunk);
}

async function loadTickerDirectory() {
  const response = await fetchWithTimeout(SEC_TICKER_DIRECTORY_URL, {
    headers: secHeaders(),
  });

  if (!response.ok) {
    throw new Error(`SEC ticker directory request failed (${response.status}).`);
  }

  const payload = (await response.json()) as Record<string, TickerDirectoryItem>;
  return Object.values(payload);
}

async function fetchLatestTenK(ticker: string): Promise<FilingMatch> {
  const directory = await loadTickerDirectory();
  const match = directory.find((item) => item.ticker.toUpperCase() === ticker.toUpperCase());

  if (!match) {
    throw new Error(`Ticker ${ticker} not found in SEC directory.`);
  }

  const cikPadded = padCik(match.cik_str);
  const cikRaw = String(match.cik_str);

  const submissionsResponse = await fetchWithTimeout(`${SEC_SUBMISSIONS_URL}/CIK${cikPadded}.json`, {
    headers: {
      ...secHeaders(),
      Host: "data.sec.gov",
    },
  });

  if (!submissionsResponse.ok) {
    throw new Error(`SEC submissions request failed (${submissionsResponse.status}).`);
  }

  const submissions = (await submissionsResponse.json()) as SubmissionsResponse;
  const recent = submissions.filings?.recent;
  const forms = recent?.form ?? [];
  const accessionNumbers = recent?.accessionNumber ?? [];
  const primaryDocs = recent?.primaryDocument ?? [];
  const filingDates = recent?.filingDate ?? [];
  const reportDates = recent?.reportDate ?? [];

  let index = forms.findIndex((form) => form === "10-K");
  if (index === -1) {
    index = forms.findIndex((form) => form.startsWith("10-K"));
  }

  if (index === -1) {
    throw new Error(`No 10-K filing found for ${ticker}.`);
  }

  const accessionNumber = accessionNumbers[index];
  const primaryDocument = primaryDocs[index];
  const filingDate = filingDates[index];

  if (!accessionNumber || !primaryDocument || !filingDate) {
    throw new Error(`SEC filing metadata incomplete for ${ticker}.`);
  }

  const accessionNoDashes = accessionNumber.replace(/-/g, "");
  const filingUrl = `${SEC_ARCHIVES_URL}/${cikRaw}/${accessionNoDashes}/${primaryDocument}`;

  const filingResponse = await fetchWithTimeout(filingUrl, {
    headers: secHeaders(),
  });

  if (!filingResponse.ok) {
    throw new Error(`Unable to fetch 10-K filing document (${filingResponse.status}).`);
  }

  const filingRaw = await filingResponse.text();
  const filingText = cleanText(filingRaw);

  if (!filingText) {
    throw new Error("Fetched filing but extracted text is empty.");
  }

  return {
    ticker: match.ticker.toUpperCase(),
    companyName: match.title,
    cik: cikPadded,
    form: forms[index] ?? "10-K",
    filingDate,
    reportDate: reportDates[index],
    filingUrl,
    text: filingText,
  };
}

function buildPrompt(params: {
  mode: RagMode;
  ticker: string;
  question?: string | null;
  filing: FilingMatch;
  contextSummary: string;
  chunks: string[];
}) {
  const { mode, ticker, question, filing, contextSummary, chunks } = params;

  const filingContext = chunks
    .map((chunk, index) => `Snippet ${index + 1}: ${chunk}`)
    .join("\n\n");

  const modeInstruction =
    mode === "summary"
      ? "Deliver a concise CFO brief with: operating performance, balance sheet/liquidity, major risks, and concrete watch-items."
      : `Answer the question precisely and ground it in the filing plus dashboard context. Question: ${question ?? ""}`;

  return [
    "You are a financial intelligence assistant for a CFO dashboard.",
    "Use only the supplied evidence and avoid unsupported claims.",
    "If evidence is insufficient, state that clearly.",
    modeInstruction,
    `Target company ticker: ${ticker}`,
    `Filing metadata: ${filing.companyName} | ${filing.form} | filed ${filing.filingDate}`,
    "",
    "Dashboard context:",
    contextSummary,
    "",
    "10-K evidence excerpts:",
    filingContext,
  ].join("\n");
}

async function callOllama(prompt: string) {
  const model = process.env.OLLAMA_MODEL ?? DEFAULT_OLLAMA_MODEL;
  const baseUrl = process.env.OLLAMA_BASE_URL ?? DEFAULT_OLLAMA_BASE_URL;

  const response = await fetchWithTimeout(`${baseUrl}/api/generate`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model,
      prompt,
      stream: false,
      options: {
        temperature: 0.2,
        top_p: 0.9,
        num_predict: 700,
      },
    }),
  }, 90000);

  if (!response.ok) {
    throw new Error(`Ollama request failed (${response.status}). Ensure Ollama is running locally.`);
  }

  const payload = (await response.json()) as {
    model?: string;
    response?: string;
  };

  if (!payload.response) {
    throw new Error("Ollama returned an empty response.");
  }

  return {
    model: payload.model ?? model,
    text: payload.response.trim(),
  };
}

export async function POST(request: Request) {
  try {
    const body = (await request.json()) as RagRequestBody;
    const mode = body.mode;
    const ticker = normalizeTicker(body.ticker ?? "");

    if (!mode || (mode !== "summary" && mode !== "qa")) {
      return NextResponse.json({ error: "Invalid mode. Use summary or qa." }, { status: 400 });
    }

    if (!ticker) {
      return NextResponse.json({ error: "Ticker is required." }, { status: 400 });
    }

    if (mode === "qa" && !body.question?.trim()) {
      return NextResponse.json({ error: "Question is required for QA mode." }, { status: 400 });
    }

    const filing = await fetchLatestTenK(ticker);
    const chunks = chunkText(filing.text);

    const contextSummary = normalizeDashboardContext(body.dashboardContext);
    const retrievalQuery =
      mode === "summary"
        ? `${ticker} 10-K business outlook liquidity debt risks ${contextSummary}`
        : `${ticker} ${body.question ?? ""} ${contextSummary}`;

    const selectedChunks = rankChunks(chunks, retrievalQuery, 5);
    const prompt = buildPrompt({
      mode,
      ticker,
      question: body.question,
      filing,
      contextSummary,
      chunks: selectedChunks,
    });

    const completion = await callOllama(prompt);

    return NextResponse.json({
      answer: completion.text,
      model: completion.model,
      filing: {
        ticker: filing.ticker,
        companyName: filing.companyName,
        form: filing.form,
        filingDate: filing.filingDate,
        filingUrl: filing.filingUrl,
      },
      snippets: selectedChunks.slice(0, 3).map((chunk) => (chunk.length > 280 ? `${chunk.slice(0, 280)}…` : chunk)),
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unexpected RAG failure.";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
