"""
Multi-Step Research Assistant using LangChain

This script creates an AI-powered research assistant that:
1. Takes a research question from the user
2. Uses a LangChain agent to decide what steps to take
3. Searches Wikipedia for relevant information
4. Uses OpenAI to synthesize and analyze findings
5. Provides a comprehensive research report

Key LangChain Concepts Demonstrated:
- Agents: Autonomous decision-making
- Tools: Wikipedia search capability
- Memory: Conversation context management
- LLMs: OpenAI integration
- Chains: Multi-step processing
"""

import logging
import os

import wikipedia
from dotenv import load_dotenv
from langchain.agents import AgentType, initialize_agent
from langchain.memory import ConversationBufferMemory
from langchain.tools import Tool
from langchain_openai import ChatOpenAI
from opentelemetry import trace
from opentelemetry.trace.status import Status, StatusCode

from tracing import setup_tracing

try:
    from traceloop.sdk.decorators import task, tool, workflow
except ImportError:
    def workflow(name=None):
        def decorator(func):
            return func
        return decorator

    def task(name=None):
        def decorator(func):
            return func
        return decorator

    def tool(name=None):
        def decorator(func):
            return func
        return decorator


# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# ============================================================================
# STEP 1: Define Custom Tools
# ============================================================================
# Tools are functions that the agent can call to gather information.
# We're creating a Wikipedia search tool.

@tool(name="wikipedia_search")
def wikipedia_search(query: str) -> str:
    """
    Search Wikipedia for information about a topic.

    Args:
        query: The search term to look up on Wikipedia

    Returns:
        A summary of the Wikipedia article or an error message
    """
    tracer = trace.get_tracer(__name__)
    with tracer.start_as_current_span("wikipedia.search") as span:
        span.set_attribute("wikipedia.query", query)
        try:
            logger.info(f"Searching Wikipedia for: {query}")
            result = wikipedia.summary(query, sentences=3)
            span.set_attribute("wikipedia.result_length", len(result))
            return result
        except wikipedia.exceptions.DisambiguationError as e:
            options = e.options[:3]
            msg = f"Multiple results found. Try: {', '.join(options)}"
            span.set_attribute("wikipedia.disambiguation", True)
            span.set_status(Status(StatusCode.ERROR, msg))
            return msg
        except wikipedia.exceptions.PageError:
            msg = f"No Wikipedia page found for '{query}'"
            span.set_status(Status(StatusCode.ERROR, msg))
            return msg
        except Exception as e:
            logger.error(f"Error searching Wikipedia: {str(e)}")
            span.record_exception(e)
            span.set_status(Status(StatusCode.ERROR, str(e)))
            return f"Error searching Wikipedia: {str(e)}"


# Create a Tool object that LangChain can use
# Tools require: name, func (the function), and description
wikipedia_tool = Tool(
    name="Wikipedia",
    func=wikipedia_search,
    description=(
        "Useful for searching for information about topics, people, "
        "places, and events. Use this tool when you need to gather "
        "factual information."
    )
)


# ============================================================================
# STEP 2: Initialize the Language Model
# ============================================================================
# This is the brain of our assistant - OpenAI's GPT model.

