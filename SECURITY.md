# Security Policy

## Supported Versions

Loomin-Docs is pre-1.0. Security fixes land on `main` and ship in the next release; older tags are not patched.

| Version | Supported |
|---------|-----------|
| `main`  | Yes       |
| < 1.0   | No        |

## Reporting a Vulnerability

**Please do not report security vulnerabilities through public GitHub issues.**

Report privately through either channel:

1. **GitHub Security Advisories** (preferred) — open a draft advisory from the [Security tab](https://github.com/smdsheriff/loomin-docs/security/advisories/new) of this repository.
2. **Email** — <smdsheriff@gmail.com> with `[SECURITY]` in the subject line.

Please include:

- A description of the issue and the component affected
- Steps to reproduce, or a proof-of-concept
- The impact you believe it has
- Your environment (OS, Docker version, deployment mode)

**What to expect:** acknowledgement within 5 business days, an assessment and remediation plan within 15 business days, and credit in the release notes when a fix ships unless you'd rather stay anonymous. Please give us a reasonable window to fix the issue before disclosing it publicly.

## Threat Model and Known Limitations

Loomin-Docs is built for **trusted, isolated networks** — an air-gapped VM or an internal segment behind existing access controls. The following are deliberate design constraints of the current release, not undisclosed bugs. Understand them before deploying.

### No authentication or authorization

There is no login, no session management, and no per-user data isolation. Anyone who can reach port 80 has full read and write access to every document, every uploaded file, and the entire chat history.

**Mitigation:** put an authenticating reverse proxy (OAuth2 Proxy, Authelia, or your organization's SSO gateway) with TLS termination in front of the stack. Never expose it directly to the internet.

### Permissive CORS

`backend/app/main.py` sets `allow_origins=["*"]` with `allow_credentials=True`. This is intentional for the single-host container setup, but it means any origin can call the API from a browser. If you add authentication, restrict `allow_origins` to your actual frontend origin at the same time.

### Backend and Ollama ports published to the host

Both Compose files publish `8000:8000` (FastAPI) and `11434:11434` (Ollama) on all host interfaces for debugging convenience. In production, bind them to loopback or drop the mappings entirely so only Nginx on port 80 is reachable:

```yaml
ports:
  - "127.0.0.1:8000:8000"
```

### No rate limiting

Nothing throttles chat requests, uploads, or embedding work. On a shared host, a single client can saturate CPU through LLM inference. Apply limits at your reverse proxy.

### PII sanitization is best-effort

`backend/app/core/pii.py` masks SSNs, credit cards, emails, API keys, AWS keys, and phone numbers using regular expressions before text reaches the LLM. Regex matching cannot catch every format, non-US identifier scheme, or obfuscated variant. **Do not treat it as a compliance control.** It reduces accidental leakage into prompts; it does not guarantee redaction.

Note also that PII sanitization protects the *prompt*, not storage — original text is persisted unredacted in SQLite and in `uploads/`.

### No encryption at rest

The SQLite database, the FAISS index, and uploaded source files are stored unencrypted in Docker volumes. Anyone with host filesystem or Docker daemon access can read every document. Use full-disk encryption on the host if that matters for your deployment.

### Untrusted file parsing

Uploads are validated by file extension only, then parsed with PyMuPDF (PDFs) or decoded as UTF-8 (`.md`, `.txt`), with a 50 MB size cap. A malicious PDF exercising a parser vulnerability is a plausible attack path. Keep `PyMuPDF` up to date and only accept uploads from users you already trust.

### Prompt injection

Content in an uploaded document can attempt to override the system prompt and steer the assistant's behavior. The RAG faithfulness rules make this harder but do not prevent it. Treat assistant output derived from untrusted documents as untrusted.

### Dependency supply chain

Air-gapped packages built by `deploy/sideload.sh` pin whatever versions were current when the bundle was created. Rebuild the package periodically so deployed hosts pick up upstream security fixes.

## Hardening Checklist

For anything beyond a local evaluation:

- [ ] Terminate TLS and enforce authentication at a reverse proxy in front of Nginx
- [ ] Remove or loopback-bind the `8000` and `11434` port mappings
- [ ] Restrict `allow_origins` in `main.py` to your real frontend origin
- [ ] Enable full-disk encryption on the Docker host
- [ ] Apply request rate limits at the proxy
- [ ] Restrict Docker daemon and volume access to administrators
- [ ] Back up the `backend-data` volume, and protect the backups as sensitive data
- [ ] Rebuild the offline package on a regular cadence to pick up dependency updates

## Scope

In scope: the application code in `frontend/` and `backend/`, the deployment scripts in `deploy/`, and the container configuration.

Out of scope: vulnerabilities in upstream dependencies (report those upstream, though we appreciate a heads-up), the limitations documented above, and issues that require pre-existing host or Docker daemon access.
