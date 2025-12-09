from pydantic import BaseModel, Field
import asyncio
import httpx
from dogu import doguda
from bs4 import BeautifulSoup, Tag
from urllib.parse import urljoin
from html_to_markdown import ConversionOptions, PreprocessingOptions, convert
from time import time


class UrlToTextResponse(BaseModel):
    source_url: str
    timestamp_millis: int
    raw: str
    text: str
    markdown: str
    metadata: dict = Field(default_factory=dict)


async def _fetch_iframe_payload(client: httpx.AsyncClient, url: str) -> tuple[str, bool]:
    try:
        response = await client.get(url)
        response.raise_for_status()
        return response.text, True
    except Exception as exc:  # noqa: BLE001 - placeholder needs the message
        return f"[Failed to embed iframe from {url}: {exc}]", False


def _replace_iframe_with_content(
    soup: BeautifulSoup,
    iframe: Tag,
    html: str,
    src_url: str,
    loaded: bool,
    fragment: BeautifulSoup | None = None,
) -> None:
    if not loaded:
        iframe.replace_with(soup.new_string(html))
        return

    fragment = fragment or BeautifulSoup(html, "html.parser")
    container = soup.new_tag("div")
    container["data-embedded-src"] = src_url

    nodes = fragment.body.contents if fragment.body else fragment.contents
    if not nodes:
        container.string = html
    else:
        for node in list(nodes):
            container.append(node)

    iframe.replace_with(container)


async def embed_iframes(
    soup: BeautifulSoup, client: httpx.AsyncClient, base_url: str
) -> dict[str, str]:
    iframe_tags = [iframe for iframe in soup.find_all("iframe") if iframe.get("src")]
    if not iframe_tags:
        return {}

    urls = [urljoin(base_url, iframe.get("src", "")) for iframe in iframe_tags]
    tasks = [_fetch_iframe_payload(client, url) for url in urls]
    payloads = await asyncio.gather(*tasks, return_exceptions=True)

    collected_metadata: dict[str, str] = {}
    for iframe, url, payload in zip(iframe_tags, urls, payloads):
        if isinstance(payload, Exception):
            html, loaded = f"[Failed to embed iframe from {url}: {payload}]", False
            fragment = None
        else:
            html, loaded = payload
            fragment = BeautifulSoup(html, "html.parser") if loaded else None

        iframe_metadata = extract_metadata(fragment) if fragment else {}
        _replace_iframe_with_content(soup, iframe, html, url, loaded, fragment)

        for key, value in iframe_metadata.items():
            collected_metadata.setdefault(key, value)

    return collected_metadata


def extract_metadata(soup: BeautifulSoup) -> dict[str, str]:
    metadata: dict[str, str] = {}
    for meta in soup.find_all("meta"):
        key = meta.get("name") or meta.get("property") or meta.get("http-equiv")
        content = meta.get("content")
        if not key or content is None:
            continue
        metadata[key] = content
    return metadata



def sanitize_content_tree(soup: BeautifulSoup) -> BeautifulSoup:
    layout_tokens = {"header", "footer", "nav", "sidebar", "menu", "advert", "ads", "sponsor"}
    for element in soup.find_all(True):
        if not isinstance(element, Tag):
            continue
        attrs = element.attrs or {}
        style = (attrs.get("style") or "")
        style = style.replace(" ", "").lower()
        if "hidden" in attrs:
            element.decompose()
            continue
        if attrs.get("aria-hidden") == "true":
            element.decompose()
            continue
        if "display:none" in style or "visibility:hidden" in style:
            element.decompose()
            continue
        if element.name == "a" and element.get("href") == "#":
            element.unwrap()
            continue
        id_attr = (attrs.get("id") or "").lower()
        class_tokens = [token.lower() for token in attrs.get("class", [])]
        if (
            element.name in layout_tokens
            or any(token in id_attr for token in layout_tokens)
            or any(any(token in cls for token in layout_tokens) for cls in class_tokens)
        ):
            element.decompose()
            continue
    return soup


def to_markdown(html: str) -> str:
    return convert(
        html,
        preprocessing=PreprocessingOptions(
            enabled=True,
            preset="aggressive",
        ),
        options=ConversionOptions(
            extract_metadata=False,
            strip_tags=["button", "svg"],
            autolinks=False,
        ),
    )


@doguda
async def url_to_text(url: str) -> UrlToTextResponse:
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        iframe_metadata = await embed_iframes(soup, client, str(response.url))
        rendered_html = soup.prettify()
        metadata = extract_metadata(soup)
        for key, value in iframe_metadata.items():
            metadata.setdefault(key, value)
        sanitized_soup = sanitize_content_tree(soup)
        markdown_content = to_markdown(sanitized_soup.prettify())
        text_content = sanitized_soup.get_text("\n", strip=True)

    return UrlToTextResponse(
        source_url=str(response.url),
        timestamp_millis=int(time() * 1000),
        raw=rendered_html,
        text=text_content,
        markdown=markdown_content,
        metadata=metadata,
    )
