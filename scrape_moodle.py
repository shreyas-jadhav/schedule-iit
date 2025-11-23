from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import time
from db import insert_task
from dateparser import parse as dateparse   # Install: pip install dateparser
import os
import platform
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import shutil
import tempfile

def get_chrome_profile_path():
    home = os.path.expanduser("~")
    system = platform.system()

    if system == "Windows":
        return os.path.join(home, "AppData", "Local", "Google", "Chrome", "User Data")
    
    elif system == "Darwin":  # macOS
        return os.path.join(home, "Library", "Application Support", "Google", "Chrome")
    
    elif system == "Linux":
        # Try Google Chrome first
        chrome_path = os.path.join(home, ".config", "google-chrome")
        if os.path.exists(chrome_path):
            return chrome_path

        # Fallback to Chromium
        chromium_path = os.path.join(home, ".config", "chromium")
        if os.path.exists(chromium_path):
            return chromium_path

    return None

def start_browser():
    #chrome_profile = get_chrome_profile_path()
    #service = ChromeService(ChromeDriverManager().install())
    options = webdriver.ChromeOptions()
    
    options.add_argument("--enable-chrome-browser-cloud-management")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-infobars")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-blink-features=AutomationControlled")

    '''if chrome_profile:
        temp_profile = tempfile.mkdtemp()
        print("Copying profile →", temp_profile)

        # Copy only essential data
        for folder in ["Default", "Profile 1", "Profile 2"]:
            src = os.path.join(chrome_profile, folder)
            dst = os.path.join(temp_profile, folder)
            if os.path.exists(src):
                shutil.copytree(src, dst, ignore=shutil.ignore_patterns("*.log", "Web Data"))
                options.add_argument(f"--user-data-dir={temp_profile}")
                options.add_argument(f"--profile-directory={folder}")
                break
    else:
        print("Could not locate Chrome profile, continuing without using stored credentials.")

    #driver = webdriver.Chrome(service=service, options=options)'''
    driver = webdriver.Chrome(options=options)                
    return driver

def wait_for_login(driver, timeout_sec=300):
    driver.get("https://moodle.iitb.ac.in/login/index.php")
    print(" Browser opened. Please complete SSO login in the Chrome window.")
    start = time.time()
    while time.time() - start < timeout_sec:
        if "/my/" in driver.current_url:
            print(" Login successful!")
            return True
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "body"))
        )
    print(" Login timeout.")
    return False

def start_headless_browser(cookies):
    #service = ChromeService(ChromeDriverManager().install())
    #temp_profile = tempfile.mkdtemp()
    #print("Using temporary Chrome profile (headless):", temp_profile)
    options = webdriver.ChromeOptions()
    #options.add_argument(f"--user-data-dir={temp_profile}")
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--no-sandbox")
    options.add_argument("--enable-chrome-browser-cloud-management")
    options.add_argument("--disable-blink-features=AutomationControlled")

    headless_driver = webdriver.Chrome(options=options)

    # Add cookies into headless browser
    headless_driver.get("https://moodle.iitb.ac.in")
    for cookie in cookies:
        headless_driver.add_cookie(cookie)

    return headless_driver


def scrape_courses(driver):
    from db import clear_all_tasks
    clear_all_tasks()
    print("\n Fetching your enrolled courses...")
    driver.get("https://moodle.iitb.ac.in/my/")
    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "body"))
    )

    soup = BeautifulSoup(driver.page_source, "html.parser")

    # Find course links — adjust selector if needed
    course_links = soup.select("a[href*='/course/view.php']")

    courses = []
    seen = set()
    for link in course_links:
        name = link.get_text(strip=True)
        url = link.get("href")
        if url in seen:
            continue
        seen.add(url)

        '''parent = link.find_parent("div", class_="w-100")

        course_code = None
        if parent:
            # The course code sits in a <div> inside the muted div above the course name
            code_div = parent.select_one("div.text-muted div")
            if code_div:
                course_code = code_div.get_text(strip=True)'''

        courses.append((name, url))

    if not courses:
        print(" No courses found! Try scrolling down the dashboard manually and re-run.")
        return
    
    # Now scrape tasks for each course
    for course_name, course_url in courses:
        all_tasks = scrape_course_tasks(driver, course_name, course_url)

        for course_code, course_name, task_name, task_type, start_time, end_time in all_tasks:
            insert_task(
                course_code=course_code,
                course_name=course_name,
                task_name=task_name,
                task_type=task_type,
                start_time=start_time,
                end_time=end_time,
                estimated_hours=None,   # user will fill later
                priority="medium",      # default
                status="pending",
                source="moodle"
            )

