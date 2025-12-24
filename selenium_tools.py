# ==========================================================
# selenium_tools.py — Headless Selenium automation functions
# ==========================================================
from selenium import webdriver
from selenium.webdriver.chrome.options import Options

def selenium_open_page(url):
    options = Options()
    options.add_argument("--headless")
    driver = webdriver.Chrome(options=options)
    driver.get(url)
    title = driver.title
    driver.quit()
    return {"title": title}

def selenium_click(selector):
    options = Options()
    options.add_argument("--headless")
    driver = webdriver.Chrome(options=options)
    element = driver.find_element("css selector", selector)
    element.click()
    driver.quit()
    return {"clicked": selector}

def selenium_get_text(selector):
    options = Options()
    options.add_argument("--headless")
    driver = webdriver.Chrome(options=options)
    text = driver.find_element("css selector", selector).text
    driver.quit()
    return {"text": text}

def selenium_screenshot(filename="screenshot.png"):
    options = Options()
    options.add_argument("--headless")
    driver = webdriver.Chrome(options=options)
    driver.save_screenshot(filename)
    driver.quit()
    return {"screenshot": filename}
