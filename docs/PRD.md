# reenigne — Product Requirements Document

**Version:** 0.2 (Desktop + subscription)
**Owner:** Toby
**Status:** Approved for build
**Last updated:** 2026-07-19
**Brand / domain:** reenigne · reenigne.dev
**Formerly:** ReverseScope

---

## 1. Product Summary

### 1.1 One-Liner
> A cross-platform desktop tool that records screen + narration, auto-captures screenshots, transcribes commentary, and hands the bundle to an LLM to produce a structured teardown report of any website or software.

### 1.2 Problem
Product teams, indie hackers, and consultants routinely study competitor products by clicking through them and taking notes. This process is:
- **Slow** — hours of screenshots, spreadsheets, docs
- **Inconsistent** — hard to compare across products
- **Lossy** — the *reasoning* while exploring is rarely captured
- **Un-actionable** — notes rarely convert into feature lists or PRDs

### 1.3 Solution
Record once. reenigne handles capture, transcription, and LLM-powered synthesis. Output: a structured teardown report, ready to inform your own product build.

### 1.4 Target Users
- **Indie founders / solopreneurs** studying incumbents before building
- **Product managers** doing competitive analysis
- **UX researchers** cataloguing patterns
- **AI builders** studying incumbents before entering a space
- **Consultants** producing rapid audits for clients

---

## 2. Goals & Non-Goals

### 2.1 Goals (MVP)
1. Zero-friction capture: one command starts recording screen + mic
2. Automatic screenshot library — no manual `Cmd+Shift+4`
3. Transcribed narration aligned with screenshots by timestamp
4. LLM-generated teardown report in markdown + JSON
5. Cross-platform: works on macOS, Windows, Linux
6. Runs as CLI in v0.1; GUI wrapper in v0.2

### 2.2 Non-Goals (MVP)
- ❌ Real-time streaming transcription (post-hoc is fine)
- ❌ Cloud storage / multi-user collaboration
- ❌ Custom LLM fine-tuning
- ❌ Automated clicking / test generation
- ❌ Video editing UI
- ❌ Mobile app recording

---

## 3. User Stories

### 3.1 Primary Flow
> As a product researcher, I want to click "record", walk through a competitor's app while narrating my observations, click "stop", and receive a structured teardown report within 5 minutes.

### 3.2 Detailed Stories
1. **Start recording** — one CLI command begins screen + mic capture
2. **Narrate while exploring** — I speak my thoughts as I click through the target product
3. **Stop recording** — Ctrl+C or "stop" ends the session
4. **Auto-processing** — App extracts screenshots every 3s, transcribes audio, aligns them
5. **Review manifest** — I can inspect the raw library before LLM analysis
6. **Generate report** — App sends bundle to Grok (OpenAI/Anthropic fallback), produces `analysis.md`
7. **Iterate** — I can re-run analysis with different prompts or models
8. **Export** — Report ships as markdown, JSON, and self-contained HTML

---

## 4. Functional Requirements

### 4.1 Capture Module
| ID | Requirement | Priority |
|----|-------------|----------|
| FR-1.1 | Capture full primary display at 1080p+ | MUST |
| FR-1.2 | Capture default microphone at 16kHz mono | MUST |
| FR-1.3 | Write video to disk (mp4, H.264) | MUST |
| FR-1.4 | Support pause/resume during recording | SHOULD |
| FR-1.5 | Support multi-monitor selection | COULD |
| FR-1.6 | Capture mouse cursor + clicks | SHOULD |
| FR-1.7 | Session metadata: start time, duration, display info | MUST |

### 4.2 Processing Module
| ID | Requirement | Priority |
|----|-------------|----------|
| FR-2.1 | Extract PNG screenshot every 3s (configurable) | MUST |
| FR-2.2 | Deduplicate visually identical consecutive frames (pHash) | MUST |
| FR-2.3 | Transcribe audio via OpenAI Whisper API | MUST |
| FR-2.4 | Segment transcript by natural pauses | MUST |
| FR-2.5 | Align transcript segments to nearest screenshots | MUST |
| FR-2.6 | OCR extracted screenshots (Tesseract) | SHOULD |
| FR-2.7 | Emit `manifest.json` describing the library | MUST |

### 4.3 Analysis Module
| ID | Requirement | Priority |
|----|-------------|----------|
| FR-3.1 | Send screenshots + transcript to multimodal LLM | MUST |
| FR-3.2 | Support Grok (xAI) as default | MUST |
| FR-3.3 | Support OpenAI GPT-4o and Claude as fallbacks | SHOULD |
| FR-3.4 | Use configurable prompt templates (`teardown`, `ux`, `features`, `tech-stack`) | MUST |
| FR-3.5 | Emit `analysis.md` (human-readable) | MUST |
| FR-3.6 | Emit `features.json` (structured) | MUST |
| FR-3.7 | Emit `report.html` (self-contained, embeds images as base64) | SHOULD |
| FR-3.8 | Handle >100 screenshots gracefully (chunking / summarization) | MUST |

