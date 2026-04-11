"""
planner/prompts.py — All AI prompt templates for the slide planner.

Keeps prompt text separate from planner logic for clarity and tuning.
"""

SYSTEM_PROMPT = """You are a professional presentation strategist. Your job is to transform a structured document
analysis into a compelling slide-by-slide presentation plan. You create coherent narratives,
not just bullet-point dumps.

Rules:
- Output ONLY valid JSON matching the schema provided. No markdown fences, no prose, no explanations.
- Slide count must be between {min_slides} and {max_slides}.
- Every major section from the source must appear somewhere.
- Assign the most appropriate layout_type for each slide from this set:
  TITLE, AGENDA, EXEC_SUMMARY, CONTENT_BULLETS, CONTENT_TWO_COLUMN, STAT_HIGHLIGHT,
  BAR_CHART, PIE_CHART, LINE_CHART, AREA_CHART, TABLE, TIMELINE_INFOGRAPHIC,
  PROCESS_FLOW_INFOGRAPHIC, COMPARISON_INFOGRAPHIC, KEY_TAKEAWAYS, SECTION_DIVIDER
- When source has numeric data, always assign a chart slide for it.
- Executive summary must appear as slide 3 (after title and agenda).
- Key takeaways must be the LAST slide.
- stat_highlight slides: max 3 stats per slide, each with a number + label.
- bullet slides: max 5 bullets, each max 12 words. Never walls of text.
- section_divider slides: use between major topic shifts, count toward total.
- All chart data values must be real numbers, not strings. Ensure data is accurate.
- Speaker notes should be 2-3 sentences for a presenter."""

USER_PROMPT = """Here is the document analysis:
{ast_json}

Target slide count: {target_count} (must be between {min_slides} and {max_slides})

Return a JSON array where each element is a slide object matching this exact schema:
{{
  "slide_number": int,
  "slide_type": str,
  "title": str,
  "subtitle": str | null,
  "content": {{...}},
  "speaker_notes": str,
  "source_sections": [str]
}}

Content schema by slide_type:
- TITLE:              {{"headline": str, "subheadline": str, "presenter": null}}
- AGENDA:             {{"items": [{{"number": int, "topic": str}}]}}
- EXEC_SUMMARY:       {{"insights": [str], "key_metric": str|null}}  (max 4 insights)
- CONTENT_BULLETS:    {{"bullets": [{{"text": str, "sub_bullets": [str]|null}}]}}  (max 5 bullets)
- CONTENT_TWO_COLUMN: {{"left": {{"heading": str, "points": [str]}}, "right": {{"heading": str, "points": [str]}}}}
- STAT_HIGHLIGHT:     {{"stats": [{{"value": str, "label": str, "context": str}}]}}  (max 3)
- BAR_CHART:          {{"chart_title": str, "x_label": str, "y_label": str, "series": [{{"name": str, "values": [[label, number]]}}]}}
- PIE_CHART:          {{"chart_title": str, "slices": [{{"label": str, "value": number}}]}}
- LINE_CHART:         {{"chart_title": str, "x_label": str, "y_label": str, "series": [{{"name": str, "points": [[x, y]]}}]}}
- AREA_CHART:         {{"chart_title": str, "x_label": str, "y_label": str, "series": [{{"name": str, "points": [[x, y]]}}]}}
- TABLE:              {{"table_title": str, "headers": [str], "rows": [[str]]}}
- TIMELINE_INFOGRAPHIC: {{"events": [{{"year": str, "title": str, "description": str}}]}}  (max 7)
- PROCESS_FLOW_INFOGRAPHIC: {{"steps": [{{"number": int, "title": str, "description": str}}], "flow_direction": "horizontal"|"vertical"}}
- COMPARISON_INFOGRAPHIC: {{"left_label": str, "right_label": str, "dimensions": [{{"aspect": str, "left": str, "right": str}}]}}
- KEY_TAKEAWAYS:      {{"takeaways": [{{"icon_hint": str, "text": str}}]}}  (max 5)
- SECTION_DIVIDER:    {{"section_number": int, "section_title": str, "section_subtitle": str|null}}

Return ONLY the JSON array. No markdown fences, no extra text."""

RETRY_PROMPT = """Your previous response had validation errors:
{errors}

Please fix these issues and return the corrected JSON array.
Remember:
- Slide count must be between {min_slides} and {max_slides}
- First slide must be TITLE, last must be KEY_TAKEAWAYS
- All content must match the schema for its slide_type
- Output ONLY valid JSON, no markdown fences

Original document analysis:
{ast_json}"""

COUNT_ADJUSTMENT_PROMPT = """The slide plan you returned has {actual_count} slides but the target
is {target_count} (range: {min_slides}–{max_slides}).

Please {"add more" if actual_count < target_count else "reduce"} slides to reach the target.
Keep the TITLE as slide 1 and KEY_TAKEAWAYS as the last slide.

Return the complete corrected JSON array. No markdown fences."""

CLUSTERING_PROMPT = """The following document has {section_count} sections, which is too many
for a {max_slides}-slide presentation. Group related sections into {target_groups} thematic
clusters. For each cluster, provide a group name and the section headings it contains.

Sections:
{section_list}

Return a JSON array of cluster objects:
[{{"group_name": str, "sections": [str]}}]

Output ONLY valid JSON, no markdown fences."""
