#!/usr/bin/env python3
"""
站点构建脚本（Wdd's Blog）。

目录约定（源与产物分离）：
    源目录                       <- 文章源（私有，路径见下方“文章源配置”，不入库）
    docs/                       <- GitHub Pages 发布目录（只放产物）
      index.html                <- 文章列表首页（生成）
      posts/<slug>.html         <- 文章子页面（生成，带大纲侧栏）
      assets/style.css, toc.js

文章源配置（私有，不入库）：
    源目录与源文件名指向一个私有仓库，**不能出现在这个公开仓库里**。
    因此构建配置从下面两个来源读取（不提交）：
      1) 环境变量 BLOG_SRC_DIR（源目录）+ BLOG_SOURCES（源文件名，逗号分隔）；
      2) 一份本地配置文件（默认 blog.local.json，已被 .gitignore 忽略），格式见
         blog.local.example.json。
    环境变量优先于配置文件。两者都缺失则构建报错并给出提示。

slug 规则：取源文件名去掉开头的 ``NN-`` 序号前缀与结尾的源变体后缀（如
    ``-rewrite`` / ``-public``），作为产物文件名与 URL。

每篇文章可选在开头放 front matter：
    ---
    title: 自定义标题
    date: 2026-06-23
    summary: 一句话摘要
    byline: 内容创作：xxx · 审核：xxx
    ---

用法（在仓库根的 .venv 中运行）：
    .venv/bin/python build.py
"""
from __future__ import annotations

import datetime as dt
import html
import json
import os
import re
import sys
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parent
DOCS = ROOT / "docs"
OUT_POSTS = DOCS / "posts"
# 本地（不入库）源配置文件；可用 BLOG_CONFIG 覆盖路径
CONFIG_FILE = Path(os.environ.get("BLOG_CONFIG", ROOT / "blog.local.json"))


def load_sources() -> list[Path]:
    """读取私有源配置，返回每篇文章源的绝对路径列表。环境变量优先，其次本地配置文件。

    这些路径指向私有仓库，刻意不写死在代码里，避免泄漏到这个公开仓库。

    配置形态：
      - 环境变量 BLOG_SRC_DIR + BLOG_SOURCES（逗号分隔的文件名，相对 BLOG_SRC_DIR）；
      - 或本地 JSON：``{"src_dir": ..., "sources": [...]}``，其中 sources 每项可以是
        相对 src_dir 的文件名字符串，也可以是 ``{"path": "/abs/or/rel"}`` 对象
        （path 为绝对路径时跨目录，相对路径时相对 src_dir）。
    """
    env_dir = os.environ.get("BLOG_SRC_DIR")
    env_sources = os.environ.get("BLOG_SOURCES")
    if env_dir and env_sources:
        base = Path(env_dir).expanduser()
        names = [s.strip() for s in env_sources.split(",") if s.strip()]
        return [base / n for n in names]

    if CONFIG_FILE.exists():
        cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        base = Path(cfg["src_dir"]).expanduser() if cfg.get("src_dir") else None
        entries = cfg.get("sources") or []
        if entries:
            resolved: list[Path] = []
            for e in entries:
                raw = e["path"] if isinstance(e, dict) else e
                p = Path(raw).expanduser()
                if not p.is_absolute():
                    if base is None:
                        raise SystemExit(f"✗ 源项 {raw!r} 是相对路径，但配置缺少 src_dir。")
                    p = base / p
                resolved.append(p)
            return resolved

    raise SystemExit(
        "✗ 缺少源配置。请设置环境变量 BLOG_SRC_DIR + BLOG_SOURCES，\n"
        f"  或创建本地配置文件 {CONFIG_FILE.name}（参考 blog.local.example.json，"
        "该文件不会提交到仓库）。"
    )

SITE_TITLE = "Wdd's Blog"
SITE_TAGLINE = "一点点心得和总结"
DEFAULT_BYLINE = "内容创作：wdd · 美化编辑：codex (gpt-5.5) · 审核：wdd"

# ---------------------------------------------------------------------------
# 模板
# ---------------------------------------------------------------------------

ARTICLE_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="{description}">
<title>{title} · {site_title}</title>
<link rel="stylesheet" href="{prefix}assets/style.css">
</head>
<body>
<a class="skip-link" href="#content">跳到正文</a>

<header class="site-header">
  <div class="site-header__inner">
    <a class="site-brand" href="{prefix}index.html">{site_title}</a>
    <button id="toc-toggle" class="toc-toggle" aria-expanded="false" aria-controls="toc">
      <span class="toc-toggle__icon" aria-hidden="true"></span>
      <span class="toc-toggle__label">目录</span>
    </button>
  </div>
  <div class="reading-progress" id="reading-progress"></div>
</header>

