"""Synthetic job generator, used ONLY to fill gaps / as an offline fallback when Kaggle data is absent.

Every job is tagged provenance=synthetic:synth_jobs:<seed>. Never present these as real.
"""
from __future__ import annotations

from common import PERSONA_SKILLS, SEED, categorize, rng, stable_id

TEMPLATES = {
    "ai_ml_engineer": [
        ("Build a {s0} classifier for {dom} data", "We need a reproducible {s0} baseline on tabular {dom} data. Compare at least two models, report precision/recall and document limitations. Experience with {s1} preferred."),
        ("{s0} chatbot for {dom} support", "Looking for an engineer to build a {s0} based assistant over our {dom} documents using {s1}. Must include evaluation of answer quality and a short handover doc."),
        ("Fine-tune a {s0} model for {dom} text", "We have labelled {dom} text and want a fine-tuned model using {s0} and {s1}. Deliver training code, metrics and a small API."),
        ("Machine learning pipeline for {dom}", "Detect patterns in {dom} data. Skills: {s0}, {s1}. Provide a notebook and a Dockerised inference service."),
    ],
    "fullstack_web_dev": [
        ("{s0} web app for {dom} startup", "Build an MVP web app with {s0} and {s1}: auth, dashboard, and a payments flow. Clean code and a deployment guide are required."),
        ("Fix and extend our {s0} {dom} website", "Existing {s0} project needs bug fixes, a new {s1} integration and responsive layout for the {dom} product."),
        ("REST API and admin panel in {s0}", "Design a {s0} backend with {s1}, role-based access and tests for a {dom} business."),
        ("Landing page + CMS using {s0}", "Marketing website for a {dom} company using {s0} and {s1}, SEO basics, fast on mobile."),
    ],
    "data_analyst": [
        ("{s0} dashboard for {dom} KPIs", "Create an interactive {s0} dashboard from our {dom} data (CSV and {s1}). Weekly refresh and a one-page metric glossary."),
        ("Clean and analyse {dom} survey data", "Messy {dom} spreadsheets need cleaning, analysis in {s0}/{s1}, and a short report with recommendations."),
        ("ETL and reporting pipeline with {s0}", "Automate monthly {dom} reporting: extract with {s0}, transform with {s1}, deliver a scheduled report."),
        ("A/B test analysis for {dom} product", "Analyse experiment results using {s0} and {s1}; report significance, effect sizes and caveats. Dashboard optional."),
    ],
}
DOMAINS = ["healthcare", "retail", "fintech", "logistics", "education", "real estate", "travel", "e-commerce", "SaaS", "media"]


def gen_jobs(n_per_persona: int = 400, salt: str = "base") -> list[dict]:
    r = rng(f"jobs:{salt}")
    out = []
    for persona, tmpls in TEMPLATES.items():
        skills = PERSONA_SKILLS[persona]
        for i in range(n_per_persona):
            t_title, t_desc = r.choice(tmpls)
            s0, s1 = r.sample(skills, 2)
            dom = r.choice(DOMAINS)
            title = t_title.format(s0=s0, s1=s1, dom=dom)
            desc = t_desc.format(s0=s0, s1=s1, dom=dom)
            hourly = r.random() < 0.4
            base = {"ai_ml_engineer": 35, "fullstack_web_dev": 28, "data_analyst": 22}[persona]
            if hourly:
                lo = round(base * r.uniform(0.6, 1.2))
                hi = round(lo * r.uniform(1.2, 1.8))
                budget = {"type": "hourly", "min": lo, "max": hi, "currency": "USD"}
            else:
                lo = round(base * r.uniform(6, 20) / 10) * 10
                budget = {"type": "fixed", "min": lo, "max": round(lo * r.uniform(1.2, 2.0) / 10) * 10, "currency": "USD"}
            full = f"{title}. {desc}"
            out.append({
                "job_id": stable_id("job", "synth", salt, persona, str(i)),
                "title": title, "description": desc,
                "required_skills": [s0, s1], "category": categorize(full),
                "budget": budget, "country": r.choice(["US", "UK", "CA", "AU", "DE", "AE"]),
                "posted_at": f"2024-{r.randint(1, 12):02d}-{r.randint(1, 28):02d}",
                "source": "synthetic", "provenance": f"synthetic:synth_jobs:{SEED}",
                "target_persona": persona,
            })
    return out