### 4.4 CLI Interface
```bash
reenigne record [--output DIR] [--interval SECS] [--display N]
reenigne process DIR [--force] [--no-ocr]
reenigne analyze DIR [--model MODEL] [--prompt TEMPLATE] [--api-key KEY]
reenigne report DIR [--format html|md|json]
reenigne pipeline DIR   # record → process → analyze in one call
```

---

## 5. Non-Functional Requirements

| Category | Requirement |
|----------|-------------|
| **Performance** | Post-recording processing < 2× real-time |
| **Cost** | < $2 per 20-minute session using default settings |
| **Privacy** | All raw media stays local; only transcript + screenshots sent to LLM |
| **Reliability** | Graceful crash recovery — partial recordings should still process |
| **Portability** | Single `pip install reenigne` install on Mac/Win/Linux |
| **Extensibility** | Plugin architecture for custom analysis prompts |

---

## 6. Data Model

```
Session (one recording)
├── metadata.json
│   ├── session_id: UUID
│   ├── target_name: str (user-provided, e.g. "Heidi Health")
│   ├── started_at: ISO8601
│   ├── duration_seconds: float
│   ├── display_resolution: str
│   └── config: dict
├── recording.mp4          (source video)
├── audio.wav              (extracted mono 16kHz)
├── screenshots/
│   ├── frame_000001.png
│   ├── frame_000002.png
│   └── ...
├── manifest.json          (see structure below)
├── transcript.json        (Whisper output with timestamps)
├── transcript.md          (human-readable)
├── ocr/                   (per-frame OCR JSON)
│   └── frame_000001.json
├── analysis.md            (LLM output)
├── features.json          (structured LLM output)
└── report.html            (self-contained bundle)
```

### 6.1 `manifest.json` Structure
```json
{
  "session_id": "uuid",
  "target": "Heidi Health",
  "started_at": "2026-07-18T16:00:00Z",
  "duration_seconds": 1245.3,
  "frames": [
    {
      "index": 1,
      "path": "screenshots/frame_000001.png",
      "timestamp_seconds": 0.0,
      "phash": "9f8e7d6c...",
      "ocr_summary": "Login  |  Email  |  Password",
      "narration": "Okay so this is the login screen, standard email + password, no SSO option visible..."
    }
  ]
}
```

---

## 7. Milestones

| Milestone | Deliverable | Est. Effort |
|-----------|-------------|-------------|
| **M0** | This PRD + architecture diagram | Done ✅ |
| **M1** | CLI prototype: record + process + analyze | 2–3 days |
| **M2** | HTML report renderer | 1 day |
| **M3** | Cross-platform packaging (`pip install`) | 1 day |
| **M4** | GUI wrapper (Electron or PyQt) | 1 week |
| **M5** | Real-time scene detection | 3 days |
| **M6** | Plugin system for custom prompts | 2 days |
| **M7** | Public release (PyPI + GitHub) | 2 days |

---

## 8. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Screen recording permission issues on macOS | High | High | Ship clear onboarding with permission grant flow |
| Whisper API rate limits | Medium | Medium | Chunk audio, retry with backoff |
| LLM cost creep on large sessions | Medium | High | Deduplicate screenshots aggressively, allow local models |
| Legal: recording paid SaaS may violate ToS | Medium | Medium | Add disclaimer, require user consent, document risk in README |
| Privacy: screenshots may contain PII | High | High | Optional local-only mode, warn before cloud upload |
| Cross-platform ffmpeg quirks | Medium | Low | Bundle static ffmpeg binaries |

---

## 9. Success Metrics

- ⏱️ **Time-to-teardown:** < 10 minutes from stop-recording to finished report
- 💰 **Cost per session:** < $2 average
- 📊 **Report quality:** User rates ≥ 4/5 on usefulness (post-launch survey)
- 📦 **Install friction:** < 5 minutes from `pip install` to first recording
- 🎯 **Retention:** Users run ≥ 3 sessions in first week

---

## 10. Open Questions

1. Do we need face-blur / PII redaction on screenshots before LLM upload? (Likely: yes, optional)
2. Should we support batch analysis (compare multiple products in one report)? (V2)
3. Should we build a shared library of teardowns (like "public autopsies")? (V3 community feature)
4. Should we integrate with Figma / Notion for export? (V3)

---

*End of PRD*