<div class="layout">
  <main class="content" id="content">
    <article class="article">
      <header class="article__hero">
        <a class="article__back" href="{prefix}index.html">← 返回文章列表</a>
        <p class="article__eyebrow">{eyebrow}</p>
        <h1 class="article__title">{title}</h1>
        <p class="article__byline">{byline}</p>
        <p class="article__meta">{meta}</p>
      </header>
      {body}
    </article>
    <footer class="site-footer">
      <p><a href="{prefix}index.html">← 返回 {site_title} 文章列表</a></p>
      <p>© {site_title} · 本页由 <code>build.py</code> 从 Markdown 静态渲染。</p>
    </footer>
  </main>

  <aside class="toc-sidebar" id="toc" aria-label="文章大纲">
    <div class="toc-sidebar__inner">
      <p class="toc-sidebar__title">大纲</p>
      <nav class="toc-nav">
        {toc}
      </nav>
    </div>
  </aside>
</div>

<div class="toc-backdrop" id="toc-backdrop" hidden></div>
{mermaid}
<script src="{prefix}assets/toc.js" defer></script>
</body>
</html>
"""

# 仅当文章含 Mermaid 图时注入：加载 mermaid（ESM CDN），按站点明暗主题初始化，
# 并把每张图包进可点开放大的容器。
MERMAID_SNIPPET = """
<script type="module">
  import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs";
  const dark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
  mermaid.initialize({
    startOnLoad: true,
    securityLevel: "strict",
    theme: dark ? "dark" : "neutral",
    flowchart: { useMaxWidth: true, htmlLabels: true, curve: "basis" },
    themeVariables: { fontFamily: "inherit", fontSize: "14px" }
  });
</script>"""

INDEX_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="{site_title} — {tagline}">
<title>{site_title}</title>
<link rel="stylesheet" href="assets/style.css">
</head>
<body>
<a class="skip-link" href="#posts">跳到文章列表</a>

<header class="site-header">
  <div class="site-header__inner">
    <a class="site-brand" href="index.html">{site_title}</a>
  </div>
</header>

<main class="home">
  <header class="home__hero">
    <h1 class="home__title">{site_title}</h1>
    <p class="home__tagline">{tagline}</p>
  </header>

  <section class="post-list" id="posts" aria-label="文章列表">
    {items}
  </section>

  <footer class="site-footer home__footer">
    <p>© {site_title} · 共 {count} 篇 · 由 <code>build.py</code> 静态生成。</p>
  </footer>
</main>
</body>
</html>
"""

POST_ITEM_TEMPLATE = """<article class="post-card">
      <a class="post-card__link" href="{url}">
        <h2 class="post-card__title">{title}</h2>
        <p class="post-card__summary">{summary}</p>
        <p class="post-card__meta"><time datetime="{date}">{date}</time> · {meta}</p>
      </a>
    </article>"""


# ---------------------------------------------------------------------------
# 解析辅助
# ---------------------------------------------------------------------------

def parse_front_matter(text: str) -> tuple[dict, str]:
    meta: dict[str, str] = {}
    if text.startswith("---"):
        m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, flags=re.DOTALL)
        if m:
            for line in m.group(1).splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    meta[k.strip()] = v.strip()
            text = text[m.end():]
    return meta, text


def extract_title(text: str) -> str:
    for line in text.splitlines():
        m = re.match(r"^#\s+(.+?)\s*$", line)
        if m:
            return m.group(1).strip()
    return SITE_TITLE


def extract_lede(text: str) -> str:
    lines = text.splitlines()
    buf: list[str] = []
    for line in lines:
        if line.startswith("> "):
            buf.append(line[2:].strip())
        elif buf:
            break
    if buf:
        return " ".join(buf).strip()
    for line in lines:
        s = line.strip()
        if s and not s.startswith("#") and not s.startswith(">") and not s.startswith("```"):
            return s
    return ""


def strip_md_inline(s: str) -> str:
    s = re.sub(r"`([^`]*)`", r"\1", s)
    s = re.sub(r"\*\*([^*]*)\*\*", r"\1", s)
    s = re.sub(r"\*([^*]*)\*", r"\1", s)
    s = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", s)
    return s.strip()


def count_cn_chars(text: str) -> int:
    return len(re.findall(r"[\u4e00-\u9fff]", text))


