import os
import time
import csv
import emoji
import re
import nltk
import pandas as pd
from flask import Flask, render_template, request, send_file, redirect, url_for, flash
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from textblob import TextBlob
from matplotlib import pyplot as plt
from nltk.tokenize import word_tokenize
import random
import io
from werkzeug.utils import secure_filename
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
app.secret_key = os.environ.get("12", "12")  # Replace with a secure key in production

# Ensure required directories exist
os.makedirs("static", exist_ok=True)
os.makedirs("logs", exist_ok=True)

# Download required NLTK data
nltk.download("punkt", quiet=True)

# Define Instagram selectors
INSTAGRAM_SELECTORS = {
    "login_username": "input[name='username']",
    "login_password": "input[name='password']",
    "post_article": 'article[class*="_aagv"]',  # Main container for a post
    "post_links": 'a[href*="/p/"]',  # Post links
    "comments_section": 'ul[class*="_a9z6k"]',  # Comments section
    "comment_items": 'li[class*="_aamw8"]',  # Individual comments
    "load_more_button": 'button[class*="_aacl"]',  # "Load more comments" button
    "username_element": 'a[class*="_aacl"]',  # Username in comments
    "comment_text": 'span[class*="_aacl"]',  # Comment text
    "close_post_button": 'svg[aria-label="Close"]',  # Close button for post modal
}

class InstagramBot:
    def __init__(self, account):
        self.username = account['username']
        self.password = account['password']
        self.info_list = []
        self.visited = set()
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None

    def setup_playwright(self):
        """Initialize Playwright and return the browser and page."""
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=True)
        self.context = self.browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080},
            locale="en-US,en",
        )
        self.page = self.context.new_page()
        log.info("Playwright initialized.")

    def random_delay(self, min_seconds=2, max_seconds=5):
        """Introduces a random delay with jitter to mimic human behavior."""
        delay = random.uniform(min_seconds, max_seconds)
        time.sleep(delay)

    def capture_debug_info(self, context_name):
        """Captures a screenshot and HTML source for debugging."""
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        screenshot_path = f"logs/{context_name}_screenshot_{timestamp}.png"
        html_path = f"logs/{context_name}_page_{timestamp}.html"
        self.page.screenshot(path=screenshot_path, full_page=True)
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(self.page.content())
        log.info(f"Captured screenshot: {screenshot_path} and HTML: {html_path}")

    def login_instagram(self):
        """Logs into Instagram using Playwright with enhanced error handling and stealth measures."""
        try:
            # Navigate to Instagram login page
            self.page.goto("https://www.instagram.com/accounts/login/", timeout=60000)
            self.random_delay(3, 6)

            # Accept cookies if prompted
            try:
                accept_button = self.page.locator("button:has-text('Accept All')")
                if accept_button.is_visible():
                    accept_button.click()
                    self.random_delay(2, 4)
            except PlaywrightTimeoutError:
                log.info("No cookies dialog found")

            # Fill in username and password
            self.page.fill(INSTAGRAM_SELECTORS["login_username"], self.username)
            self.random_delay(1, 2)
            self.page.fill(INSTAGRAM_SELECTORS["login_password"], self.password)
            self.random_delay(1, 2)

            # Click the login button
            self.page.click("button[type='submit']")
            self.random_delay(5, 7)

            # Handle "Save Your Login Info?" prompt
            try:
                not_now_button = self.page.locator("button:has-text('Not Now')")
                if not_now_button.is_visible():
                    not_now_button.click()
                    self.random_delay(2, 3)
            except PlaywrightTimeoutError:
                log.info("No 'Save Your Login Info?' dialog found")

            # Handle "Turn on Notifications" prompt
            try:
                turn_off_button = self.page.locator("button:has-text('Not Now')")
                if turn_off_button.is_visible():
                    turn_off_button.click()
                    self.random_delay(2, 3)
            except PlaywrightTimeoutError:
                log.info("No 'Turn on Notifications' dialog found")

            # Verify successful login by checking presence of Home icon
            if self.page.locator("svg[aria-label='Home']").is_visible():
                log.info("Successfully logged into Instagram")
            else:
                log.error("Failed to log into Instagram")
                self.capture_debug_info("login_failed")
                raise Exception("Login verification failed")

        except Exception as e:
            log.error(f"Error during Instagram login: {e}")
            self.capture_debug_info("login_error")
            raise

    def navigate_to_post(self, post_url):
        """Navigates to a specific Instagram post."""
        try:
            self.page.goto(post_url, timeout=60000)
            self.random_delay(5, 8)

            # Verify post page loaded by checking for comments section
            if self.page.locator(INSTAGRAM_SELECTORS["comments_section"]).count() > 0:
                log.info(f"Successfully navigated to post: {post_url}")
            else:
                log.error(f"Failed to load post page: {post_url}")
                self.capture_debug_info("navigate_post_failed")
                raise Exception("Post page verification failed")

        except Exception as e:
            log.error(f"Error navigating to post {post_url}: {e}")
            self.capture_debug_info("navigate_post_error")
            raise

    def load_more_comments(self, max_clicks=5):
        """Clicks 'Load more comments' button to reveal additional comments."""
        attempts = 0
        while attempts < max_clicks:
            try:
                load_more = self.page.locator("button:has-text('Load more comments')")
                if load_more.is_visible():
                    load_more.click()
                    log.info(f"Clicked 'Load more comments' button {attempts + 1} time(s).")
                    self.random_delay(2, 4)
                    attempts += 1
                else:
                    log.info("No more 'Load more comments' button found.")
                    break
            except PlaywrightTimeoutError:
                log.info("No more 'Load more comments' button found.")
                break
            except Exception as e:
                log.warning(f"Error loading more comments: {e}")
                break

    def scrape_comments(self, max_comments=10):
        """Scrapes comments from an Instagram post."""
        user_names = []
        user_comments = []

        try:
            # Load more comments if available
            self.load_more_comments(max_clicks=10)

            # Wait for comments section to load
            self.page.wait_for_selector(INSTAGRAM_SELECTORS["comments_section"], timeout=10000)

            # Parse the page content
            content = self.page.content()
            soup = BeautifulSoup(content, 'lxml')

            # Find all comment elements
            comment_items = soup.select(INSTAGRAM_SELECTORS["comment_items"])
            for comment in comment_items[:max_comments]:
                try:
                    username = comment.select_one(INSTAGRAM_SELECTORS["username_element"]).get_text(strip=True)
                    comment_text = comment.select_one(INSTAGRAM_SELECTORS["comment_text"]).get_text(strip=True)
                    comment_text = emoji.demojize(comment_text)

                    user_names.append(username)
                    user_comments.append(comment_text)
                except AttributeError:
                    continue

            log.info(f"Scraped {len(user_names)} comments")
            return user_names, user_comments

        except Exception as e:
            log.error(f"Failed to scrape comments: {e}")
            self.capture_debug_info("scrape_comments_error")
            return [], []

    def export_to_csv(self, user_names, user_comments, filename='comments.csv'):
        """Exports scraped comments to a CSV file."""
        try:
            df = pd.DataFrame({
                'Username': user_names,
                'Comment': user_comments
            })
            csv_path = os.path.join("static", filename)
            df.to_csv(csv_path, index=False)
            log.info(f"Exported comments to {csv_path}")
            return csv_path
        except Exception as e:
            log.error(f"Failed to export to CSV: {e}")
            self.capture_debug_info("export_csv_error")
            return None

    def perform_sentiment_analysis(self, user_comments):
        """Performs sentiment analysis on scraped comments."""
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
            self.generate_sentiment_plots(df, positive_word_counts, negative_word_counts)

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
            self.capture_debug_info("sentiment_analysis_error")
            return None

    def generate_sentiment_plots(self, df, positive_word_counts, negative_word_counts):
        """Generates sentiment analysis visualizations."""
        try:
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

            log.info("Generated sentiment analysis plots.")

        except Exception as e:
            log.error(f"Failed to generate sentiment plots: {e}")
            self.capture_debug_info("generate_plots_error")

    def close(self):
        """Closes Playwright and associated resources."""
        try:
            if self.page:
                self.page.close()
            if self.context:
                self.context.close()
            if self.browser:
                self.browser.close()
            if self.playwright:
                self.playwright.stop()
            log.info("Playwright closed successfully.")
        except Exception as e:
            log.error(f"Error closing Playwright: {e}")

