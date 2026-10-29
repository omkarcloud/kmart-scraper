# 🛒 Kmart Scraper

Kmart Scraper is a **free and open-source** scraper that gets you **unlimited** detailed Kmart Australia data for free.

## ✨ What Can I Get?

- 🛍️ **Full details on 210K+ products** — price, was-price, stock by state, variants, barcodes, seller offers & descriptions
- 🔍 **Search & browse every aisle** — keyword search, 22 departments, 496 brands, clearance & new arrivals
- ⭐ **Every customer review** — full text, star rating, photos, helpful votes & star breakdown
- 📍 **All 300+ stores & 160 marketplace sellers** — addresses, phones, GPS, trading hours & seller shops

## 💍 Example: A Full Kmart Product

```json
{
  "id": "S169775",
  "name": "Smooth Bangle - Gold Tone",
  "link": "https://www.kmart.com.au/product/smooth-bangle-gold-tone-s169775/",
  "brand": "Anko",
  "image": "https://assets.kmart.com.au/transform/77c296c4-4f1f-4ca2-a9eb-0e016e36db95/73330974-1?io=transform:fill,width:580,height:725",
  "pricing": { "price": 5, "currency": "AUD", "list_price": 5, "was_price": null, "is_on_sale": false },
  "rating": { "average": 5.0, "count": 1 },
  "colour": "GOLD",
  "barcode": "9341111152280",
  "seller": { "id": 1, "name": "Kmart" },
  "is_clearance": false,
  "out_of_stock_states": [],
  "shipping": { "is_free": true, "is_free_metro": true },
  "merchandise": { "department": 32, "class_name": "JEWELLERY" },
  "description": "Product Details\n- Material: Acrylic\n- Dimensions/Size: 6.6cm (Dia.)\n- Colour: Gold\nFeatures\n- Smooth design",
  "variants": [
    { "id": "73330974", "name": "Smooth Bangle - Gold Tone", "colour": "GOLD", "size": "NO SIZE", "barcode": "9341111152280", "pricing": { "price": 5, "currency": "AUD" }, "out_of_stock_states": [] }
  ],
  "category": {
    "id": "9abb6e2804de4e587cd87e7d6eaaacae",
    "name": "Bracelets",
    "link": "https://www.kmart.com.au/category/women/womens-bracelets/",
    "path": ["Womens", "Accessories", "Jewellery"]
  }
}
```

*Trimmed for readability.*

## 🚀 Unlimited Free Kmart Data — Get It in 60 Seconds

1️⃣ Clone and install:
```bash
git clone https://github.com/omkarcloud/kmart-scraper
cd kmart-scraper
python -m pip install -r requirements.txt
```

2️⃣ Start the API:
```bash
python run.py
```

3️⃣ Get your first data:
```bash
curl "http://localhost:8000/products/details?product=S169775"
```

```json
{
  "id": "S169775",
  "name": "Smooth Bangle - Gold Tone",
  "link": "https://www.kmart.com.au/product/smooth-bangle-gold-tone-s169775/",
  "brand": "Anko",
  "pricing": { "price": 5, "currency": "AUD", "list_price": 5, "was_price": null, "is_on_sale": false, "promotion": null },
  "rating": { "average": 5.0, "count": 1 },
  "colour": "GOLD",
  "barcode": "9341111152280",
  "seller": { "id": 1, "name": "Kmart" },
  "is_clearance": false,
  "out_of_stock_states": [],
  "merchandise": { "department": 32, "class_name": "JEWELLERY" },
  "category": {
    "id": "9abb6e2804de4e587cd87e7d6eaaacae",
    "name": "Bracelets",
    "link": "https://www.kmart.com.au/category/women/womens-bracelets/",
    "path": ["Womens", "Accessories", "Jewellery"]
  }
}
```

All 18 endpoints are now live at `http://localhost:8000`.

Pulling store, seller or sitemap pages at high volume? If they start answering 403, set `KMART_PROXY` to an Australian residential proxy (`http://user:pass@host:port`). For everything else you need nothing.

## 📚 Endpoints

18 endpoints cover everything you need.

