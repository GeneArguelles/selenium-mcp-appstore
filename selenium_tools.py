# selenium_tools.py
import os
import uuid
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from urllib.parse import quote

# ==========================================================
# Helper functions
# ==========================================================
def _wait_css(driver, selector, timeout=10):
    return WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
    )

def _wait_clickable(driver, selector, timeout=10):
    return WebDriverWait(driver, timeout).until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
    )

def _public_base_url() -> str:
    base = os.getenv("BASE_URL") or os.getenv("RENDER_EXTERNAL_URL") or ""
    base = base.strip()
    if base and not base.startswith("http"):
        base = "https://" + base
    return base.rstrip("/")

def _make_driver():
    opts = Options()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1280,720")

    on_render = os.getenv("RENDER", "").lower() in ("1", "true", "yes")

    # Prefer system chromium on Render/Debian
    chrome_bin = os.getenv("CHROME_BINARY") or "/usr/bin/chromium"
    if os.path.exists(chrome_bin):
        opts.binary_location = chrome_bin

    # Use system chromedriver (preinstalled by apt chromium-driver)
    driver_path = os.getenv("CHROMEDRIVER_PATH") or "/usr/bin/chromedriver"
    if os.path.exists(driver_path):
        return webdriver.Chrome(service=Service(driver_path), options=opts)

    # 🚫 On Render, never fall back to Selenium Manager (it downloads into /root/.cache)
    if on_render:
        raise RuntimeError(
            f"chromedriver not found at {driver_path}. "
            "Ensure Dockerfile installs chromium-driver and verifies `which chromedriver`."
        )

    # Fallback (local dev only)
    return webdriver.Chrome(options=opts)

def selenium_open_page(url: str):
    driver = _make_driver()
    try:
        driver.get(url)
        WebDriverWait(driver, 10).until(lambda d: d.execute_script("return document.readyState") == "complete")
        return {"url": url, "title": driver.title}
    finally:
        driver.quit()

def selenium_click(url: str, selector: str):
    driver = _make_driver()
    try:
        driver.get(url)
        try:
            el = _wait_clickable(driver, selector)
        except TimeoutException:
            return {"ok": False, "error": f"Timed out waiting for clickable: {selector}", "url": url}

        el.click()
        return {"ok": True, "url": url, "clicked": selector, "title": driver.title}
    finally:
        driver.quit()

def selenium_get_text(url: str, selector: str):
    driver = _make_driver()
    try:
        driver.get(url)
        el = _wait_css(driver, selector)   # or visibility_of_element_located
        return {"url": url, "selector": selector, "text": el.text}
    finally:
        driver.quit()

def selenium_screenshot(url: str, filename: str = "screenshot.png"):
    driver = _make_driver()
    try:
        driver.get(url)

        # Always write to /tmp; ensure .png extension
        base = os.path.basename(filename) if filename else "screenshot.png"
        if not base.lower().endswith(".png"):
            base += ".png"

        if base == "screenshot.png":
            base = f"screenshot-{uuid.uuid4().hex}.png"

        outpath = os.path.join("/tmp", base)

        driver.save_screenshot(outpath)

        base_url = _public_base_url()
        download_url = f"{base_url}/files?path={quote(outpath, safe='')}" if base_url else None

        return {
            "ok": True,
            "url": url,
            "screenshot": outpath,
            "download_url": download_url,
        }

    except Exception as e:
        return {"ok": False, "url": url, "error": f"Screenshot failed: {e}"}
    finally:
        driver.quit()
        