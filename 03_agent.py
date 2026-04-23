import os
from strands import Agent
from strands.models import BedrockModel
from strands_tools.tavily import tavily_search
from bedrock_agentcore.runtime import BedrockAgentCoreApp

from mcp_proxy_for_aws.client import aws_iam_streamablehttp_client
from strands.tools.mcp import MCPClient


app = BedrockAgentCoreApp()


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

BASE_SYSTEM_PROMPT = (
    "You are a helpful betting and customer support assistant for a sports betting platform."
)


@app.entrypoint
def strands_agent_bedrock(payload):
    """
    Invoke the agent with a payload.
    Accepts optional accountId to scope all customer-specific API calls.
    """
    user_input = payload.get("prompt")
    account_id = payload.get("accountId")
    print("User input:", user_input)
    print("Account ID:", account_id)

    system_prompt = BASE_SYSTEM_PROMPT
    if account_id:
        system_prompt += (
            f"\n\nThe customer you are assisting has accountId: {account_id}. "
            f"Always use this accountId when calling any customer-specific API "
            f"(getBalance, getCustomerBets, getCustomerTransactions, placeBet, etc.)."
        )

    agent = Agent(
        model=model,
        tools=[tavily_search, mcp_client],
        system_prompt=system_prompt,
    )

    response = agent(user_input)
    return response.message['content'][0]['text']


if __name__ == "__main__":
    app.run()