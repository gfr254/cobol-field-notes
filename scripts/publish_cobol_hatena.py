import base64
import html
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from zoneinfo import ZoneInfo


def required_env(name):
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"Required environment variable is missing: {name}")
    return value


def request(url, method="GET", headers=None, body=None):
    req = urllib.request.Request(url, data=body, headers=headers or {}, method=method)
    try:
        return urllib.request.urlopen(req, timeout=90)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP request failed with status {exc.code}") from None
    except urllib.error.URLError:
        raise RuntimeError("Network request failed") from None


def atom_feed_entries(endpoint, headers):
    seen_urls = set()
    url = endpoint
    titles = set()
    today_has_entry = False
    today = datetime.now(ZoneInfo("Asia/Tokyo")).date()

    for _ in range(20):
        if url in seen_urls:
            raise RuntimeError("Hatena feed pagination repeated a URL; refusing to publish")
        seen_urls.add(url)
        with request(url, headers=headers) as response:
            root = ET.fromstring(response.read())
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        if root.tag != "{http://www.w3.org/2005/Atom}feed":
            raise RuntimeError("Hatena returned an unexpected Atom feed")
        for entry in root.findall("atom:entry", ns):
            title = entry.findtext("atom:title", default="", namespaces=ns)
            if title:
                titles.add(title.strip().casefold())
            published = entry.findtext("atom:published", default="", namespaces=ns)
            if not published:
                published = entry.findtext("atom:updated", default="", namespaces=ns)
            try:
                timestamp = datetime.fromisoformat(published.replace("Z", "+00:00"))
                if timestamp.astimezone(ZoneInfo("Asia/Tokyo")).date() == today:
                    today_has_entry = True
            except (ValueError, TypeError):
                continue
        next_url = None
        for link in root.findall("atom:link", ns):
            if link.attrib.get("rel") == "next":
                next_url = urllib.parse.urljoin(url, link.attrib.get("href", ""))
                break
        if not next_url:
            return titles, today_has_entry
        parsed = urllib.parse.urlparse(next_url)
        if parsed.scheme != "https" or parsed.hostname != "blog.hatena.ne.jp":
            raise RuntimeError("Hatena returned an unexpected pagination URL")
        url = next_url

    raise RuntimeError("Hatena feed pagination exceeded the safety limit")


