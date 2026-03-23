#!/usr/bin/env python3
"""从完整归档页或当前 index 提取正文，写出带目录与 doc-reader.css 的优化版。"""
import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
INDEX = ROOT / "index.html"
FULL_BACKUP = ROOT / "index.full.html"


def extract_ne_viewer_body_div_depth(html: str) -> str:
    """仅按 div 深度截断（正文内大量嵌套 div 时易提前结束，仅作兜底）。"""
    marker = '<div class="ne-viewer-body">'
    start = html.find(marker)
    if start == -1:
        raise ValueError("未找到 ne-viewer-body")
    i = start + len(marker)
    depth = 1
    chunks = []
    n = len(html)
    while i < n and depth > 0:
        if html[i] == "<":
            if html.startswith("</div>", i):
                depth -= 1
                if depth == 0:
                    break
                chunks.append("</div>")
                i += 6
                continue
            if re.match(r"<div\b", html[i:]):
                depth += 1
                j = html.find(">", i)
                chunks.append(html[i : j + 1])
                i = j + 1
                continue
            j = html.find(">", i)
            chunks.append(html[i : j + 1])
            i = j + 1
        else:
            j = html.find("<", i)
            chunks.append(html[i:j])
            i = j
    return "".join(chunks)


def extract_ne_viewer_body(html: str) -> str:
    """优先用「正文容器闭合」定位，避免卡片内 </div> 导致截断错误。"""
    m = re.search(
        r'<div class="ne-viewer-body">\s*([\s\S]*)\s*</div>\s*</article>',
        html,
    )
    if m:
        return m.group(1).strip()
    return extract_ne_viewer_body_div_depth(html)


def normalize_inner(inner: str) -> str:
    inner = re.sub(r"\sne-image-hide\b", "", inner)
    inner = inner.replace("websocket-midsev", "websocket-midserv")
    # 语雀「六.测试用例」下：行内文件条 + 嵌入式预览（离线常显示为空框）
    # 注意：[\s\S]*? 不能跨多个 ne-p，否则会吞掉从文档首段到该附件之间的全部正文
    inner = re.sub(
        r'<ne-p[^>]*>(?:(?!</ne-p>).)*?<ne-card data-card-name="file"[\s\S]*?</ne-card>[\s\S]*?</ne-p>',
        "",
        inner,
        count=1,
    )
    inner = re.sub(r"<ne-hole[^>]*>[\s\S]*?</ne-hole>", "", inner, count=1)
    return inner


def extract_lead(_inner: str) -> str:
    """顶栏摘要：不与正文首段逐字重复，概括结构即可。"""
    return (
        "离线归档。左侧为目录，正文含服务拆分、流程图、中间件与存储选型、"
        "接口设计、上线步骤、测试用例与异常定位等。"
    )


def build_toc(inner: str) -> str:
    heads = []
    for m in re.finditer(
        r'<ne-h([123]) id="([^"]+)"[^>]*>([\s\S]*?)</ne-h\1>', inner
    ):
        level, hid, block = m.group(1), m.group(2), m.group(3)
        t = re.sub(r"<[^>]+>", " ", block)
        t = re.sub(r"\s+", " ", t).strip()
        t = re.sub(r"\s+：$", "：", t)
        t = re.sub(r"\s*：\s*", "：", t)
        if not t or len(t) > 120:
            continue
        heads.append((level, hid, t))
    lines = ['        <p class="doc-toc-title">目录</p>', "        <nav>"]
    for level, hid, t in heads:
        cls = f"toc-h{level}"
        safe = html_escape(t)
        lines.append(f'          <a class="{cls}" href="#{hid}">{safe}</a>')
    lines.append("        </nav>")
    return "\n".join(lines)


def html_escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def build_page(inner: str) -> str:
    lead = extract_lead(inner)
    toc = build_toc(inner)
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="light">
  <title>聊天系统技术文档</title>
  <link rel="stylesheet" href="./doc-reader.css">
</head>
<body>
  <div class="doc-app">
    <header class="doc-header">
      <div class="doc-header-inner">
        <h1 class="doc-title">聊天系统技术文档</h1>
        <p class="doc-lead">{html_escape(lead)}</p>
      </div>
    </header>

    <div class="doc-layout">
      <aside class="doc-toc" aria-label="文档目录">
{toc}
      </aside>

      <main class="doc-main">
        <div class="doc-paper">
          <article class="ne-viewer lakex-yuque-theme-light ne-typography-traditional" id="doc">
            <div class="ne-viewer-body">
{inner}
            </div>
          </article>
        </div>
      </main>
    </div>
  </div>
</body>
</html>
"""


def load_source_and_inner() -> str:
    """优先 index.full.html（完整语雀页），否则当前 index。"""
    candidates = []
    if FULL_BACKUP.exists():
        candidates.append(FULL_BACKUP.read_text(encoding="utf-8", errors="replace"))
    if INDEX.exists():
        candidates.append(INDEX.read_text(encoding="utf-8", errors="replace"))

    last_err = None
    for raw in candidates:
        try:
            inner = extract_ne_viewer_body(raw)
            if len(inner) > 500:
                return normalize_inner(inner)
        except ValueError as e:
            last_err = e
    raise SystemExit(
        last_err or "无法从 index.html / index.full.html 解析正文，请保留完整语雀离线页。"
    )


def main() -> None:
    inner = load_source_and_inner()
    if INDEX.exists() and not FULL_BACKUP.exists():
        try:
            t = INDEX.read_text(encoding="utf-8", errors="replace")
            if "ne-viewer-body" in t and len(t) > 400000:
                shutil.copy2(INDEX, FULL_BACKUP)
        except OSError:
            pass

    page = build_page(inner)
    INDEX.write_text(page, encoding="utf-8")
    n_toc = page.count('<a class="toc-')
    print(f"已写入 {INDEX}，约 {len(inner)} 字符正文，目录 {n_toc} 项。")


if __name__ == "__main__":
    main()
