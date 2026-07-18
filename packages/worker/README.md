# reenigne worker

Python pipeline for capture, processing, and cloud-backed analysis.

```bash
pip install -e ".[dev]"
export REENIGNE_API_TOKEN=...
export REENIGNE_API_URL=http://localhost:8000
reenigne record --target "My Product"
```

Provider API keys are **never** required in the worker when using the cloud API.
