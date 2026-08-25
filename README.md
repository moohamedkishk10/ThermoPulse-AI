# ThermoPulse AI

**Autonomous Heat Intelligence & Urban Resilience Copilot**

Built for the FortyGuard Global AI Hackathon '26 — Track 06 (Agentic AI)

**Live Demo:** [thermopulse-ai.streamlit.app](https://thermopulse-ai.streamlit.app/)

---

## Overview

ThermoPulse AI turns FortyGuard's hyperlocal temperature data into actionable urban heat intelligence. It bridges raw thermal feeds (2-meter elevation, hour-by-hour resolution) with land-cover context — impervious surface coverage and tree canopy — to compute a **Heat Risk Index** for any U.S. location, then puts that intelligence behind a conversational AI agent and an interactive dashboard.

Instead of just showing a temperature number, ThermoPulse AI answers the question that actually matters for city planners and logistics teams: **why is this location dangerous, and what should be done about it?**

## Key Features

- **Heat Risk Index (0–100):** Combines temperature severity, impervious surface coverage, and vegetation deficit into a single explainable score, with a plain-language breakdown of what's driving the risk at each point.
- **Conversational AI Copilot:** A LangGraph agent that autonomously decides which FortyGuard endpoints to call — assessing area-wide risk, comparing route options for thermal-aware navigation, or generating a formal PDF triage report — based on natural-language requests.
- **Interactive Dashboard:** Search any location by name, run a live risk assessment, and see results on a color-coded map with detailed per-point breakdowns.
- **Official PDF Reports:** One-click generation of FortyGuard's official Heat Intelligence report for the highest-risk location found.
- **Production-grade API wrapper:** Full async coverage of all 7 FortyGuard endpoints with retry/backoff, bounded polling, and client-side validation (area limits, credit-conscious defaults).

## Architecture

```
┌─────────────────────────┐
│   FortyGuard API (7     │
│      endpoints)         │
└───────────┬──────────────┘
            │
┌───────────▼──────────────┐
│      fortyguard/         │  Async wrapper: submit → poll → result,
│    (API Wrapper)         │  retry/backoff, area & filter validation
└───────────┬──────────────┘
            │
┌───────────▼──────────────┐
│    spatial_engine/       │  Heat Risk Index: temperature +
│     (Risk Engine)        │  impervious surface + vegetation deficit
└───────────┬──────────────┘
            │
     ┌──────┴───────┐
     │              │
┌────▼─────┐   ┌────▼──────────┐
│  agent/  │   │    app.py     │
│(LangGraph│   │  (Streamlit   │
│  Agent)  │   │  Dashboard)   │
└──────────┘   └───────────────┘
```

## Tech Stack

| Layer | Technology |
|---|---|
| API Integration | Python, `aiohttp`, async/await |
| Spatial Analysis | `pandas`, `geopandas`, `shapely` |
| Agentic Core | `LangGraph`, `LangChain`, OpenRouter (LLM) |
| Dashboard | `Streamlit`, `pydeck` |
| Geocoding | OpenStreetMap Nominatim (free, no API key) |

## Getting Started

### Prerequisites

- Python 3.10+
- A FortyGuard API key ([dashboard.fortyguard.com](https://dashboard.fortyguard.com))
- An OpenRouter API key ([openrouter.ai/keys](https://openrouter.ai/keys)) for the agent's LLM

### Installation

```bash
git clone https://github.com/moohamedkishk10/ThermoPulse-AI.git
cd ThermoPulse-AI
pip install -r requirements.txt
```

### Configuration

Copy the example environment file and fill in your keys:

```bash
cp .env.example .env
```

Edit `.env`:

```env
FORTYGUARD_API_KEY=your_fortyguard_key_here
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=your_openrouter_key_here
```

### Running the dashboard

```bash
streamlit run app.py
```

Opens at `http://localhost:8501`. Search for a U.S. location, run a Heat Risk Assessment, or switch to the AI Copilot tab to chat with the agent directly.

### Running the API wrapper standalone

```bash
python example_usage.py
```

Demonstrates all 7 FortyGuard endpoints end-to-end.

## Project Structure

```
ThermoPulse-AI/
├── fortyguard/           # Async API wrapper (Phase 1)
│   ├── client.py         # All 7 endpoints, retry/backoff, polling
│   ├── config.py         # Environment-based configuration
│   └── exceptions.py     # Typed exception hierarchy
├── spatial_engine/       # Heat Risk Index engine (Phase 2)
│   ├── scoring.py        # Pure scoring logic (no API dependency)
│   └── engine.py         # Orchestrates heatmap + segmentation
├── agent/                # LangGraph agentic core (Phase 3)
│   ├── llm.py            # Configurable LLM provider
│   ├── tools.py          # 3 agent tools (assess/compare/report)
│   └── graph.py          # ReAct agent assembly
├── app.py                # Streamlit dashboard (Phase 4)
├── dashboard_theme.py    # Visual identity / CSS
└── requirements.txt
```

## Coverage Notes

Per FortyGuard's Hackathon Participant Handbook, all endpoints operate over **U.S. locations only**, with data from 2021-01-01 to ~12 hours into the future, and heatmap areas capped at ~130 km². The wrapper validates area limits client-side before submitting a request.

## Known Limitations

- The Heat Risk Index weights (temperature 50% / impervious surface 25% / vegetation deficit 25%) are a reasonable default, not an officially prescribed FortyGuard formula — configurable via `spatial_engine.RiskWeights`.
- `filter_type=5` (Single Month) is supported per the Participant Handbook but its exact optional fields are unconfirmed beyond `start_date`.
- The agent's LLM is currently routed through OpenRouter's free-tier auto-router; for guaranteed-consistent output during live demos, pin a specific model via `OPENROUTER_MODEL` in `.env`.

## Acknowledgments

Built on the [FortyGuard Temperature API](https://docs-api.fortyguard.com) for the FortyGuard Global AI Hackathon '26.

---

**Team:** Mohamed Kishk (solo) — Track 06: Agentic AI