# Flask Routes
@app.route("/", methods=["GET", "POST"])
def index():
    """Renders the home page with the input form and handles form submission."""
    if request.method == "POST":
        # Get form data
        username = request.form.get('username')
        password = request.form.get('password')
        post_url = request.form.get('post_url')
        load_more_clicks = int(request.form.get('load_more_clicks', 5))
        max_comments = int(request.form.get('max_comments', 10))

        # Input validation
        if not username or not password or not post_url:
            flash("All fields are required.", "danger")
            return redirect(url_for('index'))

        # Initialize InstagramBot
        bot = InstagramBot(account={
            'username': username,
            'password': password
        })

        try:
            # Setup Playwright
            bot.setup_playwright()

            # Log in to Instagram
            bot.login_instagram()

            # Navigate to the specific post
            bot.navigate_to_post(post_url)

            # Load more comments as specified
            for _ in range(load_more_clicks):
                try:
                    load_more = bot.page.locator("button:has-text('Load more comments')")
                    if load_more.is_visible():
                        load_more.click()
                        log.info("Clicked 'Load more comments' button.")
                        bot.random_delay(2, 4)
                    else:
                        log.info("No more 'Load more comments' button found.")
                        break
                except PlaywrightTimeoutError:
                    log.info("No more 'Load more comments' button found.")
                    break
                except Exception as e:
                    log.warning(f"Error clicking 'Load more comments': {e}")
                    break

            # Scrape comments
            user_names, user_comments = bot.scrape_comments(max_comments=max_comments)

            if not user_names or not user_comments:
                flash("No comments scraped.", "warning")
                return redirect(url_for('index'))

            # Export to CSV
            csv_path = bot.export_to_csv(user_names, user_comments, filename='comments.csv')

            # Perform sentiment analysis
            sentiment_results = bot.perform_sentiment_analysis(user_comments)

            if not sentiment_results:
                flash("Error during sentiment analysis.", "danger")
                return redirect(url_for('index'))

            # Close Playwright
            bot.close()

            # Render results
            return render_template('results.html',
                                   sentiment_plot=sentiment_results["sentiment_plot"],
                                   positive_words_plot=sentiment_results["positive_words_plot"],
                                   negative_words_plot=sentiment_results["negative_words_plot"],
                                   sentiment_distribution=sentiment_results["sentiment_distribution"],
                                   )

        except Exception as e:
            log.error(f"Scraping failed: {e}")
            flash(f"An error occurred during scraping: {e}", "danger")
            bot.close()
            return redirect(url_for('index'))

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
