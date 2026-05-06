#!/usr/bin/env python3
"""
generate_de1_reports.py

Scan repository for `de1_grade_report.md` files, group them by the top-level
folder and the next-level subgroup, convert each Markdown to HTML and produce
one interactive HTML file `index_de1_grade_reports.html` in the repository root.

Usage:
    python generate_de1_reports.py

Requirements:
    pip install -r requirements.txt

The script will report missing dependencies and provide install instructions.
"""
from __future__ import annotations

import os
import re
import sys
import html
import json
from pathlib import Path
from html.parser import HTMLParser
from typing import Dict, List, Tuple

try:
    import markdown
except Exception:
    markdown = None


def natural_key(s: str):
    parts = re.split(r"(\d+)", s)
    return [int(p) if p.isdigit() else p.lower() for p in parts]


def find_reports(root: Path) -> Dict[str, Dict[str, List[Tuple[Path, str, str]]]]:
    # structure: groups[group][subgroup] = list of (path, title, content)
    groups: Dict[str, Dict[str, List[Tuple[Path, str, str]]]] = {}

    for p in root.rglob('de1_grade_report.md'):
        try:
            rel = p.relative_to(root)
        except Exception:
            rel = p
        parts = rel.parts
        if len(parts) >= 2:
            group = parts[0]
            subgroup = parts[1]
        elif len(parts) == 1:
            group = parts[0]
            subgroup = ""
        else:
            group = "root"
            subgroup = ""

        text = p.read_text(encoding='utf-8', errors='ignore')
        m = re.search(r'^\s*#\s+(.*)$', text, flags=re.M)
        title = m.group(1).strip() if m else p.stem

        groups.setdefault(group, {}).setdefault(subgroup, []).append((p, title, text))

    # sort lists
    for g in groups:
        for sg in groups[g]:
            groups[g][sg].sort(key=lambda t: natural_key(t[1]))

    return dict(sorted(groups.items(), key=lambda kv: natural_key(kv[0])))


def md_to_html(md_text: str) -> str:
    if markdown is None:
        raise RuntimeError('Python package "markdown" not installed')
    # Use common extensions for code fences and tables
    return markdown.markdown(md_text, extensions=['fenced_code', 'tables', 'toc', 'attr_list'])


def sanitize_id(s: str) -> str:
    return re.sub(r'[^0-9a-zA-Z_-]', '_', s)


def detect_statuses(text: str) -> Dict[str, object]:
    """Analyze report text and return statuses for build, errors and warnings.

    Returns a dict: { 'build': 'ok'|'fail'|'error'|'unknown',
                       'errors': 'ok'|'error'|'unknown',
                       'warnings': bool }
    """
    res = {'build': 'unknown', 'errors': 'unknown', 'warnings': False}
    if not text:
        return res

    # helper to extract a section starting at a header like '## [BUILD]'
    def extract_section(header_re: str):
        m = re.search(header_re, text, flags=re.I)
        if not m:
            return ''
        start = m.end()
        # end at next top-level header '## ' or end of text
        m2 = re.search(r'\n##\s', text[start:])
        if m2:
            return text[start:start + m2.start()]
        return text[start:]

    # Build status
    build_sec = extract_section(r'^##\s*\[?BUILD\]?')
    if build_sec:
        tokens = re.findall(r'\[?\s*(OK|SUCCESS|PASS|FAILED|FAIL|ERROR)\s*\]?', build_sec, flags=re.I)
        if tokens:
            toks = [t.lower() for t in tokens]
            if any(t in ('fail', 'failed', 'error') for t in toks):
                res['build'] = 'fail'
            elif all(t in ('ok', 'success', 'pass') for t in toks):
                res['build'] = 'ok'
            else:
                res['build'] = 'unknown'

    # Errors section
    err_sec = extract_section(r'^##\s*\[?ERROR\]?')
    if err_sec:
        if re.search(r'no errors detected', err_sec, flags=re.I) or re.search(r'^\s*\[?OK\]?\s*No errors', err_sec, flags=re.I):
            res['errors'] = 'ok'
        elif re.search(r'\b(error|failed|fatal)\b', err_sec, flags=re.I):
            res['errors'] = 'error'
        else:
            # any non-empty content that's not the 'no errors' line -> mark as error
            if re.search(r'\S', err_sec):
                res['errors'] = 'error'

    # Warnings: presence-only. Look for 'Total warnings' or a WARN section or lines starting with WARNING
    if re.search(r'Total\s+warnings\s*[:\-]\s*\d+', text, flags=re.I):
        res['warnings'] = True
    else:
        warn_sec = extract_section(r'^##\s*\[?WARN\]?')
        if warn_sec and re.search(r'\S', warn_sec):
            res['warnings'] = True
        elif re.search(r'^[ \t]*WARNING\b', text, flags=re.M | re.I):
            res['warnings'] = True
        else:
            res['warnings'] = False

    return res


