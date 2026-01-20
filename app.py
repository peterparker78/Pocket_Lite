from datetime import datetime
from flask import Flask, request, render_template, redirect, url_for, jsonify
from flask_sqlalchemy import SQLAlchemy
from utils import fetch_article_content

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///articles.db"
db = SQLAlchemy(app)


class Article(db.Model):
    """Database model for saved articles."""

    id = db.Column(db.Integer, primary_key=True)
    url = db.Column(db.String(500), nullable=False)
    title = db.Column(db.String(200))
    content = db.Column(db.Text, nullable=False)
    tags = db.Column(db.String(500), default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


@app.route("/")
def home():
    """Show a form to enter a URL and list all saved articles."""
    tag_filter = request.args.get("tag", "").strip()

    # Get all articles first to extract all unique tags
    all_articles = Article.query.order_by(Article.created_at.desc()).all()

    # Collect all unique tags
    all_tags = set()
    for article in all_articles:
        if article.tags:
            for tag in article.tags.split(","):
                tag = tag.strip()
                if tag:
                    all_tags.add(tag)
    all_tags = sorted(all_tags)

    # Filter articles if tag is specified
    if tag_filter:
        articles = [a for a in all_articles if tag_filter in [t.strip() for t in (a.tags or "").split(",")]]
    else:
        articles = all_articles

    return render_template("home.html", articles=articles, all_tags=all_tags, active_tag=tag_filter)


@app.route("/process", methods=["POST"])
def process():
    """Download the URL using browser, extract the main text, and save to database."""
    url = request.form.get("url")

    if not url:
        return "No URL provided", 400

    # Fetch and extract article content using headless browser
    result = fetch_article_content(url)

    if result is None:
        return f"Could not extract content from: {url}", 400

    title = result["title"]
    content = result["text"]  # Already formatted HTML from clean_article_html

    # Save to database
    article = Article(url=url, title=title, content=content)
    db.session.add(article)
    db.session.commit()

    # Content is already HTML formatted, use directly
    return render_template("article.html", title=title, content=content, article_id=article.id, original_url=url)


@app.route("/article/<int:article_id>")
def read_article(article_id):
    """Display a saved article from the database."""
    article = Article.query.get_or_404(article_id)

    # Content is already HTML formatted from clean_article_html
    # For legacy content (plain text), convert to paragraphs
    content = article.content
    if not content.startswith("<"):
        paragraphs = content.split("\n\n")
        content = "".join(f"<p>{p}</p>" for p in paragraphs if p.strip())

    tags = [t.strip() for t in article.tags.split(",") if t.strip()] if article.tags else []
    return render_template("article.html", title=article.title, content=content, article_id=article.id, original_url=article.url, tags=tags)


@app.route("/delete/<int:article_id>", methods=["POST"])
def delete_article(article_id):
    """Delete an article from the database."""
    article = Article.query.get_or_404(article_id)
    db.session.delete(article)
    db.session.commit()
    return redirect(url_for("home"))


@app.route("/update-tags/<int:article_id>", methods=["POST"])
def update_tags(article_id):
    """Update tags for an article."""
    article = Article.query.get_or_404(article_id)
    data = request.get_json()
    article.tags = data.get("tags", "")
    db.session.commit()
    tags = [t.strip() for t in article.tags.split(",") if t.strip()] if article.tags else []
    return jsonify({"success": True, "tags": tags})


if __name__ == "__main__":
    app.run(debug=True)