| Endpoint | Path | Returns |
|---|---|---|
| Product Details | `/products/details` | Everything about one product in a single call |
| Search Products | `/products/search` | 40 products per page; filter by brand, colour, price, state stock |
| Search Suggestions | `/products/suggestions` | Autocomplete terms with product counts, plus matching products |
| Product Reviews | `/products/reviews` | Full review text, star rating, photos and helpful votes |
| Bulk Product Details | `/products/bulk` | Up to 100 full product records in one call |
| Best Sellers | `/products/bestsellers` | Kmart's top sellers, store-wide or in any category |
| Specials | `/specials` | Clearance, online-only, OnePass deals and new arrivals |
| Category Tree | `/categories/list` | Every category with link and product count |
| Category Products | `/categories/products` | Any category or collection, 40 per page, fully filterable |
| Brands | `/brands/list` | Every brand Kmart sells, with product counts |
| Brand Products | `/brands/products` | A brand's full Kmart range, 40 per page |
| Marketplace Sellers | `/sellers/list` | Every marketplace seller with shop link and product count |
| Seller Details | `/sellers/details` | Seller shop: logo, description, shipping policy, categories |
| Seller Products | `/sellers/products` | A seller's full range, 40 per page |
| Search Stores | `/stores/search` | Stores near a suburb, postcode or GPS point |
| Store Details | `/stores/details` | Address, phone, GPS and weekly trading hours |
| Sitemap Index | `/sitemap/index` | Every Kmart sitemap file with last-modified date |
| Sitemap Links | `/sitemap/links` | Every product, category and store URL, 100 per page |

## 🔍 Exploring Parameters

The same API is published on RapidAPI, and its playground is the easiest place to try parameters and see raw responses. Once a request looks right, run it locally for **unlimited free** data.

1. [Subscribe to the free plan](https://rapidapi.com/OmkarCloud/api/best-kmart-scraper-free-1000-calls/pricing) — 1,000 calls/month, no credit card.
2. [Try the endpoints in the playground](https://rapidapi.com/OmkarCloud/api/best-kmart-scraper-free-1000-calls/playground) — every param is pre-filled, so you see real data in one click.
3. Copy the generated code and replace `https://best-kmart-scraper-free-1000-calls.p.rapidapi.com` with `http://localhost:8000`. It will now run against your local API.

```python
import requests

# generated by the playground, host swapped for the local API
response = requests.get(
    "http://localhost:8000/products/search",
    params={"query": "air fryer", "sort": "price_asc"},
)
print(response.json())
```

## 💬 Have Questions? We Have Answers.

You're a developer — we know how hard completing a project can be. So we offer full support: just message us and we'll reply ✅ with a solution within 1 working day.

[![Message Us on WhatsApp about Kmart Scraper](https://raw.githubusercontent.com/omkarcloud/assets/master/images/whatsapp-us.png)](https://api.whatsapp.com/send?phone=918178804274&text=I%20need%20help%20using%20the%20Kmart%20Scraper%20API.)

[![Ask Us by Email about Kmart Scraper](https://raw.githubusercontent.com/omkarcloud/assets/master/images/ask-on-email.png)](mailto:happy.to.help@omkar.cloud?subject=Help%20with%20Kmart%20Scraper%20API&body=I%20need%20help%20using%20the%20Kmart%20Scraper%20API.)

## ⚡ Popular Scrapers by Omkar Cloud

- [**Google Maps Scraper (3,100+ GitHub Stars)**](https://github.com/omkarcloud/google-maps-scraper) — type "dentists in New York", get every business as a ready-to-call lead list: phones, emails, websites & reviews. Up to 100K free leads/month.
- [**G2 Scraper**](https://www.omkar.cloud/tools/g2-scraper) — G2 product details, ratings & AI-found contacts
- [**Website Email Contact Scraper**](https://www.omkar.cloud/tools/website-email-contact-scraper) — emails, phones & socials from any website
- [**AliExpress Scraper**](https://www.omkar.cloud/tools/aliexpress-scraper-api) — live product details, SKU variants, stock & shipping
- [**Booking Scraper**](https://www.omkar.cloud/tools/booking-scraper) — Booking.com hotels: prices, ratings, rooms & amenities
- [**Etsy Scraper**](https://www.omkar.cloud/tools/etsy-scraper) — Etsy products: prices, discounts, shops & variations

## ⭐ Love It? [Star It ⭐!](https://github.com/omkarcloud/kmart-scraper)

Star the repo ⭐ and become my star hero!

It's just 1 click, but it means the world to me.

[![Star us on GitHub](https://raw.githubusercontent.com/omkarcloud/google-maps-scraper/master/screenshots/star-us.png)](https://github.com/omkarcloud/kmart-scraper)
