import os
import time
import logging
from flask import Flask, render_template, request, redirect, url_for, flash
from instaloader import Instaloader, Profile
from typing import List

# Logging configuration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("logs/instagram_scraper.log"),
        logging.StreamHandler()
    ],
)
log = logging.getLogger(__name__)

# Flask app initialization
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "development_key")

# Directories
os.makedirs("logs", exist_ok=True)

# Instaloader initialization
L = Instaloader()

def fetch_post_urls(username: str, max_posts: int) -> List[str]:
    """Fetches post URLs from the specified Instagram profile."""
    try:
        profile = Profile.from_username(L.context, username)
        log.info(f"Fetching posts for {username}")

        post_urls = []
        for post in profile.get_posts():
            if len(post_urls) >= max_posts:
                break
            post_urls.append(post.url)

        log.info(f"Fetched {len(post_urls)} post URLs.")
        return post_urls

    except Exception as e:
        log.error(f"Failed to fetch posts for {username}: {e}")
        return []

@app.route("/", methods=["GET", "POST"])
def index():
    """Handles the home page and form submissions."""
    if request.method == "POST":
        try:
            # Get form data
            user_username = request.form.get("username")
            user_password = request.form.get("password")
            target_username = request.form.get("target_username")
            max_posts = int(request.form.get("max_posts", 10))

            if not (user_username and user_password and target_username):
                flash("All fields are required.", "danger")
                return redirect(url_for("index"))

            # Login to Instagram
            try:
                L.login(user_username, user_password)
                log.info("Logged in successfully.")
            except Exception as e:
                log.error(f"Login failed: {e}")
                flash("Invalid Instagram credentials.", "danger")
                return redirect(url_for("index"))

            # Fetch post URLs
            post_urls = fetch_post_urls(target_username, max_posts)

            if not post_urls:
                flash("Failed to fetch post URLs. Check the target username or try again.", "danger")
                return redirect(url_for("index"))

            # Render results
            return render_template("result.html", post_urls=post_urls)

        except Exception as e:
            log.error(f"Error processing request: {e}")
            flash("An error occurred. Please try again.", "danger")
            return redirect(url_for("index"))

    return render_template("index.html")

if __name__ == "__main__":
    app.run(debug=True)
