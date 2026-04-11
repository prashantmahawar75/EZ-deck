# EZ-Deck Demo Video Script

**Presenter**: Prashant Mahawar, Software Engineer
**Duration**: ~5-6 Minutes
**Objective**: Demonstrate the end-to-end pipeline, system architecture, and intelligent decision-making of the MD-to-PPTX converter.

---

## Part 1: Introduction (0:00 - 0:45)
**Visual**: Screen recording of the project folder and the CLI.
**Audio**:
> "Hi, I'm Prashant Mahawar, a software engineer. Today I'm presenting EZ-Deck — a production-grade pipeline that transforms unstructured Markdown into visually polished, master-compliant PowerPoint presentations. Most tools just dump bullets onto slides; EZ-Deck builds a narrative. The system respects your corporate theme, automatically generates charts and tables from your data, and uses an agentic architecture to ensure quality throughout."

---

## Part 2: System Design (0:45 - 1:45)
**Visual**: Display the 5-layer diagram from the README.
**Audio**:
> "The magic happens in our 5-layer architecture. 
> 1. **Layer 1 - Parser**: We don't just read text; we detect 'signals' like currency, percentages, and trends.
> 2. **Layer 2 - AI Planner**: Using the Claude API, our system analyzes the document's structure to create a strategic slide plan. It's not a one-to-one mapping; the AI decides if a section should be a bullet list, a chart, or a process flow.
> 3. **Layer 3 - Renderers**: We use Matplotlib for pixel-perfect charts and native PPTX shapes for infographics, ensuring everything is brand-aligned.
> 4. **Layer 4 - Builder**: This layer extracts theme colors and fonts directly from your Slide Master.
> 5. **Layer 5 - QA Validator**: Finally, our validator scores the output. If it detects overflow or missing content, it triggers an agentic retry loop to fix the issue."

---

## Part 3: Demo 1 - Short Team Agenda (1:45 - 2:45)
**Visual**: Split screen showing `demo_short.md` and the terminal run.
**Audio**:
> "Let's see it in action. First, a simple 'Team Offsite Agenda'. I'll target a compact 10-slide deck. Notice the terminal logs: the parser identifies list structures, inline numeric data signals, and section hierarchy.
>
> In the output, the system generates a structured flow: Title, Agenda, Executive Summary, then content slides for each topic. The 'Schedule' section was automatically rendered as a Stat Highlight slide because it contained specific data points. Everything aligns with the Slide Master's color palette and fonts."

---

## Part 4: Demo 2 - Quarterly Performance Report (2:45 - 4:15)
**Visual**: Show `demo_long.md` (lots of data) and run with `--slides 14`.
**Audio**:
> "Now for the real test: a comprehensive 'Q3 Performance Report'. This document has financial tables, multi-level lists, revenue data, and competitive analysis. I'm targeting 14 slides to capture everything.
>
> Look at the decision-making: the system detected a table with numeric columns in 'Market Position' and automatically generated a Bar Chart with three data series. The 'Risks and Mitigations' section was rendered as a native styled table. Notice how the pipeline extracted theme colors directly from the Slide Master — the palette uses the master's own accent colors.
> 
> The output achieves a perfect 100% quality score — all 8 validation checks pass. No empty slides, no text overflow, all source sections covered."

---

## Part 5: Handling Complexity & Intelligence (4:15 - 5:15)
**Visual**: Scrolling through `config.py`, `validator/pptx_validator.py`, and terminal output.
**Audio**:
> "How do I handle complexity? The system is designed for edge cases. If the Claude API is down, there's a deterministic rule-based fallback planner that still generates charts and tables from data. The parser handles files up to 5MB with encoding fallbacks. The Validator runs 8 quality checks — file integrity, slide count, empty slides, text overflow, source coverage, chart rendering, master compliance, and accessibility.
>
> When validation fails, the pipeline automatically retries with adjusted parameters — it's a self-healing content engine. The architecture is fully modular: parsers, planners, renderers, and builders are independently testable and replaceable."

---

## Part 6: Conclusion (5:15 - 5:30)
**Visual**: Final slide of the generated PPTX, then project README.
**Audio**:
> "EZ-Deck bridges the gap between raw data and professional presentations. Every chart is generated from your data, every layout respects your brand, and the entire process is intelligent. Thanks for watching!"
