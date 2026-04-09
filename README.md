# CFO Dashboard Next.js Frontend Prototype

This repository contains the startup’s CFO Operations Board frontend prototype built with Next.js, visx charting, GSAP interactions, and a WebGL backdrop.  
It includes mock dashboard data and an optional local RAG API flow (SEC Edgar + Ollama) for AI-assisted analysis.

## 1) Install And Run Locally

1. Install prerequisites:
   - Node.js `20.x` or newer
   - npm `10.x` or newer
   - Git
2. Clone the repository.
3. Open a terminal in the `nextjs-frontend-prototype` folder.
4. Install dependencies:

```bash
npm install
```

5. Start the dev server:

```bash
npm run dev
```

6. Open:
   - [http://127.0.0.1:3000](http://127.0.0.1:3000)

## 2) Configure Optional AI/RAG Features (SEC + Ollama)

If you want the KAI assistant + 10-K summary/Q&A endpoint to work locally:

1. Install Ollama on your machine.
2. Pull the model used by this project:

```bash
ollama pull mistral
```

3. Copy environment template:

```bash
cp .env.example .env.local
```

4. Edit `.env.local` and set:
   - `SEC_USER_AGENT` to a real identifier (name/email/company)
   - `OLLAMA_BASE_URL` only if your Ollama host is not default
   - `OLLAMA_MODEL` if you want a different model
5. Ensure Ollama is running, then restart Next.js (`npm run dev`).

## Common Commands

```bash
npm run dev
npm run lint
npm run build
npm run start
```

## Notes For Team Collaboration

- Do not commit local env files (`.env.local`).
- Commit `package-lock.json` with dependency updates.
- Develop on feature branches; merge to main via PR review.
