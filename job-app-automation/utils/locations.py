"""
World locations list for autocomplete on the Job Search page.
Covers major cities in US, UK, Canada, Australia, India, Europe, and more.
"""
from typing import List

WORLD_LOCATIONS: List[str] = [
    # ── Special ───────────────────────────────────────────────────────────────
    "Remote",
    "Remote (Worldwide)",
    "Remote (US Only)",
    "Remote (UK Only)",
    "Hybrid",

    # ── United States ─────────────────────────────────────────────────────────
    "New York, NY",
    "Los Angeles, CA",
    "Chicago, IL",
    "Houston, TX",
    "Phoenix, AZ",
    "Philadelphia, PA",
    "San Antonio, TX",
    "San Diego, CA",
    "Dallas, TX",
    "San Jose, CA",
    "Austin, TX",
    "Jacksonville, FL",
    "Fort Worth, TX",
    "Columbus, OH",
    "Charlotte, NC",
    "Indianapolis, IN",
    "San Francisco, CA",
    "Seattle, WA",
    "Denver, CO",
    "Boston, MA",
    "Nashville, TN",
    "Baltimore, MD",
    "Portland, OR",
    "Las Vegas, NV",
    "Atlanta, GA",
    "Miami, FL",
    "Minneapolis, MN",
    "Tampa, FL",
    "Raleigh, NC",
    "Arlington, TX",
    "New Orleans, LA",
    "Cleveland, OH",
    "Pittsburgh, PA",
    "Richmond, VA",
    "Salt Lake City, UT",
    "Sacramento, CA",
    "Kansas City, MO",
    "Orlando, FL",
    "St. Louis, MO",
    "Detroit, MI",
    "Washington, DC",
    "Louisville, KY",
    "Memphis, TN",
    "Cincinnati, OH",
    "Milwaukee, WI",
    "Albuquerque, NM",
    "Tucson, AZ",
    "Fresno, CA",
    "Mesa, AZ",
    "Omaha, NE",
    "Colorado Springs, CO",
    "Virginia Beach, VA",
    "Oakland, CA",
    "Tulsa, OK",
    "Wichita, KS",
    "Riverside, CA",
    "St. Paul, MN",
    "Lexington, KY",
    "Stockton, CA",
    "Anchorage, AK",
    "Honolulu, HI",
    "Newark, NJ",
    "Jersey City, NJ",
    "Madison, WI",
    "Durham, NC",
    "Lubbock, TX",
    "Winston-Salem, NC",
    "Garland, TX",
    "Glendale, AZ",
    "Hialeah, FL",
    "Reno, NV",
    "Baton Rouge, LA",
    "Irvine, CA",
    "Chesapeake, VA",
    "Norfolk, VA",
    "Scottsdale, AZ",
    "Laredo, TX",
    "Madison, WI",
    "Gilbert, AZ",
    "Henderson, NV",
    "Chandler, AZ",

    # US States (broad)
    "California, USA",
    "New York State, USA",
    "Texas, USA",
    "Florida, USA",
    "Washington State, USA",
    "Massachusetts, USA",
    "Illinois, USA",
    "Georgia, USA",
    "North Carolina, USA",
    "Virginia, USA",
    "Colorado, USA",
    "Arizona, USA",
    "Pennsylvania, USA",
    "Ohio, USA",
    "Michigan, USA",
    "New Jersey, USA",
    "Minnesota, USA",
    "Oregon, USA",
    "United States",

    # ── United Kingdom ────────────────────────────────────────────────────────
    "London, UK",
    "Manchester, UK",
    "Birmingham, UK",
    "Leeds, UK",
    "Glasgow, UK",
    "Sheffield, UK",
    "Bristol, UK",
    "Edinburgh, UK",
    "Liverpool, UK",
    "Newcastle upon Tyne, UK",
    "Nottingham, UK",
    "Southampton, UK",
    "Cardiff, UK",
    "Belfast, UK",
    "Leicester, UK",
    "Oxford, UK",
    "Cambridge, UK",
    "Reading, UK",
    "Coventry, UK",
    "Bradford, UK",
    "Stoke-on-Trent, UK",
    "Wolverhampton, UK",
    "Plymouth, UK",
    "Derby, UK",
    "Swansea, UK",
    "United Kingdom",

    # ── Canada ────────────────────────────────────────────────────────────────
    "Toronto, ON, Canada",
    "Vancouver, BC, Canada",
    "Montreal, QC, Canada",
    "Calgary, AB, Canada",
    "Ottawa, ON, Canada",
    "Edmonton, AB, Canada",
    "Mississauga, ON, Canada",
    "Winnipeg, MB, Canada",
    "Quebec City, QC, Canada",
    "Hamilton, ON, Canada",
    "Brampton, ON, Canada",
    "Surrey, BC, Canada",
    "Kitchener, ON, Canada",
    "Halifax, NS, Canada",
    "London, ON, Canada",
    "Victoria, BC, Canada",
    "Canada",

    # ── Australia ─────────────────────────────────────────────────────────────
    "Sydney, NSW, Australia",
    "Melbourne, VIC, Australia",
    "Brisbane, QLD, Australia",
    "Perth, WA, Australia",
    "Adelaide, SA, Australia",
    "Gold Coast, QLD, Australia",
    "Canberra, ACT, Australia",
    "Newcastle, NSW, Australia",
    "Wollongong, NSW, Australia",
    "Hobart, TAS, Australia",
    "Darwin, NT, Australia",
    "Australia",

    # ── New Zealand ───────────────────────────────────────────────────────────
    "Auckland, New Zealand",
    "Wellington, New Zealand",
    "Christchurch, New Zealand",

    # ── India ─────────────────────────────────────────────────────────────────
    "Bangalore, India",
    "Mumbai, India",
    "Delhi, India",
    "New Delhi, India",
    "Hyderabad, India",
    "Chennai, India",
    "Pune, India",
    "Kolkata, India",
    "Ahmedabad, India",
    "Noida, India",
    "Gurgaon, India",
    "Gurugram, India",
    "Indore, India",
    "Chandigarh, India",
    "Jaipur, India",
    "Kochi, India",
    "Coimbatore, India",
    "Trivandrum, India",
    "Nagpur, India",
    "Surat, India",
    "India",

    # ── Germany ───────────────────────────────────────────────────────────────
    "Berlin, Germany",
    "Munich, Germany",
    "Hamburg, Germany",
    "Frankfurt, Germany",
    "Cologne, Germany",
    "Stuttgart, Germany",
    "Düsseldorf, Germany",
    "Leipzig, Germany",
    "Dortmund, Germany",
    "Essen, Germany",
    "Bremen, Germany",
    "Dresden, Germany",
    "Germany",

    # ── France ────────────────────────────────────────────────────────────────
    "Paris, France",
    "Lyon, France",
    "Marseille, France",
    "Toulouse, France",
    "Nice, France",
    "Nantes, France",
    "Bordeaux, France",
    "France",

    # ── Netherlands ───────────────────────────────────────────────────────────
    "Amsterdam, Netherlands",
    "Rotterdam, Netherlands",
    "The Hague, Netherlands",
    "Utrecht, Netherlands",
    "Netherlands",

    # ── Spain ─────────────────────────────────────────────────────────────────
    "Madrid, Spain",
    "Barcelona, Spain",
    "Valencia, Spain",
    "Seville, Spain",
    "Spain",

    # ── Ireland ───────────────────────────────────────────────────────────────
    "Dublin, Ireland",
    "Cork, Ireland",
    "Galway, Ireland",
    "Ireland",

    # ── Switzerland ───────────────────────────────────────────────────────────
    "Zurich, Switzerland",
    "Geneva, Switzerland",
    "Basel, Switzerland",
    "Switzerland",

    # ── Sweden ────────────────────────────────────────────────────────────────
    "Stockholm, Sweden",
    "Gothenburg, Sweden",
    "Malmö, Sweden",
    "Sweden",

    # ── Norway ────────────────────────────────────────────────────────────────
    "Oslo, Norway",
    "Bergen, Norway",
    "Norway",

    # ── Denmark ───────────────────────────────────────────────────────────────
    "Copenhagen, Denmark",
    "Denmark",

    # ── Poland ────────────────────────────────────────────────────────────────
    "Warsaw, Poland",
    "Krakow, Poland",
    "Wroclaw, Poland",
    "Poland",

    # ── Portugal ──────────────────────────────────────────────────────────────
    "Lisbon, Portugal",
    "Porto, Portugal",
    "Portugal",

    # ── Italy ─────────────────────────────────────────────────────────────────
    "Milan, Italy",
    "Rome, Italy",
    "Turin, Italy",
    "Italy",

    # ── Singapore ─────────────────────────────────────────────────────────────
    "Singapore",

    # ── UAE ───────────────────────────────────────────────────────────────────
    "Dubai, UAE",
    "Abu Dhabi, UAE",
    "Sharjah, UAE",
    "UAE",

    # ── Japan ─────────────────────────────────────────────────────────────────
    "Tokyo, Japan",
    "Osaka, Japan",
    "Kyoto, Japan",
    "Japan",

    # ── South Korea ───────────────────────────────────────────────────────────
    "Seoul, South Korea",
    "Busan, South Korea",
    "South Korea",

    # ── China ─────────────────────────────────────────────────────────────────
    "Beijing, China",
    "Shanghai, China",
    "Shenzhen, China",
    "Guangzhou, China",
    "China",

    # ── Hong Kong & Taiwan ────────────────────────────────────────────────────
    "Hong Kong",
    "Taipei, Taiwan",

    # ── Brazil ────────────────────────────────────────────────────────────────
    "São Paulo, Brazil",
    "Rio de Janeiro, Brazil",
    "Brasília, Brazil",
    "Brazil",

    # ── Mexico ────────────────────────────────────────────────────────────────
    "Mexico City, Mexico",
    "Guadalajara, Mexico",
    "Monterrey, Mexico",
    "Mexico",

    # ── Argentina ─────────────────────────────────────────────────────────────
    "Buenos Aires, Argentina",
    "Argentina",

    # ── South Africa ──────────────────────────────────────────────────────────
    "Cape Town, South Africa",
    "Johannesburg, South Africa",
    "Durban, South Africa",
    "South Africa",

    # ── Nigeria ───────────────────────────────────────────────────────────────
    "Lagos, Nigeria",
    "Abuja, Nigeria",
    "Nigeria",

    # ── Kenya ─────────────────────────────────────────────────────────────────
    "Nairobi, Kenya",
    "Kenya",

    # ── Egypt ─────────────────────────────────────────────────────────────────
    "Cairo, Egypt",
    "Egypt",

    # ── Saudi Arabia ──────────────────────────────────────────────────────────
    "Riyadh, Saudi Arabia",
    "Jeddah, Saudi Arabia",
    "Saudi Arabia",

    # ── Israel ────────────────────────────────────────────────────────────────
    "Tel Aviv, Israel",
    "Jerusalem, Israel",
    "Israel",
]


def search_locations(query: str) -> List[str]:
    """
    Return up to 8 location suggestions matching the query.
    Matching is case-insensitive and checks all parts of the location string.
    """
    if not query or len(query) < 2:
        return []
    q = query.lower()
    # Prioritise starts-with matches, then contains matches
    starts = [loc for loc in WORLD_LOCATIONS if loc.lower().startswith(q)]
    contains = [loc for loc in WORLD_LOCATIONS if q in loc.lower() and not loc.lower().startswith(q)]
    results = starts + contains
    return results[:8]
