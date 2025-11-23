import time
import os
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
from dateparser import parse as dateparse

def run_moodle_sync(app, db, Task, Settings):
    
    # --- PERSISTENT PROFILE SETUP ---
    # This creates a folder named 'chrome_data' in your project folder.
    # Chrome will save login sessions here.
    current_dir = os.getcwd()
    profile_dir = os.path.join(current_dir, "chrome_data")
    
    options = webdriver.ChromeOptions()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument(f"user-data-dir={profile_dir}") 
    
    driver = webdriver.Chrome(options=options)
    new_count = 0

    try:
        with app.app_context():
            settings = Settings.query.first()
            moodle_url = settings.moodle_url or "https://moodle.iitb.ac.in"

            print(f"Navigating to {moodle_url}...")
            driver.get(moodle_url)

            # Check if already logged in (Persistent Session)
            if "/my/" in driver.current_url or "Dashboard" in driver.title:
                print("Session found! Skipping login.")
            else:
                print("--- PLEASE LOG IN (Session saved for next time) ---")
                WebDriverWait(driver, 300).until(
                    lambda d: "/my/" in d.current_url or "Dashboard" in d.title
                )
            
            # Give it a moment to settle
            time.sleep(2)
            
            driver.get(f"{moodle_url}/my/")
            time.sleep(2) 

            soup = BeautifulSoup(driver.page_source, "html.parser")
            activity_items = soup.select(".event-list-item, .timeline-event-list-item, .activity-item, .list-group-item")
            
            for item in activity_items:
                title_el = item.select_one("h6, h5, .event-name, .text-truncate")
                date_el = item.select_one("time, .date")
                link_el = item.select_one("a.list-group-item-action, a")

                if title_el and date_el:
                    title = title_el.get_text(strip=True)
                    date_str = date_el.get_text(strip=True)
                    link = link_el['href'] if link_el else ""
                    ext_id = link.split("id=")[-1] if "id=" in link else link

                    if "id=" not in link: continue
                    deadline = dateparse(date_str)
                    if not deadline: continue

                    existing = Task.query.filter_by(external_id=str(ext_id)).first()
                    
                    if not existing:
                        new_task = Task(
                            title=title,
                            task_type="assignment",
                            deadline=deadline,
                            estimated_hours=2.0, 
                            priority=2,
                            source='moodle',
                            external_id=str(ext_id)
                        )
                        db.session.add(new_task)
                        new_count += 1
                    else:
                        if existing.deadline != deadline:
                            existing.deadline = deadline
            
            db.session.commit()
            
    except Exception as e:
        print(f"Sync Error: {e}")
        return f"Error: {str(e)}"
    finally:
        try:
            driver.quit()
        except:
            pass
    
    return f"Sync Complete. {new_count} new tasks added."