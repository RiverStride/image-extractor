import argparse
import csv
import os
import re
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import StaleElementReferenceException
import urllib.request

# First we need to find the links to all the webpages within the same domain as the home URL
def versant_get_nav_urls(driver, settings):
    # So we don't return an unititialized variable
    url_list = [f"{settings['root']}"]

    # We need to know which pages to search for images
    nav_items = driver.find_elements(By.CSS_SELECTOR, settings["targetnav"] + " " + settings["targetelem"])

    for item in nav_items:
        item_url = item.get_attribute("href")
        # Trim items based off domain, and only keep those that match the root
        if not item_url.startswith(settings['root']):
            continue

        # url_list.append(item.href)
        url_list.append(item_url)

    # We don't need it to be ordered, just without duplicates
    url_set = set(url_list)
    url_list = list(url_set)

    if settings['debug']:
        for url in url_list:
            print(url)
    
    return url_list
# Then save those links for us to crawl through each one.

def versant_get_page_images(nav_urls, driver, settings):
# For each page that we open we need to find all images on that page
    image_urls = {}
    for url in nav_urls:
        driver.get(url)
        page_images = driver.find_elements(By.CSS_SELECTOR, settings["targetimage"])

        for page_image in page_images:
            try:
                image_url = page_image.get_attribute("src")

                # src might not be the largest image
                # so if there is a larger image, we'll need to grab that instead
                srcset = page_image.get_attribute("srcset")
                if srcset != "":
                    if settings['debug']:
                        print("has srcset")
                    srcset_largest = srcset.split(", ")[-1] # get the last image assuming it's the largest
                    image_url = srcset_largest.split(" ")[0] # we don't need the pixel width included
                
                if image_url is None:
                    continue # Sometimes there isn't a url

                # We don't want any duplicate images, so we'll save a dictionary of images in an array along with their filesize and url
                image_url_split = image_url.split("/") # get url from slash
                if image_url_split[-1].startswith("?"):
                    image_url_split = image_url.split("%2F") # if that's empty get it from url attribute

                image_name = image_url_split[-1].split("?")[0] # get the last item and then remove any remaining query

                image_size = page_image.size['width'] * page_image.size['height']
                # Sometimes images are in slideshows and their size will be 0
                # We'll set a default size that's larger than the default thumbnails for these
                if image_size == 0: 
                    image_size = 90 * 90 # want this to be larger than most thumbnails
                if settings['debug']:
                    print(page_image.size)
                    print(f"{image_name}:{image_size}")

                # If the image url exists and the new one is smaller than what we already have
                # We don't need to update the image_urls dictionary listing
                if image_name in image_urls and image_urls[image_name]["size"] >= image_size:
                    if settings['debug']:
                        print(f"{image_name} replaced with larger image")
                    continue

                # If an image is larger than a previously found image, we'll replace the URL with that one
                image_urls.update({image_name: {"url": image_url, "size": image_size, "name": image_name}})
            except StaleElementReferenceException as e:
                continue

    if settings['debug']:
        for image in image_urls:
            print(image)

    return image_urls

def versant_sanitize_url(url):
    return re.sub(r'[^a-zA-Z0-9_.-]', '_', url)

# Save image URLs in CSV
def versant_save_image_url_list(image_urls, settings):
    sanitized_root = versant_sanitize_url(settings['root'])

    # We'll want to make sure we have a unique directory to save into
    folder = f"{settings['imagesfolder']}/{sanitized_root}"
    if not os.path.exists(folder):
        os.makedirs(folder)

    with open(f"{settings['imagesfolder']}/{sanitized_root}/{sanitized_root}.csv", 'w', newline='') as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=['url', 'size', 'name'])
        writer.writeheader()
        writer.writerows(image_urls.values())

# If we've already crawled the website, we'll just use the CSV instead
def versant_retrieve_image_url_list(settings):
    image_urls = {}
    sanitized_root = versant_sanitize_url(settings['root'])
    with open(f"{settings['imagesfolder']}/{sanitized_root}/{sanitized_root}.csv", 'r', encoding='utf-8') as csv_file:
        csv_reader = csv.DictReader(csv_file)
        for row in csv_reader:
            image_urls.update({row[name]: {row}})

    return image_urls

# Then we crawl through the list of images and download each one.
def versant_download_image_list(image_urls, settings):
    image_name_counter = 1

    for image_url in image_urls.values():
        print(f"Downloading image no. {image_name_counter} ...")
        sanitized_root = versant_sanitize_url(settings['root'])

        file_name = f"./images/{sanitized_root}/{image_url['name']}"
        urllib.request.urlretrieve(image_url['url'], file_name)

        print(f"{image_url['name']} downloaded successfully to {file_name}")

        image_name_counter += 1

def main(): 
    parser = argparse.ArgumentParser(
        description = 'A script to extract images from pages found in the navigation for a specific website')
    
    parser.add_argument('--url', type=str, default="https://vip.teeitup.com/",
                        help="The target url we will be crawling (default: https://vip.teeitup.com/)")
    parser.add_argument('--nav_selector', type=str, default="nav",
                        help="The CSS target for the navigation (default: nav)")
    parser.add_argument('--nav_item', type=str, default='a',
                        help="The CSS target for the links within the navigation (default: a)")
    parser.add_argument('--img_target', type=str, default='img',
                        help="The CSS target to find the images we want to download. Works with any element that contains an src or srcset attribute (default: img)")
    parser.add_argument('-d', '--debug', action='store_true',
                        help="Enable debug more and more verbose output (default: False)")
    parser.add_argument('-s', '--save', type=str, default='./images'
                        help="Set location to save images to, Images will be saved in a folder based off the root url")

    args = parser.parse_args()
    # to run Chrome in headless mode
    options = Options()
    options.add_argument("--headless") # So chrome knows we want to run in headless

    # Initialize a Chrome WebDriver instance
    # with the specified options
    driver = webdriver.Chrome(
        service = ChromeService(),
        options = options
    )

    driver.maximize_window()
    
    # internal program settings
    settings = {
        "root": args.url,
        "imagesfolder": args.save,
        "targetnav": args.nav_selector,
        "targetelem": args.nav_item,
        "targetimage": args.img_target,
        "debug": args.debug
    }

    url = settings["root"]
    driver.get(url)

    nav_urls = versant_get_nav_urls(driver, settings)
    image_urls = versant_get_page_images(nav_urls, driver, settings)
    print(len(nav_urls))
    print(len(image_urls))

    driver.quit()

    versant_save_image_url_list(image_urls, settings)
    versant_download_image_list(image_urls, settings)
    
if __name__ == "__main__":
    main()
