
import io
import os
import re
import html
from xml.sax.saxutils import escape

import streamlit as st

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import (
    getSampleStyleSheet,
    ParagraphStyle,
)
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    HRFlowable,
    Table,
    TableStyle,
)

from agent import app as research_agent


# ============================================================
# 1. STREAMLIT CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="Agentic Research Assistant",
    page_icon="🔎",
    layout="wide",
)

st.title("🔎 Agentic Research Assistant")

st.markdown(
    """
Research a topic using an AI agent that plans searches,
collects web evidence, evaluates research gaps, and writes
a report with source links.
"""
)


# ============================================================
# 2. TEXT NORMALIZATION
# ============================================================

def normalize_pdf_text(text: str) -> str:
    """Normalize problematic Unicode characters for PDF output."""

    replacements = {
        "\u00a0": " ",
        "\u200b": "",
        "\u200c": "",
        "\u200d": "",
        "\ufeff": "",
        "\u2010": "-",
        "\u2011": "-",
        "\u2012": "-",
        "\u2013": "-",
        "\u2014": "-",
        "\u2212": "-",
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2026": "...",
        "\u2022": "-",
    }

    for original, replacement in replacements.items():
        text = text.replace(original, replacement)

    return text


# ============================================================
# 3. UNICODE FONT SETUP
# ============================================================

def register_pdf_fonts():
    """
    Prefer a Unicode-capable TrueType font.

    If a suitable font is unavailable, use ReportLab's
    built-in fonts as a fallback.
    """

    font_candidates = [
        (
            r"C:\Windows\Fonts\arial.ttf",
            r"C:\Windows\Fonts\arialbd.ttf",
            r"C:\Windows\Fonts\ariali.ttf",
            r"C:\Windows\Fonts\arialbi.ttf",
        ),
        (
            r"C:\Windows\Fonts\calibri.ttf",
            r"C:\Windows\Fonts\calibrib.ttf",
            r"C:\Windows\Fonts\calibrii.ttf",
            r"C:\Windows\Fonts\calibriz.ttf",
        ),
    ]

    for regular, bold, italic, bold_italic in font_candidates:
        if not os.path.isfile(regular):
            continue

        try:
            pdfmetrics.registerFont(
                TTFont("ResearchUnicode", regular)
            )

            if os.path.isfile(bold):
                pdfmetrics.registerFont(
                    TTFont("ResearchUnicode-Bold", bold)
                )

            if os.path.isfile(italic):
                pdfmetrics.registerFont(
                    TTFont("ResearchUnicode-Italic", italic)
                )

            if os.path.isfile(bold_italic):
                pdfmetrics.registerFont(
                    TTFont("ResearchUnicode-BoldItalic", bold_italic)
                )

            pdfmetrics.registerFontFamily(
                "ResearchUnicode",
                normal="ResearchUnicode",
                bold=(
                    "ResearchUnicode-Bold"
                    if os.path.isfile(bold)
                    else "ResearchUnicode"
                ),
                italic=(
                    "ResearchUnicode-Italic"
                    if os.path.isfile(italic)
                    else "ResearchUnicode"
                ),
                boldItalic=(
                    "ResearchUnicode-BoldItalic"
                    if os.path.isfile(bold_italic)
                    else "ResearchUnicode"
                ),
            )

            return "ResearchUnicode"

        except Exception:
            continue

    return "Helvetica"


# ============================================================
# 4. MARKDOWN INLINE FORMATTER
# ============================================================

