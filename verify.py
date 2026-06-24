#!/usr/bin/env python3
"""校验生成结果：首页文章列表 + posts 子页面（结构、锚点、目录、资源路径）。"""
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

import build  # 复用源配置与 slug 规则，避免两处不一致

ROOT = Path(__file__).resolve().parent
DOCS = ROOT / "docs"
INDEX = DOCS / "index.html"
POSTS = build.load_sources()

errors, warnings, oks = [], [], []


class Collector(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack = []
        self.ids = set()
        self.toc_hrefs = []
        self.in_toc = 0
        self.counts = {}
        self.void = {"meta", "link", "br", "img", "hr", "input", "source"}

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        self.counts[tag] = self.counts.get(tag, 0) + 1
        if tag not in self.void:
            self.stack.append(tag)
        if "id" in a:
            self.ids.add(a["id"])
        if tag == "nav" and "toc-nav" in a.get("class", ""):
            self.in_toc += 1
        if self.in_toc and tag == "a" and a.get("href", "").startswith("#"):
            self.toc_hrefs.append(a["href"][1:])

    def handle_endtag(self, tag):
        if tag == "nav" and self.in_toc:
            self.in_toc -= 1
        if tag in self.void:
            return
        if tag in self.stack:
            while self.stack and self.stack.pop() != tag:
                pass


def parse(path):
    p = Collector()
    p.feed(path.read_text(encoding="utf-8"))
    return p


# ---------- 首页 ----------
idx_raw = INDEX.read_text(encoding="utf-8")
idx = parse(INDEX)

if "{" + "items" + "}" in idx_raw or re.search(r"\{(site_title|tagline|count)\}", idx_raw):
    errors.append("首页存在未替换占位符")
else:
    oks.append("首页无残留占位符")

cards = idx_raw.count('class="post-card"')
links = re.findall(r'class="post-card__link" href="([^"]+)"', idx_raw)
if cards == len(POSTS) and cards >= 1:
    oks.append(f"首页列出 {cards} 篇文章卡片（与 posts/*.md 数 {len(POSTS)} 一致）")
else:
    errors.append(f"首页卡片数={cards}，posts/*.md 数={len(POSTS)}")

# 首页每个链接指向存在的子页面
for href in links:
    target = (DOCS / href).resolve()
    if target.exists():
        oks.append(f"首页链接有效: {href}")
    else:
        errors.append(f"首页链接指向不存在的文件: {href}")

if 'assets/style.css' in idx_raw and (DOCS / "assets/style.css").exists():
    oks.append("首页资源路径正确: assets/style.css")
else:
    errors.append("首页资源路径异常")

# ---------- 子页面 ----------
for src in POSTS:
    html_path = DOCS / "posts" / (build.slugify(src.stem) + ".html")
    if not html_path.exists():
        errors.append(f"缺少子页面: {html_path.name}")
        continue
    raw = html_path.read_text(encoding="utf-8")
    p = parse(html_path)
    name = html_path.name

    # 大纲嵌套：附录的 H3 子项应在嵌套 <ul> 内（不与 H2 同级）
    toc_m = re.search(r'<nav class="toc-nav">(.*?)</nav>', raw, re.DOTALL)
    if toc_m and "<ul>" in toc_m.group(1):
        nested = toc_m.group(1).count("<ul>")
        if nested >= 2:
            oks.append(f"[{name}] 大纲存在嵌套层级（<ul>×{nested}，H3 归入上级 H2）")
        else:
            warnings.append(f"[{name}] 大纲无嵌套层级（<ul>×{nested}）")

    if re.search(r"\{(body|toc|title|prefix|meta|description)\}", raw):
        errors.append(f"[{name}] 残留占位符")
    else:
        oks.append(f"[{name}] 无残留占位符")

    if p.stack:
        warnings.append(f"[{name}] 标签栈残留: {p.stack[-4:]}")
    else:
        oks.append(f"[{name}] 标签闭合正常")

    # 大纲锚点
    uniq = list(dict.fromkeys(p.toc_hrefs))
    missing = [h for h in uniq if h not in p.ids]
    if uniq and not missing:
        oks.append(f"[{name}] 大纲 {len(uniq)} 链接全部命中锚点")
    elif not uniq:
        errors.append(f"[{name}] 无大纲链接")
    else:
        errors.append(f"[{name}] 大纲缺锚点: {missing}")

    # 资源用 ../ 前缀且文件存在
    for asset in ["../assets/style.css", "../assets/toc.js"]:
        if asset in raw and (html_path.parent / asset).resolve().exists():
            oks.append(f"[{name}] 资源路径正确: {asset}")
        else:
            errors.append(f"[{name}] 资源路径异常: {asset}")

    # 返回首页链接
    if '../index.html' in raw:
        oks.append(f"[{name}] 含返回首页链接")
    else:
        errors.append(f"[{name}] 缺少返回首页链接")

    # 结构件
    for sel, label in [("toc-sidebar", "大纲侧栏"), ("reading-progress", "进度条"),
                       ("article__title", "标题块")]:
        if sel not in raw:
            errors.append(f"[{name}] 缺少{label}")

    if p.counts.get("h1", 0) != 1:
        warnings.append(f"[{name}] H1 数量={p.counts.get('h1',0)}（预期1）")
    else:
        oks.append(f"[{name}] 恰 1 个 H1")
    # 表格/代码块是否存在取决于文章内容，缺失不算错误（纯叙述文可以没有）
    if p.counts.get("table", 0) == 0:
        warnings.append(f"[{name}] 无表格（文章不含表格时正常）")
    if p.counts.get("pre", 0) == 0:
        warnings.append(f"[{name}] 无代码块（文章不含代码块时正常）")

# ---------- 报告 ----------
print("=== OK ===")
for o in oks:
    print("  ✓", o)
if warnings:
    print("=== 警告 ===")
    for w in warnings:
        print("  ⚠", w)
if errors:
    print("=== 错误 ===")
    for e in errors:
        print("  ✗", e)
    sys.exit(1)
print("\n全部关键检查通过。")
