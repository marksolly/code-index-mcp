# Alternative MCP Server Configurations

## Development/Local Testing

```json
{
  "mcpServers": {
    "code-scope-dev": {
      "command": "uv",
      "args": ["run", "code-scope-mcp"],
      "cwd": "/path/to/code-scope-mcp",
      "disabled": false
    }
  }
}
```

## Using uvx (Universal Installation)

```json
{
  "mcpServers": {
    "code-scope": {
      "command": "uvx",
      "args": ["code-scope-mcp"],
      "disabled": false
    }
  }
}
```

## Using pip Installation

```json
{
  "mcpServers": {
    "code-scope": {
      "command": "python",
      "args": ["-m", "code_scope_mcp.server"],
      "disabled": false
    }
  }
}
```

## Configuration Locations

- **Claude Desktop**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Cline/Kilo Code**: Check your tool's MCP configuration settings
- **VS Code**: In settings, search for "mcp" or check the MCP extension settings

## Notes

- Replace `/path/to/code-scope-mcp` with the actual path to your local clone
- The `cwd` parameter is optional but recommended for local development
- Set `disabled: true` to temporarily disable the server
- Adjust `timeout` if you need more time for large database queries