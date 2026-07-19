import type { Metadata } from "next";
import Link from "next/link";
import { ContactStrip, type Frame } from "@/components/ContactStrip";

export const metadata: Metadata = {
  title: "Sample teardown — Meridian (scheduling)",
  description:
    "A complete reenigne teardown of Meridian, a fictional scheduling product: feature inventory with frame references, workflow analysis, inferred data model, and the JSON feature matrix.",
  openGraph: {
    title: "Sample teardown — Meridian | reenigne",
    description:
      "What a reenigne report looks like end to end: ten sections, every observation cited to the frame it came from.",
  },
};

const FRAMES: Frame[] = [
  { n: 1, t: 0 },
  { n: 2, t: 3 },
  { n: 3, t: 6, kept: false },
  { n: 4, t: 9 },
  { n: 5, t: 12 },
  { n: 6, t: 15 },
  { n: 7, t: 18, kept: false },
  { n: 8, t: 21 },
  { n: 9, t: 24 },
  { n: 10, t: 27, kept: false },
  { n: 11, t: 30 },
  { n: 12, t: 33 },
  { n: 13, t: 36 },
  { n: 14, t: 39, kept: false },
  { n: 15, t: 42 },
  { n: 16, t: 45 },
];

const SECTIONS = [
  ["overview", "Product overview"],
  ["features", "Feature inventory"],
  ["workflow", "Workflow analysis"],
  ["patterns", "UI/UX patterns"],
  ["data-model", "Inferred data model"],
  ["stack", "Tech stack signals"],
  ["strengths", "Strengths"],
  ["opportunities", "Opportunities"],
  ["differentiation", "Differentiation"],
  ["matrix", "Feature matrix"],
] as const;

const FEATURES = [
  {
    name: "Availability rules editor",
    where: "Settings › Scheduling",
    solves: "Expressing partial-day constraints without blocking whole blocks",
    frames: "#004, #007",
  },
  {
    name: "Per-event-type buffers",
    where: "Event type › Timing",
    solves: "Padding before and after specific meeting kinds, not globally",
    frames: "#008",
  },
  {
    name: "Round-robin pooling",
    where: "Team › Distribution",
    solves: "Spreading inbound bookings across a team by load",
    frames: "#011, #012",
  },
  {
    name: "Booking page themes",
    where: "Event type › Appearance",
    solves: "Matching the booking page to the host's brand",
    frames: "#005",
  },
  {
    name: "Workflow automations",
    where: "Workflows",
    solves: "Reminder and follow-up email sequences per event type",
    frames: "#013, #015",
  },
  {
    name: "Calendar conflict detection",
    where: "Integrations › Calendars",
    solves: "Checking multiple connected calendars before offering a slot",
    frames: "#009",
  },
  {
    name: "Routing forms",
    where: "Routing",
    solves: "Sending a booker to the right host based on answers",
    frames: "#016",
  },
];

const MATRIX = `{
  "product_name": "Meridian",
  "category": "scheduling / calendar automation",
  "features": [
    {"name": "Availability rules editor", "priority": "must", "frames": [4, 7]},
    {"name": "Per-event-type buffers",    "priority": "must", "frames": [8]},
    {"name": "Round-robin pooling",       "priority": "should", "frames": [11, 12]},
    {"name": "Calendar conflict check",   "priority": "must", "frames": [9]},
    {"name": "Workflow automations",      "priority": "should", "frames": [13, 15]},
    {"name": "Routing forms",             "priority": "could", "frames": [16]},
    {"name": "Booking page themes",       "priority": "could", "frames": [5]}
  ],
  "inferred_entities": [
    "User", "Team", "EventType", "AvailabilitySchedule",
    "Booking", "CalendarConnection", "Workflow", "RoutingForm"
  ],
  "friction_points": [
    "Availability rules live two levels deep in settings",
    "No visible bulk edit for event types",
    "Timezone of the booker is inferred, never confirmed"
  ]
}`;

