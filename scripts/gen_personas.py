"""Generate the three SYNTHETIC freelancer personas (template-based, deterministic, seeded).

Outputs under data/personas/<persona_id>/ :
  profile.json, cv.md, case_studies/*.md, repos/<name>/README.md (+ code snippet), reviews.json,
  proposals.jsonl (~150 past proposals labelled won / replied / ignored), evidence.jsonl (flat index).

Everything is provenance=synthetic:gen_personas:<seed>. The same project is described three ways
(case study, repo README, client review) and some skills are only IMPLIED, on purpose, to stress RAG.
Outcome labels follow a documented rule (see outcome_probs) -- they are NOT LLM opinions.
"""
from __future__ import annotations

import sys

from common import PERSONA_SKILLS, PERSONAS, PROCESSED, SEED, read_jsonl, rng, stable_id, write_json, write_jsonl

PROV = f"synthetic:gen_personas:{SEED}"

PROFILES = {
    "ai_ml_engineer": dict(name="Alex Morgan", headline="AI/ML Engineer (NLP and applied ML)", rate=35, floor_fixed=300, years=4,
                           stack=["python", "pytorch", "scikit-learn", "langchain", "rag", "fastapi", "docker"]),
    "fullstack_web_dev": dict(name="Sam Rivera", headline="Full-stack Web Developer (React / Node / Django)", rate=30, floor_fixed=250, years=5,
                              stack=["react", "next.js", "typescript", "node.js", "django", "postgresql", "docker"]),
    "data_analyst": dict(name="Jordan Lee", headline="Data Analyst (SQL, BI dashboards, experimentation)", rate=24, floor_fixed=150, years=3,
                         stack=["sql", "power bi", "tableau", "python", "pandas", "excel", "dbt"]),
}
INDUSTRIES = ["healthcare", "retail", "fintech", "logistics", "education", "real estate", "travel", "e-commerce", "SaaS", "media"]

