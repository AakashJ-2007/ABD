import re
import time
import logging
from typing import List, Dict, Optional
import requests

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("scout_agent")

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": "https://www.linkedin.com/jobs/search",
}

REQUEST_TIMEOUT = 10


# --- 1. SAFE LINKEDIN SCOUT --------------------------------------------------
def fetch_linkedin_jobs(
    keywords: str = "Python Developer",
    location: str = "Remote",
    max_pages: int = 4,
    limit: int = 30,
    date_posted: str = "r2592000"
) -> List[Dict]:
    if BeautifulSoup is None:
        logger.error("LinkedIn scraper requires 'bs4'. Install via: pip install beautifulsoup4")
        return []

    base_url = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
    jobs = []
    seen_links = set()

    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)

    try:
        for page in range(max_pages):
            params = {
                "keywords": keywords,
                "location": location,
                "start": page * 25,
                "f_TPR": date_posted,
            }

            if "remote" in str(location).lower():
                params["f_WT"] = "2"

            try:
                resp = session.get(base_url, params=params, timeout=REQUEST_TIMEOUT)
                if resp.status_code != 200 or not resp.text.strip():
                    break
            except Exception as e:
                logger.warning("LinkedIn page request failed: %s", e)
                break

            soup = BeautifulSoup(resp.text, "html.parser")
            cards = soup.find_all("li")
            if not cards:
                cards = soup.find_all("div", class_=re.compile(r"(base-card|job-search-card|result-card)"))

            if not cards:
                break

            found_in_page = 0
            for card in cards:
                title_elem = (
                    card.find("h3", class_=re.compile(r"(base-search-card__title|job-search-card__title)"))
                    or card.find("h3")
                )
                
                company_elem = (
                    card.find("h4", class_=re.compile(r"(base-search-card__subtitle|job-search-card__subtitle)"))
                    or card.find("a", class_=re.compile(r"hidden-nested-link"))
                    or card.find("h4")
                )
                
                location_elem = (
                    card.find("span", class_=re.compile(r"job-search-card__location"))
                    or card.find("span", class_=re.compile(r"job-result-card__location"))
                )

                link_elem = (
                    card.find("a", class_=re.compile(r"(base-card__full-link|base-card--link)"))
                    or card.find("a", href=re.compile(r"/jobs/view/"))
                )

                if title_elem and company_elem and link_elem:
                    # SAFE HREF CHECK (Fixes HTTP 500 AttributeError)
                    href = link_elem.get("href")
                    if not href or not isinstance(href, str):
                        continue

                    clean_link = href.split("?")[0].strip()
                    if not clean_link or clean_link in seen_links:
                        continue

                    seen_links.add(clean_link)
                    found_in_page += 1
                    
                    jobs.append({
                        "source": "LinkedIn",
                        "type": "job",
                        "title": title_elem.get_text(strip=True),
                        "company": company_elem.get_text(strip=True),
                        "location": location_elem.get_text(strip=True) if location_elem else location,
                        "link": clean_link,
                    })

                    if len(jobs) >= limit:
                        break

            if found_in_page == 0 or len(jobs) >= limit:
                break

            time.sleep(0.3)

    except Exception as e:
        logger.error("Error running LinkedIn scraper: %s", e)

    logger.info("LinkedIn: fetched %d jobs", len(jobs))
    return jobs


# --- 2. UNSTOP SCOUT ---------------------------------------------------------
def fetch_unstop_opportunities(keywords: str = "", opportunity_type: str = "jobs", limit: int = 20) -> List[Dict]:
    api_url = "https://unstop.com/api/public/opportunity/search-new"
    params = {"opportunity": opportunity_type, "per_page": limit, "page": 1}
    if keywords:
        params["searchKeyword"] = keywords

    items = []
    try:
        resp = requests.get(api_url, headers={**DEFAULT_HEADERS, "Accept": "application/json"}, params=params, timeout=REQUEST_TIMEOUT)
        if resp.status_code == 200:
            json_data = resp.json()
            if isinstance(json_data, dict):
                data_wrapper = json_data.get("data", {})
                data = data_wrapper.get("data", []) if isinstance(data_wrapper, dict) else []

                for item in data:
                    if not isinstance(item, dict):
                        continue
                    title = item.get("title")
                    if not title:
                        continue
                    org_data = item.get("organisation")
                    org = org_data.get("name") if isinstance(org_data, dict) else item.get("company_name", "Unstop Employer")
                    slug = item.get("public_url") or item.get("site_url") or item.get("slug", "")
                    link = slug if str(slug).startswith("http") else f"https://unstop.com/{slug}".rstrip("/")

                    items.append({
                        "source": "Unstop",
                        "type": "job",
                        "title": title,
                        "company": org or "Unstop Employer",
                        "location": item.get("region") or "Online / On-site",
                        "link": link or "https://unstop.com/",
                    })
    except Exception as e:
        logger.warning("Unstop fetch failed: %s", e)

    logger.info("Unstop: fetched %d items", len(items))
    return items


# --- 3. DEVPOST SCOUT --------------------------------------------------------
def fetch_devpost_hackathons(keywords: str = "", limit: int = 20) -> List[Dict]:
    params = {"status[]": "open"}
    if keywords:
        params["search"] = keywords

    items = []
    try:
        resp = requests.get("https://devpost.com/api/hackathons", headers={**DEFAULT_HEADERS, "Accept": "application/json"}, params=params, timeout=REQUEST_TIMEOUT)
        if resp.status_code == 200:
            json_data = resp.json()
            if isinstance(json_data, dict):
                hackathons = json_data.get("hackathons", [])
                if isinstance(hackathons, list):
                    for h in hackathons[:limit]:
                        if not isinstance(h, dict):
                            continue
                        loc_data = h.get("displayed_location", {})
                        location = loc_data.get("location") if isinstance(loc_data, dict) else None

                        items.append({
                            "source": "Devpost",
                            "type": "hackathon",
                            "title": h.get("title", "Untitled Hackathon"),
                            "company": h.get("organization_name") or "Devpost Community",
                            "location": "Online" if not location else location,
                            "link": h.get("url", "https://devpost.com/hackathons"),
                        })
    except Exception as e:
        logger.warning("Devpost fetch failed: %s", e)

    logger.info("Devpost: fetched %d hackathons", len(items))
    return items


# --- ORCHESTRATOR -----------------------------------------------------------
def run_scout(
    keywords: str = "Python Developer",
    location: str = "Remote",
    limit_per_source: int = 30
) -> Dict[str, List[Dict]]:
    """
    Safely runs scout across LinkedIn, Devpost, and Unstop.
    Guarantees returning a valid dictionary even if a scraper fails.
    """
    results = {
        "LinkedIn": [],
        "Devpost": [],
        "Unstop": []
    }

    try:
        results["LinkedIn"] = fetch_linkedin_jobs(keywords, location, max_pages=4, limit=limit_per_source)
    except Exception as e:
        logger.error("LinkedIn scraper error: %s", e)

    try:
        results["Devpost"] = fetch_devpost_hackathons(keywords, limit=limit_per_source)
    except Exception as e:
        logger.error("Devpost scraper error: %s", e)

    try:
        results["Unstop"] = fetch_unstop_opportunities(keywords, "jobs", limit_per_source)
    except Exception as e:
        logger.error("Unstop scraper error: %s", e)

    return results


if __name__ == "__main__":
    res = run_scout("Python Developer", "Coimbatore")
    print(res)