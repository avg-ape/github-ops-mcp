from mcp.server.fastmcp import FastMCP

mcp = FastMCP("github-ops")


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
