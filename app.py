import os
import time
import csv
import emoji
import re
import nltk
import pandas as pd
from flask import Flask, render_template, request, send_file, redirect, url_for, flash
from instaloader import Instaloader, Post, Profile, ConnectionException, BadResponseException
from textblob import TextBlob
from matplotlib import pyplot as plt
from nltk.tokenize import word_tokenize
import random
import io
import yaml
import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("logs/instagram_scraper.log"),
        logging.StreamHandler()
    ],
)
log = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "development_key")  # Replace with a secure key in production

# Ensure required directories exist
os.makedirs("static", exist_ok=True)
os.makedirs("logs", exist_ok=True)

# Download required NLTK data
nltk.download("punkt", quiet=True)

# Load Instagram credentials from config.yml
with open('config.yml') as file:
    account = yaml.safe_load(file)

# Initialize Instaloader
L = Instaloader()

# Log in to Instagram
try:
    L.login(account['username'], account['password'])
    log.info("Logged in to Instagram successfully.")
except Exception as e:
    log.error(f"Failed to log in to Instagram: {e}")
    raise e

def random_delay(min_seconds=2, max_seconds=5):
    """Introduces a random delay with jitter to mimic human behavior."""
    delay = random.uniform(min_seconds, max_seconds)
    time.sleep(delay)

def scrape_comments(post_shortcode: str, max_comments: int = 10) -> Tuple[List[str], List[str]]:
    """
    Scrapes comments from an Instagram post using Instaloader.

    Args:
        post_shortcode (str): The shortcode of the Instagram post.
        max_comments (int): Maximum number of comments to scrape.

    Returns:
        Tuple[List[str], List[str]]: Lists of usernames and their corresponding comments.
    """
    try:
        post = Post.from_shortcode(L.context, post_shortcode)
        log.info(f"Scraping comments from post: {post.url}")
        comments = post.get_comments()
        user_names = []
        user_comments = []
        for comment in comments:
            if len(user_names) >= max_comments:
                break
            user_names.append(comment.owner.username)
            comment_text = comment.text.replace('\n', ' ').strip()
            comment_text = emoji.demojize(comment_text)
            user_comments.append(comment_text)
        log.info(f"Scraped {len(user_names)} comments.")
        return user_names, user_comments
    except Exception as e:
        log.error(f"Error scraping comments: {e}")
        return [], []

def perform_sentiment_analysis(user_comments: List[str]) -> Dict:
    """
    Performs sentiment analysis on a list of comments.

    Args:
        user_comments (List[str]): List of comment texts.

    Returns:
        Dict: Sentiment analysis results and plot paths.
    """
    try:
        df = pd.DataFrame({"comment": user_comments})

        # Calculate sentiment scores
        df["polarity"] = df["comment"].apply(lambda x: TextBlob(x).sentiment.polarity)
        df["subjectivity"] = df["comment"].apply(lambda x: TextBlob(x).sentiment.subjectivity)

        # Classify sentiment
        df["sentiment"] = df["polarity"].apply(
            lambda x: "Positive" if x > 0.05 else ("Negative" if x < -0.05 else "Neutral")
        )

        # Extract positive and negative words
        positive_words = []
        negative_words = []
        for comment in df["comment"]:
            tokens = word_tokenize(comment.lower())
            tokens = [re.sub(r'\W+', '', word) for word in tokens]  # Remove non-alphanumerics
            blob = TextBlob(' '.join(tokens))
            for word, tag in blob.tags:
                word_blob = TextBlob(word)
                polarity = word_blob.sentiment.polarity
                if polarity > 0.1:
                    positive_words.append(word)
                elif polarity < -0.1:
                    negative_words.append(word)

        positive_word_counts = pd.Series(positive_words).value_counts().head(20)
        negative_word_counts = pd.Series(negative_words).value_counts().head(20)

        # Generate visualizations
        generate_sentiment_plots(df, positive_word_counts, negative_word_counts)

        # Prepare sentiment distribution data
        sentiment_distribution = df["sentiment"].value_counts().to_dict()

        return {
            "sentiment_distribution": sentiment_distribution,
            "sentiment_plot": url_for('static', filename='sentiment_plot.png'),
            "positive_words_plot": url_for('static', filename='positive_words.png') if not positive_word_counts.empty else None,
            "negative_words_plot": url_for('static', filename='negative_words.png') if not negative_word_counts.empty else None,
        }

    except Exception as e:
        log.error(f"Sentiment analysis failed: {e}")
        return {}

