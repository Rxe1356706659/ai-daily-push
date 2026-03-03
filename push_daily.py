"""
AI 情报中心 — GitHub Actions 每日推送脚本
功能：搜索最新 AI 动态 → 整理成情报 → 推送到微信
运行环境：GitHub Actions（无需本地电脑开机）
"""

import json
import os
import sys
import urllib.request
import urllib.parse
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta


# ============================================================
# 配置
# ============================================================

# Server酱 SendKey（从 GitHub Secrets 读取）
SERVERCHAN_KEY = os.environ.get("SERVERCHAN_KEY", "")

# 北京时间
BEIJING_TZ = timezone(timedelta(hours=8))

# AI 新闻 RSS 源（免费、无需 API Key）
RSS_FEEDS = [
    {
        "name": "Google AI Blog",
        "url": "https://blog.google/technology/ai/rss/",
        "category": "AI通用",
    },
    {
        "name": "OpenAI Blog",
        "url": "https://openai.com/blog/rss.xml",
        "category": "AI通用",
    },
    {
        "name": "MIT Technology Review AI",
        "url": "https://www.technologyreview.com/topic/artificial-intelligence/feed",
        "category": "AI通用",
    },
    {
        "name": "The Verge AI",
        "url": "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml",
        "category": "AI通用",
    },
    {
        "name": "Ars Technica AI",
        "url": "https://feeds.arstechnica.com/arstechnica/technology-lab",
        "category": "AI通用",
    },
]

# 追踪的关键词（与用户业务相关）
KEYWORDS = [
    # AI 视频
    "Kling", "可灵", "Runway", "Veo", "Pika", "Sora", "video generation",
    "AI video", "Seedance", "HeyGen", "digital human",
    # AI 图片
    "Nano Banana", "Midjourney", "FLUX", "Stable Diffusion", "ComfyUI",
    "image generation", "AI image", "DALL-E", "Ideogram", "Seedream",
    # AI 自动化
    "n8n", "AI agent", "MCP", "automation", "workflow",
    # 跨境电商
    "e-commerce AI", "Amazon AI", "Shopify AI", "TikTok Shop",
    # 大模型
    "GPT", "Claude", "Gemini", "DeepSeek", "Llama", "Qwen",
    "LLM", "language model", "multimodal",
]


# ============================================================
# RSS 抓取
# ============================================================

def fetch_rss(url, timeout=10):
    """抓取 RSS 源，返回条目列表"""
    try:
        req = urllib.request.Request(url)
        req.add_header("User-Agent", "Mozilla/5.0 AI-Intelligence-Bot/1.0")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content = resp.read()
        root = ET.fromstring(content)

        items = []
        # 支持 RSS 2.0 和 Atom 格式
        for item in root.iter("item"):
            entry = {
                "title": (item.findtext("title") or "").strip(),
                "link": (item.findtext("link") or "").strip(),
                "description": (item.findtext("description") or "").strip(),
                "pubDate": (item.findtext("pubDate") or "").strip(),
            }
            if entry["title"]:
                items.append(entry)

        # Atom 格式
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        for entry_el in root.findall(".//atom:entry", ns):
            title_el = entry_el.find("atom:title", ns)
            link_el = entry_el.find("atom:link", ns)
            summary_el = entry_el.find("atom:summary", ns)
            published_el = entry_el.find("atom:published", ns)
            entry = {
                "title": (title_el.text if title_el is not None else "").strip(),
                "link": (link_el.get("href", "") if link_el is not None else "").strip(),
                "description": (summary_el.text if summary_el is not None else "").strip(),
                "pubDate": (published_el.text if published_el is not None else "").strip(),
            }
            if entry["title"]:
                items.append(entry)

        return items[:10]  # 最多取 10 条
    except Exception as e:
        print(f"[RSS] Failed to fetch {url}: {e}")
        return []


