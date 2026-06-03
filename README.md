# Multi-Step Research Assistant

A LangChain-powered research assistant that uses OpenAI and Wikipedia to research topics and provide comprehensive summaries.

## Features

- 🤖 **Multi-step research** - Breaks down complex research tasks into steps
- 🔍 **Wikipedia integration** - Searches and retrieves information from Wikipedia
- 🧠 **LLM-powered analysis** - Uses OpenAI to synthesize and summarize findings
- 💾 **Memory** - Maintains context across research steps
- 🔗 **Agent-based** - Uses LangChain agents to autonomously decide next steps
- 📈 **Dynatrace AI observability** - Exports manual traces and LangChain-aware AI telemetry to Dynatrace

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

### Option 1: GitHub Codespaces (Recommended)

1. **Open in Codespaces**:
   - Click the green `Code` button on your repository
   - Select `Codespaces` tab
   - Click `Create codespace on main`
   - Wait for the environment to load (2-3 minutes)

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment**:
   ```bash
   cp .env.example .env
   # Edit .env and add your OpenAI API key
   nano .env
   ```

4. **Run the assistant**:
   ```bash
   python research_assistant.py
   ```

### Option 2: Local Setup

1. **Clone the repository**:
   ```bash
   git clone https://github.com/virtualrussel/research-assistant.git
   cd research-assistant
   ```

2. **Create a virtual environment**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Set up environment variables**:
   ```bash
   cp .env.example .env
   # Edit .env with your OpenAI API key
   ```

5. **Run the assistant**:
   ```bash
   python research_assistant.py
   ```

## Dynatrace AI Observability Setup

To enable full tracing visibility for manual application spans and LangChain / LLM execution, set the following variables in your `.env` file:

```dotenv
DT_API_URL=https://<your-env>.live.dynatrace.com/api/v2/otlp
DT_API_TOKEN=your_dynatrace_api_token_here
```

Notes:

- `DT_API_URL` should be the Dynatrace OTLP **base endpoint**.
- Standard OpenTelemetry spans are exported to `DT_API_URL + /v1/traces`.
- Traceloop / OpenLLMetry uses the base OTLP endpoint directly.
- If Dynatrace variables are not set, the assistant continues running without tracing.

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

With Dynatrace tracing enabled, each query also emits:
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
├── requirements.txt           # Python dependencies
├── .env.example               # Environment variables template
├── .gitignore                 # Git ignore rules
├── .devcontainer/
│   └── devcontainer.json      # GitHub Codespaces config
├── research_assistant.py      # Main agent code
└── tracing.py                 # Dynatrace / OpenTelemetry setup
```

## Learning Resources

- [LangChain Documentation](https://python.langchain.com/)
- [LangChain Agents](https://python.langchain.com/docs/modules/agents/)
- [OpenAI API Documentation](https://platform.openai.com/docs)
- [Wikipedia API](https://www.mediawiki.org/wiki/API)
- [Dynatrace AI Observability](https://docs.dynatrace.com/docs/observe/dynatrace-for-ai-observability/get-started/openllmetry)

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
