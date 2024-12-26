from flask import Flask, render_template, request, redirect, url_for, flash, send_file
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import json
import time
import os
import logging
import random

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("app.log"),
        logging.StreamHandler()
    ]
)

app = Flask(__name__)
app.secret_key = os.urandom(24)  # Replace with a secure secret key in production

# Function to introduce random delays
def random_delay(min_seconds=2, max_seconds=5):
    time.sleep(random.uniform(min_seconds, max_seconds))

# Configure Selenium WebDriver options
def get_webdriver():
    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option("useAutomationExtension", False)
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.6778.205 Safari/537.36")
    # Disable headless mode for debugging
    # chrome_options.add_argument("--headless")  
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    return driver

# Login to Instagram
def instagram_login(driver, username, password):
    try:
        driver.get("https://www.instagram.com/accounts/login/")
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.NAME, "username")))
        random_delay()
        driver.find_element(By.NAME, "username").send_keys(username)
        driver.find_element(By.NAME, "password").send_keys(password)
        driver.find_element(By.XPATH, "//button[@type='submit']").click()
        
        # Handle "Save Your Login Info?" popup
        WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Not Now')]")))
        driver.find_element(By.XPATH, "//button[contains(text(), 'Not Now')]").click()
        
        # Handle "Turn on Notifications" popup
        WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), 'Not Now')]")))
        driver.find_element(By.XPATH, "//button[contains(text(), 'Not Now')]").click()
        
        logging.info("Successfully logged into Instagram.")
    except Exception as e:
        logging.error(f"Error during Instagram login: {e}")
        driver.save_screenshot("login_error.png")
        raise e

# Scrape comments from a single post
def scrape_comments(driver, post_url, max_comments):
    driver.get(post_url)
    comments = []
    try:
        # Wait for the comments section to load
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "article")))
        random_delay()
        # Scroll to load comments
        while len(comments) < max_comments:
            comment_elements = driver.find_elements(By.XPATH, "//ul[contains(@class, 'Mr508')]//li")
            for comment in comment_elements:
                try:
                    username = comment.find_element(By.XPATH, ".//a[contains(@href, '/')]").text
                    comment_text = comment.find_element(By.XPATH, ".//span").text
                    if comment_text not in comments:
                        comments.append({"username": username, "comment": comment_text})
                        if len(comments) >= max_comments:
                            break
                except Exception as e:
                    logging.error(f"Error extracting comment: {e}")
                    continue

            # Attempt to click "Load more comments" if available
            try:
                load_more = driver.find_element(By.XPATH, "//button[contains(text(), 'Load more comments')]")
                driver.execute_script("arguments[0].click();", load_more)
                random_delay()
            except:
                break  # No more comments to load
    except Exception as e:
        logging.error(f"Error fetching comments from {post_url}: {e}")
        driver.save_screenshot("comments_error.png")
    return comments[:max_comments]

# Function to get post links
def get_post_links(driver, target_id, num_posts):
    driver.get(f"https://www.instagram.com/{target_id}/")
    WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "article")))
    random_delay()

    post_links = set()
    scrolls = 0
    max_scrolls = 10  # Prevent infinite scrolling

    while len(post_links) < num_posts and scrolls < max_scrolls:
        posts = driver.find_elements(By.XPATH, "//a[contains(@href, '/p/')]")
        for post in posts:
            href = post.get_attribute("href")
            if href not in post_links:
                post_links.add(href)
                logging.info(f"Found post: {href}")
                if len(post_links) >= num_posts:
                    break
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        random_delay(2, 4)
        scrolls += 1
        logging.info(f"Scroll attempt {scrolls}/{max_scrolls}")

    return list(post_links)[:num_posts]

# Scrape Instagram posts and their comments
def scrape_instagram_posts(username, password, target_id, num_posts, comments_per_post):
    driver = get_webdriver()
    try:
        instagram_login(driver, username, password)
        post_links = get_post_links(driver, target_id, num_posts)
        result_data = {}

        for index, link in enumerate(post_links):
            logging.info(f"Scraping Post {index + 1} of {num_posts}: {link}")
            comments = scrape_comments(driver, link, comments_per_post)
            result_data[link] = comments
            random_delay(2, 4)  # Pause between posts to mimic human behavior

        # Save results to JSON
        with open("results.json", "w", encoding='utf-8') as file:
            json.dump(result_data, file, indent=4, ensure_ascii=False)

        logging.info("Scraping completed successfully.")
        return result_data

    except Exception as e:
        logging.error(f"Error during scraping: {e}")
        return {}
    finally:
        driver.quit()

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        target_id = request.form.get("target_id", "").strip()
        num_posts = request.form.get("num_posts", "").strip()
        comments_per_post = request.form.get("comments_per_post", "").strip()

        # Validate form inputs
        if not username or not password:
            flash("Instagram username and password are required.", "error")
            return redirect(url_for("index"))
        if not target_id:
            flash("Target Instagram ID is required.", "error")
            return redirect(url_for("index"))
        try:
            num_posts = int(num_posts)
            comments_per_post = int(comments_per_post)
            if num_posts <= 0 or comments_per_post <= 0:
                raise ValueError
        except ValueError:
            flash("Number of posts and comments must be positive integers.", "error")
            return redirect(url_for("index"))

        # Perform scraping
        flash("Scraping started. This may take a while...", "info")
        results = scrape_instagram_posts(username, password, target_id, num_posts, comments_per_post)
        if results:
            flash("Scraping completed successfully!", "success")
        else:
            flash("An error occurred during scraping. Please check the logs.", "error")
        return redirect(url_for("results"))

    return render_template("index.html")

@app.route("/results", methods=["GET"])
def results():
    try:
        with open("results.json", "r", encoding='utf-8') as file:
            data = json.load(file)
    except FileNotFoundError:
        data = {}
    except json.JSONDecodeError:
        data = {}
    return render_template("results.html", results=data)

@app.route("/download", methods=["GET"])
def download_results():
    try:
        return send_file("results.json", as_attachment=True)
    except FileNotFoundError:
        flash("No results available to download.", "error")
        return redirect(url_for("results"))

if __name__ == "__main__":
    app.run(debug=True)
