from mcp.server.fastmcp import FastMCP


mcp = FastMCP(host="0.0.0.0", stateless_http=True)


# Weather tool
@mcp.tool()
def weather(city: str):
    """Get weather information.

    Args:
        city: City for which weather will be returned

    Returns:
        Weather of provided city as a string.
    """
    print(city)
    if city.lower() == "athens":
        weather = "very sunny"
    else:
        weather = "sunny"
    return weather


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