def is_relevant(item):
    """检查条目是否与我们关注的关键词相关"""
    text = (item.get("title", "") + " " + item.get("description", "")).lower()
    for kw in KEYWORDS:
        if kw.lower() in text:
            return True
    return False


def collect_intelligence():
    """从所有 RSS 源收集与 AI 相关的情报"""
    all_items = []

    for feed in RSS_FEEDS:
        print(f"[RSS] Fetching: {feed['name']}...")
        items = fetch_rss(feed["url"])
        for item in items:
            item["source"] = feed["name"]
            item["category"] = feed["category"]
        all_items.extend(items)

    # 筛选相关条目
    relevant = [item for item in all_items if is_relevant(item)]

    # 如果没有相关的，取所有来源的前 3 条
    if not relevant:
        relevant = all_items[:8]

    # 去重（按标题）
    seen_titles = set()
    unique = []
    for item in relevant:
        if item["title"] not in seen_titles:
            seen_titles.add(item["title"])
            unique.append(item)

    return unique[:10]  # 最多 10 条


# ============================================================
# 格式化
# ============================================================

def format_intelligence(items):
    """将情报条目格式化为推送内容"""
    now = datetime.now(BEIJING_TZ)
    today = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M")

    title = f"AI日报 | {today}"

    parts = []
    parts.append(f"> {today} AI 情报自动推送\n")

    if not items:
        parts.append("今日暂未抓取到与你业务相关的 AI 新动态。\n")
        parts.append("请在 Antigravity 中与我对话，获取更精准的情报分析。")
    else:
        # 按来源分组
        for i, item in enumerate(items, 1):
            source = item.get("source", "Unknown")
            link = item.get("link", "")
            desc = item.get("description", "")
            # 清理 HTML 标签
            import re
            desc = re.sub(r"<[^>]+>", "", desc)
            if len(desc) > 150:
                desc = desc[:147] + "..."

            parts.append(f"### {i}. {item['title']}\n")
            parts.append(f"- **来源**：{source}")
            if link:
                parts.append(f"- **链接**：[点击查看]({link})")
            if desc:
                parts.append(f"- **摘要**：{desc}")
            parts.append("")

    parts.append("---")
    parts.append(f"*推送时间：{time_str} | 关键词追踪：AI视频/图片/自动化/电商/大模型*")
    parts.append(f"*详细分析请在 Antigravity 中与我对话*")

    body = "\n".join(parts)
    return title, body


# ============================================================
# 推送
# ============================================================

def push_serverchan(send_key, title, content):
    """通过 Server酱推送到微信"""
    url = f"https://sctapi.ftqq.com/{send_key}.send"
    data = urllib.parse.urlencode({
        "title": title,
        "desp": content,
        "channel": "9"
    }).encode("utf-8")

    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            if result.get("code") == 0:
                print(f"[Server] push OK: {title}")
                return True
            else:
                print(f"[Server] push FAIL: {result}")
                return False
    except Exception as e:
        print(f"[Server] push ERROR: {e}")
        return False


# ============================================================
# 主函数
# ============================================================

def main():
    now = datetime.now(BEIJING_TZ)
    print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')} CST] AI 情报每日推送开始...")

    # 检查 SendKey
    if not SERVERCHAN_KEY:
        print("[ERROR] SERVERCHAN_KEY not set in environment")
        sys.exit(1)

    # Step 1: 收集情报
    print("[Step 1] 收集 AI 动态...")
    items = collect_intelligence()
    print(f"[Step 1] 收集到 {len(items)} 条相关情报")

    # Step 2: 格式化
    print("[Step 2] 格式化推送内容...")
    title, body = format_intelligence(items)

    # Step 3: 推送
    print("[Step 3] 推送到微信...")
    success = push_serverchan(SERVERCHAN_KEY, title, body)

    if success:
        print("[DONE] push SUCCESS")
    else:
        print("[DONE] push FAILED")
        sys.exit(1)


if __name__ == "__main__":
    main()
