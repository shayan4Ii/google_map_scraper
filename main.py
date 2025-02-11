"""This script serves as an example on how to use Python 
   & Playwright to scrape/extract data from Google Maps"""

from playwright.sync_api import sync_playwright
from dataclasses import dataclass, asdict, field
import pandas as pd
import argparse
import os
import sys
import logging

# Configure logger
logging.basicConfig(
    level=logging.INFO,  # Change to DEBUG for more details
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("scraper.log"),  # Logs will be written to this file
        logging.StreamHandler(sys.stdout)  # Logs will also appear in the console
    ]
)

logger = logging.getLogger(__name__)

@dataclass
class Business:
    """Holds business data"""
    name: str = None
    address: str = None
    website: str = None
    phone_number: str = None
    reviews_count: int = None
    reviews_average: float = None
    latitude: float = None
    longitude: float = None
    url: str = None  # New field for business URL



@dataclass
class BusinessList:
    """holds list of Business objects,
    and save to both excel and csv
    """
    business_list: list[Business] = field(default_factory=list)
    save_at = 'output'

    def dataframe(self):
        """transform business_list to pandas dataframe

        Returns: pandas dataframe
        """
        return pd.json_normalize(
            (asdict(business) for business in self.business_list), sep="_"
        )

    def save_to_excel(self, filename):
        """saves pandas dataframe to excel (xlsx) file

        Args:
            filename (str): filename
        """

        if not os.path.exists(self.save_at):
            os.makedirs(self.save_at)
        self.dataframe().to_excel(f"output/{filename}.xlsx", index=False)

    def save_to_csv(self, filename):
        """saves pandas dataframe to csv file

        Args:
            filename (str): filename
        """

        if not os.path.exists(self.save_at):
            os.makedirs(self.save_at)
        self.dataframe().to_csv(f"output/{filename}.csv", index=False)

def extract_coordinates_from_url(url: str) -> tuple[float,float]:
    """helper function to extract coordinates from url"""
    
    coordinates = url.split('/@')[-1].split('/')[0]
    # return latitude, longitude
    return float(coordinates.split(',')[0]), float(coordinates.split(',')[1])

