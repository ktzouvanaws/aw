import os
from strands import Agent
from strands.models import BedrockModel
from strands_tools.tavily import tavily_search
from bedrock_agentcore.runtime import BedrockAgentCoreApp

from mcp_proxy_for_aws.client import aws_iam_streamablehttp_client
from strands.tools.mcp import MCPClient


app = BedrockAgentCoreApp()


model_id = "global.anthropic.claude-haiku-4-5-20251001-v1:0"
model = BedrockModel(
    model_id=model_id,
)

# configure MCP Client
MCP_SERVER_ARN = "arn:aws:bedrock-agentcore:us-east-1:869795389844:runtime/mpc_server-IbPAU23Iwf"
REGION = "us-east-1"

encoded_arn = MCP_SERVER_ARN.replace(":", "%3A").replace("/", "%2F")
mcp_url = f"https://bedrock-agentcore.{REGION}.amazonaws.com/runtimes/{encoded_arn}/invocations?qualifier=DEFAULT"

mcp_client = MCPClient(
    lambda: aws_iam_streamablehttp_client(
        endpoint=mcp_url,
        aws_service="bedrock-agentcore",
    ),
)

# Configure TAVILY
os.environ["TAVILY_API_KEY"] = "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"

agent = Agent(
    model=model,
    tools=[tavily_search, mcp_client],
    system_prompt="You're a helpful assistant."
)


@app.entrypoint
def strands_agent_bedrock(payload):
    """
    Invoke the agent with a payload
    """
    user_input = payload.get("prompt")
    print("User input:", user_input)
    response = agent(user_input)
    return response.message['content'][0]['text']


if __name__ == "__main__":
    app.run()