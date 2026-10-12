import html, json, os, re, sys, urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

KIND=os.environ.get("BLOG_KIND", "cobol")
CONFIG={
 "cobol":("COBOL現場ノート", "COBOLの読み解き・データ定義・保守の一般知識。勤務先、顧客、実システム由来の情報を作らない。処理系差がある事項は断定しない。", "https://gfr254.github.io/cobol-field-notes/"),
 "automation":("業務自動化の実例集", "架空データでの安全な業務自動化。実在の勤務先や顧客情報を含めず、測定していない効果・数値を主張しない。", "https://gfr254.github.io/automation-casebook/"),
 "pc":("PCサポートガイド", "初心者向けPCの安全な確認手順。データ消去、レジストリ変更、管理者権限コマンド、セキュリティ回避、機器分解を勧めない。仕事用端末は管理者に相談するよう案内。", "https://gfr254.github.io/pc-support-guide/")
}
if KIND not in CONFIG: raise SystemExit("Unknown BLOG_KIND")
site, scope, base=CONFIG[KIND]
key=os.environ.get("OPENAI_API_KEY", "").strip()
if not key: raise SystemExit("OPENAI_API_KEY is required; no article was published")
entries=Path("articles.json")
old=json.loads(entries.read_text(encoding="utf-8")) if entries.exists() else []
prior="\n".join(x.get("title","") for x in old[-40:])
now=datetime.now(ZoneInfo("Asia/Tokyo")); date=now.strftime("%Y-%m-%d")
if any(x.get("date")==date for x in old): raise SystemExit("An article already exists for today; refusing duplicate publication")
system=f"あなたは{site}の日本語編集者です。対象: {scope}。独自の説明と具体的な確認手順を含む、役立つ記事を1本書く。未確認の統計・価格・日付・経験談・勤務先や顧客の情報を捏造しない。事実が処理系や環境で異なるときは条件を明記する。既存記事と重複させない。本文はMarkdown、700〜1600字程度。返答はJSON objectのみで title, description, body を返す。タイトル:30字以内。"
user=f"今日の日付: {date} (日本時間)。既存タイトル: {prior}

次の条件で新しい記事を作成してください。説明を一般化し、具体的なリストまたは段階的な手順を含め、読者が安全に試せる範囲にとどめてください。"
payload={"model":os.environ.get("OPENAI_MODEL","gpt-4o-mini"),"temperature":0.5,"max_tokens":2200,"response_format":{"type":"json_object"},"messages":[{"role":"system","content":system},{"role":"user","content":user}]}
req=urllib.request.Request("https://api.openai.com/v1/chat/completions",data=json.dumps(payload).encode(),headers={"Authorization":"Bearer "+key,"Content-Type":"application/json"},method="POST")
with urllib.request.urlopen(req,timeout=90) as r: data=json.loads(r.read())
raw=data["choices"][0]["message"]["content"]
article=json.loads(raw)
title=str(article.get("title","")).strip(); desc=str(article.get("description","")).strip(); body=str(article.get("body","")).strip()
if not (8<=len(title)<=60 and 30<=len(desc)<=180 and 650<=len(body)<=6000): raise SystemExit("Generated article failed length checks; nothing published")
if title.casefold() in {x.get("title","").casefold() for x in old}: raise SystemExit("Duplicate title; nothing published")
if re.search(r"<\s*/?\s*(script|iframe|style|img|video|audio)\b|javascript:",body,re.I): raise SystemExit("Unsafe markup found; nothing published")
if KIND=="pc" and re.search(r"regedit|レジストリ|diskpart|format c:|管理者として実行|初期化|データを削除",body,re.I): raise SystemExit("Potentially destructive PC guidance; nothing published")

def render_md(text):
    out=[]; para=[]; list_tag=None
    def flush():
        nonlocal para
        if para: out.append("<p>"+html.escape(" ".join(para))+"</p>"); para=[]
    for line in text.splitlines():
        s=line.strip()
        if not s: flush(); list_tag=None; continue
        m=re.match(r"^(#{2,3})\s+(.+)$",s)
        if m: flush(); out.append(f"<h{len(m.group(1))}>{html.escape(m.group(2))}</h{len(m.group(1))}>"); list_tag=None; continue
        if re.match(r"^[-*]\s+",s): flush(); item=re.sub(r"^[-*]\s+","",s); out.append("<p>・"+html.escape(item)+"</p>"); continue
        if re.match(r"^\d+[.)]\s+",s): flush(); item=re.sub(r"^\d+[.)]\s+","",s); out.append("<p>"+html.escape(item)+"</p>"); continue
        para.append(s)
    flush(); return "\n".join(out)
Path("articles").mkdir(exist_ok=True)
slug=date.replace("-","")
content=render_md(body)
article_html=f'''<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="description" content="{html.escape(desc,quote=True)}"><title>{html.escape(title)}｜{html.escape(site)}</title><style>body{{margin:0;background:#f6f8fa;color:#202b3c;font:16px/1.9 system-ui,sans-serif}}main{{max-width:780px;margin:5vh auto;padding:24px}}a{{color:#205f88}}article{{background:white;border:1px solid #dbe2ea;border-radius:16px;padding:clamp(20px,5vw,38px)}}small{{color:#58677a}}</style><main><p><a href="{base}">← {html.escape(site)}</a></p><article><small>{date} · 自動作成記事</small><h1>{html.escape(title)}</h1><p>{html.escape(desc)}</p>{content}<p><small>環境によって異なる点は、公式資料や管理者の案内も確認してください。</small></p></article></main></html>'''
Path(f"articles/{slug}.html").write_text(article_html,encoding="utf-8")
card=f'<article><h2><a href="articles/{slug}.html">{html.escape(title)}</a></h2><p>{html.escape(desc)}</p><small>{date}</small></article>'
index=Path("index.html"); page=index.read_text(encoding="utf-8")
if "</main>" not in page: raise SystemExit("Site template has no main section; refusing publication")
page=page.replace("</main>",card+"</main>",1); index.write_text(page,encoding="utf-8")
old.append({"date":date,"title":title,"description":desc,"url":base+"articles/"+slug+".html"})
entries.write_text(json.dumps(old,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
print(f"Created {date}: {title}")