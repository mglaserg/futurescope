from __future__ import annotations

import html

import streamlit as st


def apply_futurescope_theme() -> None:
    st.markdown(
        """
        <style>
        :root {
          --fs-ink: #0f172a;
          --fs-muted: #64748b;
          --fs-line: rgba(148, 163, 184, .22);
          --fs-card: rgba(255,255,255,.78);
          --fs-card-strong: rgba(255,255,255,.94);
          --fs-navy: #172554;
          --fs-cyan: #0e7490;
          --fs-cyan-soft: #ecfeff;
          --fs-gold: #a16207;
          --fs-gold-soft: #fffbeb;
          --fs-green: #047857;
          --fs-red: #b91c1c;
        }
        [data-testid="stAppViewContainer"] {
          background:
            radial-gradient(circle at 80% 8%, rgba(14,116,144,.08), transparent 30rem),
            radial-gradient(circle at 15% 12%, rgba(161,98,7,.05), transparent 25rem),
            #f8fafc;
        }
        [data-testid="stHeader"] { background: rgba(248,250,252,.82); backdrop-filter: blur(14px); }
        .block-container { max-width: 1420px; padding-top: 2rem; padding-bottom: 4rem; }
        h1, h2, h3 { letter-spacing: -.025em; color: var(--fs-ink); }
        [data-testid="stMetric"] {
          background: var(--fs-card-strong);
          border: 1px solid var(--fs-line);
          border-radius: 18px;
          padding: 14px 16px;
          box-shadow: 0 12px 34px rgba(15,23,42,.05);
        }
        [data-testid="stMetricLabel"] { color: var(--fs-muted); }
        [data-testid="stMetricValue"] { color: var(--fs-ink); letter-spacing: -.03em; }
        div[data-testid="stDataFrame"] { border: 1px solid var(--fs-line); border-radius: 18px; overflow: hidden; }
        .fs-hero {
          position: relative;
          overflow: hidden;
          padding: 28px 30px;
          border: 1px solid var(--fs-line);
          border-radius: 28px;
          background: linear-gradient(125deg, rgba(255,255,255,.98), rgba(236,254,255,.72));
          box-shadow: 0 24px 60px rgba(15,23,42,.07);
          margin-bottom: 22px;
        }
        .fs-hero:after {
          content: ""; position: absolute; width: 240px; height: 240px; border-radius: 999px;
          right: -90px; top: -120px; background: rgba(14,116,144,.10);
        }
        .fs-kicker { font-size: .78rem; font-weight: 750; letter-spacing: .12em; text-transform: uppercase; color: var(--fs-cyan); }
        .fs-title { font-size: clamp(2rem, 4vw, 3.35rem); line-height: 1.02; font-weight: 800; color: var(--fs-ink); margin: 8px 0 10px; letter-spacing: -.05em; }
        .fs-subtitle { max-width: 850px; color: #475569; font-size: 1.03rem; line-height: 1.65; }
        .fs-pill { display: inline-flex; gap: 7px; align-items:center; padding: 6px 10px; border-radius: 999px; font-size: .78rem; font-weight: 700; border: 1px solid var(--fs-line); background: rgba(255,255,255,.72); color: #334155; margin-right: 7px; margin-top: 12px; }
        .fs-card { background: var(--fs-card-strong); border: 1px solid var(--fs-line); border-radius: 22px; padding: 20px 22px; box-shadow: 0 14px 38px rgba(15,23,42,.045); }
        .fs-card h4 { margin: 0 0 6px; font-size: 1.05rem; color: var(--fs-ink); }
        .fs-card p { margin: 0; color: var(--fs-muted); line-height: 1.5; }
        .fs-signal { border-radius: 24px; padding: 22px 24px; border: 1px solid var(--fs-line); background: linear-gradient(125deg, #172554, #164e63); color: white; box-shadow: 0 22px 48px rgba(23,37,84,.16); }
        .fs-signal .eyebrow { opacity: .72; font-size: .76rem; font-weight: 750; letter-spacing: .12em; text-transform: uppercase; }
        .fs-signal .headline { margin-top: 5px; font-size: 1.8rem; font-weight: 800; letter-spacing: -.035em; }
        .fs-signal .detail { opacity: .82; line-height: 1.55; margin-top: 6px; }
        .fs-pressure { padding: 18px 20px; border-radius: 22px; background: white; border: 1px solid var(--fs-line); }
        .fs-pressure-track { position: relative; height: 12px; border-radius: 99px; background: linear-gradient(90deg, #fee2e2 0 25%, #f8fafc 25% 75%, #dcfce7 75% 100%); margin: 30px 4px 13px; }
        .fs-pressure-marker { position: absolute; top: 50%; width: 20px; height: 20px; border-radius: 50%; background: #0f172a; border: 4px solid white; box-shadow: 0 2px 8px rgba(15,23,42,.25); transform: translate(-50%,-50%); }
        .fs-pressure-threshold { position:absolute; top:-8px; width:1px; height:28px; background:#94a3b8; }
        .fs-pressure-labels { display:flex; justify-content:space-between; color:var(--fs-muted); font-size:.78rem; }
        .fs-timeline { display:grid; grid-template-columns: repeat(4,minmax(0,1fr)); gap:10px; }
        .fs-step { padding:14px 15px; border-radius:18px; border:1px solid var(--fs-line); background:rgba(255,255,255,.76); min-height:96px; }
        .fs-step.active { border-color: rgba(14,116,144,.5); background: var(--fs-cyan-soft); box-shadow: inset 0 0 0 1px rgba(14,116,144,.10); }
        .fs-step .n { font-size:.72rem; text-transform:uppercase; letter-spacing:.08em; color:var(--fs-muted); font-weight:750; }
        .fs-step .d { margin-top:5px; font-size:1rem; font-weight:800; color:var(--fs-ink); }
        .fs-step .t { margin-top:3px; font-size:.82rem; color:var(--fs-muted); }
        .fs-ticket { display:grid; gap:10px; grid-template-columns: repeat(2,minmax(0,1fr)); }
        .fs-leg { border:1px solid var(--fs-line); border-radius:18px; padding:15px 16px; background:white; }
        .fs-leg .side { font-size:.72rem; letter-spacing:.1em; text-transform:uppercase; font-weight:800; }
        .fs-leg .symbol { font-size:1.25rem; font-weight:850; margin-top:3px; color:var(--fs-ink); }
        .fs-leg .meta { color:var(--fs-muted); font-size:.82rem; margin-top:3px; }
        .fs-buy .side { color: var(--fs-green); } .fs-sell .side { color: var(--fs-red); }
        .fs-note { border-left:3px solid #0e7490; padding:11px 14px; background:rgba(236,254,255,.7); border-radius:0 14px 14px 0; color:#334155; font-size:.9rem; line-height:1.55; }
        .fs-workflow-card { min-height: 150px; margin-bottom: 10px; }
        .fs-flow-strip { display:grid; grid-template-columns: 1fr auto 1fr auto 1fr auto 1fr; align-items:center; gap:12px; padding:18px 20px; border:1px solid var(--fs-line); border-radius:22px; background:rgba(255,255,255,.86); }
        .fs-flow-strip > div:not(.arrow) { min-width:0; }
        .fs-flow-strip strong { display:block; color:var(--fs-ink); font-size:.95rem; }
        .fs-flow-strip span { display:block; color:var(--fs-muted); margin-top:3px; font-size:.78rem; line-height:1.35; }
        .fs-flow-strip .arrow { color:#94a3b8; font-size:1.25rem; }
        @media (max-width: 800px) { .fs-timeline, .fs-ticket, .fs-flow-strip { grid-template-columns: 1fr; } .fs-flow-strip .arrow { transform: rotate(90deg); justify-self:center; } .fs-hero { padding:22px 20px; } }
        </style>
        """,
        unsafe_allow_html=True,
    )


def hero(kicker: str, title: str, subtitle: str, pills: list[str] | None = None) -> None:
    pill_html = "".join(f'<span class="fs-pill">{html.escape(p)}</span>' for p in (pills or []))
    st.markdown(
        f"""
        <div class="fs-hero">
          <div class="fs-kicker">{html.escape(kicker)}</div>
          <div class="fs-title">{html.escape(title)}</div>
          <div class="fs-subtitle">{html.escape(subtitle)}</div>
          <div>{pill_html}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
