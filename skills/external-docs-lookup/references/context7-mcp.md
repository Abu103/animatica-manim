# Context7 MCP — exact config

## Hermes config.yaml (`~/.hermes/config.yaml`)

Add under `mcp_servers:` only after the release is seeded and you have approved it:

```yaml
mcp_servers:
  context7:
    command: "npx"
    args:
      - "-y"
      - "@upstash/context7-mcp@4.4.4"
    timeout: 120
    connect_timeout: 60
    lazy: true
```

## Version pin

`@upstash/context7-mcp@4.4.4` — published 2026-10-19 (20 days old, past the 14-day minimum). Do not use `latest`; the hash and the file cannot drift apart when pinned to an explicit version.

## Verification

```bash
hermes mcp test context7
# expect: Connected, Tools discovered: 2 (resolve-library-id, query-docs)
```

## Usage (narrow topic only)

```bash
hermes chat --toolsets skills -q \
  "Use Context7 to look up how Textual's Pilot.click works, narrow topic only."
```

## Sources

- Hermes MCP docs: https://hermes-agent.nousresearch.com/docs/user-guide/features/mcp
- Context7 README: https://github.com/upstash/context7/blob/master/README.md
- Context7 MCP server: https://www.npmjs.com/package/@upstash/context7-mcp
