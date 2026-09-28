"""ThreatLens — coordinated threat early-warning for police cyber cells (Streamlit UI).

Upload any post export (JSON / CSV). IBM Bob checks every post for violations of the Bharatiya
Nyaya Sanhita 2023 and the IT Act 2000 and explains each section; ThreatLens then finds
coordinated campaigns, their escalation state and the recommended actions.

Run from src/:  streamlit run app.py
"""
from __future__ import annotations

import html as html_lib
import json
from datetime import datetime, timedelta

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

from threatlens import bob_client
from threatlens.brief import STATE_COLOURS, bluf, countdown, render_brief
from threatlens.correlation import IST, PHASES, STATES, STATE_RANK, _to_dt
from threatlens.evaluate import evaluate
from threatlens.ingest import normalize
from threatlens.law import CANDIDATES, CATEGORIES, EXCLUDED, load_kb, source_files
from threatlens.paths import SAMPLE_DATA
from threatlens.pipeline import SAMPLES, analyze, default_cutoffs, load_sample
from threatlens.schema import ALIASES, load_incidents, load_posts

st.set_page_config(page_title="ThreatLens", page_icon="🛡️", layout="wide", initial_sidebar_state="collapsed")

PHASE_COLOURS = dict(zip(PHASES, ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]))
SEV_COLOURS = {"critical": "#b3261e", "high": "#d9480f", "medium": "#b7791f", "low": "#6b7280"}
SEV_ORDER = ["critical", "high", "medium", "low"]

