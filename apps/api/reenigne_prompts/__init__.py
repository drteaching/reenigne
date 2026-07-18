"""
Analysis prompt templates — the single source of truth.

The prompts are the product, so the paid server path and the worker's local
dev path must never resolve different text for the same template name. This
module is the only definition; both consumers import it.

Deliberately dependency-free. The worker installs it as a standalone
distribution (see the pyproject.toml beside this package) so it can be
imported without dragging in FastAPI, SQLAlchemy or any provider SDK.

It lives under apps/api because that directory is the Vercel deployment root
— scripts/deploy-vercel.sh runs `vercel` from inside it, so nothing outside
apps/api is uploaded. Keeping the canonical copy here means the server keeps
importing it with no packaging step, no requirements change and no build
hook. See docs/architecture.md for the full rationale.
"""

TEARDOWN_PROMPT = """You are a senior product analyst performing a competitive teardown of a software product.

You will receive:
1. A sequence of timestamped screenshots from a recorded user session
2. Narration from the user exploring the product

Your job is to produce a rigorous PRODUCT AUTOPSY covering:

## 1. Product Overview
- What is this product?
- Who is the target user?
- What is the core value proposition?

## 2. Feature Inventory
List EVERY feature visible in the screenshots. For each:
- Feature name
- Where it lives in the UI (nav location)
- What user problem it solves
- Screenshot references (frame numbers)

## 3. Workflow Analysis
- Primary user flow (step-by-step)
- Any secondary flows observed
- Loading/empty/error states seen
- Points of friction

## 4. UI/UX Patterns
- Design system observations (colors, typography, spacing)
- Component patterns (cards, modals, tables, forms)
- Interaction patterns (hover, drag, keyboard)
- Responsive/layout choices

## 5. Data Model (Inferred)
- Entities visible in the UI
- Relationships between them
- Business logic clues

## 6. Tech Stack Guesses
- Frontend framework hints
- Backend patterns (from any visible URLs/API calls)
- Third-party integrations

## 7. Strengths (What to Copy)
- Top 5 things this product does exceptionally well

## 8. Weaknesses / Opportunities
- Gaps, friction, UX problems
- Features conspicuously missing

## 9. Recommended Differentiation
- If building a competitor, what would you do differently?

## 10. Feature Matrix (Structured Output)
End your response with a JSON block wrapped in ```json ... ``` fences containing:
```json
{
  "product_name": "string",
  "category": "string",
  "features": [
    {"name": "string", "priority": "must|should|could",
     "location": "string", "screenshots": [1, 2, 3]}
  ],
  "strengths": ["string"],
  "weaknesses": ["string"],
  "opportunities": ["string"]
}
```

Be thorough, specific, and reference screenshot indices throughout.
The user narration will contain their live observations — weave those in.
"""

UX_PROMPT = """You are a UX designer analyzing a product's user experience.

Focus purely on UX quality, not features:
- Information architecture
- Visual hierarchy
- Micro-interactions
- Accessibility signals
- Onboarding effectiveness
- Cognitive load
- Emotional design

Reference screenshot indices. Rate each area 1-5 with justification.
"""

FEATURES_ONLY_PROMPT = """Extract a comprehensive, deduplicated feature list from these screenshots and narration.
Output ONLY a JSON array of features. Each feature: {name, description, evidence_frames: [int]}.
Wrap in ```json ... ``` fences.
"""

TECH_STACK_PROMPT = """Analyze these screenshots for technical fingerprints.
Look for: framework signatures, CSS patterns, API URLs in network devtools, loading indicators typical of specific stacks, footer credits, error message formats.
Output structured guesses with confidence levels.
"""

PROMPTS = {
    "teardown": TEARDOWN_PROMPT,
    "ux": UX_PROMPT,
    "features": FEATURES_ONLY_PROMPT,
    "tech-stack": TECH_STACK_PROMPT,
}
