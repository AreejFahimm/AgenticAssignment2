"""R&D question A: does tool granularity change agent behaviour?  40 tasks with known correct calls, three tool designs.

    python -m evals.runners.tool_granularity            # offline: embedding selector over tool names+descriptions
    python -m evals.runners.tool_granularity --llm      # needs LLM_BASE_URL + MODEL_PROFILE=open (NOT run for the committed results)

Designs: FINE (many one-purpose tools, terse descriptions), COARSE (3 mega-tools taking an `action` string),
BEST (the shipped tool set with rewritten, task-oriented descriptions).
Metrics: tool-selection accuracy, argument accuracy (LLM mode only: the offline selector cannot fill arguments),
and tokens per task (size of the tool list that must be placed in the prompt: chars/4 approximation).
HONEST SCOPE: the offline mode measures how well tool NAMES+DESCRIPTIONS separate tasks (a necessary condition for good selection); it
is not agent behaviour. Hypothesis written before running: BEST >= FINE > COARSE on selection accuracy; COARSE uses the fewest tokens.
"""
from __future__ import annotations

import argparse
import json

import numpy as np

from evals.runners._harness import ROOT

# (task text, correct tool in the BEST design, expected key args)
TASKS = [
    ("What is my Connects balance right now?", "get_connects_balance", {}),
    ("How many Connects do I have left this week?", "get_connects_balance", {}),
    ("Find jobs about React dashboards", "search_jobs", {"query": "react dashboard"}),
    ("Search the marketplace for data cleaning gigs", "search_jobs", {"query": "data cleaning"}),
    ("Look for new Django API jobs", "search_jobs", {"query": "django api"}),
    ("Show me the full details of job job-123", "get_job", {"job_id": "job-123"}),
    ("Open job job-abc and read the description", "get_job", {"job_id": "job-abc"}),
    ("Is the client client-77 payment verified?", "get_client_history", {"client_id": "client-77"}),
    ("How much has client client-9 spent in the past?", "get_client_history", {"client_id": "client-9"}),
    ("What is the rating and hire rate of client client-5?", "get_client_history", {"client_id": "client-5"}),
    ("Has the client replied on proposal prop-1?", "list_messages", {"proposal_id": "prop-1"}),
    ("Show the conversation on proposal prop-42", "list_messages", {"proposal_id": "prop-42"}),
    ("List all my proposals and their status", "list_proposals", {}),
    ("Which of my proposals got a reply?", "list_proposals", {}),
    ("What are the platform's current rules and Connects cost?", "get_platform_policy", {}),
    ("Is there a minimum cover letter length on this platform?", "get_platform_policy", {}),
    ("Save a draft proposal for job job-1 at 120 dollars", "create_proposal_draft", {"job_id": "job-1", "bid_amount": 120}),
    ("Create a proposal draft for job job-8 with my cover letter", "create_proposal_draft", {"job_id": "job-8"}),
    ("Preview what would be sent for job job-2 without sending", "create_proposal_draft", {"job_id": "job-2", "dry_run": True}),
    ("Submit proposal prop-7 now that I approved it", "submit_proposal", {"proposal_id": "prop-7"}),
    ("Send the approved proposal prop-3 and spend the Connects", "submit_proposal", {"proposal_id": "prop-3"}),
    ("Send this reply to the client on prop-5: thanks, Tuesday works", "send_message", {"proposal_id": "prop-5"}),
    ("Message the client on proposal prop-6 saying I can start Monday", "send_message", {"proposal_id": "prop-6"}),
    ("Find evidence that I have used Docker in production", "search_evidence", {"requirement": "docker production"}),
    ("What have I built with PyTorch?", "search_evidence", {"requirement": "pytorch"}),
    ("Do I have any projects in the healthcare industry?", "search_evidence", {"requirement": "healthcare industry"}),
    ("Prove I can build Stripe payment flows", "search_evidence", {"requirement": "stripe payments"}),
    ("Show the full write-up of case study web-p03a", "get_case_study", {"id": "web-p03a"}),
    ("Load case study ai_-p01b in full", "get_case_study", {"id": "ai_-p01b"}),
    ("Which skills do I have and how well are they backed by work?", "list_skills", {}),
    ("List my skills with evidence counts", "list_skills", {}),
    ("When am I free for an interview this week?", "free_calendar_slots", {"days": 5}),
    ("Give me open 30-minute slots in the next three days", "free_calendar_slots", {"days": 3}),
    ("Offer the client interview slots", "free_calendar_slots", {}),
    ("Put a tentative hold on Tuesday 10:00 for the interview", "create_tentative_hold", {}),
    ("Block 2026-11-17T10:00 tentatively for the client call", "create_tentative_hold", {"start_iso": "2026-11-17T10:00"}),
    ("Write an email draft to client@example.com about next steps", "create_email_draft", {"to": "client@example.com"}),
    ("Draft an email reply thanking them (do not send)", "create_email_draft", {}),
    ("Prepare an email to the hiring manager with my availability", "create_email_draft", {}),
    ("Check whether job job-55 is still open and its budget", "get_job", {"job_id": "job-55"}),
]

