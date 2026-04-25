import os
from strands import Agent
from strands.models import BedrockModel
from strands_tools.tavily import tavily_search
from bedrock_agentcore import BedrockAgentCoreApp, RequestContext

from mcp_proxy_for_aws.client import aws_iam_streamablehttp_client
from strands.tools.mcp import MCPClient

from bedrock_agentcore.memory.integrations.strands.config import AgentCoreMemoryConfig
from bedrock_agentcore.memory.integrations.strands.session_manager import AgentCoreMemorySessionManager


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

BASE_SYSTEM_PROMPT = (
    "You are a helpful betting and customer support assistant for a sports betting platform. "
    "Use everything you know about the user from previous conversations to provide personalized responses."
)


@app.entrypoint
def strands_agent_bedrock(payload, context: RequestContext):
    """
    Invoke the agent with a payload.
    Accepts optional accountId to scope all customer-specific API calls.
    Uses AgentCore Memory for conversation persistence and long-term recall.
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

    # Configure memory — scoped per customer (actor) and session
    memory_config = AgentCoreMemoryConfig(
        memory_id=MEMORY_ID,
        session_id=session_id,
        actor_id=account_id,
    )

    session_manager = AgentCoreMemorySessionManager(
        agentcore_memory_config=memory_config,
        region_name=REGION,
    )

    # Create agent with memory session manager
    # The session manager handles loading previous turns and saving new ones
    agent = Agent(
        model=model,
        tools=[tavily_search, mcp_client],
        system_prompt=system_prompt,
        session_manager=session_manager,
    )

    response = agent(user_input)
    return response.message['content'][0]['text']


if __name__ == "__main__":
    app.run()