def initialize_llm():
    """
    Create and configure the OpenAI language model.

    Returns:
        ChatOpenAI: Configured LLM instance
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError(
            "OPENAI_API_KEY not found in environment variables. "
            "Please set it in your .env file."
        )

    model_name = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")

    logger.info(f"Initializing LLM with model: {model_name}")

    llm = ChatOpenAI(
        model_name=model_name,
        temperature=0.7,
        api_key=api_key
    )

    return llm


# ============================================================================
# STEP 3: Initialize Memory
# ============================================================================
# Memory allows the agent to remember previous parts of the conversation.

def initialize_memory():
    """
    Create conversation memory to maintain context across turns.

    Returns:
        ConversationBufferMemory: Memory object for storing conversation history
    """
    logger.info("Initializing conversation memory")

    memory = ConversationBufferMemory(
        memory_key="chat_history",
        return_messages=True
    )

    return memory


# ============================================================================
# STEP 4: Create the Agent
# ============================================================================
# The agent combines the LLM, tools, and memory to make autonomous decisions.

def create_research_agent(llm, memory, tools, verbose=True):
    """
    Initialize a research agent with tools and memory.

    Args:
        llm: The language model to use
        memory: Conversation memory object
        tools: List of tools the agent can use
        verbose: Whether to print step-by-step reasoning

    Returns:
        Agent: Configured agent instance
    """
    logger.info("Creating research agent")

    agent = initialize_agent(
        tools=tools,
        llm=llm,
        agent=AgentType.CHAT_CONVERSATIONAL_REACT_DESCRIPTION,
        memory=memory,
        verbose=verbose,
        handle_parsing_errors=True
    )

    return agent


def create_agent_for_session():
    """
    Initialize and return a fully configured LangChain agent and memory.
    For HTTP service, verbose=False (logs via structured logging instead).

    Returns:
        tuple: (Agent, ConversationBufferMemory)
    """
    logger.info("Initializing agent and memory")
    llm = initialize_llm()
    memory = initialize_memory()
    tools = [wikipedia_tool]
    agent = create_research_agent(llm, memory, tools, verbose=False)
    return agent, memory


@task(name="run_agent_query")
def run_agent_query(agent, user_query: str) -> str:
    """
    Run the LangChain agent for a single user query.

    Args:
        agent: LangChain agent instance
        user_query: User's research query

    Returns:
        str: Agent's response
    """
    return agent.run(user_query)


@workflow(name="research_query_workflow")
def handle_research_query(agent, user_query: str) -> str:
    """
    Trace and execute a single research query workflow.

    Args:
        agent: LangChain agent instance
        user_query: User's research query

    Returns:
        str: Agent's response
    """
    tracer = trace.get_tracer(__name__)
    with tracer.start_as_current_span("research_assistant.query") as span:
        span.set_attribute("research.query", user_query)
        span.set_attribute(
            "research.model",
            os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")
        )

        try:
            result = run_agent_query(agent, user_query)
            span.set_attribute("research.result_length", len(result))
            return result
        except Exception as e:
            logger.error(f"Error during research: {str(e)}")
            span.record_exception(e)
            span.set_status(Status(StatusCode.ERROR, str(e)))
            raise


# ============================================================================
# STEP 5: Main Research Loop
# ============================================================================

def run_research_assistant():
    """
    Main function to run the research assistant in a loop.
    """
    print("\n" + "=" * 70)
    print("\U0001f50d Multi-Step Research Assistant")
    print("Powered by LangChain + OpenAI + Wikipedia")
    print("=" * 70)
    print("\nThis assistant will research topics using Wikipedia")
    print("and synthesize information using AI.")
    print("\nType 'quit' or 'exit' to stop.\n")

    try:
        setup_tracing()
        logger.info("OpenTelemetry tracing initialized")
    except ValueError as e:
        logger.warning(
            f"Tracing not configured: {e}. Continuing without Dynatrace tracing."
        )

    try:
        logger.info("Initializing research assistant components")
        llm = initialize_llm()
        memory = initialize_memory()
        tools = [wikipedia_tool]
        agent = create_research_agent(llm, memory, tools)

        logger.info("Research assistant initialized successfully")

        while True:
            user_query = input("\n\U0001f4dd Enter your research topic or question: ").strip()

            if user_query.lower() in ["quit", "exit", "q"]:
                print("\n\U0001f44b Thank you for using the Research Assistant!")
                break

            if not user_query:
                print("\u26a0\ufe0f  Please enter a valid research topic.")
                continue

            print("\n\U0001f914 Researching...\n")

            try:
                result = handle_research_query(agent, user_query)

                print("\n" + "-" * 70)
                print("\U0001f4ca Research Results:")
                print("-" * 70)
                print(result)
                print("-" * 70)

            except Exception as e:
                print(f"\n\u274c Error during research: {str(e)}")
                print("Please try again with a different topic.")

    except ValueError as e:
        print(f"\n\u274c Configuration Error: {str(e)}")
        print("\nPlease ensure:")
        print("1. You have created a .env file (copy from .env.example)")
        print("2. You've added your OpenAI API key to .env")
        print("3. You've run: pip install -r requirements.txt")

    except KeyboardInterrupt:
        print("\n\n\U0001f44b Research assistant stopped by user.")

    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        print(f"\n\u274c Unexpected error: {str(e)}")


# ============================================================================
# Entry Point
# ============================================================================

if __name__ == "__main__":
    run_mode = os.getenv("RUN_MODE", "http").lower()
    if run_mode == "cli":
        run_research_assistant()
    elif run_mode == "http":
        logger.info("HTTP mode selected; FastAPI should be started via uvicorn or app.py")
        print("This module is imported by app.py for HTTP mode.")
        print("To run CLI mode, use: RUN_MODE=cli python research_assistant.py")
    else:
        raise ValueError(f"Unknown RUN_MODE: {run_mode}. Use 'cli' or 'http'.")