PROJECTS = {
    "ai_ml_engineer": [
        ("Support ticket classifier", ["python", "scikit-learn", "nlp", "classification"], "Cut manual triage time by {m}% using a TF-IDF + logistic regression baseline, then a fine-tuned transformer."),
        ("Document Q&A assistant", ["python", "langchain", "rag", "llm", "fastapi"], "Built retrieval-augmented Q&A over {n} internal documents; answer accuracy {m}% on a 100-question review set."),
        ("Churn prediction pipeline", ["python", "scikit-learn", "machine learning", "classification"], "Compared logistic regression and gradient boosting; recall improved to {m}% on the held-out month."),
        ("Defect detection in images", ["python", "pytorch", "computer vision", "docker"], "Trained a CNN on {n} labelled images; shipped a Dockerised inference API."),
        ("Demand forecasting", ["python", "time series", "pandas", "scikit-learn"], "Weekly forecasts with MAPE {m}% versus a naive seasonal baseline."),
        ("Product recommendation engine", ["python", "recommendation", "pytorch"], "Implemented matrix factorisation; click-through uplift of {m}% in an A/B test."),
        ("Sentiment analysis service", ["python", "nlp", "huggingface", "fastapi"], "Multilingual sentiment API handling {n} requests/day at p95 under 200ms."),
        ("MLOps retraining workflow", ["python", "mlops", "docker", "fastapi"], "Automated weekly retraining and model registry; deploy time reduced by {m}%."),
        ("Resume screening assistant", ["python", "llm", "openai", "nlp"], "LLM-assisted screening with human review; agreement with recruiters {m}%."),
        ("Anomaly detection for transactions", ["python", "scikit-learn", "machine learning"], "Isolation-forest alerts reviewed by analysts; precision {m}% at fixed recall."),
        ("Voice-of-customer topic mining", ["python", "nlp", "pandas"], "Clustered {n} reviews into actionable topics for the product team."),
        ("Chatbot for appointment booking", ["python", "chatbot", "llm", "fastapi"], "Reduced front-desk call volume by {m}% with a guarded booking assistant."),
    ],
    "fullstack_web_dev": [
        ("SaaS subscription dashboard", ["react", "typescript", "node.js", "postgresql", "stripe"], "Shipped auth, billing and usage dashboards; onboarding completion up {m}%."),
        ("E-commerce storefront", ["next.js", "typescript", "stripe", "tailwind"], "Headless storefront with {n} SKUs; Lighthouse performance {m}+ on mobile."),
        ("Booking platform API", ["django", "postgresql", "rest api", "docker"], "REST API with role-based access and {n} automated tests; zero double-bookings in production."),
        ("Internal admin panel", ["react", "node.js", "postgresql"], "Replaced spreadsheets with an admin panel; ops time saved {m}%."),
        ("Marketing site with CMS", ["next.js", "tailwind", "html", "css"], "Content team publishes without developers; page load under 1.5s."),
        ("Real-time chat feature", ["node.js", "javascript", "mongodb"], "WebSocket chat for {n} concurrent users with message persistence."),
        ("Shopify theme customisation", ["shopify", "javascript", "css"], "Custom theme sections; conversion rate up {m}%."),
        ("GraphQL gateway", ["graphql", "node.js", "typescript"], "Unified {n} microservices behind one typed gateway."),
        ("WordPress migration", ["wordpress", "css", "html"], "Migrated {n} pages with SEO redirects and no ranking loss."),
        ("AWS deployment pipeline", ["aws", "docker", "node.js"], "CI/CD with blue-green deploys; release time reduced by {m}%."),
        ("Flask microservice for reports", ["flask", "postgresql", "rest api"], "Scheduled PDF reports for {n} clients."),
        ("Vue progressive web app", ["vue", "javascript", "css"], "Offline-capable PWA used by {n} field staff."),
    ],
    "data_analyst": [
        ("Executive KPI dashboard", ["power bi", "sql", "dashboard", "data visualization"], "Single source of truth for {n} KPIs; weekly review time cut by {m}%."),
        ("Sales funnel analysis", ["sql", "tableau", "excel"], "Identified a {m}% drop-off step; fix recovered revenue."),
        ("Survey data cleaning and report", ["python", "pandas", "data cleaning", "excel"], "Cleaned {n} responses; reproducible notebook and summary deck."),
        ("Marketing attribution reporting", ["google analytics", "sql", "looker"], "Channel-level ROI report refreshed daily."),
        ("A/B test analysis toolkit", ["python", "statistics", "a/b testing"], "Standardised significance and power checks across {n} experiments."),
        ("ETL pipeline for finance reports", ["sql", "etl", "dbt", "bigquery"], "Automated monthly close reports; manual hours down {m}%."),
        ("Inventory turnover dashboard", ["tableau", "sql", "reporting"], "Highlighted slow movers across {n} SKUs."),
        ("Customer segmentation", ["python", "pandas", "statistics"], "RFM segments adopted by the CRM team; email revenue up {m}%."),
        ("Google Sheets automation", ["google sheets", "excel", "reporting"], "Replaced {n} manual copy-paste steps with scripted refreshes."),
        ("HR attrition analysis", ["sql", "python", "data visualization"], "Surfaced top drivers; retention plan targeted {m}% of at-risk staff."),
        ("Web data collection (public APIs)", ["python", "web scraping", "pandas"], "Collected public dataset through an official API with documented limits."),
        ("Cohort retention study", ["sql", "statistics", "dashboard"], "Month-3 retention curve by acquisition channel."),
    ],
}


def build_projects(persona: str):
    r = rng(f"proj:{persona}")
    items = []
    for i, (name, skills, tmpl) in enumerate(PROJECTS[persona]):
        # two variants of each project -> 24 case studies (15..25 required)
        for v in range(2):
            ind = r.choice(INDUSTRIES)
            m, n = r.randint(12, 45), r.choice([300, 1200, 5000, 20000])
            year = r.randint(2021, 2024)
            items.append(dict(
                pid=f"{persona[:3]}-p{i:02d}{'ab'[v]}", name=name + (f" for a {ind} client" if v else f" ({ind})"),
                skills=skills, industry=ind, year=year, summary=tmpl.format(m=m, n=n), m=m, n=n,
                outcome=r.choice(["delivered on time", "client renewed contract", "client left 5-star review", "handed over with docs"]),
            ))
    return items