def generate_sentiment_plots(df: pd.DataFrame, positive_word_counts: pd.Series, negative_word_counts: pd.Series):
    """
    Generates sentiment analysis visualizations.

    Args:
        df (pd.DataFrame): DataFrame containing comments and sentiment scores.
        positive_word_counts (pd.Series): Series of positive word counts.
        negative_word_counts (pd.Series): Series of negative word counts.
    """
    plt.style.use("seaborn")

    # Sentiment distribution plot
    plt.figure(figsize=(10, 6))
    colors = {"Positive": "#2ecc71", "Neutral": "#95a5a6", "Negative": "#e74c3c"}
    sentiment_counts = df["sentiment"].value_counts()
    sentiment_counts.plot(
        kind="bar", color=[colors.get(x, "#95a5a6") for x in sentiment_counts.index]
    )
    plt.title("Comment Sentiment Distribution", pad=20)
    plt.xlabel("Sentiment")
    plt.ylabel("Count")
    plt.xticks(rotation=0)
    plt.tight_layout()
    plt.savefig("static/sentiment_plot.png")
    plt.close()
    log.info("Generated sentiment distribution plot.")

    # Positive words plot
    if not positive_word_counts.empty:
        plt.figure(figsize=(10, 6))
        positive_word_counts.plot(kind="bar", color="#2ecc71")
        plt.title("Top Positive Words", pad=20)
        plt.xlabel("Words")
        plt.ylabel("Frequency")
        plt.xticks(rotation=45)
        plt.tight_layout()
        plt.savefig("static/positive_words.png")
        plt.close()
        log.info("Generated top positive words plot.")

    # Negative words plot
    if not negative_word_counts.empty:
        plt.figure(figsize=(10, 6))
        negative_word_counts.plot(kind="bar", color="#e74c3c")
        plt.title("Top Negative Words", pad=20)
        plt.xlabel("Words")
        plt.ylabel("Frequency")
        plt.xticks(rotation=45)
        plt.tight_layout()
        plt.savefig("static/negative_words.png")
        plt.close()
        log.info("Generated top negative words plot.")

@app.route("/", methods=["GET", "POST"])
def index():
    """Renders the home page with the input form and handles form submission."""
    if request.method == "POST":
        # Get form data
        post_url = request.form.get('post_url')
        max_comments = int(request.form.get('max_comments', 10))

        # Input validation
        if not post_url:
            flash("Post URL is required.", "danger")
            return redirect(url_for('index'))

        # Extract post shortcode from URL
        try:
            parsed_url = urllib.parse.urlparse(post_url)
            path_parts = parsed_url.path.strip('/').split('/')
            if len(path_parts) < 2 or path_parts[0] != 'p':
                flash("Invalid Instagram post URL.", "danger")
                return redirect(url_for('index'))
            post_shortcode = path_parts[1]
        except Exception as e:
            log.error(f"Error parsing post URL: {e}")
            flash("Invalid Instagram post URL format.", "danger")
            return redirect(url_for('index'))

        # Scrape comments
        user_names, user_comments = scrape_comments(post_shortcode, max_comments)

        if not user_names or not user_comments:
            flash("No comments scraped.", "warning")
            return redirect(url_for('index'))

        # Export to CSV
        try:
            df = pd.DataFrame({
                'Username': user_names,
                'Comment': user_comments
            })
            csv_path = os.path.join("static", "comments.csv")
            df.to_csv(csv_path, index=False)
            log.info(f"Exported comments to {csv_path}")
        except Exception as e:
            log.error(f"Failed to export comments to CSV: {e}")
            flash("Failed to export comments to CSV.", "danger")
            return redirect(url_for('index'))

        # Perform sentiment analysis
        sentiment_results = perform_sentiment_analysis(user_comments)

        if not sentiment_results:
            flash("Error during sentiment analysis.", "danger")
            return redirect(url_for('index'))

        # Render results
        return render_template('results.html',
                               sentiment_plot=sentiment_results["sentiment_plot"],
                               positive_words_plot=sentiment_results.get("positive_words_plot"),
                               negative_words_plot=sentiment_results.get("negative_words_plot"),
                               sentiment_distribution=sentiment_results["sentiment_distribution"],
                               )

    return render_template("index.html")

@app.route('/download_csv')
def download_csv():
    """Provides the CSV file for download."""
    try:
        csv_path = 'static/comments.csv'
        if os.path.exists(csv_path):
            return send_file(csv_path,
                             mimetype='text/csv',
                             attachment_filename='comments.csv',
                             as_attachment=True)
        else:
            flash("CSV file not found.", "warning")
            return redirect(url_for('index'))
    except Exception as e:
        log.error(f"Error downloading CSV: {e}")
        flash(f"Error downloading CSV: {e}", "danger")
        return redirect(url_for('index'))

if __name__ == "__main__":
    # Run the Flask app
    app.run(debug=False)
