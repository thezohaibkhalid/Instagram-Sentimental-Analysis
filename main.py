from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
import time
import csv
import emoji
import pandas as pd
from textblob import TextBlob
from matplotlib import pyplot as plt

# Configure Chrome Options
options = Options()
options.add_argument('--no-sandbox')
options.add_argument('--disable-dev-shm-usage')
options.add_argument('--disable-gpu')
options.add_argument('--start-maximized')
options.add_argument('--disable-infobars')
options.add_argument('--disable-extensions')

# Set up the Chrome driver
service = Service(executable_path="E:\\Part time languages\\Esha Project\\chromedriver.exe")
driver = webdriver.Chrome(service=service, options=options)

def login_instagram(username, password):
    """Logs into Instagram and handles CAPTCHA if detected."""
    try:
        driver.get('https://www.instagram.com/accounts/login/')
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.NAME, "username"))
        )

        # Enter login credentials
        driver.find_element(By.NAME, "username").send_keys(username)
        driver.find_element(By.NAME, "password").send_keys(password)
        driver.find_element(By.NAME, "password").send_keys(Keys.RETURN)

        # Wait for the home page or CAPTCHA to load
        time.sleep(10)  # Allow time for manual CAPTCHA resolution if triggered
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div[role='main']"))
        )
        print("Logged in successfully.")
    except TimeoutException:
        print("Timeout: Unable to log in. If CAPTCHA is present, resolve it manually and rerun the script.")
        driver.quit()
        exit()
    except Exception as e:
        print(f"Error during login: {e}")
        driver.quit()
        exit()

def navigate_to_profile(profile_url):
    """Navigates to the specified Instagram profile."""
    try:
        print("Navigating to the profile...")
        driver.get(profile_url)  # Navigate to the profile URL directly
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "article"))  # Wait for posts to load
        )
        print("Profile page loaded successfully.")
    except TimeoutException:
        print("Timeout: Unable to load the profile page.")
        driver.quit()
        exit()
    except Exception as e:
        print(f"Error during navigation: {e}")
        driver.quit()
        exit()


def scrape_comments():
    """Scrapes comments from the posts on the profile."""
    try:
        posts = driver.find_elements(By.CSS_SELECTOR, "article a")[:10]
        comments_data = []

        for post in posts:
            try:
                post.click()
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "ul"))
                )  

                # Scrape comments
                comments = driver.find_elements(By.CSS_SELECTOR, "ul li")
                for comment in comments:
                    try:
                        username = comment.find_element(By.CSS_SELECTOR, "h3").text
                        text = comment.find_element(By.CSS_SELECTOR, "span").text
                        text = emoji.demojize(text)
                        comments_data.append({"username": username, "comment": text})
                    except Exception as e:
                        print(f"Error scraping a comment: {e}")

                driver.back()
                time.sleep(2)  # Wait for the profile page to load again
            except Exception as e:
                print(f"Error processing a post: {e}")

        print("Scraping complete.")
        return comments_data
    except Exception as e:
        print(f"Error during scraping: {e}")
        driver.quit()
        exit()

def save_to_csv(data, filename="comments.csv"):
    """Saves scraped data to a CSV file."""
    if not data:
        print("No data to save.")
        return

    keys = data[0].keys()
    with open(filename, "w", newline="", encoding="utf-8") as output_file:
        dict_writer = csv.DictWriter(output_file, fieldnames=keys)
        dict_writer.writeheader()
        dict_writer.writerows(data)
    print(f"Data saved to {filename}.")

def perform_sentiment_analysis(data):
    """Performs sentiment analysis on the scraped data."""
    df = pd.DataFrame(data)
    df["polarity"] = df["comment"].apply(lambda x: TextBlob(x).sentiment.polarity)
    df["sentiment"] = pd.cut(df["polarity"], [-1, -0.001, 0.001, 1], labels=["Negative", "Neutral", "Positive"])

    # Plot sentiment analysis
    sentiment_counts = df["sentiment"].value_counts()
    plt.figure(figsize=(8, 6))
    sentiment_counts.plot(kind="bar", color=["red", "gray", "green"])
    plt.title("Sentiment Analysis of Comments")
    plt.xlabel("Sentiment")
    plt.ylabel("Count")
    plt.savefig("sentiment_plot.png")
    plt.show()

    print("Positive Comments:", df[df["sentiment"] == "Positive"]["comment"].tolist())
    print("Neutral Comments:", df[df["sentiment"] == "Neutral"]["comment"].tolist())
    print("Negative Comments:", df[df["sentiment"] == "Negative"]["comment"].tolist())

# Workflow
try:
    # Step 1: Log in to Instagram
    login_instagram("techthron", "11aa22aa33aa")

    # Step 2: Navigate to Uni of Faisalabad profile
    navigate_to_profile("https://www.instagram.com/unioffaisalabad/")

    # Step 3: Scrape comments
    comments = scrape_comments()

    # Step 4: Save comments to CSV
    save_to_csv(comments)

    # Step 5: Perform sentiment analysis
    perform_sentiment_analysis(comments)
finally:
    driver.quit()