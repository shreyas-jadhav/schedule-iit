import time
import os
import re
from datetime import datetime, timedelta, date
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup

def get_driver():
    current_dir = os.getcwd()
    profile_dir = os.path.join(current_dir, "chrome_data")
    
    options = webdriver.ChromeOptions()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument(f"user-data-dir={profile_dir}") 
    
    return webdriver.Chrome(options=options)

def run_moodle_sync(app, db, Task, Settings):
   
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

           
            if "/my/" in driver.current_url or "Dashboard" in driver.title:
                print("Session found! Skipping login.")
            else:
                print("--- PLEASE LOG IN ---")
                WebDriverWait(driver, 300).until(
                    lambda d: "/my/" in d.current_url or "Dashboard" in d.title
                )
            
           
            courses_url = f"{moodle_url}/my/courses.php"
            print(f"Navigating to course list: {courses_url}")
            driver.get(courses_url)
            
           
            time.sleep(3)
           
            course_links = []
   
            elements = driver.find_elements(By.XPATH, "//a[contains(., 'View Course')] | //a[contains(@class, 'course-link')]")
            
            seen_urls = set()
            for elem in elements:
                url = elem.get_attribute('href')
                if url and "course/view.php" in url and url not in seen_urls:
                    course_links.append(url)
                    seen_urls.add(url)
            
            print(f"Found {len(course_links)} courses to scan.")

           
            for link in course_links:
                print(f"Scraping course: {link}")
                driver.get(link)
                
               
                try:
                    WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.CLASS_NAME, "course-content"))
                    )
                except:
                    print("  > Timeout waiting for course content.")
                    continue

               
                soup = BeautifulSoup(driver.page_source, "html.parser")
                
               
                activities = soup.select(".activity.activity-wrapper")
                
                for activity in activities:
                    try:
                       
                        date_container = activity.select_one(".activity-dates")
                        if not date_container:
                            continue
                        
                       
                        due_div = None
                        for div in date_container.find_all("div"):
                            if "Due:" in div.get_text():
                                due_div = div
                                break
                        
                        if not due_div:
                            continue
                            
                       
                       
                        full_text = due_div.get_text(strip=True)
                        date_str = full_text.replace("Due:", "").strip()
                        
                       
                       
                        try:
                            deadline = datetime.strptime(date_str, "%A, %d %B %Y, %I:%M %p")
                        except ValueError:
                           
                            print(f"  > Date format error: {date_str}")
                            continue

                       
                       
                        name_tag = activity.select_one(".activityname a")
                        if not name_tag:
                            continue
                            
                        title = name_tag.get_text(strip=True).split("\n")[0]
                        act_link = name_tag.get('href', '')
                        
                       
                        if "id=" in act_link:
                            ext_id = act_link.split("id=")[-1]
                        else:
                            continue

                       
                        task_type = "assignment"
                        classes = activity.get("class", [])
                        if "modtype_quiz" in classes:
                            task_type = "quiz"
                        elif "modtype_forum" in classes:
                            task_type = "forum"

                       
                        existing = Task.query.filter_by(external_id=str(ext_id)).first()
                        
                        if not existing:
                            new_task = Task(
                                title=title,
                                task_type=task_type,
                                deadline=deadline,
                                estimated_hours=2.0, 
                                priority=2,
                                source='moodle',
                                external_id=str(ext_id),
                                start_time=None,
                            )
                            db.session.add(new_task)
                            new_count += 1
                            print(f"  > Added: {title} (Due: {deadline})")
                        else:
                            if existing.deadline != deadline:
                                existing.deadline = deadline
                                print(f"  > Updated: {title}")
                                
                    except Exception as inner_e:
                        print(f"  > Error parsing activity: {inner_e}")
                        continue

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