def case_study_md(persona: str, p: dict) -> str:
    return (f"# {p['name']}\n\n**Industry:** {p['industry']}  \n**Year:** {p['year']}  \n"
            f"**Skills:** {', '.join(p['skills'])}  \n**Outcome:** {p['outcome']}\n\n"
            f"## Summary\n{p['summary']}\n\n## What I did\nScoped the problem with the client, built the first version in week 1, "
            f"iterated on feedback and documented the handover. Provenance: {PROV}.\n")


def readme_md(p: dict) -> str:
    # Deliberately describes the same project differently and only IMPLIES some skills.
    implied = p["skills"][-1]
    return (f"# {p['name'].split(' for ')[0].lower().replace(' ', '-')}\n\nInternal tooling for a {p['industry']} team.\n\n"
            f"## Usage\n`make run` then open the local app. Dependencies are pinned in the lockfile.\n\n"
            f"## Notes\nThe core uses {', '.join(p['skills'][:-1]) or 'standard tooling'}; "
            f"deployment bits relate to {implied} in `infra/`.\n")


def code_snippet(p: dict) -> str:
    return f'"""{p["name"]} - core module (synthetic example)."""\n\n\ndef main():\n    # skills touched: {", ".join(p["skills"])}\n    return "ok"\n'


def reviews(persona: str, projects: list[dict]) -> list[dict]:
    r = rng(f"rev:{persona}")
    out = []
    for p in r.sample(projects, 10):
        out.append(dict(review_id=stable_id("rev", persona, p["pid"]), project_id=p["pid"], rating=r.choice([4.5, 5.0, 5.0, 4.0]),
                        text=f"Great work on the {p['name'].split(' for ')[0].lower()} project. Communicative, delivered what was agreed, and the result held up in production.",
                        provenance=PROV))
    return out


def outcome_probs(overlap: float, specific: bool, price_ratio: float, generic: bool) -> tuple[float, float]:
    """Documented rule for past-proposal outcomes (assumed priors; NOT calibrated on real outcome data).
    Returns (p_reply, p_win_given_reply)."""
    p_reply = 0.10 + 0.35 * overlap + (0.12 if specific else 0) - (0.10 if generic else 0)
    p_reply -= 0.15 * max(0.0, price_ratio - 1.3)
    p_win = 0.08 + 0.12 * overlap
    return max(0.02, min(p_reply, 0.8)), max(0.03, min(p_win, 0.4))


def gen_proposals(persona: str, projects: list[dict], jobs: list[dict], n: int = 150) -> list[dict]:
    r = rng(f"prop:{persona}")
    pool = [j for j in jobs if j.get("target_persona") == persona]
    r.shuffle(pool)
    pool = pool[: n]  # "past" slice; dev set draws from the REMAINING jobs (see build_dev_set)
    skills = set(PERSONA_SKILLS[persona])
    out = []
    for j in pool:
        req = set(j["required_skills"])
        overlap = len(req & skills) / max(len(req), 1)
        generic = r.random() < 0.35
        proj = r.choice(projects)
        cites = [] if generic else [proj["pid"]]
        specific = not generic
        text = ("Hello, I am a hard-working professional and I can do this job. Please hire me."
                if generic else
                f"Hi - your post about {j['title'].lower()} matches work I did on '{proj['name']}' ({proj['year']}): {proj['summary']} "
                f"Happy to share how I would approach yours.")
        price_ratio = r.uniform(0.7, 1.6)
        p_reply, p_win = outcome_probs(overlap, specific, price_ratio, generic)
        u = r.random()
        outcome = "ignored"
        if u < p_reply:
            outcome = "won" if r.random() < p_win else "replied"
        out.append(dict(proposal_id=stable_id("prop", persona, j["job_id"]), persona=persona, job_id=j["job_id"],
                        job_title=j["title"], category=j["category"], text=text, cited_project_ids=cites,
                        bid_ratio_to_market=round(price_ratio, 2), outcome=outcome, provenance=PROV))
    return out


