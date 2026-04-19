# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in TokenMind, please report it responsibly:

1. Do **not** open a public issue with exploit details.
2. Create a private security advisory on GitHub, or contact the maintainers directly at `xubinrencs@gmail.com`.
3. Include:
   - a clear description of the issue
   - reproduction steps
   - expected impact
   - any suggested mitigation or fix

We aim to respond within 48 hours.

## Security Best Practices

### 1. API Keys

Never commit API keys to source control.

```bash
# Good: config file with restricted permissions
chmod 600 ~/.tokenmind/config.json
```

Recommendations:
- Store API keys in `~/.tokenmind/config.json`
- Use file permissions `0600`
- Prefer environment variables or OS keychains in production
- Rotate keys regularly
- Separate development and production credentials

Legacy note:
- If you still have `~/.tokenmind/config.json`, TokenMind can migrate it automatically on first launch.

### 2. Channel Access Control

Always configure `allowFrom` for production use.

```json
{
  "channels": {
    "telegram": {
      "enabled": true,
      "token": "YOUR_BOT_TOKEN",
      "allowFrom": ["123456789", "987654321"]
    },
    "whatsapp": {
      "enabled": true,
      "allowFrom": ["+1234567890"]
    }
  }
}
```

Notes:
- Empty `allowFrom` denies access by default
- Use `["*"]` only if you intentionally want open access
- Review access logs regularly

### 3. Shell Command Execution

The `exec` tool can run shell commands. Even with guardrails, you should:

- review tool activity in logs
- understand what the agent is being allowed to run
- use a dedicated low-privilege user account
- never run TokenMind as `root`

Blocked patterns include destructive filesystem operations, raw disk writes, and similar dangerous commands.

### 4. File System Access

TokenMind includes path traversal protection, but you should still:

- run it with a dedicated user account
- protect sensitive directories with OS permissions
- audit file operations regularly

### 5. Network Security

API calls use HTTPS by default and include timeouts. For production deployments, consider outbound firewall restrictions where appropriate.

For the WhatsApp bridge:
- it binds to `127.0.0.1:3001` by default
- set `bridgeToken` to enable shared-secret authentication between Python and Node.js
- keep authentication data in `~/.tokenmind/whatsapp-auth` protected with mode `0700`

### 6. Dependency Security

Keep dependencies updated:

```bash
pip install pip-audit
pip-audit
pip install --upgrade tokenmind-ai
```

For the bridge:

```bash
cd bridge
npm audit
npm audit fix
```

### 7. Production Deployment

Recommended production setup:

1. Run inside a container or VM
2. Use a dedicated system user
3. Restrict file permissions
4. Monitor logs
5. Configure provider-side rate limits and spending limits
6. Keep TokenMind updated

Example:

```bash
# Dedicated user
sudo useradd -m -s /bin/bash tokenmind
sudo -u tokenmind tokenmind gateway

# Permissions
chmod 700 ~/.tokenmind
chmod 600 ~/.tokenmind/config.json
chmod 700 ~/.tokenmind/whatsapp-auth
```

### 8. Privacy

- Prompts are visible to upstream LLM providers
- Local chat history is stored under `~/.tokenmind`
- API keys are stored locally unless you layer your own secret-management strategy

Protect the entire TokenMind data directory carefully.

### 9. Incident Response

If you suspect a breach:

1. Revoke affected credentials immediately
2. Review recent logs and access attempts
3. Check for unexpected file modifications
4. Rotate all relevant secrets
5. Upgrade to the latest release
6. Report the incident to maintainers

## Known Limitations

Current limitations to keep in mind:

1. No built-in per-user rate limiting
2. Plain-text local config unless you layer your own secret management
3. No automatic session expiry by default
4. Command filtering blocks obvious risks, not every possible dangerous action

## Deployment Checklist

Before deploying TokenMind:

- [ ] API keys are stored securely
- [ ] `~/.tokenmind/config.json` has restricted permissions
- [ ] `allowFrom` is configured for all enabled channels
- [ ] the process runs as a non-root user
- [ ] filesystem permissions are reviewed
- [ ] dependencies are updated
- [ ] logs are monitored
- [ ] provider-side rate limits and spending limits are configured

## Updates

For current security updates:
- GitHub Security Advisories: [HKUDS/tokenmind security advisories](https://github.com/HKUDS/tokenmind/security/advisories)
- Release Notes: [HKUDS/tokenmind releases](https://github.com/HKUDS/tokenmind/releases)

The repository path may still use the legacy `tokenmind` name even though the product brand is now TokenMind.