BEST_DESC = {
    "search_jobs": "Search marketplace jobs by free-text keywords. Use to discover new jobs matching a topic.",
    "get_job": "Get one job by id: title, description, budget, required skills, Connects cost.",
    "get_client_history": "Get a client's trust signals: payment verified, rating, total spend, hire rate, completed projects.",
    "get_connects_balance": "Get how many Connects the user has left to spend on proposals.",
    "list_messages": "List the messages on one proposal thread (client replies and our messages).",
    "list_proposals": "List all of the user's proposals with their current status (submitted, viewed, replied, interview, hired).",
    "get_platform_policy": "Get the marketplace's current platform rules: Connects cost, minimum cover letter length, daily limits.",
    "create_proposal_draft": "Create a proposal DRAFT for a job (does not spend Connects). dry_run=true previews exactly what would be sent.",
    "submit_proposal": "SUBMIT an approved draft proposal and spend Connects. Only after human approval.",
    "send_message": "SEND a message to a client on a proposal thread. Only after human approval.",
    "search_evidence": "Search the freelancer's portfolio for evidence that proves ONE job requirement (projects, outcomes, repos).",
    "get_case_study": "Load the full Markdown of one case study by its id.",
    "list_skills": "List every skill in the portfolio with how many evidence items support it.",
    "free_calendar_slots": "List free 30-minute interview slots in the next N days.",
    "create_tentative_hold": "Create a TENTATIVE calendar hold for an interview (does not invite anyone).",
    "create_email_draft": "Create an email DRAFT (never sends).",
}
FINE = {  # one-purpose, terse, overlapping names (the "many fine-grained tools" arm)
    "jobs_search_keyword": "search jobs", "jobs_search_budget": "search jobs by budget", "jobs_get_title": "get job title", "jobs_get_description": "get job description",
    "jobs_get_budget": "get job budget", "jobs_get_skills": "get job skills", "jobs_get_connects": "get job connects cost", "clients_get_rating": "get client rating",
    "clients_get_spend": "get client total spend", "clients_get_verified": "get client payment verified", "clients_get_hire_rate": "get client hire rate",
    "account_get_balance": "get balance", "messages_list": "list messages", "messages_send": "send message", "proposals_list": "list proposals",
    "proposals_get_status": "get proposal status", "proposals_create": "create proposal", "proposals_dry_run": "preview proposal", "proposals_submit": "submit proposal",
    "policy_get_connects": "get connects policy", "policy_get_limits": "get limits policy", "portfolio_search": "search portfolio", "portfolio_get_case": "get case study",
    "portfolio_skills": "list skills", "calendar_slots": "free slots", "calendar_hold": "create hold", "email_draft": "create email draft",
}
FINE_MAP = {"search_jobs": "jobs_search_keyword", "get_job": "jobs_get_description", "get_client_history": "clients_get_rating", "get_connects_balance": "account_get_balance",
            "list_messages": "messages_list", "list_proposals": "proposals_list", "get_platform_policy": "policy_get_connects", "create_proposal_draft": "proposals_create",
            "submit_proposal": "proposals_submit", "send_message": "messages_send", "search_evidence": "portfolio_search", "get_case_study": "portfolio_get_case",
            "list_skills": "portfolio_skills", "free_calendar_slots": "calendar_slots", "create_tentative_hold": "calendar_hold", "create_email_draft": "email_draft"}
