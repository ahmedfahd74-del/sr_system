# SwingTech D20 hardening baseline

This branch is the shared handoff point for Claude, Codex/Moss, and TradingView validation.

- Branch: `swingtech/d20-hardening`
- Production file: `pinescripts/swingtech_rebuild.pine`
- Source: exact D20-fixed file supplied by the user after Claude commit `ec03903` (that local-only commit was not present on GitHub).
- Verified source size: `181701` bytes
- Verified source SHA-256: `474111f40213bbd2d51d719517dee80195e95ee5d34f9fcdb286b73e53064383`
- Pine lines: `2870`

The production file was reconstructed on GitHub only after the byte count and SHA-256 matched the uploaded source exactly. Temporary transfer payloads and the one-time materialization workflow were removed automatically after verification.

## Handoff rule

Agents should fetch this branch (or the exact commit containing this document) before auditing or modifying SwingTech. Do not substitute an older local worktree such as `0c9d429`, and do not require the unavailable local-only SHA `ec03903`.
