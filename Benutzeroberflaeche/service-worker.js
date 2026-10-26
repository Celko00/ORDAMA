/**
 * Service Worker für ORDAMA PWA
 * Ermöglicht Offline-Funktionalität und aggressives Caching
 * Optimiert für Brave-Browser Kompatibilität und maximale Performance
 */

const CACHE_VERSION = 'v4';
const CACHE_NAME = `ordama-${CACHE_VERSION}`;
const STATIC_CACHE = `ordama-static-${CACHE_VERSION}`;
const DYNAMIC_CACHE = `ordama-dynamic-${CACHE_VERSION}`;
const IMAGE_CACHE = `ordama-images-${CACHE_VERSION}`;

// App Shell - kritische Ressourcen für sofortiges Laden
const urlsToCache = [
    './',
    './index.html',
    './css/style.css',
    './js/app.js',
    './js/mod/offline-storage.js',
    './js/mod/karte.js',
    './js/mod/mehrfachauswahl.js',
    './manifest.json',
    './start.png',
    'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css',
    'https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js',
    'https://cdnjs.cloudflare.com/ajax/libs/html2pdf.js/0.10.1/html2pdf.bundle.min.js',
    'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js'
];

// Cache-Strategien
const CACHE_STRATEGIES = {
    // Stale-While-Revalidate: Schnelle Antwort aus Cache, Hintergrund-Update
    staleWhileRevalidate: async (request, cacheName) => {
        const cache = await caches.open(cacheName);
        const cachedResponse = await cache.match(request);
        
        const fetchPromise = fetch(request).then(response => {
            if (response && response.status === 200) {
                cache.put(request, response.clone());
            }
            return response;
        }).catch(() => cachedResponse);
        
        return cachedResponse || fetchPromise;
    },
    
    // Network First: Zuerst Netzwerk, dann Cache
    networkFirst: async (request, cacheName) => {
        const cache = await caches.open(cacheName);
        try {
            const response = await fetch(request);
            if (response && response.status === 200) {
                cache.put(request, response.clone());
            }
            return response;
        } catch {
            return cache.match(request);
        }
    },
    
    // Cache First: Zuerst Cache, dann Netzwerk
    cacheFirst: async (request, cacheName) => {
        const cache = await caches.open(cacheName);
        const cachedResponse = await cache.match(request);
        if (cachedResponse) {
            // Hintergrund-Update
            fetch(request).then(response => {
                if (response && response.status === 200) {
                    cache.put(request, response.clone());
                }
            });
            return cachedResponse;
        }
        const response = await fetch(request);
        if (response && response.status === 200) {
            cache.put(request, response.clone());
        }
        return response;
    }
};

// Service Worker Installation und Caching
self.addEventListener('install', (event) => {
    console.log('Service Worker: Installation gestartet');
    event.waitUntil(
        Promise.all([
            caches.open(STATIC_CACHE).then(cache => {
                console.log('Service Worker: Caching app shell');
                return cache.addAll(urlsToCache.map(url => new Request(url, {cache: 'reload'})));
            }),
            caches.open(DYNAMIC_CACHE),
            caches.open(IMAGE_CACHE)
        ])
        .catch((error) => {
            console.error('Service Worker: Caching fehlgeschlagen', error);
        })
    );
    self.skipWaiting();
});

// Service Worker Aktivierung und Cache-Bereinigung
self.addEventListener('activate', (event) => {
    console.log('Service Worker: Aktivierung gestartet');
    event.waitUntil(
        caches.keys().then((cacheNames) => {
            return Promise.all(
                cacheNames.map((cacheName) => {
                    // Nur Caches der aktuellen Version behalten
                    if (!cacheName.includes(CACHE_VERSION)) {
                        console.log('Service Worker: Lösche alten Cache:', cacheName);
                        return caches.delete(cacheName);
                    }
                })
            );
        })
    );
    self.clients.claim();
});

// Fetch-Strategien basierend auf Ressourcentyp
self.addEventListener('fetch', (event) => {
    const url = new URL(event.request.url);

    // API-Requests nicht cachen (immer frisch vom Server)
    if (url.pathname.startsWith('/api/')) {
        event.respondWith(
            fetch(event.request)
                .catch(() => {
                    return new Response(
                        JSON.stringify({ error: 'Offline - Keine Server-Verbindung' }),
                        { headers: { 'Content-Type': 'application/json' } }
                    );
                })
        );
        return;
    }

    // CDN-Ressourcen cachen (für Offline-Funktionalität mit Icons)
    if (url.hostname.includes('cdnjs.cloudflare.com') ||
        url.hostname.includes('cdn.jsdelivr.net')) {
        event.respondWith(CACHE_STRATEGIES.cacheFirst(event.request, STATIC_CACHE));
        return;
    }

    // Statische Assets (CSS, JS, HTML) - Cache First mit Hintergrund-Update
    if (url.pathname.match(/\.(css|js|html|json|svg|woff2?|ttf|eot)$/)) {
        event.respondWith(CACHE_STRATEGIES.cacheFirst(event.request, STATIC_CACHE));
        return;
    }

    // Bilder - Cache First mit langer TTL
    if (url.pathname.match(/\.(jpg|jpeg|png|gif|webp|ico)$/)) {
        event.respondWith(CACHE_STRATEGIES.cacheFirst(event.request, IMAGE_CACHE));
        return;
    }

    // Andere Ressourcen - Stale-While-Revalidate für beste Performance
    event.respondWith(CACHE_STRATEGIES.staleWhileRevalidate(event.request, DYNAMIC_CACHE));
});

// Periodische Cache-Bereinigung (alle 24 Stunden)
self.addEventListener('periodicsync', (event) => {
    if (event.tag === 'cache-cleanup') {
        event.waitUntil(cleanupCaches());
    }
});

async function cleanupCaches() {
    console.log('Service Worker: Cache-Bereinigung gestartet');
    const cacheNames = await caches.keys();
    const now = Date.now();
    
    for (const cacheName of cacheNames) {
        const cache = await caches.open(cacheName);
        const requests = await cache.keys();
        
        for (const request of requests) {
            const response = await cache.match(request);
            if (response) {
                const date = response.headers.get('date');
                if (date) {
                    const cacheDate = new Date(date).getTime();
                    // Einträge älter als 7 Tage löschen (außer im Static Cache)
                    if (cacheName !== STATIC_CACHE && (now - cacheDate) > 7 * 24 * 60 * 60 * 1000) {
                        await cache.delete(request);
                    }
                }
            }
        }
    }
}

// Background Sync für Offline-Aktionen
self.addEventListener('sync', (event) => {
    if (event.tag === 'sync-pending-records') {
        event.waitUntil(syncPendingRecords());
    }
});

async function syncPendingRecords() {
    console.log('Service Worker: Background Sync gestartet');
    // Die eigentliche Logik läuft im Frontend (app.js)
}

// Push-Benachrichtigungen
self.addEventListener('push', (event) => {
    const options = {
        body: event.data ? event.data.text() : 'Neue Benachrichtigung',
        icon: './start.png',
        badge: './start.png',
        vibrate: [200, 100, 200]
    };

    event.waitUntil(
        self.registration.showNotification('ORDAMA', options)
    );
});
