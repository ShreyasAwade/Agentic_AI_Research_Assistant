
import os
import time
import operator
from typing import TypedDict, Annotated, List

from dotenv import load_dotenv
from langgraph.graph import StateGraph, END
from langchain_groq import ChatGroq

from ddgs import DDGS


# ============================================================
# 1. CONFIGURATION
# ============================================================

load_dotenv()

MAX_LOOPS = 3
MAX_RESULTS_PER_QUERY = 5
SEARCH_RETRIES = 2

llm = ChatGroq(
    model=os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"),
    temperature=0.2,
)


# ============================================================
# 2. STATE DEFINITION
# ============================================================

class ResearchState(TypedDict):
    topic: str
    queries: List[str]
    search_results: Annotated[List[dict], operator.add]
    report: str
    loop_count: int
    logs: Annotated[List[str], operator.add]
    needs_more_research: bool


# ============================================================
# 3. HELPER FUNCTIONS
# ============================================================

def log_message(message: str) -> List[str]:
    """Create a log entry for the research workflow."""
    print(f"[AGENT] {message}")
    return [message]


def get_response_text(response) -> str:
    """Safely extract text from an LLM response."""
    content = response.content

    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        parts = []

        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and item.get("text"):
                parts.append(item["text"])

        return "\n".join(parts).strip()

    return str(content).strip()


def clean_queries(text: str) -> List[str]:
    """Convert an LLM response into a list of search queries."""
    queries = []

    for line in text.splitlines():
        line = line.strip()

        if not line:
            continue

        # Remove common list markers and numbering.
        line = line.lstrip("-*• ").strip()

        while line and line[0].isdigit():
            line = line[1:]

        line = line.lstrip(".)-: ").strip()

        if line:
            queries.append(line)

    # Remove duplicate queries while preserving order.
    return list(dict.fromkeys(queries))


# ============================================================
# 4. PLANNER NODE
# ============================================================

def planner(state: ResearchState) -> dict:
    """Generate focused search queries for the research topic."""

    topic = state["topic"]

    logs = log_message(
        f"Planning research for topic: {topic}"
    )

    try:
        response = llm.invoke(
            f"""
You are an expert research planner.

Research topic:
{topic}

Generate exactly 3 distinct web search queries.

Requirements:
- Cover different important aspects of the topic.
- Prefer specific, factual and research-oriented queries.
- Make the queries useful for finding reliable sources.
- Return only the queries, one per line.
- Do not include numbering or explanations.
"""
        )

        queries = clean_queries(get_response_text(response))[:3]

    except Exception as exc:
        queries = []

        logs.extend(
            log_message(
                f"Planner error: {exc}. Using fallback queries."
            )
        )

    if not queries:
        queries = [
            topic,
            f"{topic} benefits risks and challenges",
            f"{topic} recent developments and evidence",
        ]

    logs.extend(
        log_message(
            f"Planner created {len(queries)} search queries."
        )
    )

    return {
        "queries": queries,
        "logs": logs,
    }


# ============================================================
# 5. WEB SEARCH NODE
# ============================================================

def search_web(state: ResearchState) -> dict:
    """Search DuckDuckGo and collect results with source URLs."""

    results = []
    logs = []

    existing_urls = {
        item.get("url")
        for item in state.get("search_results", [])
        if item.get("url")
    }

    for query in state.get("queries", []):
        logs.extend(
            log_message(f"Searching: {query}")
        )

        search_succeeded = False

        for attempt in range(1, SEARCH_RETRIES + 1):
            try:
                search_results = list(
                    DDGS().text(
                        query,
                        max_results=MAX_RESULTS_PER_QUERY,
                    )
                )

                for item in search_results:
                    url = item.get("href") or item.get("url")

                    if not url or url in existing_urls:
                        continue

                    results.append(
                        {
                            "title": item.get(
                                "title", "Untitled"
                            ),
                            "url": url,
                            "snippet": item.get("body", ""),
                            "query": query,
                        }
                    )

                    existing_urls.add(url)

                search_succeeded = True
                break

            except Exception as exc:
                logs.extend(
                    log_message(
                        f"Search attempt {attempt}/"
                        f"{SEARCH_RETRIES} failed: {exc}"
                    )
                )

                if attempt < SEARCH_RETRIES:
                    time.sleep(1)

        if not search_succeeded:
            logs.extend(
                log_message(
                    f"Could not retrieve results for: {query}"
                )
            )

    logs.extend(
        log_message(
            f"Search round completed. "
            f"Found {len(results)} new results."
        )
    )

    return {
        "search_results": results,
        "logs": logs,
    }