def main():
    
    ########
    # input 
    ########
    
    # read search from arguments
    parser = argparse.ArgumentParser()
    parser.add_argument("-s", "--search", type=str)
    parser.add_argument("-t", "--total", type=int)
    args = parser.parse_args()
    
    if args.search:
        search_list = [args.search]
        
    if args.total:
        total = args.total
    else:
        # if no total is passed, we set the value to random big number
        total = 1_000_000

    if not args.search:
        search_list = []
        # read search from input.txt file
        input_file_name = 'input.txt'
        # Get the absolute path of the file in the current working directory
        input_file_path = os.path.join(os.getcwd(), input_file_name)
        # Check if the file exists
        if os.path.exists(input_file_path):
        # Open the file in read mode
            with open(input_file_path, 'r') as file:
            # Read all lines into a list
                search_list = file.readlines()
                
        if len(search_list) == 0:
            print('Error occured: You must either pass the -s search argument, or add searches to input.txt')
            sys.exit()
        
    ###########
    # scraping
    ###########
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False, 
            executable_path="/usr/bin/google-chrome"  # Adjust path if necessary
        )

        page = browser.new_page()

        page.goto("https://www.google.com/maps", timeout=60000)
        # wait is added for dev phase. can remove it in production
        page.wait_for_timeout(5000)
        
        for search_for_index, search_for in enumerate(search_list):
            logger.info(f"-----\n{search_for_index} - {search_for}".strip())

            page.locator('//input[@id="searchboxinput"]').fill(search_for)
            page.wait_for_timeout(5000)

            page.keyboard.press("Enter")
            page.wait_for_timeout(5000)

            # Scroll to load more results
            page.hover('//a[contains(@href, "https://www.google.com/maps/place")]')

            previously_counted = 0
            same_count_attempts = 0  # Counter to track if no new results appear for multiple attempts

            while True:
                page.mouse.wheel(0, 10000)  # Scroll down
                page.wait_for_timeout(10000)  # Wait 10 seconds for new results to load

                current_count = page.locator('//a[contains(@href, "https://www.google.com/maps/place")]').count()

                if current_count >= total:
                    # Stop if we have collected enough listings
                    listings = page.locator('//a[contains(@href, "https://www.google.com/maps/place")]').all()[:total]
                    listings = [listing.locator("xpath=..") for listing in listings]
                    logger.info(f"Total Scraped: {len(listings)}")
                    break
                elif current_count == previously_counted:
                    # If no new listings appear, increment the counter
                    same_count_attempts += 1
                    logger.info(f"No new listings, attempt {same_count_attempts}/3")
                    
                    if same_count_attempts >= 3:
                        # Stop if no new listings appear for 3 consecutive attempts
                        listings = page.locator('//a[contains(@href, "https://www.google.com/maps/place")]').all()
                        logger.info(f"Arrived at all available\nTotal Scraped: {len(listings)}")
                        break
                else:
                    # Reset counter if new results appear
                    same_count_attempts = 0

                previously_counted = current_count
                logger.info(f"Currently Scraped: {current_count}")

            business_list = BusinessList()

            # Scraping loop
            for listing in listings:
                try:
                    listing.click()
                    page.wait_for_timeout(5000)

                    business = Business()

                    if len(listing.get_attribute("aria-label")) >= 1:
                        business.name = listing.get_attribute("aria-label")
                    else:
                        business.name = ""

                    address_xpath = '//button[@data-item-id="address"]//div[contains(@class, "fontBodyMedium")]'
                    website_xpath = '//a[@data-item-id="authority"]//div[contains(@class, "fontBodyMedium")]'
                    phone_number_xpath = '//button[contains(@data-item-id, "phone:tel:")]//div[contains(@class, "fontBodyMedium")]'
                    review_count_xpath = '//button[@jsaction="pane.reviewChart.moreReviews"]//span'
                    reviews_average_xpath = '//div[@jsaction="pane.reviewChart.moreReviews"]//div[@role="img"]'

                    if page.locator(address_xpath).count() > 0:
                        business.address = page.locator(address_xpath).all()[0].inner_text()
                    else:
                        business.address = ""

                    if page.locator(website_xpath).count() > 0:
                        business.website = page.locator(website_xpath).all()[0].inner_text()
                    else:
                        business.website = ""

                    if page.locator(phone_number_xpath).count() > 0:
                        business.phone_number = page.locator(phone_number_xpath).all()[0].inner_text()
                    else:
                        business.phone_number = ""

                    if page.locator(review_count_xpath).count() > 0:
                        business.reviews_count = int(
                            page.locator(review_count_xpath).inner_text().split()[0].replace(',', '').strip()
                        )
                    else:
                        business.reviews_count = ""

                    if page.locator(reviews_average_xpath).count() > 0:
                        business.reviews_average = float(
                            page.locator(reviews_average_xpath).get_attribute("aria-label").split()[0].replace(',', '.').strip()
                        )
                    else:
                        business.reviews_average = ""

                    # Capture latitude, longitude, and business URL
                    business.latitude, business.longitude = extract_coordinates_from_url(page.url)
                    business.url = page.url  # Capture the clinic's URL

                    business_list.business_list.append(business)

                except Exception as e:
                    logger.error(f'Error occurred: {e}')

            
            #########
            # output
            #########
            business_list.save_to_excel(f"google_maps_data_{search_for}".replace(' ', '_'))
            business_list.save_to_csv(f"google_maps_data_{search_for}".replace(' ', '_'))

        logger.info("Scraping complete. Exiting program.")
        browser.close()
        sys.exit(0)



if __name__ == "__main__":
    main()

