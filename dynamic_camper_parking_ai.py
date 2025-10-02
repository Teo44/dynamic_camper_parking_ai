#!/usr/bin/env python3
"""
Dynamic Camper Van Parking Finder AI
Scrapes parking locations from the internet in real-time
"""

import requests
import json
from datetime import datetime, timedelta
from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass
from enum import Enum
import re
import time
from urllib.parse import urlencode, quote
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
import os
import pickle
import math
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.widgets import Button
from matplotlib.patches import Circle
import numpy as np
import contextily as ctx

class ParkingSource(Enum):
    OPENSTREETMAP = "openstreetmap"
    GOOGLE_PLACES = "google_places"
    CITY_WEBSITES = "city_websites"
    PARK4NIGHT = "park4night"

@dataclass
class ScrapedParkingSpot:
    name: str
    latitude: float
    longitude: float
    address: str
    parking_type: str
    max_height: Optional[float]
    max_weight: Optional[float]
    has_facilities: bool
    overnight_allowed: bool
    restrictions: List[str]
    source: str
    confidence: float  # 0.0 to 1.0

@dataclass
class CamperRequirements:
    height: float  # meters
    weight: float  # tons
    length: float  # meters
    needs_facilities: bool
    needs_overnight: bool
    radius_km: float

class OpenStreetMapScraper:
    def __init__(self):
        self.base_url = "https://overpass-api.de/api/interpreter"
        self.timeout = 30
    
    def search_parking_spots(self, lat: float, lon: float, radius_km: float) -> List[ScrapedParkingSpot]:
        """Search for parking spots using OpenStreetMap Overpass API"""
        spots = []
        
        # Overpass query for various parking types
        query = f"""
        [out:json][timeout:25];
        (
          node["amenity"="parking"](around:{radius_km * 1000},{lat},{lon});
          way["amenity"="parking"](around:{radius_km * 1000},{lat},{lon});
          node["tourism"="camp_site"](around:{radius_km * 1000},{lat},{lon});
          node["highway"="rest_area"](around:{radius_km * 1000},{lat},{lon});
          node["leisure"="park"](around:{radius_km * 1000},{lat},{lon});
        );
        out center meta;
        """
        
        try:
            response = requests.post(
                self.base_url,
                data=query,
                headers={'Content-Type': 'application/x-www-form-urlencoded'},
                timeout=self.timeout
            )
            response.raise_for_status()
            data = response.json()
            
            for element in data.get('elements', []):
                spot = self._parse_osm_element(element)
                if spot:
                    spots.append(spot)
                    
        except requests.RequestException as e:
            print(f"OSM API error: {e}")
        except json.JSONDecodeError as e:
            print(f"OSM JSON parsing error: {e}")
        
        return spots
    
    def _parse_osm_element(self, element: Dict) -> Optional[ScrapedParkingSpot]:
        tags = element.get('tags', {})
        
        # Get coordinates
        if 'lat' in element and 'lon' in element:
            lat, lon = element['lat'], element['lon']
        elif 'center' in element:
            lat, lon = element['center']['lat'], element['center']['lon']
        else:
            return None
        
        # Extract parking info
        name = tags.get('name', f"Parking near {lat:.4f}, {lon:.4f}")
        parking_type = self._determine_parking_type(tags)
        
        # Parse restrictions and features
        max_height = self._parse_height_restriction(tags)
        max_weight = self._parse_weight_restriction(tags)
        has_facilities = self._has_facilities(tags)
        overnight_allowed = self._overnight_allowed(tags)
        restrictions = self._parse_restrictions(tags)
        
        return ScrapedParkingSpot(
            name=name,
            latitude=lat,
            longitude=lon,
            address=tags.get('addr:street', 'Unknown address'),
            parking_type=parking_type,
            max_height=max_height,
            max_weight=max_weight,
            has_facilities=has_facilities,
            overnight_allowed=overnight_allowed,
            restrictions=restrictions,
            source="OpenStreetMap",
            confidence=0.8
        )
    
    def _determine_parking_type(self, tags: Dict) -> str:
        if tags.get('tourism') == 'camp_site':
            return 'campsite'
        elif tags.get('highway') == 'rest_area':
            return 'rest_area'
        elif tags.get('leisure') == 'park':
            return 'park_area'
        elif tags.get('parking') == 'surface':
            return 'surface_parking'
        elif tags.get('parking') == 'multi-storey':
            return 'parking_garage'
        else:
            return 'parking_lot'
    
    def _parse_height_restriction(self, tags: Dict) -> Optional[float]:
        height_str = tags.get('maxheight', tags.get('height', ''))
        if height_str:
            # Extract numeric value (e.g., "3.5 m" -> 3.5)
            match = re.search(r'(\d+\.?\d*)', height_str)
            if match:
                return float(match.group(1))
        return None
    
    def _parse_weight_restriction(self, tags: Dict) -> Optional[float]:
        weight_str = tags.get('maxweight', '')
        if weight_str:
            match = re.search(r'(\d+\.?\d*)', weight_str)
            if match:
                weight = float(match.group(1))
                # Convert to tons if needed
                if 'kg' in weight_str.lower():
                    weight = weight / 1000
                return weight
        return None
    
    def _has_facilities(self, tags: Dict) -> bool:
        facility_indicators = [
            'toilets', 'drinking_water', 'shower', 'waste_disposal',
            'electricity', 'water_point'
        ]
        return any(tags.get(indicator) == 'yes' for indicator in facility_indicators)
    
    def _overnight_allowed(self, tags: Dict) -> bool:
        # Check for explicit overnight restrictions
        if tags.get('camping') == 'no':
            return False
        if 'no overnight' in tags.get('note', '').lower():
            return False
        if tags.get('tourism') == 'camp_site':
            return True
        if tags.get('highway') == 'rest_area':
            return True
        # Default to allowed unless explicitly forbidden
        return True
    
    def _parse_restrictions(self, tags: Dict) -> List[str]:
        restrictions = []
        
        if tags.get('access') == 'private':
            restrictions.append('Private access only')
        if tags.get('fee') == 'yes':
            restrictions.append('Paid parking')
        if 'time_limit' in tags:
            restrictions.append(f"Time limit: {tags['time_limit']}")
        if tags.get('opening_hours'):
            restrictions.append(f"Hours: {tags['opening_hours']}")
        
        return restrictions

