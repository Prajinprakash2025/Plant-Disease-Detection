(function () {
    let locationMap = null;
    let locationMarker = null;

    window.openLocationModal = function () {
        const modal = document.getElementById('locationModal');
        if (!modal) return;
        modal.classList.remove('hidden');
        
        // Timeout to allow modal display before map initialization
        setTimeout(() => {
            const mapContainer = document.getElementById('leafletMap');
            if (!mapContainer) return;

            // If map instance already exists, remove it before creating a new one
            if (locationMap) {
                try {
                    locationMap.remove();
                } catch (e) {
                    console.warn("Could not remove Leaflet map instance:", e);
                }
                locationMap = null;
                locationMarker = null;
            }
            
            const latVal = document.getElementById('mapLat').value;
            const lonVal = document.getElementById('mapLon').value;
            
            let initialLat = parseFloat(latVal) || 10.8505; // Default to Kerala latitude if empty
            let initialLon = parseFloat(lonVal) || 76.2711; // Default to Kerala longitude if empty
            let zoomLevel = latVal ? 13 : 7;
            
            locationMap = L.map('leafletMap').setView([initialLat, initialLon], zoomLevel);
            
            L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
                maxZoom: 19,
                attribution: '© OpenStreetMap'
            }).addTo(locationMap);
            
            if (latVal && lonVal) {
                locationMarker = L.marker([initialLat, initialLon]).addTo(locationMap);
            }

            locationMap.on('click', function (e) {
                window.setCoordinates(e.latlng.lat, e.latlng.lng);
                
                const cityInput = document.getElementById('cityNameInput');
                if (cityInput) {
                    cityInput.placeholder = "Locating...";
                }
                
                fetch(`https://nominatim.openstreetmap.org/reverse?lat=${e.latlng.lat}&lon=${e.latlng.lng}&format=json`)
                    .then(r => r.json())
                    .then(data => {
                        const city = data.address?.city || data.address?.town || data.address?.village || data.address?.suburb || data.address?.county || data.address?.state || '';
                        if (cityInput) {
                            cityInput.value = city;
                            cityInput.placeholder = "e.g. Springfield Farm";
                        }
                    })
                    .catch(() => {
                        if (cityInput) {
                            cityInput.placeholder = "e.g. Springfield Farm";
                        }
                    });
            });
        }, 150);
    };

    window.closeLocationModal = function () {
        const modal = document.getElementById('locationModal');
        if (modal) modal.classList.add('hidden');
    };

    window.setCoordinates = function (lat, lng) {
        const latInput = document.getElementById('mapLat');
        const lonInput = document.getElementById('mapLon');
        if (latInput) latInput.value = lat.toFixed(6);
        if (lonInput) lonInput.value = lng.toFixed(6);
        
        if (locationMarker) {
            locationMarker.setLatLng([lat, lng]);
        } else if (locationMap) {
            locationMarker = L.marker([lat, lng]).addTo(locationMap);
        }
    };

    window.useCurrentLocation = function (event) {
        const btn = event.currentTarget || event.target;
        const originalText = btn.innerHTML;
        btn.innerHTML = '<i data-lucide="loader-2" class="h-3 w-3 animate-spin"></i> Detecting...';
        btn.disabled = true;

        if (!navigator.geolocation) {
            alert("Geolocation is not supported by your browser.");
            btn.innerHTML = originalText;
            btn.disabled = false;
            return;
        }

        navigator.geolocation.getCurrentPosition(
            function (position) {
                const lat = position.coords.latitude;
                const lng = position.coords.longitude;
                window.setCoordinates(lat, lng);
                if (locationMap) locationMap.setView([lat, lng], 14);
                btn.innerHTML = '<i data-lucide="check" class="h-3 w-3"></i> Location Set!';
                btn.disabled = false;
                if (window.lucide) window.lucide.createIcons();

                // Try reverse geocoding for city/town name
                fetch(`https://nominatim.openstreetmap.org/reverse?lat=${lat}&lon=${lng}&format=json`)
                    .then(r => r.json())
                    .then(data => {
                        const city = data.address?.city || data.address?.town || data.address?.village || data.address?.county || '';
                        const cityInput = document.getElementById('cityNameInput');
                        if (city && cityInput) cityInput.value = city;
                    })
                    .catch(() => {});

                setTimeout(() => { 
                    btn.innerHTML = originalText; 
                    if (window.lucide) window.lucide.createIcons(); 
                }, 2000);
            },
            function (error) {
                let msg = "Could not get your location.";
                if (error.code === 1) msg = "Location permission denied. Please allow location access in your browser settings.";
                else if (error.code === 2) msg = "Location unavailable. Check your device GPS/network.";
                else if (error.code === 3) msg = "Location request timed out. Try again.";
                alert(msg);
                btn.innerHTML = originalText;
                btn.disabled = false;
                if (window.lucide) window.lucide.createIcons();
            },
            { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }
        );
    };
})();
