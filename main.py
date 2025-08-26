import os
import re
import time
import pandas as pd
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# --- Gemini (Google AI) ---
import google.generativeai as genai

# --- Selenium ---
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from dotenv import load_dotenv
load_dotenv()


#############################################
# Config
#############################################
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY not set in environment. Please add it to your .env file.")
genai.configure(api_key=GEMINI_API_KEY)


#############################################
# Extractors
#############################################
def extract_price_gemini(user_message: str):
    """Use Gemini to extract only the price number in millions from a Darija/Fr/Ar sentence.
    Returns int or None. Falls back to regex if API errors or empty.
    """
    prompt = (
        "u r text extractor\n"
        "Extract the car price in millions from this message (Darija/Arabic/French mix).\n"
        "If you can't find a number, reply with only: NULL.\n"
        "please extract exact price focus and the price ussally dont under 100 \n"
        f"Message: \"{user_message}\"\n"
        "Return only the number without text."
    )
    try: 
        print(prompt)
        model = genai.GenerativeModel("gemini-1.5-flash")
        response = model.generate_content(prompt)
        result = (response.text or "").strip()
        if result.upper() == "NULL":
            return None
        
        
        print(response.text)
        return int(re.search(r"\d+", result).group())
    except Exception:
        return None


def build_driver(headless: bool = True):
    options = webdriver.ChromeOptions()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    options.add_argument("--start-maximized")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
    )
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    driver.set_page_load_timeout(60)
    return driver


def scroll_to_bottom(driver, max_loops: int = 15, pause: float = 1.2):
    """Scroll until height stops changing or until max_loops reached."""
    last_height = driver.execute_script("return document.body.scrollHeight")
    loops = 0
    while loops < max_loops:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(pause)
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            break
        last_height = new_height
        loops += 1


def parse_price_to_int(price_text: str):
    if not price_text:
        return None
    m = re.search(r"\d+", price_text.replace(" ", ""))
    return int(m.group()) if m else None


from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import time
import pandas as pd


def get_cars(minprice: int, maxprice: int, start_page: int = 1, pages: int = 5):
    """Scrape Ouedkniss automobiles within [minprice, maxprice] (Millions). Returns DataFrame."""
    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")  
    options.add_argument("--start-maximized")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--window-size=1920,1080")

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

    data = {
        "name": [],
        "price": [],
        "location": [],
        "date": [],
        "url": [],
        "image": []
    }

    try:
        url = (
            f"https://www.ouedkniss.com/automobiles_vehicules/{start_page}?"
            f"priceUnit=MILLION&priceRangeMin={minprice}&priceRangeMax={maxprice}"
        )
        print(f"Fetching URL: {url}")
        driver.get(url)

        for p in range(pages):
            # wait for cards to appear
            WebDriverWait(driver, 20).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, "a.o-announ-card-content"))
            )

            # scroll until end
            last_height = driver.execute_script("return document.body.scrollHeight")
            while True:
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(2)
                new_height = driver.execute_script("return document.body.scrollHeight")
                if new_height == last_height:
                    break
                last_height = new_height

            # extract cars
            cars = driver.find_elements(By.CSS_SELECTOR, "a.o-announ-card-content")

            for car in cars:
                try:
                    name = car.find_element(By.CSS_SELECTOR, "h3.o-announ-card-title").text.strip()
                except:
                    name = None

                try:
                    price_txt = car.find_element(By.CSS_SELECTOR, "div.mr-1").text.strip()
                except:
                    price_txt = None

                try:
                    location = car.find_element(By.CSS_SELECTOR, "span.o-announ-card-city").text.strip()
                except:
                    location = None

                try:
                    date_txt = car.find_element(By.CSS_SELECTOR, "span.o-announ-card-date").text.strip()
                except:
                    date_txt = None

                try:
                    url = car.get_attribute("href")
                except:
                    url = None
                
                try:
                    # find the first <source> with type="image/webp"
                    image = car.find_element(By.CSS_SELECTOR, "source[type='image/webp']").get_attribute("srcset")
                    
                    
                except:
                    image = None

                # validate & clean price
                if price_txt:
                    price_num = price_txt.replace(" ", "")
                    if price_num.isdigit():
                        price_num = int(price_num)
                        if price_num not in (111, 123) and minprice <= price_num <= maxprice:
                            data["name"].append(name)
                            data["price"].append(price_num)
                            data["location"].append(location)
                            data["date"].append(date_txt)
                            data["url"].append(url)
                            data["image"].append(image)

            # next page
            if p < pages - 1:
                try:
                    next_btn = driver.find_element(By.CSS_SELECTOR, "button[aria-label='Page suivante']")
                    if next_btn.is_enabled():
                        driver.execute_script("arguments[0].click();", next_btn)
                        time.sleep(3)
                    else:
                        print("Next button disabled. Stopping.")
                        break
                except:
                    print("No more pages.")
                    break
    finally:
        driver.quit()

    df = pd.DataFrame(data)
    print(f"Scraped {len(df)} cars")
    return data

#############################################
# FastAPI App
#############################################
app = FastAPI(
    title="Car Scraper API",
    version="1.0",
    description="Scrapes Ouedkniss cars and extracts prices with Gemini AI",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files


# Serve React app
@app.get("/")
def serve_react_app():
    return FileResponse("website/build/index.html")

@app.get("/static/{path:path}")
def serve_static(path: str):
    return FileResponse(f"website/build/static/{path}")


class SearchRequest(BaseModel):
    message: Optional[str] = ""
    margin: Optional[int] = 20
    pages: Optional[int] = 5
    minprice: Optional[int] = None
    maxprice: Optional[int] = None
    start_page: Optional[int] = 1




@app.get("/health")
def health():
    return {"ok": True}


@app.post("/search")
def search(req: SearchRequest):
    message = req.message
    margin = req.margin
    pages = 5
    minprice = req.minprice
    maxprice = req.maxprice
    start_page = req.start_page

    if minprice is None or maxprice is None:
        price = extract_price_gemini(message)
        if price is None:
            raise HTTPException(status_code=400, detail="Ma fahmtch, 3tini prix en millions (ex: 300).")
        minprice = price - margin
        maxprice = price + margin

    minprice = int(minprice)
    maxprice = int(maxprice)

    results = get_cars(minprice=minprice, maxprice=maxprice, start_page=start_page, pages=pages)

    return {
        "query": {
            "message": message,
            "min": minprice,
            "max": maxprice,
            "pages": pages
        },
        "count": len(results),
        "results": results
    }
