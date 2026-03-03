"""
AI 情报中心 — GitHub Actions 每日推送脚本（中文详细版）
功能：搜索中文 AI 动态 → Gemini 深度分析 → 推送详细中文情报到微信
运行环境：GitHub Actions（无需本地电脑开机）
"""

import json
import os
import re
import sys
import urllib.request
import urllib.parse
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta


# ============================================================
# 配置
# ============================================================

SERVERCHAN_KEY = os.environ.get("SERVERCHAN_KEY", "")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

BEIJING_TZ = timezone(timedelta(hours=8))

# 中文 + 英文 AI 资讯 RSS 源
RSS_FEEDS = [
    {"name": "机器之心", "url": "https://www.jiqizhixin.com/rss", "lang": "zh"},
    {"name": "量子位", "url": "https://www.qbitai.com/feed", "lang": "zh"},
    {"name": "36氪AI", "url": "https://36kr.com/feed", "lang": "zh"},
    {"name": "Google AI Blog", "url": "https://blog.google/technology/ai/rss/", "lang": "en"},
    {"name": "The Verge AI", "url": "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml", "lang": "en"},
    {"name": "Ars Technica", "url": "https://feeds.arstechnica.com/arstechnica/technology-lab", "lang": "en"},
]

# 业务关键词
KEYWORDS = [
    "Kling", "可灵", "Runway", "Veo", "Pika", "Sora", "视频生成", "AI视频",
    "Seedance", "HeyGen", "数字人", "Nano Banana", "Midjourney", "FLUX",
    "Stable Diffusion", "ComfyUI", "图片生成", "AI图片", "AI绘画", "文生图",
    "DALL-E", "Ideogram", "Seedream", "n8n", "AI Agent", "智能体", "MCP",
    "自动化", "工作流", "电商", "Amazon", "Shopify", "TikTok Shop", "跨境",
    "GPT", "Claude", "Gemini", "DeepSeek", "Llama", "Qwen", "通义",
    "大模型", "多模态", "开源模型", "AI", "人工智能",
]

# Gemini 分析提示词
ANALYSIS_PROMPT = """你是一位 AI 情报分析师，服务于一位在跨境电商公司担任 AI 视频设计师 & AI 赋能规划师的用户。

用户的核心业务：
- 信息流 AI 视频制作（用于独立站投流）
- TVC 品牌广告片
- 企业 AI 赋能培训（美工组/运营组）
- 跨境电商运营（亚马逊/TikTok Shop）
- AI 自动化流程建设

请根据以下 AI 新闻标题和摘要，生成一份**中文 AI 日报**。

要求：
1. 从中筛选出最重要的 3-5 条情报
2. 每条情报按以下格式输出：

## 情报 N：[中文标题]

- **来源**：[新闻来源名称和链接]
- **类型**：视频 / 图片 / 自动化 / 电商 / 通用
- **关键信息**：用一段话详细描述核心内容（至少 50 字）
- **技术细节**：补充关键的技术参数、版本号、对比数据等
- **对我的价值**：
  - 工作方面：具体分析这条信息如何应用到用户的工作中
  - 生活方面：是否有个人使用价值
- **行动建议**：立即尝试 / 加入学习计划 / 持续观察 / 仅了解

3. 最后输出"今日小结"：
## 今日小结
- **最有价值的发现**：列出 1-3 个
- **需要行动的项目**：具体行动
- **值得关注的趋势**：行业趋势性判断

请确保内容丰富、分析深入、与用户业务紧密相关。如果某条新闻是英文的，请翻译成中文并分析。

以下是今天的 AI 新闻：

{news_content}
"""


# ============================================================
# RSS 抓取
# ============================================================

def fetch_rss(url, timeout=10):
    """抓取 RSS 源"""
    try:
        req = urllib.request.Request(url)
        req.add_header("User-Agent", "Mozilla/5.0 AI-Intelligence-Bot/1.0")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content = resp.read()
        root = ET.fromstring(content)

        items = []
        # RSS 2.0
        for item in root.iter("item"):
            entry = {
                "title": (item.findtext("title") or "").strip(),
                "link": (item.findtext("link") or "").strip(),
                "description": (item.findtext("description") or "").strip(),
            }
            if entry["title"]:
                items.append(entry)

        # Atom
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        for entry_el in root.findall(".//atom:entry", ns):
            title_el = entry_el.find("atom:title", ns)
            link_el = entry_el.find("atom:link", ns)
            summary_el = entry_el.find("atom:summary", ns)
            entry = {
                "title": (title_el.text if title_el is not None else "").strip(),
                "link": (link_el.get("href", "") if link_el is not None else "").strip(),
                "description": (summary_el.text if summary_el is not None else "").strip(),
            }
            if entry["title"]:
                items.append(entry)

        return items[:10]
    except Exception as e:
        print(f"[RSS] Failed: {url} -> {e}")
        return []