def generate_article(api_key, date, previous_titles):
    system = (
        "あなたはCOBOLの一般的な実務知識を解説する日本語編集者です。"
        "記事は特定の勤務先、顧客、実在システム、個人の経験談を含めず、"
        "公開済みの一般知識だけを扱ってください。未確認の仕様や効果を断定せず、"
        "処理系・環境によって違う場合は条件を明記してください。"
        "読者が安全に学べる具体例を使い、秘密情報や実データを作らないでください。"
        "本文はプレーンテキストで、Markdown記法・HTML・コードフェンスは使わないでください。"
        "説明が必要なCOBOLコードは、短い架空の一般例だけにしてください。"
        "日本語で600〜1400字程度。返答はJSON objectのみで、title、bodyを返してください。"
    )
    user = (
        f"日本時間の日付は{date}です。次の既存記事と重複しない、"
        f"COBOLの読解・データ定義・ファイル処理・テスト・保守・キャリアに関する"
        f"実用的な記事を1本作成してください。\n既存タイトル: "
        + " / ".join(sorted(previous_titles)[-80:])
        + "\nタイトルは日本語で8〜40字にしてください。"
    )
    payload = {
        "model": os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
        "temperature": 0.4,
        "max_tokens": 2000,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    req = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": "Bearer " + api_key,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with request(req.full_url, method="POST", headers=dict(req.header_items()), body=req.data) as response:
        result = json.loads(response.read())
    article = json.loads(result["choices"][0]["message"]["content"])
    title = str(article.get("title", "")).strip()
    body = str(article.get("body", "")).strip()
    if not 8 <= len(title) <= 40 or not 600 <= len(body) <= 6000:
        raise RuntimeError("Generated article failed length checks; nothing was published")
    if re.search(r"<\s*/?\s*[a-zA-Z!]", body) or re.search(r"```|^\s{0,3}#{1,6}\s", body, re.M):
        raise RuntimeError("Generated article is not plain text; nothing was published")
    if re.search(r"勤務先|顧客|実在の.*システム|社内情報|個人情報", title + "\n" + body):
        raise RuntimeError("Generated article may contain private workplace material; nothing was published")
    return title, body


def escape_xml(value):
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )



    def plain_text_to_html(text):
        paragraphs = re.split(r"\n\s*\n+", str(text or "").strip())
        return "\n".join(
            "<p>" + html.escape(paragraph.strip()).replace("\n", "<br>") + "</p>"
            for paragraph in paragraphs
            if paragraph.strip()
        )


    def format_existing_article(endpoint, headers, expected_title):
        seen_urls = set()
        url = endpoint
        found = None
        for _ in range(20):
            if url in seen_urls:
                raise RuntimeError("Hatena feed pagination repeated a URL; refusing to edit")
            seen_urls.add(url)
            with request(url, headers=headers) as response:
                root = ET.fromstring(response.read())
            if root.tag != "{http://www.w3.org/2005/Atom}feed":
                raise RuntimeError("Hatena returned an unexpected Atom feed")
            for entry in root.findall("atom:entry", {"atom": "http://www.w3.org/2005/Atom"}):
                title = entry.findtext("atom:title", default="", namespaces={"atom": "http://www.w3.org/2005/Atom"}).strip()
                if title.casefold() == expected_title.strip().casefold():
                    if found is not None:
                        raise RuntimeError("Multiple matching Hatena entries found; refusing to edit")
                    found = entry
            next_url = None
            for link in root.findall("atom:link", {"atom": "http://www.w3.org/2005/Atom"}):
                if link.attrib.get("rel") == "next":
                    next_url = urllib.parse.urljoin(url, link.attrib.get("href", ""))
                    break
            if not next_url:
                break
            parsed_next = urllib.parse.urlparse(next_url)
            if parsed_next.scheme != "https" or parsed_next.hostname != "blog.hatena.ne.jp":
                raise RuntimeError("Hatena returned an unexpected pagination URL")
            url = next_url
        else:
            raise RuntimeError("Hatena feed pagination exceeded the safety limit")
        if found is None:
            raise RuntimeError("Matching published article was not found; refusing to create a post")
        atom_ns = "http://www.w3.org/2005/Atom"
        content = found.find("atom:content", {"atom": atom_ns})
        if content is None or content.attrib.get("type") not in ("text", "text/plain") or content.text is None:
            raise RuntimeError("Article is not plain text; refusing to reformat")
        edit_link = next((link.attrib.get("href") for link in found.findall("atom:link", {"atom": atom_ns}) if link.attrib.get("rel") == "edit"), None)
        if not edit_link:
            raise RuntimeError("Hatena edit link not found; refusing to edit")
        parsed_edit = urllib.parse.urlparse(urllib.parse.urljoin(endpoint, edit_link))
        expected_prefix = urllib.parse.urlparse(endpoint).path + "/"
        if parsed_edit.scheme != "https" or parsed_edit.hostname != "blog.hatena.ne.jp" or not parsed_edit.path.startswith(expected_prefix):
            raise RuntimeError("Hatena returned an unexpected edit URL; refusing to edit")
        root = ET.Element("{" + atom_ns + "}entry")
        ET.SubElement(root, "{" + atom_ns + "}title").text = expected_title
        ET.SubElement(root, "{" + atom_ns + "}content", {"type": "html"}).text = plain_text_to_html(content.text)
        for category in found.findall("atom:category", {"atom": atom_ns}):
            if category.attrib.get("term"):
                ET.SubElement(root, "{" + atom_ns + "}category", {"term": category.attrib["term"]})
        put_headers = {**headers, "Content-Type": "application/atom+xml; charset=utf-8"}
        with request(parsed_edit.geturl(), method="PUT", headers=put_headers, body=ET.tostring(root, encoding="utf-8", xml_declaration=True)) as response:
            pass
        print("Formatted existing article: " + expected_title)


    def process_format_request(endpoint, headers):
        request_path = "format-request.json"
        if not os.path.exists(request_path):
            return False
        with open(request_path, "r", encoding="utf-8") as file:
            data = json.load(file)
        if data.get("action") != "format_existing" or not isinstance(data.get("title"), str) or not data["title"].strip():
            raise RuntimeError("Invalid format request; refusing to publish or edit")
        format_existing_article(endpoint, headers, data["title"])
        return True

    def main():
    user_id = required_env("HATENA_USER_ID")
    blog_id = required_env("HATENA_COBOL_BLOG_ID")
    api_key = required_env("HATENA_API_KEY")
    openai_key = required_env("OPENAI_API_KEY")
    endpoint = (
        "https://blog.hatena.ne.jp/"
        + urllib.parse.quote(user_id, safe="")
        + "/"
        + urllib.parse.quote(blog_id, safe="")
        + "/atom/entry"
    )
    auth = "Basic " + base64.b64encode(f"{user_id}:{api_key}".encode()).decode()
    headers = {"Accept": "application/atom+xml", "Authorization": auth}

    if process_format_request(endpoint, headers):
        return

    existing_titles, already_posted_today = atom_feed_entries(endpoint, headers)
    if already_posted_today:
        print("An article already exists for today in Asia/Tokyo; no article was generated or published.")
        return

    date = datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%Y-%m-%d")
    title, body = generate_article(openai_key, date, existing_titles)
    if title.casefold() in existing_titles:
        raise RuntimeError("Duplicate title found; nothing was published")

    xml = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<entry xmlns="http://www.w3.org/2005/Atom">'
        f"<title>{escape_xml(title)}</title>"
        f'<content type="html">{escape_xml(plain_text_to_html(body))}</content>'
        "<category term=\"COBOL\"/>"
        "</entry>"
    ).encode("utf-8")
    post_headers = {
        **headers,
        "Content-Type": "application/atom+xml; charset=utf-8",
    }
    with request(endpoint, method="POST", headers=post_headers, body=xml) as response:
        location = response.headers.get("Location", "")
    print(f"Published COBOL article: {title}")
    if location:
        print(f"Article URL: {location}")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"COBOL Hatena publishing stopped: {error}", file=sys.stderr)
        raise SystemExit(1)
