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
    """Returns a driver with a persistent profile"""
    current_dir = os.getcwd()
    profile_dir = os.path.join(current_dir, "chrome_data")
    
    options = webdriver.ChromeOptions()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument(f"user-data-dir={profile_dir}") 
    
    return webdriver.Chrome(options=options)

def run_moodle_sync(app, db, Task, Settings):
    # --- PERSISTENT PROFILE SETUP ---
    current_dir = os.getcwd()
    profile_dir = os.path.join(current_dir, "chrome_data")
    
    options = webdriver.ChromeOptions()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    # options.add_argument("--headless") # Uncomment for headless mode
    options.add_argument(f"user-data-dir={profile_dir}") 
    
    driver = webdriver.Chrome(options=options)
    new_count = 0

    try:
        with app.app_context():
            settings = Settings.query.first()
            moodle_url = settings.moodle_url or "https://moodle.iitb.ac.in"

            print(f"Navigating to {moodle_url}...")
            driver.get(moodle_url)

            # 1. Login Check
            if "/my/" in driver.current_url or "Dashboard" in driver.title:
                print("Session found! Skipping login.")
            else:
                print("--- PLEASE LOG IN ---")
                WebDriverWait(driver, 300).until(
                    lambda d: "/my/" in d.current_url or "Dashboard" in d.title
                )
            
            # 2. Go to My Courses
            courses_url = f"{moodle_url}/my/courses.php"
            print(f"Navigating to course list: {courses_url}")
            driver.get(courses_url)
            
            # Wait for course cards to load
            time.sleep(3) # Simple wait; can be improved with explicit waits

            # 3. Collect Course URLs 
            # Strategy: Find all elements with text "View Course" (or course links) and get hrefs first.
            # This is more stable than clicking and going 'back'.
            course_links = []
            
            # Look for standard Moodle/RemUI course links or buttons containing "View Course"
            # Using XPath to find 'a' tags that contain "View Course" text or are standard course links
            elements = driver.find_elements(By.XPATH, "//a[contains(., 'View Course')] | //a[contains(@class, 'course-link')]")
            
            seen_urls = set()
            for elem in elements:
                url = elem.get_attribute('href')
                if url and "course/view.php" in url and url not in seen_urls:
                    course_links.append(url)
                    seen_urls.add(url)
            
            print(f"Found {len(course_links)} courses to scan.")

            # 4. Iterate over each course
            for link in course_links:
                print(f"Scraping course: {link}")
                driver.get(link)
                
                # Wait for activities to load
                try:
                    WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.CLASS_NAME, "course-content"))
                    )
                except:
                    print("  > Timeout waiting for course content.")
                    continue

                # Parse with BS4
                soup = BeautifulSoup(driver.page_source, "html.parser")
                
                # Find all activity wrappers
                activities = soup.select(".activity.activity-wrapper")
                
                for activity in activities:
                    try:
                        # Check for Dates
                        date_container = activity.select_one(".activity-dates")
                        if not date_container:
                            continue
                        
                        # Look for "Due:" text inside the date container
                        due_div = None
                        for div in date_container.find_all("div"):
                            if "Due:" in div.get_text():
                                due_div = div
                                break
                        
                        if not due_div:
                            continue # Skip if no due date
                            
                        # Extract Date String
                        # Format example: "Due: Sunday, 30 November 2025, 12:00 AM"
                        full_text = due_div.get_text(strip=True)
                        date_str = full_text.replace("Due:", "").strip()
                        
                        # Parse Date
                        # Adjust format based on Moodle's output (Day, d Month Y, I:M p)
                        try:
                            deadline = datetime.strptime(date_str, "%A, %d %B %Y, %I:%M %p")
                        except ValueError:
                            # Fallback if format differs slightly
                            print(f"  > Date format error: {date_str}")
                            continue

                        # Extract Title and Link
                        # Title is usually inside .activityname -> a
                        name_tag = activity.select_one(".activityname a")
                        if not name_tag:
                            continue
                            
                        title = name_tag.get_text(strip=True).split("\n")[0] # Remove "Assignment" suffix if present
                        act_link = name_tag.get('href', '')
                        
                        # Extract ID
                        if "id=" in act_link:
                            ext_id = act_link.split("id=")[-1]
                        else:
                            continue

                        # Determine Type (Assign, Quiz, etc.)
                        task_type = "assignment"
                        classes = activity.get("class", [])
                        if "modtype_quiz" in classes:
                            task_type = "quiz"
                        elif "modtype_forum" in classes:
                            task_type = "forum"

                        # Database Logic
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