st.markdown("""
<style>
#MainMenu, footer, .stAppDeployButton, [data-testid="stToolbar"], [data-testid="stDecoration"] {display:none !important;}
header[data-testid="stHeader"] {background: transparent; height: 0;}
.block-container {padding-top: 1.2rem; padding-bottom: 3rem; max-width: 1400px;}
.hero {background: linear-gradient(120deg, #0f2a4f 0%, #1f4e8c 100%); color: #fff; border-radius: 14px;
       padding: 22px 28px; margin-bottom: 18px;}
.hero h1 {color:#fff; margin:0; font-size: 1.9rem; letter-spacing: -.01em;}
.hero p {color:#d6e2f3; margin:.3rem 0 .7rem; font-size: .98rem;}
.pill {display:inline-block; padding:3px 10px; border-radius:999px; font-size:.78rem; font-weight:600;
       margin:0 6px 4px 0; background: rgba(255,255,255,.14); color:#fff; border:1px solid rgba(255,255,255,.25);}
.pill.ok::before {content:"● "; color:#5be38f;} .pill.off::before {content:"● "; color:#ffb4a8;}
.chip {display:inline-block; padding:2px 10px; border-radius:12px; color:#fff; font-weight:700; font-size:.78rem;}
.sev {display:inline-block; padding:1px 8px; border-radius:6px; color:#fff; font-weight:700; font-size:.74rem;
      text-transform: uppercase; letter-spacing:.03em;}
.tag {display:inline-block; padding:1px 8px; border-radius:6px; font-size:.76rem; background:#eef2f7;
      color:#1f3b63; margin:0 4px 4px 0; border:1px solid #d7dfea;}
.kpi {background:#fff; border:1px solid #e3e7ee; border-radius:12px; padding:14px 16px; height:100%;}
.kpi .l {font-size:.78rem; color:#5b6573; text-transform:uppercase; letter-spacing:.04em;}
.kpi .v {font-size:1.7rem; font-weight:700; color:#10223d; line-height:1.2; margin-top:4px;}
.kpi .s {font-size:.8rem; color:#5b6573; margin-top:2px;}
.card {background:#fff; border:1px solid #e3e7ee; border-radius:12px; padding:14px 18px; margin-bottom:10px;}
.card h4 {margin:0 0 6px; font-size:1rem;}
.law {border-left:4px solid #1f4e8c; background:#f7f9fc; border-radius:0 10px 10px 0; padding:10px 14px; margin:8px 0;}
.law b {color:#10223d;}
.muted {color:#5b6573; font-size:.85rem;}
.ids {font-family:Consolas,monospace; font-size:.78rem; color:#5b6573;}
.ladder {display:flex; gap:6px; margin:.4rem 0 .9rem;}
.ladder div {flex:1; text-align:center; padding:10px 4px; border-radius:8px; font-weight:700; font-size:.82rem;
             border:2px solid #d5dae2; color:#9aa3ad; background:#fff;}
table.t {width:100%; border-collapse:collapse; font-size:.88rem; background:#fff;}
table.t th {text-align:left; border-bottom:2px solid #dfe4ec; padding:8px; color:#3b4656; font-weight:600;}
table.t td {border-bottom:1px solid #eef1f5; padding:8px; vertical-align:top;}
.stTabs [data-baseweb="tab-list"] {gap: 4px;}
.stTabs [data-baseweb="tab"] {padding: 8px 16px; border-radius: 8px 8px 0 0;}
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

def esc(s) -> str:
    return html_lib.escape(str(s if s is not None else ""))


def chip(state: str) -> str:
    return f'<span class="chip" style="background:{STATE_COLOURS[state]}">{state}</span>'


def sev(s: str | None) -> str:
    return f'<span class="sev" style="background:{SEV_COLOURS.get(s, "#6b7280")}">{esc(s or "—")}</span>'


def fmt_t(iso) -> str:
    return _to_dt(iso).strftime("%d %b %H:%M") if iso else "—"


def ids(xs: list[str], n: int = 5) -> str:
    return ", ".join(xs[:n]) + (" …" if len(xs) > n else "")


def kpi(col, label: str, value: str, sub: str = "") -> None:
    col.markdown(f"<div class='kpi'><div class='l'>{esc(label)}</div><div class='v'>{value}</div>"
                 f"<div class='s'>{sub}</div></div>", unsafe_allow_html=True)


def embed_html(html: str, height: int) -> None:
    if hasattr(st, "iframe"):
        st.iframe(html, height=height)
    else:
        components.html(html, height=height, scrolling=True)


def cat_label(c: str) -> str:
    return CATEGORIES[c]["label"] if c in CATEGORIES else c


# ---------------------------------------------------------------------------
# Header + control panel
# ---------------------------------------------------------------------------

def hero() -> None:
    kb = load_kb()
    bns = sum(1 for k in kb if k[0] == "BNS")
    it = sum(1 for k in kb if k[0] == "IT Act")
    bob = bob_client.status()
    st.markdown(f"""
<div class="hero">
  <h1>🛡️ ThreatLens</h1>
  <p>Early warning for coordinated online threats. Upload posts, and IBM Bob checks each one against the
  Bharatiya Nyaya Sanhita 2023 and the IT Act 2000, explains every section it applies, and ThreatLens
  tracks how coordinated campaigns escalate toward offline action.</p>
  <span class="pill {'ok' if bob['ready'] else 'off'}">{esc(bob['detail'])}</span>
  <span class="pill">Legal KB: BNS 2023 · {bns} sections — IT Act 2000 · {it} sections (official text)</span>
  <span class="pill">Human review required for every action</span>
</div>""", unsafe_allow_html=True)


@st.cache_data(show_spinner=False)
def _sample(name: str):
    return load_sample(name)


def control_panel() -> dict | None:
    with st.container(border=True):
        c1, c2, c3 = st.columns([1.25, 1.35, 1])
        with c1:
            st.markdown("**1 · Data**")
            choice = st.radio("Data", ["Sample · 100 posts", "Full demo day · 522 posts", "Upload JSON / CSV"],
                              label_visibility="collapsed")
            df, incidents, name = None, [], None
            if choice.startswith("Upload"):
                up = st.file_uploader("Posts (.json or .csv)", type=["json", "csv"])
                up_inc = st.file_uploader("Offline incident log (optional, .json / .csv)", type=["json", "csv"])
                try:
                    if up is not None:
                        df = normalize(load_posts(up))
                        name = up.name
                    if up_inc is not None:
                        incidents = load_incidents(up_inc)
                except Exception as exc:
                    st.error(f"Could not read the file: {exc}")
                    df = None
                if df is not None and df.attrs.get("inferred"):
                    with st.expander(f"{len(df.attrs['inferred'])} fields were mapped or inferred"):
                        for line in df.attrs["inferred"]:
                            st.caption("• " + line)
            else:
                key = "sample_100" if choice.startswith("Sample") else "demo_day"
                df, incidents = _sample(key)
                name = SAMPLES[key][1]
            if df is not None:
                st.caption(f"{len(df)} posts · {df['account_id'].nunique()} accounts · {len(incidents)} offline "
                           f"incidents · {fmt_t(df['timestamp'].min())} → {fmt_t(df['timestamp'].max())}")
        if df is None:
            with c2:
                st.info("Upload a posts file to continue. Only a text column is required; see **Data & sources** "
                        "for the accepted fields.")
            return None
        with c2:
            st.markdown("**2 · Time window**")
            lo = df["timestamp"].min().to_pydatetime().replace(second=0, microsecond=0)
            hi = df["timestamp"].max().to_pydatetime().replace(second=0, microsecond=0) + timedelta(minutes=1)
            d_prev, d_cur = (_to_dt(x) for x in default_cutoffs(df))
            d_prev = min(max(d_prev.replace(second=0, microsecond=0), lo), hi)
            d_cur = min(max(d_cur.replace(second=0, microsecond=0), lo), hi)
            cur = st.slider("Analyse posts up to", min_value=lo, max_value=hi, value=d_cur,
                            step=timedelta(minutes=1), format="DD MMM HH:mm")
            prev = st.slider("Compare with an earlier snapshot at", min_value=lo, max_value=hi,
                             value=min(d_prev, cur), step=timedelta(minutes=1), format="DD MMM HH:mm",
                             help="'What changed' compares the campaigns at this earlier time with now.")
        with c3:
            st.markdown("**3 · Engine**")
            bob = bob_client.status()
            engine = st.radio("Engine", ["IBM Bob", "Offline rules (no AI)"], index=0 if bob["ready"] else 1,
                              label_visibility="collapsed")
            if engine == "IBM Bob" and not bob["ready"]:
                st.warning(f"Bob is not available: {bob['detail']}. Results will use offline rules.")
            analyst = st.text_input("Analyst", value="Inspector Demo")
            run = st.button("Analyse", type="primary", width="stretch")
    return {"df": df, "incidents": incidents, "name": name, "prev": prev.isoformat(), "cur": cur.isoformat(),
            "mode": "auto" if engine == "IBM Bob" else "rules", "analyst": analyst, "run": run,
            "sample": not choice.startswith("Upload")}


def run_analysis(opts: dict) -> None:
    if opts["prev"] >= opts["cur"]:
        st.warning("The comparison snapshot must be earlier than the analysis time.")
        return
    bar = st.progress(0.0, text="IBM Bob is reading the posts…")

    def progress(done: int, total: int) -> None:
        bar.progress(done / total, text=f"IBM Bob: batch {done} of {total} analysed")

    try:
        result = analyze(opts["df"], opts["incidents"], opts["prev"], opts["cur"], opts["mode"], progress)
        st.session_state.update(result=result, df=opts["df"], data_name=opts["name"], sample=opts["sample"])
    except Exception as exc:
        st.error(f"Analysis failed: {exc}")
    finally:
        bar.empty()


# ---------------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------------

def view_overview(r: dict) -> None:
    s, camps = r["violation_summary"], r["campaigns"]
    viol = [v for v in r["violations"].values() if v["violation"]]
    hi = sum(1 for v in viol if v["severity"] in ("critical", "high"))
    top = max((c["state"] for c in camps), key=STATE_RANK.get, default=None)
    upcoming = [c["offline"]["planned_event"] for c in camps
                if c["offline"]["planned_event"] and c["offline"]["planned_event"]["hours_from_snapshot"] >= 0]
    nxt = min(upcoming, key=lambda p: p["hours_from_snapshot"]) if upcoming else None
    k = st.columns(5)
    kpi(k[0], "Posts analysed", f"{s['posts']:,}", f"{r['snapshot_accounts']:,} accounts")
    kpi(k[1], "Posts violating law", f"{s['violating']:,}",
        f"{(s['violating'] / max(s['posts'], 1)):.0%} of posts · {hi} high/critical")
    kpi(k[2], "Coordinated campaigns", str(len(camps)),
        f"{sum(1 for p, v in r['violations'].items() if v['violation'] and p not in r['in_campaign'])} "
        "standalone violations")
    kpi(k[3], "Highest campaign state", chip(top) if top else "—", "explicit triggers T1–T5")
    kpi(k[4], "Next planned gathering", f"{nxt['hours_from_snapshot']:.1f} h" if nxt else "none",
        f"{esc(nxt['place'])} · {_to_dt(nxt['time']).strftime('%a %H:%M')}" if nxt else "no upcoming place + time call")
    src = r["llm_sources"]
    st.caption(f"Engine: {', '.join(f'{k} ×{v}' for k, v in src.items())} posts · "
               f"{r['violation_meta']['bob_calls']} new Bob calls ({r['violation_meta']['bob_cost']} bobcoins) · "
               f"{r['timings']['total_s']} s" + (" · ⚠ " + "; ".join(r["violation_meta"]["errors"][:2])
                                               if r["violation_meta"]["errors"] else ""))

    left, right = st.columns(2)
    with left:
        st.markdown("##### Violations by type")
        cats = s["by_category"].most_common()
        if cats:
            fig = go.Figure(go.Bar(y=[cat_label(c) for c, _ in cats], x=[n for _, n in cats], orientation="h",
                                   marker_color="#1f4e8c", text=[n for _, n in cats], textposition="outside",
                                   hovertemplate="%{y}: %{x} posts<extra></extra>"))
            fig.update_layout(height=40 + 34 * len(cats), margin=dict(l=0, r=30, t=4, b=0),
                              yaxis=dict(autorange="reversed"), xaxis=dict(title="posts"),
                              plot_bgcolor="#fff", paper_bgcolor="rgba(0,0,0,0)")
            st.plotly_chart(fig, width="stretch")
        else:
            st.success("No post violates any of the listed sections.")
    with right:
        st.markdown("##### Sections most often applied")
        secs = s["by_section"].most_common(8)
        if secs:
            kb = load_kb()
            rows = "".join(f"<tr><td><b>{esc(sec)}</b></td><td>{esc(kb[tuple(sec.split(' ', 1)) if sec.startswith('BNS') else ('IT Act', sec.split(' ')[-1])]['title'][:70])}</td>"
                           f"<td style='text-align:right'>{n}</td></tr>" for sec, n in secs)
            st.markdown(f"<table class='t'><tr><th>Section</th><th>Offence (official title)</th>"
                        f"<th style='text-align:right'>Posts</th></tr>{rows}</table>", unsafe_allow_html=True)
    st.markdown("##### Campaigns")
    if not camps:
        st.caption("No coordinated group of 5 or more accounts in this window.")
    for c in camps:
        pe = c["offline"]["planned_event"]
        wc = c["what_changed"]
        badge = "NEW" if wc["is_new_campaign"] else ("CHANGED since " + fmt_t(wc["previous_cutoff"]) if wc["items"] else "")
        st.markdown(
            f"<div class='card'><h4>{chip(c['state'])} &nbsp;{esc(c['campaign_id'])} · {esc(c['_main_hashtag'])} · "
            f"{esc(c['label'])} <span class='muted'>{esc(badge)}</span></h4>"
            f"<span class='muted'>{len(c['_cluster']['account_ids'])} accounts · {len(c['_cluster']['post_ids'])} posts"
            f" · coordination {c['_cluster']['coordination_score']}/100 · {esc(c['narrative']['path'])}</span><br>"
            + (f"<b>Planned gathering:</b> {esc(pe['place'])}, {esc(_to_dt(pe['time']).strftime('%a %d %b %H:%M'))} "
               f"— {esc(countdown(pe))}<br>" if pe else "")
            + "".join(f"<span class='tag'>{esc(l['id'])}</span>" for l in c["legal"]) + "</div>",
            unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Violations (per post)
# ---------------------------------------------------------------------------

def view_violations(r: dict, df: pd.DataFrame) -> None:
    viol = {p: v for p, v in r["violations"].items() if v["violation"]}
    if not viol:
        st.success("No post in this window violates BNS or IT Act provisions in the catalogue.")
        return
    rows = df.set_index("post_id")
    campaign_of = {p: c["campaign_id"] for c in r["campaigns"] for p in c["_cluster"]["post_ids"]}
    f1, f2, f3, f4 = st.columns([1.4, 1, 1, 1.2])
    cats = f1.multiselect("Violation type", sorted({c for v in viol.values() for c in v["categories"]}),
                          format_func=cat_label)
    sevs = f2.multiselect("Severity", SEV_ORDER)
    act = f3.selectbox("Law", ["Both", "BNS 2023", "IT Act 2000"])
    scope = f4.selectbox("Scope", ["All posts", "Only inside campaigns", "Only standalone posts"])
    query = st.text_input("Search text or handle", placeholder="e.g. chowk, @meera_reports, OTP")

    def keep(pid, v):
        if cats and not set(cats) & set(v["categories"]):
            return False
        if sevs and v["severity"] not in sevs:
            return False
        if act != "Both" and not any(s["act"] == ("BNS" if act.startswith("BNS") else "IT Act") for s in v["sections"]):
            return False
        if scope.startswith("Only inside") and pid not in campaign_of or scope.startswith("Only standalone") and pid in campaign_of:
            return False
        if query and query.lower() not in (rows.loc[pid, "text"] + " @" + rows.loc[pid, "handle"]).lower():
            return False
        return True

    shown = sorted((p for p, v in viol.items() if keep(p, v)),
                   key=lambda p: (SEV_ORDER.index(viol[p]["severity"] or "low"), rows.loc[p, "timestamp"]))
    table = pd.DataFrame([{
        "Post": p, "Time": rows.loc[p, "timestamp"].strftime("%d %b %H:%M"), "Account": "@" + rows.loc[p, "handle"],
        "Severity": viol[p]["severity"], "Violation": ", ".join(cat_label(c) for c in viol[p]["categories"]),
        "Sections": ", ".join(f"{s['act']} {s['section']}" for s in viol[p]["sections"]),
        "Campaign": campaign_of.get(p, "standalone"), "Text (masked)": rows.loc[p, "text_masked"],
        "Engine": viol[p]["source"]} for p in shown])
    st.caption(f"{len(shown)} of {len(viol)} violating posts")
    if table.empty:
        return
    st.dataframe(table, hide_index=True, width="stretch", height=320,
                 column_config={"Text (masked)": st.column_config.TextColumn(width="large")})
    report = [{"post_id": p, "timestamp": rows.loc[p, "timestamp"].isoformat(), "handle": rows.loc[p, "handle"],
               "text_masked": rows.loc[p, "text_masked"], "campaign": campaign_of.get(p), **{
                   k: viol[p][k] for k in ("categories", "severity", "target", "evidence_quote", "location", "time",
                                           "sections", "source")}} for p in shown]
    st.download_button("Download violations report (JSON)", json.dumps(report, ensure_ascii=False, indent=1),
                       file_name="threatlens_violations.json", mime="application/json")

    st.markdown("##### Why is this post a violation?")
    pid = st.selectbox("Post", shown, format_func=lambda p: f"{p} · {viol[p]['severity']} · "
                       f"{rows.loc[p, 'text_masked'][:90]}")
    v, row = viol[pid], rows.loc[pid]
    kb = load_kb()
    quote = esc(v["evidence_quote"] or "")
    text = esc(row["text_masked"])
    if quote and quote in text:
        text = text.replace(quote, f"<mark>{quote}</mark>", 1)
    st.markdown(
        f"<div class='card'><div class='muted'>@{esc(row['handle'])} · {esc(row['timestamp'].strftime('%d %b %Y %H:%M IST'))}"
        f" · {esc(row['platform'])} · {esc(campaign_of.get(pid, 'standalone post'))}</div>"
        f"<p style='font-size:1.05rem;margin:.5rem 0'>{text}</p>"
        f"{sev(v['severity'])} " + "".join(f"<span class='tag'>{esc(cat_label(c))}</span>" for c in v["categories"])
        + (f"<br><span class='muted'>Target: {esc(v['target'])} ({esc(v['target_type'])})</span>" if v["target"] else "")
        + (f"<span class='muted'> · Place: {esc(v['location'])}</span>" if v["location"] else "")
        + (f"<span class='muted'> · Time: {esc(v['time'])}</span>" if v["time"] else "")
        + (f"<br><span class='muted'>{esc(v['summary'])}</span>" if v["summary"] else "")
        + f"<br><span class='muted'>Engine: {'IBM Bob' if v['source'] in ('bob', 'cache') else 'offline rules'}"
          f"{' (cached)' if v['source'] == 'cache' else ''}</span></div>", unsafe_allow_html=True)
    for s in v["sections"]:
        rec = kb.get((s["act"], s["section"]))
        st.markdown(f"<div class='law'><b>{esc(s['act'])} section {esc(s['section'])} — {esc(s['title'])}</b>"
                    f"<br>{esc(s['explanation'])}<br><span class='muted'>Official text: "
                    f"{esc(rec['source'].split(',')[0]) if rec else ''}, page {esc(s['page'])} · "
                    "Suggested — requires legal officer review</span></div>", unsafe_allow_html=True)
        if rec:
            with st.expander(f"Read {s['act']} {s['section']} (official text)"):
                st.write(rec["text"])
    if v.get("rejected_sections"):
        st.caption("Rejected citations (not in the catalogue): " + ", ".join(v["rejected_sections"]))


# ---------------------------------------------------------------------------
# Campaigns
# ---------------------------------------------------------------------------

def ladder(state: str, reached: set[str]) -> None:
    boxes = []
    for s in STATES:
        style = (f"background:{STATE_COLOURS[s]};border-color:{STATE_COLOURS[s]};color:#fff" if s == state else
                 f"border-color:{STATE_COLOURS[s]};color:{STATE_COLOURS[s]}" if s in reached else "")
        boxes.append(f"<div style='{style}'>{s}</div>")
    st.markdown("<div class='ladder'>" + "".join(boxes) + "</div>", unsafe_allow_html=True)


def c_overview(c: dict) -> None:
    for line in bluf(c):
        head, body = line.split(":", 1)
        st.markdown(f"**{head}:**{body}")
    ladder(c["state"], {h["state"] for h in c["state_history"]})
    st.dataframe(pd.DataFrame([{
        "Trigger": t["id"], "State": t["state"], "Rule": t["condition"], "Observed": t["observed"],
        "Fired": ("✅ " + fmt_t(t["fired_at"]) + ("" if t["counts_toward_state"] else " (benign: capped)"))
        if t["fired"] else "—", "Evidence": ids(t["evidence_post_ids"])} for t in c["triggers"]]),
        hide_index=True, width="stretch")
    cl = c["_cluster"]
    weights = {"text_similarity": 25, "time_sync": 20, "fresh_accounts": 20, "shared_url": 15, "amplification": 20}
    names = list(cl["contributions"])
    fig = go.Figure()
    fig.add_bar(y=names, x=[weights[k] for k in names], orientation="h", marker_color="rgba(31,78,140,.12)",
                hoverinfo="skip")
    fig.add_bar(y=names, x=[cl["contributions"][k] for k in names], orientation="h", marker_color="#1f4e8c",
                text=[f"{cl['contributions'][k]} pts (signal {cl['signals'][k]:.2f})" for k in names],
                textposition="outside", hovertemplate="%{y}: %{x} points<extra></extra>")
    fig.update_layout(barmode="overlay", height=220, margin=dict(l=0, r=40, t=30, b=0), showlegend=False,
                      title=dict(text=f"Coordination score {cl['coordination_score']}/100 (how coordinated, not how dangerous)",
                                 font=dict(size=13)),
                      xaxis=dict(range=[0, 30]), yaxis=dict(autorange="reversed"), plot_bgcolor="#fff",
                      paper_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig, width="stretch")


def c_timeline(c: dict, df: pd.DataFrame) -> None:
    cdf = df[df["post_id"].isin(c["_cluster"]["post_ids"])].copy()
    cdf["phase"] = cdf["post_id"].map(c["_phase_by_post"])
    cdf["minute"] = cdf["timestamp"].dt.floor("min").dt.tz_localize(None)
    start, detected = _to_dt(c["_cluster"]["start"]), _to_dt(c["_cluster"]["detected_at"])
    lag = (detected - start).total_seconds() / 60
    st.markdown(f"**Detected T+{lag:.0f} min** after the first post · narrative **{c['narrative']['path']}**")
    fig = go.Figure()
    for ph in PHASES:
        per = cdf[cdf["phase"] == ph].groupby("minute").size()
        if len(per):
            fig.add_bar(x=per.index, y=per.values, name=ph, marker_color=PHASE_COLOURS[ph], marker_line_width=0,
                        hovertemplate=f"{ph}<br>%{{x|%H:%M}}: %{{y}} posts<extra></extra>")
    marks = [(detected, f"Detected T+{lag:.0f}m", "#10223d")] + \
        [(_to_dt(e["t"]), e["type"].replace("_", " ").title(), "#b3261e") for e in c["timeline"]
         if e["type"] in ("MOBILIZATION_SIGNAL", "OFFLINE_MATCH")]
    for i, (t, label, colour) in enumerate(marks):
        x = t.astimezone(IST).replace(tzinfo=None)
        fig.add_shape(type="line", x0=x, x1=x, y0=0, y1=1, yref="paper", line=dict(color=colour, width=1.5, dash="dot"))
        fig.add_annotation(x=x, y=1 - 0.09 * i, yref="paper", text=label, showarrow=False, xanchor="left",
                           font=dict(size=11, color=colour), bgcolor="rgba(255,255,255,.8)")
    fig.update_layout(barmode="stack", height=320, margin=dict(l=0, r=0, t=10, b=0), yaxis_title="posts per minute",
                      legend=dict(orientation="h", y=-0.2), plot_bgcolor="#fff", paper_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig, width="stretch")
    st.dataframe(pd.DataFrame([{"Phase": p["phase"], "First seen": fmt_t(p["first_seen"]), "Posts": p["post_count"],
                                "Example (masked)": p["example_quote"], "Evidence": ids(p["evidence_post_ids"])}
                               for p in c["narrative"]["phases"]]), hide_index=True, width="stretch")
    st.caption(f"Summary ({'IBM Bob' if c['narrative']['summary_source'] in ('bob', 'cache') else 'template'}): "
               f"{c['narrative']['summary']}")
    st.dataframe(pd.DataFrame([{"Time": fmt_t(e["t"]), "Event": e["type"], "What": e["description"],
                                "Evidence": ids(e["evidence_post_ids"], 3)} for e in c["timeline"]]),
                 hide_index=True, width="stretch")


def network_html(c: dict, df: pd.DataFrame) -> str:
    from pyvis.network import Network
    cl = c["_cluster"]
    handles = df.drop_duplicates("account_id").set_index("account_id")["handle"].map(html_lib.escape)
    first, amps = set(cl["first_posters"]), set(cl["top_amplifiers"])
    net = Network(height="500px", width="100%", bgcolor="#ffffff", font_color="#333333", cdn_resources="in_line")
    for a in cl["account_ids"]:
        colour, size, role = ("#b3261e", 26, "first poster") if a in first else \
            ("#eb6834", 18, "top amplifier") if a in amps else ("#9aa3ad", 10, "member")
        net.add_node(a, font={"size": 16}, label="@" + handles.get(a, a) if a in first | amps else " ",
                     color=colour, size=size, title=f"@{handles.get(a, a)} ({role})")
    for a, b, kinds in cl["edges"]:
        net.add_edge(a, b, title=", ".join(kinds), color="#c8ccd2", width=1 + ("repost" in kinds))
    net.set_options(json.dumps({"physics": {"solver": "forceAtlas2Based",
                                            "stabilization": {"enabled": True, "iterations": 200},
                                            "forceAtlas2Based": {"gravitationalConstant": -40, "springLength": 70}},
                                "interaction": {"hover": True}}))
    return net.generate_html().replace(
        "network = new vis.Network(container, data, options);",
        "network = new vis.Network(container, data, options);"
        "network.once('stabilizationIterationsDone', function(){network.setOptions({physics:false});});")


def c_propagation(c: dict, df: pd.DataFrame) -> None:
    p = c["propagation"]
    b = pd.DataFrame(p["buckets"])
    b["start"] = pd.to_datetime(b["start"]).dt.tz_localize(None)
    fig = go.Figure()
    fig.add_scatter(x=b["start"], y=b["cum_posts"], name="posts (cumulative)", mode="lines+markers",
                    line=dict(color="#2a78d6", width=2), marker=dict(size=8))
    fig.add_scatter(x=b["start"], y=b["cum_accounts"], name="accounts (cumulative)", mode="lines+markers",
                    line=dict(color="#eb6834", width=2), marker=dict(size=8))
    fig.update_layout(height=240, margin=dict(l=0, r=0, t=10, b=0), hovermode="x unified", yaxis_title="count",
                      legend=dict(orientation="h", y=-0.3), plot_bgcolor="#fff", paper_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig, width="stretch")
    k = st.columns(3)
    kpi(k[0], "Potential reach", f"{p['potential_reach']:,}", "followers of all accounts")
    kpi(k[1], "Peak 10-min window", fmt_t(p["peak_bucket"]))
    kpi(k[2], "Accounts", str(len(c["_cluster"]["account_ids"])))
    st.markdown("###### Account network — red: first posters · orange: top amplifiers")
    try:
        embed_html(network_html(c, df), 520)
    except Exception as exc:
        st.warning(f"Network graph unavailable: {exc}")
    st.dataframe(pd.DataFrame([{"Top amplifier": "@" + a["handle"], "Reposts received": a["reposts_received"],
                                "Copies of their text": a["copies_of_their_text"], "Followers": a["followers"],
                                "Evidence": ids(a["evidence_post_ids"])} for a in p["amplifiers"]]),
                 hide_index=True, width="stretch")


def c_changes(c: dict) -> None:
    wc = c["what_changed"]
    left, right = st.columns(2)
    with left:
        st.markdown(f"###### What changed since {fmt_t(wc['previous_cutoff'])}")
        if wc["is_new_campaign"]:
            st.info("New campaign — not present in the earlier snapshot.")
        elif not wc["items"]:
            st.caption("No change.")
        for it in wc["items"]:
            st.markdown(f"<div class='card'><h4>{esc(it['kind'].replace('_', ' ').title())}</h4>{esc(it['detail'])}"
                        f"<div class='ids'>{esc(ids(it['evidence_post_ids']))}</div></div>", unsafe_allow_html=True)
    with right:
        st.markdown("###### Planned gathering")
        pe = c["offline"]["planned_event"]
        if pe:
            (st.error if pe["hours_from_snapshot"] >= 0 else st.warning)(
                f"**{pe['place']}** · {_to_dt(pe['time']).strftime('%A %d %b, %H:%M IST')} — {countdown(pe)}  \n"
                f"Said as “{pe.get('time_phrase') or ''}” · evidence {ids(pe['evidence_post_ids'])}")
        else:
            st.caption("No place + time call to gather.")
        st.markdown("###### Offline incident matches")
        for m in c["offline"]["matches"]:
            st.markdown(f"<div class='card'><h4>{esc(m['incident_id'])} · {esc(m['confidence'])} · "
                        f"{m['time_delta_min']:+d} min vs first post</h4>{esc(m['incident'])}<br><i>{esc(m['note'])}</i>"
                        f"<div class='ids'>{esc(ids(m['evidence_post_ids']))}</div></div>", unsafe_allow_html=True)
        if not c["offline"]["matches"]:
            st.caption("No incident in the log matches this campaign.")


def c_legal(c: dict) -> None:
    if not c["legal"]:
        st.success("No legal sections — benign campaign.")
    else:
        st.warning("Suggested — requires legal officer review.")
    for l in c["legal"]:
        st.markdown(f"<div class='law'><b>{esc(l['act'])} {esc(l['section'])} — {esc(l['offence'])}</b> "
                    f"<span class='muted'>(page {esc(l['page'])} · basis: {esc(l['basis'])} · {l['posts']} posts)</span>"
                    f"<br>{esc(l['reason'])}<div class='ids'>{esc(ids(l['evidence_post_ids']))}</div></div>",
                    unsafe_allow_html=True)
    st.markdown("###### Recommended actions (cumulative up to the current state)")
    for a in c["actions"]:
        weight = "700" if a["state"] == c["state"] else "400"
        st.markdown(f"<div class='card' style='border-left:5px solid {STATE_COLOURS[a['state']]}'>"
                    f"<span style='font-weight:{weight}'>{esc(a['step'])}</span><div class='ids'>{a['state']} · "
                    f"because {a['because']} · {esc(ids(a['evidence_post_ids'], 3))}</div></div>", unsafe_allow_html=True)


def c_brief(c: dict, analyst: str) -> None:
    key = c["campaign_id"]
    st.caption("The brief is a printable police intelligence note. Paste an assessment drafted by IBM Bob "
               "(through the ThreatLens MCP tools), or leave it empty for the fact-only assessment.")
    text = st.text_area("Analyst assessment (optional)", key=f"assess_{key}", height=110)
    if st.button("Generate threat brief", type="primary", key=f"gen_{key}"):
        try:
            st.session_state[f"brief_{key}"] = render_brief(c, analyst, text or None)[:2]
        except Exception as exc:
            st.error(f"Could not render the brief: {exc}")
    if f"brief_{key}" in st.session_state:
        brief_id, html = st.session_state[f"brief_{key}"]
        st.download_button("Download brief (HTML — open and print to PDF)", html, file_name=f"{brief_id}.html",
                           mime="text/html", key=f"dl_{key}")
        embed_html(html, 640)
    st.markdown("###### Decision")
    cols = st.columns(3)
    for col, decision in zip(cols, ["Approve", "Escalate", "Dismiss"]):
        if col.button(decision, key=f"{decision}_{key}", width="stretch"):
            st.session_state.setdefault("log", []).append(
                {"time (IST)": datetime.now(IST).strftime("%H:%M:%S"), "campaign": key, "state": c["state"],
                 "decision": decision, "analyst": analyst})
    if st.session_state.get("log"):
        st.dataframe(pd.DataFrame(st.session_state["log"]), hide_index=True, width="stretch")


def view_campaigns(r: dict, df: pd.DataFrame, analyst: str) -> None:
    camps = r["campaigns"]
    if not camps:
        st.info("No coordinated campaign (5+ accounts acting together) in this window. Individual violations are "
                "listed under **Violations**.")
        return
    labels = {c["campaign_id"]: f"{c['campaign_id']} · {c['_main_hashtag']} · {c['label']} · {c['state']}" for c in camps}
    sel = st.selectbox("Campaign", list(labels), format_func=labels.get)
    c = next(x for x in camps if x["campaign_id"] == sel)
    tabs = st.tabs(["Summary", "Timeline & narrative", "Spread", "What changed & offline", "Legal & actions",
                    "Brief"])
    views = [lambda: c_overview(c), lambda: c_timeline(c, df), lambda: c_propagation(c, df), lambda: c_changes(c),
             lambda: c_legal(c), lambda: c_brief(c, analyst)]
    for tab, view in zip(tabs, views):
        with tab:
            try:
                view()
            except Exception as exc:
                st.error(f"This view failed: {exc}")


# ---------------------------------------------------------------------------
# Legal reference and data sources
# ---------------------------------------------------------------------------

def view_law() -> None:
    kb = load_kb()
    c1, c2 = st.columns([3, 1])
    q = c1.text_input("Search the official text", placeholder="e.g. enmity, intimidation, personation, 353")
    act = c2.selectbox("Act", ["Both", "BNS", "IT Act"], key="law_act")
    only = st.toggle("Only sections ThreatLens can apply to posts", value=not q)
    hits = [r for r in kb.values() if (act == "Both" or r["act"] == act)
            and (not only or (r["act"], r["section"]) in CANDIDATES)
            and (not q or q.lower() in (r["title"] + " " + r["text"] + " " + r["section"]).lower())]
    st.caption(f"{len(hits)} sections")
    for r in hits[:60]:
        note = EXCLUDED.get((r["act"], r["section"]))
        with st.expander(f"{r['act']} {r['section']} — {r['title'][:110]}" + ("  ⛔ not applicable" if note else "")):
            if note:
                st.error(note)
            st.write(r["text"])
            st.caption(f"Source: {r['source']} · PDF page {r['page']}")


def view_sources(r: dict | None) -> None:
    st.markdown("##### Where the data comes from")
    files = {f["file"]: f for f in source_files()}
    bns, it = files.get("bns_2023_gazette.pdf", {}), files.get("it_act_2000_updated.pdf", {})
    st.markdown(f"""
<table class='t'>
<tr><th>Data</th><th>Source</th><th>Authenticity</th></tr>
<tr><td><b>BNS 2023 section text</b></td><td>The Bharatiya Nyaya Sanhita, 2023 (Act No. 45 of 2023), <i>Gazette of India
Extraordinary</i>, Part II Section 1, No. 53, 25 Dec 2023, notification CG-DL-E-25122023-250883, Ministry of Law and Justice
(Legislative Department). File <code>law/sources/bns_2023_gazette.pdf</code>.</td>
<td>Official gazette PDF, text extracted verbatim by <code>law/build_kb.py</code>. SHA-256
<code>{bns.get('sha256', '')[:16]}…</code></td></tr>
<tr><td><b>IT Act 2000 section text</b></td><td>The Information Technology Act, 2000 (Act No. 21 of 2000), updated text as
amended (India Code / Legislative Department). File <code>law/sources/it_act_2000_updated.pdf</code>.</td>
<td>Official consolidated text, extracted verbatim. SHA-256 <code>{it.get('sha256', '')[:16]}…</code>. §66A is marked
not applicable (struck down, <i>Shreya Singhal v. Union of India</i>, 2015).</td></tr>
<tr><td><b>Bundled posts & incident log</b></td><td><code>sample_data/generate_mock.py</code> (seed 42): the 100-post
sample and the 522-post demo day.</td><td><b>Synthetic.</b> Every person, handle, community, district and URL is invented
(<code>.example</code> domains). Real users' posts are not redistributed, to protect privacy; load real data with
<b>Upload</b>.</td></tr>
<tr><td><b>Your uploads</b></td><td>Any JSON or CSV export (X, Facebook, Instagram, CrowdTangle-style, etc.).</td>
<td>Each post is hashed (SHA-256) exactly as uploaded, for chain of custody. Nothing is stored except the Bob
answer cache.</td></tr>
</table>""", unsafe_allow_html=True)
    st.markdown("##### Upload format")
    st.caption("Only a text column is required. Other columns are recognised by these names (case-insensitive):")
    st.dataframe(pd.DataFrame([{"Field": f, "Accepted column names": ", ".join(n)} for f, n in ALIASES.items()]),
                 hide_index=True, width="stretch")
    sample_csv = (SAMPLE_DATA / "sample_100_posts.csv").read_bytes()
    st.download_button("Download the 100-post sample as CSV (template)", sample_csv, file_name="sample_100_posts.csv",
                       mime="text/csv")
    st.markdown("##### How ThreatLens decides")
    st.markdown("""
1. **Every post → IBM Bob.** Bob Shell runs headless with an API key, with tools disabled and an empty workspace.
   It returns the violation types, severity, target, place and time, and the sections from a fixed catalogue of 23 BNS / IT Act
   offence sections. For each section it explains how the words of the post meet that section. Citations outside the
   catalogue are rejected. Answers are cached, so a re-run costs nothing.
2. **Coordination (no AI).** Accounts are linked by near-identical text (TF-IDF ≥ 0.80), reposts/replies, a shared
   link or image, and hashtag bursts. Groups of 5 or more accounts are campaigns, with a 0–100 coordination score.
3. **Campaign state (no AI).** DETECTED → COORDINATED → AMPLIFYING → ESCALATING → MOBILIZATION, each with a written trigger
   and the evidence posts. A benign campaign can never pass COORDINATED.
4. **Legal mapping per campaign.** Bob's per-post citations are aggregated. BNS 61 (conspiracy) and BNS 57
   (abetment by more than ten persons) are added by rule from the coordination evidence.
5. **Human in the loop.** Every legal output is a suggestion for a legal officer; actions need an analyst decision.
""")
    if r and st.session_state.get("sample"):
        with st.expander("Evaluation against the answer key (bundled data only)"):
            ak = json.loads((SAMPLE_DATA / "answer_key.json").read_text(encoding="utf-8"))
            present = set(st.session_state["df"]["account_id"])
            for g in ak.values():
                g["account_ids"] = [a for a in g["account_ids"] if a in present]
            ev = evaluate(r, ak)
            o = ev["overall"]
            k = st.columns(4)
            kpi(k[0], "Mean account F1", f"{o['mean_f1']:.2f}")
            kpi(k[1], "Label accuracy", f"{o['label_accuracy']:.0%}")
            kpi(k[2], "State accuracy", f"{o['state_accuracy']:.0%}")
            kpi(k[3], "False-alarm campaigns", str(len(o["false_alarm_campaigns"])))
            st.dataframe(pd.DataFrame(ev["per_group"]), hide_index=True, width="stretch")
            s1 = ak.get("S1", {}).get("expected_categories", {})
            if s1:
                rows = [{"post": p, "expected": ", ".join(exp),
                         "found": ", ".join(r["violations"].get(p, {}).get("categories", [])),
                         "flagged": r["violations"].get(p, {}).get("violation", False)}
                        for p, exp in s1.items() if p in r["violations"]]
                st.markdown("Standalone violations (expected vs found)")
                st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
            st.caption("Scores on synthetic data show that the logic works as designed, not real-world accuracy.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    hero()
    opts = control_panel()
    if opts and (opts["run"] or ("result" not in st.session_state and opts["sample"])):
        run_analysis(opts)
    r = st.session_state.get("result")
    df = st.session_state.get("df")
    tabs = st.tabs(["Overview", "Violations", "Campaigns", "Legal reference", "Data & sources"])
    with tabs[3]:
        view_law()
    with tabs[4]:
        view_sources(r)
    if not r:
        with tabs[0]:
            st.info("Choose data above and press **Analyse**.")
        return
    analyst = opts["analyst"] if opts else "Inspector Demo"
    for tab, view in zip(tabs[:3], [lambda: view_overview(r), lambda: view_violations(r, df),
                                   lambda: view_campaigns(r, df, analyst)]):
        with tab:
            try:
                view()
            except Exception as exc:
                st.error(f"This view failed: {exc}")
    st.caption(f"Analysed: {st.session_state.get('data_name')} · up to {fmt_t(r['current_cutoff'])}, compared with "
               f"{fmt_t(r['previous_cutoff'])} · generated {fmt_t(r['generated_at'])} IST. "
               "ThreatLens flags behaviour and content, never identity. All outputs require human review.")


main()
