"""
Financial news cleaning and briefing utilities.

This module turns raw SearchFinancialNews MCP payloads into a concise,
LLM-ready Markdown brief using the configured project LLM.
"""

from __future__ import annotations

import html
import json
import os
import re
from datetime import datetime, timedelta
from difflib import SequenceMatcher
from typing import Any

from utils.config import load_config


NEWS_CLEANING_SYSTEM_PROMPT = """
你是一个专业的金融数据清洗专家。输入是已经完成结构化降噪与时间窗聚类的快讯簇。

### 核心任务流程
1. 结构化降噪：只保留核心事实、数值、时间和来源。
2. 语义合并：同一事件必须合并，来源用 "/" 分隔；如果多条快讯只是同一事件的不同标题、不同媒体口径、不同人物视角，必须合并为一条综合摘要。
3. 主体锚定：站在查询核心实体的立场判断；同领域竞争对手增强、替代方案出现、份额流失、客户被分流一律偏 [利空]。如果新闻里出现“合作”“再出奇招”“重磅客户”等积极词汇，但主语是竞对或替代方案，也不能判为核心实体利好。
4. 特征增强：补充涉及实体、情绪标签和逻辑标签。
5. 数值保护：严禁改动任何百分比、金额、时间节点。

### 合并偏好
- 同一时间窗内，如果多条快讯围绕同一核心事件展开，优先合并，不要逐条输出。
- 会议、会见、政策发布、发布会、财报解读、公告解读这类新闻，只要核心事件相同，就不要按不同人物或不同媒体拆成多条。
- 如果不能确定是否完全同一事件，仍优先合并成一条更完整的摘要，避免浪费 token。

### 输出要求
- 只能输出 JSON 数组，严禁输出 Markdown、解释、前言或总结。
- 每个对象必须包含：
  - time
  - source
  - title
  - summary
  - entities
  - emotion
  - logic
- summary 必须是单行，尽量保留核心动词和数值，不要写成长段落。
- entities 必须写具体对象；如有多个，用 "/" 或列表表达。
- emotion 只能是 [利好] [利空] [中性] 之一。
- logic 只能是 [竞争叙事] [基本面支撑] [宏观扰动] [政策监管] [政策支持] [市场博弈] [供需变化] [其他] 之一。
- 凡是涉及“净利润同比下降、亏损扩大、终止上市、违约、立案调查、临时停牌、溢价风险”等关键词，且无显著对冲利好时，严禁判定为 [中性]，必须判定为 [利空]。

### 输出示例
[
  {
    "time": "2026-04-20 09:34:40",
    "source": "媒体A/媒体B",
    "title": "净利下滑但海外业务增长",
    "summary": "投入加大导致短期利润承压，但海外业务与核心产品增长强劲",
    "entities": "核心实体",
    "emotion": "[中性]",
    "logic": "[基本面支撑]"
  }
]
"""


HOT_NEWS_CLEANING_SYSTEM_PROMPT = """
你是一个专业的金融市场热点清洗专家。输入是已经完成结构化降噪与时间窗聚类的 7x24 热门快讯簇。

### 核心任务流程
1. 结构化降噪：只保留时间、来源、标题/核心摘要、涉及实体和市场影响。
2. 语义合并：同一事件必须合并，来源用 "/" 分隔；同一时间窗内、同一主题、同一对象、同一政策/会议/发布会/访问，只输出一条综合摘要。
3. 市场立场校准：站在市场整体 / 相关板块视角判断情绪。
4. 特征增强：补充涉及实体、情绪标签和逻辑标签。
5. 数值保护：严禁改动任何百分比、金额、时间节点。

### 合并偏好
- 以“事件”为单位，不要以标题或新闻源为单位。
- 对政务、外交、宏观政策类快讯尤其要主动合并：如果只是不同会见人、不同媒体口径或不同修辞，但核心事件相同，必须合并为一条。
- 同一主题的关联快讯宁可少，不要重复罗列；优先输出覆盖面更完整的一条综合摘要。
- 如果一组快讯明显属于同一个主题簇（例如同一访问、同一政策、同一发布会、同一公告解读），请在模型内部先合并再输出。

### 输出要求
- 只能输出 JSON 数组，严禁输出 Markdown、解释、前言或总结。
- 每个对象必须包含：
  - time
  - source
  - title
  - summary
  - entities
  - emotion
  - logic
- summary 必须是单行，尽量保留核心动词和数值，不要写成长段落。
- entities 必须写具体对象（公司、国家、资产、板块或行业），禁止使用“市场热点”“新闻”等泛化词；如有多个实体，用 "/" 或列表表达。
- emotion 只能是 [利好] [利空] [中性] 之一。
- logic 只能是 [竞争叙事] [基本面支撑] [宏观扰动] [政策监管] [政策支持] [市场博弈] [供需变化] [其他] 之一。
- 凡是涉及“净利润同比下降、亏损扩大、终止上市、违约、立案调查、临时停牌、溢价风险”等关键词，且无显著对冲利好时，严禁判定为 [中性]，必须判定为 [利空]。

### 输出示例
[
  {
    "time": "2026-04-20 15:14:00",
    "source": "媒体A/媒体B",
    "title": "地缘冲突升级推升油价波动",
    "summary": "地缘冲突升级推升油价波动，石油股承压",
    "entities": "石油",
    "emotion": "[利空]",
    "logic": "[宏观扰动]"
  }
]
"""


def _get_news_cleaner_model_name() -> str:
    config = load_config()
    return (
        os.environ.get("OLLAMA_NEWS_MODEL")
        or str(config.get("news_processing", {}).get("ollama_model", "")).strip()
        or str(config.get("ollama", {}).get("model", "qwen3")).strip()
    )


def _call_news_cleaner_model(messages: list[dict[str, str]], timeout: int, options: dict[str, Any]) -> str:
    config = load_config()
    provider = str(config.get("llm_provider", "ollama")).strip().lower()
    if provider == "gemini":
        from llm.gemini_client import gemini_chat

        return gemini_chat(messages, timeout=timeout, options=options)
    if provider == "openrouter":
        from llm.openrouter_client import openrouter_chat

        return openrouter_chat(messages, timeout=timeout, options=options)

    from llm.ollama_client import ollama_chat

    return ollama_chat(
        messages,
        model_name=_get_news_cleaner_model_name(),
        timeout=timeout,
        options=options,
    )


