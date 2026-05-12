from __future__ import annotations

import hashlib
import html
import json
import re
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


CLS_ARTICLE_URL = "https://www.cls.cn/detail/{article_id}"
CLS_IMAGE_RE = re.compile(r"https://image\.cls\.cn/images/[^\"'<>\\\s)]+", re.IGNORECASE)


@dataclass(frozen=True)
class ClsImage:
    url: str
    width: int | None
    height: int | None
    is_classification_image: bool


@dataclass(frozen=True)
class ClsRelatedStock:
    name: str
    change_percent: str | None


@dataclass(frozen=True)
class ClsLimitUpAnalysis:
    trade_date: str
    title: str
    url: str
    published_at: str | None
    summary: str | None
    images: list[ClsImage]
    classification_images: list[ClsImage]
    related_stocks: list[ClsRelatedStock]
    theme_stocks: list[dict[str, Any]]
    raw_html_sha256: str
    collected_at: str


def fetch_cls_limit_up_analysis(
    url: str,
    trade_date: date | None = None,
    timeout: float = 15.0,
) -> ClsLimitUpAnalysis:
    html_text = fetch_cls_html(url, timeout=timeout)
    title = _extract_title(html_text) or "涨停分析"
    visible_text = _visible_text(html_text)
    published_at = _extract_published_at(visible_text)
    resolved_trade_date = trade_date or _date_from_title(title, published_at) or date.today()
    images = _extract_images(html_text)
    related_stocks = _extract_related_stocks(visible_text)
    return ClsLimitUpAnalysis(
        trade_date=resolved_trade_date.strftime("%Y-%m-%d"),
        title=title,
        url=url,
        published_at=published_at,
        summary=_extract_summary(visible_text),
        images=images,
        classification_images=[image for image in images if image.is_classification_image],
        related_stocks=related_stocks,
        theme_stocks=[],
        raw_html_sha256=hashlib.sha256(html_text.encode("utf-8", errors="ignore")).hexdigest(),
        collected_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )


def fetch_cls_html(url: str, timeout: float = 15.0) -> str:
    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 stock-bro/0.1",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Referer": "https://www.cls.cn/",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return response.read().decode(charset, errors="replace")
    except HTTPError as exc:
        raise RuntimeError(f"CLS request failed with HTTP {exc.code}") from exc
    except (TimeoutError, URLError) as exc:
        raise RuntimeError(f"CLS request failed: {exc}") from exc


def write_json(data: ClsLimitUpAnalysis, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    suffix = data.trade_date.replace("-", "")
    output = out_dir / f"{suffix}_limit_up_analysis.json"
    with output.open("w", encoding="utf-8") as file:
        json.dump(_to_jsonable(data), file, ensure_ascii=False, indent=2)
        file.write("\n")
    return output


def _extract_title(html_text: str) -> str | None:
    for pattern in (
        r"<meta[^>]+property=[\"']og:title[\"'][^>]+content=[\"']([^\"']+)",
        r"<title[^>]*>(.*?)</title>",
    ):
        match = re.search(pattern, html_text, re.IGNORECASE | re.DOTALL)
        if match:
            title = _clean_text(match.group(1))
            if title:
                return title.split("|", 1)[0].strip()
    visible = _visible_text(html_text)
    match = re.search(r"\d{1,2}月\d{1,2}日涨停分析", visible)
    return match.group(0) if match else None


def _extract_published_at(text: str) -> str | None:
    match = re.search(r"(\d{4}年\d{2}月\d{2}日\s+\d{2}:\d{2}:\d{2})", text)
    return match.group(1) if match else None


def _extract_summary(text: str) -> str | None:
    match = re.search(r"(财联社\d{1,2}月\d{1,2}日电，.*?。)", text)
    return match.group(1) if match else None


def _extract_images(html_text: str) -> list[ClsImage]:
    seen: set[str] = set()
    images: list[ClsImage] = []
    for raw_url in CLS_IMAGE_RE.findall(html_text):
        url = html.unescape(raw_url).rstrip("\\")
        if url in seen:
            continue
        seen.add(url)
        width, height = _dimensions_from_url(url)
        images.append(
            ClsImage(
                url=url,
                width=width,
                height=height,
                is_classification_image=bool(width and height and height > width * 2),
            )
        )
    return images


def _dimensions_from_url(url: str) -> tuple[int | None, int | None]:
    match = re.search(r"_(\d+)x(\d+)\.(?:jpg|jpeg|png|webp)(?:\?|$)", url, re.IGNORECASE)
    if not match:
        return None, None
    return int(match.group(1)), int(match.group(2))


def _extract_related_stocks(text: str) -> list[ClsRelatedStock]:
    marker = text.find("关联个股")
    if marker == -1:
        return []
    tail = text[marker + len("关联个股") : marker + 300]
    result: list[ClsRelatedStock] = []
    for name, change in re.findall(r"([\u4e00-\u9fa5A-Za-z\s]{2,12})\s+([+-]\d+(?:\.\d+)?%)", tail):
        clean_name = " ".join(name.split())
        if clean_name and not any(item.name == clean_name for item in result):
            result.append(ClsRelatedStock(name=clean_name, change_percent=change))
    return result


def _date_from_title(title: str, published_at: str | None = None) -> date | None:
    match = re.search(r"(\d{1,2})月(\d{1,2})日", title)
    if not match:
        return None
    year_match = re.search(r"(\d{4})年", published_at or "")
    year = int(year_match.group(1)) if year_match else date.today().year
    return date(year, int(match.group(1)), int(match.group(2)))


def _visible_text(html_text: str) -> str:
    text = re.sub(r"<script[\s\S]*?</script>", " ", html_text, flags=re.IGNORECASE)
    text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    return _clean_text(text)


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(value)).strip()


def _to_jsonable(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__"):
        return asdict(value)
    if isinstance(value, list):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {key: _to_jsonable(item) for key, item in value.items()}
    return value
