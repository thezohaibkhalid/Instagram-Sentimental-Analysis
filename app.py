import os
import sys
import time
import csv
import emoji
import re
import nltk
import pandas as pd
from flask import Flask, render_template, request, send_file, redirect, url_for, flash
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager  # To handle chromedriver automatically
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    ElementClickInterceptedException,
    StaleElementReferenceException,
)
from textblob import TextBlob
from matplotlib import pyplot as plt
from nltk.tokenize import word_tokenize
import random
import io
from werkzeug.utils import secure_filename

# Initialize Flask app
app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Replace with a secure key in production

# Ensure NLTK data is downloaded
nltk.download('punkt')

def random_delay(min_seconds=2, max_seconds=5):
    """Introduces a random delay to mimic human behavior."""
    delay = random.uniform(min_seconds, max_seconds)
    time.sleep(delay)

def login_instagram(driver, username, password):
    """Logs into Instagram."""
    try:
        driver.get('https://www.instagram.com/accounts/login/')
        # Wait until username and password fields are present
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.NAME, "username"))
        )
        random_delay(2, 4)  # Additional wait to ensure page is loaded

        # Enter username
        username_field = driver.find_element(By.NAME, "username")
        username_field.send_keys(username)

        # Enter password
        password_field = driver.find_element(By.NAME, "password")
        password_field.send_keys(password)
        password_field.send_keys(Keys.RETURN)

        # Wait for main page to load or for any popups
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "nav"))
        )
        print("Logged in successfully.")

        # Handle "Save Your Login Info?" popup
        try:
            not_now_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Not Now')]"))
            )
            not_now_button.click()
            print("Clicked 'Not Now' on save login info.")
            random_delay(2, 4)
        except TimeoutException:
            print("'Save Your Login Info?' popup did not appear.")

        # Handle "Turn on Notifications" popup
        try:
            not_now_notifications = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Not Now')]"))
            )
            not_now_notifications.click()
            print("Clicked 'Not Now' on turn on notifications.")
            random_delay(2, 4)
        except TimeoutException:
            print("'Turn on Notifications' popup did not appear.")

    except TimeoutException:
        print("Timeout while trying to log in.")
        driver.save_screenshot("login_timeout.png")
        with open("login_page.html", "w", encoding="utf-8") as f:
            f.write(driver.page_source)
        driver.quit()
        raise Exception("Timeout while trying to log in.")
    except Exception as e:
        print(f"Error during login: {e}")
        driver.save_screenshot("login_error.png")
        driver.quit()
        raise e

def navigate_to_profile(driver, profile_url):
    """Navigates to the specified Instagram profile."""
    try:
        print(f"Navigating to the profile: {profile_url}")
        driver.get(profile_url)
        random_delay(3, 6)  # Wait for page to load

        # Scroll down to load posts
        for _ in range(3):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            random_delay(2, 4)

        # Wait for posts to load using reliable selector
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "article"))
        )
        print("Profile page loaded successfully.")

        # Optional: Log page title and URL
        print(f"Page Title: {driver.title}")
        print(f"Current URL: {driver.current_url}")
    except TimeoutException:
        print("Timeout: Unable to load the profile page.")
        driver.save_screenshot("profile_timeout.png")
        with open("profile_page.html", "w", encoding="utf-8") as f:
            f.write(driver.page_source)
        driver.quit()
        raise Exception("Timeout: Unable to load the profile page.")
    except Exception as e:
        print(f"Error navigating to profile: {e}")
        driver.save_screenshot("profile_error.png")
        driver.quit()
        raise e

def get_posts(driver, count=10):
    """Retrieves the first 'count' post elements from the profile."""
    try:
        # Use a reliable selector to find post links
        posts = WebDriverWait(driver, 10).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, "article a[href*='/p/']"))
        )
        print(f"Found {len(posts)} posts.")
        return posts[:count]
    except TimeoutException:
        print("Timeout: Unable to find any posts with the selector: article a[href*='/p/']")
        driver.save_screenshot("no_posts_found.png")
        with open("no_posts_found.html", "w", encoding="utf-8") as f:
            f.write(driver.page_source)
        return []
    except Exception as e:
        print(f"Error retrieving posts: {e}")
        driver.save_screenshot("posts_error.png")
        return []

def load_more_comments(driver, max_loads=10):
    """Clicks the 'Load more comments' button up to 'max_loads' times."""
    for i in range(max_loads):
        try:
            load_more_button = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Load more comments')]"))
            )
            load_more_button.click()
            print(f"Clicked 'Load more comments' button {i+1} time(s).")
            random_delay(2, 4)  # Wait for comments to load
        except TimeoutException:
            print("No more 'Load more comments' button found.")
            break
        except Exception as e:
            print(f"Error clicking 'Load more comments' button: {e}")
            break

