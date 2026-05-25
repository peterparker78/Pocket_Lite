import html
import json
import os
import re
from datetime import datetime
from functools import wraps

from flask import (
    Flask,
    request,
    render_template,
    redirect,
    url_for,
    jsonify,
    flash,
    send_file,
)
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import or_, desc, asc, text

from utils import fetch_article_content, estimate_reading_time, validate_url
from llm import summarize_and_tag

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///articles.db"
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or os.urandom(32).hex()
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)
migrate = Migrate(app, db)
csrf = CSRFProtect(app)

# Rate limiting setup
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://",
)


class Article(db.Model):
    """Database model for saved articles."""

    id = db.Column(db.Integer, primary_key=True)
    url = db.Column(db.String(500), nullable=False)
    title = db.Column(db.String(200))
    content = db.Column(db.Text, nullable=False)
    summary = db.Column(db.Text, default="")
    images = db.Column(db.Text, default="")  # JSON string of image URLs
    tags = db.Column(db.String(500), default="")
    notes = db.Column(db.Text, default="")  # Personal notes
    is_favorite = db.Column(db.Boolean, default=False)
    reading_progress = db.Column(db.Integer, default=0)  # Scroll position %
    reading_time = db.Column(db.Integer, default=0)  # Minutes
    word_count = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    highlights = db.relationship(
        "Highlight", backref="article", cascade="all, delete-orphan", lazy=True
    )

    def to_dict(self):
        """Convert article to dictionary."""
        images = []
        if self.images:
            try:
                images = json.loads(self.images)
            except json.JSONDecodeError:
                pass
        return {
            "id": self.id,
            "url": self.url,
            "title": self.title,
            "summary": self.summary,
            "tags": [t.strip() for t in self.tags.split(",") if t.strip()] if self.tags else [],
            "is_favorite": self.is_favorite,
            "reading_time": self.reading_time,
            "word_count": self.word_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Highlight(db.Model):
    """A user-saved text selection within an article, with an optional note."""

    id = db.Column(db.Integer, primary_key=True)
    article_id = db.Column(
        db.Integer, db.ForeignKey("article.id", ondelete="CASCADE"), nullable=False, index=True
    )
    text = db.Column(db.Text, nullable=False)
    # Short surrounding context to disambiguate duplicate matches when re-locating
    # the highlight in the rendered article body.
    prefix = db.Column(db.String(64), default="")
    suffix = db.Column(db.String(64), default="")
    note = db.Column(db.Text, default="")
    color = db.Column(db.String(16), default="yellow")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "text": self.text,
            "prefix": self.prefix or "",
            "suffix": self.suffix or "",
            "note": self.note or "",
            "color": self.color or "yellow",
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


def init_fts():
    """
    Create the FTS5 virtual table mirroring article(title, content, tags),
    plus triggers to keep it synced. Backfill on first run. Safe to call
    on every startup — uses IF NOT EXISTS for everything.
    """
    with db.engine.begin() as conn:
        conn.execute(text("""
            CREATE VIRTUAL TABLE IF NOT EXISTS article_fts USING fts5(
                title, content, tags,
                content='article',
                content_rowid='id',
                tokenize='porter unicode61'
            )
        """))
        conn.execute(text("""
            CREATE TRIGGER IF NOT EXISTS article_ai AFTER INSERT ON article BEGIN
                INSERT INTO article_fts(rowid, title, content, tags)
                VALUES (new.id, new.title, new.content, new.tags);
            END
        """))
        conn.execute(text("""
            CREATE TRIGGER IF NOT EXISTS article_ad AFTER DELETE ON article BEGIN
                INSERT INTO article_fts(article_fts, rowid, title, content, tags)
                VALUES ('delete', old.id, old.title, old.content, old.tags);
            END
        """))
        conn.execute(text("""
            CREATE TRIGGER IF NOT EXISTS article_au AFTER UPDATE ON article BEGIN
                INSERT INTO article_fts(article_fts, rowid, title, content, tags)
                VALUES ('delete', old.id, old.title, old.content, old.tags);
                INSERT INTO article_fts(rowid, title, content, tags)
                VALUES (new.id, new.title, new.content, new.tags);
            END
        """))
        # Backfill if FTS row count diverges from article count (handles
        # both first-run and any out-of-sync index from older revisions).
        article_n = conn.execute(text("SELECT COUNT(*) FROM article")).scalar()
        fts_n = conn.execute(text("SELECT COUNT(*) FROM article_fts")).scalar()
        if fts_n != article_n:
            conn.execute(text("DELETE FROM article_fts"))
            conn.execute(text("""
                INSERT INTO article_fts(rowid, title, content, tags)
                SELECT id, title, content, tags FROM article
            """))
            # External content tables need an explicit rebuild for the
            # inverted index to be queryable after bulk inserts.
            conn.execute(text("INSERT INTO article_fts(article_fts) VALUES('rebuild')"))


def fts_query_string(user_input: str, prefix_last: bool = False) -> str:
    """
    Build a safe FTS5 MATCH expression from raw user input. Splits on
    whitespace, strips FTS metacharacters, double-quotes each token so
    things like dots, hyphens and apostrophes are treated literally.
    With prefix_last=True the final token gets a '*' for prefix match
    (used for autocomplete).
    """
    tokens = re.findall(r"[\w'\-]+", user_input or "", flags=re.UNICODE)
    if not tokens:
        return ""
    parts = []
    for i, t in enumerate(tokens):
        t = t.replace('"', "")
        if not t:
            continue
        if prefix_last and i == len(tokens) - 1:
            parts.append(f'"{t}"*')
        else:
            parts.append(f'"{t}"')
    return " ".join(parts)


# Template filters
@app.template_filter("format_date")
def format_date(value):
    """Format datetime for display."""
    if value is None:
        return ""
    return value.strftime("%B %d, %Y")


@app.template_filter("truncate")
def truncate_filter(value, length=200):
    """Truncate text to specified length."""
    if not value:
        return ""
    if len(value) <= length:
        return value
    return value[:length].rsplit(" ", 1)[0] + "..."


def get_sorted_articles(query, sort_by="date", order="desc"):
    """Apply sorting to article query."""
    if sort_by == "date":
        sort_column = Article.created_at
    elif sort_by == "title":
        sort_column = Article.title
    elif sort_by == "reading_time":
        sort_column = Article.reading_time
    elif sort_by == "word_count":
        sort_column = Article.word_count
    else:
        sort_column = Article.created_at

    if order == "asc":
        return query.order_by(asc(sort_column))
    return query.order_by(desc(sort_column))


@app.route("/")
def home():
    """Show a form to enter a URL and list all saved articles."""
    tag_filter = request.args.get("tag", "").strip()
    search_query = request.args.get("q", "").strip()
    sort_by = request.args.get("sort", "date")
    order = request.args.get("order", "desc")
    favorites_only = request.args.get("favorites", "0") == "1"
    page = request.args.get("page", 1, type=int)
    per_page = 20

    # Base query
    base_query = Article.query

    # Apply filters
    if favorites_only:
        base_query = base_query.filter(Article.is_favorite == True)

    if tag_filter:
        base_query = base_query.filter(Article.tags.contains(tag_filter))

    if search_query:
        fts_expr = fts_query_string(search_query)
        if fts_expr:
            matched_ids = [
                row[0]
                for row in db.session.execute(
                    text("SELECT rowid FROM article_fts WHERE article_fts MATCH :q"),
                    {"q": fts_expr},
                ).fetchall()
            ]
            if matched_ids:
                base_query = base_query.filter(Article.id.in_(matched_ids))
            else:
                base_query = base_query.filter(Article.id == -1)
        else:
            # Fall back to URL substring match when input has no FTS-usable tokens
            base_query = base_query.filter(Article.url.ilike(f"%{search_query}%"))

    # Collect all unique tags (query only the tags column, not full articles)
    all_tags = set()
    for (tags_str,) in db.session.query(Article.tags).filter(
        Article.tags.isnot(None), Article.tags != ""
    ):
        for tag in tags_str.split(","):
            tag = tag.strip()
            if tag:
                all_tags.add(tag)
    all_tags = sorted(all_tags)

    # Apply sorting and pagination
    sorted_query = get_sorted_articles(base_query, sort_by, order)
    pagination = sorted_query.paginate(page=page, per_page=per_page, error_out=False)
    articles = pagination.items

    return render_template(
        "home.html",
        articles=articles,
        pagination=pagination,
        all_tags=all_tags,
        active_tag=tag_filter,
        search_query=search_query,
        sort_by=sort_by,
        order=order,
        favorites_only=favorites_only,
    )


@app.route("/search")
def search():
    """AJAX search endpoint for autocomplete."""
    query = request.args.get("q", "").strip()
    if not query or len(query) < 2:
        return jsonify([])

    fts_expr = fts_query_string(query, prefix_last=True)
    if fts_expr:
        rows = db.session.execute(
            text(
                "SELECT rowid FROM article_fts "
                "WHERE article_fts MATCH :q "
                "ORDER BY rank LIMIT 10"
            ),
            {"q": f'({fts_expr}) AND (title:{fts_expr} OR tags:{fts_expr})'},
        ).fetchall()
        ids = [r[0] for r in rows]
        if not ids:
            # Fall back to body match for results that don't hit title/tags
            rows = db.session.execute(
                text(
                    "SELECT rowid FROM article_fts WHERE article_fts MATCH :q "
                    "ORDER BY rank LIMIT 10"
                ),
                {"q": fts_expr},
            ).fetchall()
            ids = [r[0] for r in rows]
        articles = Article.query.filter(Article.id.in_(ids)).all() if ids else []
        # Preserve FTS ranking order
        order_map = {aid: i for i, aid in enumerate(ids)}
        articles.sort(key=lambda a: order_map.get(a.id, 999))
    else:
        articles = []

    results = [
        {
            "id": a.id,
            "title": a.title or "Untitled",
            "url": url_for("read_article", article_id=a.id),
            "tags": [t.strip() for t in a.tags.split(",") if t.strip()] if a.tags else [],
        }
        for a in articles
    ]
    return jsonify(results)


@app.route("/process", methods=["POST"])
@limiter.limit("10 per minute")
def process():
    """Download the URL using browser, extract the main text, and save to database."""
    url = request.form.get("url")

    if not url:
        flash("No URL provided", "error")
        return redirect(url_for("home"))

    # Validate URL to prevent SSRF
    is_valid, error_msg = validate_url(url)
    if not is_valid:
        flash(error_msg, "error")
        return redirect(url_for("home"))

    # Check if article already exists
    existing = Article.query.filter(Article.url == url).first()
    if existing:
        flash("Article already exists in your library", "info")
        return redirect(url_for("read_article", article_id=existing.id))

    # Fetch and extract article content using headless browser
    result = fetch_article_content(url)

    if result is None:
        flash(f"Could not extract content from: {url}", "error")
        return redirect(url_for("home"))

    title = result["title"]
    content = result["text"]
    summary = result.get("summary", "")
    images = result.get("images", [])

    # Calculate reading time and word count
    word_count = len(content.split())
    reading_time = estimate_reading_time(word_count)

    # Store images as JSON
    images_json = json.dumps(images) if images else ""

    # Upgrade summary + suggest tags via Claude (falls back silently if no key)
    tags_str = ""
    llm_result = summarize_and_tag(title, content)
    if llm_result:
        summary = llm_result["summary"]
        tags_str = ",".join(llm_result["tags"])

    # Save to database
    article = Article(
        url=url,
        title=title,
        content=content,
        summary=summary,
        images=images_json,
        tags=tags_str,
        word_count=word_count,
        reading_time=reading_time,
    )
    db.session.add(article)
    db.session.commit()

    flash("Article saved successfully", "success")
    return redirect(url_for("read_article", article_id=article.id))


@app.route("/article/<int:article_id>")
def read_article(article_id):
    """Display a saved article from the database."""
    article = Article.query.get_or_404(article_id)

    # Content is already HTML formatted from clean_article_html
    content = article.content
    if not content.startswith("<"):
        paragraphs = content.split("\n\n")
        content = "".join(f"<p>{p}</p>" for p in paragraphs if p.strip())

    tags = [t.strip() for t in article.tags.split(",") if t.strip()] if article.tags else []

    # Parse images from JSON
    images = []
    if article.images:
        try:
            images = json.loads(article.images)
        except json.JSONDecodeError:
            images = []

    return render_template(
        "article.html",
        title=article.title,
        content=content,
        summary=article.summary,
        images=images,
        notes=article.notes,
        article_id=article.id,
        original_url=article.url,
        tags=tags,
        is_favorite=article.is_favorite,
        reading_time=article.reading_time,
        word_count=article.word_count,
        reading_progress=article.reading_progress,
    )


@app.route("/delete/<int:article_id>", methods=["POST"])
def delete_article(article_id):
    """Delete an article from the database."""
    article = Article.query.get_or_404(article_id)
    db.session.delete(article)
    db.session.commit()
    flash("Article deleted", "success")
    return redirect(url_for("home"))


@app.route("/batch-delete", methods=["POST"])
@limiter.limit("10 per minute")
def batch_delete():
    """Delete multiple articles at once."""
    data = request.get_json()
    ids = data.get("ids", [])

    if not ids:
        return jsonify({"success": False, "error": "No IDs provided"})

    if len(ids) > 100:
        return jsonify({"success": False, "error": "Too many IDs (max 100)"})

    Article.query.filter(Article.id.in_(ids)).delete(synchronize_session=False)
    db.session.commit()
    return jsonify({"success": True, "deleted": len(ids)})


@app.route("/batch-tag", methods=["POST"])
@limiter.limit("10 per minute")
def batch_tag():
    """Add tags to multiple articles at once."""
    data = request.get_json()
    ids = data.get("ids", [])
    tags = data.get("tags", "")

    if not ids:
        return jsonify({"success": False, "error": "No IDs provided"})

    if len(ids) > 100:
        return jsonify({"success": False, "error": "Too many IDs (max 100)"})

    articles = Article.query.filter(Article.id.in_(ids)).all()
    for article in articles:
        current_tags = set(t.strip() for t in article.tags.split(",") if t.strip())
        new_tags = set(t.strip() for t in tags.split(",") if t.strip())
        all_tags = sorted(current_tags | new_tags)
        article.tags = ",".join(all_tags)

    db.session.commit()
    return jsonify({"success": True, "updated": len(articles)})


@app.route("/update-tags/<int:article_id>", methods=["POST"])
@limiter.limit("30 per minute")
def update_tags(article_id):
    """Update tags for an article."""
    article = Article.query.get_or_404(article_id)
    data = request.get_json()
    article.tags = data.get("tags", "")
    db.session.commit()
    tags = [t.strip() for t in article.tags.split(",") if t.strip()] if article.tags else []
    return jsonify({"success": True, "tags": tags})


@app.route("/toggle-favorite/<int:article_id>", methods=["POST"])
@limiter.limit("30 per minute")
def toggle_favorite(article_id):
    """Toggle favorite status for an article."""
    article = Article.query.get_or_404(article_id)
    article.is_favorite = not article.is_favorite
    db.session.commit()
    return jsonify({"success": True, "is_favorite": article.is_favorite})


@app.route("/update-notes/<int:article_id>", methods=["POST"])
@limiter.limit("30 per minute")
def update_notes(article_id):
    """Update personal notes for an article."""
    article = Article.query.get_or_404(article_id)
    data = request.get_json()
    article.notes = data.get("notes", "")
    db.session.commit()
    return jsonify({"success": True})


@app.route("/update-progress/<int:article_id>", methods=["POST"])
@limiter.limit("60 per minute")
def update_progress(article_id):
    """Update reading progress for an article."""
    article = Article.query.get_or_404(article_id)
    data = request.get_json()
    article.reading_progress = data.get("progress", 0)
    db.session.commit()
    return jsonify({"success": True})


@app.route("/article/<int:article_id>/highlights", methods=["GET"])
def list_highlights(article_id):
    """Return all highlights for an article as JSON."""
    Article.query.get_or_404(article_id)
    rows = (
        Highlight.query.filter_by(article_id=article_id)
        .order_by(Highlight.created_at.asc())
        .all()
    )
    return jsonify([h.to_dict() for h in rows])


@app.route("/article/<int:article_id>/highlights", methods=["POST"])
@limiter.limit("60 per minute")
def create_highlight(article_id):
    """Create a new highlight on an article."""
    Article.query.get_or_404(article_id)
    data = request.get_json() or {}
    text_val = (data.get("text") or "").strip()
    if not text_val:
        return jsonify({"success": False, "error": "Empty selection"}), 400
    if len(text_val) > 5000:
        return jsonify({"success": False, "error": "Selection too long"}), 400

    h = Highlight(
        article_id=article_id,
        text=text_val,
        prefix=(data.get("prefix") or "")[:64],
        suffix=(data.get("suffix") or "")[:64],
        note=(data.get("note") or "")[:2000],
        color=(data.get("color") or "yellow")[:16],
    )
    db.session.add(h)
    db.session.commit()
    return jsonify({"success": True, "highlight": h.to_dict()})


@app.route("/highlights/<int:highlight_id>", methods=["PUT"])
@limiter.limit("60 per minute")
def update_highlight(highlight_id):
    """Update a highlight's note or color."""
    h = Highlight.query.get_or_404(highlight_id)
    data = request.get_json() or {}
    if "note" in data:
        h.note = (data.get("note") or "")[:2000]
    if "color" in data:
        h.color = (data.get("color") or "yellow")[:16]
    db.session.commit()
    return jsonify({"success": True, "highlight": h.to_dict()})


@app.route("/highlights/<int:highlight_id>", methods=["DELETE"])
@limiter.limit("60 per minute")
def delete_highlight(highlight_id):
    """Delete a highlight."""
    h = Highlight.query.get_or_404(highlight_id)
    db.session.delete(h)
    db.session.commit()
    return jsonify({"success": True})


@app.route("/export/<int:article_id>")
def export_article(article_id):
    """Export article in various formats."""
    import io
    import tempfile
    import os

    article = Article.query.get_or_404(article_id)
    format_type = request.args.get("format", "md")

    # Clean HTML content for export
    content_text = re.sub(r"<[^>]+>", "", article.content)
    content_text = re.sub(r"\n\s*\n", "\n\n", content_text).strip()

    if format_type == "md":
        # Markdown export
        md_content = f"# {article.title}\n\n"
        md_content += f"**Source:** {article.url}\n\n"
        md_content += f"**Saved:** {article.created_at.strftime('%Y-%m-%d')}\n\n"
        if article.tags:
            md_content += f"**Tags:** {article.tags}\n\n"
        md_content += "---\n\n"
        md_content += content_text

        buffer = io.BytesIO()
        buffer.write(md_content.encode("utf-8"))
        buffer.seek(0)

        filename = re.sub(r"[^\w\s-]", "", article.title or "article").strip().replace(" ", "-")
        return send_file(
            buffer,
            mimetype="text/markdown",
            as_attachment=True,
            download_name=f"{filename}.md",
        )

    elif format_type == "txt":
        # Plain text export
        txt_content = f"{article.title}\n\n"
        txt_content += f"Source: {article.url}\n"
        txt_content += f"Saved: {article.created_at.strftime('%Y-%m-%d')}\n\n"
        txt_content += content_text

        buffer = io.BytesIO()
        buffer.write(txt_content.encode("utf-8"))
        buffer.seek(0)

        filename = re.sub(r"[^\w\s-]", "", article.title or "article").strip().replace(" ", "-")
        return send_file(
            buffer,
            mimetype="text/plain",
            as_attachment=True,
            download_name=f"{filename}.txt",
        )

    elif format_type == "epub":
        # EPUB export
        try:
            from ebooklib import epub

            book = epub.EpubBook()

            # Metadata
            book.set_identifier(f"pocket-lite-{article_id}")
            book.set_title(article.title or "Untitled")
            book.set_language("en")

            # Add author/source
            book.add_author("Pocket Lite Export")

            # Create chapter
            c1 = epub.EpubHtml(title=article.title or "Article", file_name="article.xhtml", lang="en")

            safe_title = html.escape(article.title or "Article")
            safe_url = html.escape(article.url)

            html_content = f"""
            <html>
            <head>
                <title>{safe_title}</title>
                <style>
                    body {{ font-family: Georgia, serif; line-height: 1.6; padding: 20px; max-width: 700px; margin: 0 auto; }}
                    h1 {{ font-size: 2em; margin-bottom: 0.5em; }}
                    .meta {{ color: #666; font-size: 0.9em; margin-bottom: 2em; padding-bottom: 1em; border-bottom: 1px solid #eee; }}
                    p {{ margin-bottom: 1em; }}
                </style>
            </head>
            <body>
                <h1>{safe_title}</h1>
                <div class="meta">
                    <p>Source: <a href="{safe_url}">{safe_url}</a></p>
                    <p>Saved: {article.created_at.strftime('%Y-%m-%d')}</p>
                </div>
                {article.content}
            </body>
            </html>
            """
            c1.set_content(html_content)

            # Add chapter to book
            book.add_item(c1)
            book.toc = (epub.Link("article.xhtml", article.title or "Article", "article"),)
            book.add_item(epub.EpubNcx())
            book.add_item(epub.EpubNav())

            # Create spine
            book.spine = ["nav", c1]

            # Write to temp file
            with tempfile.NamedTemporaryFile(suffix=".epub", delete=False) as tmp:
                tmp_path = tmp.name

            epub.write_epub(tmp_path, book, {})

            filename = re.sub(r"[^\w\s-]", "", article.title or "article").strip().replace(" ", "-")

            response = send_file(
                tmp_path,
                mimetype="application/epub+zip",
                as_attachment=True,
                download_name=f"{filename}.epub",
            )

            # Clean up temp file after sending
            @response.call_on_close
            def cleanup():
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass

            return response

        except Exception as e:
            app.logger.error(f"EPUB export failed for article {article_id}: {e}")
            flash("EPUB export failed. Please try another format.", "error")
            return redirect(url_for("read_article", article_id=article_id))

    else:
        flash("Unsupported format", "error")
        return redirect(url_for("read_article", article_id=article_id))


@app.route("/export-batch", methods=["POST"])
def export_batch():
    """Export multiple articles as a single file."""
    import io
    import zipfile

    data = request.get_json()
    ids = data.get("ids", [])
    format_type = data.get("format", "md")

    if not ids:
        return jsonify({"success": False, "error": "No articles selected"})

    if len(ids) > 100:
        return jsonify({"success": False, "error": "Too many articles (max 100)"})

    articles = Article.query.filter(Article.id.in_(ids)).all()

    buffer = io.BytesIO()

    if format_type == "zip":
        # Create ZIP with individual files
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for article in articles:
                content_text = re.sub(r"<[^>]+>", "", article.content)
                content_text = re.sub(r"\n\s*\n", "\n\n", content_text).strip()

                md_content = f"# {article.title}\n\n"
                md_content += f"**Source:** {article.url}\n\n"
                md_content += f"**Saved:** {article.created_at.strftime('%Y-%m-%d')}\n\n"
                if article.tags:
                    md_content += f"**Tags:** {article.tags}\n\n"
                md_content += "---\n\n"
                md_content += content_text

                filename = re.sub(r"[^\w\s-]", "", article.title or f"article-{article.id}").strip().replace(" ", "-")
                zf.writestr(f"{filename}.md", md_content.encode("utf-8"))

        buffer.seek(0)
        return send_file(
            buffer,
            mimetype="application/zip",
            as_attachment=True,
            download_name="articles-export.zip",
        )

    else:
        # Single combined file
        combined = ""
        for i, article in enumerate(articles):
            content_text = re.sub(r"<[^>]+>", "", article.content)
            content_text = re.sub(r"\n\s*\n", "\n\n", content_text).strip()

            if i > 0:
                combined += "\n\n" + "=" * 80 + "\n\n"

            combined += f"# {article.title}\n\n"
            combined += f"**Source:** {article.url}\n\n"
            combined += f"**Saved:** {article.created_at.strftime('%Y-%m-%d')}\n\n"
            if article.tags:
                combined += f"**Tags:** {article.tags}\n\n"
            combined += "---\n\n"
            combined += content_text

        buffer.write(combined.encode("utf-8"))
        buffer.seek(0)

        return send_file(
            buffer,
            mimetype="text/markdown",
            as_attachment=True,
            download_name="articles-export.md",
        )


@app.errorhandler(429)
def ratelimit_handler(e):
    """Handle rate limit errors."""
    return jsonify({"error": "Rate limit exceeded. Please try again later."}), 429


@app.route("/health")
def health_check():
    """Health check endpoint."""
    return jsonify({"status": "healthy", "timestamp": datetime.utcnow().isoformat()})


with app.app_context():
    db.create_all()  # picks up the new Highlight table without a migration
    init_fts()


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG", "0") == "1")
