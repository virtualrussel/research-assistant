# Multi-Step Research Assistant

A LangChain-powered research assistant that uses OpenAI and Wikipedia to research topics and provide comprehensive summaries.

## Features

- 🤖 **Multi-step research** - Breaks down complex research tasks into steps
- 🔍 **Wikipedia integration** - Searches and retrieves information from Wikipedia
- 🧠 **LLM-powered analysis** - Uses OpenAI to synthesize and summarize findings
- 💾 **Memory** - Maintains context across research steps
- 🔗 **Agent-based** - Uses LangChain agents to autonomously decide next steps
- 📈 **OpenTelemetry AI observability** - Manual spans and LangChain-aware AI telemetry via OpenLLMetry/Traceloop

## How It Works

1. You provide a research topic or question
2. The agent decides what steps to take (search Wikipedia, summarize, analyze, etc.)
3. It uses Wikipedia as a tool to gather information
4. OpenAI's LLM synthesizes the information into a comprehensive answer
5. The process repeats until the research goal is met

## Prerequisites

- Python 3.9+
- OpenAI API key
- Optional: Dynatrace OTLP endpoint and API token for tracing
- GitHub Codespaces (or local environment with Python installed)

## Setup Instructions

### Option 1: Docker (Recommended)

1. **Clone the repository**:
   ```bash
   git clone https://github.com/virtualrussel/research-assistant.git
   cd research-assistant
   ```

2. **Configure environment**:
   ```bash
   cp .env.example .env
   # Edit .env — OPENAI_API_KEY is required; DT_* vars enable tracing
   nano .env
   ```

3. **Build and start**:
   ```bash
   docker-compose up -d research-assistant
   ```

4. **Open the assistant**:
   Navigate to `http://localhost:8000` (or your EC2 public IP on port 8000).

### Option 2: Local Python

1. **Clone and install**:
   ```bash
   git clone https://github.com/virtualrussel/research-assistant.git
   cd research-assistant
   python -m venv venv
   source venv/bin/activate  # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Configure environment**:
   ```bash
   cp .env.example .env
   # Edit .env — OPENAI_API_KEY is required
   ```

3. **Run**:
   ```bash
   uvicorn app:app --reload
   ```

4. **Open the assistant**:
   Navigate to `http://localhost:8000`.

## OpenTelemetry / AI Observability Setup

Traces and LLM metrics are exported via [OpenLLMetry/Traceloop](https://github.com/traceloop/openllmetry) to any OTLP-compatible backend. To enable, set the following in your `.env` file:

```dotenv
DT_API_URL=https://<your-env>.live.dynatrace.com/api/v2/otlp
DT_API_TOKEN=your_dynatrace_api_token_here
```

Notes:

- `DT_API_URL` should be the OTLP **base endpoint** with no trailing slash.
- Standard OpenTelemetry spans are exported to `DT_API_URL + /v1/traces`.
- Traceloop / OpenLLMetry uses the base endpoint directly.
- If these variables are not set, the assistant runs without tracing — no other functionality is affected.

## Getting an OpenAI API Key

1. Visit https://platform.openai.com/account/api-keys
2. Sign up or log in to your OpenAI account
3. Click "Create new secret key"
4. Copy the key and paste it in your `.env` file as `OPENAI_API_KEY`

## Usage

Once running, the assistant will prompt you for a research topic:

```
Enter your research topic: What is machine learning?
```

The agent will then:
1. Search Wikipedia for relevant information
2. Analyze and summarize the findings
3. Provide a comprehensive answer with sources

With tracing enabled, each query also emits:
- a top-level research workflow span
- LangChain / LLM spans captured through Traceloop
- tool spans for Wikipedia searches
- manual custom spans with query/result metadata

## LangChain Components Used

- **Agents** - Autonomous decision-making about what steps to take
- **Tools** - Wikipedia search tool for gathering information
- **Memory** - Conversation history context
- **LLMs** - OpenAI GPT models for reasoning and synthesis
- **Chains** - Orchestrating multiple LLM calls

## Project Structure

```
research-assistant/
├── README.md                  # This file
├── DEPLOYMENT.md              # EC2 deployment guide
├── requirements.txt           # Python dependencies
├── .env.example               # Environment variables template
├── .gitignore                 # Git ignore rules
├── Dockerfile                 # Container image definition
├── docker-compose.yml         # Compose service for the assistant
├── nginx.conf                 # Optional nginx config (port 80 / HTTPS)
├── public/
│   ├── index.html             # Web UI
│   ├── index.css              # Styles
│   └── index.js               # Chat client
├── app.py                     # FastAPI service + session management
├── research_assistant.py      # LangChain agent + Wikipedia tool
├── tracing.py                 # OpenTelemetry / Traceloop setup
└── .devcontainer/
    └── devcontainer.json      # GitHub Codespaces config
```

## Learning Resources

- [LangChain Documentation](https://python.langchain.com/)
- [LangChain Agents](https://python.langchain.com/docs/modules/agents/)
- [OpenAI API Documentation](https://platform.openai.com/docs)
- [Wikipedia API](https://www.mediawiki.org/wiki/API)
- [OpenLLMetry / Traceloop](https://github.com/traceloop/openllmetry)

## Troubleshooting

### "ModuleNotFoundError: No module named 'langchain'"
- Make sure you've run `pip install -r requirements.txt`

### "ModuleNotFoundError: No module named 'traceloop'"
- Reinstall dependencies with `pip install -r requirements.txt`
- Confirm your virtual environment is activated

### "OpenAI API key not found"
- Check your `.env` file has `OPENAI_API_KEY=your_key_here`
- Make sure you've restarted the script after updating `.env`

### "Tracing not configured"
- Check that `DT_API_URL` and `DT_API_TOKEN` are set in `.env`
- Confirm `DT_API_URL` is the base Dynatrace OTLP endpoint, not `/v1/traces`
- Verify the Dynatrace API token has trace ingest permissions

### "No Wikipedia results found"
- Try a more general search term
- Wikipedia may have the information under a different name

## Next Steps

Once you have the basic assistant working, try extending it with:
- Additional tools (web search, arXiv for research papers)
- Different LLMs (Hugging Face, Claude)
- Persistent storage for research results
- Better error handling and retries
- Custom prompts for specific research domains

## Questions?

Refer to the inline comments in `research_assistant.py` for detailed explanations of how each LangChain component works.