def scrape_comments(driver, max_comments=10):
    """Scrapes up to 'max_comments' comments from the currently opened Instagram post."""
    user_names = []
    user_comments = []
    try:
        # Wait until comments are loaded
        comments_ul = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, "//ul[contains(@class, 'Mr508')]"))
        )

        # Load more comments if available
        load_more_comments(driver, max_loads=10)

        # Find comment elements
        comments = comments_ul.find_elements(By.XPATH, ".//li")
        print(f"Found {len(comments)} comments in the post.")

        for comment in comments[:max_comments]:
            try:
                username = comment.find_element(By.XPATH, ".//a").text
                content = comment.find_element(By.XPATH, ".//span").text
                content = emoji.demojize(content)
                user_names.append(username)
                user_comments.append(content)
            except NoSuchElementException:
                continue
            except Exception as e:
                print(f"Error scraping a comment: {e}")
                continue

        print(f"Scraped {len(user_names)} comments.")
    except TimeoutException:
        print("Timeout: Unable to load comments for this post.")
        driver.save_screenshot("comments_timeout.png")
    except Exception as e:
        print(f"Error during scraping comments: {e}")
        driver.save_screenshot("scrape_comments_error.png")

    return user_names, user_comments

def scrape_comments_from_posts(driver, posts, max_comments_per_post=10):
    """Scrapes comments from a list of post elements."""
    all_user_names = []
    all_user_comments = []
    for index, post in enumerate(posts, start=1):
        try:
            print(f"Processing post {index}...")
            post.click()
            random_delay(3, 6)  # Wait for modal to open

            # Scrape comments
            user_names, user_comments = scrape_comments(driver, max_comments=max_post_comments)
            all_user_names.extend(user_names)
            all_user_comments.extend(user_comments)

            # Close the modal
            close_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, "//div[@role='dialog']//button[contains(@class, 'wpO6b')]"))
            )
            close_button.click()
            print(f"Closed post {index} modal.")
            random_delay(2, 4)
        except Exception as e:
            print(f"Error processing post {index}: {e}")
            driver.save_screenshot(f"post_{index}_error.png")
            with open(f"post_{index}_error.html", "w", encoding="utf-8") as f:
                f.write(driver.page_source)
            continue

    return all_user_names, all_user_comments

def perform_sentiment_analysis(user_names, user_comments):
    """Performs sentiment analysis on the scraped comments."""
    try:
        data = {"username": user_names, "comment": user_comments}
        df = pd.DataFrame(data)

        # Calculate sentiment polarity and subjectivity
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

        # Plot sentiment analysis
        sentiment_counts = df["sentiment"].value_counts()
        plt.figure(figsize=(8, 6))
        sentiment_counts.plot(kind="bar", color=["red", "gray", "green"])
        plt.title("Sentiment Analysis of Comments")
        plt.xlabel("Sentiment")
        plt.ylabel("Count")
        plt.xticks(rotation=0)
        plt.tight_layout()
        plt.savefig("static/sentiment_plot.png")
        plt.close()

        # Plot positive words
        if not positive_word_counts.empty:
            plt.figure(figsize=(10, 6))
            positive_word_counts.plot(kind="bar", color="green")
            plt.title("Top Positive Words")
            plt.xlabel("Words")
            plt.ylabel("Frequency")
            plt.xticks(rotation=45)
            plt.tight_layout()
            plt.savefig("static/positive_words.png")
            plt.close()
        else:
            print("No positive words found.")

        # Plot negative words
        if not negative_word_counts.empty:
            plt.figure(figsize=(10, 6))
            negative_word_counts.plot(kind="bar", color="red")
            plt.title("Top Negative Words")
            plt.xlabel("Words")
            plt.ylabel("Frequency")
            plt.xticks(rotation=45)
            plt.tight_layout()
            plt.savefig("static/negative_words.png")
            plt.close()
        else:
            print("No negative words found.")

        # Save to CSV
        csv_buffer = io.StringIO()
        df.to_csv(csv_buffer, index=False)
        csv_buffer.seek(0)

        # Prepare sentiment distribution data
        sentiment_distribution = sentiment_counts.to_dict()
        top_positive = positive_word_counts.to_dict()
        top_negative = negative_word_counts.to_dict()

        return {
            "csv": csv_buffer,
            "sentiment_plot": url_for('static', filename='sentiment_plot.png'),
            "positive_words_plot": url_for('static', filename='positive_words.png') if not positive_word_counts.empty else None,
            "negative_words_plot": url_for('static', filename='negative_words.png') if not negative_word_counts.empty else None,
            "sentiment_distribution": sentiment_distribution,
            "top_positive_words": top_positive,
            "top_negative_words": top_negative
        }

    except Exception as e:
        print(f"Error during sentiment analysis: {e}")
        return None

    return None