def format_inline_markdown(text: str) -> str:
    """
    Convert common Markdown inline formatting to ReportLab markup.
    Escape HTML/XML before inserting safe formatting tags.
    """

    placeholders = []

    def save_link(match):
        label = match.group(1)
        url = match.group(2).strip()

        if not url.startswith(("https://", "http://")):
            return escape(match.group(0))

        placeholder = f"PDFLINKTOKEN{len(placeholders)}END"

        safe_label = escape(label)
        safe_url = html.escape(url, quote=True)

        placeholders.append(
            (
                placeholder,
                f'<link href="{safe_url}" color="blue">'
                f"{safe_label}</link>",
            )
        )

        return placeholder

    # Preserve Markdown links before escaping the remaining text.
    text = re.sub(
        r"\[([^\]]+)\]\((https?://[^)\s]+)\)",
        save_link,
        text,
    )

    text = escape(text)

    # Convert bare URLs to clickable links.
    text = re.sub(
        r"(?<![=\"/])(https?://[^\s<]+)",
        lambda match: (
            f'<link href="{html.escape(match.group(1), quote=True)}" '
            f'color="blue">{match.group(1)}</link>'
        ),
        text,
    )

    # Basic Markdown inline formatting.
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(
        r"(?<!\*)\*([^*]+)\*(?!\*)",
        r"<i>\1</i>",
        text,
    )

    text = re.sub(
        r"`([^`]+)`",
        r"<font name='Courier'>\1</font>",
        text,
    )

    for placeholder, replacement in placeholders:
        text = text.replace(placeholder, replacement)

    return text


# ============================================================
# 5. PDF GENERATOR
# ============================================================