def main() -> int:
    jobs = read_jsonl(PROCESSED / "jobs.jsonl")
    for persona, prof in PROFILES.items():
        d = PERSONAS / persona
        projects = build_projects(persona)
        evidence = []
        for p in projects:
            (d / "case_studies").mkdir(parents=True, exist_ok=True)
            (d / "case_studies" / f"{p['pid']}.md").write_text(case_study_md(persona, p), encoding="utf-8")
            if int(p["pid"][-3:-1]) % 2 == 0 and p["pid"].endswith("a"):  # repos for a subset
                rd = d / "repos" / p["pid"]
                rd.mkdir(parents=True, exist_ok=True)
                (rd / "README.md").write_text(readme_md(p), encoding="utf-8")
                (rd / "main.py").write_text(code_snippet(p), encoding="utf-8")
                evidence.append(dict(evidence_id=f"{p['pid']}:readme", project_id=p["pid"], type="repo_readme", text=readme_md(p),
                                     skills=p["skills"][:-1], industry=p["industry"], date=str(p["year"]), outcome=None, provenance=PROV))
                evidence.append(dict(evidence_id=f"{p['pid']}:code", project_id=p["pid"], type="code", text=code_snippet(p),
                                     skills=p["skills"], industry=p["industry"], date=str(p["year"]), outcome=None, provenance=PROV))
            evidence.append(dict(evidence_id=p["pid"], project_id=p["pid"], type="case_study", text=f"{p['name']}. {p['summary']}",
                                 skills=p["skills"], industry=p["industry"], date=str(p["year"]), outcome=p["outcome"], provenance=PROV))
        revs = reviews(persona, projects)
        write_json(d / "reviews.json", revs)
        for rv in revs:
            pr = next(x for x in projects if x["pid"] == rv["project_id"])
            evidence.append(dict(evidence_id=rv["review_id"], project_id=rv["project_id"], type="review", text=rv["text"],
                                 skills=[], industry=pr["industry"], date=str(pr["year"]), outcome=f"rating {rv['rating']}", provenance=PROV))
        props = gen_proposals(persona, projects, jobs)
        write_jsonl(d / "proposals.jsonl", props)
        for pr in props:
            evidence.append(dict(evidence_id=pr["proposal_id"], project_id=None, type="past_proposal", text=pr["text"], skills=[],
                                 industry=None, date=None, outcome=pr["outcome"], provenance=PROV))
        write_jsonl(d / "evidence.jsonl", evidence)
        write_json(d / "profile.json", dict(persona_id=persona, display_name=prof["name"] + " (synthetic)", headline=prof["headline"],
                                            skills=PERSONA_SKILLS[persona], core_stack=prof["stack"], hourly_rate_usd=prof["rate"],
                                            minimum_project_budget_usd=prof["floor_fixed"], years_experience=prof["years"],
                                            provenance=PROV))
        (d / "cv.md").write_text(
            f"# {prof['name']} (synthetic)\n{prof['headline']}\n\n## Skills\n{', '.join(PERSONA_SKILLS[persona])}\n\n"
            f"## Experience\n{prof['years']} years. Selected projects:\n" + "\n".join(f"- {p['name']} ({p['year']}): {p['summary']}" for p in projects[:10])
            + f"\n\nProvenance: {PROV}\n", encoding="utf-8")
        from collections import Counter
        c = Counter(p["outcome"] for p in props)
        print(f"{persona}: {len(projects)} case studies, {len(props)} proposals {dict(c)}, {len(evidence)} evidence items")
    return 0


if __name__ == "__main__":
    sys.exit(main())
