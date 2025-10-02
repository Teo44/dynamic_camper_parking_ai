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
        
        # Add background color
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
        button_reset = Button(ax_reset, 'Reset View')
        button_info = Button(ax_info, 'Show All Info')
        
        # Button callbacks
        def reset_view(event):
            self.ax.set_xlim(self.min_lon, self.max_lon)
            self.ax.set_ylim(self.min_lat, self.max_lat)
            plt.draw()
        
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
        
        button_reset.on_clicked(reset_view)
        button_info.on_clicked(show_all_info)
    
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
        plt.draw()
        
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