def generate_pdf(report: str) -> bytes:
    """Convert a Markdown research report into a formatted PDF."""

    report = normalize_pdf_text(report)

    buffer = io.BytesIO()
    font_name = register_pdf_fonts()

    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title="Agentic Research Report",
        author="Agentic Research Assistant",
    )

    styles = getSampleStyleSheet()

    styles.add(
        ParagraphStyle(
            name="ResearchTitle",
            parent=styles["Title"],
            fontName=font_name,
            fontSize=20,
            leading=26,
            alignment=TA_CENTER,
            spaceAfter=18,
        )
    )

    styles.add(
        ParagraphStyle(
            name="ResearchH2",
            parent=styles["Heading2"],
            fontName=font_name,
            fontSize=14,
            leading=18,
            spaceBefore=14,
            spaceAfter=7,
        )
    )

    styles.add(
        ParagraphStyle(
            name="ResearchH3",
            parent=styles["Heading3"],
            fontName=font_name,
            fontSize=11,
            leading=14,
            spaceBefore=9,
            spaceAfter=5,
        )
    )

    styles.add(
        ParagraphStyle(
            name="ResearchBody",
            parent=styles["BodyText"],
            fontName=font_name,
            fontSize=9,
            leading=13,
            spaceAfter=7,
            wordWrap="CJK",
        )
    )

    styles.add(
        ParagraphStyle(
            name="ResearchTable",
            parent=styles["BodyText"],
            fontName=font_name,
            fontSize=7.5,
            leading=10,
            spaceAfter=2,
            wordWrap="CJK",
        )
    )

    styles.add(
        ParagraphStyle(
            name="ResearchTableHeader",
            parent=styles["ResearchTable"],
            fontName=font_name,
            textColor=colors.white,
        )
    )

    story = []
    lines = report.splitlines()
    index = 0

    while index < len(lines):
        line = lines[index].strip()

        if not line:
            story.append(Spacer(1, 4))
            index += 1
            continue

        # Horizontal rules.
        if line in ("---", "***", "___"):
            story.append(
                HRFlowable(
                    width="100%",
                    thickness=0.6,
                    color=colors.grey,
                    spaceBefore=5,
                    spaceAfter=8,
                )
            )
            index += 1
            continue

        # Markdown tables: header, separator, then rows.
        if (
            line.startswith("|")
            and index + 1 < len(lines)
            and re.match(
                r"^\s*\|?\s*:?-{3,}",
                lines[index + 1],
            )
        ):
            raw_rows = [line]
            index += 2

            while index < len(lines):
                row_line = lines[index].strip()

                if not row_line.startswith("|"):
                    break

                raw_rows.append(row_line)
                index += 1

            table_data = []

            for row_number, row_line in enumerate(raw_rows):
                cells = [
                    cell.strip()
                    for cell in row_line.strip("|").split("|")
                ]

                # Remove Markdown separator rows.
                if all(
                    re.fullmatch(r":?-{3,}:?", cell.strip())
                    for cell in cells
                ):
                    continue

                formatted_cells = []

                for cell in cells:
                    cell = format_inline_markdown(cell)

                    style = (
                        styles["ResearchTableHeader"]
                        if row_number == 0
                        else styles["ResearchTable"]
                    )

                    formatted_cells.append(
                        Paragraph(cell, style)
                    )

                table_data.append(formatted_cells)

            if table_data:
                column_count = max(
                    len(row) for row in table_data
                )

                # Pad rows with missing cells.
                for row in table_data:
                    while len(row) < column_count:
                        row.append(
                            Paragraph("", styles["ResearchTable"])
                        )

                available_width = (
                    A4[0] - document.leftMargin - document.rightMargin
                )

                col_widths = [
                    available_width / column_count
                ] * column_count

                pdf_table = Table(
                    table_data,
                    colWidths=col_widths,
                    repeatRows=1,
                    hAlign="LEFT",
                    splitByRow=1,
                )

                pdf_table.setStyle(
                    TableStyle(
                        [
                            (
                                "BACKGROUND",
                                (0, 0),
                                (-1, 0),
                                colors.HexColor("#243B53"),
                            ),
                            (
                                "TEXTCOLOR",
                                (0, 0),
                                (-1, 0),
                                colors.white,
                            ),
                            (
                                "GRID",
                                (0, 0),
                                (-1, -1),
                                0.4,
                                colors.HexColor("#B8C2CC"),
                            ),
                            (
                                "VALIGN",
                                (0, 0),
                                (-1, -1),
                                "TOP",
                            ),
                            (
                                "LEFTPADDING",
                                (0, 0),
                                (-1, -1),
                                5,
                            ),
                            (
                                "RIGHTPADDING",
                                (0, 0),
                                (-1, -1),
                                5,
                            ),
                            (
                                "TOPPADDING",
                                (0, 0),
                                (-1, -1),
                                5,
                            ),
                            (
                                "BOTTOMPADDING",
                                (0, 0),
                                (-1, -1),
                                5,
                            ),
                            (
                                "ROWBACKGROUNDS",
                                (0, 1),
                                (-1, -1),
                                [
                                    colors.white,
                                    colors.HexColor("#F3F6F9"),
                                ],
                            ),
                        ]
                    )
                )

                story.append(pdf_table)
                story.append(Spacer(1, 10))

            continue

        # Markdown headings.
        heading = re.match(r"^(#{1,3})\s+(.*)$", line)

        if heading:
            level = len(heading.group(1))
            heading_text = format_inline_markdown(
                heading.group(2)
            )

            if level == 1:
                style = styles["ResearchTitle"]
            elif level == 2:
                style = styles["ResearchH2"]
            else:
                style = styles["ResearchH3"]

            story.append(Paragraph(heading_text, style))
            index += 1
            continue

        # Bullet lists.
        bullet = re.match(r"^[-*•]\s+(.*)$", line)

        if bullet:
            text = (
                "&#8226; "
                + format_inline_markdown(bullet.group(1))
            )

            story.append(
                Paragraph(text, styles["ResearchBody"])
            )

            index += 1
            continue

        # Numbered lists.
        numbered = re.match(r"^(\d+)[.)]\s+(.*)$", line)

        if numbered:
            text = (
                f"{numbered.group(1)}. "
                + format_inline_markdown(numbered.group(2))
            )

            story.append(
                Paragraph(text, styles["ResearchBody"])
            )

            index += 1
            continue

        # Normal paragraphs.
        story.append(
            Paragraph(
                format_inline_markdown(line),
                styles["ResearchBody"],
            )
        )

        index += 1

    def add_page_number(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.grey)

        canvas.drawCentredString(
            A4[0] / 2,
            10 * mm,
            f"Page {doc.page}",
        )

        canvas.restoreState()

    document.build(
        story,
        onFirstPage=add_page_number,
        onLaterPages=add_page_number,
    )

    return buffer.getvalue()


