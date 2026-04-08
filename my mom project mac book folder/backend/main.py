import asyncio
import json
import uuid
import os
import sys
import threading
from datetime import datetime
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

sys.path.insert(0, os.path.dirname(__file__))

from researcher import research_subjects
from summarizer import summarize_article, generate_overview
from database import save_session, save_article, get_sessions, get_session_articles

PROJECT_DIR = os.path.join(os.path.dirname(__file__), "..")
REPORTS_DIR = os.path.join(PROJECT_DIR, "reports")
os.makedirs(REPORTS_DIR, exist_ok=True)

app = FastAPI(title="PsychNeuro Research Bot")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve frontend
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.exists(FRONTEND_DIR):
    app.mount("/app", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")


@app.get("/")
async def root():
    return JSONResponse({"status": "PsychNeuro Research Bot running", "ui": "/app"})


@app.get("/api/sessions")
async def list_sessions():
    return get_sessions()


@app.get("/api/sessions/{session_id}/articles")
async def session_articles(session_id: str):
    return get_session_articles(session_id)


@app.websocket("/ws/research")
async def research_websocket(websocket: WebSocket):
    await websocket.accept()

    try:
        raw = await websocket.receive_text()
        data = json.loads(raw)
        subjects = data.get("subjects", [])
        max_per_source = data.get("max_per_source", 6)

        if not subjects:
            await websocket.send_json({"type": "error", "message": "No subjects provided"})
            return

        session_id = str(uuid.uuid4())
        save_session(session_id, subjects)

        await websocket.send_json({
            "type": "session_start",
            "session_id": session_id,
            "subjects": subjects,
            "message": f"Starting research on: {', '.join(subjects)}"
        })

        # Collect articles from all sources
        all_articles = []
        async for update in _async_research(subjects, max_per_source):
            if update.get("type") == "articles_ready":
                all_articles = update.get("articles", [])
                await websocket.send_json({
                    "type": "search_complete",
                    "total_found": len(all_articles),
                    "message": f"Found {len(all_articles)} unique articles. Starting AI summarization..."
                })
            else:
                await websocket.send_json(update)
                await asyncio.sleep(0)

        if not all_articles:
            await websocket.send_json({
                "type": "complete",
                "message": "No articles found. Try different search terms.",
                "session_id": session_id,
                "articles": [],
                "overview": ""
            })
            return

        # Summarize articles with Claude
        summarized = []
        total = len(all_articles)
        for i, article in enumerate(all_articles):
            await websocket.send_json({
                "type": "summarizing",
                "message": f"Summarizing article {i+1}/{total}: {article.get('title', '')[:60]}...",
                "progress": round((i / total) * 100),
                "current": i + 1,
                "total": total
            })

            loop = asyncio.get_event_loop()
            article = await loop.run_in_executor(None, summarize_article, article)
            save_article(session_id, article)
            summarized.append(article)

            # Send article immediately as it's summarized
            await websocket.send_json({
                "type": "article",
                "article": article,
                "index": i,
                "total": total
            })
            await asyncio.sleep(0)

        # Generate overview
        await websocket.send_json({
            "type": "status",
            "message": "Generating research overview..."
        })
        loop = asyncio.get_event_loop()
        overview = await loop.run_in_executor(
            None, generate_overview, subjects, summarized
        )

        # Save report file
        loop = asyncio.get_event_loop()
        report_path = await loop.run_in_executor(
            None, save_report, subjects, summarized, overview
        )

        await websocket.send_json({
            "type": "complete",
            "message": "Research complete!",
            "session_id": session_id,
            "overview": overview,
            "total": len(summarized),
            "report_path": report_path
        })

    except WebSocketDisconnect:
        print("Client disconnected")
    except Exception as e:
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass


def save_report(subjects: list, articles: list, overview: str) -> str:
    """Save a self-contained HTML report to the reports folder."""
    date_str = datetime.now().strftime("%Y-%m-%d_%H-%M")
    safe_subjects = "_".join(s.replace(" ", "-")[:20] for s in subjects[:3])
    filename = f"{date_str}_{safe_subjects}.html"
    filepath = os.path.join(REPORTS_DIR, filename)

    def esc(s):
        return str(s or "").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"','&quot;')

    articles_html = ""
    for i, a in enumerate(articles, 1):
        key_points = a.get("key_points") or []
        kp_html = "".join(f"<li>{esc(kp)}</li>" for kp in key_points)
        authors = ", ".join(a.get("authors") or []) or "Unknown"
        rel = int((a.get("reliability_score") or 0) * 100)
        rel_color = "#22c55e" if rel >= 80 else "#eab308" if rel >= 60 else "#ef4444"
        src_type = a.get("source_type","academic")
        badge_color = "#22c55e" if src_type == "peer-reviewed" else "#7c6af7"
        diff = a.get("difficulty","intermediate")
        diff_color = "#22c55e" if diff=="beginner" else "#eab308" if diff=="intermediate" else "#ef4444"
        url = a.get("source_url","")
        implications = a.get("implications","")

        articles_html += f"""
        <div class="article">
            <div class="article-header">
                <div class="article-num">#{i}</div>
                <div class="article-title-wrap">
                    <h3 class="article-title">{esc(a.get('title','Untitled'))}</h3>
                    <div class="meta">
                        <span>👥 {esc(authors)}</span>
                        <span>📅 {a.get('year','N/A')}</span>
                        <span>🔗 {esc((a.get('source') or '').split('—')[0].strip())}</span>
                        <span class="badge" style="background:{badge_color}22;color:{badge_color};border:1px solid {badge_color}44">{esc(src_type)}</span>
                        <span class="badge" style="background:{diff_color}22;color:{diff_color};border:1px solid {diff_color}44">{diff}</span>
                        <span class="badge" style="background:{rel_color}22;color:{rel_color};border:1px solid {rel_color}44">⭐ {rel}% reliable</span>
                    </div>
                </div>
            </div>
            <div class="summary"><strong>📝 Summary:</strong><br>{esc(a.get('summary',''))}</div>
            {f'<div class="key-points"><strong>🔑 Key Points:</strong><ul>{kp_html}</ul></div>' if key_points else ''}
            {f'<div class="implications">💡 <strong>Implication:</strong> {esc(implications)}</div>' if implications else ''}
            {f'<div class="source-link"><a href="{esc(url)}" target="_blank">🔗 View Original Source →</a></div>' if url else ''}
        </div>"""

    subj_tags = " ".join(f'<span class="subj-tag">{esc(s)}</span>' for s in subjects)
    date_display = datetime.now().strftime("%B %d, %Y at %H:%M")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Research Report — {esc(', '.join(subjects))}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'Segoe UI', system-ui, sans-serif; background: #0f1117; color: #e2e8f0; line-height: 1.7; }}
  .page {{ max-width: 900px; margin: 0 auto; padding: 40px 24px; }}

  /* HEADER */
  .report-header {{ background: linear-gradient(135deg,#1e1b4b,#1e3a5f); border-radius: 16px; padding: 32px; margin-bottom: 28px; border: 1px solid rgba(124,106,247,.3); }}
  .report-header h1 {{ font-size: 1.8rem; font-weight: 700; background: linear-gradient(135deg,#a78bfa,#38bdf8); -webkit-background-clip:text; -webkit-text-fill-color:transparent; margin-bottom: 8px; }}
  .report-header .date {{ color: #64748b; font-size: .85rem; margin-bottom: 14px; }}
  .subj-tag {{ background: rgba(124,106,247,.2); border: 1px solid rgba(124,106,247,.4); color: #a78bfa; border-radius: 20px; padding: 4px 12px; font-size: .82rem; margin-right: 6px; display: inline-block; }}
  .stats-row {{ display: flex; gap: 24px; margin-top: 18px; }}
  .stat {{ text-align: center; }}
  .stat .num {{ font-size: 1.6rem; font-weight: 700; color: #5eead4; }}
  .stat .lbl {{ font-size: .72rem; color: #64748b; text-transform: uppercase; letter-spacing: .05em; }}

  /* OVERVIEW */
  .overview {{ background: #1a1d2e; border: 1px solid #2d3252; border-radius: 14px; padding: 24px; margin-bottom: 28px; }}
  .overview h2 {{ font-size: 1rem; color: #5eead4; text-transform: uppercase; letter-spacing: .08em; margin-bottom: 14px; }}
  .overview p {{ color: #94a3b8; font-size: .92rem; white-space: pre-wrap; }}

  /* ARTICLES */
  .articles-title {{ font-size: 1.1rem; font-weight: 600; color: #e2e8f0; margin-bottom: 16px; padding-bottom: 10px; border-bottom: 1px solid #2d3252; }}
  .article {{ background: #1a1d2e; border: 1px solid #2d3252; border-radius: 14px; padding: 22px; margin-bottom: 18px; }}
  .article:hover {{ border-color: rgba(124,106,247,.4); }}
  .article-header {{ display: flex; gap: 14px; margin-bottom: 14px; }}
  .article-num {{ background: rgba(124,106,247,.2); color: #a78bfa; border-radius: 8px; width: 36px; height: 36px; display: flex; align-items: center; justify-content: center; font-weight: 700; font-size: .9rem; flex-shrink: 0; }}
  .article-title {{ font-size: 1rem; font-weight: 600; color: #e2e8f0; margin-bottom: 8px; line-height: 1.4; }}
  .meta {{ display: flex; flex-wrap: wrap; gap: 10px; font-size: .78rem; color: #64748b; }}
  .badge {{ border-radius: 10px; padding: 2px 8px; font-size: .7rem; font-weight: 600; }}
  .summary {{ background: rgba(255,255,255,.03); border-radius: 8px; padding: 14px; font-size: .88rem; color: #94a3b8; margin-bottom: 12px; }}
  .key-points {{ margin-bottom: 12px; font-size: .85rem; color: #94a3b8; }}
  .key-points ul {{ padding-left: 20px; margin-top: 6px; }}
  .key-points li {{ margin-bottom: 4px; }}
  .implications {{ background: rgba(94,234,212,.06); border: 1px solid rgba(94,234,212,.15); border-radius: 8px; padding: 10px 14px; font-size: .82rem; color: #5eead4; margin-bottom: 12px; }}
  .source-link {{ margin-top: 8px; }}
  .source-link a {{ color: #7c6af7; text-decoration: none; font-size: .82rem; }}
  .source-link a:hover {{ text-decoration: underline; }}

  /* FOOTER */
  .footer {{ text-align: center; color: #2d3252; font-size: .78rem; margin-top: 40px; padding-top: 20px; border-top: 1px solid #1a1d2e; }}
</style>
</head>
<body>
<div class="page">

  <div class="report-header">
    <div style="font-size:2rem;margin-bottom:10px">🧠</div>
    <h1>Research Report</h1>
    <div class="date">Generated on {date_display}</div>
    <div>{subj_tags}</div>
    <div class="stats-row">
      <div class="stat"><div class="num">{len(articles)}</div><div class="lbl">Articles</div></div>
      <div class="stat"><div class="num">3</div><div class="lbl">Sources</div></div>
      <div class="stat"><div class="num">{len(subjects)}</div><div class="lbl">Topics</div></div>
    </div>
  </div>

  {'<div class="overview"><h2>✨ Research Overview</h2><p>' + esc(overview) + '</p></div>' if overview else ''}

  <div class="articles-title">📄 Articles ({len(articles)} found)</div>
  {articles_html}

  <div class="footer">PsychNeuro Research Bot · {date_display}</div>
</div>
</body>
</html>"""

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"[Report saved] {filepath}")
    return filepath


async def _async_research(subjects, max_per_source):
    """Wrap the sync generator in async by running it in a thread."""
    loop = asyncio.get_event_loop()
    queue = asyncio.Queue()

    def run_gen():
        try:
            for item in research_subjects(subjects, max_per_source):
                loop.call_soon_threadsafe(queue.put_nowait, item)
        except Exception as e:
            loop.call_soon_threadsafe(queue.put_nowait, {"type": "error", "message": str(e)})
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)  # sentinel

    threading.Thread(target=run_gen, daemon=True).start()

    while True:
        item = await queue.get()
        if item is None:
            break
        yield item
        await asyncio.sleep(0)


if __name__ == "__main__":
    import uvicorn
    print("\n" + "="*60)
    print("  PsychNeuro Research Bot Starting...")
    print("="*60)
    print("  Dashboard: http://localhost:8000/app")
    print("  API:       http://localhost:8000")
    print("="*60 + "\n")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