def is_relevant(item):
    """关键词匹配"""
    text = (item.get("title", "") + " " + item.get("description", "")).lower()
    for kw in KEYWORDS:
        if kw.lower() in text:
            return True
    return False


def collect_news():
    """收集新闻"""
    all_items = []
    for feed in RSS_FEEDS:
        print(f"[RSS] {feed['name']}...")
        items = fetch_rss(feed["url"])
        for item in items:
            item["source"] = feed["name"]
            # 清理 HTML
            desc = item.get("description", "")
            desc = re.sub(r"<[^>]+>", "", desc).strip()
            if len(desc) > 300:
                desc = desc[:300] + "..."
            item["description"] = desc
        all_items.extend(items)

    # 筛选相关的
    relevant = [i for i in all_items if is_relevant(i)]
    if len(relevant) <3:
        relevant = all_items[:15]

    # 去重
    seen = set()
    unique = []
    for item in relevant:
        if item["title"] not in seen:
            seen.add(item["title"])
            unique.append(item)

    return unique[:15]


# ============================================================
# Gemini 分析
# ============================================================

def analyze_with_gemini(news_items):
    """用 Gemini API 生成详细中文情报分析"""
    if not GEMINI_API_KEY:
        print("[Gemini] No API key, using simple format")
        return None

    # 构建新闻内容
    news_text = ""
    for i, item in enumerate(news_items, 1):
        news_text += f"\n{i}. 标题：{item['title']}\n"
        news_text += f"   来源：{item['source']}\n"
        if item.get("link"):
            news_text += f"   链接：{item['link']}\n"
        if item.get("description"):
            news_text += f"   摘要：{item['description']}\n"

    prompt = ANALYSIS_PROMPT.format(news_content=news_text)

    # 调用 Gemini API
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 4096,
        }
    }).encode("utf-8")

    req = urllib.request.Request(url, data=payload, method="POST")
    req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            text = result["candidates"][0]["content"]["parts"][0]["text"]
            print(f"[Gemini] Analysis done, {len(text)} chars")
            return text
    except Exception as e:
        print(f"[Gemini] ERROR: {e}")
        return None


# ============================================================
# 简单格式化（无 Gemini 时降级使用）
# ============================================================

def simple_format(news_items):
    """当 Gemini 不可用时的中文格式化"""
    now = datetime.now(BEIJING_TZ)
    parts = []

    for i, item in enumerate(news_items[:8], 1):
        parts.append(f"### {i}. {item['title']}\n")
        parts.append(f"- **来源**：{item['source']}")
        if item.get("link"):
            parts.append(f"- **链接**：[查看原文]({item['link']})")
        if item.get("description"):
            parts.append(f"- **摘要**：{item['description']}")
        parts.append("")

    if not parts:
        parts.append("今日暂未抓取到 AI 新动态。")

    return "\n".join(parts)


# ============================================================
# 推送
# ============================================================

def push_serverchan(send_key, title, content):
    """通过 Server酱推送"""
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
    today = now.strftime("%Y-%m-%d")
    print(f"[{now.strftime('%Y-%m-%d %H:%M:%S')} CST] AI 情报每日推送开始...")

    if not SERVERCHAN_KEY:
        print("[ERROR] SERVERCHAN_KEY not set")
        sys.exit(1)

    # Step 1: 收集新闻
    print("[Step 1] 收集 AI 动态...")
    news_items = collect_news()
    print(f"[Step 1] 收集到 {len(news_items)} 条")

    # Step 2: 分析生成情报
    print("[Step 2] 生成情报分析...")
    analysis = analyze_with_gemini(news_items)

    if analysis:
        # Gemini 生成的详细分析
        title = f"AI日报 | {today}"
        body = f"> {today} AI 情报自动推送（Gemini 深度分析）\n\n"
        body += f"> 今日关键词：`AI视频` `AI图片` `大模型` `自动化` `跨境电商`\n\n---\n\n"
        body += analysis
        body += f"\n\n---\n*推送时间：{now.strftime('%H:%M')} | 由 GitHub Actions + Gemini 自动生成*\n"
        body += "*详细分析请在 Antigravity 中与我对话*"
    else:
        # 降级：简单格式化
        title = f"AI日报 | {today}"
        body = f"> {today} AI 情报自动推送\n\n"
        body += simple_format(news_items)
        body += f"\n---\n*推送时间：{now.strftime('%H:%M')} | 由 GitHub Actions 自动生成*\n"
        body += "*提示：配置 GEMINI_API_KEY 可获得更详细的中文分析*"

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
