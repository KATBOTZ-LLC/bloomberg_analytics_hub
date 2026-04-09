# AGENT Setup Guide (Teammate Onboarding)

This file is for engineers/agents joining development on this repo.  
It gives a clean local setup path so everyone runs the same environment.

## 1) Local Machine Setup

1. Install:
   - Node.js `20.x+`
   - npm `10.x+`
   - Git
2. Clone the repository and open terminal in `nextjs-frontend-prototype`.
3. Install dependencies:

```bash
npm install
```

4. Run the app:

```bash
npm run dev
```

5. Open [http://127.0.0.1:3000](http://127.0.0.1:3000).

## 2) Optional: Enable KAI RAG API Locally

The `/api/rag` route uses SEC Edgar + local Ollama.

1. Install Ollama.
2. Pull model:

```bash
ollama pull mistral
```

3. Create env file:

```bash
cp .env.example .env.local
```

4. Set values in `.env.local`:
   - `SEC_USER_AGENT=Your Name your-email@company.com`
   - `OLLAMA_BASE_URL=http://127.0.0.1:11434` (default)
   - `OLLAMA_MODEL=mistral` (default)
5. Restart `npm run dev`.

## Validation Checklist

Run all before pushing:

```bash
npm run lint
npm run build
```

Both should pass with no errors.