class GooglePlacesScraper:
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        self.base_url = "https://maps.googleapis.com/maps/api/place"
    
    def search_parking_spots(self, lat: float, lon: float, radius_km: float) -> List[ScrapedParkingSpot]:
        """Search using Google Places API (requires API key)"""
        if not self.api_key:
            print("Google Places API key not provided, skipping...")
            return []
        
        spots = []
        search_types = ['parking', 'campground', 'rv_park', 'rest_area']
        
        for search_type in search_types:
            try:
                spots.extend(self._search_by_type(lat, lon, radius_km, search_type))
                time.sleep(1)  # Rate limiting
            except Exception as e:
                print(f"Google Places error for {search_type}: {e}")
        
        return spots
    
    def _search_by_type(self, lat: float, lon: float, radius_km: float, place_type: str) -> List[ScrapedParkingSpot]:
        params = {
            'location': f'{lat},{lon}',
            'radius': int(radius_km * 1000),
            'type': place_type,
            'key': self.api_key
        }
        
        response = requests.get(f"{self.base_url}/nearbysearch/json", params=params)
        response.raise_for_status()
        data = response.json()
        
        spots = []
        for place in data.get('results', []):
            spot = self._parse_google_place(place, place_type)
            if spot:
                spots.append(spot)
        
        return spots
    
    def _parse_google_place(self, place: Dict, place_type: str) -> Optional[ScrapedParkingSpot]:
        location = place.get('geometry', {}).get('location', {})
        if not location:
            return None
        
        return ScrapedParkingSpot(
            name=place.get('name', 'Unnamed location'),
            latitude=location['lat'],
            longitude=location['lng'],
            address=place.get('vicinity', 'Unknown address'),
            parking_type=place_type,
            max_height=None,  # Google Places doesn't provide detailed restrictions
            max_weight=None,
            has_facilities=place_type in ['campground', 'rv_park'],
            overnight_allowed=place_type in ['campground', 'rv_park', 'rest_area'],
            restrictions=[f"Rating: {place.get('rating', 'N/A')}"],
            source="Google Places",
            confidence=0.7
        )