def build_html(root: Path, groups: Dict[str, Dict[str, List[Tuple[Path, str, str]]]], links: Dict) -> str:
    css = """
    body{font-family: Arial, Helvetica, sans-serif;margin:0}
    .wrap{display:flex;height:100vh;}
    .nav{width:320px;overflow:auto;padding:16px;border-right:1px solid #ddd;background:#f8f9fb}
    .content{flex:1;overflow:auto;padding:24px}
    .group{margin-bottom:12px}
    .group h3{margin:6px 0}
    .sublist{margin:6px 0 12px 12px;padding-left:0}
    .sublist li{list-style:none;margin:4px 0}
    .report{margin-bottom:40px}
    .meta{color:#666;font-size:0.9em}
    .status-badge{display:inline-block;padding:4px 8px;margin-left:8px;border-radius:12px;font-weight:700;font-size:0.8em}
    .status-error{background:#f8d7da;color:#721c24}
    .status-fail{background:#fbe5d6;color:#7a3b00}
    .status-warn{background:#fff3cd;color:#856404}
    .status-ok{background:#d4edda;color:#155724}
    .nav a.active{font-weight:700;color:#0a58ca}
    .hl-ok{background:#e6f4ea;color:#0f5132;padding:2px 8px;border-radius:6px;display:inline-block;margin:0 2px 0 2px;font-weight:700}
    .hl-ok::before{content:"✓ ";}
    .hl-warn{background:#fff8e1;color:#6b4f00;padding:2px 8px;border-radius:6px;display:inline-block;margin:0 2px 0 2px;font-weight:700}
    .hl-warn::before{content:"⚠ ";}
    .hl-error{background:#fdecea;color:#7a1416;padding:2px 8px;border-radius:6px;display:inline-block;margin:0 2px 0 2px;font-weight:700}
    .hl-error::before{content:"✖ ";}
    .hl-fail{background:#fff3e0;color:#7a3b00;padding:2px 8px;border-radius:6px;display:inline-block;margin:0 2px 0 2px;font-weight:700}
    .hl-fail::before{content:"✖ ";}
    .hl-crit{background:#ffeef0;color:#6b0b0b;padding:2px 8px;border-radius:6px;display:inline-block;margin:0 2px 0 2px;font-weight:900}
    .hl-crit::before{content:"‼ ";}
    .repo-link{margin-left:12px;font-size:0.9em}
    .search{width:100%;padding:8px;margin-bottom:8px;border:1px solid #ccc;border-radius:4px}
    pre code{background:#272822;color:#f8f8f2;padding:8px;display:block;border-radius:4px}
    @media (max-width:900px){.nav{display:none}}
    """
    js = """
        function toggle(id){
            var el=document.getElementById(id);
            if(!el) return;
            el.style.display = (el.style.display==='none') ? 'block':'none';
        }
        function filterNav(){
            var q=document.getElementById('q').value.toLowerCase();
            var items=document.querySelectorAll('.nav a.report-link');
            items.forEach(function(a){
                var txt=a.textContent.toLowerCase();
                a.parentElement.style.display = txt.indexOf(q)!==-1 ? 'list-item' : 'none';
            });
        }
        function showReport(id, linkId){
            var reports=document.querySelectorAll('.report');
            reports.forEach(function(r){ r.style.display='none'; });
            var el=document.getElementById(id);
            if(!el) return;
            el.style.display='block';
            // highlight active nav
            var navLinks=document.querySelectorAll('.nav a.report-link');
            navLinks.forEach(function(a){ a.classList.remove('active'); });
            if(linkId){
                var la=document.getElementById(linkId);
                if(la) la.classList.add('active');
            }
            window.scrollTo(0,0);
        }
        document.addEventListener('keydown', function(e){ if(e.key==='/' && document.activeElement.id!=='q'){ e.preventDefault(); document.getElementById('q').focus(); }});
        document.addEventListener('DOMContentLoaded', function(){
            // show first report by default
            var first=document.querySelector('.report');
            if(first) first.style.display='block';
            var firstLink=document.querySelector('.nav a.report-link');
            if(firstLink) firstLink.classList.add('active');
        });
        """

    nav_parts = []
    content_parts = []

    for group, subd in groups.items():
        gid = sanitize_id(group)
        nav_parts.append(f'<div class="group"><strong>{html.escape(group)}</strong> <button onclick="toggle(\'g_{gid}\')">▸</button>')
        nav_parts.append(f'<ul id="g_{gid}" class="sublist">')
        for subgroup, reports in sorted(subd.items(), key=lambda kv: natural_key(kv[0])):
            if subgroup:
                nav_parts.append(f'<li style="font-weight:600">{html.escape(subgroup)}</li>')
            for p, title, _ in reports:
                rid = sanitize_id(str(p.relative_to(root)))
                link_id = f'l_{rid}'
                nav_parts.append(f'<li><a id="{link_id}" class="report-link" href="#" onclick="showReport(\'r_{rid}\', \'{link_id}\');return false;">{html.escape(title)}</a></li>')
        nav_parts.append('</ul></div>')

        for subgroup, reports in sorted(subd.items(), key=lambda kv: natural_key(kv[0])):
            for p, title, text in reports:
                rid = sanitize_id(str(p.relative_to(root)))
                try:
                    html_content = md_to_html(text)
                except Exception as e:
                    html_content = '<pre>ERROR converting markdown: %s</pre>' % html.escape(str(e))
                # highlight keywords from the original markdown inside the rendered HTML
                # Use HTMLParser to only touch text nodes (safe for attributes/tags)
                # single combined regex to avoid nested replacements
                token_pat = re.compile(r'(\bCRITICAL\s+WARNING\b|\[ERROR\]|\bERROR\b|\[FAIL\]|\bFAIL\b|\bFAILED\b|\bWARNING\b|\[OK\]|\bOK\b)', flags=re.I)

                def _class_for_token(tok: str) -> str:
                    t = tok.strip()
                    if re.fullmatch(r'critical\s+warning', t, flags=re.I):
                        return 'hl-crit'
                    t = t.upper()
                    if 'ERROR' in t:
                        return 'hl-error'
                    if 'FAIL' in t or 'FAILED' in t:
                        return 'hl-fail'
                    if 'WARNING' in t:
                        return 'hl-warn'
                    if 'OK' in t:
                        return 'hl-ok'
                    return ''

                class _Highlighter(HTMLParser):
                    def __init__(self):
                        super().__init__(convert_charrefs=False)
                        self.out: List[str] = []
                        self.tag_stack: List[str] = []

                    def handle_starttag(self, tag, attrs):
                        # rebuild tag with attributes preserved (do not alter attribute values)
                        s = '<' + tag
                        for k, v in attrs:
                            if v is None:
                                s += f' {k}'
                            else:
                                s += ' ' + k + '="' + html.escape(v, quote=True) + '"'
                        s += '>'
                        self.out.append(s)
                        self.tag_stack.append(tag.lower())

                    def handle_endtag(self, tag):
                        self.out.append(f'</{tag}>')
                        if self.tag_stack and self.tag_stack[-1] == tag.lower():
                            self.tag_stack.pop()

                    def handle_startendtag(self, tag, attrs):
                        s = '<' + tag
                        for k, v in attrs:
                            if v is None:
                                s += f' {k}'
                            else:
                                s += ' ' + k + '="' + html.escape(v, quote=True) + '"'
                        s += '/>'
                        self.out.append(s)

                    def handle_data(self, data):
                        # skip replacements inside code/pre and any headers
                        skip_tags = {'code', 'pre', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6'}
                        if any(tag in skip_tags for tag in self.tag_stack):
                            self.out.append(data)
                            return
                        txt = data
                        # replace tokens in a single pass to avoid wrapping inserted tags
                        def _repl(m):
                            tok = m.group(0)
                            cls = _class_for_token(tok)
                            return f'<span class="{cls}">{tok}</span>' if cls else tok
                        txt = token_pat.sub(_repl, txt)
                        self.out.append(txt)

                    def handle_entityref(self, name):
                        self.out.append('&' + name + ';')

                    def handle_charref(self, name):
                        self.out.append('&#' + name + ';')

                    def handle_comment(self, data):
                        self.out.append('<!--' + data + '-->')

                parser = _Highlighter()
                parser.feed(html_content)
                html_content = ''.join(parser.out)

                # repository link from provided links mapping (show small link)
                repo_url = ''
                try:
                    repo_url = links.get(group, {}).get(subgroup, '')
                except Exception:
                    repo_url = ''
                repo_html = f'<a class="repo-link" href="{html.escape(repo_url)}" target="_blank">Repository</a>' if repo_url else ''

                meta = f'File: {html.escape(str(p))} | Group: {html.escape(group)} {repo_html}'
                content_parts.append(f'<div id="r_{rid}" class="report" style="display:none"><h2>{html.escape(title)}</h2><div class="meta">{meta}</div><div class="md">{html_content}</div></div>')

    nav_html = '\n'.join(nav_parts)
    content_html = '\n'.join(content_parts)

    full = f'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>DE1 Grade Reports</title>
  <style>{css}</style>
</head>
<body>
<a id="top"></a>
<div class="wrap">
  <nav class="nav">
    <input id="q" class="search" placeholder="Search reports (press / to focus)" oninput="filterNav()" />
    {nav_html}
  </nav>
  <main class="content">
    <h1>DE1 Grade Reports</h1>
    {content_html}
  </main>
</div>
<script>{js}</script>
</body>
</html>
'''

    return full


def main():
    root = Path(__file__).parent.resolve()

    if markdown is None:
        print('Missing dependency: Python package "markdown" is required.')
        print('Install with:')
        print('    pip install -r requirements.txt')
        sys.exit(1)

    print('Scanning for de1_grade_report.md files...')
    groups = find_reports(root)
    if not groups:
        print('No de1_grade_report.md files found under', root)
        sys.exit(1)

    # load repository links mapping if available
    links_path = root / 'git_links_de1.json'
    links = {}
    if links_path.exists():
        try:
            links = json.loads(links_path.read_text(encoding='utf-8'))
        except Exception as e:
            print('Warning: failed to parse git_links_de1.json:', e)

    out_html = build_html(root, groups, links)
    out_path = root / 'index_de1_grade_reports.html'
    out_path.write_text(out_html, encoding='utf-8')
    print('Wrote', out_path)


if __name__ == '__main__':
    main()