# ============================================================
# 6. SIDEBAR
# ============================================================

with st.sidebar:
    st.header("Research Workflow")

    st.markdown(
        """
**1. Plan**  
Generate focused research queries.

**2. Search**  
Retrieve web search results.

**3. Reflect**  
Evaluate missing information.

**4. Iterate**  
Search again when necessary, up to three rounds.

**5. Report**  
Generate findings with source references.
"""
    )

    st.divider()

    st.caption(
        "Built with LangGraph, Groq, DuckDuckGo, "
        "Streamlit and ReportLab."
    )

    st.caption(
        "Reports use retrieved search snippets; "
        "the original webpages may contain additional information."
    )


# ============================================================
# 7. RESEARCH INPUT
# ============================================================

topic = st.text_area(
    "What would you like to research?",
    placeholder=(
        "Example: How is agentic AI transforming "
        "software engineering in 2026?"
    ),
    height=110,
    key="research_topic",
)

start_research = st.button(
    "🔎 Start Research",
    type="primary",
    use_container_width=True,
)


# ============================================================
# 8. EXECUTE THE RESEARCH AGENT
# ============================================================

if start_research:

    if not topic.strip():
        st.warning("Please enter a research topic.")

    else:
        initial_state = {
            "topic": topic.strip(),
            "queries": [],
            "search_results": [],
            "report": "",
            "loop_count": 0,
            "logs": [],
            "needs_more_research": False,
        }

        st.subheader("Research Progress")

        progress_bar = st.progress(0)
        status_text = st.empty()
        log_container = st.container()

        report = ""
        completed = False

        node_labels = {
            "planner": "Planning research queries",
            "search": "Searching the web",
            "reflect": "Evaluating research coverage",
            "write_report": "Writing the final report",
        }

        node_progress = {
            "planner": 15,
            "search": 40,
            "reflect": 65,
            "write_report": 90,
        }

        try:
            # Stream progress as each graph node completes.
            for update in research_agent.stream(
                initial_state,
                stream_mode="updates",
            ):
                for node_name, node_output in update.items():

                    status_text.info(
                        node_labels.get(
                            node_name,
                            f"Running {node_name}",
                        )
                    )

                    progress_bar.progress(
                        node_progress.get(node_name, 50)
                    )

                    for message in node_output.get("logs", []):
                        with log_container:
                            st.write(f"• {message}")

                    if node_output.get("report"):
                        report = node_output["report"]

            completed = True
            progress_bar.progress(100)
            status_text.success("Research completed.")

        except Exception as exc:
            status_text.error("The research process failed.")

            st.error(
                "An error occurred while running the research agent."
            )

            st.exception(exc)

        # ====================================================
        # 9. DISPLAY REPORT AND DOWNLOADS
        # ====================================================

        if completed and report:

            st.divider()
            st.subheader("📄 Research Report")

            st.markdown(report)

            st.divider()
            st.subheader("Download Your Report")

            col1, col2 = st.columns(2)

            with col1:
                st.download_button(
                    label="⬇️ Download Markdown",
                    data=report.encode("utf-8"),
                    file_name="research_report.md",
                    mime="text/markdown",
                    use_container_width=True,
                    key="download_markdown",
                )

            with col2:
                try:
                    pdf_data = generate_pdf(report)

                    st.download_button(
                        label="⬇️ Download PDF",
                        data=pdf_data,
                        file_name="research_report.pdf",
                        mime="application/pdf",
                        use_container_width=True,
                        key="download_pdf",
                    )

                except Exception as exc:
                    st.error(
                        "PDF generation failed. "
                        "The Markdown report is still available."
                    )

                    st.exception(exc)

        elif completed:
            st.warning(
                "The workflow completed, but no report was returned."
            )


# ============================================================
# 10. FOOTER
# ============================================================

st.divider()

st.caption(
    "Agentic Research Assistant | Verify important claims "
    "against original sources."
)
