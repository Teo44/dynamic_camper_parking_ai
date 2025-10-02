#!/usr/bin/env python3
"""
Test script to demonstrate the graphical map functionality
"""
import dynamic_camper_parking_ai as app

def test_map_gui():
    """Test the graphical map interface"""
    print("🗺️  Testing Graphical Map Interface")
    print("=====================================")
    
    # Create some test data that mimics real search results
    test_results = {
        "status": "success",
        "location": "Helsinki Test Area", 
        "search_radius": "5km",
        "camper_specs": "3.2m H × 3.5t × 7.0m L",
        "spots_found": 5,
        "parking_spots": [
            {
                "name": "Test Parking Spot 1",
                "address": "Helsinki Center",
                "coordinates": [60.1699, 24.9384],
                "type": "street_parking",
                "overnight_allowed": True,
                "facilities": True,
                "max_height": "3.5m",
                "max_weight": "7.5t",
                "restrictions": ["Free parking evenings", "Max 4 hours daytime"],
                "source": "Test Data",
                "confidence": "95.0%"
            },
            {
                "name": "Test Parking Spot 2", 
                "address": "Helsinki Port",
                "coordinates": [60.1676, 24.9518],
                "type": "parking_lot",
                "overnight_allowed": False,
                "facilities": False,
                "max_height": "Unknown",
                "max_weight": "Unknown",
                "restrictions": ["Short-term only"],
                "source": "Test Data",
                "confidence": "75.0%"
            },
            {
                "name": "Test Parking Spot 3",
                "address": "Helsinki North",
                "coordinates": [60.1750, 24.9300],
                "type": "municipal_parking", 
                "overnight_allowed": True,
                "facilities": True,
                "max_height": "4.0m",
                "max_weight": "12.0t",
                "restrictions": ["Paid parking Mon-Fri"],
                "source": "Test Data",
                "confidence": "88.0%"
            },
            {
                "name": "Test Parking Spot 4",
                "address": "Helsinki East",
                "coordinates": [60.1650, 24.9450],
                "type": "surface_parking",
                "overnight_allowed": True,
                "facilities": False,
                "max_height": "Unknown",
                "max_weight": "Unknown", 
                "restrictions": [],
                "source": "Test Data",
                "confidence": "65.0%"
            },
            {
                "name": "Test Parking Spot 5",
                "address": "Helsinki West",
                "coordinates": [60.1720, 24.9250],
                "type": "parking_garage",
                "overnight_allowed": False,
                "facilities": True,
                "max_height": "2.1m",
                "max_weight": "3.5t",
                "restrictions": ["Height barrier", "No overnight parking"],
                "source": "Test Data", 
                "confidence": "55.0%"
            }
        ]
    }
    
    print("Test data created with 5 parking spots in Helsinki")
    print("Features to test:")
    print("  ✅ Color coding by confidence (green=high, orange=medium, red=low)")
    print("  ✅ Facility indicators (💙)")
    print("  ✅ Overnight parking indicators (🌙)")
    print("  ✅ Interactive spot details on click")
    print("  ✅ Zoom controls")
    print("  ✅ Coordinate grid")
    print()
    
    try:
        print("Opening map window... (close the window when done testing)")
        map_window = app.ParkingMapVisualization(test_results)
        map_window.show()
        print("Map window closed.")
    except KeyboardInterrupt:
        print("\nMap test cancelled by user.")
    except Exception as e:
        print(f"❌ Error opening map: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_map_gui()