def _coerce_json_like(raw_result: Any) -> Any:
    if not isinstance(raw_result, str):
        return raw_result

    cleaned = _strip_code_fences(raw_result)
    if not cleaned:
        return raw_result

    try:
        return json.loads(cleaned)
    except Exception:
        return raw_result


def _clean_text_value(value: Any) -> str:
    text = _first_nonempty(value)
    if not text:
        return ""
    text = html.unescape(text)
    text = text.replace("\xa0", " ").replace("&nbsp;", " ")
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("\r", " ").replace("\n", " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _parse_news_datetime(value: Any) -> datetime | None:
    text = _clean_text_value(value)
    if not text:
        return None

    candidates = (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d %H:%M",
        "%Y/%m/%d",
    )
    for fmt in candidates:
        try:
            parsed = datetime.strptime(text[: len(fmt.replace("%f", "000000"))], fmt)
            return parsed
        except Exception:
            continue

    match = re.search(r"(\d{4}-\d{2}-\d{2})(?:\s+(\d{2}:\d{2})(?::(\d{2}))?)?", text)
    if match:
        base = match.group(1)
        hm = match.group(2) or "00:00"
        ss = match.group(3) or "00"
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                return datetime.strptime(f"{base} {hm}:{ss}", "%Y-%m-%d %H:%M:%S")
            except Exception:
                try:
                    return datetime.strptime(f"{base} {hm}", "%Y-%m-%d %H:%M")
                except Exception:
                    continue
    return None


def _extract_news_items(raw_result: Any) -> list[dict[str, Any]]:
    raw_result = _coerce_json_like(raw_result)

    if isinstance(raw_result, dict):
        data = raw_result.get("data", raw_result)
        if isinstance(data, dict):
            items = data.get("items") or data.get("news") or data.get("list") or []
        elif isinstance(data, list):
            items = data
        else:
            items = []
    elif isinstance(raw_result, list):
        items = raw_result
    else:
        items = []

    normalized: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        publish_date = _clean_text_value(
            item.get("publishDate")
            or item.get("publish_date")
            or item.get("publish_time")
            or item.get("publish_time_str")
            or item.get("time")
            or ""
        )
        source = _clean_text_value(item.get("sources") or item.get("source") or "")
        title = _clean_text_value(item.get("title") or item.get("newsTitle") or item.get("headline") or "")
        content = _clean_text_value(item.get("summary") or item.get("content") or item.get("snippet") or "")
        normalized.append(
            {
                "id": item.get("id"),
                "publishDate": publish_date,
                "time_dt": _parse_news_datetime(publish_date),
                "source": source,
                "title": title,
                "content": content,
                "summary": content,
                "url": _clean_text_value(item.get("url") or item.get("link") or item.get("href") or ""),
            }
        )
    return normalized


def _is_low_value_news_item(item: dict[str, Any]) -> bool:
    text = _normalize_text(
        _compact_text(
            _first_nonempty(item.get("title")),
            _first_nonempty(item.get("content"), item.get("summary")),
        )
    )
    if not text:
        return True

    promo_terms = (
        "直播",
        "预告",
        "活动",
        "投教",
        "讲座",
        "路演",
        "宣讲",
        "培训",
        "课程",
        "回放",
        "专场",
        "解码",
        "投资思路",
        "今晚7点",
        "今晚19点",
        "点击链接",
        "免责声明",
        "仅供参考",
        "请点击",
        "报名",
        "扫码",
        "直播间",
        "公开课",
        "专题",
    )
    substantive_terms = (
        "财报",
        "业绩",
        "利润",
        "净利",
        "营收",
        "gmv",
        "订单",
        "合作",
        "并购",
        "收购",
        "融资",
        "回购",
        "增持",
        "减持",
        "起火",
        "袭击",
        "事故",
        "制裁",
        "监管",
        "调查",
        "诉讼",
        "签约",
        "发布",
        "获批",
        "指引",
        "通告",
        "警告",
        "扩产",
        "停产",
        "上涨",
        "下跌",
        "走高",
        "走低",
        "突破",
        "回落",
        "下滑",
        "增长",
        "缩水",
        "风险",
        "供应",
        "需求",
        "油价",
        "黄金",
        "%",
        "亿元",
        "亿美元",
        "万亿元",
        "同比",
        "环比",
        "利润",
        "净利",
    )

    if _contains_any(text, promo_terms) and not _contains_any(text, substantive_terms):
        return True

    if _contains_any(text, ("早评", "午评", "收评", "点评", "解读")) and not _contains_any(text, substantive_terms):
        return True

    return False


def _build_prompt_payload(
    keyword: str,
    start_date: str | None,
    end_date: str | None,
    page: int | None,
    page_size: int | None,
    cluster_items: list[dict[str, Any]],
) -> str:
    payload = {
        "request": {
            "keyword": keyword,
            "startDate": start_date,
            "endDate": end_date,
            "page": page,
            "pageSize": page_size,
        },
        "clusters": cluster_items,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _build_hot_news_prompt_payload(limit: int | None, cluster_items: list[dict[str, Any]]) -> str:
    payload = {
        "request": {
            "limit": limit,
        },
        "clusters": cluster_items,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _extract_item_datetime(item: dict[str, Any]) -> datetime | None:
    return item.get("time_dt") if isinstance(item.get("time_dt"), datetime) else _parse_news_datetime(
        item.get("publishDate")
        or item.get("publish_date")
        or item.get("publish_time")
        or item.get("publish_time_str")
        or item.get("time")
        or ""
    )


def _news_item_similarity(left: dict[str, Any], right: dict[str, Any]) -> float:
    left_text = _normalize_text(_compact_text(_first_nonempty(left.get("title")), _first_nonempty(left.get("content"), left.get("summary"))))
    right_text = _normalize_text(_compact_text(_first_nonempty(right.get("title")), _first_nonempty(right.get("content"), right.get("summary"))))
    if not left_text or not right_text:
        return 0.0
    ratio = SequenceMatcher(None, left_text, right_text).ratio()
    left_tokens = set(re.findall(r"[\u4e00-\u9fff]{2,}|[a-zA-Z]{3,}|\d{2,}", left_text))
    right_tokens = set(re.findall(r"[\u4e00-\u9fff]{2,}|[a-zA-Z]{3,}|\d{2,}", right_text))
    if not left_tokens or not right_tokens:
        return ratio
    jaccard = len(left_tokens & right_tokens) / max(len(left_tokens | right_tokens), 1)
    return max(ratio, jaccard)


def _cluster_news_items(
    items: list[dict[str, Any]],
    window_minutes: int,
    similarity_threshold: float = 0.72,
) -> list[list[dict[str, Any]]]:
    if not items:
        return []

    sorted_items = sorted(
        items,
        key=lambda item: _extract_item_datetime(item) or datetime.min,
        reverse=True,
    )

    clusters: list[dict[str, Any]] = []
    window = timedelta(minutes=window_minutes)

    for item in sorted_items:
        item_dt = _extract_item_datetime(item)
        best_idx: int | None = None
        best_score = 0.0

        for idx, cluster in enumerate(clusters):
            rep = cluster["items"][0]
            rep_dt = cluster.get("latest_dt")
            if item_dt and rep_dt and abs(item_dt - rep_dt) > window:
                continue
            score = _news_item_similarity(item, rep)
            if score >= similarity_threshold and score > best_score:
                best_idx = idx
                best_score = score

        if best_idx is None:
            clusters.append(
                {
                    "latest_dt": item_dt,
                    "items": [item],
                }
            )
        else:
            cluster = clusters[best_idx]
            cluster["items"].append(item)
            latest_dt = cluster.get("latest_dt")
            if item_dt and (latest_dt is None or item_dt > latest_dt):
                cluster["latest_dt"] = item_dt

    return [cluster["items"] for cluster in clusters]


def _build_cluster_record(
    keyword: str,
    cluster: list[dict[str, Any]],
    summary_limit: int = 60,
    content_limit: int = 180,
) -> dict[str, Any]:
    if not cluster:
        return {}

    times = [item.get("publishDate", "").strip() for item in cluster if _first_nonempty(item.get("publishDate"))]
    sources: list[str] = []
    titles: list[str] = []
    contents: list[str] = []

    for item in cluster:
        source = _first_nonempty(item.get("source"))
        if source and source not in sources:
            sources.append(source)
        title = _first_nonempty(item.get("title"))
        if title:
            titles.append(title)
        content = _first_nonempty(item.get("content"), item.get("summary"))
        if content:
            contents.append(content)

    best_title = _pick_concise_title(keyword, titles, contents)
    merged_summary = _shorten_text(_merge_unique_sentences(cluster, summary_limit=summary_limit), summary_limit)
    merged_content = _shorten_text(_compact_text(*contents, *titles), content_limit)
    if not merged_content:
        merged_content = merged_summary or best_title
    merged_entities = _anchor_entities(keyword, _compact_text(*titles, *contents))

    return {
        "time": max(times) if times else "",
        "source": "/".join(sources),
        "title": best_title,
        "summary": merged_summary,
        "content": merged_content,
        "entities": merged_entities,
        "cluster_size": len(cluster),
        "subject_hint": keyword,
    }


def _prepare_briefing_clusters(
    keyword: str,
    raw_items: list[dict[str, Any]],
    *,
    summary_limit: int,
    window_minutes: int,
    content_limit: int,
) -> list[dict[str, Any]]:
    cleaned_items = [item for item in raw_items if not _is_low_value_news_item(item)]
    if not cleaned_items:
        return []

    clusters = _cluster_news_items(cleaned_items, window_minutes=window_minutes)
    prepared: list[dict[str, Any]] = []
    for cluster in clusters:
        record = _build_cluster_record(keyword, cluster, summary_limit=summary_limit, content_limit=content_limit)
        if record and _compact_text(record.get("title", ""), record.get("summary", ""), record.get("content", "")):
            prepared.append(record)
    return prepared


def _extract_candidate_entities_from_text(text: str) -> list[str]:
    cleaned = _first_nonempty(text)
    if not cleaned:
        return []

    blacklist = {
        "市场",
        "新闻",
        "公告",
        "热点",
        "消息",
        "快讯",
        "简报",
        "投资",
        "观点",
        "分析",
        "解读",
        "行业",
        "板块",
        "政策",
        "宏观",
        "公司",
        "集团",
        "股份",
        "有限公司",
    }
    patterns = (
        r"\b[A-Z]{2,6}(?:\.[A-Z]{2})?\b",
        r"\b\d{6}(?:\.(?:SZ|SH|HK))?\b",
        r"\b\d{4}\.HK\b",
        r"[\u4e00-\u9fffA-Za-z0-9·&（）()\-]{2,18}(?:股份有限公司|有限公司|集团|公司|银行|证券|能源|燃气|石油|半导体|科技|电商|基金|ETF|LOF|汽车|医药|地产|保险|煤炭|有色|通信|算力|游戏|互联网|芯片|黄金|原油|期货|航运|航空|电力|物流|消费|传媒|生物|化工|农业|机器人|数据|AI|人工智能)",
    )

    ordered: list[str] = []
    for pattern in patterns:
        for match in re.findall(pattern, cleaned):
            candidate = _first_nonempty(match)
            if not candidate:
                continue
            normalized = candidate.replace(" ", "")
            if len(normalized) < 2:
                continue
            if normalized in blacklist:
                continue
            if normalized not in ordered:
                ordered.append(normalized)
    return ordered


def _anchor_entities(keyword: str, *texts: str) -> str:
    ordered: list[str] = []
    for candidate in (_first_nonempty(keyword),):
        if candidate and candidate not in ordered:
            ordered.append(candidate)
    for text in texts:
        for candidate in _extract_candidate_entities_from_text(text):
            if candidate not in ordered:
                ordered.append(candidate)
    return "、".join(ordered)


def _strip_code_fences(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped

    lines = stripped.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _first_nonempty(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str):
            candidate = value.strip()
            if candidate:
                return candidate
        elif isinstance(value, list):
            candidate = "、".join(str(item).strip() for item in value if str(item).strip())
            if candidate:
                return candidate
        else:
            candidate = str(value).strip()
            if candidate:
                return candidate
    return ""


def _normalize_tag(value: Any) -> str:
    text = _first_nonempty(value)
    if not text:
        return ""
    if text.startswith("[") and text.endswith("]"):
        return text
    return f"[{text}]"


def _normalize_keyword(keyword: str) -> str:
    return re.sub(r"\s+", "", keyword).lower()


def _normalize_text(text: str) -> str:
    normalized = re.sub(r"[\s\W_]+", "", text.lower())
    return normalized


def _extract_entity_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        parts = re.split(r"[、,/，;；\s]+", value)
        return [part.strip() for part in parts if part.strip()]
    if value is None:
        return []
    text = str(value).strip()
    return [text] if text else []


def _extract_tag_value(value: Any) -> str:
    text = _first_nonempty(value)
    if not text:
        return ""
    match = re.search(r"(利好|利空|中性)", text)
    return f"[{match.group(1)}]" if match else _normalize_tag(text)


def _extract_logic_value(value: Any) -> str:
    text = _first_nonempty(value)
    if not text:
        return ""
    for candidate in ("竞争叙事", "基本面支撑", "宏观扰动", "政策监管", "政策支持", "市场博弈", "供需变化", "其他"):
        if candidate in text:
            return f"[{candidate}]"
    return _normalize_tag(text)


def _compact_text(*parts: str) -> str:
    return " ".join(part.strip() for part in parts if part and part.strip())


def _parse_pipe_segments(text: str) -> list[str]:
    return [segment.strip() for segment in text.split("|") if segment.strip()]


def _parse_bracket_time(text: str) -> tuple[str, str]:
    stripped = text.strip()
    bracket_match = re.match(r"^\[(\d{4}-\d{2}-\d{2}(?:\s+\d{2}:\d{2}:\d{2})?)\]\s*(.*)$", stripped)
    if bracket_match:
        return bracket_match.group(1).strip(), bracket_match.group(2).strip()

    plain_match = re.match(r"^(\d{4}-\d{2}-\d{2}(?:\s+\d{2}:\d{2}:\d{2})?)(.*)$", stripped)
    if plain_match:
        return plain_match.group(1).strip(), plain_match.group(2).strip()

    return "", stripped


def _parse_text_entry(text: str) -> dict[str, Any]:
    stripped = text.strip()
    entry: dict[str, Any] = {
        "time": "",
        "source": "",
        "title": "",
        "summary": "",
        "involving_entities": [],
        "emotion": "",
        "logic": "",
        "raw_text": stripped,
    }

    if stripped in {"无匹配结果", "- 无匹配结果"}:
        return entry

    if stripped.startswith("-"):
        stripped = stripped.lstrip("-").strip()

    segments = _parse_pipe_segments(stripped)
    if not segments:
        segments = [stripped]

    first_segment = segments[0]
    time, main_text = _parse_bracket_time(first_segment)
    entry["time"] = time
    main_text = main_text.strip()

    if "：" in main_text and not main_text.startswith(("来源", "时间", "标题", "摘要", "实体", "情绪", "逻辑")):
        title_part, summary_part = main_text.split("：", 1)
        entry["title"] = title_part.strip()
        entry["summary"] = summary_part.strip()
    else:
        entry["title"] = main_text.strip()

    for segment in segments[1:]:
        seg = segment.strip()
        if not seg:
            continue
        if seg.startswith("来源：") or seg.startswith("来源:"):
            entry["source"] = seg.split("：", 1)[-1].split(":", 1)[-1].strip()
            continue
        if seg.startswith("实体：") or seg.startswith("涉及实体："):
            value = seg.split("：", 1)[-1].split(":", 1)[-1].strip()
            entry["involving_entities"] = _extract_entity_list(value)
            continue
        if seg.startswith("情绪：") or seg.startswith("情绪标签：") or seg.startswith("情绪标签:"):
            entry["emotion"] = _extract_tag_value(seg)
            continue
        if seg.startswith("逻辑：") or seg.startswith("逻辑标签：") or seg.startswith("逻辑标签:"):
            entry["logic"] = _extract_logic_value(seg)
            continue
        if seg.startswith("标题：") or seg.startswith("标题:"):
            entry["title"] = seg.split("：", 1)[-1].split(":", 1)[-1].strip()
            continue
        if seg.startswith("摘要：") or seg.startswith("摘要:"):
            entry["summary"] = seg.split("：", 1)[-1].split(":", 1)[-1].strip()
            continue

    if not entry["title"] and entry["summary"]:
        entry["title"] = entry["summary"]

    if not entry["summary"]:
        entry["summary"] = entry["title"]

    if not entry["time"]:
        time_match = re.search(r"\d{4}-\d{2}-\d{2}(?:\s+\d{2}:\d{2}:\d{2})?", stripped)
        if time_match:
            entry["time"] = time_match.group(0)

    source_match = re.search(r"来源[:：]\s*([^|)]+)", stripped)
    if source_match and not entry["source"]:
        entry["source"] = source_match.group(1).strip()
    paren_source = re.search(r"\((?:来源[:：]\s*)?([^()]+)\)\s*$", stripped)
    if paren_source and not entry["source"]:
        maybe_source = paren_source.group(1).strip()
        if "：" not in maybe_source and ":" not in maybe_source:
            entry["source"] = maybe_source

    if not entry["emotion"]:
        emotion_match = re.search(r"(利好|利空|中性)", stripped)
        if emotion_match:
            entry["emotion"] = f"[{emotion_match.group(1)}]"

    if not entry["logic"]:
        for candidate in ("竞争叙事", "基本面支撑", "宏观扰动", "政策监管", "政策支持", "市场博弈", "供需变化", "其他"):
            if candidate in stripped:
                entry["logic"] = f"[{candidate}]"
                break

    return entry


def _shorten_text(text: str, max_chars: int) -> str:
    clean = _first_nonempty(text)
    if not clean:
        return ""
    clean = re.sub(r"\s+", " ", clean).strip()
    if len(clean) <= max_chars:
        return clean

    sentences = [part.strip() for part in re.split(r"[。！？!?；;\n]+", clean) if part.strip()]
    if not sentences:
        return clean[:max_chars].rstrip("，,；; ") + "…"

    pieces: list[str] = []
    current_len = 0
    for sentence in sentences:
        candidate_len = len(sentence) if not pieces else len(sentence) + 1
        if pieces and current_len + candidate_len > max_chars:
            break
        if not pieces and len(sentence) > max_chars:
            return sentence[:max_chars].rstrip("，,；; ") + "…"
        pieces.append(sentence)
        current_len += candidate_len
        if current_len >= max_chars:
            break

    shortened = "；".join(pieces)
    if len(shortened) > max_chars:
        shortened = shortened[:max_chars].rstrip("，,；; ") + "…"
    return shortened


def _compose_headline(title: str, summary: str, max_chars: int = 80) -> str:
    short_title = _shorten_text(title, min(48, max_chars))
    short_summary = _shorten_text(summary, min(60, max_chars))
    if not short_title:
        return short_summary
    if not short_summary or short_summary == short_title:
        return short_title

    title_norm = _normalize_text(short_title)
    summary_norm = _normalize_text(short_summary)
    if title_norm and title_norm in summary_norm:
        return short_summary
    if summary_norm and summary_norm in title_norm:
        return short_title

    combined = f"{short_title}：{short_summary}"
    if len(combined) > max_chars:
        return _shorten_text(combined, max_chars)
    if len(short_title) <= 48:
        return combined
    return short_summary or short_title


def _pick_concise_title(keyword: str, titles: list[str], summaries: list[str]) -> str:
    candidates = [title for title in titles if title]
    if not candidates:
        candidates = [summary for summary in summaries if summary]
    if not candidates:
        return keyword

    keyword_norm = _normalize_keyword(keyword)
    promo_terms = (
        "直播",
        "预告",
        "活动",
        "投教",
        "讲座",
        "路演",
        "宣讲",
        "培训",
        "课程",
        "回放",
        "专场",
        "解码",
        "投资思路",
        "今晚7点",
        "今晚19点",
    )

    def score(text: str) -> tuple[int, int, int]:
        normalized = _normalize_text(text)
        entity_hit = 1 if keyword_norm and keyword_norm in normalized else 0
        promo_penalty = 1 if _contains_any(normalized, promo_terms) else 0
        length = len(text)
        # entity hit higher is better; promo penalty lower is better; shorter is better
        return (-entity_hit, promo_penalty, length)

    return sorted(candidates, key=score)[0]


def _parse_model_output_to_entries(response: str) -> list[dict[str, Any]]:
    cleaned = _strip_code_fences(response)
    if not cleaned:
        return []

    try:
        parsed = json.loads(cleaned)
    except Exception:
        parsed = None

    entries: list[dict[str, Any]] = []
    if isinstance(parsed, dict):
        if isinstance(parsed.get("items"), list):
            parsed = parsed["items"]
        elif isinstance(parsed.get("data"), dict) and isinstance(parsed["data"].get("items"), list):
            parsed = parsed["data"]["items"]
        else:
            parsed = [parsed]

    if isinstance(parsed, list):
        for item in parsed:
            if isinstance(item, dict):
                entries.append(
                    {
                        "time": _first_nonempty(
                            item.get("time"),
                            item.get("publishDate"),
                            item.get("publish_time"),
                            item.get("publish_time_str"),
                        ),
                        "source": _first_nonempty(item.get("source"), item.get("sources")),
                        "title": _first_nonempty(item.get("title"), item.get("newsTitle"), item.get("headline")),
                        "summary": _first_nonempty(item.get("summary"), item.get("content"), item.get("snippet")),
                        "involving_entities": _extract_entity_list(
                            item.get("involving_entities") or item.get("entities") or item.get("涉及实体")
                        ),
                        "emotion": _extract_tag_value(item.get("emotions") or item.get("emotion") or item.get("情绪标签")),
                        "logic": _extract_logic_value(
                            item.get("logical_tags")
                            or item.get("logic_tags")
                            or item.get("logic")
                            or item.get("逻辑标签")
                        ),
                        "raw_text": json.dumps(item, ensure_ascii=False),
                    }
                )
            else:
                entries.append(_parse_text_entry(str(item)))
        return [entry for entry in entries if _compact_text(entry.get("title", ""), entry.get("summary", ""))]

    lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
    current_block: list[str] = []

    def flush_block() -> None:
        if not current_block:
            return
        block_text = "\n".join(current_block).strip()
        current_block.clear()
        if block_text:
            entry = _parse_text_entry(block_text)
            if _compact_text(entry.get("title", ""), entry.get("summary", "")):
                entries.append(entry)

    for line in lines:
        if re.match(r"^(\d+[\.\)]\s+|-)\s*", line):
            flush_block()
            current_block.append(line)
        else:
            if current_block:
                current_block.append(line)
            else:
                current_block.append(line)
    flush_block()
    return entries


def _entry_text(entry: dict[str, Any]) -> str:
    return _compact_text(
        _first_nonempty(entry.get("title")),
        _first_nonempty(entry.get("summary")),
        _first_nonempty(entry.get("entities"), entry.get("involving_entities")),
        _first_nonempty(entry.get("raw_text")),
    )


def _item_similarity(left: dict[str, Any], right: dict[str, Any]) -> float:
    left_text = _normalize_text(_entry_text(left))
    right_text = _normalize_text(_entry_text(right))
    if not left_text or not right_text:
        return 0.0
    ratio = SequenceMatcher(None, left_text, right_text).ratio()
    left_tokens = set(re.findall(r"[\u4e00-\u9fff]{2,}|[a-zA-Z]{3,}|\d{2,}", left_text))
    right_tokens = set(re.findall(r"[\u4e00-\u9fff]{2,}|[a-zA-Z]{3,}|\d{2,}", right_text))
    if not left_tokens or not right_tokens:
        return ratio
    jaccard = len(left_tokens & right_tokens) / max(len(left_tokens | right_tokens), 1)
    return max(ratio, jaccard)


def _is_same_event(keyword: str, left: dict[str, Any], right: dict[str, Any]) -> bool:
    left_text = _normalize_text(_entry_text(left))
    right_text = _normalize_text(_entry_text(right))
    similarity = _item_similarity(left, right)
    if similarity >= 0.78:
        return True

    left_entities = set(_extract_entity_list(left.get("entities") or left.get("involving_entities")))
    right_entities = set(_extract_entity_list(right.get("entities") or right.get("involving_entities")))
    shared_entities = left_entities & right_entities
    if shared_entities and similarity >= 0.62:
        return True

    left_dt = _extract_item_datetime(left)
    right_dt = _extract_item_datetime(right)
    if left_dt and right_dt and abs(left_dt - right_dt) > timedelta(hours=8):
        return False

    return False


def _dedupe_entries(
    keyword: str,
    entries: list[dict[str, Any]],
    summary_limit: int = 60,
) -> list[dict[str, Any]]:
    groups: list[list[dict[str, Any]]] = []
    for entry in entries:
        placed = False
        for group in groups:
            if _is_same_event(keyword, entry, group[0]):
                group.append(entry)
                placed = True
                break
        if not placed:
            groups.append([entry])
    merged: list[dict[str, Any]] = []
    for group in groups:
        merged.append(_merge_group(keyword, group, summary_limit=summary_limit))
    return merged


def _merge_group(
    keyword: str,
    group: list[dict[str, Any]],
    summary_limit: int = 60,
) -> dict[str, Any]:
    if not group:
        return {}

    times = [item.get("time", "").strip() for item in group if _first_nonempty(item.get("time"))]
    sources: list[str] = []
    titles: list[str] = []
    summaries: list[str] = []
    entities: list[str] = []
    emotions: list[str] = []
    logics: list[str] = []

    for item in group:
        source = _first_nonempty(item.get("source"))
        if source and source not in sources:
            sources.append(source)
        title = _first_nonempty(item.get("title"))
        if title:
            titles.append(title)
        summary = _first_nonempty(item.get("summary"))
        if summary:
            summaries.append(summary)
        entities.extend(_extract_entity_list(item.get("involving_entities") or item.get("entities")))
        emotion = _extract_tag_value(item.get("emotion"))
        if emotion:
            emotions.append(emotion)
        logic = _extract_logic_value(item.get("logic"))
        if logic:
            logics.append(logic)

    best_title = _pick_concise_title(keyword, titles, summaries)
    merged_summary = _shorten_text(_merge_unique_sentences(group, summary_limit=summary_limit), summary_limit)
    merged_entities = _merge_unique_list(entities)
    if not merged_entities:
        merged_entities = _anchor_entities(keyword, " ".join(titles + summaries))
    sentiment = _resolve_sentiment(keyword, " ".join(titles + summaries), emotions)
    logic = _resolve_logic(keyword, " ".join(titles + summaries), logics)

    return {
        "time": max(times) if times else "",
        "source": "/".join(sources),
        "title": best_title,
        "summary": merged_summary,
        "entities": merged_entities,
        "emotion": sentiment,
        "logic": logic,
    }


def _merge_unique_sentences(group: list[dict[str, Any]], summary_limit: int = 120) -> str:
    seen: set[str] = set()
    pieces: list[str] = []
    for item in group:
        for raw_text in (
            _first_nonempty(item.get("summary")),
            _first_nonempty(item.get("title")),
        ):
            if not raw_text:
                continue
            sentences = re.split(r"[。！？!?；;\n]+", raw_text)
            for sentence in sentences:
                sentence = sentence.strip()
                if not sentence:
                    continue
                normalized = _normalize_text(sentence)
                if normalized and normalized not in seen:
                    seen.add(normalized)
                    pieces.append(sentence)
    if not pieces:
        return ""
    joined = "；".join(pieces[:2])
    return _shorten_text(joined, summary_limit)


def _merge_unique_list(values: list[str]) -> str:
    ordered: list[str] = []
    for value in values:
        if value and value not in ordered:
            ordered.append(value)
    return "、".join(ordered)


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in text for keyword in keywords)


def _score_sentiment(text: str) -> int:
    positive_terms = (
        "利好",
        "增长",
        "上涨",
        "回升",
        "创新高",
        "突破",
        "强劲",
        "提振",
        "改善",
        "扩张",
        "加速",
        "获批",
        "支持",
        "促进",
        "回购",
        "增持",
        "中标",
        "签约",
        "合作",
        "超预期",
        "扩产",
    )
    negative_terms = (
        "利空",
        "下降",
        "下滑",
        "同比下降",
        "同比下滑",
        "缩水",
        "承压",
        "下跌",
        "回落",
        "走低",
        "放缓",
        "受损",
        "冲击",
        "挑战",
        "减少",
        "收缩",
        "违约",
        "退市",
        "终止上市",
        "立案调查",
        "调查",
        "处罚",
        "临时停牌",
        "溢价风险",
        "下修",
        "减持",
        "起火",
        "袭击",
        "事故",
        "停产",
    )
    score = 0
    for term in positive_terms:
        if term in text:
            score += 1
    for term in negative_terms:
        if term in text:
            score -= 1
    return score


def _resolve_sentiment(keyword: str, text: str, model_emotions: list[str]) -> str:
    normalized_text = _normalize_text(text)
    model_emotion_set = {emotion for emotion in model_emotions if emotion}

    competition_negative_patterns = (
        r"去[\u4e00-\u9fffA-Za-z0-9]{1,12}化",
        r"替代",
        r"替换",
        r"竞争对手",
        r"对标",
        r"挑战",
        r"份额流失",
        r"客户流失",
        r"市场份额",
        r"侵蚀",
        r"蚕食",
        r"分流",
        r"国产替代",
        r"自研",
    )

    strong_negative_terms = (
        "净利润下滑",
        "利润下滑",
        "净利下滑",
        "净利润下降",
        "利润下降",
        "净利下降",
        "亏损扩大",
        "亏损",
        "业绩下滑",
        "业绩下降",
        "终止上市",
        "退市",
        "违约",
        "立案调查",
        "处罚",
        "临时停牌",
        "溢价风险",
        "下修",
        "减持",
        "起火",
        "袭击",
        "停产",
        "事故",
        "暴雷",
        "同比下降",
        "同比下滑",
    )
    strong_positive_terms = (
        "净利润增长",
        "利润增长",
        "营收增长",
        "业绩增长",
        "订单增长",
        "扩产",
        "获批",
        "支持",
        "促进",
        "回购",
        "增持",
        "中标",
        "签约",
        "合作",
        "超预期",
        "创新高",
        "提振",
        "改善",
    )

    if keyword and any(re.search(pattern, normalized_text) for pattern in competition_negative_patterns):
        return "[利空]"

    has_negative = _contains_any(normalized_text, strong_negative_terms)
    has_positive = _contains_any(normalized_text, strong_positive_terms)

    if has_negative and has_positive:
        return "[中性]"
    if has_negative:
        return "[利空]"
    if has_positive:
        return "[利好]"

    score = _score_sentiment(normalized_text)
    if model_emotion_set == {"[利好]"}:
        return "[利好]" if score >= 0 else "[中性]"
    if model_emotion_set == {"[利空]"}:
        return "[利空]" if score <= 0 else "[中性]"
    if model_emotion_set == {"[中性]"}:
        if score > 1:
            return "[利好]"
        if score < -1:
            return "[利空]"
        return "[中性]"

    if score > 0:
        return "[利好]"
    if score < 0:
        return "[利空]"
    return "[中性]"


def _resolve_logic(keyword: str, text: str, model_logics: list[str]) -> str:
    normalized_text = _normalize_text(text)
    market_battle_terms = ("溢价风险", "停牌", "复牌", "临时停牌", "大宗交易", "换手", "涨停", "跌停", "异动", "折价")
    policy_support_terms = ("国务院", "发改委", "财政部", "央行", "工信部", "商务部", "意见", "方案", "规划", "支持", "促进", "推进", "提质", "扩能", "补贴", "减税", "降税")
    policy_reg_terms = ("监管", "制裁", "立案", "调查", "处罚", "审查", "合规", "退市", "终止上市", "*st", "问询", "禁令")
    competition_terms = ("替代", "替换", "去", "自研", "份额", "竞争对手", "挑战", "国产替代", "新芯片", "换芯")
    supply_terms = ("供给", "供需", "产量", "库存", "运力", "运输", "钻井", "减产", "增产", "油价", "原油", "油气", "供应")
    basic_terms = ("财报", "业绩", "利润", "净利", "营收", "订单", "销量", "出货", "gmv", "回购", "增持", "合作", "中标", "签约")
    macro_terms = ("中东", "俄乌", "霍尔木兹", "黑海", "地缘", "战争", "通胀", "利率", "降息", "美联储", "美元", "汇率")

    if _contains_any(normalized_text, market_battle_terms):
        return "[市场博弈]"
    if _contains_any(normalized_text, policy_reg_terms):
        return "[政策监管]"
    if _contains_any(normalized_text, policy_support_terms):
        return "[政策支持]"
    if _contains_any(normalized_text, competition_terms):
        return "[竞争叙事]"
    if _contains_any(normalized_text, supply_terms):
        return "[供需变化]"
    if _contains_any(normalized_text, basic_terms):
        return "[基本面支撑]"
    if _contains_any(normalized_text, macro_terms):
        return "[宏观扰动]"

    for logic in model_logics:
        if logic:
            return logic
    return "[其他]"


def _render_entry_markdown(item: dict[str, Any], headline_max_chars: int = 80) -> str:
    time = _first_nonempty(item.get("time"))
    source = _first_nonempty(item.get("source"))
    title = _first_nonempty(item.get("title"))
    summary = _first_nonempty(item.get("summary"))
    entities = _first_nonempty(item.get("entities"))
    emotion = _extract_tag_value(item.get("emotion"))
    logic = _extract_logic_value(item.get("logic"))
    headline = _compose_headline(title, summary, max_chars=headline_max_chars)

    parts: list[str] = []
    if time:
        parts.append(f"[{time}] {headline or title}")
    elif headline or title:
        parts.append(headline or title)
    if source:
        parts.append(f"来源：{source}")
    if entities:
        parts.append(f"实体：{entities}")
    if emotion:
        parts.append(f"情绪：{emotion}")
    if logic:
        parts.append(f"逻辑：{logic}")
    return "- " + " | ".join(parts)


def _render_entries_markdown(entries: list[dict[str, Any]], headline_max_chars: int = 80) -> str:
    if not entries:
        return "## 新闻简报\n- 无匹配结果"

    lines = ["## 新闻简报"]
    sorted_entries = sorted(entries, key=lambda item: _first_nonempty(item.get("time")), reverse=True)
    for entry in sorted_entries:
        lines.append(_render_entry_markdown(entry, headline_max_chars=headline_max_chars))
    return "\n".join(lines).strip()


def _render_hot_news_markdown(entries: list[dict[str, Any]]) -> str:
    return _render_entries_markdown(entries, headline_max_chars=80)


def _postprocess_news_entries(
    keyword: str,
    entries: list[dict[str, Any]],
    summary_limit: int = 120,
) -> list[dict[str, Any]]:
    if not entries:
        return []

    deduped = _dedupe_entries(keyword, entries, summary_limit=summary_limit)
    return deduped


def _render_markdown_entry(item: dict[str, Any]) -> str:
    time = _first_nonempty(
        item.get("time"),
        item.get("publishDate"),
        item.get("publish_time"),
        item.get("publish_time_str"),
    )
    source = _first_nonempty(item.get("source"), item.get("sources"))
    title = _first_nonempty(item.get("title"), item.get("newsTitle"), item.get("headline"))
    summary = _first_nonempty(item.get("summary"), item.get("content"), item.get("snippet"))
    entities = _first_nonempty(
        item.get("involving_entities"),
        item.get("entities"),
        item.get("涉及实体"),
    )
    emotion = _normalize_tag(item.get("emotions") or item.get("emotion") or item.get("情绪标签"))
    logic = _normalize_tag(
        item.get("logical_tags")
        or item.get("logic_tags")
        or item.get("logic")
        or item.get("逻辑标签")
    )

    parts: list[str] = []
    if time:
        parts.append(f"[{time}]")
    if source:
        parts.append(f"来源：{source}")
    if title:
        parts.append(f"标题：{title}")
    if summary and summary != title:
        parts.append(f"摘要：{summary}")
    if entities:
        parts.append(f"实体：{entities}")
    if emotion:
        parts.append(f"情绪：{emotion}")
    if logic:
        parts.append(f"逻辑：{logic}")

    return "- " + " | ".join(parts) if parts else "- 无可用内容"


def _normalize_model_output(
    response: str,
    briefing_items: list[dict[str, Any]],
    keyword: str,
    summary_limit: int = 120,
    headline_max_chars: int = 80,
) -> str:
    cleaned = _strip_code_fences(response)
    if not cleaned:
        return _fallback_markdown(
            briefing_items,
            keyword,
            summary_limit=summary_limit,
            headline_max_chars=headline_max_chars,
        )

    parsed_entries = _parse_model_output_to_entries(cleaned)
    if not parsed_entries:
        return _fallback_markdown(
            briefing_items,
            keyword,
            summary_limit=summary_limit,
            headline_max_chars=headline_max_chars,
        )

    merged_entries = _postprocess_news_entries(keyword, parsed_entries, summary_limit=summary_limit)
    if not merged_entries:
        return _fallback_markdown(
            briefing_items,
            keyword,
            summary_limit=summary_limit,
            headline_max_chars=headline_max_chars,
        )

    return _render_entries_markdown(merged_entries, headline_max_chars=headline_max_chars)


def _normalize_hot_news_model_output(
    response: str,
    briefing_items: list[dict[str, Any]],
    summary_limit: int = 140,
    headline_max_chars: int = 80,
) -> str:
    cleaned = _strip_code_fences(response)
    if not cleaned:
        return _fallback_markdown(
            briefing_items,
            "",
            summary_limit=summary_limit,
            headline_max_chars=headline_max_chars,
        )

    parsed_entries = _parse_model_output_to_entries(cleaned)
    if not parsed_entries:
        return _fallback_markdown(
            briefing_items,
            "",
            summary_limit=summary_limit,
            headline_max_chars=headline_max_chars,
        )

    merged_entries = _postprocess_news_entries("", parsed_entries, summary_limit=summary_limit)
    if not merged_entries:
        return _fallback_markdown(
            briefing_items,
            "",
            summary_limit=summary_limit,
            headline_max_chars=headline_max_chars,
        )

    return _render_entries_markdown(merged_entries, headline_max_chars=headline_max_chars)


def _build_structured_fallback_entries(
    keyword: str,
    raw_items: list[dict[str, Any]],
    summary_limit: int = 120,
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for item in raw_items:
        title = _first_nonempty(item.get("title"), item.get("headline"))
        content = _first_nonempty(item.get("content"), item.get("summary"), item.get("snippet"))
        summary = _shorten_text(_compact_text(content, title), summary_limit)
        text = _compact_text(title, summary, content)
        entries.append(
            {
                "time": _first_nonempty(item.get("time"), item.get("publishDate")),
                "source": _first_nonempty(item.get("source"), item.get("sources")),
                "title": title or keyword,
                "summary": summary,
                "entities": _anchor_entities(keyword, _compact_text(title, content)),
                "emotion": _resolve_sentiment(keyword, text, []),
                "logic": _resolve_logic(keyword, text, []),
            }
        )
    return entries


def _fallback_markdown(
    raw_items: list[dict[str, Any]],
    keyword: str,
    summary_limit: int = 120,
    headline_max_chars: int = 80,
) -> str:
    if not raw_items:
        return "## 新闻简报\n- 无匹配结果"

    structured_entries = _postprocess_news_entries(
        keyword,
        _build_structured_fallback_entries(keyword, raw_items, summary_limit=summary_limit),
        summary_limit=summary_limit,
    )
    if not structured_entries:
        return "## 新闻简报\n- 无匹配结果"
    return _render_entries_markdown(structured_entries, headline_max_chars=headline_max_chars)


def summarize_financial_news_for_agent(
    raw_result: Any,
    keyword: str,
    start_date: str | None = None,
    end_date: str | None = None,
    page: int | None = None,
    page_size: int | None = None,
) -> str:
    """
    将 SearchFinancialNews 的原始返回，转换成适合 LLM 直接消费的
    极简 Markdown 简报。
    """

    raw_items = _extract_news_items(raw_result)
    if not raw_items:
        return _fallback_markdown(raw_items, keyword, summary_limit=120, headline_max_chars=80)

    raw_items = [item for item in raw_items if not _is_low_value_news_item(item)]
    if not raw_items:
        return "## 新闻简报\n- 无匹配结果"

    briefing_items = _prepare_briefing_clusters(
        keyword,
        raw_items,
        summary_limit=120,
        window_minutes=20,
        content_limit=240,
    )
    if not briefing_items:
        return "## 新闻简报\n- 无匹配结果"

    prompt_payload = _build_prompt_payload(
        keyword=keyword,
        start_date=start_date,
        end_date=end_date,
        page=page,
        page_size=page_size,
        cluster_items=briefing_items,
    )

    messages = [
        {"role": "system", "content": NEWS_CLEANING_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                "请基于以下已经完成结构化降噪、时间窗聚类与实体锚定的快讯簇，按照规则输出 JSON 数组。\n"
                "同一事件已经在输入阶段做过初步合并，若仍存在同义重复、同主题的政务会见/政策发布/公告解读，请继续主动合并；来源用 \"/\" 分隔。\n"
                "情绪判断必须站在本次查询关键词/涉及实体的立场，不要站在竞争对手或新闻整体的立场。\n\n"
                f"{prompt_payload}"
            ),
        },
    ]

    try:
        response = _call_news_cleaner_model(
            messages,
            timeout=600,
            options={
                "temperature": 0.0,
                "num_predict": 128,
            },
        )
        return _normalize_model_output(
            response,
            briefing_items,
            keyword,
            summary_limit=120,
            headline_max_chars=80,
        )
    except Exception:
        return _fallback_markdown(briefing_items, keyword, summary_limit=120, headline_max_chars=80)


def summarize_hot_news_for_agent(
    raw_result: Any,
    limit: int | None = None,
) -> str:
    """
    将 hot_news_7x24 的原始返回，转换成适合 LLM 直接消费的
    极简 Markdown 热点简报。
    """

    raw_items = _extract_news_items(raw_result)
    if not raw_items:
        return "## 新闻简报\n- 无匹配结果"

    raw_items = [item for item in raw_items if not _is_low_value_news_item(item)]
    if not raw_items:
        return "## 新闻简报\n- 无匹配结果"

    briefing_items = _prepare_briefing_clusters(
        "",
        raw_items,
        summary_limit=140,
        window_minutes=20,
        content_limit=260,
    )
    if not briefing_items:
        return "## 新闻简报\n- 无匹配结果"

    prompt_payload = _build_hot_news_prompt_payload(
        limit=limit,
        cluster_items=briefing_items,
    )

    messages = [
        {"role": "system", "content": HOT_NEWS_CLEANING_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                "请基于以下已经完成结构化降噪、时间窗聚类与市场实体锚定的 7x24 热门快讯簇，按照规则输出 JSON 数组。\n"
                "同一事件已经在输入阶段做过初步合并，若仍存在同义重复、同主题的政务会见/政策发布/宏观解读，请继续主动合并；来源用 \"/\" 分隔。\n"
                "请保留对市场最有意义的信息，过滤掉投教、直播、路演、纯评论和纯点位罗列。\n\n"
                f"{prompt_payload}"
            ),
        },
    ]

    try:
        response = _call_news_cleaner_model(
            messages,
            timeout=600,
            options={
                "temperature": 0.0,
                "num_predict": 128,
            },
        )
        return _normalize_hot_news_model_output(
            response,
            briefing_items,
            summary_limit=140,
            headline_max_chars=80,
        )
    except Exception:
        return _fallback_markdown(briefing_items, "", summary_limit=140, headline_max_chars=80)
