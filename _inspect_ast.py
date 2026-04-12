"""Quick utility to inspect AST structure."""
import sys
sys.path.insert(0, '.')
from parser.md_parser import parse_markdown

ast = parse_markdown('test_dynamic.md')
for s in ast['sections']:
    heading = s["heading"]
    level = s["level"]
    print(f'\n=== {heading} (level={level}) ===')
    for b in s['blocks']:
        btype = b['type']
        if btype == 'table':
            content = b.get('content', {})
            hdrs = content.get("headers", [])
            rows = content.get("rows", [])
            print(f'  {btype}: headers={hdrs}, {len(rows)} rows')
        elif btype in ('bullet_list', 'ordered_list'):
            items = b.get('content', [])
            for item in items[:4]:
                text = item.get('text', '') if isinstance(item, dict) else str(item)
                print(f'  {btype}: {text[:90]}')
            if len(items) > 4:
                print(f'  ... +{len(items)-4} more')
        else:
            text = b.get('content', '')
            if isinstance(text, str):
                print(f'  {btype}: {text[:90]}')
        sigs = b.get('data_signals', [])
        if sigs:
            for sig in sigs:
                st = sig.get("type", "?")
                ch = sig.get("chart_hint", "?")
                m = sig.get("matches", [])
                print(f'    signal: {st} -> {ch} ({len(m)} matches)')