def run_asc_sync(app, db, Task, Settings):
    # --- PERSISTENT PROFILE SETUP ---
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
            # 1. Check Credentials
            settings = Settings.query.first()
            asc_user = settings.asc_username
            asc_pass = settings.asc_password

            if not asc_user or not asc_pass:
                print("⚠️ ASC Credentials missing in Settings!")
                return "Error: Please save ASC Username and Password in Settings first."

            # 2. Navigate to ASC
            base_url = "https://asc.iitb.ac.in/acadmenu/index.jsp"
            print(f"Navigating to {base_url}...")
            driver.get(base_url)
            
            time.sleep(20)

            # 4. Navigate Sidebar & EXTRACT URL
            print("Navigating sidebar to find URL...")
            try:
                driver.switch_to.frame("leftFrame") 
            except:
                try:
                    driver.switch_to.frame(0) 
                except:
                    print("Warning: Could not switch to 'leftFrame'.")

            wait = WebDriverWait(driver, 10)
            timetable_url = None
            
            try:
                # 1. Expand "Academic"
                icon1 = wait.until(EC.element_to_be_clickable((By.ID, "ygtvt1")))
                icon1.click()
                time.sleep(1) 
                
                # 2. Expand "Timetable"
                icon2 = wait.until(EC.element_to_be_clickable((By.ID, "ygtvt22")))
                icon2.click()
                time.sleep(1) 
                
                # 3. EXTRACT URL instead of clicking
                print("Extracting TimeTable URL...")
                link = wait.until(EC.presence_of_element_located((By.PARTIAL_LINK_TEXT, "My Timetable")))
                
                timetable_url = link.get_attribute('href')
                print(f"Found Target URL: {timetable_url}")
                
            except Exception as e:
                print(f"❌ Sidebar Navigation Failed: {e}")
                return "Error: Could not find Timetable link."
            
            # 5. Direct Navigation to Timetable
            if timetable_url:
                driver.switch_to.default_content() # Reset context
                print(f"Navigating directly to: {timetable_url}")
                driver.get(timetable_url)
                time.sleep(3)

                # 6. Find Table (Handle if it opens in frame or direct)
                try:
                    # First try: Is the table directly here? (Standalone page)
                    wait.until(EC.presence_of_element_located((By.ID, "example22")))
                    print("Table found directly on page.")
                except:
                    # Second try: Did it load a frameset? Switch to rightFrame.
                    print("Table not found directly. Checking 'rightFrame'...")
                    try:
                        driver.switch_to.frame("rightFrame")
                        wait.until(EC.presence_of_element_located((By.ID, "example22")))
                        print("Table found in rightFrame.")
                    except:
                        return "Error: Could not find table 'example22' after navigation."

            # 7. Parse HTML with BeautifulSoup
            soup = BeautifulSoup(driver.page_source, "html.parser")
            table = soup.find("table", {"id": "example22"})
            
            if not table:
                return "Error: Timetable table not found in DOM."

            # --- PARSE HEADERS ---
            header_cells = table.find("thead").find_all("td")
            time_slots = {} 
            
            for idx, cell in enumerate(header_cells[1:], start=1):
                txt = cell.get_text(separator=" ").strip()
                match = re.search(r'(\d{1,2}(?::\d{2})?)\s+(\d{1,2}(?::\d{2})?)', txt)
                if match:
                    s_str, e_str = match.groups()
                    if ":" not in s_str: s_str += ":00"
                    if ":" not in e_str: e_str += ":00"
                    
                    try:
                        t_start = datetime.strptime(s_str, "%H:%M").time()
                        t_end = datetime.strptime(e_str, "%H:%M").time()
                        time_slots[idx] = (t_start, t_end)
                    except ValueError:
                        continue

            # --- PARSE ROWS ---
            schedule_map = {} 
            rows = table.find("tbody").find_all("tr")
            
            for r_idx, row in enumerate(rows):
                cells = row.find_all("td")
                if not cells: continue
                
                day_label = cells[0].get_text().lower()
                weekday = None
                if "mon" in day_label: weekday = 0
                elif "tue" in day_label: weekday = 1
                elif "wed" in day_label: weekday = 2
                elif "thu" in day_label: weekday = 3
                elif "fri" in day_label: weekday = 4
                
                if weekday is None: continue
                
                for c_idx, cell in enumerate(cells[1:], start=1):
                    if c_idx not in time_slots: continue
                    
                    course_bold = cell.find("b")
                    if course_bold:
                        course_code = course_bold.get_text(strip=True)
                        t_start, t_end = time_slots[c_idx]
                        
                        if weekday not in schedule_map:
                            schedule_map[weekday] = []
                        
                        schedule_map[weekday].append({
                            'code': course_code,
                            'start_t': t_start,
                            'end_t': t_end
                        })

            # --- GENERATE TASKS ---
            today = date.today()
            current_year = today.year
            
            if today.month > 6:
                sem_end = date(current_year, 12, 1)
            else:
                sem_end = date(current_year, 5, 1)
                
            print(f"Generating classes from {today} to {sem_end}")
            
            curr_date = today
            while curr_date <= sem_end:
                wkday = curr_date.weekday()
                if wkday in schedule_map:
                    classes_today = schedule_map[wkday]
                    for cls in classes_today:
                        start_dt = datetime.combine(curr_date, cls['start_t'])
                        end_dt = datetime.combine(curr_date, cls['end_t'])
                        
                        uid_str = f"{cls['code']}_{curr_date}_{cls['start_t'].strftime('%H%M')}"
                        ext_id = f"asc_{uid_str}".replace(" ", "")
                        
                        existing = Task.query.filter_by(external_id=ext_id).first()
                        
                        if not existing:
                            duration = (end_dt - start_dt).total_seconds() / 3600.0
                            new_task = Task(
                                title=f"{cls['code']} (Class)",
                                task_type="class",
                                start_time=start_dt,
                                end_time=end_dt,
                                estimated_hours=round(duration, 2),
                                priority=3, 
                                source='asc',
                                external_id=ext_id
                            )
                            db.session.add(new_task)
                            new_count += 1
                
                curr_date += timedelta(days=1)

            db.session.commit()
            print(f"ASC Sync Complete. {new_count} classes added.")

    except Exception as e:
        print(f"ASC Sync Error: {e}")
        return f"Error: {str(e)}"
    finally:
        try:
            driver.quit()
        except:
            pass

    return f"ASC Sync Complete. {new_count} fixed tasks added."