# ============================================================
# 6. REFLECTION NODE
# ============================================================

def reflect(state: ResearchState) -> dict:
    """
    Evaluate research coverage and decide whether another
    search round is necessary.
    """

    current_round = state.get("loop_count", 0) + 1
    results = state.get("search_results", [])

    logs = log_message(
        f"Reflection: evaluating research round {current_round}."
    )

    # Hard limit: never exceed MAX_LOOPS search rounds.
    if current_round >= MAX_LOOPS:
        logs.extend(
            log_message(
                "Maximum search rounds reached. "
                "Proceeding to report generation."
            )
        )

        return {
            "loop_count": current_round,
            "needs_more_research": False,
            "queries": [],
            "logs": logs,
        }

    if not results:
        logs.extend(
            log_message(
                "No search results available. "
                "Stopping additional research."
            )
        )

        return {
            "loop_count": current_round,
            "needs_more_research": False,
            "queries": [],
            "logs": logs,
        }

    source_summary = "\n".join(
        [
            (
                f"Title: {item['title']}\n"
                f"URL: {item['url']}\n"
                f"Snippet: {item['snippet'][:500]}"
            )
            for item in results[-20:]
        ]
    )

    try:
        response = llm.invoke(
            f"""
You are a critical research evaluator.

Research topic:
{state['topic']}

Current search round:
{current_round} of {MAX_LOOPS}

Retrieved evidence:
{source_summary}

Determine whether another search round would materially improve
the research.

Look for:
- Important unanswered questions.
- Missing perspectives.
- Insufficient evidence for key claims.
- Useful additional angles not covered by current sources.

Return your answer in exactly this format:

DECISION: MORE or DONE
QUERY: first additional search query, or NONE
QUERY: second additional search query, or NONE

Rules:
- Choose DONE if the evidence is sufficient for a useful report.
- Choose MORE only when additional searches are likely to help.
- Do not repeat existing searches.
- Never invent facts about the retrieved sources.
"""
        )

        reflection = get_response_text(response)
        lines = reflection.splitlines()

        decision_line = next(
            (
                line.strip().upper()
                for line in lines
                if line.strip().upper().startswith("DECISION:")
            ),
            "",
        )

        needs_more = (
            decision_line.split(":", 1)[1].strip().startswith("MORE")
            if ":" in decision_line
            else False
        )

        new_queries = []

        if needs_more:
            for line in lines:
                if line.strip().upper().startswith("QUERY:"):
                    query = line.split(":", 1)[1].strip()

                    if query.upper() != "NONE" and query:
                        new_queries.append(query)

            new_queries = list(dict.fromkeys(new_queries))[:2]

            existing_queries = {
                query.strip().lower()
                for query in state.get("queries", [])
            }

            new_queries = [
                query
                for query in new_queries
                if query.strip().lower() not in existing_queries
            ]

        if not new_queries:
            needs_more = False

    except Exception as exc:
        needs_more = False
        new_queries = []

        logs.extend(
            log_message(
                f"Reflection failed: {exc}. "
                "Proceeding with the evidence already collected."
            )
        )

    if needs_more:
        logs.extend(
            log_message(
                f"Reflection identified {len(new_queries)} "
                "additional search queries."
            )
        )
    else:
        logs.extend(
            log_message(
                "Research coverage is sufficient. "
                "Proceeding to report generation."
            )
        )

    return {
        "loop_count": current_round,
        "needs_more_research": needs_more,
        "queries": new_queries,
        "logs": logs,
    }


# ============================================================
# 7. REPORT WRITER NODE
# ============================================================

