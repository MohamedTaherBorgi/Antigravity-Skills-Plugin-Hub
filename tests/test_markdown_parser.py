# Test Markdown Parser Logic
import re

def render_simple_markdown(md, current_doc_dir=""):
    if not md:
        return ""

    # Strip YAML frontmatter
    text = re.sub(r"^---\s*[\r\n]+[\s\S]*?[\r\n]+---\s*[\r\n]+", "", md)

    # 1. Code blocks
    code_blocks = []
    def code_repl(m):
        lang = m.group(1)
        code = m.group(2)
        idx = len(code_blocks)
        code_blocks.append((lang, code))
        return f"__CB_{idx}__"
    text = re.sub(r"```([\w-]*)\r?\n([\s\S]*?)```", code_repl, text)

    # 2. Tables
    tables = []
    def table_repl(m):
        lines = m.group(0).strip().splitlines()
        if len(lines) >= 2:
            html = '<div class="table-wrap"><table>'
            for idx, line in enumerate(lines):
                if re.match(r"^\|\s*[-:]+\s*\|", line):
                    continue
                cells = [c.strip() for c in line.split("|")[1:-1]]
                tag = "th" if idx == 0 else "td"
                html += "<tr>" + "".join(f"<{tag}>{c}</{tag}>" for c in cells) + "</tr>"
            html += "</table></div>"
            idx = len(tables)
            tables.append(html)
            return f"__TBL_{idx}__"
        return m.group(0)
    text = re.sub(r"(?:^\|.+?\|(?:\r?\n|$)){2,}", table_repl, text, flags=re.MULTILINE)

    # Basic escaping
    def esc(s):
        return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")

    text = esc(text)

    # Headers
    text = re.sub(r"^#### (.*?)$", r"<h4>\1</h4>", text, flags=re.MULTILINE)
    text = re.sub(r"^### (.*?)$", r"<h3>\1</h3>", text, flags=re.MULTILINE)
    text = re.sub(r"^## (.*?)$", r"<h2>\1</h2>", text, flags=re.MULTILINE)
    text = re.sub(r"^# (.*?)$", r"<h1>\1</h1>", text, flags=re.MULTILINE)

    # Inline styles
    text = re.sub(r"\*\*(.*?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"\*(.*?)\*", r"<em>\1</em>", text)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"^&gt; (.*?)$", r"<blockquote>\1</blockquote>", text, flags=re.MULTILINE)
    text = re.sub(r"^---$", r"<hr/>", text, flags=re.MULTILINE)

    # Markdown Links: [label](target)
    def link_repl(m):
        label = m.group(1)
        target = m.group(2).strip()
        if target.startswith(("http://", "https://")):
            return f'<a href="{target}" target="_blank" rel="noopener noreferrer" class="ext-link">{label} ↗</a>'
        else:
            return f'<a href="javascript:void(0)" class="doc-link" data-href="{target}" onclick="handleDocLink(this)">{label}</a>'
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", link_repl, text)

    # Grouped Lists: Unordered and Ordered
    # Unordered
    lines = text.splitlines()
    in_ul = False
    in_ol = False
    new_lines = []
    for line in lines:
        ul_m = re.match(r"^\s*[-*]\s+(.*)$", line)
        ol_m = re.match(r"^\s*(\d+)\.\s+(.*)$", line)
        if ul_m:
            if in_ol:
                new_lines.append("</ol>")
                in_ol = False
            if not in_ul:
                new_lines.append("<ul>")
                in_ul = True
            new_lines.append(f"<li>{ul_m.group(1)}</li>")
        elif ol_m:
            if in_ul:
                new_lines.append("</ul>")
                in_ul = False
            if not in_ol:
                new_lines.append("<ol>")
                in_ol = True
            new_lines.append(f"<li>{ol_m.group(2)}</li>")
        else:
            if in_ul:
                new_lines.append("</ul>")
                in_ul = False
            if in_ol:
                new_lines.append("</ol>")
                in_ol = False
            new_lines.append(line)
    if in_ul:
        new_lines.append("</ul>")
    if in_ol:
        new_lines.append("</ol>")
    text = "\n".join(new_lines)

    # Paragraphs
    blocks = re.split(r"\n\s*\n", text)
    rendered_blocks = []
    for b in blocks:
        b_str = b.strip()
        if not b_str:
            continue
        if any(b_str.startswith(tag) for tag in ("<h", "<ul>", "<ol>", "<blockquote>", "<hr", "__CB_", "__TBL_")):
            rendered_blocks.append(b_str)
        else:
            rendered_blocks.append(f"<p>{b_str}</p>")
    text = "\n".join(rendered_blocks)

    # Restore tables
    for idx, tbl in enumerate(tables):
        text = text.replace(f"__TBL_{idx}__", tbl)

    # Restore code blocks
    for idx, (lang, code) in enumerate(code_blocks):
        code_html = f'<pre><code class="lang-{lang}">{esc(code.strip())}</code></pre>'
        text = text.replace(f"__CB_{idx}__", code_html)

    return text

sample = """---
name: test
description: sample
---
# Title
This is **bold** and `code` and [link](linux-pentesting.md).

- item 1
- item 2

1. step one
2. step two

| Col 1 | Col 2 |
| --- | --- |
| val 1 | val 2 |

```python
print("hello world")
```
"""

out = render_simple_markdown(sample)
print(out)
assert "<ul>\n<li>item 1</li>\n<li>item 2</li>\n</ul>" in out
assert "<ol>\n<li>step one</li>\n<li>step two</li>\n</ol>" in out
assert 'class="doc-link" data-href="linux-pentesting.md"' in out
assert "<table>" in out
assert 'class="lang-python"' in out
print("\nAll parser assertions passed!")