def scrape_course_tasks(driver, course_name, course_url):
    print(f"\n Scraping tasks for: {course_name}")
    driver.get(course_url)
    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "body"))
    )

    soup = BeautifulSoup(driver.page_source, "html.parser")
    header = soup.select_one("h1.header-heading.coursepage")
    if header:
        text = header.get_text(strip=True)
        if "|" in text:
            parts = text.split("|", 1)  
            code_full = parts[0].strip()            
            course_code = code_full.split("-", 1)[0].strip()  
            course_name = parts[1].strip()
        else:
            course_name = text
            course_code = None
    activities = soup.select("li.activity")
    tasks = []

    for act in activities:
        # 1. Extract task link
        link = act.select_one("a[href*='mod/assign'], a[href*='mod/quiz']")
        if not link:
            continue

        task_name = link.get_text(strip=True)
        task_url = link["href"]

        # determine task type
        if "mod/assign" in task_url:
            task_type = "assignment"
        elif "mod/quiz" in task_url:
            task_type = "quiz"
        else:
            task_type = "misc"

        # 2. Extract dates inside activity-dates block
        dates_block = act.select_one(".activity-dates")
        start_time = None
        end_time = None

        if dates_block:
            date_lines = dates_block.find_all("div", recursive=False)
            for line in date_lines:
                strong = line.find("strong")
                if not strong:
                    continue

                label = strong.get_text(strip=True).rstrip(":")   # 'Opened', 'Due'
                date_text = strong.next_sibling.strip()           # actual date string

                if (
                    label.lower() == "opened"
                    or label.lower() == "opens"
                    or label.lower() == "open"
                    or label.lower() == "start date"
                    or label.lower() == "from"
                    or label.lower() == "available from"
                ):
                    start_time = dateparse(date_text)
                elif (
                    label.lower() == "due"
                    or label.lower() == "closes"
                    or label.lower() == "close"
                    or label.lower() == "end date"
                    or label.lower() == "to"
                    or label.lower() == "available until"
                    or label.lower() == "deadline"
                ):
                    end_time = dateparse(date_text)

        # Add to list
        tasks.append((course_code, course_name, task_name, task_type, start_time, end_time))
    tasks = [
        t for t in tasks
        if t[4] is not None and t[5] is not None
    ]
    return tasks

#unused function , will see later
def scrape_task_page(driver, course_name, task_name, task_type, task_url):
    driver.get(task_url)
    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "body"))
    )

    soup = BeautifulSoup(driver.page_source, "html.parser")

    # Extract deadlines
    due_element = soup.select_one(".duedate, .submissionduedate, .event-date, .activity-dates")

    due_date = None
    if due_element:
        due_date = dateparse(due_element.get_text(strip=True))

    # Extract start/available date
    start_element = soup.select_one(".availabilityinfo, .startdate, .submissionstart")
    start_date = None
    if start_element:
        start_date = dateparse(start_element.get_text(strip=True))

    # Fallback: if no start date, keep None
    # Insert into DB
    insert_task(
        course_code=course_name.split(":")[0] if ":" in course_name else None,
        course_name=course_name,
        task_name=task_name,
        task_type=task_type,
        start_time=start_date,
        end_time=due_date
    )

    print(f"Task inserted into DB: {task_name}")


def main():
    driver = start_browser()
    try:
        if wait_for_login(driver):
            print("Logged in.")
            #cookies = driver.get_cookies()
            #driver.quit()

            # start headless browser
            #driver = start_headless_browser(cookies)

            # scrape everything here
            scrape_courses(driver)
        else:
            print("Login not detected.")
    finally:
        input("Press Enter to close browser...")
        driver.quit()

if __name__ == "__main__":
    main()