def normalize_text_dumps(text: str) -> str:
    """处理“文件内容型” ```text 代码块中嵌套的 ``` 围栏。

    作者用 ```text 内联展示 CLAUDE.md / MAINTENANCE.md 等文件内容，其中
    MAINTENANCE.md 块里又含一段 ``` 围栏（JOURNAL 示例）。同长度围栏无法嵌套，
    标准解析会在内层 ``` 处提前闭合，导致示例里的 `### / ##` 行被当作真实标题，
    污染文章大纲。

    规则：每个 ```text 开栏到“下一个 ```text 开栏（或文末）”为一个区间，区间内
    最后一个裸 ``` 即该块的真实闭栏；其间全部内容（含内层 ``` 与示例标题）按字面
    处理，用 4 反引号围栏重新包裹（可安全容纳内部 3 反引号围栏）。
    """
    lines = text.split("\n")
    openers = [i for i, l in enumerate(lines) if l.strip() == "```text"]
    if not openers:
        return text

    edits = []  # (opener_idx, close_idx, content_lines)
    for k, op in enumerate(openers):
        region_end = openers[k + 1] if k + 1 < len(openers) else len(lines)
        close = None
        for j in range(op + 1, region_end):
            if lines[j].strip() == "```":
                close = j
        if close is None:
            continue
        edits.append((op, close, lines[op + 1:close]))

    for op, close, content in sorted(edits, reverse=True):
        lines[op:close + 1] = ["````text", *content, "````"]
    return "\n".join(lines)


def unwrap_toc(toc_html: str) -> str:
    """剥掉 markdown toc 扩展生成的最外层 <div class="toc"> 包裹。

    toc 扩展输出形如 ``<div class="toc"><ul>…</ul></div>``。侧栏样式用
    ``.toc-nav > ul`` 这类直接子选择器来区分 H2/H3 层级（缩进 + 左引导线），
    但中间多出的 <div> 会让这些选择器全部落空，导致大纲层级被拍平成一级。
    这里把外层 <div class="toc"> 去掉，让 <ul> 直接挂在 .toc-nav 下，层级样式
    才能命中（嵌套的 <ul> 结构本身是对的，无需改动）。
    """
    m = re.match(r'^<div class="toc">\s*(.*?)\s*</div>\s*$', toc_html, flags=re.DOTALL)
    return m.group(1) if m else toc_html


def slugify(stem: str) -> str:
    """源文件名 → 产物 slug：去掉开头 ``NN-`` 序号前缀与结尾的源变体后缀。

    源目录里同一篇文章可能有 ``-rewrite`` / ``-public`` 等变体后缀，slug 统一剥掉，
    例如 ``NN-some-title-rewrite.md`` → ``some-title.html``。
    """
    stem = re.sub(r"^\d+-", "", stem)
    stem = re.sub(r"-(rewrite|public)$", "", stem)
    return stem


DIAGRAMS_DIR = ROOT / "diagrams"
# 框线/箭头字符：纯 ``` 围栏里出现这些字符即判定为「ASCII 流程图」，可换成 Mermaid
_DIAGRAM_CHARS = set("→▶◀├└│┌┐┘▼─‖↓↑←")


def load_diagrams(slug: str) -> dict[str, str]:
    """读取某文的图替换表：{第N个图(字符串) -> Mermaid 源}。无文件则返回空表。"""
    f = DIAGRAMS_DIR / (slug + ".json")
    if not f.exists():
        return {}
    data = json.loads(f.read_text(encoding="utf-8"))
    out: dict[str, str] = {}
    for k, v in data.items():
        if k.startswith("_"):
            continue
        out[k] = "\n".join(v) if isinstance(v, list) else str(v)
    return out


def replace_diagrams(text: str, diagrams: dict[str, str]) -> tuple[str, list[str]]:
    """把正文里第 N 个『ASCII 流程图块』替换成占位符，返回 (新正文, Mermaid 源列表)。

    仅命中「纯 ``` 围栏且含框线/箭头字符」的块；带语言标记的代码块（go/json/sql 等）
    一律不动。占位符在 markdown 渲染后再替换成 <pre class="mermaid">（见 build_post），
    避免 fenced_code 扩展把 Mermaid 源 HTML 转义。
    """
    if not diagrams:
        return text, []
    lines = text.split("\n")
    out_lines: list[str] = []
    mermaids: list[str] = []
    diagram_idx = 0
    i = 0
    while i < len(lines):
        m = re.match(r"^(\s*)```(\w*)\s*$", lines[i])
        if m:
            # 任何围栏块：先完整配对到闭栏（闭栏是裸 ```），避免把闭栏误判成新开栏。
            lang = m.group(2)
            j = i + 1
            while j < len(lines) and lines[j].strip() != "```":
                j += 1
            body = lines[i + 1:j]  # j 指向闭栏（或越界）
            is_diagram = (not lang) and any(
                ch in _DIAGRAM_CHARS for ch in "\n".join(body)
            )
            if is_diagram and j < len(lines):
                key = str(diagram_idx)
                diagram_idx += 1
                if key in diagrams:
                    # 独占一行的占位段落，markdown 会原样保留成 <p>TOKEN</p>，
                    # 渲染后再换成 <pre class="mermaid">。
                    out_lines += ["", f"DIAGRAMPLACEHOLDER{len(mermaids)}END", ""]
                    mermaids.append(diagrams[key])
                    i = j + 1
                    continue
            # 非图块（或没给 Mermaid 的图）：整块原样拷贝，并跳过闭栏。
            out_lines += lines[i:j + 1]
            i = j + 1
            continue
        out_lines.append(lines[i])
        i += 1
    return "\n".join(out_lines), mermaids