def write_report(state: ResearchState) -> dict:
    """Generate a research report grounded in retrieved snippets."""

    topic = state["topic"]
    results = state.get("search_results", [])

    logs = log_message("Generating the final research report.")

    if not results:
        report = (
            f"# Research Report: {topic}\n\n"
            "## Research limitation\n\n"
            "The agent could not retrieve web search results. "
            "No evidence-backed conclusions can be provided. "
            "Check your internet connection and search service, "
            "then try again."
        )

        return {
            "report": report,
            "logs": logs,
        }

    # Assign stable source identifiers.
    source_material = []

    for index, item in enumerate(results, start=1):
        source_material.append(
            f"""
[S{index}]
Title: {item['title']}
URL: {item['url']}
Search query: {item['query']}
Retrieved snippet: {item['snippet']}
"""
        )

    evidence = "\n".join(source_material)

    try:
        response = llm.invoke(
            f"""
You are an evidence-focused research analyst.

Write a clear, useful research report on:
{topic}

Use only the evidence in the supplied search results.

RESEARCH EVIDENCE:
{evidence}

REPORT REQUIREMENTS:
1. Start with a concise executive summary.
2. Organize the findings under useful headings.
3. Explain key findings, implications and relevant limitations.
4. Support factual claims with source identifiers such as [S1].
5. Use only source identifiers that actually exist in the evidence.
6. Do not invent facts, statistics, quotations, publication dates,
   source contents or citations.
7. Distinguish supported findings from uncertainty.
8. If the snippets do not establish a claim, say so.
9. Do not create a separate bibliography; the application
   will append the verified source list.
10. Write in professional, readable Markdown.

Important:
You have search-result snippets, not necessarily the full
contents of the linked webpages. Do not imply that you have
read full articles when you have not.
"""
        )

        report_body = get_response_text(response)

        if not report_body:
            raise ValueError("The model returned an empty report.")

    except Exception as exc:
        logs.extend(
            log_message(
                f"Report generation failed: {exc}. "
                "Creating a fallback evidence summary."
            )
        )

        report_body = (
            f"# Research Report: {topic}\n\n"
            "## Retrieved evidence\n\n"
            "Automated report generation failed. "
            "The following search snippets are available "
            "for manual review.\n\n"
        )

        for index, item in enumerate(results, start=1):
            report_body += (
                f"### [S{index}] {item['title']}\n\n"
                f"{item['snippet']}\n\n"
            )

    # Build the source list from actual retrieved URLs.
    source_list = "\n\n## Sources\n\n"

    for index, item in enumerate(results, start=1):
        source_list += (
            f"{index}. **[S{index}] "
            f"{item['title']}** — {item['url']}\n"
        )

    final_report = (
        f"{report_body}\n\n"
        "---"
        f"{source_list}"
        "\n\n---\n"
        "*Research limitation: This report is based on "
        "search-result snippets. Verify important claims "
        "against the original sources.*"
    )

    logs.extend(
        log_message(
            f"Report generated using {len(results)} retrieved sources."
        )
    )

    return {
        "report": final_report,
        "logs": logs,
    }


# ============================================================
# 8. ROUTING LOGIC
# ============================================================

def route_after_reflection(state: ResearchState) -> str:
    """Continue searching only when reflection requests it."""

    if (
        state.get("needs_more_research", False)
        and state.get("loop_count", 0) < MAX_LOOPS
    ):
        return "search"

    return "write_report"


# ============================================================
# 9. BUILD THE LANGGRAPH WORKFLOW
# ============================================================

workflow = StateGraph(ResearchState)

workflow.add_node("planner", planner)
workflow.add_node("search", search_web)
workflow.add_node("reflect", reflect)
workflow.add_node("write_report", write_report)

workflow.set_entry_point("planner")

workflow.add_edge("planner", "search")
workflow.add_edge("search", "reflect")

workflow.add_conditional_edges(
    "reflect",
    route_after_reflection,
    {
        "search": "search",
        "write_report": "write_report",
    },
)

workflow.add_edge("write_report", END)

# Export the compiled graph for Streamlit.
app = workflow.compile()


# ============================================================
# 10. STANDALONE EXECUTION FOR TESTING
# ============================================================

def run_agent(topic: str) -> dict:
    """Run the research agent and return its final state."""

    topic = topic.strip()

    if not topic:
        raise ValueError("Research topic cannot be empty.")

    initial_state = {
        "topic": topic,
        "queries": [],
        "search_results": [],
        "report": "",
        "loop_count": 0,
        "logs": [],
        "needs_more_research": False,
    }

    return app.invoke(initial_state)


if __name__ == "__main__":
    research_topic = input(
        "Enter a research topic: "
    ).strip()

    try:
        result = run_agent(research_topic)

        print("\n" + "=" * 60)
        print("FINAL RESEARCH REPORT")
        print("=" * 60)
        print(result.get("report", "No report generated."))

        print("\n" + "=" * 60)
        print("RESEARCH LOGS")
        print("=" * 60)

        for entry in result.get("logs", []):
            print(f"- {entry}")

    except Exception as exc:
        print(f"\nAgent execution failed: {exc}")
