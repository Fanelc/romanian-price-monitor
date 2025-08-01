import requests
from bs4 import BeautifulSoup
import json
import time
import random
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from fake_useragent import UserAgent
import re
from datetime import datetime
import os

class RomanianPriceMonitor:
    def __init__(self):
        with open('config.json', 'r') as f:
            self.config = json.load(f)
        with open('products.json', 'r') as f:
            self.products = json.load(f)
        self.ua = UserAgent()
        
    def get_headers(self):
        return {
            'User-Agent': self.ua.random,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
        }
    
    def extract_price(self, html, url):
        """Extract price from Romanian e-commerce sites"""
        soup = BeautifulSoup(html, 'html.parser')
        price = None
        
        # eMAG price selectors
        if 'emag.ro' in url:
            price_elem = soup.find('p', class_='product-new-price')
            if not price_elem:
                price_elem = soup.find('span', class_='price-current')
        
        # Altex price selectors
        elif 'altex.ro' in url:
            price_elem = soup.find('span', class_='Price-int')
            if not price_elem:
                price_elem = soup.find('div', class_='price-new')
        
        # Flanco price selectors
        elif 'flanco.ro' in url:
            price_elem = soup.find('span', class_='price-new')
            if not price_elem:
                price_elem = soup.find('div', class_='current-price')
        
        # bf.ro price selectors
        elif 'bf.ro' in url:
            price_elem = soup.find('span', class_='price')
        
        else:
            # Generic price extraction
            price_patterns = [
                r'(\d{1,3}(?:\.\d{3})*(?:,\d{2})?)\s*lei',
                r'(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)\s*RON',
                r'price["\']?[:\s]*["\']?(\d+(?:\.\d{3})*(?:,\d{2})?)'
            ]
            
            for pattern in price_patterns:
                matches = re.findall(pattern, html, re.IGNORECASE)
                if matches:
                    price_text = matches[0]
                    price = self.parse_price(price_text)
                    break
        
        if price_elem:
            price_text = price_elem.get_text().strip()
            price = self.parse_price(price_text)
        
        return price
    
    def parse_price(self, price_text):
        """Convert Romanian price text to float"""
        # Remove currency symbols and clean up
        price_text = re.sub(r'[^\d.,]', '', price_text)
        
        # Handle Romanian number format (1.234,56)
        if ',' in price_text and '.' in price_text:
            price_text = price_text.replace('.', '').replace(',', '.')
        elif ',' in price_text:
            # Could be thousands separator or decimal
            parts = price_text.split(',')
            if len(parts[-1]) == 2:  # Decimal separator
                price_text = price_text.replace(',', '.')
            else:  # Thousands separator
                price_text = price_text.replace(',', '')
        
        try:
            return float(price_text)
        except ValueError:
            return None
    
    def scrape_product(self, product):
        """Scrape all URLs for a product and find best price"""
        best_price = float('inf')
        best_url = None
        results = []
        
        for url in product['urls']:
            try:
                time.sleep(random.uniform(
                    self.config['scraping']['delay_min'],
                    self.config['scraping']['delay_max']
                ))
                
                response = requests.get(url, headers=self.get_headers(), timeout=10)
                if response.status_code == 200:
                    price = self.extract_price(response.text, url)
                    if price and price < best_price:
                        best_price = price
                        best_url = url
                    
                    results.append({
                        'url': url,
                        'price': price,
                        'status': 'success'
                    })
                else:
                    results.append({
                        'url': url,
                        'price': None,
                        'status': f'error_{response.status_code}'
                    })
                    
            except Exception as e:
                results.append({
                    'url': url,
                    'price': None,
                    'status': f'error_{str(e)[:50]}'
                })
                print(f"Error scraping {url}: {e}")
        
        return {
            'product_name': product['name'],
            'best_price': best_price if best_price != float('inf') else None,
            'best_url': best_url,
            'all_results': results,
            'target_price': product.get('max_price')
        }
    
    def send_email(self, subject, body):
        """Send email notification"""
        try:
            msg = MIMEMultipart()
            msg['From'] = self.config['email']['sender_email']
            msg['To'] = self.config['email']['recipient_email']
            msg['Subject'] = subject
            
            msg.attach(MIMEText(body, 'html'))
            
            server = smtplib.SMTP(
                self.config['email']['smtp_server'],
                self.config['email']['smtp_port']
            )
            server.starttls()
            server.login(
                self.config['email']['sender_email'],
                self.config['email']['sender_password']
            )
            
            server.send_message(msg)
            server.quit()
            return True
            
        except Exception as e:
            print(f"Email error: {e}")
            return False
    
    def create_discount_email(self, good_deals):
        """Create HTML email for discounts"""
        html = """
        <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                        color: white; padding: 20px; text-align: center;">
                <h1>🚨 DISCOUNT ALERTS!</h1>
                <p>Great deals found on Romanian e-commerce sites</p>
            </div>
            <div style="padding: 20px;">
        """
        
        for deal in good_deals:
            discount_pct = ((deal['target_price'] - deal['best_price']) / deal['target_price']) * 100
            html += f"""
                <div style="border: 1px solid #ddd; padding: 15px; margin-bottom: 15px; border-radius: 5px;">
                    <h3 style="color: #333; margin-top: 0;">{deal['product_name']}</h3>
                    <p><strong>Target Price:</strong> {deal['target_price']} RON</p>
                    <p><strong>Found Price:</strong> 
                       <span style="color: #e74c3c; font-size: 1.3em; font-weight: bold;">
                       {deal['best_price']} RON
                       </span>
                    </p>
                    <p><strong>You Save:</strong> 
                       <span style="color: #27ae60; font-weight: bold;">
                       {discount_pct:.1f}% ({deal['target_price'] - deal['best_price']:.0f} RON)
                       </span>
                    </p>
                    <div style="text-align: center; margin-top: 15px;">
                        <a href="{deal['best_url']}" 
                           style="background: #e74c3c; color: white; padding: 12px 25px; 
                                  text-decoration: none; border-radius: 5px; font-weight: bold;">
                            SHOP NOW →
                        </a>
                    </div>
                </div>
            """
        
        html += """
            </div>
            <div style="text-align: center; padding: 20px; color: #666; font-size: 12px;">
                <p>Romanian Price Monitor | Automated by GitHub Actions</p>
            </div>
        </body>
        </html>
        """
        return html
    
    def run(self):
        """Main monitoring function"""
        print(f"Starting price monitoring at {datetime.now()}")
        good_deals = []
        
        for product in self.products:
            print(f"Checking {product['name']}...")
            result = self.scrape_product(product)
            
            if result['best_price']:
                print(f"  Best price: {result['best_price']} RON")
                
                # Check if it's a good deal
                if (result['target_price'] and 
                    result['best_price'] <= result['target_price']):
                    good_deals.append(result)
                    print(f"  🎉 GOOD DEAL FOUND!")
            else:
                print(f"  No price found")
        
        # Send email if good deals found
        if good_deals:
            subject = f"🔥 {len(good_deals)} Great Deals Found!"
            body = self.create_discount_email(good_deals)
            
            if self.send_email(subject, body):
                print(f"✅ Email sent with {len(good_deals)} deals")
            else:
                print("❌ Failed to send email")
        else:
            print("No good deals found this time")

if __name__ == "__main__":
    monitor = RomanianPriceMonitor()
    monitor.run()