def inject_mermaid(body_html: str, mermaids: list[str]) -> str:
    """把渲染后正文里的占位符换成 <pre class="mermaid"> 块（含原图的可访问降级）。"""
    for idx, src in enumerate(mermaids):
        block = f'<pre class="mermaid">\n{html.escape(src)}\n</pre>'
        # 占位符可能被包成 <p>…</p>，一并替掉
        body_html = re.sub(
            rf"(?:<p>)?\s*DIAGRAMPLACEHOLDER{idx}END\s*(?:</p>)?",
            lambda _m, b=block: b,
            body_html,
            count=1,
        )
    return body_html


def truncate(s: str, n: int) -> str:
    return (s[:n] + "…") if len(s) > n else s


# ---------------------------------------------------------------------------
# 构建
# ---------------------------------------------------------------------------

def new_md() -> markdown.Markdown:
    return markdown.Markdown(
        extensions=["extra", "toc", "sane_lists", "admonition"],
        extension_configs={"toc": {"anchorlink": True, "toc_depth": "2-3"}},
        output_format="html5",
    )


def build_post(src: Path) -> dict:
    raw = src.read_text(encoding="utf-8")
    fm, text = parse_front_matter(raw)

    slug = slugify(src.stem)
    text, mermaids = replace_diagrams(text, load_diagrams(slug))

    md = new_md()
    body_html = md.convert(normalize_text_dumps(text))
    body_html = re.sub(r"^\s*<h1[^>]*>.*?</h1>\s*", "", body_html, count=1, flags=re.DOTALL)
    body_html = inject_mermaid(body_html, mermaids)
    toc_html = unwrap_toc(getattr(md, "toc", "").strip())

    title = fm.get("title") or extract_title(text)
    lede = strip_md_inline(fm.get("summary") or extract_lede(text))
    description = truncate(lede, 140) or title

    cn = count_cn_chars(text)
    read_min = max(1, round(cn / 350))
    meta_line = f"约 {cn} 字 · 阅读约 {read_min} 分钟"

    date = fm.get("date") or dt.date.fromtimestamp(src.stat().st_mtime).isoformat()

    OUT_POSTS.mkdir(parents=True, exist_ok=True)
    out = OUT_POSTS / (slug + ".html")
    page = ARTICLE_TEMPLATE.format(
        site_title=html.escape(SITE_TITLE),
        title=html.escape(title),
        description=html.escape(description),
        eyebrow="工程笔记",
        byline=html.escape(fm.get("byline", DEFAULT_BYLINE)),
        meta=html.escape(meta_line),
        body=body_html,
        toc=toc_html or "<p class=\"toc-empty\">（无小节）</p>",
        prefix="../",
        mermaid=MERMAID_SNIPPET if mermaids else "",
    )
    out.write_text(page, encoding="utf-8")

    return {
        "title": title,
        "summary": truncate(lede, 110),
        "date": date,
        "meta": meta_line,
        "url": f"posts/{out.name}",
        "out": out,
    }


def build_index(posts: list[dict]) -> Path:
    posts_sorted = sorted(posts, key=lambda p: p["date"], reverse=True)
    items = "\n    ".join(
        POST_ITEM_TEMPLATE.format(
            url=html.escape(p["url"]),
            title=html.escape(p["title"]),
            summary=html.escape(p["summary"]),
            date=html.escape(p["date"]),
            meta=html.escape(p["meta"]),
        )
        for p in posts_sorted
    )
    page = INDEX_TEMPLATE.format(
        site_title=html.escape(SITE_TITLE),
        tagline=html.escape(SITE_TAGLINE),
        items=items or "<p class=\"toc-empty\">暂无文章。</p>",
        count=len(posts_sorted),
    )
    out = DOCS / "index.html"
    out.write_text(page, encoding="utf-8")
    return out


def main() -> int:
    sources = load_sources()
    missing = [s for s in sources if not s.exists()]
    if missing:
        for s in missing:
            print(f"✗ 发布清单中的源文件不存在: {s}", file=sys.stderr)
        return 1

    posts = []
    for src in sources:
        info = build_post(src)
        posts.append(info)
        print(f"  ✓ 文章: {info['out'].relative_to(ROOT)}  «{info['title']}»  {info['date']}")

    index = build_index(posts)
    print(f"✓ 首页: {index.relative_to(ROOT)}  (共 {len(posts)} 篇)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
