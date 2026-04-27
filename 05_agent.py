import os
from strands import Agent
from strands.models import BedrockModel
from strands_tools.tavily import tavily_search
from strands_tools import retrieve
from bedrock_agentcore import BedrockAgentCoreApp, RequestContext

from mcp_proxy_for_aws.client import aws_iam_streamablehttp_client
from strands.tools.mcp import MCPClient

from bedrock_agentcore.memory.integrations.strands.config import AgentCoreMemoryConfig
from bedrock_agentcore.memory.integrations.strands.session_manager import AgentCoreMemorySessionManager
from strands_tools.agent_core_memory import AgentCoreMemoryToolProvider


app = BedrockAgentCoreApp()

REGION = "us-east-1"

model_id = "global.anthropic.claude-opus-4-6-v1"
model = BedrockModel(
    model_id=model_id,
)

# configure MCP Client
mcp_url = "https://gateway-ehjdbglfzt.gateway.bedrock-agentcore.us-east-1.amazonaws.com/mcp"

mcp_client = MCPClient(
    lambda: aws_iam_streamablehttp_client(
        endpoint=mcp_url,
        aws_service="bedrock-agentcore",
    ),
)

# Configure TAVILY
os.environ["TAVILY_API_KEY"] = "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"

# AgentCore Memory — replace with your memory ID from 09_deploy_memory.ipynb
MEMORY_ID = os.environ.get("MEMORY_ID", "agentic_ai_demo-AwrsGjE0oe")

# Bedrock Knowledge Base — replace with your KB ID from 09_deploy_kb.ipynb
os.environ["KNOWLEDGE_BASE_ID"] = os.environ.get("KNOWLEDGE_BASE_ID", "MCJNMES8UI")
os.environ.setdefault("AWS_REGION", REGION)

BASE_SYSTEM_PROMPT = (
    "You are a helpful betting and customer support assistant for a sports betting platform. "
    "You have access to a Memory tool that lets you store and retrieve user preferences. "
    "Always check memory first before asking the user for information they may have already shared. "
    "Use everything you know about the user from previous conversations to provide personalized responses.\n\n"
    "You also have access to a 'retrieve' tool connected to a Knowledge Base containing EU regulatory "
    "and compliance documents for the betting and gaming industry (GDPR, AML, PSD2, DSA, AVMSD, "
    "EU Commission Recommendation on online gambling, and iGaming regulations). "
    "When a customer asks about policies, regulations, responsible gambling options, data rights, "
    "AML obligations, or any compliance-related topic, use the retrieve tool to search the Knowledge Base "
    "and ground your answer in the actual regulatory documents. Always cite which regulation or document "
    "your answer is based on."
)


@app.entrypoint
def strands_agent_bedrock(payload, context: RequestContext):
    """
    Invoke the agent with a payload.
    Accepts optional accountId to scope all customer-specific API calls.
    Uses AgentCore Memory for conversation persistence and long-term recall.
    Uses Bedrock Knowledge Base for EU regulatory/compliance document retrieval.
    """
    user_input = payload.get("prompt")
    account_id = payload.get("accountId", "default")
    session_id = context.session_id or "default-session"

    print("User input:", user_input)
    print("Account ID:", account_id)
    print("Session ID:", session_id)

    # Build system prompt with accountId
    system_prompt = BASE_SYSTEM_PROMPT
    if account_id:
        system_prompt += (
            f"\n\nThe customer you are assisting has accountId: {account_id}. "
            f"Always use this accountId when calling any customer-specific API "
            f"(getBalance, getCustomerBets, getCustomerTransactions, placeBet, etc.)."
        )

    # Namespace for long-term preference retrieval (matches PreferenceLearner template)
    preference_namespace = f"/preferences/user/{account_id}/"

    # Configure short-term memory — scoped per customer (actor) and session
    memory_config = AgentCoreMemoryConfig(
        memory_id=MEMORY_ID,
        session_id=session_id,
        actor_id=account_id,
    )

    session_manager = AgentCoreMemorySessionManager(
        agentcore_memory_config=memory_config,
        region_name=REGION,
    )

    # Configure long-term memory tool — enables the agent to store/retrieve preferences
    memory_tool_provider = AgentCoreMemoryToolProvider(
        memory_id=MEMORY_ID,
        actor_id=account_id,
        session_id=session_id,
        namespace=preference_namespace,
        region=REGION,
    )

    # Create agent with memory (short + long term), MCP tools, web search, and KB retrieval
    agent = Agent(
        model=model,
        tools=[tavily_search, mcp_client, retrieve] + memory_tool_provider.tools,
        system_prompt=system_prompt,
        session_manager=session_manager,
    )

    response = agent(user_input)
    return response.message['content'][0]['text']


if __name__ == "__main__":
    app.run()
