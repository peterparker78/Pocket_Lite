import json
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
from sqlalchemy import or_, desc, asc

from utils import fetch_article_content, estimate_reading_time

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///articles.db"
app.config["SECRET_KEY"] = "your-secret-key-here-change-in-production"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)
migrate = Migrate(app, db)

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
        search_pattern = f"%{search_query}%"
        base_query = base_query.filter(
            or_(
                Article.title.ilike(search_pattern),
                Article.content.ilike(search_pattern),
                Article.url.ilike(search_pattern),
                Article.tags.ilike(search_pattern),
            )
        )

    # Get all articles for tag extraction (before pagination)
    all_articles_for_tags = Article.query.all()

    # Collect all unique tags
    all_tags = set()
    for article in all_articles_for_tags:
        if article.tags:
            for tag in article.tags.split(","):
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

    search_pattern = f"%{query}%"
    articles = (
        Article.query.filter(
            or_(
                Article.title.ilike(search_pattern),
                Article.tags.ilike(search_pattern),
            )
        )
        .limit(10)
        .all()
    )

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

    # Save to database
    article = Article(
        url=url,
        title=title,
        content=content,
        summary=summary,
        images=images_json,
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
def batch_delete():
    """Delete multiple articles at once."""
    data = request.get_json()
    ids = data.get("ids", [])

    if not ids:
        return jsonify({"success": False, "error": "No IDs provided"})

    Article.query.filter(Article.id.in_(ids)).delete(synchronize_session=False)
    db.session.commit()
    return jsonify({"success": True, "deleted": len(ids)})


@app.route("/batch-tag", methods=["POST"])
def batch_tag():
    """Add tags to multiple articles at once."""
    data = request.get_json()
    ids = data.get("ids", [])
    tags = data.get("tags", "")

    if not ids:
        return jsonify({"success": False, "error": "No IDs provided"})

    articles = Article.query.filter(Article.id.in_(ids)).all()
    for article in articles:
        current_tags = set(t.strip() for t in article.tags.split(",") if t.strip())
        new_tags = set(t.strip() for t in tags.split(",") if t.strip())
        all_tags = sorted(current_tags | new_tags)
        article.tags = ",".join(all_tags)

    db.session.commit()
    return jsonify({"success": True, "updated": len(articles)})


@app.route("/update-tags/<int:article_id>", methods=["POST"])
def update_tags(article_id):
    """Update tags for an article."""
    article = Article.query.get_or_404(article_id)
    data = request.get_json()
    article.tags = data.get("tags", "")
    db.session.commit()
    tags = [t.strip() for t in article.tags.split(",") if t.strip()] if article.tags else []
    return jsonify({"success": True, "tags": tags})


@app.route("/toggle-favorite/<int:article_id>", methods=["POST"])
def toggle_favorite(article_id):
    """Toggle favorite status for an article."""
    article = Article.query.get_or_404(article_id)
    article.is_favorite = not article.is_favorite
    db.session.commit()
    return jsonify({"success": True, "is_favorite": article.is_favorite})


@app.route("/update-notes/<int:article_id>", methods=["POST"])
def update_notes(article_id):
    """Update personal notes for an article."""
    article = Article.query.get_or_404(article_id)
    data = request.get_json()
    article.notes = data.get("notes", "")
    db.session.commit()
    return jsonify({"success": True})


@app.route("/update-progress/<int:article_id>", methods=["POST"])
def update_progress(article_id):
    """Update reading progress for an article."""
    article = Article.query.get_or_404(article_id)
    data = request.get_json()
    article.reading_progress = data.get("progress", 0)
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

            html_content = f"""
            <html>
            <head>
                <title>{article.title or "Article"}</title>
                <style>
                    body {{ font-family: Georgia, serif; line-height: 1.6; padding: 20px; max-width: 700px; margin: 0 auto; }}
                    h1 {{ font-size: 2em; margin-bottom: 0.5em; }}
                    .meta {{ color: #666; font-size: 0.9em; margin-bottom: 2em; padding-bottom: 1em; border-bottom: 1px solid #eee; }}
                    p {{ margin-bottom: 1em; }}
                </style>
            </head>
            <body>
                <h1>{article.title or "Article"}</h1>
                <div class="meta">
                    <p>Source: <a href="{article.url}">{article.url}</a></p>
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
            flash(f"EPUB export failed: {str(e)}", "error")
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


if __name__ == "__main__":
    app.run(debug=True)
