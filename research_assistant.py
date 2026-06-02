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

import os
import logging
from typing import Any
from dotenv import load_dotenv

# Import LangChain components
from langchain_openai import ChatOpenAI
from langchain.tools import Tool
from langchain.agents import initialize_agent, AgentType
from langchain.memory import ConversationBufferMemory
import wikipedia

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

def wikipedia_search(query: str) -> str:
    """
    Search Wikipedia for information about a topic.
    
    Args:
        query: The search term to look up on Wikipedia
        
    Returns:
        A summary of the Wikipedia article or an error message
    """
    try:
        logger.info(f"Searching Wikipedia for: {query}")
        # Set the number of sentences in the summary
        result = wikipedia.summary(query, sentences=3)
        return result
    except wikipedia.exceptions.DisambiguationError as e:
        # Handle cases where Wikipedia returns multiple possible matches
        options = e.options[:3]  # Get first 3 options
        return f"Multiple results found. Try: {', '.join(options)}"
    except wikipedia.exceptions.PageError:
        # Handle case where page is not found
        return f"No Wikipedia page found for '{query}'"
    except Exception as e:
        # Handle any other errors
        logger.error(f"Error searching Wikipedia: {str(e)}")
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
        temperature=0.7,  # Controls randomness (0 = deterministic, 1 = random)
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
        memory_key="chat_history",  # Key to access the memory in prompts
        return_messages=True  # Return message objects instead of strings
    )
    
    return memory


# ============================================================================
# STEP 4: Create the Agent
# ============================================================================
# The agent combines the LLM, tools, and memory to make autonomous decisions.

def create_research_agent(llm, memory, tools):
    """
    Initialize a research agent with tools and memory.
    
    Args:
        llm: The language model to use
        memory: Conversation memory object
        tools: List of tools the agent can use
        
    Returns:
        Agent: Configured agent instance
    """
    logger.info("Creating research agent")
    
    # AGENT TYPES EXPLAINED:
    # - ZERO_SHOT_REACT_DESCRIPTION: Agent decides on its own (no memory)
    # - CHAT_CONVERSATIONAL_REACT_DESCRIPTION: Includes conversation history
    
    agent = initialize_agent(
        tools=tools,
        llm=llm,
        agent=AgentType.CHAT_CONVERSATIONAL_REACT_DESCRIPTION,
        memory=memory,
        verbose=True,  # Set to True to see the agent's reasoning
        handle_parsing_errors=True  # Gracefully handle errors
    )
    
    return agent


# ============================================================================
# STEP 5: Main Research Loop
# ============================================================================

def run_research_assistant():
    """
    Main function to run the research assistant in a loop.
    """
    print("\n" + "="*70)
    print("🔍 Multi-Step Research Assistant")
    print("Powered by LangChain + OpenAI + Wikipedia")
    print("="*70)
    print("\nThis assistant will research topics using Wikipedia")
    print("and synthesize information using AI.")
    print("\nType 'quit' or 'exit' to stop.\n")
    
    try:
        # Initialize components
        logger.info("Initializing research assistant components")
        llm = initialize_llm()
        memory = initialize_memory()
        tools = [wikipedia_tool]
        
        # Create the agent
        agent = create_research_agent(llm, memory, tools)
        
        logger.info("Research assistant initialized successfully")
        
        # Research loop
        while True:
            # Get user input
            user_query = input("\n📝 Enter your research topic or question: ").strip()
            
            # Check for exit commands
            if user_query.lower() in ["quit", "exit", "q"]:
                print("\n👋 Thank you for using the Research Assistant!")
                break
            
            # Validate input
            if not user_query:
                print("⚠️  Please enter a valid research topic.")
                continue
            
            print("\n🤔 Researching...\n")
            
            try:
                # Run the agent with the user's query
                # The agent will:
                # 1. Decide if it needs to search Wikipedia
                # 2. Potentially search Wikipedia multiple times
                # 3. Synthesize information into an answer
                result = agent.run(user_query)
                
                print("\n" + "-"*70)
                print("📊 Research Results:")
                print("-"*70)
                print(result)
                print("-"*70)
                
            except Exception as e:
                logger.error(f"Error during research: {str(e)}")
                print(f"\n❌ Error during research: {str(e)}")
                print("Please try again with a different topic.")
    
    except ValueError as e:
        print(f"\n❌ Configuration Error: {str(e)}")
        print("\nPlease ensure:")
        print("1. You have created a .env file (copy from .env.example)")
        print("2. You've added your OpenAI API key to .env")
        print("3. You've run: pip install -r requirements.txt")
    
    except KeyboardInterrupt:
        print("\n\n👋 Research assistant stopped by user.")
    
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        print(f"\n❌ Unexpected error: {str(e)}")


# ============================================================================
# Entry Point
# ============================================================================

if __name__ == "__main__":
    run_research_assistant()