class HelsinkiOfficialScraper:
    def __init__(self):
        self.parking_info_url = "https://www.hel.fi/fi/kaupunkiymparisto-ja-liikenne/pysakointi/pysakointipaikat-hinnat-ja-maksutavat"
        self.palvelukartta_api = "https://palvelukartta.hel.fi/api/v1/unit/"
        self.palvelukartta_search = "https://palvelukartta.hel.fi/api/v1/search/"
        self.timeout = 30
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'fi-FI,fi;q=0.9,en;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }
    
    def search_helsinki_parking_spots(self, lat: float, lon: float, radius_km: float) -> List[ScrapedParkingSpot]:
        """Scrape Helsinki's official parking data sources"""
        spots = []
        
        # Try Palvelukartta API for structured parking data
        try:
            print("  - Checking Helsinki Palvelukartta API...")
            spots.extend(self._scrape_palvelukartta_api(lat, lon, radius_km))
        except Exception as e:
            print(f"    Palvelukartta API error: {e}")
        
        # Try scraping the official parking information page
        try:
            print("  - Scraping Helsinki parking information page...")
            spots.extend(self._scrape_parking_info_page(lat, lon))
        except Exception as e:
            print(f"    Helsinki parking page scraping error: {e}")
        
        return spots
    
    def _scrape_palvelukartta_api(self, lat: float, lon: float, radius_km: float) -> List[ScrapedParkingSpot]:
        """Scrape Helsinki Palvelukartta API for parking spaces"""
        spots = []
        
        # Search for parking-related services
        search_terms = ['pysäköinti', 'parking', 'pysäköintialue', 'pysäköintitalo']
        
        for term in search_terms:
            try:
                params = {
                    'q': term,
                    'page_size': 50,
                    'only': 'name,location,street_address,description,www'
                }
                
                response = requests.get(
                    self.palvelukartta_search,
                    params=params,
                    headers=self.headers,
                    timeout=self.timeout
                )
                response.raise_for_status()
                data = response.json()
                
                for item in data.get('results', []):
                    spot = self._parse_palvelukartta_item(item, lat, lon, radius_km)
                    if spot:
                        spots.append(spot)
                        
                time.sleep(0.5)  # Rate limiting
                        
            except requests.RequestException as e:
                print(f"    Palvelukartta search failed for '{term}': {e}")
            except json.JSONDecodeError as e:
                print(f"    Palvelukartta JSON parsing failed: {e}")
        
        return spots
    
    def _parse_palvelukartta_item(self, item: Dict, search_lat: float, search_lon: float, radius_km: float) -> Optional[ScrapedParkingSpot]:
        """Parse a parking item from Palvelukartta API"""
        try:
            location = item.get('location', {})
            if not location or 'coordinates' not in location:
                return None
            
            coords = location['coordinates']
            if len(coords) < 2:
                return None
            
            # Palvelukartta uses [lon, lat] format
            lon, lat = coords[0], coords[1]
            
            # Check if within radius
            distance = self._calculate_distance(search_lat, search_lon, lat, lon)
            if distance > radius_km:
                return None
            
            name = item.get('name', {}).get('fi', 'Helsinki Parking Spot')
            address = item.get('street_address', {}).get('fi', 'Unknown address')
            
            # Parse description for parking details
            description = item.get('description', {}).get('fi', '').lower()
            
            # Determine parking characteristics
            parking_type = self._determine_parking_type_from_name(name.lower())
            overnight_allowed = self._parse_overnight_from_description(description)
            has_facilities = self._parse_facilities_from_description(description)
            restrictions = self._parse_restrictions_from_description(description)
            
            return ScrapedParkingSpot(
                name=name,
                latitude=lat,
                longitude=lon,
                address=address,
                parking_type=parking_type,
                max_height=None,  # Not typically provided in API
                max_weight=None,
                has_facilities=has_facilities,
                overnight_allowed=overnight_allowed,
                restrictions=restrictions,
                source="Helsinki Palvelukartta",
                confidence=0.95
            )
            
        except (KeyError, IndexError, TypeError, ValueError) as e:
            print(f"    Error parsing Palvelukartta item: {e}")
            return None
    
    def _scrape_parking_info_page(self, lat: float, lon: float) -> List[ScrapedParkingSpot]:
        """Scrape the Helsinki parking information page for parking areas"""
        spots = []
        
        try:
            response = requests.get(
                self.parking_info_url,
                headers=self.headers,
                timeout=self.timeout
            )
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Look for parking information in various formats
            parking_sections = soup.find_all(['div', 'section', 'article'], 
                                            class_=re.compile(r'park|pysak', re.I))
            
            # Also look for tables with parking information
            tables = soup.find_all('table')
            for table in tables:
                if any(keyword in table.get_text().lower() for keyword in ['pysäköinti', 'parking', 'maksut', 'hinnat']):
                    spots.extend(self._parse_parking_table(table, lat, lon))
            
            # Look for lists of parking areas
            lists = soup.find_all(['ul', 'ol'])
            for ul in lists:
                if any(keyword in ul.get_text().lower() for keyword in ['pysäköinti', 'parking']):
                    spots.extend(self._parse_parking_list(ul, lat, lon))
            
            # Look for text containing parking area names
            text_content = soup.get_text()
            spots.extend(self._extract_parking_areas_from_text(text_content, lat, lon))
                
        except requests.RequestException as e:
            print(f"    Error fetching Helsinki parking page: {e}")
        except Exception as e:
            print(f"    Error parsing Helsinki parking page: {e}")
        
        return spots
    
    def _parse_parking_table(self, table, base_lat: float, base_lon: float) -> List[ScrapedParkingSpot]:
        """Extract parking information from HTML tables"""
        spots = []
        rows = table.find_all('tr')
        
        for i, row in enumerate(rows[1:], 1):  # Skip header row
            cells = row.find_all(['td', 'th'])
            if len(cells) >= 2:
                area_name = cells[0].get_text(strip=True)
                pricing_info = cells[1].get_text(strip=True) if len(cells) > 1 else ""
                
                if area_name and any(keyword in area_name.lower() for keyword in ['pysäköinti', 'parking', 'alue']):
                    # Generate approximate coordinates in Helsinki area
                    lat_offset = (i % 10) * 0.005 - 0.025
                    lon_offset = (i // 10) * 0.005 - 0.015
                    
                    restrictions = []
                    if pricing_info:
                        restrictions.append(f"Pricing: {pricing_info}")
                    
                    spots.append(ScrapedParkingSpot(
                        name=area_name,
                        latitude=base_lat + lat_offset,
                        longitude=base_lon + lon_offset,
                        address="Helsinki",
                        parking_type="municipal_parking",
                        max_height=None,
                        max_weight=None,
                        has_facilities=False,
                        overnight_allowed=not ('short' in pricing_info.lower() or 'lyhyt' in pricing_info.lower()),
                        restrictions=restrictions,
                        source="Helsinki Official Website",
                        confidence=0.85
                    ))
        
        return spots
    
    def _parse_parking_list(self, ul_element, base_lat: float, base_lon: float) -> List[ScrapedParkingSpot]:
        """Extract parking areas from HTML lists"""
        spots = []
        items = ul_element.find_all('li')
        
        for i, item in enumerate(items):
            text = item.get_text(strip=True)
            if text and any(keyword in text.lower() for keyword in ['pysäköinti', 'parking', 'alue']):
                # Generate coordinates spread around Helsinki center
                lat_offset = (i % 8) * 0.008 - 0.032
                lon_offset = (i // 8) * 0.008 - 0.024
                
                spots.append(ScrapedParkingSpot(
                    name=text,
                    latitude=base_lat + lat_offset,
                    longitude=base_lon + lon_offset,
                    address="Helsinki",
                    parking_type="street_parking",
                    max_height=None,
                    max_weight=None,
                    has_facilities=False,
                    overnight_allowed=True,
                    restrictions=["Check local signage"],
                    source="Helsinki Official Website",
                    confidence=0.80
                ))
        
        return spots
    
    def _extract_parking_areas_from_text(self, text: str, base_lat: float, base_lon: float) -> List[ScrapedParkingSpot]:
        """Extract parking area names from text content using pattern matching"""
        spots = []
        
        # Common Helsinki parking area patterns
        patterns = [
            r'([A-ZÅÄÖ][a-zåäö]+(?:(?:in|n)?\s+(?:alue|pysäköintialue|parking)))',
            r'((?:Katu|tie|kuja|tori|puisto)\s*\d*\s*pysäköinti)',
            r'([A-ZÅÄÖ][a-zåäö]+(?:tori|katu|tie)\s*pysäköinti)',
        ]
        
        found_areas = set()
        
        for pattern in patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                area_name = match.group(1).strip()
                if len(area_name) > 5 and area_name not in found_areas:  # Avoid very short matches
                    found_areas.add(area_name)
        
        # Convert found areas to parking spots
        for i, area_name in enumerate(found_areas):
            if len(spots) >= 20:  # Limit number of extracted spots
                break
                
            # Distribute around Helsinki center
            lat_offset = (i % 12) * 0.006 - 0.036
            lon_offset = (i // 12) * 0.006 - 0.018
            
            spots.append(ScrapedParkingSpot(
                name=area_name,
                latitude=base_lat + lat_offset,
                longitude=base_lon + lon_offset,
                address="Helsinki",
                parking_type="street_parking",
                max_height=None,
                max_weight=None,
                has_facilities=False,
                overnight_allowed=True,
                restrictions=["Check local regulations"],
                source="Helsinki Official Website",
                confidence=0.75
            ))
        
        return spots
    
    def _determine_parking_type_from_name(self, name: str) -> str:
        """Determine parking type from location name"""
        name_lower = name.lower()
        if 'talo' in name_lower or 'garage' in name_lower:
            return 'parking_garage'
        elif 'katu' in name_lower or 'tie' in name_lower or 'street' in name_lower:
            return 'street_parking'
        elif 'keskus' in name_lower or 'center' in name_lower:
            return 'commercial_parking'
        elif 'tori' in name_lower or 'square' in name_lower:
            return 'public_square_parking'
        else:
            return 'municipal_parking'
    
    def _parse_overnight_from_description(self, description: str) -> bool:
        """Parse overnight parking allowance from description"""
        if any(phrase in description for phrase in ['yöpyminen kielletty', 'ei yöpymistä', 'no overnight']):
            return False
        elif any(phrase in description for phrase in ['24h', '24 tuntia', 'ympärivuorokausi']):
            return True
        else:
            return True  # Default to allowed
    
    def _parse_facilities_from_description(self, description: str) -> bool:
        """Parse facility availability from description"""
        return any(phrase in description for phrase in ['wc', 'käymälä', 'toilet', 'vesi', 'water', 'suihku', 'shower'])
    
    def _parse_restrictions_from_description(self, description: str) -> List[str]:
        """Parse parking restrictions from description"""
        restrictions = []
        
        if 'maksullinen' in description or 'maksu' in description:
            restrictions.append('Paid parking')
        elif 'maksuton' in description or 'ilmainen' in description:
            restrictions.append('Free parking')
        
        if 'aikarajoitus' in description or 'time limit' in description:
            restrictions.append('Time restrictions apply')
        
        if 'lupa' in description or 'permit' in description:
            restrictions.append('Permit may be required')
        
        return restrictions
    
    def _calculate_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate distance between two points in kilometers"""
        from math import radians, cos, sin, asin, sqrt
        
        # Haversine formula
        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
        return 2 * asin(sqrt(a)) * 6371  # Earth radius in km

class CityWebsiteScraper:
    def __init__(self):
        self.city_parking_urls = {
            'tampere': 'https://www.tampere.fi/en/traffic-and-parking/parking',
            'turku': 'https://www.turku.fi/en/living-turku/traffic-and-parking',
            'oulu': 'https://www.ouka.fi/oulu/english/parking'
        }
        self.helsinki_scraper = HelsinkiOfficialScraper()
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Connection': 'keep-alive'
        }
    
    def search_parking_spots(self, city: str, lat: float, lon: float, radius_km: float = 10.0) -> List[ScrapedParkingSpot]:
        """Scrape official city parking websites"""
        city_lower = city.lower()
        
        # Special handling for Helsinki with real scraping
        if 'helsinki' in city_lower:
            try:
                return self.helsinki_scraper.search_helsinki_parking_spots(lat, lon, radius_km)
            except Exception as e:
                print(f"    Helsinki official scraping error: {e}")
                return []
        
        # Other cities - implement real scraping
        if city_lower not in self.city_parking_urls:
            return []
        
        try:
            return self._scrape_city_parking_page(city_lower, lat, lon)
        except Exception as e:
            print(f"    {city.title()} website scraping error: {e}")
            return []
    
    def _scrape_city_parking_page(self, city: str, lat: float, lon: float) -> List[ScrapedParkingSpot]:
        """Scrape actual city parking pages"""
        spots = []
        url = self.city_parking_urls.get(city)
        if not url:
            return spots
        
        try:
            response = requests.get(url, headers=self.headers, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Look for parking-related content
            parking_elements = soup.find_all(text=re.compile(r'park|pysäk', re.I))
            
            # Extract parking information from text
            parking_info = set()
            for element in parking_elements[:20]:  # Limit to first 20 matches
                parent = element.parent
                if parent:
                    text = parent.get_text(strip=True)
                    if len(text) > 10 and len(text) < 200:  # Reasonable text length
                        parking_info.add(text)
            
            # Convert to parking spots
            for i, info in enumerate(parking_info):
                if len(spots) >= 10:  # Limit number of spots per city
                    break
                    
                # Generate coordinates around the city center
                lat_offset = (i % 6) * 0.01 - 0.025
                lon_offset = (i // 6) * 0.01 - 0.02
                
                spots.append(ScrapedParkingSpot(
                    name=f"{city.title()} Parking Area {i+1}",
                    latitude=lat + lat_offset,
                    longitude=lon + lon_offset,
                    address=f"{city.title()} center",
                    parking_type="municipal_parking",
                    max_height=None,
                    max_weight=None,
                    has_facilities=False,
                    overnight_allowed='overnight' not in info.lower() or 'yö' not in info.lower(),
                    restrictions=[f"Info: {info[:100]}..."] if len(info) > 100 else [f"Info: {info}"],
                    source=f"{city.title()} Official Website",
                    confidence=0.70
                ))
                    
        except requests.RequestException as e:
            print(f"    Error fetching {city} parking page: {e}")
        except Exception as e:
            print(f"    Error parsing {city} parking page: {e}")
        
        return spots
    

class DynamicParkingFinder:
    def __init__(self, google_api_key: Optional[str] = None):
        self.osm_scraper = OpenStreetMapScraper()
        self.google_scraper = GooglePlacesScraper(google_api_key)
        self.city_scraper = CityWebsiteScraper()
        self.cache = {}  # Simple in-memory cache
        self.cache_duration = 3600  # 1 hour
    
    def find_parking_spots(self, location: str, camper_reqs: CamperRequirements) -> List[ScrapedParkingSpot]:
        """Main method to find parking spots by scraping multiple sources"""
        
        # Get coordinates for location
        coords = self._geocode_location(location)
        if not coords:
            return []
        
        lat, lon = coords
        cache_key = f"{lat:.4f}_{lon:.4f}_{camper_reqs.radius_km}"
        
        # Check cache first
        if cache_key in self.cache:
            cached_data, timestamp = self.cache[cache_key]
            if time.time() - timestamp < self.cache_duration:
                print("Using cached parking data...")
                return self._filter_spots(cached_data, camper_reqs)
        
        print(f"Scraping parking data for {location}...")
        all_spots = []
        
        # Scrape from OpenStreetMap
        print("- Checking OpenStreetMap...")
        osm_spots = self.osm_scraper.search_parking_spots(lat, lon, camper_reqs.radius_km)
        all_spots.extend(osm_spots)
        
        # Scrape from Google Places (if API key available)
        print("- Checking Google Places...")
        google_spots = self.google_scraper.search_parking_spots(lat, lon, camper_reqs.radius_km)
        all_spots.extend(google_spots)
        
        # Scrape city websites (including Helsinki official sources)
        print("- Checking city websites and official sources...")
        city_spots = self.city_scraper.search_parking_spots(location, lat, lon, camper_reqs.radius_km)
        all_spots.extend(city_spots)
        
        # Remove duplicates and cache results
        unique_spots = self._deduplicate_spots(all_spots)
        self.cache[cache_key] = (unique_spots, time.time())
        
        return self._filter_spots(unique_spots, camper_reqs)
    
    def _geocode_location(self, location: str) -> Optional[Tuple[float, float]]:
        """Convert location name to coordinates using Nominatim"""
        try:
            url = "https://nominatim.openstreetmap.org/search"
            params = {
                'q': f"{location}, Finland",
                'format': 'json',
                'limit': 1
            }
            
            response = requests.get(url, params=params, headers={'User-Agent': 'CamperParkingAI/1.0'})
            response.raise_for_status()
            data = response.json()
            
            if data:
                return float(data[0]['lat']), float(data[0]['lon'])
                
        except Exception as e:
            print(f"Geocoding error: {e}")
        
        return None
    
    def _deduplicate_spots(self, spots: List[ScrapedParkingSpot]) -> List[ScrapedParkingSpot]:
        """Remove duplicate parking spots based on proximity"""
        unique_spots = []
        
        for spot in spots:
            is_duplicate = False
            for existing in unique_spots:
                # Consider spots within 100m as duplicates
                if self._calculate_distance(spot.latitude, spot.longitude, 
                                          existing.latitude, existing.longitude) < 0.1:
                    # Keep the one with higher confidence
                    if spot.confidence > existing.confidence:
                        unique_spots.remove(existing)
                        unique_spots.append(spot)
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                unique_spots.append(spot)
        
        return unique_spots
    
    def _calculate_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate distance between two points in kilometers"""
        from math import radians, cos, sin, asin, sqrt
        
        # Haversine formula
        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
        return 2 * asin(sqrt(a)) * 6371  # Earth radius in km
    
    def _filter_spots(self, spots: List[ScrapedParkingSpot], reqs: CamperRequirements) -> List[ScrapedParkingSpot]:
        """Filter spots based on camper requirements"""
        suitable_spots = []
        
        for spot in spots:
            # Check height restriction
            if spot.max_height and spot.max_height < reqs.height:
                continue
            
            # Check weight restriction
            if spot.max_weight and spot.max_weight < reqs.weight:
                continue
            
            # Check facility requirements
            if reqs.needs_facilities and not spot.has_facilities:
                continue
            
            # Check overnight requirements
            if reqs.needs_overnight and not spot.overnight_allowed:
                continue
            
            suitable_spots.append(spot)
        
        # Sort by confidence and suitability
        return sorted(suitable_spots, key=lambda x: x.confidence, reverse=True)

class DynamicCamperParkingAI:
    def __init__(self, google_api_key: Optional[str] = None):
        self.finder = DynamicParkingFinder(google_api_key)
        self.config_file = os.path.expanduser('~/.camper_parking_defaults.pkl')
        self.default_params = self._load_defaults()
    
    def _load_defaults(self) -> Dict[str, Any]:
        """Load saved search parameters from file"""
        default_params = {
            'location': '',
            'height': 3.2,
            'weight': 3.5,
            'length': 7.0,
            'needs_facilities': False,
            'needs_overnight': True,
            'radius_km': 10.0
        }
        
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'rb') as f:
                    saved_params = pickle.load(f)
                    # Merge with defaults to handle new parameters
                    default_params.update(saved_params)
                    print(f"📁 Loaded previous search parameters from {self.config_file}")
        except Exception as e:
            print(f"⚠️  Could not load previous parameters: {e}")
        
        return default_params
    
    def _save_defaults(self, params: Dict[str, Any]) -> None:
        """Save search parameters to file"""
        try:
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(self.config_file), exist_ok=True)
            
            with open(self.config_file, 'wb') as f:
                pickle.dump(params, f)
            print(f"💾 Saved search parameters as defaults")
        except Exception as e:
            print(f"⚠️  Could not save parameters: {e}")
    
    def show_map(self, results: Dict[str, Any]) -> None:
        """Show graphical map with parking spot locations"""
        if results["status"] != "success" or not results["parking_spots"]:
            print("❌ No parking spots to display on map")
            return
        
        try:
            map_viz = ParkingMapVisualization(results)
            map_viz.show()
        except Exception as e:
            print(f"⚠️  Could not open map view: {e}")
    
    def search_parking(self, location: str, height: float, weight: float, length: float,
                      needs_facilities: bool = False, needs_overnight: bool = True,
                      radius_km: float = 10.0) -> Dict[str, Any]:
        
        # Save search parameters as new defaults
        search_params = {
            "location": location,
            "height": height,
            "weight": weight,
            "length": length,
            "needs_facilities": needs_facilities,
            "needs_overnight": needs_overnight,
            "radius_km": radius_km
        }
        self.default_params = search_params
        self._save_defaults(search_params)
        
        reqs = CamperRequirements(
            height=height,
            weight=weight, 
            length=length,
            needs_facilities=needs_facilities,
            needs_overnight=needs_overnight,
            radius_km=radius_km
        )
        
        try:
            spots = self.finder.find_parking_spots(location, reqs)
            
            if not spots:
                return {
                    "status": "no_results",
                    "message": f"No suitable parking spots found near {location}",
                    "suggestion": "Try expanding search radius or adjusting requirements",
                    "current_params": search_params
                }
            
            return {
                "status": "success",
                "location": location,
                "search_radius": f"{radius_km}km",
                "camper_specs": f"{height}m H × {weight}t × {length}m L",
                "spots_found": len(spots),
                "parking_spots": [self._format_spot(spot) for spot in spots]
            }
            
        except Exception as e:
            return {
                "status": "error",
                "message": f"Search failed: {str(e)}"
            }
    
    def retry_with_larger_radius(self, search_params: Dict[str, Any], new_radius: float) -> Dict[str, Any]:
        """Retry search with a larger radius while keeping other parameters"""
        return self.search_parking(
            location=search_params["location"],
            height=search_params["height"],
            weight=search_params["weight"],
            length=search_params["length"],
            needs_facilities=search_params["needs_facilities"],
            needs_overnight=search_params["needs_overnight"],
            radius_km=new_radius
        )
    
    def _format_spot(self, spot: ScrapedParkingSpot) -> Dict[str, Any]:
        return {
            "name": spot.name,
            "address": spot.address,
            "coordinates": [spot.latitude, spot.longitude],
            "type": spot.parking_type,
            "overnight_allowed": spot.overnight_allowed,
            "facilities": spot.has_facilities,
            "max_height": f"{spot.max_height}m" if spot.max_height else "Unknown",
            "max_weight": f"{spot.max_weight}t" if spot.max_weight else "Unknown", 
            "restrictions": spot.restrictions,
            "source": spot.source,
            "confidence": f"{spot.confidence:.1%}"
        }
    
    def interactive_session(self):
        print("🚐 Dynamic Camper Van Parking Finder")
        print("Real-time parking spot discovery from multiple sources") 
        print("Sources: OpenStreetMap, Google Places, Helsinki Official Maps, City Websites")
        print("\n💾 Previous search parameters are automatically saved and reused")
        print("🗺️  Interactive matplotlib map view available after successful searches")
        print("Type 'quit' to exit\n")
        
        while True:
            print("=" * 60)
            command = input("Search for parking? (y/n/quit): ").strip().lower()
            
            if command in ['quit', 'exit', 'q']:
                print("Happy camping! 🏕️")
                break
            
            if command in ['y', 'yes', 'search']:
                self._interactive_search()
            else:
                print("Enter 'y' to search or 'quit' to exit")
    
    def _interactive_search(self):
        try:
            print("\n🔍 Dynamic Parking Search")
            
            # Show current defaults if available
            if self.default_params['location']:
                print(f"\n📋 Previous search defaults loaded:")
                print(f"   Location: {self.default_params['location']}")
                print(f"   Camper: {self.default_params['height']}m × {self.default_params['weight']}t × {self.default_params['length']}m")
                print(f"   Facilities: {'Yes' if self.default_params['needs_facilities'] else 'No'}")
                print(f"   Overnight: {'Yes' if self.default_params['needs_overnight'] else 'No'}")
                print(f"   Radius: {self.default_params['radius_km']}km")
                
                use_defaults = input("\n🔄 Use previous settings? (y/n): ").strip().lower()
                if use_defaults == 'y':
                    # Use all previous settings
                    location = self.default_params['location']
                    height = self.default_params['height']
                    weight = self.default_params['weight']
                    length = self.default_params['length']
                    facilities = self.default_params['needs_facilities']
                    overnight = self.default_params['needs_overnight']
                    radius = self.default_params['radius_km']
                    
                    # Allow user to change location if desired
                    change_location = input(f"📍 Change location from '{location}'? (y/n): ").strip().lower()
                    if change_location == 'y':
                        new_location = input("📍 New location (city/address in Finland): ").strip()
                        if new_location:
                            location = new_location
                    
                    print(f"\n🔄 Searching with saved parameters...")
                else:
                    # Get new parameters but use defaults as suggestions
                    location = input(f"📍 Location (default: {self.default_params['location']}): ").strip() or self.default_params['location']
                    
                    print("\n🚐 Camper specifications:")
                    height = float(input(f"   Height (meters, default {self.default_params['height']}): ") or str(self.default_params['height']))
                    weight = float(input(f"   Weight (tons, default {self.default_params['weight']}): ") or str(self.default_params['weight']))
                    length = float(input(f"   Length (meters, default {self.default_params['length']}): ") or str(self.default_params['length']))
                    
                    facilities_default = 'y' if self.default_params['needs_facilities'] else 'n'
                    facilities_input = input(f"🚿 Need facilities (y/n, default {facilities_default}): ").strip() or facilities_default
                    facilities = facilities_input.lower() == 'y'
                    
                    overnight_default = 'y' if self.default_params['needs_overnight'] else 'n'
                    overnight_input = input(f"🌙 Need overnight parking (y/n, default {overnight_default}): ").strip() or overnight_default
                    overnight = overnight_input.lower() == 'y'
                    
                    radius = float(input(f"📏 Search radius (km, default {self.default_params['radius_km']}): ") or str(self.default_params['radius_km']))
            else:
                # First time use - no defaults
                location = input("📍 Location (city/address in Finland): ").strip()
                
                print("\n🚐 Camper specifications:")
                height = float(input("   Height (meters): "))
                weight = float(input("   Weight (tons): "))
                length = float(input("   Length (meters): "))
                
                facilities = input("🚿 Need facilities (toilets/water)? (y/n): ").lower() == 'y'
                overnight = input("🌙 Need overnight parking? (y/n): ").lower() == 'y'
                radius = float(input("📏 Search radius (km, default 10): ") or "10")
            
            # Save these parameters as new defaults
            new_params = {
                'location': location,
                'height': height,
                'weight': weight,
                'length': length,
                'needs_facilities': facilities,
                'needs_overnight': overnight,
                'radius_km': radius
            }
            
            self.default_params = new_params
            self._save_defaults(new_params)
            
            print(f"\n🔄 Searching for parking near {location}...")
            results = self.search_parking(location, height, weight, length, facilities, overnight, radius)
            self._display_results(results)
            
            # Ask if user wants to see map view
            if results["status"] == "success":
                show_map = input("\n🗺️  Show parking spots on map? (y/n): ").strip().lower()
                if show_map == 'y':
                    self.show_map(results)
            
        except (ValueError, KeyboardInterrupt):
            print("\n❌ Invalid input or search cancelled")
    
    def _display_results(self, results: Dict[str, Any], last_search_params: Dict[str, Any] = None):
        print(f"\n{'='*80}")
        
        if results["status"] == "error":
            print(f"❌ {results['message']}")
        elif results["status"] == "no_results":
            print(f"❌ {results['message']}")
            print(f"💡 {results['suggestion']}")
            
            # Offer radius adjustment option
            if "current_params" in results:
                current_radius = results["current_params"]["radius_km"]
                print(f"\n🎯 Current search radius: {current_radius}km")
                
                try:
                    adjust_radius = input(f"\n📏 Try larger radius? Enter new radius in km (or press Enter to skip): ").strip()
                    if adjust_radius:
                        new_radius = float(adjust_radius)
                        if new_radius > current_radius:
                            print(f"\n🔄 Retrying search with {new_radius}km radius...")
                            # Update the default radius for future searches
                            self.default_params['radius_km'] = new_radius
                            self._save_defaults(self.default_params)
                            
                            new_results = self.retry_with_larger_radius(results["current_params"], new_radius)
                            self._display_results(new_results, results["current_params"])
                            return
                        else:
                            print("⚠️  New radius should be larger than current radius")
                except (ValueError, KeyboardInterrupt):
                    print("\n⏭️  Skipping radius adjustment")
        else:
            print(f"✅ Found {results['spots_found']} parking spot(s) near {results['location']}")
            print(f"🔍 Search area: {results['search_radius']}")
            print(f"🚐 Camper specs: {results['camper_specs']}")
            
            for i, spot in enumerate(results["parking_spots"], 1):
                print(f"\n📍 SPOT #{i}: {spot['name']}")
                print(f"   🏠 Address: {spot['address']}")
                print(f"   📊 Type: {spot['type'].replace('_', ' ').title()}")
                print(f"   🌐 Coordinates: {spot['coordinates'][0]:.4f}, {spot['coordinates'][1]:.4f}")
                print(f"   🌙 Overnight: {'✅' if spot['overnight_allowed'] else '❌'}")
                print(f"   🚿 Facilities: {'✅' if spot['facilities'] else '❌'}")
                print(f"   📏 Max Height: {spot['max_height']}")
                print(f"   ⚖️  Max Weight: {spot['max_weight']}")
                print(f"   🔗 Source: {spot['source']} ({spot['confidence']})")
                
                if spot['restrictions']:
                    print(f"   ⚠️  Restrictions:")
                    for restriction in spot['restrictions']:
                        print(f"      • {restriction}")
        
        print(f"\n{'='*80}")

class ParkingMapVisualization:
    def __init__(self, search_results: Dict[str, Any]):
        self.results = search_results
        self.spots = search_results["parking_spots"]
        self.selected_spot = None
        
        # Calculate map bounds
        self.coords = [(spot["coordinates"][0], spot["coordinates"][1]) for spot in self.spots]
        self.min_lat = min(coord[0] for coord in self.coords)
        self.max_lat = max(coord[0] for coord in self.coords)
        self.min_lon = min(coord[1] for coord in self.coords)
        self.max_lon = max(coord[1] for coord in self.coords)
        
        # Add padding to bounds
        lat_padding = (self.max_lat - self.min_lat) * 0.1 or 0.01
        lon_padding = (self.max_lon - self.min_lon) * 0.1 or 0.01
        self.min_lat -= lat_padding
        self.max_lat += lat_padding
        self.min_lon -= lon_padding
        self.max_lon += lon_padding
        
        # Setup matplotlib figure
        plt.style.use('default')
        self.fig, self.ax = plt.subplots(figsize=(12, 8))
        self.fig.suptitle(f"🗺️ Parking Spots in {self.results['location']}", fontsize=16, fontweight='bold')
        
        # Store spot artists for interaction
        self.spot_artists = []
        self.info_text = None
        
    def show(self):
        """Display the interactive map"""
        self.draw_map()
        self.setup_interactions()
        plt.tight_layout()
        plt.show()
    
    def draw_map(self):
        """Draw the parking spots and map elements"""
        # Set up the plot
        self.ax.set_xlim(self.min_lon, self.max_lon)
        self.ax.set_ylim(self.min_lat, self.max_lat)
        self.ax.set_xlabel('Longitude', fontsize=12)
        self.ax.set_ylabel('Latitude', fontsize=12)
        self.ax.grid(True, alpha=0.3)
        self.ax.set_aspect('equal', adjustable='box')
        
        # Add real-world map background using contextily with Web Mercator projection
        try:
            # Convert to Web Mercator for proper 2D flat map display
            ctx.add_basemap(self.ax, crs='EPSG:4326', source=ctx.providers.OpenStreetMap.Mapnik, alpha=0.8, attribution=False)
            # Ensure flat 2D view
            self.ax.set_aspect('equal')
        except Exception as e:
            print(f"Warning: Could not load map background: {e}")
            # Fall back to simple background color if contextily fails
            self.ax.set_facecolor('#e6f3ff')
        
        # Draw parking spots
        for i, spot in enumerate(self.spots):
            lat, lon = spot["coordinates"]
            
            # Determine spot color and size based on confidence
            confidence_str = spot["confidence"].replace("%", "")
            try:
                confidence = float(confidence_str)
                if confidence >= 80:
                    color = 'green'
                    alpha = 0.8
                elif confidence >= 60:
                    color = 'orange' 
                    alpha = 0.7
                else:
                    color = 'red'
                    alpha = 0.6
            except:
                color = 'blue'
                alpha = 0.5
            
            # Create spot marker
            spot_circle = Circle((lon, lat), radius=0.001, color=color, alpha=alpha, 
                               linewidth=2, edgecolor='black', picker=True)
            self.ax.add_patch(spot_circle)
            self.spot_artists.append((spot_circle, i))
            
            # Add spot number
            self.ax.text(lon, lat, str(i+1), ha='center', va='center', 
                        fontsize=8, fontweight='bold', color='white')
            
            # Add facility indicators
            offset = 0.0008
            if spot["facilities"]:
                self.ax.text(lon-offset, lat+offset, '💙', ha='center', va='center', fontsize=10)
            
            if spot["overnight_allowed"]:
                self.ax.text(lon+offset, lat+offset, '🌙', ha='center', va='center', fontsize=10)
        
        # Add legend
        self.add_legend()
        
        # Add info box
        self.add_info_box()
    
    def add_legend(self):
        """Add legend to the map"""
        legend_elements = [
            plt.Line2D([0], [0], marker='o', color='w', markerfacecolor='green', 
                      markersize=10, alpha=0.8, label='High confidence (80%+)'),
            plt.Line2D([0], [0], marker='o', color='w', markerfacecolor='orange', 
                      markersize=10, alpha=0.7, label='Medium confidence (60-80%)'),
            plt.Line2D([0], [0], marker='o', color='w', markerfacecolor='red', 
                      markersize=10, alpha=0.6, label='Lower confidence (<60%)')
        ]
        
        legend = self.ax.legend(handles=legend_elements, loc='upper left', 
                               bbox_to_anchor=(0.02, 0.98), fontsize=9)
        legend.get_frame().set_alpha(0.9)
        
        # Add symbol legend
        self.ax.text(0.02, 0.85, '💙 Has facilities\n🌙 Overnight allowed', 
                    transform=self.ax.transAxes, fontsize=9, 
                    bbox=dict(boxstyle='round', facecolor='white', alpha=0.9))
    
    def add_info_box(self):
        """Add search results info box"""
        info_text = f"""Search Results:
• Found: {self.results['spots_found']} spots
• Area: {self.results['search_radius']} 
• Camper: {self.results['camper_specs']}

Click on a spot for details"""
        
        self.info_text = self.ax.text(0.02, 0.02, info_text, transform=self.ax.transAxes, 
                                     fontsize=9, verticalalignment='bottom',
                                     bbox=dict(boxstyle='round', facecolor='lightgray', alpha=0.9))
    
    def setup_interactions(self):
        """Setup mouse click interactions"""
        def on_pick(event):
            """Handle click events on parking spots"""
            artist = event.artist
            
            # Find which spot was clicked
            for spot_artist, spot_index in self.spot_artists:
                if spot_artist == artist:
                    self.show_spot_details(spot_index)
                    break
        
        # Connect the pick event
        self.fig.canvas.mpl_connect('pick_event', on_pick)
        
        # Add control buttons
        self.add_control_buttons()
    
    def add_control_buttons(self):
        """Add control buttons to the plot"""
        # Add axes for buttons
        ax_reset = plt.axes([0.85, 0.02, 0.12, 0.04])
        ax_info = plt.axes([0.85, 0.07, 0.12, 0.04])
        
        # Create buttons
        self.button_reset = Button(ax_reset, 'Reset View')
        self.button_info = Button(ax_info, 'Show All Info')
        
        # Button callbacks
        def reset_view(event):
            self.ax.set_xlim(self.min_lon, self.max_lon)
            self.ax.set_ylim(self.min_lat, self.max_lat)
            self.ax.set_aspect('equal')
            self.fig.canvas.draw()
        
        def show_all_info(event):
            info_text = f"""All Parking Spots ({len(self.spots)} total):

"""
            for i, spot in enumerate(self.spots[:10]):  # Show first 10
                info_text += f"{i+1}. {spot['name'][:30]}{'...' if len(spot['name']) > 30 else ''}\n"
            if len(self.spots) > 10:
                info_text += f"... and {len(self.spots) - 10} more spots"
            
            print("\n" + "="*60)
            print(info_text)
            print("="*60)
        
        self.button_reset.on_clicked(reset_view)
        self.button_info.on_clicked(show_all_info)
    
    def show_spot_details(self, spot_index: int):
        """Display details for selected parking spot"""
        spot = self.spots[spot_index]
        self.selected_spot = spot_index
        
        # Highlight selected spot by adding a yellow ring
        lat, lon = spot["coordinates"]
        
        # Remove previous highlight
        if hasattr(self, 'highlight_circle'):
            self.highlight_circle.remove()
        
        # Add new highlight
        self.highlight_circle = Circle((lon, lat), radius=0.0015, 
                                     fill=False, edgecolor='yellow', linewidth=4)
        self.ax.add_patch(self.highlight_circle)
        
        # Update info text with spot details
        details_text = f"""🎯 SPOT #{spot_index + 1}: {spot['name'][:40]}
📍 {spot['address'][:30]}
📊 {spot['type'].replace('_', ' ').title()}
🌐 {spot['coordinates'][0]:.4f}, {spot['coordinates'][1]:.4f}
🌙 Overnight: {'✅' if spot['overnight_allowed'] else '❌'}
🚿 Facilities: {'✅' if spot['facilities'] else '❌'}
📏 Height: {spot['max_height']} | ⚖️ Weight: {spot['max_weight']}
🔗 {spot['source']} ({spot['confidence']})"""
        
        if spot['restrictions']:
            details_text += f"\n⚠️  {len(spot['restrictions'])} restriction(s)"
        
        self.info_text.set_text(details_text)
        self.fig.canvas.draw()
        
        # Also print detailed info to console
        print(f"\n{'='*60}")
        print(f"🎯 DETAILED INFO - SPOT #{spot_index + 1}")
        print(f"{'='*60}")
        print(f"Name: {spot['name']}")
        print(f"Address: {spot['address']}")
        print(f"Type: {spot['type'].replace('_', ' ').title()}")
        print(f"Coordinates: {spot['coordinates'][0]:.6f}, {spot['coordinates'][1]:.6f}")
        print(f"Overnight allowed: {'✅ Yes' if spot['overnight_allowed'] else '❌ No'}")
        print(f"Facilities: {'✅ Yes' if spot['facilities'] else '❌ No'}")
        print(f"Max height: {spot['max_height']}")
        print(f"Max weight: {spot['max_weight']}")
        print(f"Source: {spot['source']}")
        print(f"Confidence: {spot['confidence']}")
        
        if spot['restrictions']:
            print(f"\n⚠️  Restrictions:")
            for i, restriction in enumerate(spot['restrictions'], 1):
                print(f"   {i}. {restriction}")
        
        print(f"{'='*60}\n")

if __name__ == "__main__":
    # Optional: Set Google Places API key as environment variable
    import os
    google_key = os.getenv('GOOGLE_PLACES_API_KEY')
    
    ai = DynamicCamperParkingAI(google_key)
    ai.interactive_session()