# acceptable alternatives in the FINE design (several fine tools legitimately answer one task)
FINE_OK = {"get_job": {"jobs_get_title", "jobs_get_description", "jobs_get_budget", "jobs_get_skills", "jobs_get_connects", "jobs_search_keyword"},
           "get_client_history": {"clients_get_rating", "clients_get_spend", "clients_get_verified", "clients_get_hire_rate"},
           "get_platform_policy": {"policy_get_connects", "policy_get_limits"}, "create_proposal_draft": {"proposals_create", "proposals_dry_run"},
           "list_proposals": {"proposals_list", "proposals_get_status"}}
COARSE = {"marketplace": "Marketplace operations. Pass an action name and parameters.", "portfolio": "Portfolio operations. Pass an action name and parameters.",
          "workspace": "Workspace operations. Pass an action name and parameters."}
SERVER_OF = {**{t: "marketplace" for t in ("search_jobs", "get_job", "get_client_history", "get_connects_balance", "list_messages", "list_proposals", "get_platform_policy",
                                           "create_proposal_draft", "submit_proposal", "send_message")},
             **{t: "portfolio" for t in ("search_evidence", "get_case_study", "list_skills")},
             **{t: "workspace" for t in ("free_calendar_slots", "create_tentative_hold", "create_email_draft")}}


def tokens(tools: dict[str, str]) -> int:
    return sum(len(f"{n}: {d}") for n, d in tools.items()) // 4


def embed_select(tools: dict[str, str], tasks: list[str]) -> list[str]:
    from rag.index.store import embed_docs, embed_query
    names = list(tools)
    d = embed_docs([f"{n.replace('_', ' ')}: {tools[n]}" for n in names])
    return [names[int(np.argmax(d @ embed_query(t)))] for t in tasks]


def main(use_llm: bool) -> dict:
    texts = [t[0] for t in TASKS]
    out = {}
    designs = {"fine": FINE, "coarse": COARSE, "best": BEST_DESC}
    for name, tools in designs.items():
        if use_llm:
            raise NotImplementedError("LLM mode: implement with agent.llm.complete_json using the tool list; not run for the committed results")
        pred = embed_select(tools, texts)
        correct = 0
        for (txt, gold, _), p in zip(TASKS, pred):
            if name == "best":
                correct += p == gold
            elif name == "fine":
                correct += p in FINE_OK.get(gold, {FINE_MAP[gold]}) | {FINE_MAP[gold]}
            else:
                correct += p == SERVER_OF[gold]
        out[name] = dict(n_tools=len(tools), selection_accuracy=round(correct / len(TASKS), 4), tokens_per_task=tokens(tools),
                         argument_accuracy=None if not use_llm else "n/a",
                         note="coarse: server-level accuracy only; the action argument is not measurable offline" if name == "coarse" else "")
    return dict(mode="llm" if use_llm else "offline-embedding-selector", n_tasks=len(TASKS), designs=out,
                caveat="measures description discriminability, not agent behaviour; argument accuracy requires an LLM run (not done)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--llm", action="store_true")
    a = ap.parse_args()
    res = main(a.llm)
    print(json.dumps(res, indent=2))
    (ROOT / "evals" / "results" / "tool_granularity.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