export default function SampleReportPage() {
  return (
    <div className="wrap section">
      <p className="eyebrow">Sample output</p>
      <h1 style={{ maxWidth: "18ch" }}>Teardown: Meridian</h1>
      <p className="lede">
        A complete report in the format reenigne produces. Meridian is a{" "}
        <strong>fictional</strong> scheduling product invented for this page — the
        structure, citations and JSON are real, the company is not.
      </p>

      <div className="notice" style={{ marginTop: "1.5rem" }}>
        <strong>About this example</strong>
        Meridian does not exist. No real product was recorded, and no screenshots of
        any real company appear here. This page demonstrates the report format on an
        invented subject so the shape is honest without publishing someone else&rsquo;s
        interface.
      </div>

      <dl
        className="mono small"
        style={{
          display: "grid",
          gridTemplateColumns: "auto 1fr",
          gap: "0.35rem 1.25rem",
          border: "1px solid var(--rule)",
          borderRadius: "3px",
          padding: "1rem 1.25rem",
          margin: "0 0 2rem",
          maxWidth: "34rem",
        }}
      >
        <dt className="muted">Session</dt>
        <dd style={{ margin: 0 }}>meridian-20260718-142203</dd>
        <dt className="muted">Duration</dt>
        <dd style={{ margin: 0 }}>00:47.2</dd>
        <dt className="muted">Frames</dt>
        <dd style={{ margin: 0 }}>16 captured · 4 dropped · 12 analysed</dd>
        <dt className="muted">Template</dt>
        <dd style={{ margin: 0 }}>teardown</dd>
      </dl>

      <ContactStrip frames={FRAMES} />
      <p className="mono small muted" style={{ marginTop: "0.6rem" }}>
        Frames #001–#016. Struck frames were dropped as near-duplicates before
        analysis.
      </p>

      <hr className="sprocket" style={{ margin: "2.5rem 0" }} />

      <div className="report-grid">
        <nav className="report-toc" aria-label="Report sections">
          <p className="eyebrow" style={{ marginBottom: "0.5rem" }}>
            Contents
          </p>
          <ol>
            {SECTIONS.map(([id, label], i) => (
              <li key={id}>
                <a href={`#${id}`}>
                  {String(i + 1).padStart(2, "0")} {label}
                </a>
              </li>
            ))}
          </ol>
        </nav>

        <article>
          <section id="overview" className="report-section">
            <h2>
              <span className="num">01</span> Product overview
            </h2>
            <p>
              Meridian is a scheduling product for teams who take inbound bookings —
              sales calls, onboarding sessions, support consultations. The booker
              picks a slot from a public page; the host&rsquo;s calendars are checked
              for conflicts first <span className="cite">[#009]</span>.
            </p>
            <p>
              The target user is an operations or revenue lead configuring booking on
              behalf of a team, not an individual scheduling their own calendar. Two
              things point that way: the settings hierarchy assumes multiple event
              types before it assumes one <span className="cite">[#004]</span>, and
              distribution rules appear at team level rather than per person{" "}
              <span className="cite">[#011]</span>.
            </p>
            <p>
              The stated value proposition, from the empty state on the dashboard, is
              reducing back-and-forth to book time. What the interface actually
              optimises for is narrower: enforcing constraints the host has already
              decided, rather than negotiating between two calendars.
            </p>
          </section>

          <section id="features" className="report-section">
            <h2>
              <span className="num">02</span> Feature inventory
            </h2>
            <p>
              Every feature visible in the session, where it lives, and the frames
              that show it.
            </p>
            <table className="feature-table">
              <caption>
                Seven features observed across 12 analysed frames. Absence from this
                table means it was not seen in this session, not that it does not
                exist.
              </caption>
              <thead>
                <tr>
                  <th scope="col">Feature</th>
                  <th scope="col">Location</th>
                  <th scope="col">Problem it solves</th>
                  <th scope="col">Frames</th>
                </tr>
              </thead>
              <tbody>
                {FEATURES.map((f) => (
                  <tr key={f.name}>
                    <th scope="row" style={{ fontFamily: "var(--font-body)", fontSize: "0.92rem", textTransform: "none", letterSpacing: 0, color: "var(--graphite)", fontWeight: 500 }}>
                      {f.name}
                    </th>
                    <td className="mono small muted">{f.where}</td>
                    <td className="muted">{f.solves}</td>
                    <td className="cite">{f.frames}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>

          <section id="workflow" className="report-section">
            <h2>
              <span className="num">03</span> Workflow analysis
            </h2>
            <h3>Primary flow — configuring a bookable event type</h3>
            <ol className="stack" style={{ paddingLeft: "1.2rem" }}>
              <li>
                Dashboard lists existing event types with booking counts{" "}
                <span className="cite">[#002]</span>.
              </li>
              <li>
                &ldquo;New event type&rdquo; opens a two-column editor: settings left,
                live booking-page preview right <span className="cite">[#005]</span>.
              </li>
              <li>
                Duration, buffers and notice period sit under a Timing tab{" "}
                <span className="cite">[#008]</span>.
              </li>
              <li>
                Availability is selected from a named schedule rather than defined
                inline — the schedule is edited elsewhere{" "}
                <span className="cite">[#004]</span>.
              </li>
              <li>
                Publishing produces a shareable URL; no confirmation step observed{" "}
                <span className="cite">[#006]</span>.
              </li>
            </ol>

            <h3 style={{ marginTop: "1.5rem" }}>Friction observed</h3>
            <ul className="stack muted" style={{ paddingLeft: "1.2rem" }}>
              <li>
                Availability rules are two levels deep in Settings, away from the
                event type that uses them. The narration on{" "}
                <span className="cite">[#004]</span> records a wrong turn into Team
                settings first.
              </li>
              <li>
                The booking-page preview does not reflect timezone, so the host cannot
                see what a booker in another region will be offered{" "}
                <span className="cite">[#005]</span>.
              </li>
              <li>
                No bulk edit: changing a buffer across six event types means six
                visits <span className="cite">[#013]</span>.
              </li>
            </ul>

            <div className="readout" style={{ marginTop: "1.5rem" }}>
              <p className="readout-label">Aligned narration — 00:09.0</p>
              <p className="mono" style={{ fontSize: "0.85rem", marginBottom: 0 }}>
                &ldquo;OK so availability isn&rsquo;t on the event type at all, it&rsquo;s
                a separate schedule I have to have made earlier — that&rsquo;s going to
                confuse anyone setting this up for the first time.&rdquo;
              </p>
            </div>
          </section>

          <section id="patterns" className="report-section">
            <h2>
              <span className="num">04</span> UI/UX patterns
            </h2>
            <p>
              <strong>Layout.</strong> A persistent left rail with six destinations,
              content in a centred column capped near 1100px. The event-type editor
              breaks this with a split view, preview pinned right{" "}
              <span className="cite">[#005]</span>.
            </p>
            <p>
              <strong>Components.</strong> Tabs inside the editor rather than a wizard
              — the whole configuration is reachable at any point, which suits editing
              more than first-time setup. Modals are reserved for destructive
              confirmations <span className="cite">[#014]</span>.
            </p>
            <p>
              <strong>Type and colour.</strong> A single grotesk at three sizes, one
              accent used only for primary actions and active nav. Generous spacing;
              cards separated by whitespace rather than borders.
            </p>
            <p>
              <strong>States.</strong> Empty states carry an illustration and a single
              action <span className="cite">[#002]</span>. Loading uses skeleton rows
              matching final row height, so no layout shift{" "}
              <span className="cite">[#011]</span>.
            </p>
          </section>

          <section id="data-model" className="report-section">
            <h2>
              <span className="num">05</span> Inferred data model
            </h2>
            <p>
              Inferred from what the interface exposes — not confirmed against an API.
            </p>
            <ul className="stack muted" style={{ paddingLeft: "1.2rem" }}>
              <li>
                <strong style={{ color: "var(--graphite)" }}>EventType</strong> is a
                first-class record: it has its own appearance, timing and workflow
                settings rather than inheriting a global preset{" "}
                <span className="cite">[#008]</span>.
              </li>
              <li>
                <strong style={{ color: "var(--graphite)" }}>AvailabilitySchedule</strong>{" "}
                is separate and referenced by name, so it is many-to-one with event
                types <span className="cite">[#004]</span>.
              </li>
              <li>
                <strong style={{ color: "var(--graphite)" }}>Team</strong> owns
                distribution rules, implying membership carries a weighting used by
                round-robin <span className="cite">[#011, #012]</span>.
              </li>
              <li>
                <strong style={{ color: "var(--graphite)" }}>CalendarConnection</strong>{" "}
                is per user and plural — the conflict check lists more than one source{" "}
                <span className="cite">[#009]</span>.
              </li>
            </ul>
          </section>

          <section id="stack" className="report-section">
            <h2>
              <span className="num">06</span> Tech stack signals
            </h2>
            <p className="muted">
              Weak evidence only; nothing here is confirmed. Client-side route changes
              with no full reload suggest a single-page application. Skeleton loaders
              of fixed height suggest server-driven pagination with known page sizes.
              No network panel was open during this session, so no API shapes were
              observed.
            </p>
          </section>

          <section id="strengths" className="report-section">
            <h2>
              <span className="num">07</span> Strengths
            </h2>
            <ol className="stack" style={{ paddingLeft: "1.2rem" }}>
              <li>
                Live booking-page preview beside the settings removes a publish-check-fix
                loop <span className="cite">[#005]</span>.
              </li>
              <li>
                Per-event-type buffers rather than one global padding — a real
                constraint expressed properly <span className="cite">[#008]</span>.
              </li>
              <li>
                Conflict checking across several connected calendars, surfaced before
                a slot is offered <span className="cite">[#009]</span>.
              </li>
              <li>
                Skeletons sized to the final content, so lists do not jump{" "}
                <span className="cite">[#011]</span>.
              </li>
              <li>
                Destructive actions are the only modals, which keeps the pattern
                meaningful <span className="cite">[#014]</span>.
              </li>
            </ol>
          </section>

          <section id="opportunities" className="report-section">
            <h2>
              <span className="num">08</span> Opportunities
            </h2>
            <ul className="stack muted" style={{ paddingLeft: "1.2rem" }}>
              <li>
                Availability is the most-edited setting and the hardest to reach.
                Inline editing on the event type, with the named schedule as an
                option, would remove the wrong turn recorded at{" "}
                <span className="cite">[#004]</span>.
              </li>
              <li>
                No timezone preview. A host cannot see what a booker in another region
                is offered, and the booker&rsquo;s timezone is inferred rather than
                confirmed.
              </li>
              <li>
                No bulk edit across event types — the cost of this grows with exactly
                the accounts worth the most.
              </li>
              <li>
                Nothing observed for rescheduling policy or cancellation windows in
                this session.
              </li>
            </ul>
          </section>

          <section id="differentiation" className="report-section">
            <h2>
              <span className="num">09</span> Differentiation
            </h2>
            <p>
              If building against Meridian, the opening is configuration at scale
              rather than feature parity. Its model is sound and its constraints are
              expressed well; what it lacks is anything for the operator maintaining
              forty event types across a team.
            </p>
            <p className="muted">
              Concretely: bulk edit across event types, availability visible where it
              is used, and a booker-timezone preview before publish. None of these
              require matching its automation surface.
            </p>
          </section>

          <section id="matrix" className="report-section">
            <h2>
              <span className="num">10</span> Feature matrix
            </h2>
            <p>
              Every report ends with a JSON block, so a session can feed a spreadsheet
              or a comparison table without re-reading the prose.
            </p>
            <details className="json-block">
              <summary>features.json — 7 features, 8 inferred entities</summary>
              <div className="readout">
                <pre>
                  <code>{MATRIX}</code>
                </pre>
              </div>
            </details>
          </section>
        </article>
      </div>

      <hr className="sprocket" style={{ margin: "3rem 0 2rem" }} />

      <h2>Run this on a product you care about</h2>
      <p className="lede">
        A session like this one takes about a minute to record and returns a report in
        a few minutes.
      </p>
      <div className="btn-row" style={{ marginTop: "1.25rem" }}>
        <Link href="/download" className="btn primary">
          Download
        </Link>
        <Link href="/pricing" className="btn">
          Pricing
        </Link>
      </div>
    </div>
  );
}
