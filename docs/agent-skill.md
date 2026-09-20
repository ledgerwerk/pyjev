# Agent skill

The bundled pyjev skill at `skills/pyjev/SKILL.md` teaches an agent to use
named decision contracts without reading pyjev source or adding an MCP
integration.

Its workflow is deliberately inspect-first:

1. list and show named decisions;
2. validate the complete `.pyjev.toml` locally;
3. compile the exact request without credentials;
4. inspect the schema marker and specification fingerprint;
5. execute only after offline checks succeed;
6. preserve uncertainty and metadata unless a scalar is explicitly safe;
7. apply confidence thresholds as caller policy;
8. keep deterministic constraints in normal application code.

The skill also documents credential-safe setup, `auth test`, and pyjev's
project-specific exit codes. It does not expose a generic primitive MCP server;
a future agent adapter should expose named-decision and offline tooling instead.
