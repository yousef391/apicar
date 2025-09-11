import os
import re
import time
import pandas as pd
from typing import Optional
import sys, asyncio

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# --- Gemini (Google AI) ---
import google.generativeai as genai

# --- Playwright ---
from playwright.sync_api import sync_playwright

# Fix for Playwright subprocess issue on Windows
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

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
        
        return int(re.search(r"\d+", result).group())
    except Exception:
        return None


#############################################
# Playwright Scraper
#############################################
def get_cars(minprice: int, maxprice: int, start_page: int = 1, pages: int = 5):
    """Scrape Ouedkniss automobiles with Playwright. Returns dict of lists."""
    data = {"name": [], "price": [], "location": [], "date": [], "url": [], "image": []}

    url = (
        f"https://www.ouedkniss.com/automobiles_vehicules/{start_page}?"
        f"priceUnit=MILLION&priceRangeMin={minprice}&priceRangeMax={maxprice}"
    )
    print(f"Fetching URL: {url}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()

        # safer navigation
        page.goto(url, wait_until="domcontentloaded", timeout=60000)

        # wait loader
        try:
            page.wait_for_selector("#loader", state="detached", timeout=20000)
        except:
            print("⚠️ Loader not found, continuing...")

        # wait for car cards
        page.wait_for_selector(
            "a.o-announ-card-content, a.v-card.o-announ-card-content", timeout=60000
        )

        for p_i in range(pages):
            print(f"Scraping page {p_i+1}...")

            # scroll for lazy load
            last_height = 0
            for _ in range(20):
                page.evaluate("window.scrollBy(0, 400)")
                time.sleep(0.5)
                new_height = page.evaluate("document.body.scrollHeight")
                if new_height == last_height:
                    break
                last_height = new_height

            # extract car cards
            cars = page.query_selector_all(
                "a.o-announ-card-content, a.v-card.o-announ-card-content"
            )
            print(f"Found {len(cars)} cars on page {p_i+1}")

            for car in cars:
                name = car.query_selector("h3.o-announ-card-title")
                name = name.inner_text().strip() if name else None

                try:
                    price_element = car.query_selector("div.mr-1")
                    price_txt = price_element.inner_text().strip() if price_element else None
                except:
                    price_txt = None

                location = car.query_selector("span.o-announ-card-city")
                location = location.inner_text().strip() if location else None

                date_txt = car.query_selector("span.o-announ-card-date")
                date_txt = date_txt.inner_text().strip() if date_txt else None

                url = car.get_attribute("href")
                image = car.query_selector("source[type='image/webp']")
                image = image.get_attribute("srcset") if image else None

                # clean price
                price_num = None
                if price_txt:
                    digits = re.findall(r"\d+", price_txt)
                    if digits:
                        price_num = int(digits[0])

                if price_num and price_num not in [123, 111, 1]:
                    data["name"].append(name)
                    data["price"].append(price_num)
                    data["location"].append(location)
                    data["date"].append(date_txt)
                    data["url"].append(url)
                    data["image"].append(image)

            # next page
            if p_i < pages - 1:
                next_btn = page.query_selector("button[aria-label='Page suivante']")
                if next_btn and next_btn.is_enabled():
                    next_btn.click()
                    try:
                        page.wait_for_selector("#loader", state="detached", timeout=10000)
                    except:
                        page.wait_for_timeout(2000)
                else:
                    print("No more pages.")
                    break

        browser.close()

    return data

#############################################
# FastAPI App
#############################################
app = FastAPI(
    title="Car Scraper API",
    version="1.0",
    description="Scrapes Ouedkniss cars and extracts prices with Gemini AI",
)

origins = [
    "http://localhost:2000",
    "http://204.12.218.86:2000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins= ["*"],  # or ["*"] to allow all (less secure)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
    print('////////////////////')
    print("Search request:", req.dict())
    message = req.message
    margin = req.margin
    pages = req.pages or 5
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
    print(minprice)
    print('***********')

    results = get_cars(minprice=minprice, maxprice=maxprice, start_page=start_page, pages=pages)

    # Ensure all arrays exist and have the same length
    car_count = len(results["name"])
    print(f"Found {car_count} cars")
    print(f"Results structure: {list(results.keys())}")
    for key in results.keys():
        print(f"  {key}: {len(results[key])} items")
    
    # Make sure all arrays have the same length
    for key in ["name", "price", "location", "date", "url", "image"]:
        if len(results[key]) != car_count:
            # Pad with None values if needed
            while len(results[key]) < car_count:
                results[key].append(None)

    return {
        "query": {
            "message": message,
            "min": minprice,
            "max": maxprice,
            "pages": pages
        },
        "count": car_count,
        "results": results
    }