def save_to_csv(user_names, user_comments, filename="comments.csv"):
    """Saves scraped comments to a CSV file."""
    try:
        data = {"username": user_names, "comment": user_comments}
        df = pd.DataFrame(data)
        df.to_csv(filename, index=False)
        print(f"Scraped comments saved to {filename}.")
    except Exception as e:
        print(f"Error saving to CSV: {e}")

@app.route('/', methods=['GET'])
def index():
    """Renders the home page with the input form."""
    return render_template('index.html')

@app.route('/scrape', methods=['POST'])
def scrape():
    """Handles the form submission, performs scraping, and returns the results."""
    # Get form data
    username = request.form.get('username')
    password = request.form.get('password')
    target_profile = request.form.get('target_profile')
    posts_count = int(request.form.get('posts_count', 10))
    comments_count = int(request.form.get('comments_count', 10))

    if not username or not password or not target_profile:
        flash("All fields are required.", "danger")
        return redirect(url_for('index'))

    # Initialize Chrome Options
    options = Options()
    # Disable headless mode for debugging; uncomment the next line to enable headless mode
    # options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-gpu')
    options.add_argument('--start-maximized')
    options.add_argument('--disable-infobars')
    options.add_argument('--disable-extensions')

    # Optional: Set user-agent to mimic a real browser
    user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko)" \
                 " Chrome/85.0.4183.102 Safari/537.36"
    options.add_argument(f'user-agent={user_agent}')

    # Initialize WebDriver using webdriver-manager
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)

    try:
        # Step 1: Log in to Instagram
        login_instagram(driver, username, password)
        random_delay(3, 6)  # Wait after login

        # Step 2: Navigate to the target profile
        target_profile_url = f"https://www.instagram.com/{target_profile}/"
        navigate_to_profile(driver, target_profile_url)
        random_delay(3, 6)  # Wait after navigation

        # Step 3: Get posts
        posts = get_posts(driver, count=posts_count)
        if not posts:
            flash("No posts found to scrape.", "warning")
            return redirect(url_for('index'))

        # Step 4: Scrape comments from posts
        global max_post_comments
        max_post_comments = comments_count  # Set globally for scrape_comments_from_posts
        all_user_names, all_user_comments = scrape_comments_from_posts(driver, posts, max_comments_per_post=comments_count)
        if not all_user_names or not all_user_comments:
            flash("No comments scraped.", "warning")
            return redirect(url_for('index'))

        # Step 5 & 6: Perform sentiment analysis and generate results
        sentiment_results = perform_sentiment_analysis(all_user_names, all_user_comments)
        if sentiment_results is None:
            flash("Error during sentiment analysis.", "danger")
            return redirect(url_for('index'))

        # Prepare CSV file
        csv_data = sentiment_results["csv"].getvalue()
        csv_file = io.BytesIO()
        csv_file.write(csv_data.encode('utf-8'))
        csv_file.seek(0)

        # Render results on a new page
        return render_template('results.html',
                               sentiment_plot=sentiment_results["sentiment_plot"],
                               positive_words_plot=sentiment_results["positive_words_plot"],
                               negative_words_plot=sentiment_results["negative_words_plot"],
                               sentiment_distribution=sentiment_results["sentiment_distribution"],
                               top_positive_words=sentiment_results["top_positive_words"],
                               top_negative_words=sentiment_results["top_negative_words"],
                               )

    except Exception as e:
        print(f"Error in scraping process: {e}")
        flash(f"An error occurred: {e}", "danger")
        return redirect(url_for('index'))
    finally:
        driver.quit()

@app.route('/download_csv')
def download_csv():
    """Provides the CSV file for download."""
    try:
        return send_file('comments_with_sentiment.csv',
                         mimetype='text/csv',
                         attachment_filename='comments_with_sentiment.csv',
                         as_attachment=True)
    except Exception as e:
        flash(f"Error downloading CSV: {e}", "danger")
        return redirect(url_for('index'))

if __name__ == '__main__':
    # Run the Flask app
    app.run(debug=True)
