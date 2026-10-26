/**
 * ORDAMA Frontend - Mobile-First App
 */

const App = {
    currentUser: null,
    currentSection: 'records',
    appointmentOnDateCache: new Map(),
    records: [],
    categories: [],
    editingId: null,
    searchType: 'all',
    calendarDate: new Date(),
    lockCheckInterval: null,
    currentLock: null,
    paginationInfo: null,
    isLoadingMore: false,
    scrollListener: null,
    searchTimeout: null,
    hasChanges: false,
    attachmentOcrRefreshTimer: null,
    reminders: [],
    reminderFilterActive: false,
    pendingReminder: null, // Für Erinnerungn bei neuen Akten
    galleryIsOffline: false, // Flag für Galerie-Offline-Status
    manualOfflineMode: false, // Manueller Offline-Modus
    wasOnline: true, // Um zu erkennen, wann die Verbindung verloren geht
    dom: {}, // Cache für DOM-Elemente
    galleryMedia: [],
    galleryCurrentIndex: 0,
    gallerySearchType: 'all',
    archiveAuswahlIstAktiv: false,
    archiveAuswahlIds: new Set(),
    archiveOffset: 0,
    userPreferences: null,
    recentAlerts: new Map(), // Verhindert doppelte Alert-Meldungen
    recentConfirms: new Map(), // Verhindert doppelte Confirm-Meldungen
    _prefsSaveTimer: null,
    sidebarDisplayIndex: 0,
    sidebarDisplays: ['logo', 'clock', 'calendar'],
    miniCalendarDate: new Date(),
    clockInterval: null,
    securityLogsInterval: null,

    // ── Init ───────────────────────────────────────
    init() {
        this.cacheDom();
        // Mobile: "100vh"-Problem (Adressleiste blendet ein/aus) – stabile Viewporthöhe setzen.
        this.aktualisiereViewportHoehe();
        window.addEventListener('resize', () => this.aktualisiereViewportHoehe());
        if (window.visualViewport) {
            window.visualViewport.addEventListener('resize', () => this.aktualisiereViewportHoehe());
            window.visualViewport.addEventListener('scroll', () => this.aktualisiereViewportHoehe());
        }

        // Hilfsfunktion für sicheren localStorage-Zugriff (für Edge-Kompatibilität bei IP-Adressen)
        // Versucht sessionStorage als Fallback, wenn localStorage blockiert ist
        this.safeLocalStorage = {
            getItem: (key) => {
                try {
                    return localStorage.getItem(key);
                } catch (e) {
                    // Fallback zu sessionStorage
                    try {
                        return sessionStorage.getItem(key);
                    } catch (e2) {
                        // Fallback zu globaler Variable (stiller Fallback, keine Warnung)
                        return window[`temp_${key}`] || null;
                    }
                }
            },
            setItem: (key, value) => {
                try {
                    localStorage.setItem(key, value);
                } catch (e) {
                    // Fallback zu sessionStorage
                    try {
                        sessionStorage.setItem(key, value);
                    } catch (e2) {
                        // Fallback zu globaler Variable (stiller Fallback)
                        window[`temp_${key}`] = value;
                    }
                }
            },
            removeItem: (key) => {
                try {
                    localStorage.removeItem(key);
                } catch (e) {
                    // Fallback zu sessionStorage
                    try {
                        sessionStorage.removeItem(key);
                    } catch (e2) {
                        // Fallback zu globaler Variable
                        delete window[`temp_${key}`];
                    }
                }
            }
        };

        // Device-ID generieren falls nicht vorhanden (für zuverlässige Session-Management)
        let deviceId = this.safeLocalStorage.getItem('device_id');
        if (!deviceId) {
            // Fallback: Prüfen ob Device-ID in globaler Variable gespeichert (für Edge bei IP-Adressen)
            deviceId = window.tempDeviceId;
        }
        if (!deviceId) {
            // Zufällige Hex-String generieren
            deviceId = Array.from(crypto.getRandomValues(new Uint8Array(16)))
                .map(b => b.toString(16).padStart(2, '0')).join('');
            this.safeLocalStorage.setItem('device_id', deviceId);
            // Fallback: Auch in globaler Variable speichern
            window.tempDeviceId = deviceId;
            console.log('📱 Neue Device-ID generiert und gespeichert:', deviceId);
        } else {
            console.log('📱 Vorhandene Device-ID gefunden:', deviceId);
            // Fallback: Auch in globaler Variable speichern
            window.tempDeviceId = deviceId;
        }

        this.initDarkMode();
        this.initOfflineMode();
        
        // PDF.js Worker initialisieren
        if (window.pdfjsLib) {
            window.pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';
        }

        this.bindEvents();
        this.checkSession();
        this.loadServerName();
        // loadCategories() wird jetzt in showApp() aufgerufen, wenn nicht Offline-Modus
        // Custom Dropdowns im Modal initialisieren
        this.initModalDropdowns();
        // Custom Filter Dropdowns (Filter & Sortierung) initialisieren
        this.initFilterDropdowns();
        this.initGalleryFilterDropdowns();
        // Event-Delegation für automatisch erzeugte Links
        this.setupLinkHandling();
        // Mehrfachauswahl (Long-Press / Strg-Klick)
        if (typeof this.initMehrfachAuswahl === 'function') {
            this.initMehrfachAuswahl();
        }
        // Load reminders periodically
        setInterval(() => {
            if (this.currentUser && this.currentUser?.username !== 'Offline-Modus') {
                this.loadReminders();
            }
        }, 60000); // Check every minute

        // Update chat unread count periodically
        setInterval(() => {
            if (this.currentUser && this.currentUser?.username !== 'Offline-Modus') {
                this.chatUpdateUnreadCount();
            }
        }, 30000); // Check every 30 seconds
        
        // Heartbeat für aktive Sessions - prüft ob Nutzer noch online ist
        this.heartbeatInterval = setInterval(() => {
            if (this.currentUser && this.currentUser?.username !== 'Offline-Modus' && !this.manualOfflineMode) {
                this.sendHeartbeat();
            }
        }, 15000); // Alle 15 Sekunden (verkürzt für bessere Session-Aktivität)
        
        // Aktivitätsüberwachung initialisieren - überwacht Maus, Tastatur und Klicks
        this.initActivityMonitoring();
        
        // Sidebar Navigation initialisieren
        this.initSidebarNavigation();
        
        // Offline Storage initialisieren
        if (typeof OfflineStorage !== 'undefined') {
            console.log('🔄 Initialisiere OfflineStorage...');
            OfflineStorage.init().then(async () => {
                console.log('✅ OfflineStorage erfolgreich initialisiert');
                
                // Offline-Akten beim App-Start laden
                await this.loadOfflineRecords();
                
                await this.updateOfflineIndicator();
                // Bei Online-Verbindung sofort synchronisieren
                const isOnline = await this.checkServerConnection();
                console.log('📡 Initialisierungs-Verbindungscheck:', isOnline ? 'Online' : 'Offline');
                if (isOnline) {
                    this.syncPendingRecords();
                }
                
                // Periodische Verbindungstprüfung starten (alle 10 Sekunden)
                this.startConnectionCheck();
            }).catch(e => {
                console.error('❌ Offline Storage Init fehlgeschlagen:', e);
                // Trotzdem Button aktualisieren mit Fallback
                this.updateOfflineIndicatorFallback();
                // Periodische Prüfung trotzdem starten
                this.startConnectionCheck();
            });
        } else {
            console.error('❌ OfflineStorage ist nicht verfügbar - Modul nicht geladen');
            this.updateOfflineIndicatorFallback();
            // Periodische Prüfung trotzdem starten
            this.startConnectionCheck();
        }
    },

    cacheDom() {
        this.dom = {
            app: document.getElementById('app'),
            loginScreen: document.getElementById('loginScreen'),
            recordsList: document.getElementById('recordsList'),
            recordsSearch: document.getElementById('recordsSearch'),
            recordAddress: document.getElementById('recordAddress'),
            recordFilter: document.getElementById('recordFilter'),
            recordSort: document.getElementById('recordSort'),
            modalOverlay: document.getElementById('modalOverlay'),
            recordModal: document.getElementById('recordModal'),
            recordForm: document.getElementById('recordForm'),
            recordContent: document.getElementById('recordContent'),
            pageTitle: document.getElementById('pageTitle'),
            sidebar: document.getElementById('sidebar'),
            sidebarOverlay: document.getElementById('sidebarOverlay'),
            dashboardSection: document.getElementById('dashboardSection'),
            calendarSection: document.getElementById('calendarSection'),
            assistantSection: document.getElementById('assistantSection'),
            recordsSection: document.getElementById('recordsSection'),
            recordCategoryFilter: document.getElementById('recordCategoryFilter'),
            recordCategory: document.getElementById('recordCategory'),
            categoryModalOverlay: document.getElementById('categoryModalOverlay'),
            categoryForm: document.getElementById('categoryForm'),
            categoryManageList: document.getElementById('categoryManageList'),
            karteSection: document.getElementById('karteSection'),
            usersSection: document.getElementById('usersSection'),
            formTemplatesSection: document.getElementById('formTemplatesSection'),
            settingsSection: document.getElementById('settingsSection'),
            loadingOverlay: document.getElementById('loadingOverlay'),
            sidebarContentDisplay: document.getElementById('sidebarContentDisplay'),
            sidebarDisplayItems: document.querySelectorAll('.sidebar-display-item'),
            clockHour: document.getElementById('clockHour'),
            clockMinute: document.getElementById('clockMinute'),
            clockSecond: document.getElementById('clockSecond'),
            digitalTime: document.getElementById('digitalTime'),
            miniCalMonth: document.getElementById('miniCalMonth'),
            miniCalGrid: document.getElementById('miniCalGrid'),
            miniCalPrev: document.getElementById('miniCalPrev'),
            miniCalNext: document.getElementById('miniCalNext'),
            securityConsoleLogs: document.getElementById('securityConsoleLogs'),
            consoleTabs: document.querySelectorAll('.console-tab')
        };
    },

    aktualisiereViewportHoehe() {
        // Während einer aktiven Karten-Interaktion (Finger gedrückt/Drag) die Viewport-Höhe NICHT nachführen,
        // weil mobile Browser (Android/iOS) die Adressleiste animieren können und dadurch der Canvas "wandert".
        if (this.karteInteraktionAktiv) return;

        // Setzt --vh auf 1% der tatsächlich sichtbaren Höhe (iOS/Android Browser-UI sicher)
        const h = window.visualViewport?.height || window.innerHeight;
        const vh = Math.max(1, h * 0.01);
        document.documentElement.style.setProperty('--vh', `${vh}px`);
    },

    getReminderVisibilityMeta(isPrivate) {
        return isPrivate
            ? {
                icon: 'fa-user',
                className: 'visibility-private',
                title: 'Termin nur für mich sichtbar'
            }
            : {
                icon: 'fa-users',
                className: 'visibility-all',
                title: 'Termin für alle sichtbar'
            };
    },

    // ── Dark Mode ──────────────────────────────────
    initDarkMode() {
        const isDark = this.safeLocalStorage.getItem('darkMode') === 'true';
        if (isDark) {
            document.body.classList.add('dark-mode');
            this.updateDarkModeButton(true);
        }
    },

    // ── Offline Mode ───────────────────────────────
    initOfflineMode() {
        const isManualOffline = this.safeLocalStorage.getItem('manualOfflineMode') === 'true';
        this.manualOfflineMode = isManualOffline;
        this.wasOnline = true; // Initial auf true setzen
        this.updateOfflineModeButton();
    },

    async showOfflineModeConfirmation() {
        // Verhindert mehrfache Anzeigen des Dialogs
        if (this.offlineConfirmationShown) {
            return;
        }
        this.offlineConfirmationShown = true;

        const confirmed = await this.confirm(
            'Keine Verbindung zum Server',
            'Möchten Sie in den Offline-Modus wechseln?',
            'Ja, Offline-Modus',
            'btn-primary'
        );

        if (confirmed) {
            this.manualOfflineMode = true;
            this.safeLocalStorage.setItem('manualOfflineMode', 'true');
            this.updateOfflineModeButton();
            this.toast('Offline-Modus aktiviert', 'info');
            this.checkConnectionStatus();
        }

        // Flag nach 5 Sekunden zurücksetzen, damit der Dialog erneut angezeigt werden kann
        setTimeout(() => {
            this.offlineConfirmationShown = false;
        }, 5000);
    },

    async toggleOfflineMode() {
        // Bestätigungsabfrage vor dem Aktivieren/Deaktivieren des Offline-Modus
        const action = this.manualOfflineMode ? 'Online-Modus' : 'Offline-Modus';
        const message = this.manualOfflineMode
            ? 'Möchten Sie die Verbindung zum Server wiederherstellen?'
            : 'Wollen Sie wirklich die Verbindung zum Server trennen?';

        if (!await this.confirm(action, message, this.manualOfflineMode ? 'Ja, Online-Modus' : 'Ja, Offline-Modus', 'btn-primary')) {
            return;
        }

        this.manualOfflineMode = !this.manualOfflineMode;
        this.safeLocalStorage.setItem('manualOfflineMode', this.manualOfflineMode);
        this.updateOfflineModeButton();

        if (this.manualOfflineMode) {
            // Beim Wechsel in Offline-Modus: Online-Status auf Server auf offline setzen
            if (this.currentUser && this.currentUser.id) {
                try {
                    // Online-Status auf offline setzen
                    fetch('/api/auth/set-online-status', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json'
                        },
                        body: JSON.stringify({ is_online: false })
                    }).catch(e => {
                        console.log('Online-Status konnte nicht gesetzt werden (erwartet):', e.message);
                    });
                    
                    console.log('Online-Status auf offline gesetzt');
                } catch (e) {
                    console.error('Fehler beim Setzen des Online-Status:', e);
                }
            }
            
            // Heartbeat-Interval stoppen
            if (this.heartbeatInterval) {
                clearInterval(this.heartbeatInterval);
                this.heartbeatInterval = null;
                console.log('Heartbeat-Interval gestoppt (Offline-Modus)');
            }
            
            this.toast('Offline-Modus aktiviert - Online-Status aktualisiert', 'info');
            // Sofort Status aktualisieren
            this.checkConnectionStatus();
        } else {
            // Beim Wechsel in Online-Modus: Online-Status auf Server auf online setzen
            if (this.currentUser && this.currentUser.id) {
                try {
                    // Online-Status auf online setzen
                    fetch('/api/auth/set-online-status', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json'
                        },
                        body: JSON.stringify({ is_online: true })
                    }).catch(e => {
                        console.log('Online-Status konnte nicht gesetzt werden:', e.message);
                    });
                    
                    console.log('Online-Status auf online gesetzt');
                } catch (e) {
                    console.error('Fehler beim Setzen des Online-Status:', e);
                }
            }
            
            // Heartbeat-Interval neu starten
            if (!this.heartbeatInterval) {
                this.heartbeatInterval = setInterval(() => {
                    if (this.currentUser && this.currentUser?.username !== 'Offline-Modus' && !this.manualOfflineMode) {
                        this.sendHeartbeat();
                    }
                }, 30000);
                console.log('Heartbeat-Interval neu gestartet (Online-Modus)');
            }
            
            this.toast('Online-Modus aktiviert - Verbindungsprüfungen aktiviert', 'info');
            this.checkConnectionStatus();
        }
    },

    updateOfflineModeButton() {
        const btn = document.getElementById('offlineModeBtn');
        const btnText = document.getElementById('offlineModeButtonText');
        if (btn && btnText) {
            if (this.manualOfflineMode) {
                btn.classList.add('offline-active');
                btn.innerHTML = '<i class="fas fa-wifi-slash"></i> <span id="offlineModeButtonText">Offline-Modus aktiv</span>';
                btn.title = 'Offline-Modus aktiv (klicken zum Deaktivieren)';
            } else {
                btn.classList.remove('offline-active');
                btn.innerHTML = '<i class="fas fa-wifi"></i> <span id="offlineModeButtonText">Offline-Modus</span>';
                btn.title = 'Offline-Modus deaktiviert (klicken zum Aktivieren)';
            }
        }
    },

    showOfflineOverlay() {
        const overlay = document.getElementById('offlineModeOverlay');
        if (overlay) {
            overlay.classList.remove('hidden');
        }
    },

    hideOfflineOverlay() {
        const overlay = document.getElementById('offlineModeOverlay');
        if (overlay) {
            overlay.classList.add('hidden');
        }
    },

    async sendHeartbeat() {
        // Sendet Heartbeat an Server um Session und Locks am Leben zu halten
        // Im Offline-Modus nicht ausführen
        if (this.manualOfflineMode) {
            console.log('Heartbeat im Offline-Modus übersprungen');
            return;
        }
        
        // Wenn kein Benutzer eingeloggt ist, Heartbeat überspringen
        if (!this.currentUser || !this.currentUser.id) {
            return;
        }

        const deviceId = this.safeLocalStorage.getItem('device_id');

        try {
            const response = await fetch('/api/auth/heartbeat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Device-ID': deviceId
                },
                credentials: 'include'
            });

            if (response.ok) {
                const data = await response.json();
                if (data.session_expired) {
                    // Session wurde vom Admin beendet
                    console.log('Session vom Admin beendet');
                    // Kein Toast anzeigen - nur ausloggen
                    this.logout(true); // force=true um Bestätigungsabfrage zu überspringen
                } else {
                    console.log('Heartbeat erfolgreich');
                    // Benutzerliste im Chat aktualisieren wenn im Privat-Tab (alle 15 Sekunden)
                    if (this.chatTab === 'conversations') {
                        this.chatLoadUsers();
                    }
                }
            } else if (response.status === 401) {
                // 401 bedeutet nicht eingeloggt - einfach ignorieren, kein Logout nötig
                console.log('Heartbeat: Nicht eingeloggt (401), überspringe');
            } else {
                console.warn('Heartbeat fehlgeschlagen:', response.status);
            }
        } catch (error) {
            console.error('Heartbeat Fehler:', error);
            // Bei Fehler keine Aktion - nächste Interval wird es erneut versuchen
        }
    },

    async updateSessionActivity() {
        // Aktualisiert die Session-Aktivität bei Benutzeraktionen
        // Im Offline-Modus nicht ausführen
        if (this.manualOfflineMode) {
            return;
        }
        
        // Heartbeat senden, um Session-Aktivität zu aktualisieren
        this.sendHeartbeat();
    },

    initActivityMonitoring() {
        // Aktivitätsüberwachung initialisieren - überwacht Maus, Tastatur und Klicks
        let activityTimeout = null;
        let lastHeartbeatTime = 0;
        const ACTIVITY_THRESHOLD = 5000; // 5 Sekunden ohne Aktivität = inaktiv
        const HEARTBEAT_INTERVAL = 10000; // Nur alle 10 Sekunden Heartbeat senden

        const resetActivity = () => {
            if (activityTimeout) {
                clearTimeout(activityTimeout);
            }
            
            const now = Date.now();
            // Nur Heartbeat senden, wenn mindestens 10 Sekunden seit dem letzten vergangen sind
            if (now - lastHeartbeatTime >= HEARTBEAT_INTERVAL) {
                this.updateSessionActivity();
                lastHeartbeatTime = now;
            }
            
            // Timeout für Inaktivität setzen
            activityTimeout = setTimeout(() => {
                console.log('Benutzer inaktiv für 5 Sekunden');
            }, ACTIVITY_THRESHOLD);
        };

        // Mausbewegungen überwachen (mit Debounce)
        let mouseMoveTimeout = null;
        document.addEventListener('mousemove', () => {
            if (mouseMoveTimeout) {
                clearTimeout(mouseMoveTimeout);
            }
            mouseMoveTimeout = setTimeout(() => {
                resetActivity();
            }, 500); // 500ms Debounce für Mausbewegungen
        });

        // Tastatureingaben überwachen
        document.addEventListener('keydown', () => {
            resetActivity();
        });

        // Klicks überwachen
        document.addEventListener('click', () => {
            resetActivity();
        });

        // Scrollen überwachen (mit Debounce)
        let scrollTimeout = null;
        document.addEventListener('scroll', () => {
            if (scrollTimeout) {
                clearTimeout(scrollTimeout);
            }
            scrollTimeout = setTimeout(() => {
                resetActivity();
            }, 500); // 500ms Debounce für Scrollen
        });

        console.log('Aktivitätsüberwachung initialisiert');
    },

    toggleDarkMode() {
        const isDark = document.body.classList.toggle('dark-mode');
        this.safeLocalStorage.setItem('darkMode', isDark);
        this.updateDarkModeButton(isDark);
        this.saveUserPreferences();
    },

    setDarkMode(isDark) {
        document.body.classList.toggle('dark-mode', !!isDark);
        this.safeLocalStorage.setItem('darkMode', !!isDark);
        this.updateDarkModeButton(!!isDark);
    },

    toggleMobileFilters() {
        const content = document.getElementById('mobileFilterContent');
        if (content) {
            content.classList.toggle('show');
            // Auswahl-Leiste NICHT schließen, wenn Auswahlmodus aktiv ist
        }
    },

    updateDarkModeButton(isDark) {
        const btn = document.getElementById('darkModeToggle');
        if (btn) {
            btn.innerHTML = isDark ? '<i class="fas fa-sun"></i> Light Mode' : '<i class="fas fa-moon"></i> Dark Mode';
        }
    },

    // ── API ────────────────────────────────────────
    generateDeviceId() {
        // Generiert eine eindeutige Device-ID basierend auf Browser-Informationen
        const timestamp = Date.now().toString(36);
        const random = Math.random().toString(36).substring(2, 15);
        return `device_${timestamp}_${random}`;
    },

    async api(method, endpoint, body = null, showLoadingOverlay = true, timeoutMs = 15000, overrideDeviceId = null) {
        const url = `/api${endpoint}`;
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

        // Device-ID aus localStorage holen oder overrideDeviceId verwenden
        let deviceId = overrideDeviceId || this.safeLocalStorage.getItem('device_id');
        // Fallback: Wenn immer noch keine Device-ID, aus globaler Variable holen
        if (!deviceId && window.tempDeviceId) {
            deviceId = window.tempDeviceId;
        }

        const cfg = {
            method: method,
            headers: {
                'X-Offline-Mode': this.manualOfflineMode ? 'true' : 'false'
            },
            credentials: 'include' // WICHTIG: Session-Cookies senden
        };

        // Device-ID immer im Header senden (wenn vorhanden)
        if (deviceId) {
            cfg.headers['X-Device-ID'] = deviceId;
        }

        // Content-Type nur setzen wenn es kein FormData ist
        if (body && !(body instanceof FormData)) {
            cfg.headers['Content-Type'] = 'application/json';
            cfg.body = JSON.stringify(body);
        } else if (body) {
            cfg.body = body;
        }

        if (showLoadingOverlay) this.showLoading(true);

        cfg.signal = controller.signal;

        try {
            const res = await fetch(url, cfg);
            clearTimeout(timeoutId);

            // Response-Body nur einmal lesen
            const contentType = res.headers.get('content-type');
            let data;

            if (contentType && contentType.includes('application/json')) {
                data = await res.json();
            } else {
                const text = await res.text();
                console.error('Server Antwort nicht JSON:', text.substring(0, 200));
                throw new Error('Server-Antwort ungültig. Überprüfen Sie die Server-Logs.');
            }

            if (!res.ok) {
                // Spezielle Behandlung für Session-Konflikt (409 Conflict)
                if (res.status === 409) {
                    // Session ungültig - aber device_id NICHT löschen (für Offline-Sync)
                    this.currentUser = null;
                    this.showLogin(data.error || 'Sie wurden von einem anderen Gerät ausgeloggt', 'warning');
                    return null; // Kein Error werfen, da bereits Toast angezeigt
                }
                // Rate-Limit (429) - Fehler mit zusätzlichen Daten weitergeben
                if (res.status === 429) {
                    const error = new Error(data.error || `Fehler ${res.status}`);
                    error.response = { status: res.status, data: data };
                    error.waitSeconds = data.waitSeconds;
                    error.remainingAttempts = data.remainingAttempts;
                    throw error;
                }
                // Authentifizierungsfehler (401/403) - auch zum Login leiten
                // AUSNAHME: Im Offline-Modus nicht ausloggen, da API-Aufrufe fehlschlagen können
                if ((res.status === 401 || res.status === 403) && !this.manualOfflineMode) {
                    this.currentUser = null;
                    // Nur Server-Fehlermeldung anzeigen, sonst generische Meldung
                    this.showLogin(data.error || 'Session abgelaufen. Bitte erneut einloggen.', 'warning');
                    return null;
                }
                const error = new Error(data.error || `Fehler ${res.status}`);
                error.response = { status: res.status, data: data };
                throw error;
            }

            // Auch bei erfolgreicher Antwort auf session_expired prüfen
            if (data.session_expired && !this.manualOfflineMode) {
                this.currentUser = null;
                this.logout(true); // force=true um Bestätigungsabfrage zu überspringen
                return null;
            }

            return data;
        } catch (e) {
            if (e.name === 'AbortError') {
                throw new Error('Server nicht erreichbar (Timeout). Daten werden offline gespeichert.');
            }
            if (e.name === 'TypeError' && e.message === 'Failed to fetch') {
                throw new Error('Verbindung zum Server fehlgeschlagen. Daten werden offline gespeichert.');
            }
            if (e.message && e.message.includes('Failed to fetch')) {
                throw new Error('Verbindung zum Server fehlgeschlagen. Daten werden offline gespeichert.');
            }
            if (e.message && e.message.includes('NetworkError')) {
                throw new Error('Netzwerkfehler. Daten werden offline gespeichert.');
            }
            throw e;
        } finally {
            if (showLoadingOverlay) this.showLoading(false);
        }
    },
    apiGet(endpoint, showLoadingOverlay = true, overrideDeviceId = null) { return this.api('GET', endpoint, null, showLoadingOverlay, 15000, overrideDeviceId); },
    apiPost(endpoint, body = null, showLoadingOverlay = true, overrideDeviceId = null) { return this.api('POST', endpoint, body, showLoadingOverlay, 15000, overrideDeviceId); },
    apiPut(endpoint, body = null, showLoadingOverlay = true, overrideDeviceId = null) { return this.api('PUT', endpoint, body, showLoadingOverlay, 15000, overrideDeviceId); },
    apiDelete(endpoint, showLoadingOverlay = true, overrideDeviceId = null) { return this.api('DELETE', endpoint, null, showLoadingOverlay, 15000, overrideDeviceId); },

    // ── Upload with Progress ───────────────────────
    uploadQueue: [],
    isUploading: false,

    updateUploadProgress(percent, filename, done = false, isDownload = false) {
        const panel = document.getElementById('uploadProgressPanel');
        const bar = document.getElementById('uploadProgressBar');
        const text = document.getElementById('uploadProgressText');
        const file = document.getElementById('uploadProgressFile');
        if (!panel) return;
        
        // Bei 100% und done=true komplett ausblenden
        if (done && percent >= 100) {
            panel.classList.add('hidden');
            return;
        }
        
        panel.classList.remove('hidden');
        bar.style.width = percent + '%';
        const action = isDownload ? 'Download' : 'Upload';
        text.textContent = `${action} ${Math.round(percent)}%`;
        file.textContent = filename || '-';
    },

    uploadFileWithProgress(endpoint, formData, filename) {
        return new Promise((resolve, reject) => {
            const xhr = new XMLHttpRequest();
            xhr.open('POST', `/api${endpoint}`);
            xhr.withCredentials = true;

            xhr.upload.addEventListener('progress', (e) => {
                if (e.lengthComputable) {
                    const percent = (e.loaded / e.total) * 100;
                    this.updateUploadProgress(percent, filename);
                }
            });

            xhr.addEventListener('load', () => {
                if (xhr.status >= 200 && xhr.status < 300) {
                    try {
                        const data = JSON.parse(xhr.responseText);
                        resolve(data);
                    } catch {
                        resolve(xhr.responseText);
                    }
                } else {
                    try {
                        const data = JSON.parse(xhr.responseText);
                        reject(new Error(data.error || `Fehler ${xhr.status}`));
                    } catch {
                        reject(new Error(`Fehler ${xhr.status}`));
                    }
                }
            });

            xhr.addEventListener('error', () => reject(new Error('Netzwerkfehler')));
            xhr.addEventListener('abort', () => reject(new Error('Upload abgebrochen')));

            xhr.send(formData);
        });
    },

    async processUploadQueue() {
        if (this.isUploading || !this.uploadQueue.length) return;
        this.isUploading = true;
        while (this.uploadQueue.length) {
            const { endpoint, formData, filename, recordId } = this.uploadQueue.shift();
            this.updateUploadProgress(0, filename);
            try {
                const response = await this.uploadFileWithProgress(endpoint, formData, filename);
                this.updateUploadProgress(100, filename, true);
                if (response?.ocr?.queued) {
                    this.toast(`Datei hochgeladen: ${filename} – OCR gestartet`, 'success');
                } else {
                    this.toast(`Datei hochgeladen: ${filename}`, 'success');
                }
            } catch (e) {
                this.updateUploadProgress(0, filename, true);
                this.toast(e.message, 'error');
            }
        }
        this.isUploading = false;
        // Refresh attachments
        if (this.editingId) {
            try {
                const data = await this.apiGet(`/records/${this.editingId}`);
                this.renderAttachments(data.attachments || []);
            } catch (e) {
                console.error('Aktualisierung der Anhänge fehlgeschlagen:', e);
            }
        }
        document.getElementById('uploadProgressPanel').classList.add('hidden');
    },

    // ── Loading & Toast ────────────────────────────
    translateErrorMessage(errorMsg) {
        if (!errorMsg) return 'Unbekannter Fehler';
        
        const translations = {
            'Cannot read properties of undefined': 'Eigenschaft konnte nicht gelesen (Wert ist undefiniert)',
            'Cannot read properties of null': 'Eigenschaft konnte nicht gelesen (Wert ist null)',
            'Cannot read': 'Eigenschaft konnte nicht gelesen',
            'is not defined': 'ist nicht definiert',
            'is not a function': 'ist keine Funktion',
            'Failed to fetch': 'Verbindung zum Server fehlgeschlagen',
            'NetworkError': 'Netzwerkfehler'
        };
        
        let translated = errorMsg;
        for (const [english, german] of Object.entries(translations)) {
            translated = translated.replace(new RegExp(english, 'g'), german);
        }
        
        return translated;
    },
    
    showLoading(show) {
        if (this.dom.loadingOverlay) this.dom.loadingOverlay.classList.toggle('show', show);
    },
    toast(msg, type = 'info', duration = 3000) {
        // Toast-Meldungen deaktiviert - keine Anzeige mehr
        return;
    },

    // ── Auth ───────────────────────────────────────
    async loadServerName() {
        try {
            const response = await fetch('/api/server-name');
            const data = await response.json();
            const serverNameElement = document.getElementById('loginServerName');
            if (serverNameElement && data.server_name) {
                serverNameElement.textContent = data.server_name;
            }
        } catch (e) {
            console.log('Konnte Servernamen nicht laden:', e);
        }
    },

    async checkSession() {
        // Ladescreen zeigen während des Checks
        this.showLoading(true);

        // Manueller Offline-Modus hat Priorität
        if (this.manualOfflineMode) {
            console.log('Manueller Offline-Modus aktiv - zeige App ohne Login');
            this.showLoading(false);
            this.currentUser = {
                username: 'Offline-Modus',
                role: 'admin',
                can_view_records: true,
                can_create_records: true,
                can_edit_records: true,
                can_delete_records: true,
                can_view_gallery: true,
                can_view_map: true,
                can_view_calendar: true,
                can_view_assistant: true,
                can_view_stats: true,
                can_view_archive: true,
                can_archive: true
            };
            await this.showApp();
            return;
        }

        // Browser-Status prüfen (schnell und zuverlässig)
        let isOffline = false;
        if (!navigator.onLine) {
            isOffline = true;
            console.log('Browser ist offline');
        }

        // Wenn offline, IMMER in Offline-Modus wechseln
        if (isOffline) {
            console.log('Offline - zeige App ohne Login');
            this.showLoading(false);
            // Offline-Benutzer mit allen Berechtigungen erstellen
            this.currentUser = {
                username: 'Offline-Modus',
                role: 'admin', // Admin-Rechte für Offline-Modus
                can_view_records: true,
                can_create_records: true,
                can_edit_records: true,
                can_delete_records: true,
                can_view_gallery: true,
                can_view_map: true,
                can_view_calendar: true,
                can_view_assistant: true,
                can_view_stats: true,
                can_view_archive: true,
                can_archive: true
            };
            await this.showApp();
            return;
        }

        // Normaler Online-Check
        try {
            const data = await this.apiGet('/auth/me', false);
            if (data.user) {
                this.currentUser = data.user;
                this.showLoading(false);
                await this.showApp();
                this.updateAuthButton();
            } else {
                this.showLoading(false);
                this.showLogin('Bitte loggen Sie sich ein', 'info');
                this.updateAuthButton();
            }
        } catch (e) {
            this.showLoading(false);

            // Spezielle Behandlung für Session-Fehler
            if (e.response && e.response.status === 409) {
                this.showLogin(e.response.data && e.response.data.error ? e.response.data.error : 'Sie wurden von einem anderen Gerät ausgeloggt', 'warning');
            } else if (e.response && e.response.status === 401) {
                this.showLogin(e.response.data && e.response.data.error ? e.response.data.error : 'Bitte loggen Sie sich ein', 'error');
            } else {
                this.showLogin('Bitte loggen Sie sich ein', 'info');
            }
        }
    },

    async login(ev) {

    // Verhindert doppelte Toast-Meldungen innerhalb von 3 Sekunden
    const toastKey = `${msg}_${type}`;
    const now = Date.now();
    if (this.recentToasts.has(toastKey)) {
        const lastShown = this.recentToasts.get(toastKey);
        if (now - lastShown < 3000) {
            console.log('🔒 Doppelte Toast-Meldung verhindert:', msg);
            return; // Überspringe doppelte Meldung
        }
    }

    const el = document.createElement('div');
    el.className = `toast ${type}`;
    const icon = type === 'success' ? 'check-circle' : type === 'error' ? 'exclamation-circle' : 'info-circle';
    el.innerHTML = `<i class="fas fa-${icon}"></i><span>${this.escapeHtml(msg)}</span>`;
    c.appendChild(el);

    // Speichere Zeitstempel der Toast-Meldung
    this.recentToasts.set(toastKey, now);

    // Entferne Toast nach 3 Sekunden und aus der Map
    setTimeout(() => {
        el.remove();
        this.recentToasts.delete(toastKey);
    }, 3000);
},

// ── Auth ───────────────────────────────────────
async checkSession() {
    // Ladescreen zeigen während des Checks
    this.showLoading(true);

    // Manueller Offline-Modus hat Priorität
    if (this.manualOfflineMode) {
        console.log('Manueller Offline-Modus aktiv - zeige App ohne Login');
        this.showLoading(false);
        this.currentUser = {
            username: 'Offline-Modus',
            role: 'admin',
            can_view_records: true,
            can_create_records: true,
            can_edit_records: true,
            can_delete_records: true,
            can_view_gallery: true,
            can_view_map: true,
            can_view_calendar: true,
            can_view_assistant: true,
            can_view_stats: true,
            can_view_archive: true,
            can_archive: true
        };
        await this.showApp();
        return;
    }

    // Browser-Status prüfen (schnell und zuverlässig)
    let isOffline = false;
    if (!navigator.onLine) {
        isOffline = true;
        console.log('Browser ist offline');
    }

    // Wenn offline, IMMER in Offline-Modus wechseln
    if (isOffline) {
        console.log('Offline - zeige App ohne Login');
        this.showLoading(false);
        // Offline-Benutzer mit allen Berechtigungen erstellen
        this.currentUser = {
            username: 'Offline-Modus',
            role: 'admin', // Admin-Rechte für Offline-Modus
            can_view_records: true,
            can_create_records: true,
            can_edit_records: true,
            can_delete_records: true,
            can_view_gallery: true,
            can_view_map: true,
            can_view_calendar: true,
            can_view_assistant: true,
            can_view_stats: true,
            can_view_archive: true,
            can_archive: true
        };
        await this.showApp();
        return;
    }

    // Normaler Online-Check
    try {
        const data = await this.apiGet('/auth/me', false);
        if (data.user) {
            this.currentUser = data.user;
            this.showLoading(false);
            await this.showApp();
            this.updateAuthButton();
        } else {
            this.showLoading(false);
            this.showLogin('Bitte loggen Sie sich ein', 'info');
            this.updateAuthButton();
        }
    } catch (e) {
        this.showLoading(false);

        // Spezielle Behandlung für Session-Fehler
        if (e.response && e.response.status === 409) {
            this.showLogin(e.response.data && e.response.data.error ? e.response.data.error : 'Sie wurden von einem anderen Gerät ausgeloggt', 'warning');
        } else if (e.response && e.response.status === 401) {
            this.showLogin(e.response.data && e.response.data.error ? e.response.data.error : 'Bitte loggen Sie sich ein', 'error');
        } else {
            this.showLogin('Bitte loggen Sie sich ein', 'info');
        }
    }
},

async login(ev) {
    ev.preventDefault();
    const username = document.getElementById('loginUser').value.trim();
    const password = document.getElementById('loginPass').value;
    if (!username || !password) { this.toast('Bitte alle Felder ausfuellen', 'error'); return; }

    this.currentUser = null;
    this.safeLocalStorage.removeItem('auth_token');

    // Loading-Overlay anzeigen
    this.showLoading(true);

    try {
        // Device-ID aus localStorage holen oder neu generieren
        // Wichtig: device_id muss über Browser-Neustarts hinweg konstant bleiben
        let deviceId = this.safeLocalStorage.getItem('device_id');
        if (!deviceId) {
            deviceId = this.generateDeviceId();
            this.safeLocalStorage.setItem('device_id', deviceId);
        }

        const data = await this.apiPost('/auth/login', { username, password }, true, deviceId);
        if (!data) {
            // 409 Conflict wurde bereits im API-Handler behandelt
            return;
        }
        this.currentUser = data.user;

            // Device-ID speichern (falls vom Server zugewiesen)
            if (data.device_id) {
                this.safeLocalStorage.setItem('device_id', data.device_id);
            }

            // Settings laden für Ähnlichkeitssuche-Limit
            if (this.currentUser.role === 'admin') {
                try {
                    const settingsData = await this.apiGet('/settings', false);
                    this.settings = settingsData.settings || {};
                } catch (e) {
                    console.error('Fehler beim Laden der Settings:', e);
                    this.settings = {};
                }
            } else {
                this.settings = {};
            }

            await this.showApp();
            this.updateAuthButton();
        } catch (e) {
            // Fehlermeldung im loginMessage Feld anzeigen
            const loginMessage = document.getElementById('loginMessage');
            if (e.waitSeconds !== undefined) {
                const waitMinutes = Math.ceil(e.waitSeconds / 60);
                loginMessage.textContent = `Bitte ${waitMinutes} Minute(n) warten`;
                loginMessage.className = 'login-message warning';
            } else if (e.remainingAttempts !== undefined) {
                loginMessage.textContent = `${e.message || 'Fehler beim Login'}. Noch ${e.remainingAttempts} Versuche übrig`;
                loginMessage.className = 'login-message warning';
            } else {
                loginMessage.textContent = e.message || 'Fehler beim Login';
                loginMessage.className = 'login-message error';
            }
        } finally {
            // Loading-Overlay ausblenden
            this.showLoading(false);
        }
    },

    async uploadSignature(userId) {
        const input = document.createElement('input');
        input.type = 'file';
        input.accept = 'image/*';
        input.onchange = async (e) => {
            const file = e.target.files[0];
            if (!file) return;

            // Dateigröße prüfen (max 2MB für Signaturen)
            if (file.size > 2 * 1024 * 1024) {
                this.toast('Die Bilddatei ist zu groß (max. 2MB).', 'error');
                return;
            }

            const reader = new FileReader();
            reader.onload = async (event) => {
                const base64 = event.target.result;
                try {
                    await this.apiPost(`/users/${userId}/signature`, { signature: base64 });
                    this.toast('Unterschrift erfolgreich hochgeladen', 'success');
                    this.loadUsers();
                } catch (err) {
                    this.toast('Fehler beim Hochladen: ' + err.message, 'error');
                }
            };
            reader.readAsDataURL(file);
        };
        input.click();
    },

    async logout(force = false) {
        // Allgemeine Bestätigungsabfrage vor dem Abmelden (nicht bei force=true)
        if (!force && !await this.confirm('Abmelden bestätigen', 'Möchten Sie sich wirklich abmelden?', 'Ja, abmelden', 'btn-primary')) {
            return;
        }

        if (this.hasChanges) {
            if (!force && !await this.confirm('Ungespeicherte Änderungen', 'Möchten Sie sich wirklich abmelden? Alle ungespeicherten Änderungen gehen verloren.', 'Ja, abmelden', 'btn-danger')) {
                return;
            }
            this.hasChanges = false;
        }
        // Unlock current record if any
        if (this.editingId && this.currentLock) {
            await this.unlockRecord(this.editingId).catch(()=>{});
        }
        
        // Logout-Status lokal speichern für späteren Cleanup beim Online-Wechsel
        if (this.currentUser && this.currentUser.id) {
            this.safeLocalStorage.setItem('pending_logout_user_id', this.currentUser.id);
            this.safeLocalStorage.setItem('pending_logout_username', this.currentUser.username);
        }
        
        try {
            await this.apiPost('/auth/logout');
        } catch (e) {
            console.error('Fehler beim Abmelden:', e);
            // Im Offline-Modus oder bei Verbindungsfehlern trotzdem lokal aufräumen
            if (this.currentUser && this.currentUser.id) {
                console.log('Logout im Offline-Modus - Session wird beim nächsten Online-Wechsel bereinigt');
            }
        }

        // Device-ID beim Logout löschen, damit jedes Gerät eine andere ID hat
        this.safeLocalStorage.removeItem('device_id');

        this.currentUser = null;
        this.safeLocalStorage.removeItem('auth_token');
        this.safeLocalStorage.removeItem('saved_username');
        this.safeLocalStorage.removeItem('saved_password');
        this.showLogin('Bitte loggen Sie sich ein', 'info');
        this.updateAuthButton();
    },

    handleAuthButton() {
        // Dynamischer Auth-Button: Abmelden wenn eingeloggt, Anmelden wenn nicht
        if (this.currentUser && this.currentUser.username !== 'Offline-Modus') {
            this.logout();
        } else {
            this.showLogin('Bitte loggen Sie sich ein', 'info');
        }
    },

    updateAuthButton() {
        // Aktualisiert den Auth-Button je nach Login-Status
        const authButton = document.getElementById('authButton');
        const authButtonText = document.getElementById('authButtonText');
        if (!authButton || !authButtonText) return;

        if (this.currentUser && this.currentUser.username !== 'Offline-Modus') {
            // Benutzer ist eingeloggt
            authButton.innerHTML = '<i class="fas fa-sign-out-alt"></i> <span id="authButtonText">Abmelden</span>';
            authButton.classList.remove('btn-primary');
            authButton.classList.add('btn-secondary');
        } else {
            // Benutzer ist nicht eingeloggt oder im Offline-Modus
            authButton.innerHTML = '<i class="fas fa-sign-in-alt"></i> <span id="authButtonText">Anmelden</span>';
            authButton.classList.remove('btn-secondary');
            authButton.classList.add('btn-primary');
        }
    },

    showLogin(message = null, messageType = 'warning') {
        // Offline-Screen ausblenden
        const offlineScreen = document.getElementById('offlineScreen');
        if (offlineScreen) offlineScreen.classList.add('hidden');

        document.getElementById('loginScreen').classList.remove('hidden');
        document.getElementById('app').classList.remove('active');
        
        // Nur fokussieren, wenn Passwortfeld nicht bereits fokussiert ist
        const passField = document.getElementById('loginPass');
        if (document.activeElement !== passField) {
            document.getElementById('loginUser').focus();
        }

        // Login-Meldung anzeigen wenn vorhanden
        const loginMessage = document.getElementById('loginMessage');
        if (message) {
            loginMessage.textContent = message;
            loginMessage.className = `login-message ${messageType}`;
        } else {
            loginMessage.textContent = '';
            loginMessage.className = 'login-message';
        }
    },

    showOfflineMessage() {
        // Login-Screen ausblenden
        document.getElementById('loginScreen').classList.add('hidden');
        document.getElementById('app').classList.remove('active');
        
        // Offline-Screen zeigen
        let offlineScreen = document.getElementById('offlineScreen');
        if (!offlineScreen) {
            offlineScreen = document.createElement('div');
            offlineScreen.id = 'offlineScreen';
            offlineScreen.className = 'login-screen';
            offlineScreen.innerHTML = `
                <div class="login-container">
                    <div class="login-header">
                        <h1>ORDAMA</h1>
                        <p class="offline-message">
                            <i class="fas fa-wifi-slash"></i>
                            <br><br>
                            Sie sind offline.<br>
                            Keine Verbindung zum Server möglich.<br><br>
                            <small>Bitte stellen Sie eine Verbindung her oder erstellen Sie Offline-Akten.</small>
                        </p>
                    </div>
                    <div class="login-actions">
                        <button type="button" class="btn btn-primary" onclick="location.reload()">
                            <i class="fas fa-sync"></i> Neu laden
                        </button>
                    </div>
                </div>
            `;
            document.body.appendChild(offlineScreen);
        }
        offlineScreen.classList.remove('hidden');
    },

    showSectionOfflineMessage(sectionName) {
        // Offline-Overlay für die aktive Sektion anzeigen
        const activeSection = document.querySelector('.section.active');
        if (activeSection) {
            // Prüfen ob bereits ein Offline-Overlay existiert
            let offlineOverlay = activeSection.querySelector('.section-offline-overlay');
            if (!offlineOverlay) {
                offlineOverlay = document.createElement('div');
                offlineOverlay.className = 'section-offline-overlay';
                offlineOverlay.style.cssText = `
                    position: absolute;
                    top: 0;
                    left: 0;
                    right: 0;
                    bottom: 0;
                    background: #000;
                    color: #fff;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    text-align: center;
                    padding: 20px;
                    z-index: 1000;
                `;
                activeSection.appendChild(offlineOverlay);
            }
            
            offlineOverlay.innerHTML = `
                <div>
                    <i class="fas fa-wifi-slash" style="font-size: 64px; margin-bottom: 20px;"></i>
                    <h2 style="font-size: 32px; margin-bottom: 20px;">Offline</h2>
                    <p style="font-size: 18px; color: #ccc;">
                        Dieser Bereich ist nur mit Server-Verbindung verfügbar.<br><br>
                        <small>Bitte stellen Sie eine Verbindung zum Server her.</small>
                    </p>
                </div>
            `;
            offlineOverlay.style.display = 'flex';
        }
    },

    hideSectionOfflineMessage() {
        // Offline-Overlay ausblenden
        const offlineOverlay = document.querySelector('.section-offline-overlay');
        if (offlineOverlay) {
            offlineOverlay.style.display = 'none';
        }
    },
    
    setupOnlineOfflineListeners() {
        // Event-Listener für Online/Offline-Statusänderungen
        window.addEventListener('online', () => {
            console.log('✅ Browser ist wieder online');
            this.hideSectionOfflineMessage();
            
            // Wenn wir in einer server-abhängigen Sektion sind, den Inhalt neu laden
            const serverDependentSections = ['gallery', 'karte', 'calendar', 'assistant', 'dashboard', 'formTemplates', 'users', 'audit', 'settings'];
            if (serverDependentSections.includes(this.currentSection)) {
                console.log(`🔄 Lade ${this.currentSection} neu nach Online-Status`);
                this.showSection(this.currentSection);
            }
        });
        
        window.addEventListener('offline', () => {
            console.log('❌ Browser ist offline');
            // Wenn wir in einer server-abhängigen Sektion sind, Offline-Meldung anzeigen
            const serverDependentSections = ['gallery', 'karte', 'calendar', 'assistant', 'dashboard', 'formTemplates', 'users', 'audit', 'settings'];
            if (serverDependentSections.includes(this.currentSection)) {
                const sectionTitles = {
                    dashboard: 'Statistik',
                    records: 'Akten',
                    gallery: 'Galerie',
                    karte: 'Karte',
                    calendar: 'Kalender',
                    assistant: 'Assistent'
                };
                this.showSectionOfflineMessage(sectionTitles[this.currentSection] || 'diesen Bereich');
            }
        });
    },

    hasUserPermission(permission) {
        return this.currentUser?.role === 'admin' || !!this.currentUser?.[permission];
    },

    getSectionPermission(sectionName) {
        const permissionMap = {
            dashboard: 'can_view_stats',
            records: 'can_view_records',
            archive: 'can_view_records',
            gallery: 'can_view_gallery',
            chat: 'can_chat',
            karte: 'can_view_map',
            calendar: 'can_view_calendar',
            assistant: 'can_view_assistant'
        };
        return permissionMap[sectionName] || null;
    },

    hasSectionAccess(sectionName) {
        const permission = this.getSectionPermission(sectionName);
        if (!permission) return true;
        return this.hasUserPermission(permission);
    },

    getFirstAccessibleSection(preferredSection = 'records') {
        const sectionOrder = [preferredSection, 'gallery', 'karte', 'calendar', 'dashboard'];
        const uniqueSections = [...new Set(sectionOrder)];
        return uniqueSections.find(section => this.hasSectionAccess(section)) || 'records';
    },

    async showApp() {
        // Offline-Screen ausblenden
        const offlineScreen = document.getElementById('offlineScreen');
        if (offlineScreen) offlineScreen.classList.add('hidden');
        
        document.getElementById('loginScreen').classList.add('hidden');
        document.getElementById('app').classList.add('active');
        document.getElementById('sidebarUser').textContent = this.currentUser?.username || '';
        // Admin UI
        const adminOnly = document.querySelectorAll('.admin-only');
        adminOnly.forEach(el => el.classList.toggle('hidden', this.currentUser?.role !== 'admin'));
        // Permission-based UI
        document.querySelectorAll('[data-perm]').forEach(el => {
            const perm = el.dataset.perm;
            const has = this.currentUser?.role === 'admin' || this.currentUser?.[perm];
            el.classList.toggle('hidden', !has);
        });

        // Add console to sidebar displays if admin
        if (this.currentUser?.role === 'admin' && !this.sidebarDisplays.includes('console')) {
            this.sidebarDisplays.push('console');
        }
        
        // Online/Offline Event-Listener einrichten
        this.setupOnlineOfflineListeners();

        // Prüfen ob offline und Galerie ausblenden (optional, darf App nicht blockieren)
        let isOffline = false;
        try {
            if (typeof OfflineStorage !== 'undefined') {
                isOffline = !(await OfflineStorage.isOnline());
            }
        } catch (e) {
            console.log('Offline-Check fehlgeschlagen, setze auf online:', e);
            isOffline = false;
        }

        ['records', 'archive', 'gallery', 'chat', 'karte', 'calendar', 'assistant', 'dashboard'].forEach(sectionName => {
            const hasAccess = this.hasSectionAccess(sectionName);
            // Galerie NICHT ausblenden wenn offline - sie soll sichtbar bleiben mit leeren Inhalt
            document.querySelectorAll(`.sidebar-item[data-section="${sectionName}"], .bottom-nav-item[data-section="${sectionName}"]`).forEach(el => {
                el.classList.toggle('hidden', !hasAccess);
            });
        });
        
        // Prüfen ob Offline-Modus aktiv ist
        const isOfflineMode = this.currentUser?.username === 'Offline-Modus';
        
        // Load categories (im Offline-Modus überspringen)
        if (!isOfflineMode) {
            await this.loadCategories();
        }
        
        // Load offline records from IndexedDB (optional, darf App nicht blockieren)
        try {
            await this.loadOfflineRecords();
        } catch (e) {
            console.error('Fehler beim Laden der Offline-Akten:', e);
        }
        
        // Load reminders (im Offline-Modus überspringen)
        if (!isOfflineMode) {
            this.loadReminders();
        }

        // Update chat unread count (im Offline-Modus überspringen)
        if (!isOfflineMode) {
            this.chatUpdateUnreadCount();
        }
        
        // Nutzerspezifische Auswahlfelder laden (im Offline-Modus überspringen)
        if (!isOfflineMode) {
            try {
                await this.loadUserPreferences();
            } catch (e) {
                console.error('Fehler beim Laden der Benutzereinstellungen:', e);
            }
        }
        
        const firstAccessibleSection = this.getFirstAccessibleSection('records');
        this.currentSection = firstAccessibleSection;
        this.showSection(firstAccessibleSection);
    },

    // ── User Preferences (Auswahlfelder) ───────────
    collectUserPreferences() {
        return {
            records: {
                filter: document.getElementById('recordFilter')?.value || 'recent30',
                sort: document.getElementById('recordSort')?.value || 'created_desc',
                categoryId: document.getElementById('recordCategoryFilter')?.value || '',
                searchType: this.searchType || 'all'
            },
            gallery: {
                filter: document.getElementById('galleryFilter')?.value || 'all',
                sort: document.getElementById('gallerySort')?.value || 'newest',
                categoryId: document.getElementById('galleryCategory')?.value || '',
                searchType: this.gallerySearchType || 'all'
            },
            ui: {
                darkMode: document.body.classList.contains('dark-mode')
            }
        };
    },

    applyUserPreferences(prefs) {
        if (!prefs || typeof prefs !== 'object') return;

        const records = prefs.records || {};
        if (records.filter != null) {
            const filterEl = document.getElementById('recordFilter');
            if (filterEl) filterEl.value = records.filter;
            this.updateFilterDropdownUI('recordFilterDropdown', records.filter, 'fa-filter');
        }
        if (records.sort != null) {
            const sortEl = document.getElementById('recordSort');
            if (sortEl) sortEl.value = records.sort;
            this.updateFilterDropdownUI('recordSortDropdown', records.sort, 'fa-sort-amount-down');
        }
        if (records.categoryId != null) {
            const catEl = document.getElementById('recordCategoryFilter');
            if (catEl) catEl.value = String(records.categoryId);
            this.updateFilterDropdownUI('recordCategoryFilterDropdown', String(records.categoryId), 'fa-tags');
        }
        if (records.searchType) {
            this.searchType = records.searchType;
            document.querySelectorAll('#recordsSection .search-tab').forEach(t => {
                t.classList.toggle('active', t.dataset.type === records.searchType);
            });
        }

        const gallery = prefs.gallery || {};
        if (gallery.filter != null) {
            const filterEl = document.getElementById('galleryFilter');
            if (filterEl) filterEl.value = gallery.filter;
            this.updateFilterDropdownUI('galleryFilterDropdown', gallery.filter, 'fa-filter');
        }
        if (gallery.sort != null) {
            const sortEl = document.getElementById('gallerySort');
            if (sortEl) sortEl.value = gallery.sort;
            this.updateFilterDropdownUI('gallerySortDropdown', gallery.sort, 'fa-sort-amount-down');
        }
        if (gallery.categoryId != null) {
            const catEl = document.getElementById('galleryCategory');
            if (catEl) catEl.value = String(gallery.categoryId);
            this.updateFilterDropdownUI('galleryCategoryDropdown', String(gallery.categoryId), 'fa-tags');
        }
        if (gallery.searchType) {
            this.gallerySearchType = gallery.searchType;
            document.querySelectorAll('#gallerySection .search-tab').forEach(t => {
                t.classList.toggle('active', t.dataset.type === gallery.searchType);
            });
        }

        if (prefs.ui && typeof prefs.ui.darkMode === 'boolean') {
            this.setDarkMode(prefs.ui.darkMode);
        }

        this.userPreferences = prefs;
    },

    async loadUserPreferences() {
        // Im Offline-Modus überspringen
        if (this.currentUser?.username === 'Offline-Modus') {
            console.log('Offline-Modus: User Preferences überspringen');
            return;
        }
        const data = await this.apiGet('/users/me/preferences', false);
        this.applyUserPreferences(data.preferences || {});
    },

    saveUserPreferences() {
        if (!this.currentUser) return;
        clearTimeout(this._prefsSaveTimer);
        this._prefsSaveTimer = setTimeout(() => this.persistUserPreferences(), 400);
    },

    async persistUserPreferences() {
        if (!this.currentUser) return;
        // Im Offline-Modus überspringen
        if (this.currentUser?.username === 'Offline-Modus') {
            console.log('Offline-Modus: User Preferences speichern überspringen');
            return;
        }
        try {
            const preferences = this.collectUserPreferences();
            this.userPreferences = preferences;
            await this.apiPut('/users/me/preferences', { preferences }, false);
        } catch (e) {
            console.error('Fehler beim Speichern der Benutzereinstellungen:', e);
        }
    },

    // ── Navigation ─────────────────────────────────
    async showSection(name) {
        const sectionTitles = {
            dashboard: 'Statistik',
            records: 'Akten',
            archive: 'Archiv',
            gallery: 'Galerie',
            karte: 'Karte',
            calendar: 'Kalender',
            assistant: 'Assistent',
            chat: 'Chat'
        };
        if (!this.hasSectionAccess(name)) {
            const sectionTitle = sectionTitles[name] || 'diesen Bereich';
            this.toast(`Keine Berechtigung für ${sectionTitle}`, 'error');
            return;
        }

        // Session-Aktivität bei Reiter-Wechsel aktualisieren
        this.updateSessionActivity();

        // Server-abhängige Reiter (alles außer Akten)
        const serverDependentSections = ['archive', 'gallery', 'karte', 'calendar', 'assistant', 'chat', 'dashboard', 'formTemplates', 'users', 'audit', 'settings'];
        
        // Offline-Overlay ausblenden, wenn wir zu einer Sektion wechseln
        this.hideSectionOfflineMessage();
        
        // Offline-Overlay immer zurücksetzen beim Sektionswechsel
        this.hideOfflineOverlay();
        
        // Sektion aktivieren (vor dem Offline-Check)
        const currentActive = document.querySelector('.section.active');
        const nextActive = document.getElementById(name + 'Section');
        
        if (nextActive && currentActive !== nextActive) {
            // Aktive Sektion wechseln
            if (currentActive) currentActive.classList.remove('active');
            nextActive.classList.add('active');
        }
        
        // Bei Wechsel zu Akten: Lock-Status prüfen und aktualisieren
        if (name === 'records' && this.editingId) {
            console.log('Wechsel zu Akten - prüfe Lock-Status...');
            try {
                const data = await this.apiGet(`/records/${this.editingId}/lock-info`, false);
                if (!data.locked) {
                    // Lock wurde entfernt, automatisch wieder sperren
                    console.log('Lock beim Tab-Wechsel entfernt, erneuere...');
                    await this.apiPost(`/records/${this.editingId}/lock`, null, false);
                    this.currentLock = this.editingId;
                } else if (data.locked && data.lock_info?.user_id !== this.currentUser.id) {
                    // Jemand anderes hat die Sperre
                    this.toast(`Akte wurde von ${data.lock_info.username} gesperrt`, 'warning');
                    this.currentLock = null;
                    this.stopLockCheck();
                }
            } catch (e) {
                console.warn('Lock-Prüfung beim Tab-Wechsel fehlgeschlagen:', e);
            }
        }
        
        // Offline-Check für server-abhängige Reiter (nach dem Sektionswechsel)
        if (serverDependentSections.includes(name)) {
            // Wenn manueller Offline-Modus aktiv ist, Overlay anzeigen und nicht weitermachen
            if (this.manualOfflineMode) {
                console.log(`📡 ${name}: Manueller Offline-Modus aktiv - Overlay anzeigen`);
                this.showOfflineOverlay();
                // Navigation-Status trotzdem aktualisieren
                document.querySelectorAll('.bottom-nav-item, .sidebar-item').forEach(el => {
                    el.classList.toggle('active', el.dataset.section === name);
                });
                this.currentSection = name;
                return;
            }
            
            let isOffline = false;
            
            // Nur Browser-Status prüfen (schnell und zuverlässig)
            if (!navigator.onLine) {
                isOffline = true;
                console.log(`❌ ${name} offline: Browser offline`);
            } else {
                console.log(`✅ ${name}-Zugriff erlaubt: Browser online`);
            }
            
            // Galerie-Offline-Flag setzen für renderGallery
            if (name === 'gallery') {
                this.galleryIsOffline = isOffline;
            }
            
            // Wenn offline, Offline-Meldung anzeigen und NICHT weitermachen
            if (isOffline) {
                this.showSectionOfflineMessage(sectionTitles[name] || 'diesen Bereich');
                // Navigation-Status trotzdem aktualisieren
                document.querySelectorAll('.bottom-nav-item, .sidebar-item').forEach(el => {
                    el.classList.toggle('active', el.dataset.section === name);
                });
                this.currentSection = name;
                return;
            }
        }
        
        if (this.hasChanges) {
            if (!await this.confirm('Ungespeicherte Änderungen', 'Möchten Sie den Bereich wirklich wechseln? Alle ungespeicherten Änderungen an der Akte gehen verloren.', 'Ja, wechseln', 'btn-danger')) {
                return;
            }
            this.hasChanges = false;
        }

        // Wenn ein Modal offen ist, schließen wir es beim Sektionswechsel
        if (document.querySelector('.modal-overlay.show')) {
            await this.closeModal(true);
        }
        
        // Galerie-Offline-Flag zurücksetzen beim Sektionswechsel
        if (name !== 'gallery') {
            this.galleryIsOffline = false;
        }

        this.currentSection = name;
        
        // Kartenansicht: Scrollen im App-Body deaktivieren
        const appBody = document.querySelector('.app-body');
        if (appBody) {
            appBody.style.overflow = name === 'karte' ? 'hidden' : '';
        }
        
        // Kartenansicht: Scrollen im App-Body deaktivieren (damit die Karte „steht“
        // und die Bedien-Buttons nicht durch Seiten-Scrollen „wegrutschen“).
        const appEl = document.getElementById('app');
        if (appEl) appEl.classList.toggle('karte-aktiv', name === 'karte');
        // Zusätzlich am <body> markieren (für Touch-/Gesten-Sperren auf Mobile)
        document.body?.classList.toggle('karte-aktiv', name === 'karte');

        // Update nav active states
        document.querySelectorAll('.bottom-nav-item, .sidebar-item').forEach(el => {
            el.classList.toggle('active', el.dataset.section === name);
        });

        // FAB Dynamik: Im Benutzer-Reiter öffnet der FAB den Benutzer-Modal, sonst den Akten-Modal.
        const fab = document.getElementById('mainFab');
        if (fab) {
            if (name === 'users') {
                fab.setAttribute('aria-label', 'Neuer Benutzer');
                fab.title = 'Neuer Benutzer';
                fab.dataset.perm = 'can_write';
                fab.classList.remove('hidden');
            } else if (name === 'formTemplates') {
                fab.setAttribute('aria-label', 'Neue Vorlage');
                fab.title = 'Neue Vorlage';
                fab.dataset.perm = 'can_write';
                fab.classList.remove('hidden');
            } else if (name === 'chat') {
                fab.setAttribute('aria-label', 'Neuer Chat-Raum');
                fab.title = 'Neuer Chat-Raum';
                fab.dataset.perm = 'can_chat';
                fab.classList.remove('hidden');
                // Re-apply permission visibility
                const perm = fab.dataset.perm;
                const has = this.currentUser?.role === 'admin' || this.currentUser?.[perm];
                fab.classList.toggle('hidden', !has);
            } else if (name === 'gallery' || name === 'assistant' || name === 'settings' || name === 'audit' || name === 'dashboard' || name === 'karte' || name === 'archive') {
                fab.classList.add('hidden');
            } else {
                fab.setAttribute('aria-label', 'Neue Akte');
                fab.title = 'Neue Akte';
                fab.dataset.perm = 'can_write';
                fab.classList.remove('hidden');
                // Re-apply permission visibility
                const perm = fab.dataset.perm;
                const has = this.currentUser?.role === 'admin' || this.currentUser?.[perm];
                fab.classList.toggle('hidden', !has);
            }
        }

        // Update header title
        const titles = {
            dashboard: 'Statistik',
            records: 'Akten',
            karte: 'Karte',
            calendar: 'Kalender',
            gallery: 'Galerie',
            users: 'Benutzerverwaltung',
            formTemplates: 'Formulare',
            settings: 'Einstellungen',
            audit: 'Logbuch',
            chat: 'Chat',
            archive: 'Archiv'
        };
        document.getElementById('pageTitle').textContent = titles[name] || 'ORDAMA';

        if (name === 'users') {
            this.loadUsers(false);
        } else if (name === 'formTemplates') {
            this.loadFormTemplates(false);
        } else if (name === 'audit') {
            this.loadAuditLogs(false);
        } else if (name === 'dashboard') {
            this.loadDashboard(false);
        } else if (name === 'archive') {
            this.loadArchiveRecords(false);
        } else if (name === 'records') {
            this.loadRecords(false, false);
        } else if (name === 'gallery') {
            this.loadGalleryPreferences();
            this.loadGallery(false);
        } else if (name === 'karte') {
            // Mobile: Viewport-Höhe vor Karten-Render aktualisieren (Adressleiste/Toolbar-Effekte)
            try { this.aktualisiereViewportHoehe?.(); } catch (_) {}
            if (typeof this.loadKarte === 'function') {
                // Prüfen ob eine Mehrfachauswahl aktiv ist und diese zur Karte übernehmen
                if (this.auswahlIds && this.auswahlIds.size > 0) {
                    this.karteAktiveIds = Array.from(this.auswahlIds);
                }
                
                // Karte IMMER neu laden wenn zur Karten-Ansicht gewechselt wird
                // Das stellt sicher dass die Auswahl korrekt angezeigt wird
                this.loadKarte(this.karteAktiveIds || null);
            }
            // Canvas-Größe stabilisieren und rendern
            requestAnimationFrame(() => {
                try { this.renderKarte?.(); } catch (_) {}
            });
            // Zweites Rendering nach kurzer Verzögerung für Stabilität
            setTimeout(() => {
                try { this.renderKarte?.(); } catch (_) {}
            }, 100);
        } else if (name === 'calendar') {
            this.renderCalendar();
        } else if (name === 'settings') {
            this.loadSettings(false);
        } else if (name === 'chat') {
            this.chatRestoreState();
        }

        // Close sidebar on mobile
        this.toggleSidebar(false);
    },

    setupLinkHandling() {
        // Event-Delegation für automatisch erzeugte Links
        document.addEventListener('click', (e) => {
            const link = e.target.closest('[data-auto-link="true"]');
            if (link) {
                e.preventDefault();
                e.stopPropagation();
                // Link in neuem Tab öffnen
                window.open(link.href, '_blank', 'noopener,noreferrer');
            }
        });

        // ── Erweiterter Quelltext-Schutz ────────────────
        // Rechtsklick verhindern (Erschwert das Inspizieren)
        document.addEventListener('contextmenu', e => e.preventDefault());

        // Tastenkombinationen für Entwicklertools blockieren
        document.addEventListener('keydown', e => {
            // F12 blockieren
            if (e.key === 'F12') {
                e.preventDefault();
                return false;
            }
            // Strg+U (Quelltext anzeigen) blockieren
            if (e.ctrlKey && e.key === 'u') {
                e.preventDefault();
                return false;
            }
            // Strg+Shift+I / J (Entwicklertools) blockieren
            if (e.ctrlKey && e.shiftKey && (e.key === 'I' || e.key === 'J' || e.key === 'C')) {
                e.preventDefault();
                return false;
            }
        });

        // Konsolen-Warnung für neugierige Nutzer
        console.log("%cORDAMA SICHERHEITSSYSTEM", "color: red; font-size: 30px; font-weight: bold;");
        console.log("%cDies ist ein geschütztes System. Unbefugte Eingriffe werden protokolliert.", "font-size: 16px;");
    },

    toggleSidebar(force) {
        const sb = document.getElementById('sidebar');
        const ov = document.getElementById('sidebarOverlay');
        const open = force !== undefined ? force : !sb.classList.contains('open');
        sb.classList.toggle('open', open);
        ov.classList.toggle('show', open);
    },

    // ── Statistik ──────────────────────────────────
    async loadDashboard(showLoadingOverlay = false) {
        // Wenn manueller Offline-Modus aktiv ist, nicht laden (Overlay wird in showSection angezeigt)
        if (this.manualOfflineMode) {
            console.log('📡 Dashboard: Manueller Offline-Modus aktiv - Nicht laden');
            return;
        }

        try {
            // Einheitlicher API-Call für alle Dashboard-Daten
            const response = await this.apiGet('/records/stats', showLoadingOverlay);
            const data = response.stats;
            if (!data) return;

            const statsGrid = document.getElementById('dashStatsGrid');
            if (!statsGrid) return;

            if (this.currentUser?.role === 'admin') {
                // Admin-HTML
                statsGrid.innerHTML = `
                    <div class="stat-card">
                        <div class="stat-number">${data.totalUsers || 0}</div>
                        <div class="stat-label">Benutzer</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-number">${data.adminUsers || 0}</div>
                        <div class="stat-label">Admins</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-number">${data.totalRecords || 0}</div>
                        <div class="stat-label">Gesamte Akten</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-number">${data.archivedRecords || 0}</div>
                        <div class="stat-label">Archivierte Akten</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-number">${data.totalCategories || 0}</div>
                        <div class="stat-label">Kategorien</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-number">${data.totalAttachments || 0}</div>
                        <div class="stat-label">Dateianhänge</div>
                    </div>
                `;
                statsGrid.style.gridTemplateColumns = 'repeat(3, 1fr)';
            } else {
                // Normaler Benutzer
                statsGrid.innerHTML = `
                    <div class="stat-card">
                        <div class="stat-number">${data.totalRecords || 0}</div>
                        <div class="stat-label">Gesamte Akten</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-number">${data.archivedRecords || 0}</div>
                        <div class="stat-label">Archivierte Akten</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-number">${data.totalAttachments || 0}</div>
                        <div class="stat-label">Dateianhänge</div>
                    </div>
                `;
                statsGrid.style.gridTemplateColumns = 'repeat(3, 1fr)';
            }

            // Diagramme mit den bereits geladenen Daten rendern
            this.renderStatsCharts(data);

            // Scroll-Position zurücksetzen
            setTimeout(() => {
                const dashboard = document.getElementById('dashboardSection');
                if (dashboard) dashboard.scrollTop = 0;
            }, 50);
        } catch (e) {
            console.error('Fehler beim Laden der Statistik:', e);
            this.toast('Fehler beim Laden der Statistik', 'error');
        }
    },

    // ── Statistik-Diagramme ─────────────────────────────
    renderStatsCharts(stats) {
        try {
            if (!stats) return;
            const isDark = document.body.classList.contains('dark-mode');
            
            // 1. GLOBALE DEFAULTS FÜR CHART.JS (Erzwingt absolute Einheitlichkeit)
            Chart.defaults.font.family = "'Segoe UI', system-ui, -apple-system, sans-serif";
            Chart.defaults.font.size = 12;
            Chart.defaults.font.weight = 400;
            Chart.defaults.color = isDark ? '#b0b0b0' : '#6c757d'; // Entspricht .chart-title Farbe
            
            // Gemeinsame Optionen für alle Diagramme
            const commonOptions = {
                responsive: true,
                maintainAspectRatio: false,
                animation: { duration: 0 },
                plugins: {
                    legend: {
                        position: 'bottom',
                        labels: {
                            padding: 20,
                            usePointStyle: true,
                            font: { size: 12 }
                        }
                    },
                    tooltip: {
                        backgroundColor: isDark ? '#2d2d2d' : '#fff',
                        titleColor: isDark ? '#fff' : '#2c3e50',
                        bodyColor: isDark ? '#ccc' : '#666',
                        borderColor: isDark ? '#444' : '#ddd',
                        borderWidth: 1,
                        padding: 10,
                        cornerRadius: 8,
                        displayColors: true
                    }
                }
            };

            // 2. Status Chart
            const statusCtx = document.getElementById('statusChart');
            if (statusCtx) {
                if (this.statusChartInstance) this.statusChartInstance.destroy();
                
                const statusLabels = {
                    'neutral': 'Neutral',
                    'offen': 'Offen',
                    'bearbeitung': 'In Bearbeitung',
                    'erledigt': 'Erledigt'
                };
                
                const labels = Object.keys(stats.status_distribution).map(k => statusLabels[k] || k);
                const values = Object.values(stats.status_distribution);
                const colors = [
                    'rgba(108, 117, 125, 0.7)', // neutral - grau
                    'rgba(245, 158, 11, 0.7)',   // offen - gelb
                    'rgba(0, 123, 255, 0.7)',   // bearbeitung - blau
                    'rgba(40, 167, 69, 0.7)'    // erledigt - grün
                ];

                this.statusChartInstance = new Chart(statusCtx, {
                    type: 'doughnut',
                    data: {
                        labels: labels,
                        datasets: [{
                            data: values,
                            backgroundColor: colors,
                            borderWidth: 0
                        }]
                    },
                    options: {
                        ...commonOptions,
                        cutout: '70%',
                        maintainAspectRatio: false
                    }
                });
            }

            // 3. File Type Chart
            const fileCtx = document.getElementById('fileTypeChart');
            if (fileCtx) {
                if (this.fileChartInstance) this.fileChartInstance.destroy();
                
                const labels = ['PDF', 'Bilder', 'Sonstiges'];
                const values = [
                    stats.attachment_types.pdf || 0,
                    stats.attachment_types.image || 0,
                    stats.attachment_types.other || 0
                ];
                const colors = [
                    'rgba(231, 76, 60, 0.7)',  // PDF - rot
                    'rgba(52, 152, 219, 0.7)', // Bilder - blau
                    'rgba(149, 165, 166, 0.7)' // Sonstiges - grau
                ];

                this.fileChartInstance = new Chart(fileCtx, {
                    type: 'doughnut',
                    data: {
                        labels: labels,
                        datasets: [{
                            data: values,
                            backgroundColor: colors,
                            borderWidth: 0
                        }]
                    },
                    options: {
                        ...commonOptions,
                        cutout: '70%',
                        maintainAspectRatio: false
                    }
                });
            }

            // 4. Category Chart
            const catCtx = document.getElementById('categoryChart');
            if (catCtx) {
                if (this.catChartInstance) this.catChartInstance.destroy();
                
                const labels = Object.keys(stats.category_distribution);
                const values = Object.values(stats.category_distribution);
                
                // Sortieren nach Anzahl (absteigend)
                const sortedData = labels.map((label, i) => ({ label, value: values[i] }))
                    .sort((a, b) => b.value - a.value);
                
                const sortedLabels = sortedData.map(d => d.label);
                const sortedValues = sortedData.map(d => d.value);
                
                const colors = [
                    'rgba(59, 130, 246, 0.7)', 'rgba(16, 185, 129, 0.7)', 
                    'rgba(245, 158, 11, 0.7)', 'rgba(139, 92, 246, 0.7)', 
                    'rgba(236, 72, 153, 0.7)', 'rgba(239, 68, 68, 0.7)', 
                    'rgba(6, 182, 212, 0.7)', 'rgba(20, 184, 166, 0.7)'
                ];

                this.catChartInstance = new Chart(catCtx, {
                    type: 'doughnut',
                    data: {
                        labels: sortedLabels,
                        datasets: [{
                            data: sortedValues,
                            backgroundColor: colors,
                            borderWidth: 0
                        }]
                    },
                    options: {
                        ...commonOptions,
                        cutout: '60%',
                        maintainAspectRatio: false,
                        plugins: {
                            ...commonOptions.plugins,
                            legend: { display: false },
                            tooltip: {
                                callbacks: {
                                    label: function(context) {
                                        const label = context.label || '';
                                        const value = context.raw || 0;
                                        const total = context.dataset.data.reduce((a, b) => a + b, 0);
                                        const percentage = ((value / total) * 100).toFixed(1);
                                        return `${label}: ${value} (${percentage}%)`;
                                    }
                                }
                            }
                        }
                    }
                });
            }

            // 5. Color Chart
            const colorCtx = document.getElementById('colorChart');
            if (colorCtx) {
                if (this.colorChartInstance) this.colorChartInstance.destroy();
                
                const colorMap = { 
                    '': 'Keine', 
                    'border-red': 'Rot', 
                    'border-blue': 'Blau', 
                    'border-yellow': 'Gelb', 
                    'border-green': 'Grün', 
                    'border-magenta': 'Magenta',
                    'red': 'Rot',
                    'blue': 'Blau',
                    'yellow': 'Gelb',
                    'green': 'Grün',
                    'magenta': 'Magenta'
                };
                
                // Filtere nur Farben mit border- Präfix und leere Werte heraus
                const colorKeys = Object.keys(stats.color_distribution).filter(k => {
                    return k && k !== '' && k !== null && k.startsWith('border-');
                });
                
                const labels = colorKeys.map(k => {
                    // Entferne 'border-' Präfix falls vorhanden und mappe den Namen
                    const key = k.replace('border-', '');
                    return colorMap[k] || colorMap[key] || k;
                });
                const values = colorKeys.map(k => stats.color_distribution[k]);
                const bgColors = colorKeys.map(k => {
                    const key = k.replace('border-', '');
                    switch(key) {
                        case 'red': return 'rgba(220, 53, 69, 0.7)';
                        case 'blue': return 'rgba(0, 123, 255, 0.7)';
                        case 'yellow': return 'rgba(255, 193, 7, 0.7)';
                        case 'green': return 'rgba(40, 167, 69, 0.7)';
                        case 'magenta': return 'rgba(255, 0, 255, 0.7)';
                        default: 
                            // Fallback: Versuche den originalen key
                            switch(k) {
                                case 'border-red': return 'rgba(220, 53, 69, 0.7)';
                                case 'border-blue': return 'rgba(0, 123, 255, 0.7)';
                                case 'border-yellow': return 'rgba(255, 193, 7, 0.7)';
                                case 'border-green': return 'rgba(40, 167, 69, 0.7)';
                                case 'border-magenta': return 'rgba(255, 0, 255, 0.7)';
                                default: return 'rgba(108, 117, 125, 0.7)';
                            }
                    }
                });

                this.colorChartInstance = new Chart(colorCtx, {
                    type: 'bar',
                    data: {
                        labels: labels,
                        datasets: [{
                            label: 'Markierungen',
                            data: values,
                            backgroundColor: bgColors,
                            borderRadius: 5
                        }]
                    },
                    options: {
                        ...commonOptions,
                        plugins: { ...commonOptions.plugins, legend: { display: false } },
                        scales: {
                            y: { grid: { color: isDark ? '#333' : '#eee' }, ticks: { stepSize: 1 } },
                            x: { grid: { display: false } }
                        }
                    }
                });
            }

            // 6. Trend Chart
            const trendCtx = document.getElementById('trendChart');
            if (trendCtx) {
                if (this.trendChartInstance) this.trendChartInstance.destroy();
                
                this.trendChartInstance = new Chart(trendCtx, {
                    type: 'line',
                    data: {
                        labels: stats.creation_trend.labels,
                        datasets: [{
                            label: 'Neue Akten',
                            data: stats.creation_trend.values,
                            borderColor: '#3b82f6',
                            backgroundColor: 'rgba(59, 130, 246, 0.1)',
                            fill: true,
                            tension: 0.4,
                            pointRadius: 4,
                            pointBackgroundColor: '#3b82f6'
                        }]
                    },
                    options: {
                        ...commonOptions,
                        scales: {
                            y: { grid: { color: isDark ? '#333' : '#eee' }, ticks: { stepSize: 1 } },
                            x: { grid: { display: false } }
                        }
                    }
                });
            }

            // 7. Archive Trend Chart
            const archiveTrendCtx = document.getElementById('archiveTrendChart');
            if (archiveTrendCtx) {
                if (this.archiveTrendChartInstance) this.archiveTrendChartInstance.destroy();
                
                this.archiveTrendChartInstance = new Chart(archiveTrendCtx, {
                    type: 'line',
                    data: {
                        labels: stats.archive_trend.labels,
                        datasets: [{
                            label: 'Archivierte Akten',
                            data: stats.archive_trend.values,
                            borderColor: '#f59e0b',
                            backgroundColor: 'rgba(245, 158, 11, 0.1)',
                            fill: true,
                            tension: 0.4,
                            pointRadius: 4,
                            pointBackgroundColor: '#f59e0b'
                        }]
                    },
                    options: {
                        ...commonOptions,
                        scales: {
                            y: { grid: { color: isDark ? '#333' : '#eee' }, ticks: { stepSize: 1 } },
                            x: { grid: { display: false } }
                        }
                    }
                });
            }

            // 8. Storage Disk Chart (Partition)
            const storageDiskCtx = document.getElementById('storageDiskChart');
            if (storageDiskCtx) {
                if (this.storageDiskChartInstance) this.storageDiskChartInstance.destroy();
                
                if (stats.storage) {
                    const mainUsed = stats.storage.total_disk_bytes - stats.storage.free_disk_bytes;
                    const mainFree = stats.storage.free_disk_bytes;
                    const backupUsed = stats.storage.backup ? stats.storage.backup.used_bytes : 0;
                    const backupFree = stats.storage.backup ? stats.storage.backup.free_bytes : 0;
                    
                    this.storageDiskChartInstance = new Chart(storageDiskCtx, {
                        type: 'bar',
                        data: {
                            labels: ['Hauptspeicher', 'Backup-Speicher'],
                            datasets: [
                                { label: 'Belegt', data: [mainUsed, backupUsed], backgroundColor: 'rgba(108, 117, 125, 0.7)', borderWidth: 0 },
                                { label: 'Verfügbar', data: [mainFree, backupFree], backgroundColor: 'rgba(40, 167, 69, 0.7)', borderWidth: 0 }
                            ]
                        },
                        options: {
                            ...commonOptions,
                            indexAxis: 'y',
                            scales: {
                                x: { stacked: true, display: false },
                                y: { stacked: true, grid: { display: false }, ticks: { crossAlign: 'center', padding: 10 } }
                            },
                            plugins: {
                                ...commonOptions.plugins,
                                tooltip: {
                                    callbacks: {
                                        label: (context) => `${context.dataset.label}: ${this.formatBytes(context.parsed.x)}`
                                    }
                                }
                            }
                        }
                    });
                }
            }

            // 7. Storage Program Info (ORDAMA Verbrauch)
            const usedText = document.getElementById('storageUsedText');
            const totalText = document.getElementById('storageTotalText');
            const progressBar = document.getElementById('storageProgressBar');
            
            if (stats.storage) {
                if (usedText) usedText.textContent = this.formatBytes(stats.storage.program_used_bytes);
                if (totalText) totalText.textContent = this.formatBytes(stats.storage.total_disk_bytes);
                
                if (progressBar) {
                    const totalUsedPercent = ( (stats.storage.total_disk_bytes - stats.storage.free_disk_bytes) / stats.storage.total_disk_bytes * 100);
                    progressBar.style.width = totalUsedPercent + '%';
                    progressBar.style.backgroundColor = totalUsedPercent > 90 ? '#ef4444' : (totalUsedPercent > 75 ? '#f59e0b' : '#3b82f6');
                }
            } else {
                if (usedText) usedText.textContent = 'N/A';
                if (totalText) totalText.textContent = 'N/A';
                if (progressBar) progressBar.style.width = '0%';
            }

        } catch (e) {
            console.error('Fehler beim Laden der Statistik-Diagramme:', e);
        }
    },

    // ── Kalender-Diagramm ─────────────────────────────
    // Veraltet - wurde durch renderStatsCharts ersetzt
    async renderCalendarChart(showLoadingOverlay = false) {
        return;
    },

    // ── Kategorien (Ablage) ─────────────────────────
    async loadCategories() {
        // Im Offline-Modus leere Liste verwenden
        if (this.currentUser?.username === 'Offline-Modus') {
            console.log('Offline-Modus: Kategorien überspringen');
            this.categories = [];
            this.renderCategoryFilters();
            this.updateRecordCategoryDropdown();
            return;
        }
        try {
            const data = await this.apiGet('/categories');
            this.categories = data.categories || [];
            this.renderCategoryFilters();
            this.updateRecordCategoryDropdown();
            this.renderCategoryManageList();
            this.updateBulkMoveDropdown();
            this.loadGalleryCategories();
        } catch (e) {
            console.error('Fehler beim Laden der Kategorien:', e);
        }
    },

    renderCategoryFilters() {
        const menu = document.getElementById('recordCategoryFilterMenu');
        const input = document.getElementById('recordCategoryFilter');
        if (!menu || !input) return;

        const currentValue = input.value;
        menu.innerHTML = '<button type="button" data-value="">Alle Kategorien</button>';

        // Add "Neue Kategorie erstellen" option for admins
        let newCatBtn = null;
        if (this.currentUser && this.currentUser.role === 'admin') {
            newCatBtn = document.createElement('button');
            newCatBtn.type = 'button';
            newCatBtn.innerHTML = '<i class="fas fa-plus"></i> Neue Kategorie erstellen';
            newCatBtn.style.fontWeight = '600';
            newCatBtn.style.borderBottom = '1px solid var(--border-color)';
            newCatBtn.style.marginBottom = '8px';
            newCatBtn.style.paddingBottom = '8px';
            newCatBtn.onclick = () => {
                this.showCategoryModal();
                menu.closest('.custom-filter-dropdown').classList.remove('show');
            };
            menu.appendChild(newCatBtn);
        }

        this.categories.forEach(cat => {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.dataset.value = cat.id;
            btn.textContent = cat.name;
            if (cat.id === currentValue) btn.classList.add('selected');
            menu.appendChild(btn);
        });

        // UI aktualisieren falls der Wert noch existiert
        this.updateFilterDropdownUI('recordCategoryFilterDropdown', currentValue, 'fa-tags');

        // Auch Archiv-Kategorien befüllen
        this.renderArchiveCategoryFilters();
    },

    renderArchiveCategoryFilters() {
        const menu = document.getElementById('archiveCategoryFilterMenu');
        const input = document.getElementById('archiveCategoryFilter');
        if (!menu || !input) return;

        const currentValue = input.value;
        menu.innerHTML = '<button type="button" data-value="">Alle Kategorien</button>';

        this.categories.forEach(cat => {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.dataset.value = cat.id;
            btn.textContent = cat.name;
            if (cat.id === currentValue) btn.classList.add('selected');
            menu.appendChild(btn);
        });

        // UI aktualisieren falls der Wert noch existiert
        this.updateFilterDropdownUI('archiveCategoryFilterDropdown', currentValue, 'fa-tags');
    },

    updateRecordCategoryDropdown() {
        const dropdown = document.getElementById('modalCategoryDropdown');
        if (!dropdown) return;
        const menu = dropdown.querySelector('.dropdown-menu');
        const input = document.getElementById('recordCategory');
        const toggle = dropdown.querySelector('.dropdown-toggle');
        const currentValue = input.value;
        
        menu.innerHTML = '<button type="button" data-value=""><i class="fas fa-tag"></i> <span>Keine Kategorie</span></button>';
        
        // Add "Neue Kategorie erstellen" option for admins
        let newCatBtn = null;
        if (this.currentUser && this.currentUser.role === 'admin') {
            newCatBtn = document.createElement('button');
            newCatBtn.type = 'button';
            newCatBtn.innerHTML = '<i class="fas fa-plus"></i> <span>Neue Kategorie erstellen</span>';
            newCatBtn.style.fontWeight = '600';
            newCatBtn.style.borderBottom = '1px solid var(--border-color)';
            newCatBtn.style.marginBottom = '8px';
            newCatBtn.style.paddingBottom = '8px';
            newCatBtn.onclick = () => {
                this.showCategoryModal();
                dropdown.classList.remove('show');
            };
            menu.appendChild(newCatBtn);
        }
        
        this.categories.forEach(cat => {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.dataset.value = cat.id;
            btn.innerHTML = `<i class="fas fa-tag"></i> <span>${this.escapeHtml(cat.name)}</span>`;
            if (cat.id == currentValue) btn.classList.add('selected');
            menu.appendChild(btn);
        });
        
        // Re-attach click listeners to new buttons (except the new category button)
        menu.querySelectorAll('button').forEach(btn => {
            if (btn === newCatBtn) return; // Skip the "Neue Kategorie erstellen" button
            btn.addEventListener('click', () => {
                const val = btn.dataset.value;
                input.value = val;
                toggle.innerHTML = btn.innerHTML;
                dropdown.classList.remove('show');
                this.hasChanges = true;
                // selected-Klasse aktualisieren
                menu.querySelectorAll('button').forEach(b => b.classList.remove('selected'));
                btn.classList.add('selected');
            });
        });
        
        this.updateModalDropdownUI('modalCategoryDropdown', currentValue);
    },

    updateBulkMoveDropdown() {
        // Wird in mehrfachauswahl.js initialisiert, falls vorhanden
        if (typeof this.updateBulkMoveDropdownMod === 'function') {
            this.updateBulkMoveDropdownMod();
        }
    },

    renderCategoryManageList() {
        const list = this.dom.categoryManageList;
        if (!list) return;

        list.innerHTML = '';
        this.categories.forEach(cat => {
            const badge = document.createElement('button');
            badge.type = 'button';
            badge.className = 'search-tab';
            badge.innerHTML = `<i class="fas fa-tag"></i> ${this.escapeHtml(cat.name)}`;
            badge.onclick = () => this.editCategory(cat);
            list.appendChild(badge);
        });
    },

    editCategory(cat) {
        document.getElementById('categoryId').value = cat.id;
        document.getElementById('categoryName').value = cat.name;
        document.getElementById('categoryModalTitle').textContent = 'Kategorie bearbeiten';
        
        const btn = document.getElementById('closeOrDeleteCategoryBtn');
        btn.textContent = 'Löschen';
        btn.classList.remove('btn-secondary');
        btn.classList.add('btn-danger');
        btn.onclick = () => this.deleteCategory();
    },

    showCategoryModal() {
        this.dom.categoryForm.reset();
        document.getElementById('categoryId').value = '';
        document.getElementById('categoryModalTitle').textContent = 'Kategorie erstellen';
        
        const btn = document.getElementById('closeOrDeleteCategoryBtn');
        btn.textContent = 'Schließen';
        btn.classList.remove('btn-danger');
        btn.classList.add('btn-secondary');
        btn.onclick = () => this.closeCategoryModal();
        
        this.dom.categoryModalOverlay.classList.add('show');
        document.body.style.overflow = 'hidden';
    },

    closeCategoryModal() {
        this.dom.categoryForm.reset();
        document.getElementById('categoryId').value = '';
        document.getElementById('categoryModalTitle').textContent = 'Kategorie erstellen';
        
        // Reset the button to "Schließen"
        const btn = document.getElementById('closeOrDeleteCategoryBtn');
        btn.textContent = 'Schließen';
        btn.classList.remove('btn-danger');
        btn.classList.add('btn-secondary');
        btn.onclick = () => this.closeCategoryModal();
        
        this.dom.categoryModalOverlay.classList.remove('show');
        document.body.style.overflow = '';
    },

    async saveCategory(e) {
        if (e) e.preventDefault();
        const id = document.getElementById('categoryId').value;
        const name = document.getElementById('categoryName').value.trim();

        if (!name) return;

        try {
            if (id) {
                await this.apiPut(`/categories/${id}`, { name });
                this.toast('Kategorie aktualisiert', 'success');
            } else {
                await this.apiPost('/categories', { name });
                this.toast('Kategorie erstellt', 'success');
            }
            this.loadCategories();
            this.dom.categoryForm.reset();
            document.getElementById('categoryId').value = '';
            document.getElementById('categoryModalTitle').textContent = 'Kategorie erstellen';
            
            // Reset the button to "Schließen"
            const btn = document.getElementById('closeOrDeleteCategoryBtn');
            btn.textContent = 'Schließen';
            btn.classList.remove('btn-danger');
            btn.classList.add('btn-secondary');
            btn.onclick = () => this.closeCategoryModal();
        } catch (e) {
            this.toast(e.message, 'error');
        }
    },

    async deleteCategory() {
        const id = document.getElementById('categoryId').value;
        if (!id) return;

        if (!await this.confirm('Kategorie löschen?', 'Die Akten bleiben erhalten, werden aber aus dieser Kategorie entfernt.')) return;

        try {
            await this.apiDelete(`/categories/${id}`);
            this.toast('Kategorie gelöscht', 'success');
            this.loadCategories();
            this.dom.categoryForm.reset();
            document.getElementById('categoryId').value = '';
            document.getElementById('categoryModalTitle').textContent = 'Kategorie erstellen';
            
            // Reset the button to "Schließen"
            const btn = document.getElementById('closeOrDeleteCategoryBtn');
            btn.textContent = 'Schließen';
            btn.classList.remove('btn-danger');
            btn.classList.add('btn-secondary');
            btn.onclick = () => this.closeCategoryModal();
        } catch (e) {
            this.toast(e.message, 'error');
        }
    },

    // ── Records ────────────────────────────────────
    async loadSimilarRecords(searchQuery = null, referenceRecordId = null) {
        try {
            // Limit aus den geladenen Settings holen
            const similarityLimit = this.settings?.similarity_limit || 20;
            
            const params = new URLSearchParams({
                limit: parseInt(similarityLimit),
                offset: 0,
                min_similarity: 0.1
            });
            
            if (searchQuery) {
                params.set('search_query', searchQuery);
            }
            if (referenceRecordId) {
                params.set('reference_record_id', referenceRecordId);
            }
            
            const data = await this.apiGet(`/records/similar?${params.toString()}`, true);
            
            if (data.success) {
                this.records = data.records || [];
                this.paginationInfo = data.pagination;
                
                // Such-ID für Klick-Tracking speichern
                this.currentSearchLogId = data.search_log_id || null;
                
                this.renderRecords();
                this.toast(`${data.records.length} ähnliche Akten gefunden`, 'success');
            } else {
                this.toast(data.error || 'Fehler bei Ähnlichkeitssuche', 'error');
            }
        } catch (e) {
            console.error('Fehler bei Ähnlichkeitssuche:', e);
            this.toast('Fehler bei Ähnlichkeitssuche: ' + e.message, 'error');
        }
    },

    async loadRecords(loadMore = false, showLoadingOverlay = false, bypassCache = false) {
        try {
            // Bei neuem Laden (Suche/Filter) Auswahlmodus NICHT beenden - nur Auswahl leeren
            if (!loadMore && typeof this.auswahlIds !== 'undefined') {
                this.auswahlIds.clear();
                if (typeof this._aktualisiereAuswahlToolbar === 'function') {
                    this._aktualisiereAuswahlToolbar();
                }
            }

            const searchEl = document.getElementById('recordsSearch');
            const filterEl = document.getElementById('recordFilter');
            const categoryEl = document.getElementById('recordCategoryFilter');

            const search = searchEl ? searchEl.value.trim() : '';
            let filter = filterEl ? filterEl.value : 'all';
            const categoryId = categoryEl ? categoryEl.value : '';
            
            // Update search button icon when loading records
            this.updateSearchButtonIcon();

            // Filter UI aktualisieren (falls durch JS gesetzt)
            this.updateFilterDropdownUI('recordFilterDropdown', filter, 'fa-filter');
            this.updateFilterDropdownUI('recordCategoryFilterDropdown', categoryId, 'fa-tags');

            // Farbfilter verarbeiten
            let colorFilter = null;
            if (filter.startsWith('color_')) {
                const colorMap = {
                    'color_standard': '',
                    'color_red': 'border-red',
                    'color_yellow': 'border-yellow',
                    'color_green': 'border-green',
                    'color_blue': 'border-blue',
                    'color_magenta': 'border-magenta'
                };
                colorFilter = colorMap[filter];
                // Für Farbfilter setzen wir filter auf 'all', damit nicht nach Status gefiltert wird
                filter = 'all';
            }

            // Offline-Akten immer aus IndexedDB laden, um sicherzustellen dass sie vorhanden sind
            let offlineRecords = [];
            console.log(`🔍 Lade Offline-Akten aus IndexedDB...`);
            
            // Immer aus IndexedDB laden, um sicherzustellen dass alle Offline-Akten vorhanden sind
            if (typeof OfflineStorage !== 'undefined') {
                try {
                    const pendingRecords = await OfflineStorage.getPendingRecords();
                    if (pendingRecords.length > 0) {
                        offlineRecords = pendingRecords.map(record => {
                            const displayId = record.temp_id || `offline_${record.id}`;
                            // Erinnerungen-Array erstellen (aus pending_reminder oder erinnerungen)
                            const erinnerungenArray = record.erinnerungen || [];
                            if (record.pending_reminder && !erinnerungenArray.some(e => e.reminder_date === record.pending_reminder.reminder_date)) {
                                erinnerungenArray.push({
                                    id: Date.now(), // Temporäre ID
                                    reminder_date: record.pending_reminder.reminder_date,
                                    assigned_to: record.pending_reminder.assigned_to,
                                    note: record.pending_reminder.note,
                                    completed: 0,
                                    created_by: record.user_id,
                                    created_by_username: record.user_name
                                });
                            }
                            
                            return {
                                ...record,
                                id: displayId,
                                is_offline: true,
                                created_at: record.created_at,
                                created_by_name: record.user_name || record.created_by_name || 'Unbekannt', // Benutzername für Anzeige
                                attachments: [],
                                erinnerungen: erinnerungenArray, // Erinnerungen für Glocken-Anzeige
                                _indexedDbId: record.id,
                                temp_id: record.temp_id,
                                temp_record_id: record.temp_id
                            };
                        });
                        console.log(`📊 ${offlineRecords.length} Offline-Akten aus IndexedDB geladen`);
                    } else {
                        console.log(`📊 Keine Offline-Akten in IndexedDB gefunden`);
                    }
                } catch (e) {
                    console.error('❌ Fehler beim Laden von Offline-Akten aus IndexedDB:', e);
                }
            }

            // Erinnerungs-Filter benötigen höheres Limit, da clientseitig gefiltert wird
            const isReminderFilter = ['has_reminders', 'has_my_reminders', 'expired_termine', 'expired_erinnerungn'].includes(filter);
            const limit = isReminderFilter ? 500 : 50;

            const params = new URLSearchParams({
                filter,
                search_type: this.searchType,
                limit: limit,
                offset: loadMore ? this.records.length : 0
            });
            if (search) params.set('search', search);
            if (categoryId) params.set('category_id', categoryId);
            if (colorFilter !== null) params.set('border_color', colorFilter);

            // Nur Online-Akten laden, wenn Server verfügbar ist und nicht manueller Offline-Modus
            let data;
            let serverAvailable = true;
            
            // Wenn manueller Offline-Modus aktiv ist, API-Call überspringen
            if (this.manualOfflineMode) {
                console.log('🔒 Manueller Offline-Modus - API-Call übersprungen');
                serverAvailable = false;
                data = { records: [], pagination: null };
            } else {
                try {
                    data = await this.apiGet(`/records?${params.toString()}`, showLoadingOverlay);
                } catch (e) {
                    console.log('❌ Server nicht erreichbar, zeige nur Offline-Akten');
                    serverAvailable = false;
                    data = { records: [], pagination: null };
                }
            }

            // If reminder filter is active, only keep records that are in this.reminders (user-specific)
            let filteredRecords = data.records || [];
            if (this.reminderFilterActive) {
                const today = new Date();
                today.setHours(0,0,0,0);
                const reminderRecordIds = new Set(
                    this.reminders
                        .filter(r => {
                            if (r.completed !== 0) return false;
                            if (r.assigned_to !== null && r.assigned_to !== this.currentUser?.id) return false;
                            const reminderDate = new Date(r.reminder_date);
                            reminderDate.setHours(0,0,0,0);
                            return reminderDate.getTime() === today.getTime();
                        })
                        .map(r => r.record_id)
                );
                filteredRecords = filteredRecords.filter(record => reminderRecordIds.has(record.id));
            } else if (filter === 'has_reminders') {
                // For has_reminders filter, keep records that have any reminder (from any user, completed or not)
                const reminderRecordIds = new Set(this.reminders.map(r => r.record_id));
                filteredRecords = filteredRecords.filter(record => reminderRecordIds.has(record.id));
            } else if (filter === 'has_my_reminders') {
                // For has_my_reminders filter, keep records that have reminders assigned to current user (completed or not)
                const reminderRecordIds = new Set(
                    this.reminders
                        .filter(r => {
                            // Only include reminders assigned to current user
                            return r.assigned_to === this.currentUser?.id;
                        })
                        .map(r => r.record_id)
                );
                filteredRecords = filteredRecords.filter(record => reminderRecordIds.has(record.id));
            } else if (filter === 'expired_termine') {
                // For expired_termine filter, keep records that have expired calendar terms (reminder_date in records table)
                const today = new Date();
                today.setHours(0, 0, 0, 0);
                filteredRecords = filteredRecords.filter(record => {
                    if (!record.reminder_date) return false;
                    const reminderDate = new Date(record.reminder_date);
                    reminderDate.setHours(0, 0, 0, 0);
                    return reminderDate < today;
                });
            } else if (filter === 'expired_erinnerungn') {
                // For expired_erinnerungn filter, keep records that have expired erinnerungn (reminders table)
                const today = new Date();
                today.setHours(0, 0, 0, 0);
                const expiredReminderRecordIds = new Set(
                    this.reminders
                        .filter(r => {
                            if (r.completed === 1) return false;
                            const reminderDate = new Date(r.reminder_date);
                            reminderDate.setHours(0, 0, 0, 0);
                            return reminderDate < today;
                        })
                        .map(r => r.record_id)
                );
                filteredRecords = filteredRecords.filter(record => expiredReminderRecordIds.has(record.id));
            }

            // Offline-Akten vor dem Überschreiben speichern, um Daten wie erinnerungen und created_by_name zu erhalten
            const existingOfflineRecords = this.records.filter(r => r.is_offline);
            
            if (loadMore) {
                // Append new records to existing ones
                this.records = [...this.records, ...filteredRecords];
            } else {
                // Replace all records for new search/filter
                this.records = filteredRecords;
            }
            
            // Offline-Akten nur beim ersten Laden hinzufügen (loadMore = false), um Duplikate bei Pagination zu vermeiden
            let offlineToAdd = loadMore ? [] : offlineRecords;
            
            // Such-Logik auf Offline-Akten anwenden
            if (search) {
                const searchLower = search.toLowerCase();
                offlineToAdd = offlineToAdd.filter(record => {
                    const titleMatch = record.title && record.title.toLowerCase().includes(searchLower);
                    const contentMatch = record.content && record.content.toLowerCase().includes(searchLower);
                    const addressMatch = record.address && record.address.toLowerCase().includes(searchLower);
                    const hashtagMatch = record.hashtags && record.hashtags.some(tag => tag.toLowerCase().includes(searchLower));
                    return titleMatch || contentMatch || addressMatch || hashtagMatch;
                });
                console.log(`🔍 Suche "${search}" ergab ${offlineToAdd.length} Offline-Akten`);
            }
            
            // Kategorie-Filter auf Offline-Akten anwenden
            if (categoryId) {
                offlineToAdd = offlineToAdd.filter(record => record.category_id == categoryId);
                console.log(`🏷️ Kategorie-Filter ${categoryId} ergab ${offlineToAdd.length} Offline-Akten`);
            }
            
            // Farbfilter auf Offline-Akten anwenden
            if (colorFilter !== null) {
                offlineToAdd = offlineToAdd.filter(record => record.border_color === colorFilter);
                console.log(`🎨 Farbfilter ${colorFilter} ergab ${offlineToAdd.length} Offline-Akten`);
            }
            
            // Status-Filter auf Offline-Akten anwenden (mit "status_" Präfix-Entfernung)
            if (filter.startsWith('status_')) {
                console.log(`📊 Wende Status-Filter ${filter} auf Offline-Akten an...`);
                console.log(`📊 Offline-Akten vor Filter:`, offlineToAdd.map(r => ({ id: r.id, status: r.status })));
                // "status_" Präfix entfernen für den Vergleich
                const statusFilter = filter.substring(7);
                offlineToAdd = offlineToAdd.filter(record => record.status === statusFilter);
                console.log(`📊 Status-Filter ${filter} (als ${statusFilter}) ergab ${offlineToAdd.length} Offline-Akten`);
            }
            
            // Erinnerungs-Filter auf Offline-Akten anwenden
            if (filter === 'has_reminders') {
                // Offline-Akten mit erinnerungen Array (nur echte Erinnerungen, keine Termine)
                offlineToAdd = offlineToAdd.filter(record => {
                    return record.erinnerungen && Array.isArray(record.erinnerungen) && record.erinnerungen.length > 0;
                });
                console.log(`📊 Erinnerungs-Filter ${filter} ergab ${offlineToAdd.length} Offline-Akten`);
            } else if (filter === 'has_my_reminders') {
                // Offline-Akten mit erinnerungen für den aktuellen Benutzer
                offlineToAdd = offlineToAdd.filter(record => {
                    if (record.erinnerungen && Array.isArray(record.erinnerungen)) {
                        return record.erinnerungen.some(er => er.assigned_to === this.currentUser?.id);
                    }
                    return false;
                });
                console.log(`📊 Erinnerungs-Filter ${filter} ergab ${offlineToAdd.length} Offline-Akten`);
            } else if (filter === 'expired_termine') {
                // Offline-Akten mit abgelaufenem reminder_date (Termine)
                const today = new Date();
                today.setHours(0, 0, 0, 0);
                offlineToAdd = offlineToAdd.filter(record => {
                    if (!record.reminder_date) return false;
                    const reminderDate = new Date(record.reminder_date);
                    reminderDate.setHours(0, 0, 0, 0);
                    return reminderDate < today;
                });
                console.log(`📊 Erinnerungs-Filter ${filter} ergab ${offlineToAdd.length} Offline-Akten`);
            } else if (filter === 'expired_erinnerungen') {
                // Offline-Akten mit abgelaufenen erinnerungen (im erinnerungen Array, keine Termine)
                const today = new Date();
                today.setHours(0, 0, 0, 0);
                offlineToAdd = offlineToAdd.filter(record => {
                    if (record.erinnerungen && Array.isArray(record.erinnerungen)) {
                        const hasExpired = record.erinnerungen.some(er => {
                            if (er.completed === 1) return false;
                            const reminderDate = new Date(er.reminder_date);
                            reminderDate.setHours(0, 0, 0, 0);
                            return reminderDate < today;
                        });
                        if (hasExpired) return true;
                    }
                    return false;
                });
                console.log(`📊 Erinnerungs-Filter ${filter} ergab ${offlineToAdd.length} Offline-Akten`);
            } else if (filter === 'has_termine') {
                // Offline-Akten mit reminder_date (Termine)
                offlineToAdd = offlineToAdd.filter(record => {
                    return record.reminder_date;
                });
                console.log(`📊 Erinnerungs-Filter ${filter} ergab ${offlineToAdd.length} Offline-Akten`);
            } else if (filter === 'has_my_termine') {
                // Offline-Akten mit reminder_date für den aktuellen Benutzer
                offlineToAdd = offlineToAdd.filter(record => {
                    if (!record.reminder_date) return false;
                    // Prüfen ob der Termin für den aktuellen Benutzer sichtbar ist
                    // reminder_assigned_to == null bedeutet "für alle sichtbar"
                    // reminder_assigned_to == current user bedeutet "nur für mich sichtbar"
                    return record.reminder_assigned_to === null || record.reminder_assigned_to === this.currentUser?.id;
                });
                console.log(`📊 Erinnerungs-Filter ${filter} ergab ${offlineToAdd.length} Offline-Akten`);
            }
            
            // Zeit-Filter auf Offline-Akten anwenden (neueste X Tage)
            if (filter === 'recent' || filter === 'recent30' || filter === 'recent365') {
                const days = filter === 'recent' ? 7 : (filter === 'recent30' ? 30 : 365);
                const cutoffDate = new Date();
                cutoffDate.setDate(cutoffDate.getDate() - days);
                cutoffDate.setHours(0, 0, 0, 0);
                
                offlineToAdd = offlineToAdd.filter(record => {
                    const recordDate = new Date(record.created_at);
                    return recordDate >= cutoffDate;
                });
                console.log(`📅 Zeit-Filter ${filter} (${days} Tage) ergab ${offlineToAdd.length} Offline-Akten`);
            }
            
            // Offline-Akten hinzufügen (nur wenn sie noch nicht drin sind)
            const existingOfflineIds = new Set(this.records.filter(r => r.is_offline).map(r => r.temp_id));
            const newOfflineRecords = offlineToAdd.filter(r => !existingOfflineIds.has(r.temp_id));
            
            if (newOfflineRecords.length > 0) {
                this.records = [...newOfflineRecords, ...this.records];
                console.log(`📊 ${newOfflineRecords.length} Offline-Akten hinzugefügt (mit Filter-Logik)`);
            }
            
            // Zusätzliche Deduplizierung: Falls durch irgendwas Duplikate entstanden sind, entfernen
            const seenIds = new Set();
            this.records = this.records.filter(record => {
                const id = record.is_offline ? record.temp_id : record.id;
                if (seenIds.has(id)) {
                    console.warn(`⚠️ Duplikat entfernt: ${id}`);
                    return false;
                }
                seenIds.add(id);
                return true;
            });
            
            if (serverAvailable) {
                this.paginationInfo = data.pagination;
            } else {
                this.paginationInfo = null;
            }
            
            console.log(`📊 Nach dem Hinzufügen der Offline-Akten:`, this.records);
            console.log(`📊 Offline-Akten in der Liste:`, this.records.filter(r => r.is_offline));

            this.sortRecords();
            this.renderRecords(loadMore);

        } catch (e) {
            this.toast(e.message, 'error');
        }
    },

    renderRecords(append = false) {
        const container = document.getElementById('recordsList');
        if (!this.records.length) {
            container.innerHTML = `
                <div class="empty-state" style="grid-column: 1 / -1;">
                    <i class="fas fa-folder-open"></i>
                    <p>Keine Akten gefunden</p>
                </div>`;
            return;
        }

        // Performance: Virtual Scrolling für sehr große Listen (> 100 Items)
        if (this.records.length > 100 && !append) {
            this.renderVirtualRecords();
            return;
        }

        // Event-Handler für Auswahl nach dem Rendern neu initialisieren
        if (typeof this.initMehrfachAuswahl === 'function') {
            this.initMehrfachAuswahl();
        }
        
        // Performance: CSS Containment für bessere Rendering-Performance
        container.style.contain = 'layout style paint';
        
        // Performance: Hardware-Beschleunigung für Scroll-Performance
        container.style.willChange = 'transform';
        
        // Performance: Gestaffeltes Rendering in Chunks
        const chunkSize = 25; // 25 Items pro Chunk
        const recordsToRender = append ? this.records.slice(-50) : this.records;
        const chunks = [];
        for (let i = 0; i < recordsToRender.length; i += chunkSize) {
            chunks.push(recordsToRender.slice(i, i + chunkSize));
        }
        
        // Performance: DocumentFragment für effizienteres DOM-Insertion
        const fragment = document.createDocumentFragment();
        const tempDiv = document.createElement('div');
        
        const renderChunk = (chunkIndex) => {
            if (chunkIndex >= chunks.length) {
                // Alle Chunks gerendert
                if (typeof this.aktualisiereAuswahlDarstellungNachRender === 'function') {
                    this.aktualisiereAuswahlDarstellungNachRender();
                }
                // will-change entfernen wenn nicht mehr benötigt
                setTimeout(() => container.style.willChange = '', 1000);
                return;
            }
            
            const chunk = chunks[chunkIndex];
            const html = chunk.map(r => this.recordCardHTML(r)).join('');
            
            // Performance: DocumentFragment statt direkter DOM-Manipulation
            tempDiv.innerHTML = html;
            while (tempDiv.firstChild) {
                fragment.appendChild(tempDiv.firstChild);
            }
            
            if (append) {
                container.appendChild(fragment);
            } else {
                if (chunkIndex === 0) {
                    container.innerHTML = '';
                    container.appendChild(fragment);
                } else {
                    container.appendChild(fragment);
                }
            }
            
            // Nächsten Chunk mit requestAnimationFrame für bessere Performance
            requestAnimationFrame(() => renderChunk(chunkIndex + 1));
        };
        
        // Start gestaffeltes Rendering
        renderChunk(0);
        
        // Pagination-Button anzeigen/verstecken
        const paginationContainer = document.getElementById('recordsPagination');
        if (paginationContainer) {
            if (this.paginationInfo && this.records.length < this.paginationInfo.total) {
                paginationContainer.classList.remove('hidden');
            } else {
                paginationContainer.classList.add('hidden');
            }
        }
    },
    
    renderVirtualRecords() {
        // Performance: Virtual Scrolling für sehr große Listen
        const container = document.getElementById('recordsList');
        if (!container) return;
        
        // Nur bei großen Listen Virtual Scrolling aktivieren
        if (this.records.length <= 100) {
            this.renderRecords();
            return;
        }
        
        container.style.contain = 'layout style paint';
        container.style.willChange = 'transform';
        
        const itemHeight = 220; // Geschätzte Höhe pro Item (etwas höher für Sicherheit)
        const containerHeight = container.clientHeight || window.innerHeight;
        const visibleCount = Math.ceil(containerHeight / itemHeight) + 10; // +10 Puffer für smooth scrolling
        const scrollTop = container.scrollTop || 0;
        const startIndex = Math.max(0, Math.floor(scrollTop / itemHeight) - 5);
        const endIndex = Math.min(this.records.length, startIndex + visibleCount);
        
        const visibleRecords = this.records.slice(startIndex, endIndex);
        
        // Padding für Scroll-Position simulieren
        container.style.paddingTop = `${startIndex * itemHeight}px`;
        container.style.paddingBottom = `${(this.records.length - endIndex) * itemHeight}px`;
        
        // Nur sichtbare Items rendern mit Lazy Loading
        const html = visibleRecords.map((r, index) => {
            const globalIndex = startIndex + index;
            return this.recordCardHTML(r, globalIndex);
        }).join('');
        container.innerHTML = html;
        
        // Lazy Loading für Bilder mit Intersection Observer
        this.setupLazyLoading();
        
        // Event-Handler für Auswahl nach dem Rendern neu initialisieren
        if (typeof this.initMehrfachAuswahl === 'function') {
            this.initMehrfachAuswahl();
        }
        
        // Auswahl-Optik nach Render wiederherstellen
        if (typeof this.aktualisiereAuswahlDarstellungNachRender === 'function') {
            this.aktualisiereAuswahlDarstellungNachRender();
        }
        
        // Scroll-Event-Listener für Virtual Scrolling mit Intersection Observer
        if (!this._virtualRecordsScrollListener) {
            this._virtualRecordsScrollListener = this.debounce(() => {
                if (this.records.length > 100) {
                    this.renderVirtualRecords();
                }
            }, 50); // Reduziert von 100ms auf 50ms für schnellere Reaktion
            container.addEventListener('scroll', this._virtualRecordsScrollListener, { passive: true });
        }
        
        setTimeout(() => container.style.willChange = '', 1000);
    },
    
    setupLazyLoading() {
        // Lazy Loading für Bilder mit Intersection Observer
        if ('IntersectionObserver' in window) {
            const imageObserver = new IntersectionObserver((entries, observer) => {
                entries.forEach(entry => {
                    if (entry.isIntersecting) {
                        const img = entry.target;
                        const src = img.dataset.src;
                        if (src) {
                            img.src = src;
                            img.classList.remove('lazy');
                            observer.unobserve(img);
                        }
                    }
                });
            }, {
                rootMargin: '50px 0px',
                threshold: 0.1
            });
            
            document.querySelectorAll('img.lazy').forEach(img => {
                imageObserver.observe(img);
            });
        } else {
            // Fallback für Browser ohne Intersection Observer
            document.querySelectorAll('img.lazy').forEach(img => {
                if (img.dataset.src) {
                    img.src = img.dataset.src;
                    img.classList.remove('lazy');
                }
            });
        }
    },

    async loadMoreRecords() {
        if (this.isLoadingMore) return;
        this.isLoadingMore = true;
        
        const btn = document.querySelector('#recordsPagination button');
        const originalHTML = btn.innerHTML;
        btn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Lade...';

        await this.loadRecords(true);
        
        btn.innerHTML = originalHTML;
        this.isLoadingMore = false;
    },

    recordCardHTML(r) {
        // Performance: Cache für wiederholte Berechnungen
        if (!this._recordCardCache) {
            this._recordCardCache = new Map();
        }
        const searchMatchesKey = r.search_matches ? JSON.stringify(r.search_matches) : '';
        const cacheKey = `${r.id}_${r.updated_at}_${searchMatchesKey}_${r.category_id}_${r.border_color}_${r.hashtags}`;
        if (this._recordCardCache.has(cacheKey)) {
            return this._recordCardCache.get(cacheKey);
        }
        
        let borderClass = r.border_color ? r.border_color : '';
        const locked = r.locked ? `<span class="lock-badge"><i class="fas fa-lock"></i> Gesperrt</span>` : '';
        // Offline-Badge nur anzeigen, wenn es eine Offline-Akte ist
        const offlineBadge = r.is_offline ? `<span class="offline-badge"><i class="fas fa-wifi-slash"></i> Offline</span>` : '';

        // Performance: Einmalige Datum-Berechnung für alle Vergleiche
        const today = new Date();
        today.setHours(0, 0, 0, 0);
        
        // Performance: Optimierter Reminder-Check mit early return
        const hasExpiredReminder = this.reminders.some(rem => {
            if (rem.record_id !== r.id || rem.completed === 1) return false;
            const reminderDate = new Date(rem.reminder_date);
            reminderDate.setHours(0, 0, 0, 0);
            return reminderDate < today;
        });
        
        // Check if calendar reminder (termin) is expired
        let calendarReminderExpired = false;
        if (r.reminder_date) {
            const reminderDate = new Date(r.reminder_date);
            reminderDate.setHours(0, 0, 0, 0);
            calendarReminderExpired = reminderDate < today;
        }

        let statusHtml = '';
        if (r.status === 'erledigt') {
            statusHtml = `<span class="status-badge status-erledigt"><i class="fas fa-check-circle"></i> Erledigt</span>`;
        } else if (r.status === 'bearbeitung') {
            statusHtml = `<span class="status-badge status-bearbeitung"><i class="fas fa-spinner fa-spin"></i> In Bearbeitung</span>`;
        } else if (r.status === 'offen') {
            statusHtml = `<span class="status-badge status-offen"><i class="fas fa-clock"></i> Offen</span>`;
        } else if (r.status === 'neutral') {
            statusHtml = `<span class="status-badge status-neutral"><i class="fas fa-info-circle"></i> Neutral</span>`;
        }

        const hasSearchMatches = Array.isArray(r.search_matches) && r.search_matches.length;
        const hashtags = r.hashtags ? r.hashtags.split(/\s+/).filter(Boolean).map(h =>
            `<span class="hashtag">${this.escapeHtml(h)}</span>`
        ).join('') : '';
        const excerpt = this.stripHtml(r.content || '').substring(0, 120);
        const searchMatches = hasSearchMatches
            ? `<div class="record-search-matches" style="margin-top:6px;padding:0;">
                <div style="display:flex;flex-direction:column;gap:6px;">
                    ${r.search_matches.slice(0, 1).map(match => `
                        <button
                            type="button"
                            class="record-search-match"
                            data-record-id="${r.id}"
                            data-filename="${this.escapeHtml(match.filename || '')}"
                            data-page="${match.page || ''}"
                            data-snippet="${this.escapeHtml(match.snippet || '')}"
                            data-match-type="${this.escapeHtml(match.type || '')}"
                            style="padding:6px 8px;border:1px solid rgba(74,163,255,0.25);border-radius:6px;background:rgba(74,163,255,0.08);text-align:left;color:inherit;cursor:pointer;transition:all 0.2s;"
                            onmouseover="this.style.background='rgba(74,163,255,0.15)';this.style.borderColor='rgba(74,163,255,0.4)'"
                            onmouseout="this.style.background='rgba(74,163,255,0.08)';this.style.borderColor='rgba(74,163,255,0.25)'"
                        >
                            <div style="display:flex;align-items:center;justify-content:space-between;gap:8px;">
                                <div style="font-size:12px;font-weight:600;color:#4aa3ff;word-break:break-word;flex:1;">
                                    <i class="fas ${match.type === 'ocr' ? 'fa-file-pdf' : 'fa-file-alt'}" style="margin-right:5px;opacity:0.85"></i>${this.escapeHtml(match.filename || 'Anhang')}
                                </div>
                                ${match.page ? `<div style="font-size:11px;color:rgba(74,163,255,0.7);font-weight:600;background:rgba(74,163,255,0.1);padding:2px 8px;border-radius:10px;">Seite ${match.page}</div>` : ''}
                            </div>
                            <div style="font-size:11px;color:var(--text-secondary, #bfc7d5);margin-top:4px;line-height:1.3;padding-left:20px;">
                                <i class="fas fa-quote-left" style="opacity:0.5;margin-right:3px;"></i>${this.escapeHtml(match.snippet || 'Treffer im Anhang').substring(0, 80)}${match.snippet && match.snippet.length > 80 ? '...' : ''}
                            </div>
                        </button>
                    `).join('')}
                    ${r.search_matches.length > 1 ? `<div style="text-align:center;font-size:11px;color:rgba(74,163,255,0.7);padding-top:2px;">+${r.search_matches.length - 1} weitere Treffer</div>` : ''}
                </div>
            </div>`
            : '';
        const address = r.address ? `<div class="record-address"><i class="fas fa-map-marker-alt" style="margin-right:4px;opacity:0.6"></i>${this.escapeHtml(r.address)}</div>` : '';
        const author = r.created_by_name || 'Unbekannt';
        
        // Kalender-Termin (Wiederholung, Uhr-Symbol)
        let calendarReminder = '';
        let reminderIcon = 'fa-calendar';
        // Parse repeat type
        let repeatType = r.reminder_repeat;
        if (r.reminder_repeat) {
            try {
                const repeatData = JSON.parse(r.reminder_repeat);
                repeatType = repeatData.type;
            } catch (e) {
                // It's a simple string
            }
        }
        if (repeatType === 'weekly' || repeatType === 'weekly_interval') reminderIcon = 'fa-redo';
        if (repeatType === 'monthly' || repeatType === 'monthly_interval' || repeatType === 'monthly_nth_weekday' || repeatType === 'monthly_last_weekday') reminderIcon = 'fa-calendar-alt';
        if (repeatType === 'yearly' || repeatType === 'yearly_interval') reminderIcon = 'fa-history';
        if (r.reminder_date) {
            let dateStr = this.formatDate(r.reminder_date);
            if (r.reminder_end_date && r.reminder_end_date.substring(0, 10) !== r.reminder_date.substring(0, 10)) {
                dateStr += ` - ${this.formatDate(r.reminder_end_date)}`;
            }
            const visibilityMeta = this.getReminderVisibilityMeta(Boolean(r.reminder_is_private));
            const visibilityIcon = `<i class="fas ${visibilityMeta.icon} visibility-icon ${visibilityMeta.className}" title="${visibilityMeta.title}"></i>`;
            const expiredClass = calendarReminderExpired ? 'expired-reminder' : '';
            const iconColor = calendarReminderExpired ? 'color:#dc3545;' : '';
            calendarReminder = `<span class="meta-reminder ${expiredClass}">${visibilityIcon}<i class="fas ${reminderIcon}" style="margin-right:4px;opacity:0.6;${iconColor}"></i>${dateStr}</span>`;
        }

        // Erinnerung (Glocken-Symbol)
        let reminderBell = '';
        
        // Offline-Akten: Erinnerungen nur aus dem erinnerungen Array
        if (r.is_offline) {
            if (r.erinnerungen && Array.isArray(r.erinnerungen)) {
                const activeReminders = r.erinnerungen.filter(er => er.completed !== 1);
                if (activeReminders.length > 0) {
                    // Nimm die erste aktive Erinnerung
                    const reminder = activeReminders[0];
                    const reminderDate = this.formatDate(reminder.reminder_date);
                    // Check if this erinnerung is expired
                    const reminderDateObj = new Date(reminder.reminder_date);
                    reminderDateObj.setHours(0, 0, 0, 0);
                    const isExpired = reminderDateObj < today;
                    const expiredClass = isExpired ? 'expired-reminder' : '';
                    const iconColor = isExpired ? 'color:#dc3545;' : '';
                    reminderBell = `<span class="meta-reminder ${expiredClass}"><i class="fas fa-bell" style="margin-right:4px;opacity:0.6;${iconColor}"></i>${reminderDate}</span>`;
                }
            }
        } else {
            // Online-Akten: Erinnerungen aus this.reminders
            const activeReminders = this.reminders.filter(rem => rem.record_id === r.id && rem.completed !== 1);
            if (activeReminders.length > 0) {
                // Nimm die erste aktive Erinnerung
                const reminder = activeReminders[0];
                const reminderDate = this.formatDate(reminder.reminder_date);
                // Check if this erinnerung is expired
                const reminderDateObj = new Date(reminder.reminder_date);
                reminderDateObj.setHours(0, 0, 0, 0);
                const isExpired = reminderDateObj < today;
                const expiredClass = isExpired ? 'expired-reminder' : '';
                const iconColor = isExpired ? 'color:#dc3545;' : '';
                reminderBell = `<span class="meta-reminder ${expiredClass}"><i class="fas fa-bell" style="margin-right:4px;opacity:0.6;${iconColor}"></i>${reminderDate}</span>`;
            }
        }

        // Kategorie anzeigen
        const category = this.categories.find(c => c.id === r.category_id);
        const categoryHtml = category ? `<span class="category-badge"><i class="fas fa-tag" style="margin-right:4px;opacity:0.6"></i>${this.escapeHtml(category.name)}</span>` : '';

        // Wenn es Suchtreffer gibt, blende normalen Inhalt aus, aber behalte Kategorie, Hashtags und Reminder!
        const normalContent = !hasSearchMatches ? `
            ${address}
            <div class="record-excerpt">${this.linkifyUrls(this.escapeHtml(excerpt))}</div>
            <div class="record-meta">
                <div class="meta-row">
                    <span class="meta-author"><i class="fas fa-user" style="margin-right:4px;opacity:0.6"></i>${this.escapeHtml(author)}</span>
                    <div class="meta-dates">
                        ${calendarReminder}
                        ${reminderBell}
                    </div>
                </div>
                <div class="hashtags">${hashtags}</div>
                ${categoryHtml}
            </div>
        ` : `
            <div class="record-meta">
                <div class="meta-row">
                    <span class="meta-author"><i class="fas fa-user" style="margin-right:4px;opacity:0.6"></i>${this.escapeHtml(author)}</span>
                    <div class="meta-dates">
                        ${calendarReminder}
                        ${reminderBell}
                    </div>
                </div>
                <div class="hashtags">${hashtags}</div>
                ${categoryHtml}
            </div>
        `;

        const html = `
        <div class="record-card ${borderClass}" data-record-id="${r.id}" role="button" tabindex="0">
            <button class="auswahl-indikator" type="button" aria-label="Akte auswählen" aria-pressed="false">
                <i class="fas fa-check"></i>
            </button>
            ${locked}
            ${r.is_offline ? '' : offlineBadge}
            <div class="record-header">
                <div class="record-header-left">
                    ${r.is_offline ? offlineBadge : `<span class="record-number">#${r.number}</span>`}
                    ${statusHtml}
                </div>
            </div>
            <div class="record-title">${this.escapeHtml(r.title)}</div>
            ${searchMatches}
            ${normalContent}
        </div>`;
        
        // Performance: Cache mit Limit (max 500 Einträge)
        if (this._recordCardCache.size > 500) {
            this._recordCardCache.clear();
        }
        this._recordCardCache.set(cacheKey, html);
        
        return html;
    },

    sortRecords() {
        const sortEl = document.getElementById('recordSort');
        const sort = sortEl ? sortEl.value : 'created_desc';
        
        // Sort UI aktualisieren
        this.updateFilterDropdownUI('recordSortDropdown', sort, 'fa-sort-amount-down');

        // Performance: Cache für Sortierfunktionen
        if (!this._sortCache) {
            this._sortCache = {
                updated_desc: (a,b) => new Date(b.updated_at) - new Date(a.updated_at),
                updated_asc: (a,b) => new Date(a.updated_at) - new Date(b.updated_at),
                created_desc: (a,b) => new Date(b.created_at) - new Date(a.created_at),
                created_asc: (a,b) => new Date(a.created_at) - new Date(b.created_at),
                title_asc: (a,b) => a.title.localeCompare(b.title),
                title_desc: (a,b) => b.title.localeCompare(a.title),
            };
        }

        const baseSorter = this._sortCache[sort] || this._sortCache.updated_desc;
        this.records.sort(baseSorter);
    },

    switchSearchTab(type) {
        this.searchType = type;
        document.querySelectorAll('.search-tab').forEach(t => t.classList.toggle('active', t.dataset.type === type));
        // Reset pagination when switching search type
        this.saveUserPreferences();
        
        if (type === 'similar') {
            const searchInput = document.getElementById('recordsSearch');
            const searchQuery = searchInput ? searchInput.value.trim() : '';
            if (searchQuery) {
                this.loadSimilarRecords(searchQuery);
            } else {
                this.toast('Bitte geben Sie einen Suchbegriff ein für die Ähnlichkeitssuche', 'warning');
                // Tab aktivieren lassen, aber keine Suche ausführen
                this.records = [];
                this.renderRecords();
            }
        } else {
            this.loadRecords();
        }
    },

    switchGallerySearchTab(type) {
        this.gallerySearchType = type;
        document.querySelectorAll('#gallerySection .search-tab').forEach(t => t.classList.toggle('active', t.dataset.type === type));
        // Reset pagination when switching search type
        this.saveUserPreferences();
        this.loadGallery();
    },

    debounceSearch() {
        clearTimeout(this.searchTimeout);
        // Performance: Längeres Debounce (500ms) für weniger API-Calls wie bei Gallery
        this.searchTimeout = setTimeout(() => {
            if (this.searchType === 'similar') {
                const searchInput = document.getElementById('recordsSearch');
                const searchQuery = searchInput ? searchInput.value.trim() : '';
                if (searchQuery) {
                    this.loadSimilarRecords(searchQuery);
                } else {
                    this.records = [];
                    this.renderRecords();
                }
            } else {
                this.loadRecords();
            }
        }, 500);
    },

    debounceGallerySearch() {
        clearTimeout(this.gallerySearchTimeout);
        // Performance: Längeres Debounce (500ms) für weniger API-Calls
        this.gallerySearchTimeout = setTimeout(() => this.loadGallery(), 500);
    },

    updateSearchButtonIcon() {
        const searchInput = document.getElementById('recordsSearch');
        const searchBtn = document.getElementById('searchClearBtn');
        const icon = searchBtn.querySelector('i');

        if (searchInput && searchBtn && icon) {
            if (searchInput.value.trim()) {
                icon.className = 'fas fa-times';
            } else {
                icon.className = 'fas fa-search';
            }
        }
    },

    updateGallerySearchButtonIcon() {
        const searchInput = document.getElementById('gallerySearch');
        const searchBtn = document.getElementById('gallerySearchClearBtn');
        if (!searchInput || !searchBtn) return;
        const icon = searchBtn.querySelector('i');

        if (searchInput.value.trim()) {
            icon.className = 'fas fa-times';
            searchBtn.title = 'Suchtext löschen';
        } else {
            icon.className = 'fas fa-search';
            searchBtn.title = 'Durchsuchen';
        }
    },

    clearSearch() {
        const searchInput = document.getElementById('recordsSearch');
        if (searchInput) {
            searchInput.value = '';
            this.updateSearchButtonIcon();
            this.loadRecords();
        }
    },

    handleGallerySearchClick() {
        const searchInput = document.getElementById('gallerySearch');
        const hasSearchText = searchInput && searchInput.value.trim();
        
        // Wenn Suchtext vorhanden ist, löschen
        if (hasSearchText) {
            this.clearGallerySearch();
        } else {
            // Sonst handleGallerySearch (für Abweichungssuche)
            this.handleGallerySearch();
        }
    },

    handleGallerySearch() {
        const searchInput = document.getElementById('gallerySearch');
        if (searchInput) {
            this.loadGallery();
        }
    },

    clearGallerySearch() {
        const searchInput = document.getElementById('gallerySearch');
        if (searchInput) {
            searchInput.value = '';
            this.updateGallerySearchButtonIcon();
            this.loadGallery();
        }
    },

    setupInfiniteScroll() {
        const container = document.getElementById('recordsList');
        if (!container) return;
        
        // Remove existing scroll listener to prevent duplicates
        if (this.scrollListener) {
            container.removeEventListener('scroll', this.scrollListener);
        }
        
        this.scrollListener = async () => {
            // Check if user has scrolled near the bottom
            const scrollTop = container.scrollTop;
            const scrollHeight = container.scrollHeight;
            const clientHeight = container.clientHeight;
            
            // Load more when user is within 200px of bottom
            if (scrollTop + clientHeight >= scrollHeight - 200) {
                // Check if there are more records to load
                if (this.paginationInfo && this.paginationInfo.has_more && !this.isLoadingMore) {
                    this.isLoadingMore = true;
                    this.showLoadingIndicator();
                    await this.loadRecords(true);
                    this.hideLoadingIndicator();
                    this.isLoadingMore = false;
                }
            }
        };
        
        container.addEventListener('scroll', this.scrollListener);
    },

    showLoadingIndicator() {
        const container = document.getElementById('recordsList');
        if (container && !document.getElementById('loadingMoreIndicator')) {
            const indicator = document.createElement('div');
            indicator.id = 'loadingMoreIndicator';
            indicator.className = 'loading-more';
            indicator.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Lade weitere Akten...';
            container.appendChild(indicator);
        }
    },

    hideLoadingIndicator() {
        const indicator = document.getElementById('loadingMoreIndicator');
        if (indicator) {
            indicator.remove();
        }
    },

    // Floating Action Button (FAB) Klick-Handler
    handleFabClick() {
        if (this.currentSection === 'users') {
            this.openUserModal();
        } else if (this.currentSection === 'formTemplates') {
            this.showCreateTemplateModal();
        } else if (this.currentSection === 'chat') {
            this.chatCreateRoom();
        } else {
            // Wenn im Kalender-Reiter und ein Datum ausgewählt ist, dieses als Termin übernehmen
            const initialDate = (this.currentSection === 'calendar' && this.selectedCalDate) ? this.selectedCalDate : null;
            this.openNewRecordModal(initialDate);
        }
    },

    // ── Record Modal ───────────────────────────────
    toggleFullscreen() {
        const modal = document.getElementById('recordModal');
        const fullscreenBtn = document.getElementById('modalFullscreen');
        const icon = fullscreenBtn.querySelector('i');

        modal.classList.toggle('fullscreen');

        if (modal.classList.contains('fullscreen')) {
            icon.className = 'fas fa-compress';
            fullscreenBtn.title = 'Vollbild beenden';
            fullscreenBtn.setAttribute('aria-label', 'Vollbild beenden');
        } else {
            icon.className = 'fas fa-expand';
            fullscreenBtn.title = 'Vollbildmodus';
            fullscreenBtn.setAttribute('aria-label', 'Vollbild');
        }
    },

    toggleFormSelectFullscreen() {
        const modal = document.getElementById('formSelectModal');
        const btn = document.getElementById('formSelectFullscreen');
        const icon = btn.querySelector('i');
        
        modal.classList.toggle('fullscreen');
        
        if (modal.classList.contains('fullscreen')) {
            icon.className = 'fas fa-compress';
            btn.title = 'Vollbild beenden';
        } else {
            icon.className = 'fas fa-expand';
            btn.title = 'Vollbildmodus';
        }
    },

    toggleDesignerFullscreen() {
        const modal = document.getElementById('formDesignerModal');
        const btn = document.getElementById('designerFullscreen');
        const icon = btn.querySelector('i');
        
        modal.classList.toggle('fullscreen');
        
        if (modal.classList.contains('fullscreen')) {
            icon.className = 'fas fa-compress';
            btn.title = 'Vollbild beenden';
            btn.setAttribute('aria-label', 'Vollbild beenden');
        } else {
            icon.className = 'fas fa-expand';
            btn.title = 'Vollbildmodus';
            btn.setAttribute('aria-label', 'Vollbild');
        }
    },



    updateRecordModalPermissions() {
        const isAdmin = this.currentUser?.role === 'admin';
        // Category
        const catGroup = document.getElementById('formGroupCategory');
        if (catGroup) {
            catGroup.style.display = (isAdmin || this.currentUser?.can_set_category) ? 'block' : 'none';
        }
        // Status
        const statusGroup = document.getElementById('formGroupStatus');
        if (statusGroup) {
            statusGroup.style.display = (isAdmin || this.currentUser?.can_set_status) ? 'block' : 'none';
        }
        // Border Color
        const colorGroup = document.getElementById('formGroupBorderColor');
        if (colorGroup) {
            colorGroup.style.display = (isAdmin || this.currentUser?.can_set_border_color) ? 'block' : 'none';
        }
        // Reminder (Termin)
        const remGroup = document.getElementById('formGroupReminder');
        if (remGroup) {
            remGroup.style.display = (isAdmin || this.currentUser?.can_set_reminder) ? 'block' : 'none';
        }
        const remEndGroup = document.getElementById('formGroupReminderEnd');
        if (remEndGroup) {
            remEndGroup.style.display = (isAdmin || this.currentUser?.can_set_reminder) ? 'block' : 'none';
        }
        const remRepeatGroup = document.getElementById('formGroupReminderRepeat');
        if (remRepeatGroup) {
            remRepeatGroup.style.display = (isAdmin || this.currentUser?.can_set_reminder) ? 'block' : 'none';
        }
        const remVisibilityGroup = document.getElementById('formGroupReminderVisibility');
        if (remVisibilityGroup) {
            remVisibilityGroup.style.display = (isAdmin || this.currentUser?.can_set_reminder) ? 'block' : 'none';
        }
        // Erinnerung
        const addReminderBtn = document.getElementById('addReminderBtn');
        if (addReminderBtn) {
            addReminderBtn.style.display = (isAdmin || this.currentUser?.can_set_erinnerung) ? 'block' : 'none';
        }
        const recordRemindersSection = document.getElementById('recordRemindersSection');
        if (recordRemindersSection) {
            recordRemindersSection.style.display = (isAdmin || this.currentUser?.can_set_erinnerung) ? 'block' : 'none';
        }
        // Note
        const noteGroup = document.getElementById('formGroupNote');
        if (noteGroup) {
            noteGroup.style.display = (isAdmin || this.currentUser?.can_set_note) ? 'block' : 'none';
        }
    },

    openNewRecordModal(initialDate = null) {
        if (!this.currentUser?.can_write && this.currentUser?.role !== 'admin') {
            this.toast('Keine Schreibberechtigung', 'error'); return;
        }
        this.editingId = null;
        this.currentLock = null;
        this.clearModal();
        document.getElementById('modalTitle').textContent = 'Neue Akte';

        // Standardwerte laden und anwenden
        this.loadAndApplyRecordDefaults();

        // Aktennummer beim Erstellen sicher ausblenden
        const numGroup = document.getElementById('recordNumberGroup');
        if (numGroup) numGroup.style.display = 'none';

        // Wenn ein initiales Datum übergeben wurde (z.B. vom Kalender), setzen wir es
        if (initialDate) {
            document.getElementById('recordReminderDateValue').value = initialDate;
            document.getElementById('recordReminderDate').value = this.formatDate(initialDate);
        }

        this.updateRecordModalPermissions();
        this.renderRecordReminders([]);
        this.loadUsersForReminderDropdown();
        
        // Datei-Upload-Verfügbarkeit basierend auf Server-Status prüfen
        this.updateFileUploadAvailability();
        
        this.showModal('recordModal');
        this.hasChanges = false;
    },

    async openRecord(id) {
        // Klick-Tracking für Lernsystem
        if (this.currentSearchLogId && this.records) {
            const recordIndex = this.records.findIndex(r => r.id === id);
            if (recordIndex !== -1) {
                try {
                    await this.apiPost('/learning/log-result-click', {
                        search_log_id: this.currentSearchLogId,
                        record_id: id,
                        click_position: recordIndex + 1
                    });
                } catch (e) {
                    console.error('Fehler beim Klick-Tracking:', e);
                }
            }
        }
        
        // Offline-Akten können jetzt bearbeitet werden - keine Blockierung mehr

        try {
            // Prüfen ob es eine Offline-Akte ist - mit verschiedenen ID-Konvertierungen
            let currentRecord = this.records.find(r => r.id === id);
            
            // Wenn nicht gefunden, versuche es mit String-Konvertierung
            if (!currentRecord) {
                currentRecord = this.records.find(r => String(r.id) === String(id));
            }
            
            // Wenn immer noch nicht gefunden, versuche es mit Number-Konvertierung
            if (!currentRecord && !isNaN(id)) {
                currentRecord = this.records.find(r => r.id === Number(id));
            }
            
            const isOfflineRecord = currentRecord?.is_offline;
            
            // Zusätzliche Prüfung: Suche nach temp_record_id
            const recordByTempId = this.records.find(r => r.temp_record_id === id);
            
            // Wenn kein Record gefunden wurde, aber temp_record_id existiert, versuche es damit
            let recordToUse = currentRecord;
            let isOffline = isOfflineRecord;
            
            if (!recordToUse && recordByTempId) {
                recordToUse = recordByTempId;
                isOffline = recordByTempId.is_offline;
            }
            
            // VOR dem Laden der Daten: Lock setzen für Online-Akten (verhindert Race Condition)
            let lockFailed = false;
            let lockInfo = null;
            if (!isOffline && (this.currentUser.can_write || this.currentUser.role === 'admin')) {
                try {
                    await this.apiPost(`/records/${id}/lock`, null, false);
                    this.currentLock = id;
                    this.startLockCheck(id);
                } catch (e) {
                    console.log('❌ Lock konnte nicht gesetzt werden (Server offline oder bereits gesperrt)');
                    if (e.response && e.response.status === 423 && e.response.data && e.response.data.lock_info) {
                        lockFailed = true;
                        lockInfo = e.response.data.lock_info;
                    }
                }
            }
            
            let data;
            if (isOffline) {
                // Offline-Akte direkt aus lokaler Liste laden
                data = recordToUse;
                this.editingId = id;
                this.currentLock = null;
                // Speichere is_offline Information im data Objekt
                data.is_offline = true;
            } else {
                // Online-Akte vom Server laden
                try {
                    data = await this.apiGet(`/records/${id}`, false);
                    this.editingId = id;
                    // Speichere is_offline Information im data Objekt
                    data.is_offline = false;
                } catch (e) {
                    // Wenn Server nicht erreichbar, prüfe ob es eine Offline-Akte ist
                    console.log('❌ Server nicht erreichbar, prüfe auf Offline-Akte');
                    const offlineRecord = this.records.find(r => r.is_offline && (r.id === id || r.temp_record_id === id));
                    if (offlineRecord) {
                        console.log('💾 Offline-Akte gefunden, öffne sie offline');
                        data = offlineRecord;
                        isOffline = true;
                        this.editingId = id;
                        this.currentLock = null;
                        // Speichere is_offline Information im data Objekt
                        data.is_offline = true;
                    } else {
                        throw e;
                    }
                }
            }
            
            // Check lock before opening (data already includes lock info)
            if (data.locked && data.lock_info?.user_id !== this.currentUser.id) {
                this.toast(`Akte gesperrt von ${data.lock_info.username}`, 'warning');
            }
            
            // Update local records list with the loaded data (prevents duplicates)
            if (!isOffline) {
                const existingIndex = this.records.findIndex(r => r.id === data.id);
                if (existingIndex !== -1) {
                    this.records[existingIndex] = data;
                } else {
                    this.records.push(data);
                }
            }
            
            // Aktennummer beim Bearbeiten anzeigen
            const numGroup = document.getElementById('recordNumberGroup');
            if (numGroup) numGroup.style.display = 'block';

            document.getElementById('modalTitle').textContent = `Akte #${data.number}`;
            document.getElementById('recordId').value = data.id;
            document.getElementById('recordNumber').value = data.number;
            document.getElementById('recordTitle').value = data.title;
            document.getElementById('recordAddress').value = data.address || '';
            document.getElementById('recordContent').innerHTML = this.linkifyUrls(data.content || '');
            document.getElementById('recordHashtags').value = data.hashtags || '';
            document.getElementById('recordStatus').value = data.status || 'neutral';
            document.getElementById('recordBorderColor').value = data.border_color || '';
            document.getElementById('recordCategory').value = data.category_id || '';

            // Checkbox-Zustände wiederherstellen
            const contentElement = document.getElementById('recordContent');
            const checkboxes = contentElement.querySelectorAll('input[type="checkbox"]');
            checkboxes.forEach(checkbox => {
                checkbox.checked = checkbox.hasAttribute('checked');
            });

            // Custom Dropdowns UI aktualisieren
            this.updateModalDropdownUI('modalStatusDropdown', data.status || 'neutral');
            this.updateModalDropdownUI('modalColorDropdown', data.border_color || '');
            // Handle reminder repeat: could be string or JSON
            let repeatVal = '';
            let repeatData = null;
            if (data.reminder_repeat) {
                try {
                    repeatData = JSON.parse(data.reminder_repeat);
                    repeatVal = repeatData.type;
                    if (repeatVal === 'monthly_last_weekday') {
                        repeatVal = 'monthly_nth_weekday';
                        repeatData = {
                            type: 'monthly_nth_weekday',
                            nth: 'last',
                            weekday: repeatData?.weekday ?? 1
                        };
                    } else if (repeatVal === 'monthly_nth_weekday' && repeatData?.nth === 5) {
                        repeatData = { ...repeatData, nth: 'last' };
                    }
                } catch (e) {
                    repeatVal = data.reminder_repeat;
                }
            }
            this.updateModalDropdownUI('modalRepeatDropdown', repeatVal);
            
            // Update advanced options based on repeatData or repeatVal
            const advancedOptions = document.getElementById('advancedRepeatOptions');
            const weekIntervalGroup = document.getElementById('formGroupWeekInterval');
            const monthIntervalGroup = document.getElementById('formGroupMonthInterval');
            const monthModeGroup = document.getElementById('formGroupMonthMode');
            const yearIntervalGroup = document.getElementById('formGroupYearInterval');
            const nthWeekdayGroup = document.getElementById('formGroupNthWeekday');
            const weekdayGroup = document.getElementById('formGroupWeekday');
            
            advancedOptions.classList.add('hidden');
            weekIntervalGroup.classList.add('hidden');
            monthIntervalGroup.classList.add('hidden');
            monthModeGroup.classList.add('hidden');
            yearIntervalGroup.classList.add('hidden');
            nthWeekdayGroup.classList.add('hidden');
            weekdayGroup.classList.add('hidden');
            
            if (repeatVal) {
                advancedOptions.classList.remove('hidden');
                if (repeatVal === 'weekly') {
                    weekdayGroup.classList.remove('hidden');
                    this.updateModalDropdownUI('modalWeekdayDropdown', String(repeatData?.weekday || (d2.getDay() === 0 ? 0 : d2.getDay())));
                } else if (repeatVal === 'weekly_interval') {
                    weekIntervalGroup.classList.remove('hidden');
                    weekdayGroup.classList.remove('hidden');
                    this.updateModalDropdownUI('modalWeekIntervalDropdown', String(repeatData?.interval || 2));
                    this.updateModalDropdownUI('modalWeekdayDropdown', String(repeatData?.weekday || 1));
                } else if (repeatVal === 'monthly_interval') {
                    const monthMode = repeatData?.mode || 'date';
                    monthIntervalGroup.classList.remove('hidden');
                    monthModeGroup.classList.remove('hidden');
                    this.updateModalDropdownUI('modalMonthIntervalDropdown', String(repeatData?.interval || 2));
                    this.updateModalDropdownUI('modalMonthModeDropdown', monthMode);
                    if (monthMode === 'weekday') {
                        nthWeekdayGroup.classList.remove('hidden');
                        weekdayGroup.classList.remove('hidden');
                        this.updateModalDropdownUI('modalNthWeekdayDropdown', repeatData?.nth === 'last' ? 'last' : String(repeatData?.nth || 1));
                        this.updateModalDropdownUI('modalWeekdayDropdown', String(repeatData?.weekday ?? 1));
                    }
                } else if (repeatVal === 'yearly_interval') {
                    yearIntervalGroup.classList.remove('hidden');
                    this.updateModalDropdownUI('modalYearIntervalDropdown', String(repeatData?.interval || 2));
                } else if (repeatVal === 'monthly_nth_weekday') {
                    nthWeekdayGroup.classList.remove('hidden');
                    weekdayGroup.classList.remove('hidden');
                    this.updateModalDropdownUI('modalNthWeekdayDropdown', repeatData?.nth === 'last' ? 'last' : String(repeatData?.nth || 1));
                    this.updateModalDropdownUI('modalWeekdayDropdown', String(repeatData?.weekday || 1));
                } else if (repeatVal === 'monthly_last_weekday') {
                    weekdayGroup.classList.remove('hidden');
                    this.updateModalDropdownUI('modalWeekdayDropdown', String(repeatData?.weekday || 1));
                } else {
                    advancedOptions.classList.add('hidden');
                }
            }
            
            this.updateModalDropdownUI('modalCategoryDropdown', data.category_id || '');

            const isoDate = data.reminder_date ? data.reminder_date.substring(0,10) : '';
            document.getElementById('recordReminderDateValue').value = isoDate;
            if (isoDate) {
                const [y, m, d] = isoDate.split('-');
                document.getElementById('recordReminderDate').value = `${d}.${m}.${y}`;
            } else {
                document.getElementById('recordReminderDate').value = '';
            }

            const isoEndDate = data.reminder_end_date ? data.reminder_end_date.substring(0,10) : '';
            document.getElementById('recordReminderEndDateValue').value = isoEndDate;
            if (isoEndDate) {
                const [y, m, d] = isoEndDate.split('-');
                document.getElementById('recordReminderEndDate').value = `${d}.${m}.${y}`;
            } else {
                document.getElementById('recordReminderEndDate').value = '';
            }
            this.updateModalDropdownUI('modalReminderVisibilityDropdown', data.reminder_is_private && !data.reminder_hidden ? 'private' : 'all');
            if (data.reminder_hidden) {
                this.toast('Für diese Akte existiert ein privater Termin eines anderen Benutzers.', 'info');
            }

            // Lock banner and form state
            const banner = document.getElementById('lockBanner');
            // Use lock info from failed lock attempt or from data
            const effectiveLockInfo = lockFailed ? lockInfo : data.lock_info;
            const isLockedByOther = (lockFailed || (data.locked && data.lock_info?.user_id !== this.currentUser.id));

            if (isLockedByOther && effectiveLockInfo) {
                banner.innerHTML = `<i class="fas fa-lock"></i> Gesperrt durch <strong>${this.escapeHtml(effectiveLockInfo.username)}</strong>`;
                banner.classList.remove('hidden');
                this.disableRecordForm(true);
                // Don't start lock check if we failed to acquire lock
                if (lockFailed) {
                    this.currentLock = null;
                    if (this.lockCheckInterval) {
                        clearInterval(this.lockCheckInterval);
                        this.lockCheckInterval = null;
                    }
                }
            } else {
                banner.classList.add('hidden');
                this.disableRecordForm(false);
            }

            // Speichere die temp_id für Offline-Akten für späteren Zugriff
            if (isOffline && data.temp_id) {
                console.log('💾 Speichere temp_id für Offline-Akte:', data.temp_id);
                // Aktualisiere den Record in this.records mit der temp_id
                const recordIndex = this.records.findIndex(r => r.id === id);
                if (recordIndex !== -1) {
                    this.records[recordIndex].temp_id = data.temp_id;
                }
            }

            this.updateRecordModalPermissions();
            this.renderAttachments(data.attachments || []);
            this.loadRecordReminders(id);
            this.showModal('recordModal');
            this.hasChanges = false;
        } catch (e) {
            this.toast(e.message, 'error');
        }
    },

    disableRecordForm(disabled) {
        const fields = ['recordTitle', 'recordAddress', 'recordContent', 'recordHashtags', 'recordStatus', 'recordBorderColor', 'recordCategory', 'recordReminderDate', 'recordReminderEndDate', 'recordReminderRepeat', 'recordReminderWeekInterval', 'recordReminderMonthInterval', 'recordReminderMonthMode', 'recordReminderYearInterval'];
        fields.forEach(id => {
            const element = document.getElementById(id);
            if (element) {
                element.disabled = disabled;
                element.style.opacity = disabled ? '0.5' : '1';
                element.style.pointerEvents = disabled ? 'none' : 'auto';
            }
        });

        // Custom Dropdowns im Modal sperren
        const modalDropdowns = ['modalStatusDropdown', 'modalColorDropdown', 'modalRepeatDropdown', 'modalWeekIntervalDropdown', 'modalMonthIntervalDropdown', 'modalMonthModeDropdown', 'modalYearIntervalDropdown', 'modalNthWeekdayDropdown', 'modalWeekdayDropdown', 'modalCategoryDropdown', 'modalReminderVisibilityDropdown', 'bulkReminderVisibilityDropdown'];
        modalDropdowns.forEach(id => {
            const el = document.getElementById(id);
            if (el) {
                const toggle = el.querySelector('.dropdown-toggle');
                if (toggle) {
                    toggle.disabled = disabled;
                    el.style.opacity = disabled ? '0.5' : '1';
                    el.style.pointerEvents = disabled ? 'none' : 'auto';
                }
            }
        });
        
        // Disable/enable save button
        const saveBtn = document.querySelector('#recordForm button[type="submit"]');
        if (saveBtn) {
            saveBtn.disabled = disabled;
            saveBtn.style.opacity = disabled ? '0.5' : '1';
            saveBtn.style.pointerEvents = disabled ? 'none' : 'auto';
        }
        
        // Disable/enable delete button
        const deleteBtn = document.querySelector('#recordForm button[data-perm="can_delete"]');
        if (deleteBtn) {
            deleteBtn.disabled = disabled;
            deleteBtn.style.opacity = disabled ? '0.5' : '1';
            deleteBtn.style.pointerEvents = disabled ? 'none' : 'auto';
        }
    },

    initModalDropdowns() {
        const setups = [
            { id: 'modalStatusDropdown', inputId: 'recordStatus' },
            { id: 'modalColorDropdown', inputId: 'recordBorderColor' },
            { id: 'modalRepeatDropdown', inputId: 'recordReminderRepeat' },
            { id: 'modalWeekIntervalDropdown', inputId: 'recordReminderWeekInterval' },
            { id: 'modalMonthIntervalDropdown', inputId: 'recordReminderMonthInterval' },
            { id: 'modalMonthModeDropdown', inputId: 'recordReminderMonthMode' },
            { id: 'modalYearIntervalDropdown', inputId: 'recordReminderYearInterval' },
            { id: 'modalNthWeekdayDropdown', inputId: 'recordReminderNthWeekday' },
            { id: 'modalWeekdayDropdown', inputId: 'recordReminderWeekday' },
            { id: 'modalCategoryDropdown', inputId: 'recordCategory' },
            { id: 'modalReminderVisibilityDropdown', inputId: 'recordReminderVisibility' },
            { id: 'modalFontSizeDropdown', inputId: 'recordFontSize', isFontSize: true },
            { id: 'bulkModalRepeatDropdown', inputId: 'bulkReminderRepeat' },
            { id: 'bulkReminderVisibilityDropdown', inputId: 'bulkReminderVisibility' },
            { id: 'userRoleDropdown', inputId: 'userEditRole' },
            { id: 'reminderAssignDropdown', inputId: 'reminderAssignedTo' }
        ];

        setups.forEach(setup => {
            const dropdown = document.getElementById(setup.id);
            if (!dropdown) return;
            const toggle = dropdown.querySelector('.dropdown-toggle');
            const menu = dropdown.querySelector('.dropdown-menu');
            const input = document.getElementById(setup.inputId);

            toggle.addEventListener('click', (e) => {
                e.stopPropagation();
                // Alle anderen modal dropdowns schließen
                document.querySelectorAll('.custom-modal-dropdown').forEach(d => {
                    if (d !== dropdown) d.classList.remove('show');
                });
                dropdown.classList.toggle('show');
            });

            menu.querySelectorAll('button').forEach(btn => {
                btn.addEventListener('click', () => {
                    const val = btn.dataset.value;
                    input.value = val;
                    toggle.innerHTML = btn.innerHTML;
                    dropdown.classList.remove('show');
                    this.hasChanges = true;
                    if (setup.isFontSize) {
                        this.changeFontSize(val);
                    }
                    // Handle advanced repeat options visibility
                    if (setup.id === 'modalRepeatDropdown') {
                        const advancedOptions = document.getElementById('advancedRepeatOptions');
                        const weekIntervalGroup = document.getElementById('formGroupWeekInterval');
                        const monthIntervalGroup = document.getElementById('formGroupMonthInterval');
                        const monthModeGroup = document.getElementById('formGroupMonthMode');
                        const yearIntervalGroup = document.getElementById('formGroupYearInterval');
                        const nthWeekdayGroup = document.getElementById('formGroupNthWeekday');
                        const weekdayGroup = document.getElementById('formGroupWeekday');
                        
                        advancedOptions.classList.remove('hidden');
                        // Hide all first
                        weekIntervalGroup.classList.add('hidden');
                        monthIntervalGroup.classList.add('hidden');
                        monthModeGroup.classList.add('hidden');
                        yearIntervalGroup.classList.add('hidden');
                        nthWeekdayGroup.classList.add('hidden');
                        weekdayGroup.classList.add('hidden');
                        
                        // Show relevant ones
                        if (val === 'weekly') {
                            weekdayGroup.classList.remove('hidden');
                        } else if (val === 'weekly_interval') {
                            weekIntervalGroup.classList.remove('hidden');
                            weekdayGroup.classList.remove('hidden');
                        } else if (val === 'monthly_interval') {
                            monthIntervalGroup.classList.remove('hidden');
                            monthModeGroup.classList.remove('hidden');
                            if (document.getElementById('recordReminderMonthMode').value === 'weekday') {
                                nthWeekdayGroup.classList.remove('hidden');
                                weekdayGroup.classList.remove('hidden');
                            }
                        } else if (val === 'yearly_interval') {
                            yearIntervalGroup.classList.remove('hidden');
                        } else if (val === 'monthly_nth_weekday' || val === 'monthly_last_weekday') {
                            nthWeekdayGroup.classList.remove('hidden');
                            weekdayGroup.classList.remove('hidden');
                        } else {
                            advancedOptions.classList.add('hidden');
                        }
                    } else if (setup.id === 'modalMonthModeDropdown' && document.getElementById('recordReminderRepeat').value === 'monthly_interval') {
                        const nthWeekdayGroup = document.getElementById('formGroupNthWeekday');
                        const weekdayGroup = document.getElementById('formGroupWeekday');
                        nthWeekdayGroup.classList.toggle('hidden', val !== 'weekday');
                        weekdayGroup.classList.toggle('hidden', val !== 'weekday');
                    }
                    // selected-Klasse aktualisieren
                    menu.querySelectorAll('button').forEach(b => b.classList.remove('selected'));
                    btn.classList.add('selected');
                });
            });

            // Initial selected-Klasse setzen basierend auf dem aktuellen Input-Wert
            const currentValue = input.value;
            menu.querySelectorAll('button').forEach(btn => {
                if (btn.dataset.value === currentValue) {
                    btn.classList.add('selected');
                }
            });
        });

        // Initialize reminder assign dropdown separately (dynamic buttons)
        const reminderDropdown = document.getElementById('reminderAssignDropdown');
        if (reminderDropdown) {
            const reminderToggle = reminderDropdown.querySelector('.dropdown-toggle');
            const reminderMenu = reminderDropdown.querySelector('.dropdown-menu');
            const reminderInput = document.getElementById('reminderAssignedTo');

            reminderToggle.addEventListener('click', (e) => {
                e.stopPropagation();
                document.querySelectorAll('.custom-modal-dropdown').forEach(d => {
                    if (d !== reminderDropdown) d.classList.remove('show');
                });
                reminderDropdown.classList.toggle('show');
            });

            // Use event delegation for dynamic buttons
            reminderMenu.addEventListener('click', (e) => {
                const btn = e.target.closest('button');
                if (!btn) return;
                
                const val = btn.dataset.value;
                reminderInput.value = val;
                reminderToggle.innerHTML = btn.innerHTML;
                reminderDropdown.classList.remove('show');
                
                // Update selected class
                reminderMenu.querySelectorAll('button').forEach(b => b.classList.remove('selected'));
                btn.classList.add('selected');
            });
        }

        // Schließen beim Klick außerhalb
        document.addEventListener('click', () => {
            document.querySelectorAll('.custom-modal-dropdown').forEach(d => d.classList.remove('show'));
        });
    },

    updateModalDropdownUI(dropdownId, value) {
        const dropdown = document.getElementById(dropdownId);
        if (!dropdown) return;
        const btn = dropdown.querySelector(`.dropdown-menu button[data-value="${value}"]`);
        const toggle = dropdown.querySelector('.dropdown-toggle');
        const input = dropdown.querySelector('input[type="hidden"]');
        if (input) {
            input.value = value;
        }
        if (btn && toggle) {
            toggle.innerHTML = btn.innerHTML;
        }
        // Alle Buttons durchlaufen und selected-Klasse entfernen/hinzufügen
        dropdown.querySelectorAll('.dropdown-menu button').forEach(button => {
            button.classList.remove('selected');
            if (button.dataset.value === value) {
                button.classList.add('selected');
            }
        });
    },

    initFilterDropdowns() {
        const setups = [
            { id: 'recordFilterDropdown', inputId: 'recordFilter', icon: 'fa-filter', action: () => this.loadRecords() },
            { id: 'recordSortDropdown', inputId: 'recordSort', icon: 'fa-sort-amount-down', action: () => this.loadRecords() },
            { id: 'recordCategoryFilterDropdown', inputId: 'recordCategoryFilter', icon: 'fa-tags', action: () => this.loadRecords() },
            { id: 'archiveFilterDropdown', inputId: 'archiveFilter', icon: 'fa-filter', action: () => this.loadArchiveRecords() },
            { id: 'archiveSortDropdown', inputId: 'archiveSort', icon: 'fa-sort-amount-down', action: () => this.loadArchiveRecords() },
            { id: 'archiveCategoryFilterDropdown', inputId: 'archiveCategoryFilter', icon: 'fa-tags', action: () => this.loadArchiveRecords() }
        ];

        setups.forEach(setup => {
            const dropdown = document.getElementById(setup.id);
            if (!dropdown) return;
            const toggle = dropdown.querySelector('.dropdown-toggle');
            const menu = dropdown.querySelector('.dropdown-menu');
            const input = document.getElementById(setup.inputId);

            toggle.addEventListener('click', (e) => {
                e.stopPropagation();
                // Alle anderen filter dropdowns schließen
                document.querySelectorAll('.custom-filter-dropdown').forEach(d => {
                    if (d !== dropdown) d.classList.remove('show');
                });
                dropdown.classList.toggle('show');
            });

            // Event-Delegation für Buttons (wichtig für Kategorien, die dynamisch geladen werden)
            menu.addEventListener('click', (e) => {
                const btn = e.target.closest('button');
                if (!btn) return;
                if (typeof btn.dataset.value === 'undefined') return; // Skip buttons without a data-value (like "Neue Kategorie erstellen")
                
                const val = btn.dataset.value;
                input.value = val;
                
                // Toggle-Inhalt aktualisieren
                toggle.innerHTML = `<i class="fas ${setup.icon}"></i> ${btn.textContent}`;
                dropdown.classList.remove('show');
                
                // selected-Klasse aktualisieren
                menu.querySelectorAll('button').forEach(b => b.classList.remove('selected'));
                btn.classList.add('selected');
                
                // Aktion auslösen
                this.saveUserPreferences();
                if (setup.action) setup.action();
            });

            // Initial selected-Klasse setzen
            const currentValue = input.value;
            menu.querySelectorAll('button').forEach(btn => {
                if (btn.dataset.value === currentValue) {
                    btn.classList.add('selected');
                }
            });
        });

        // Schließen beim Klick außerhalb
        document.addEventListener('click', () => {
            document.querySelectorAll('.custom-filter-dropdown').forEach(d => d.classList.remove('show'));
        });
    },

    updateFilterDropdownUI(dropdownId, value, iconClass) {
        const dropdown = document.getElementById(dropdownId);
        if (!dropdown) return;
        const btn = dropdown.querySelector(`.dropdown-menu button[data-value="${value}"]`);
        const toggle = dropdown.querySelector('.dropdown-toggle');
        if (btn && toggle) {
            toggle.innerHTML = `<i class="fas ${iconClass}"></i> ${btn.textContent}`;
        }
        // Alle Buttons durchlaufen und selected-Klasse entfernen/hinzufügen
        dropdown.querySelectorAll('.dropdown-menu button').forEach(button => {
            button.classList.remove('selected');
            if (button.dataset.value === value) {
                button.classList.add('selected');
            }
        });
    },

    initGalleryFilterDropdowns() {
        const setups = [
            { id: 'galleryFilterDropdown', inputId: 'galleryFilter', icon: 'fa-filter' },
            { id: 'gallerySortDropdown', inputId: 'gallerySort', icon: 'fa-sort-amount-down' },
            { id: 'galleryCategoryDropdown', inputId: 'galleryCategory', icon: 'fa-tags' }
        ];

        setups.forEach(setup => {
            const dropdown = document.getElementById(setup.id);
            if (!dropdown) return;
            const toggle = dropdown.querySelector('.dropdown-toggle');
            const menu = dropdown.querySelector('.dropdown-menu');
            const input = document.getElementById(setup.inputId);

            toggle.addEventListener('click', (e) => {
                e.stopPropagation();
                document.querySelectorAll('.custom-filter-dropdown').forEach(d => {
                    if (d !== dropdown) d.classList.remove('show');
                });
                dropdown.classList.toggle('show');
            });

            menu.addEventListener('click', (e) => {
                const btn = e.target.closest('button');
                if (!btn) return;
                if (typeof btn.dataset.value === 'undefined') return;
                
                const val = btn.dataset.value;
                input.value = val;
                
                toggle.innerHTML = `<i class="fas ${setup.icon}"></i> ${btn.textContent}`;
                dropdown.classList.remove('show');
                
                menu.querySelectorAll('button').forEach(b => b.classList.remove('selected'));
                btn.classList.add('selected');
                
                this.saveUserPreferences();
                this.loadGallery(false);
            });

            const currentValue = input.value;
            menu.querySelectorAll('button').forEach(btn => {
                if (btn.dataset.value === currentValue) {
                    btn.classList.add('selected');
                }
            });
        });
    },

    loadGalleryCategories() {
        const menu = document.getElementById('galleryCategoryMenu');
        const input = document.getElementById('galleryCategory');
        if (!menu || !input || !this.categories) return;

        menu.innerHTML = '<button type="button" data-value="">Alle Kategorien</button>';

        this.categories.forEach(cat => {
            const btn = document.createElement('button');
            btn.type = 'button';
            btn.dataset.value = cat.id;
            btn.textContent = cat.name;
            menu.appendChild(btn);
        });

        const currentValue = input.value;
        menu.querySelectorAll('button').forEach(btn => {
            if (btn.dataset.value === currentValue) {
                btn.classList.add('selected');
            }
        });
    },

    toggleGalleryMobileFilters() {
        const content = document.getElementById('galleryMobileFilterContent');
        if (content) {
            content.classList.toggle('show');
        }
    },

    async _createRecordWithForce(body, forceCreate, submitBtn, originalBtnText, savingOverlay) {
        // Hilfsfunktion zum Erstellen einer Akte mit force_create Flag
        body.force_create = forceCreate;
        
        // Button wieder deaktivieren für den eigentlichen Speichervorgang
        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Speichere...';
        }
        if (savingOverlay) {
            savingOverlay.style.display = 'flex';
        }
        
        const result = await this.apiPost('/records', body);
        this.toast('Akte erstellt', 'success');
        if (this.pendingReminder && result.record) {
            await this.apiPost(`/records/${result.record.id}/reminders`, this.pendingReminder);
        }
        this.pendingReminder = null;
        
        // Modal schließen nach dem Speichern
        this.closeModal(false, true);
        
        // Button wiederherstellen
        if (submitBtn) {
            submitBtn.disabled = false;
            submitBtn.innerHTML = originalBtnText;
        }
        if (savingOverlay) {
            savingOverlay.style.display = 'none';
        }
    },

    async saveRecord(ev) {
        ev.preventDefault();
        if (!this.currentUser?.can_write && this.currentUser?.role !== 'admin') {
            this.toast('Keine Schreibberechtigung', 'error'); return;
        }
        
        // Check if form is disabled (locked by other user)
        const titleField = document.getElementById('recordTitle');
        if (titleField && titleField.disabled) {
            this.toast('Akte ist gesperrt und kann nicht bearbeitet werden', 'error'); return;
        }

        // Validate reminder dates
        const reminderStartValue = document.getElementById('recordReminderDateValue').value;
        const reminderEndValue = document.getElementById('recordReminderEndDateValue').value;
        if (reminderStartValue && reminderEndValue) {
            const startDate = new Date(reminderStartValue);
            const endDate = new Date(reminderEndValue);
            if (endDate < startDate) {
                this.toast('Das Enddatum darf nicht vor dem Startdatum liegen!', 'error');
                return;
            }
        }

        // Validate repeat data
        const validateRepeatData = (data) => {
            if (!data) return true;
            if (typeof data === 'string') {
                return ['weekly', 'monthly', 'yearly'].includes(data);
            }
            if (!data.type) return false;
            switch (data.type) {
                case 'weekly':
                    return typeof data.weekday === 'number' && data.weekday >= 0 && data.weekday <= 6;
                case 'weekly_interval':
                    return (
                        typeof data.interval === 'number' && data.interval >= 1 && data.interval <= 5 &&
                        typeof data.weekday === 'number' && data.weekday >= 0 && data.weekday <= 6
                    );
                case 'monthly_interval':
                    return (
                        typeof data.interval === 'number' && data.interval >= 1 && data.interval <= 12 &&
                        (!data.mode || data.mode === 'date' || (
                            data.mode === 'weekday' &&
                            (data.nth === 'last' || (typeof data.nth === 'number' && data.nth >= 1 && data.nth <= 5)) &&
                            typeof data.weekday === 'number' && data.weekday >= 0 && data.weekday <= 6
                        ))
                    );
                case 'yearly_interval':
                    return typeof data.interval === 'number' && data.interval >= 1 && data.interval <= 10;
                case 'monthly':
                    return true;
                case 'monthly_nth_weekday':
                    return (
                        (
                            data.nth === 'last' ||
                            (typeof data.nth === 'number' && data.nth >= 1 && data.nth <= 5)
                        ) &&
                        typeof data.weekday === 'number' && data.weekday >= 0 && data.weekday <= 6
                    );
                case 'monthly_last_weekday':
                    return typeof data.weekday === 'number' && data.weekday >= 0 && data.weekday <= 6;
                case 'yearly':
                    return true;
                default:
                    return false;
            }
        };

        // Prepare reminder repeat value
        let reminderRepeat = null;
        let repeatDataObj = null;
        const repeatType = document.getElementById('recordReminderRepeat').value;
        if (repeatType) {
            if (repeatType === 'weekly') {
                repeatDataObj = {
                    type: 'weekly',
                    weekday: parseInt(document.getElementById('recordReminderWeekday').value, 10) || 1
                };
            } else if (repeatType === 'weekly_interval') {
                repeatDataObj = {
                    type: 'weekly_interval',
                    interval: parseInt(document.getElementById('recordReminderWeekInterval').value, 10) || 2,
                    weekday: parseInt(document.getElementById('recordReminderWeekday').value, 10) || 1
                };
            } else if (repeatType === 'monthly_interval') {
                const monthModeValue = document.getElementById('recordReminderMonthMode').value || 'date';
                repeatDataObj = {
                    type: 'monthly_interval',
                    interval: parseInt(document.getElementById('recordReminderMonthInterval').value, 10) || 2,
                    mode: monthModeValue
                };
                if (monthModeValue === 'weekday') {
                    const nthWeekdayValue = document.getElementById('recordReminderNthWeekday').value;
                    repeatDataObj.nth = (nthWeekdayValue === 'last' || nthWeekdayValue === '5') ? 'last' : (parseInt(nthWeekdayValue, 10) || 1);
                    repeatDataObj.weekday = parseInt(document.getElementById('recordReminderWeekday').value, 10) || 1;
                }
            } else if (repeatType === 'yearly_interval') {
                repeatDataObj = {
                    type: 'yearly_interval',
                    interval: parseInt(document.getElementById('recordReminderYearInterval').value, 10) || 2
                };
            } else if (repeatType === 'monthly_nth_weekday') {
                const nthWeekdayValue = document.getElementById('recordReminderNthWeekday').value;
                repeatDataObj = {
                    type: 'monthly_nth_weekday',
                    nth: (nthWeekdayValue === 'last' || nthWeekdayValue === '5') ? 'last' : (parseInt(nthWeekdayValue, 10) || 1),
                    weekday: parseInt(document.getElementById('recordReminderWeekday').value, 10) || 1
                };
            } else if (repeatType === 'monthly_last_weekday') {
                repeatDataObj = {
                    type: 'monthly_nth_weekday',
                    nth: 'last',
                    weekday: parseInt(document.getElementById('recordReminderWeekday').value, 10) || 1
                };
            } else {
                repeatDataObj = repeatType;
            }
            // Validate the repeat data
            if (!validateRepeatData(repeatDataObj)) {
                this.toast('Ungültige Wiederholungsdaten!', 'error');
                return;
            }

            // Stringify if it's an object
            if (typeof repeatDataObj === 'object') {
                reminderRepeat = JSON.stringify(repeatDataObj);
            } else {
                reminderRepeat = repeatDataObj;
            }
        }
        
        // Checkbox-Zustände persistent machen
        const contentElement = document.getElementById('recordContent');
        const checkboxes = contentElement.querySelectorAll('input[type="checkbox"]');
        checkboxes.forEach(checkbox => {
            if (checkbox.checked) {
                checkbox.setAttribute('checked', 'checked');
            } else {
                checkbox.removeAttribute('checked');
            }
        });

        const body = {
            title: document.getElementById('recordTitle').value.trim(),
            address: document.getElementById('recordAddress').value.trim(),
            content: this.sanitizeHtml(contentElement.innerHTML),
            hashtags: document.getElementById('recordHashtags').value,
            status: document.getElementById('recordStatus').value,
            border_color: document.getElementById('recordBorderColor').value,
            category_id: document.getElementById('recordCategory').value ? parseInt(document.getElementById('recordCategory').value, 10) : null,
            reminder_date: document.getElementById('recordReminderDateValue').value || null,
            reminder_end_date: document.getElementById('recordReminderEndDateValue').value || null,
            reminder_repeat: reminderRepeat,
            reminder_assigned_to: document.getElementById('recordReminderVisibility').value === 'private' ? this.currentUser.id : null
        };
        if (!body.title) { this.toast('Titel ist erforderlich', 'error'); return; }

        // Mehrfachklicks verhindern
        const submitBtn = document.getElementById('submitRecordBtn');
        if (submitBtn && submitBtn.disabled) {
            console.log('⚠️ Speichern bereits in Bearbeitung');
            return;
        }
        
        // Button deaktivieren und Lade-Animation zeigen
        const originalBtnText = submitBtn ? submitBtn.innerHTML : '';
        if (submitBtn) {
            submitBtn.disabled = true;
            submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Speichere...';
        }
        
        // Speichern-Overlay anzeigen für sofortiges Feedback
        const savingOverlay = document.getElementById('savingOverlay');
        if (savingOverlay) {
            savingOverlay.style.display = 'flex';
            // Nachricht je nach Online/Offline anpassen
            const savingText = savingOverlay.querySelector('p:first-of-type');
            if (savingText) {
                savingText.textContent = 'Prüfe Verbindung...';
            }
        }

        try {
            if (this.editingId) {
                // Prüfen ob es eine Offline-Akte ist (aus data Objekt oder records)
                const currentRecord = this.records.find(r => r.id === this.editingId);
                const isOfflineRecord = currentRecord?.is_offline || false;
                
                if (isOfflineRecord) {
                    // Offline-Akte direkt im IndexedDB aktualisieren
                    console.log('💾 Aktualisiere Offline-Akte:', body.title);
                    console.log('🔍 currentRecord.temp_id:', currentRecord.temp_id);
                    
                    const updatedOfflineRecord = {
                        title: body.title,
                        address: body.address,
                        content: body.content,
                        hashtags: body.hashtags,
                        status: body.status,
                        border_color: body.border_color,
                        category_id: body.category_id,
                        reminder_date: body.reminder_date,
                        reminder_end_date: body.reminder_end_date,
                        reminder_repeat: body.reminder_repeat,
                        reminder_assigned_to: body.reminder_assigned_to
                    };
                    
                    // Verwende direkt die temp_id aus currentRecord
                    const recordId = currentRecord.temp_id;
                    
                    console.log('🔍 Verwendete recordId für IndexedDB:', recordId);
                    
                    if (!recordId) {
                        console.error('❌ Keine temp_id gefunden!');
                        this.toast('Fehler beim Speichern: Keine temp_id', 'error');
                        // Button wiederherstellen
                        if (submitBtn) {
                            submitBtn.disabled = false;
                            submitBtn.innerHTML = originalBtnText;
                        }
                        return;
                    }
                    
                    await OfflineStorage.updatePendingRecord(recordId, updatedOfflineRecord);
                    this.toast('Akte offline aktualisiert (wird später synchronisiert)', 'info');
                    
                    // Lokale Liste aktualisieren
                    const recordIndex = this.records.findIndex(r => r.id === this.editingId);
                    if (recordIndex !== -1) {
                        this.records[recordIndex] = {
                            ...this.records[recordIndex],
                            ...updatedOfflineRecord
                        };
                    }
                    this.renderRecords();
                    
                    // Modal schließen
                    this.closeModal(false, true);
                } else {
                    // Online-Akte: Server-Verbindung prüfen
                    const isOnline = await this.checkServerConnection();
                    
                    // Overlay-Text aktualisieren
                    if (savingOverlay) {
                        const savingText = savingOverlay.querySelector('p:first-of-type');
                        if (savingText) {
                            savingText.textContent = isOnline ? 'Speichere...' : 'Speichere offline...';
                        }
                    }
                    if (!isOnline) {
                        // Offline speichern - Akte als Offline-Akte konvertieren
                        console.log('💾 Keine Server-Verbindung, speichere Akte offline');
                        
                        const offlineRecord = {
                            title: body.title,
                            address: body.address,
                            content: body.content,
                            hashtags: body.hashtags,
                            status: body.status,
                            border_color: body.border_color,
                            category_id: body.category_id,
                            reminder_date: body.reminder_date,
                            reminder_end_date: body.reminder_end_date,
                            reminder_repeat: body.reminder_repeat,
                            reminder_assigned_to: body.reminder_assigned_to,
                            // Speichere die ursprüngliche ID für spätere Synchronisation
                            _original_id: this.editingId,
                            user_id: this.currentUser.id,
                            user_name: this.currentUser.username,
                            temp_id: Date.now(),
                            number: null // Wird bei Sync zugewiesen
                        };
                        
                        await OfflineStorage.savePendingRecord(offlineRecord);
                        this.toast('Akte offline gespeichert (wird später synchronisiert)', 'info');
                        
                        // Lokale Liste aktualisieren - alte Online-Akte entfernen, Offline-Akte hinzufügen
                        this.records = this.records.filter(r => r.id !== this.editingId);
                        this.records.unshift({
                            id: offlineRecord.temp_id,
                            number: '???...',
                            title: offlineRecord.title,
                            content: offlineRecord.content,
                            hashtags: offlineRecord.hashtags,
                            status: offlineRecord.status,
                            border_color: offlineRecord.border_color,
                            address: offlineRecord.address,
                            created_at: new Date().toISOString(),
                            created_by_name: this.currentUser.username, // Benutzername für Anzeige
                            is_offline: true,
                            temp_id: offlineRecord.temp_id,
                            temp_record_id: offlineRecord.temp_id,
                            _original_id: this.editingId
                        });
                        this.renderRecords();
                        
                        // Sync-Button und Verbindungsstatus aktualisieren
                        await this.updateOfflineIndicator();
                        await this.checkConnectionStatus();
                        
                        // Modal schließen
                        this.closeModal(false, true);
                        return;
                    }
                    
                    // PLZ-Validierung beim Update
                    const plzCheck = await this.apiPost('/records/check-plz', {
                        address: body.address
                    }, false);

                    // Wenn Validierung deaktiviert ist, einfach weitermachen
                    if (plzCheck.warning === 'plz_invalid' && plzCheck.validation_disabled !== true) {
                        // PLZ nicht gefunden - Dialog anzeigen
                        const plzWarning = plzCheck.message;
                        
                        // Button wiederherstellen vor dem Dialog
                        if (submitBtn) {
                            submitBtn.disabled = false;
                            submitBtn.innerHTML = originalBtnText;
                        }
                        if (savingOverlay) {
                            savingOverlay.style.display = 'none';
                        }
                        
                        // Dialog erstellen
                        const plzDialog = document.createElement('div');
                        plzDialog.className = 'modal-overlay show';
                        plzDialog.style.zIndex = '10000';
                        plzDialog.style.visibility = 'visible';
                        plzDialog.style.opacity = '1';
                        
                        plzDialog.innerHTML = `
                            <div class="modal" id="plzModal" style="max-width: 700px; width: 700px;">
                                <div class="modal-header">
                                    <h3>⚠️ Postleitzahl-Warnung</h3>
                                    <div class="modal-header-actions">
                                        <button class="header-btn" id="plzFullscreen" aria-label="Vollbild" title="Vollbildmodus">
                                            <i class="fas fa-expand"></i>
                                        </button>
                                        <button class="header-btn" id="plzClose" aria-label="Schliessen">
                                            <i class="fas fa-times"></i>
                                        </button>
                                    </div>
                                </div>
                                <div class="modal-body">
                                    <p>${plzWarning}</p>
                                </div>
                                <div class="modal-footer">
                                    <button class="btn btn-secondary" id="plzCancel">Abbrechen</button>
                                    <button class="btn btn-primary" id="plzForceSave">Trotzdem speichern</button>
                                </div>
                            </div>
                        `;
                        
                        document.body.appendChild(plzDialog);
                        
                        // Event-Handler für Dialog-Buttons
                        const userChoice = await new Promise((resolve) => {
                            const plzCancel = document.getElementById('plzCancel');
                            const plzForceSave = document.getElementById('plzForceSave');
                            const plzClose = document.getElementById('plzClose');
                            const plzFullscreen = document.getElementById('plzFullscreen');
                            const plzModal = document.getElementById('plzModal');
                            
                            const cleanup = () => {
                                plzDialog.remove();
                                if (submitBtn) {
                                    submitBtn.disabled = false;
                                    submitBtn.innerHTML = originalBtnText;
                                }
                            };
                            
                            plzCancel.addEventListener('click', () => {
                                cleanup();
                                resolve('cancel');
                            });
                            
                            plzClose.addEventListener('click', () => {
                                cleanup();
                                resolve('cancel');
                            });
                            
                            plzForceSave.addEventListener('click', async () => {
                                cleanup();
                                resolve('force');
                            });
                            
                            // Vollbild-Funktionalität
                            let isFullscreen = false;
                            plzFullscreen.addEventListener('click', () => {
                                isFullscreen = !isFullscreen;
                                if (isFullscreen) {
                                    plzModal.classList.add('fullscreen');
                                } else {
                                    plzModal.classList.remove('fullscreen');
                                }
                            });
                        });
                        
                        // Wenn abgebrochen, hier stoppen
                        if (userChoice === 'cancel') {
                            return;
                        }
                        
                        // Wenn "Trotzdem speichern", mit force_create flag weitermachen
                        body.force_create = true;
                    }
                    
                    await this.apiPut(`/records/${this.editingId}`, body);
                    this.toast('Akte gespeichert', 'success');

                    // Standardwerte speichern
                    await this.saveRecordDefaults();

                    // Modal schließen nach dem Speichern
                    this.closeModal(false, true);
                }
            } else {
                // Neue Akte - Online oder Offline
                const isOnline = await this.checkServerConnection();
                console.log(`📡 Server-Status für Speichern: ${isOnline ? 'Online' : 'Offline'}`);
                
                // Overlay-Text aktualisieren
                if (savingOverlay) {
                    const savingText = savingOverlay.querySelector('p:first-of-type');
                    if (savingText) {
                        savingText.textContent = isOnline ? 'Speichere...' : 'Speichere offline...';
                    }
                }
                
                if (isOnline) {
                    // PLZ-Validierung vor der Erstellung
                    const plzCheck = await this.apiPost('/records/check-plz', {
                        address: body.address
                    }, false);

                    // Wenn Validierung deaktiviert ist, einfach weitermachen
                    if (plzCheck.warning === 'plz_invalid' && !plzCheck.validation_disabled) {
                        // PLZ nicht gefunden - Dialog anzeigen
                        const plzWarning = plzCheck.message;
                        
                        // Button wiederherstellen vor dem Dialog
                        if (submitBtn) {
                            submitBtn.disabled = false;
                            submitBtn.innerHTML = originalBtnText;
                        }
                        if (savingOverlay) {
                            savingOverlay.style.display = 'none';
                        }
                        
                        // Dialog erstellen
                        const plzDialog = document.createElement('div');
                        plzDialog.className = 'modal-overlay show';
                        plzDialog.style.zIndex = '10000';
                        plzDialog.style.visibility = 'visible';
                        plzDialog.style.opacity = '1';
                        
                        plzDialog.innerHTML = `
                            <div class="modal" id="plzModal" style="max-width: 700px; width: 700px;">
                                <div class="modal-header">
                                    <h3>⚠️ Postleitzahl-Warnung</h3>
                                    <div class="modal-header-actions">
                                        <button class="header-btn" id="plzFullscreen" aria-label="Vollbild" title="Vollbildmodus">
                                            <i class="fas fa-expand"></i>
                                        </button>
                                        <button class="header-btn" id="plzClose" aria-label="Schliessen">
                                            <i class="fas fa-times"></i>
                                        </button>
                                    </div>
                                </div>
                                <div class="modal-body">
                                    <p>${plzWarning}</p>
                                </div>
                                <div class="modal-footer">
                                    <button class="btn btn-secondary" id="plzCancel">Abbrechen</button>
                                    <button class="btn btn-primary" id="plzForceSave">Trotzdem speichern</button>
                                </div>
                            </div>
                        `;
                        
                        document.body.appendChild(plzDialog);
                        
                        const userChoice = await new Promise((resolve) => {
                            const plzCancel = document.getElementById('plzCancel');
                            const plzForceSave = document.getElementById('plzForceSave');
                            const plzClose = document.getElementById('plzClose');
                            const plzFullscreen = document.getElementById('plzFullscreen');
                            const plzModal = document.getElementById('plzModal');
                            
                            const cleanup = () => {
                                plzDialog.remove();
                                if (submitBtn) {
                                    submitBtn.disabled = false;
                                    submitBtn.innerHTML = originalBtnText;
                                }
                            };
                            
                            plzCancel.addEventListener('click', () => {
                                cleanup();
                                resolve('cancel');
                            });
                            
                            plzClose.addEventListener('click', () => {
                                cleanup();
                                resolve('cancel');
                            });
                            
                            plzForceSave.addEventListener('click', async () => {
                                cleanup();
                                resolve('force');
                            });
                            
                            // Vollbild-Funktionalität
                            let isFullscreen = false;
                            plzFullscreen.addEventListener('click', () => {
                                isFullscreen = !isFullscreen;
                                if (isFullscreen) {
                                    plzModal.classList.add('fullscreen');
                                } else {
                                    plzModal.classList.remove('fullscreen');
                                }
                            });
                        });
                        
                        // Wenn abgebrochen, hier stoppen
                        if (userChoice === 'cancel') {
                            return;
                        }
                        
                        // Wenn "Trotzdem speichern", mit force_create flag weitermachen
                        body.force_create = true;
                    }
                    
                    // Dublettenerkennung vor der Erstellung
                    const duplicateCheck = await this.apiPost('/records/check-duplicates', {
                        title: body.title,
                        content: body.content,
                        address: body.address,
                        hashtags: body.hashtags
                    }, false);

                    if (duplicateCheck.duplicate_check && duplicateCheck.duplicate_check.has_duplicates) {
                        // Dubletten gefunden - Dialog anzeigen
                        const duplicates = duplicateCheck.duplicate_check.duplicates;
                        const threshold = duplicateCheck.duplicate_check.threshold;
                        
                        // Button wiederherstellen vor dem Dialog
                        if (submitBtn) {
                            submitBtn.disabled = false;
                            submitBtn.innerHTML = originalBtnText;
                        }
                        if (savingOverlay) {
                            savingOverlay.style.display = 'none';
                        }
                        
                        // Dialog erstellen
                        const duplicateDialog = document.createElement('div');
                        duplicateDialog.className = 'modal-overlay show';
                        duplicateDialog.style.zIndex = '10000';
                        duplicateDialog.style.visibility = 'visible';
                        duplicateDialog.style.opacity = '1';
                        
                        const isExactMatch = duplicates.some(d => d.is_exact_match);
                        const dialogTitle = isExactMatch ? '⚠️ Akte mit gleichem Titel oder Inhalt existiert bereits' : '⚠️ Ähnliche Akten gefunden';
                        const dialogMessage = isExactMatch 
                            ? `Möchten Sie zur existierenden Akte wechseln oder trotzdem eine neue erstellen?`
                            : `Es wurden ${duplicates.length} ähnliche Akten gefunden. Möchten Sie:`;
                        
                        duplicateDialog.innerHTML = `
                            <div class="modal" id="duplicateModal" style="max-width: 700px; width: 700px; height: 85vh;">
                                <div class="modal-header">
                                    <h3>${dialogTitle}</h3>
                                    <div class="modal-header-actions">
                                        <button class="header-btn" id="duplicateFullscreen" aria-label="Vollbild" title="Vollbildmodus">
                                            <i class="fas fa-expand"></i>
                                        </button>
                                        <button class="header-btn" id="duplicateClose" aria-label="Schliessen">
                                            <i class="fas fa-times"></i>
                                        </button>
                                    </div>
                                </div>
                                <div class="modal-body" style="overflow: hidden; display: flex; flex-direction: column;" id="duplicateModalBody">
                                    <p>${dialogMessage}</p>
                                    <div class="duplicate-list" style="flex: 1; overflow-y: auto; margin: 15px 0; min-height: 200px;">
                                        ${duplicates.map(dup => `
                                            <div class="duplicate-item" style="padding: 12px; border: 1px solid var(--border-color); border-radius: var(--radius); cursor: pointer; transition: background 0.2s, border-color 0.2s; border-left: ${dup.is_exact_match ? '4px solid var(--primary, #3b82f6)' : '4px solid var(--border-color)'}; margin-bottom: 0;" data-id="${dup.id}">
                                                <div style="font-weight: 600; color: var(--text-main); display: flex; justify-content: space-between; align-items: center;">
                                                    <span>#${dup.number} - ${dup.title}</span>
                                                    ${dup.is_exact_match ? '<span style="font-size: 0.75em; background: var(--primary, #3b82f6); color: white; padding: 2px 8px; border-radius: 12px;">Exakt</span>' : ''}
                                                </div>
                                                <div style="font-size: 0.9em; color: var(--text-muted); margin-top: 4px;">${dup.content.substring(0, 100)}${dup.content.length > 100 ? '...' : ''}</div>
                                            </div>
                                        `).join('')}
                                    </div>
                                    <style>
                                        .duplicate-item {
                                            background: #ffffff !important;
                                            margin-bottom: 0 !important;
                                            outline: none !important;
                                            border: 1px solid var(--border-color) !important;
                                        }
                                        .duplicate-item::after,
                                        .duplicate-item::before {
                                            content: none !important;
                                            display: none !important;
                                        }
                                        body.dark-mode .duplicate-item {
                                            background: #252525 !important;
                                            border: 1px solid var(--border-color) !important;
                                        }
                                        .duplicate-item:hover {
                                            background: #3b82f6 !important;
                                            border-color: #3b82f6 !important;
                                            margin-bottom: 0 !important;
                                            box-shadow: none !important;
                                            outline: none !important;
                                            -webkit-box-shadow: none !important;
                                            text-shadow: none !important;
                                        }
                                        .duplicate-item:hover::after,
                                        .duplicate-item:hover::before {
                                            content: none !important;
                                            display: none !important;
                                        }
                                        body.dark-mode .duplicate-item:hover {
                                            background: #3b82f6 !important;
                                            border-color: #3b82f6 !important;
                                            margin-bottom: 0 !important;
                                            box-shadow: none !important;
                                            outline: none !important;
                                            -webkit-box-shadow: none !important;
                                            text-shadow: none !important;
                                        }
                                        .duplicate-item:hover > div,
                                        .duplicate-item:hover > div > span,
                                        .duplicate-item:hover > div > div {
                                            color: #ffffff !important;
                                        }
                                        .duplicate-list::-webkit-scrollbar {
                                            width: 8px;
                                        }
                                        .duplicate-list::-webkit-scrollbar-track {
                                            background: transparent;
                                        }
                                        .duplicate-list::-webkit-scrollbar-thumb {
                                            background: #ccc;
                                            border-radius: 4px;
                                        }
                                        .duplicate-list::-webkit-scrollbar-thumb:hover {
                                            background: #999;
                                        }
                                        body.dark-mode .duplicate-list::-webkit-scrollbar-thumb {
                                            background: #444;
                                        }
                                        body.dark-mode .duplicate-list::-webkit-scrollbar-thumb:hover {
                                            background: #666;
                                        }
                                    </style>
                                </div>
                                <div class="modal-footer">
                                    <button class="btn btn-secondary" id="cancelDuplicateBtn">Abbrechen</button>
                                    <button class="btn btn-primary" id="forceCreateBtn">Trotzdem erstellen</button>
                                </div>
                            </div>
                        `;
                        document.body.appendChild(duplicateDialog);

                        // Event-Handler mit Promise
                        const userChoice = await new Promise((resolve) => {
                            const cancelBtn = duplicateDialog.querySelector('#cancelDuplicateBtn');
                            const forceBtn = duplicateDialog.querySelector('#forceCreateBtn');
                            const closeBtn = duplicateDialog.querySelector('#duplicateClose');
                            const fullscreenBtn = duplicateDialog.querySelector('#duplicateFullscreen');
                            const duplicateItems = duplicateDialog.querySelectorAll('.duplicate-item');
                            const duplicateModal = duplicateDialog.querySelector('#duplicateModal');

                            cancelBtn.addEventListener('click', () => {
                                duplicateDialog.remove();
                                resolve('cancel');
                            });

                            forceBtn.addEventListener('click', () => {
                                duplicateDialog.remove();
                                resolve('force');
                            });

                            closeBtn.addEventListener('click', () => {
                                duplicateDialog.remove();
                                resolve('cancel');
                            });

                            // Vollbild-Funktionalität
                            let isFullscreen = false;
                            fullscreenBtn.addEventListener('click', () => {
                                isFullscreen = !isFullscreen;
                                if (isFullscreen) {
                                    duplicateModal.classList.add('fullscreen');
                                } else {
                                    duplicateModal.classList.remove('fullscreen');
                                }
                            });

                            // Klick auf eine Dublette - zur existierenden Akte wechseln
                            duplicateItems.forEach(item => {
                                item.addEventListener('click', () => {
                                    const recordId = parseInt(item.dataset.id);
                                    duplicateDialog.remove();
                                    resolve({ action: 'switch', recordId });
                                });
                            });
                        });
                        
                        // User-Choice verarbeiten
                        if (userChoice === 'cancel') {
                            return; // Abbrechen, nichts tun
                        } else if (userChoice === 'force') {
                            // Erzwingen der Erstellung
                            body.force_create = true;
                        } else if (userChoice && userChoice.action === 'switch') {
                            // Zur existierenden Akte wechseln
                            this.closeModal(false, true);
                            this.openRecord(userChoice.recordId);
                            return;
                        }
                        
                        // Button wieder deaktivieren für den eigentlichen Speichervorgang
                        if (submitBtn) {
                            submitBtn.disabled = true;
                            submitBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Speichere...';
                        }
                        if (savingOverlay) {
                            savingOverlay.style.display = 'flex';
                        }
                    }

                    const result = await this.apiPost('/records', body);
                    this.toast('Akte erstellt', 'success');
                    if (this.pendingReminder && result.record) {
                        await this.apiPost(`/records/${result.record.id}/reminders`, this.pendingReminder);
                        // Keine separate Toast-Meldung für Erinnerung
                    }
                    this.pendingReminder = null;

                    // Standardwerte speichern
                    await this.saveRecordDefaults();

                    // Modal schließen nach dem Speichern
                    this.closeModal(false, true);
                } else {
                    // Offline: Akte lokal speichern
                    console.log('💾 Speichere Akte offline:', body.title);
                    console.log('👤 Aktueller Benutzer:', this.currentUser);
                    
                    // Erinnerungen-Array für IndexedDB erstellen
                    const erinnerungenArray = [];
                    if (this.pendingReminder) {
                        erinnerungenArray.push({
                            id: Date.now(), // Temporäre ID
                            reminder_date: this.pendingReminder.reminder_date,
                            assigned_to: this.pendingReminder.assigned_to,
                            note: this.pendingReminder.note,
                            completed: 0,
                            created_by: this.currentUser.id,
                            created_by_username: this.currentUser.username
                        });
                    }
                    
                    const offlineRecord = {
                        title: body.title,
                        content: body.content,
                        hashtags: body.hashtags,
                        status: body.status,
                        border_color: body.border_color,
                        address: body.address,
                        category_id: body.category_id,
                        reminder_date: body.reminder_date,
                        reminder_end_date: body.reminder_end_date,
                        reminder_repeat: body.reminder_repeat,
                        reminder_assigned_to: body.reminder_assigned_to,
                        pending_reminder: this.pendingReminder,
                        erinnerungen: erinnerungenArray, // Erinnerungen für IndexedDB
                        user_id: this.currentUser.id,
                        user_name: this.currentUser.username || this.currentUser.name || 'Unbekannt',
                        // Temporäre ID für Anzeige - KEINE Nummer vergeben, wird erst bei Sync zugewiesen
                        temp_id: Date.now(),
                        number: null // Keine Nummer offline - wird vom Server bei Sync zugewiesen
                    };
                    
                    await OfflineStorage.savePendingRecord(offlineRecord);
                    this.toast('Akte offline erstellt (wird später synchronisiert)', 'info');
                    this.pendingReminder = null;
                    
                    // Offline-Akte zur Liste hinzufügen für sofortige Anzeige
                    this.records.unshift({
                        id: offlineRecord.temp_id,
                        number: '???...', // Platzhalter für offline-Akten (da is_offline Markierung existiert)
                        title: offlineRecord.title,
                        content: offlineRecord.content,
                        hashtags: offlineRecord.hashtags,
                        status: offlineRecord.status,
                        border_color: offlineRecord.border_color,
                        address: offlineRecord.address,
                        created_at: new Date().toISOString(),
                        created_by_name: offlineRecord.user_name, // Benutzername für Anzeige
                        reminder_date: offlineRecord.reminder_date, // Termin für sofortige Anzeige
                        reminder_end_date: offlineRecord.reminder_end_date,
                        reminder_repeat: offlineRecord.reminder_repeat,
                        reminder_assigned_to: offlineRecord.reminder_assigned_to,
                        reminder_is_private: Boolean(offlineRecord.reminder_assigned_to),
                        erinnerungen: erinnerungenArray, // Erinnerungen für Glocken-Anzeige
                        is_offline: true, // Markierung für offline-Akte
                        temp_id: offlineRecord.temp_id, // Für Bearbeitung wichtig
                        temp_record_id: offlineRecord.temp_id // Für Datei-Zuordnung
                    });
                    this.renderRecords();
                    
                    // Sync-Button und Verbindungsstatus sofort aktualisieren
                    await this.updateOfflineIndicator();
                    await this.checkConnectionStatus();
                    
                    // Modal schließen (ohne ungespeicherte Änderungen-Check)
                    this.closeModal(false, true);
                }
            }
            
            this.hasChanges = false;
            
            // Nur Online Liste neu laden
            const isOnline = await this.checkServerConnection();
            if (isOnline) {
                this.loadRecords();
            }
            
            await this.loadReminders();
            if (this.currentSection === 'dashboard') this.loadDashboard();
            if (this.currentSection === 'dashboard') this.renderCalendarChart();
            if (this.currentSection === 'calendar') this.renderCalendar();
        } catch (e) {
            this.toast(e.message, 'error');
        } finally {
            // Button immer wiederherstellen
            if (submitBtn) {
                submitBtn.disabled = false;
                submitBtn.innerHTML = originalBtnText;
            }
            
            // Speichern-Overlay immer ausblenden
            if (savingOverlay) {
                savingOverlay.style.display = 'none';
            }
        }
    },

    async deleteRecord() {
        if (!this.editingId) return;
        if (!await this.confirm('Akte löschen?', 'Diese Aktion kann nicht rückgängig gemacht werden.')) return;
        try {
            console.log('Deleting record:', this.editingId);
            
            // Prüfen ob es eine Offline-Akte ist
            const currentRecord = this.records.find(r => r.id === this.editingId);
            const isOfflineRecord = currentRecord?.is_offline;
            
            if (isOfflineRecord) {
                // Offline-Akte direkt im IndexedDB löschen
                console.log('💾 Lösche Offline-Akte:', this.editingId);
                console.log('🔍 currentRecord.temp_id:', currentRecord.temp_id);
                
                // Verwende temp_id für die Löschung (wie bei updatePendingRecord)
                await OfflineStorage.deletePendingRecord(currentRecord.temp_id);
                this.toast('Akte offline gelöscht', 'success');
                
                // Aus lokaler Liste entfernen
                this.records = this.records.filter(r => r.id !== this.editingId);
                this.renderRecords();
                
                // Sync-Button und Verbindungsstatus aktualisieren
                await this.updateOfflineIndicator();
                await this.checkConnectionStatus();
            } else {
                // Online-Akte: Server-Verbindung prüfen
                const isOnline = await this.checkServerConnection();
                if (!isOnline) {
                    this.toast('Löschen nur Online möglich', 'warning');
                    return;
                }
                
                const result = await this.apiDelete(`/records/${this.editingId}`);
                console.log('Delete result:', result);
                this.toast('Akte geloescht', 'success');
                this.loadRecords();
                this.loadDashboard();
                this.renderCalendarChart();
                if (this.currentSection === 'calendar') this.renderCalendar();
            }
            
            this.hasChanges = false;
            this.currentLock = null;
            this.closeModal(true);
        } catch (e) {
            console.error('Fehler beim Löschen:', e);
            this.toast(e.message, 'error');
        }
    },

    clearModal() {
        const modal = document.getElementById('recordModal');
        const fullscreenBtn = document.getElementById('modalFullscreen');
        const maximizeBtn = document.getElementById('maximizeEditorBtn');
        const fullscreenIcon = fullscreenBtn?.querySelector('i');
        const maximizeIcon = maximizeBtn?.querySelector('i');
        
        document.getElementById('recordForm').reset();
        
        // Reset pending reminder
        this.pendingReminder = null;
        
        // Reset modal state
        modal.classList.remove('fullscreen', 'editor-maximized');
        if (fullscreenIcon) fullscreenIcon.className = 'fas fa-expand';
        if (maximizeIcon) maximizeIcon.className = 'fas fa-expand';
        if (fullscreenBtn) fullscreenBtn.title = 'Vollbildmodus';
        if (maximizeBtn) maximizeBtn.title = 'Editor vergrößern';
        
        // Aktennummer-Feld zurücksetzen und verstecken
        const numGroup = document.getElementById('recordNumberGroup');
        if (numGroup) numGroup.style.display = 'none';

        const addressField = document.getElementById('recordAddress');
        if (addressField) addressField.value = '';
        const statusSelect = document.getElementById('recordStatus');
        if (statusSelect) statusSelect.value = 'offen';
        const colorSelect = document.getElementById('recordBorderColor');
        if (colorSelect) colorSelect.value = '';
        const categoryInput = document.getElementById('recordCategory');
        if (categoryInput) categoryInput.value = '';
        
        // Custom Dropdowns UI zurücksetzen
        this.updateModalDropdownUI('modalStatusDropdown', 'offen');
        this.updateModalDropdownUI('modalColorDropdown', '');
        this.updateModalDropdownUI('modalCategoryDropdown', '');
        this.updateModalDropdownUI('modalRepeatDropdown', '');
        this.updateModalDropdownUI('modalReminderVisibilityDropdown', 'all');

        document.getElementById('recordReminderDateValue').value = '';
        document.getElementById('recordReminderDate').value = '';
        document.getElementById('recordReminderEndDateValue').value = '';
        document.getElementById('recordReminderEndDate').value = '';
        document.getElementById('recordReminderVisibility').value = 'all';
        document.getElementById('recordReminderWeekInterval').value = 2;
        document.getElementById('recordReminderMonthInterval').value = 2;
        document.getElementById('recordReminderMonthMode').value = 'date';
        document.getElementById('recordReminderYearInterval').value = 2;
        this.updateModalDropdownUI('modalWeekIntervalDropdown', '2');
        this.updateModalDropdownUI('modalMonthIntervalDropdown', '2');
        this.updateModalDropdownUI('modalMonthModeDropdown', 'date');
        this.updateModalDropdownUI('modalYearIntervalDropdown', '2');
        this.updateModalDropdownUI('modalNthWeekdayDropdown', '1');
        this.updateModalDropdownUI('modalWeekdayDropdown', '1');
        document.getElementById('advancedRepeatOptions').classList.add('hidden');
        
        document.getElementById('recordContent').innerHTML = '';
        document.getElementById('attachmentList').innerHTML = '';
        document.getElementById('lockBanner').classList.add('hidden');
        document.getElementById('mediaPlayerSection').classList.remove('show');
        document.getElementById('mediaPlayerContent').innerHTML = '';
        
        // Show add reminder button again
        const addButton = document.querySelector('.reminders-section .btn-primary');
        if (addButton) addButton.style.display = 'inline-flex';

        // Standard-Checkboxes zurücksetzen
        const setDefaultStatus = document.getElementById('setDefaultStatus');
        const setDefaultCategory = document.getElementById('setDefaultCategory');
        const setDefaultNote = document.getElementById('setDefaultNote');
        const setDefaultColor = document.getElementById('setDefaultColor');
        if (setDefaultStatus) setDefaultStatus.checked = false;
        if (setDefaultCategory) setDefaultCategory.checked = false;
        if (setDefaultNote) setDefaultNote.checked = false;
        if (setDefaultColor) setDefaultColor.checked = false;
    },

    async loadAndApplyRecordDefaults() {
        try {
            const response = await this.apiGet('/users/me/preferences');
            const prefs = response.preferences || {};
            const defaults = prefs.record_defaults || {};

            // Standardwerte anwenden
            if (defaults.status !== undefined) {
                document.getElementById('recordStatus').value = defaults.status;
                this.updateModalDropdownUI('modalStatusDropdown', defaults.status);
                const setDefaultStatus = document.getElementById('setDefaultStatus');
                if (setDefaultStatus) setDefaultStatus.checked = true;
            }
            if (defaults.category_id !== undefined) {
                document.getElementById('recordCategory').value = defaults.category_id;
                this.updateModalDropdownUI('modalCategoryDropdown', defaults.category_id);
                const setDefaultCategory = document.getElementById('setDefaultCategory');
                if (setDefaultCategory) setDefaultCategory.checked = true;
            }
            if (defaults.hashtags !== undefined) {
                document.getElementById('recordHashtags').value = defaults.hashtags;
                const setDefaultNote = document.getElementById('setDefaultNote');
                if (setDefaultNote) setDefaultNote.checked = true;
            }
            if (defaults.border_color !== undefined) {
                document.getElementById('recordBorderColor').value = defaults.border_color;
                this.updateModalDropdownUI('modalColorDropdown', defaults.border_color);
                const setDefaultColor = document.getElementById('setDefaultColor');
                if (setDefaultColor) setDefaultColor.checked = true;
            }
        } catch (e) {
            console.error('Fehler beim Laden der Standardwerte:', e);
        }
    },

    async saveRecordDefaults() {
        try {
            const response = await this.apiGet('/users/me/preferences');
            const prefs = response.preferences || {};
            const defaults = prefs.record_defaults || {};

            // Checkboxen prüfen und entsprechende Werte speichern
            const setDefaultStatus = document.getElementById('setDefaultStatus');
            const setDefaultCategory = document.getElementById('setDefaultCategory');
            const setDefaultNote = document.getElementById('setDefaultNote');
            const setDefaultColor = document.getElementById('setDefaultColor');

            // Status
            if (setDefaultStatus && setDefaultStatus.checked) {
                defaults.status = document.getElementById('recordStatus').value;
            } else {
                delete defaults.status;
            }

            // Kategorie
            if (setDefaultCategory && setDefaultCategory.checked) {
                defaults.category_id = document.getElementById('recordCategory').value;
            } else {
                delete defaults.category_id;
            }

            // Vermerk
            if (setDefaultNote && setDefaultNote.checked) {
                defaults.hashtags = document.getElementById('recordHashtags').value;
            } else {
                delete defaults.hashtags;
            }

            // Rahmenfarbe
            if (setDefaultColor && setDefaultColor.checked) {
                defaults.border_color = document.getElementById('recordBorderColor').value;
            } else {
                delete defaults.border_color;
            }

            prefs.record_defaults = defaults;
            await this.apiPut('/users/me/preferences', { preferences: prefs });
        } catch (e) {
            console.error('Fehler beim Speichern der Standardwerte:', e);
        }
    },

    showModal(id) {
        const overlay = document.getElementById(id).closest('.modal-overlay');
        if (overlay) overlay.classList.add('show');
        document.body.style.overflow = 'hidden';
        // Scroll modal body to top
        const modal = document.getElementById(id);
        const modalBody = modal.querySelector('.modal-body');
        if (modalBody) {
            modalBody.scrollTop = 0;
        }
        
        // Speichern-Overlay verstecken (falls noch sichtbar)
        const savingOverlay = document.getElementById('savingOverlay');
        if (savingOverlay) {
            savingOverlay.style.display = 'none';
        }
        
        // Wenn es das Record-Modal ist, Datei-Upload-Verfügbarkeit prüfen
        if (id === 'recordModal') {
            this.updateFileUploadAvailability();
        }
    },

    async closeModal(force = false, skipChangesCheck = false) {
        if (!force && !skipChangesCheck && this.hasChanges) {
            if (!await this.confirm('Ungespeicherte Änderungen', 'Möchten Sie die Akte wirklich verlassen, ohne zu speichern? Alle Änderungen gehen verloren.', 'Ja, verlassen', 'btn-danger')) {
                return;
            }
        }

        // --- SOFORTIGES AUSBLENDEN (Gegen Blitzen/Verzögerung) ---
        document.querySelectorAll('.modal-overlay').forEach(m => m.classList.remove('show'));
        document.body.style.overflow = '';
        
        // --- CLEANUP IM HINTERGRUND ---
        const recordIdToUnlock = this.editingId;
        const needsUnlock = this.editingId && this.currentLock;

        this.stopLockCheck();
        this.editingId = null;
        this.currentLock = null;
        this.hasChanges = false;
        
        if (needsUnlock) {
            // Nicht 'await'en, damit das UI sofort reagiert
            this.unlockRecord(recordIdToUnlock).catch(()=>{});
        }
        
        // Reset fullscreen state
        const modal = document.getElementById('recordModal');
        const fullscreenBtn = document.getElementById('modalFullscreen');
        const icon = fullscreenBtn.querySelector('i');
        
        modal.classList.remove('fullscreen');
        icon.className = 'fas fa-expand';
        fullscreenBtn.title = 'Vollbildmodus';
        fullscreenBtn.setAttribute('aria-label', 'Vollbild');
        
        // Reset editor maximized state
        modal.classList.remove('editor-maximized');
        const maxBtn = document.getElementById('maximizeEditorBtn');
        if (maxBtn) {
            maxBtn.querySelector('i').className = 'fas fa-expand';
            maxBtn.title = 'Editor vergrößern';
        }
        
        document.querySelectorAll('.modal-overlay').forEach(m => m.classList.remove('show'));
        document.body.style.overflow = '';
    },

    async unlockRecord(id) {
        await this.apiPost(`/records/${id}/unlock`);
        this.currentLock = null;
    },

    startLockCheck(id) {
        this.stopLockCheck();
        this.lockHeartbeatInterval = setInterval(async () => {
            try {
                // Heartbeat um Lock zu verlängern (Hintergrund)
                await this.apiPost(`/records/${id}/heartbeat`, null, false);
                
                // Prüfen ob Lock noch existiert (kann durch Cleanup entfernt worden sein)
                const data = await this.apiGet(`/records/${id}/lock-info`, false);
                if (!data.locked && this.editingId === id) {
                    // Lock wurde durch Backend-Cleanup entfernt, automatisch wieder sperren
                    console.log('Lock wurde entfernt, versuche erneut zu sperren...');
                    try {
                        await this.apiPost(`/records/${id}/lock`, null, false);
                        this.currentLock = id;
                    } catch (e) {
                        // Konnte nicht sperren, evtl. jetzt von jemand anderem gesperrt
                        console.warn('Konnte Lock nicht erneuern:', e);
                        if (e.response && e.response.status === 423) {
                            this.toast('Akte wurde von einem anderen Benutzer gesperrt', 'warning');
                            this.currentLock = null;
                            this.stopLockCheck();
                        }
                    }
                } else if (data.locked && data.lock_info?.user_id !== this.currentUser.id) {
                    // Someone else took the lock
                    this.toast(`Akte wurde von ${data.lock_info.username} gesperrt`, 'warning');
                    this.closeModal();
                }
            } catch { /* ignore */ }
        }, 10000); // Alle 10 Sekunden (schneller für bessere Reaktion)
        
        // Page Visibility API für Tab-Wechsel
        this.setupVisibilityHandler(id);
    },

    stopLockCheck() {
        if (this.lockHeartbeatInterval) { clearInterval(this.lockHeartbeatInterval); this.lockHeartbeatInterval = null; }
        if (this.visibilityHandler) {
            document.removeEventListener('visibilitychange', this.visibilityHandler);
            this.visibilityHandler = null;
        }
        if (this.beforeUnloadHandler) {
            window.removeEventListener('beforeunload', this.beforeUnloadHandler);
            this.beforeUnloadHandler = null;
        }
    },

    setupVisibilityHandler(id) {
        // Page Visibility API - Tab wird inaktiv
        this.visibilityHandler = async () => {
            if (document.hidden && this.editingId === id) {
                // Tab ist inaktiv, kein Heartbeat mehr
            } else if (!document.hidden && this.editingId === id) {
                // Tab wird wieder aktiv, sofort Heartbeat
                try {
                    await this.apiPost(`/records/${id}/heartbeat`);
                } catch (e) {
                    console.error('Heartbeat fehlgeschlagen:', e);
                }
            }
        };
        
        document.addEventListener('visibilitychange', this.visibilityHandler);
        
        // BeforeUnload Event - Tab wird geschlossen
        this.beforeUnloadHandler = () => {
            if (this.editingId === id) {
                // Synchron entsperren vor dem Schließen
                navigator.sendBeacon(`/api/records/${id}/unlock`);
            }
        };
        
        window.addEventListener('beforeunload', this.beforeUnloadHandler);
    },

    // ── Attachments ────────────────────────────────
    getMediaType(filename) {
        const f = filename.toLowerCase();
        if (/\.(jpg|jpeg|png|gif|bmp|webp|svg)$/i.test(f)) return { type: 'image', icon: 'fa-image', cls: 'thumb-image' };
        if (/\.(mp4|webm|ogv|mov|avi|mkv|wmv|flv|m4v)$/i.test(f)) return { type: 'video', icon: 'fa-video', cls: 'thumb-video' };
        if (/\.(mp3|wav|ogg|m4a|aac|flac|wma|opus)$/i.test(f)) return { type: 'audio', icon: 'fa-music', cls: 'thumb-audio' };
        if (/\.pdf$/i.test(f)) return { type: 'pdf', icon: 'fa-file-pdf', cls: 'thumb-pdf' };
        if (/\.(txt|md|markdown|rtf|csv|json|xml|html|htm|log)$/i.test(f)) return { type: 'text', icon: 'fa-file-alt', cls: 'thumb-text' };
        return { type: 'file', icon: 'fa-file', cls: 'thumb-file' };
    },

    renderAttachments(list) {
        const c = document.getElementById('attachmentList');
        clearTimeout(this.attachmentOcrRefreshTimer);
        if (!list.length) { c.innerHTML = '<p class="text-muted" style="padding:10px">Keine Anhänge</p>'; return; }
        
        // Aktuelle Liste lokal speichern für Reordering
        this.currentAttachments = list;

        c.innerHTML = list.map((a, index) => {
            const mt = this.getMediaType(a.filename);
            const url = `/api/records/${this.editingId}/files/${encodeURIComponent(a.filename)}`;
            const ocrStatus = this.renderAttachmentOcrStatus(a);
            const retryOcrBtn = a.ocr_status === 'error'
                ? `<button type="button" class="btn btn-sm btn-secondary" data-perm="can_write" onclick="App.retryAttachmentOcr('${this.escapeHtml(a.filename)}')" title="OCR neu starten">
                        <i class="fas fa-rotate-right"></i>
                   </button>`
                : '';
            
            let thumb = '';
            if (mt.type === 'image') {
                thumb = `<div class="attachment-thumb ${mt.cls}" 
                             onclick="App.openMediaViewer('${this.escapeHtml(a.filename)}')"
                             onmouseenter="App.showAttachmentPreview(event, '${this.escapeHtml(a.filename)}', 'image')"
                             onmouseleave="App.hideAttachmentPreview()">
                             <img src="${url}" 
                                  onload="this.style.opacity='1'"
                                  onerror="this.style.display='none'; this.nextElementSibling.style.display='flex'"
                                  style="opacity:0; transition: opacity 0.3s">
                             <div class="thumb-icon" style="display:none"><i class="fas ${mt.icon}"></i></div>
                           </div>`;
            } else if (mt.type === 'video') {
                // Video-Vorschau durch Laden des ersten Frames (#t=0.5)
                // Wir verstecken das Icon sofort, wenn das Video geladen wurde
                thumb = `<div class="attachment-thumb ${mt.cls}"
                             onclick="App.openMediaViewer('${this.escapeHtml(a.filename)}')"
                             onmouseenter="App.showAttachmentPreview(event, '${this.escapeHtml(a.filename)}', 'video')"
                             onmouseleave="App.hideAttachmentPreview()">
                             <video src="${url}#t=0.5" preload="metadata" muted playsinline
                                    disablePictureInPicture controlsList="nopictureinpicture" disableremoteplayback
                                    onloadeddata="this.closest('.attachment-thumb').classList.add('video-loaded'); this.style.opacity='1'"
                                    onerror="this.style.display='none'; this.nextElementSibling.style.display='flex'"
                                    style="opacity:0; transition: opacity 0.3s">
                             </video>
                             <div class="thumb-icon"><i class="fas ${mt.icon}"></i></div>
                           </div>`;
            } else if (mt.type === 'audio') {
                // Audio-Symbol mit Klick-Handler für großen Player
                thumb = `<div class="attachment-thumb ${mt.cls} audio-thumb-container" onclick="App.openMediaViewer('${this.escapeHtml(a.filename)}')">
                             <div class="audio-thumb-player">
                                 <i class="fas ${mt.icon} audio-thumb-icon"></i>
                             </div>
                           </div>`;
            } else if (mt.type === 'pdf') {
                thumb = `<div class="attachment-thumb ${mt.cls} pdf-thumb-container" 
                             data-pdf-url="${url}" 
                             onclick="App.openMediaViewer('${this.escapeHtml(a.filename)}')"
                             onmouseenter="App.showAttachmentPreview(event, '${this.escapeHtml(a.filename)}', 'pdf')"
                             onmouseleave="App.hideAttachmentPreview()">
                             <img class="pdf-thumb-img" style="display:none; opacity:0; transition: opacity 0.3s">
                             <div class="thumb-icon"><i class="fas ${mt.icon}"></i></div>
                           </div>`;
            } else if (mt.type === 'text') {
                thumb = `<div class="attachment-thumb ${mt.cls} text-thumb-container" 
                             data-text-url="${url}" 
                             onclick="App.openMediaViewer('${this.escapeHtml(a.filename)}')"
                             onmouseenter="App.showAttachmentPreview(event, '${this.escapeHtml(a.filename)}', 'text')"
                             onmouseleave="App.hideAttachmentPreview()">
                             <div class="text-thumb-preview" style="display:none; opacity:0; transition: opacity 0.3s; overflow:hidden; width:100%; height:100%; background:white; font-family:monospace; font-size:6px; padding:4px; line-height:1.2; color:#333; word-break:break-all;"></div>
                             <div class="thumb-icon"><i class="fas ${mt.icon}"></i></div>
                           </div>`;
            } else {
                thumb = `<div class="attachment-thumb ${mt.cls}" onclick="App.openMediaViewer('${this.escapeHtml(a.filename)}')">
                             <div class="thumb-icon"><i class="fas ${mt.icon}"></i></div>
                           </div>`;
            }

            const upBtn = index > 0 ? `<button type="button" class="btn btn-sm btn-secondary order-btn" onclick="App.moveAttachment(${index}, -1)" title="Nach oben">
                    <i class="fas fa-arrow-up"></i>
                </button>` : '';
            
            const downBtn = index < list.length - 1 ? `<button type="button" class="btn btn-sm btn-secondary order-btn" onclick="App.moveAttachment(${index}, 1)" title="Nach unten">
                    <i class="fas fa-arrow-down"></i>
                </button>` : '';

            return `
            <div class="attachment-item" data-filename="${this.escapeHtml(a.filename)}">
                ${thumb}
                <div style="display:flex; flex-direction:column; gap:4px; min-width:0; flex:1;">
                    <span class="file-name">${this.escapeHtml(a.filename)}</span>
                    <div class="ocr-status-container">${ocrStatus}</div>
                </div>
                <div class="attachment-actions">
                    <div class="order-controls">
                        ${upBtn}
                        ${downBtn}
                    </div>
                    ${retryOcrBtn}
                    <button type="button" class="btn btn-sm btn-secondary" data-perm="can_write" onclick="App.renameAttachment('${this.escapeHtml(a.filename)}')" title="Umbenennen">
                        <i class="fas fa-edit"></i>
                    </button>
                    <button type="button" class="btn btn-sm btn-secondary" data-perm="can_download" onclick="App.downloadFile('${this.escapeHtml(a.filename)}', ${a.size})">
                        <i class="fas fa-download"></i>
                    </button>
                    <button type="button" class="btn btn-sm btn-danger" data-perm="can_delete" onclick="App.deleteAttachment('${this.escapeHtml(a.filename)}')">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
            </div>`;
        }).join('');
        // Re-apply permission visibility
        document.querySelectorAll('[data-perm]').forEach(el => {
            const perm = el.dataset.perm;
            const has = this.currentUser?.role === 'admin' || this.currentUser?.[perm];
            el.classList.toggle('hidden', !has);
        });

        // PDF-Vorschauen generieren
        this.processPdfThumbnails();
        // Text-Vorschauen generieren
        this.processTextThumbnails();

        if (list.some(a => ['pending', 'running'].includes(a.ocr_status)) && this.editingId) {
            this.attachmentOcrRefreshTimer = setTimeout(() => {
                this.refreshCurrentAttachments(false);
            }, 4000);
        }
    },

    renderAttachmentOcrStatus(attachment) {
        const status = attachment.ocr_status || '';
        if (!status) return '';

        const progress = Math.max(0, Math.min(100, Math.round((attachment.ocr_progress || 0) * 100)));
        const pagesDone = attachment.ocr_pages_done || 0;
        const pagesTotal = attachment.ocr_pages_total || 0;
        const hasText = attachment.ocr_has_text === 1;

        if (status === 'done') {
            if (!hasText) {
                return `<span style="font-size:12px;color:#95a5a6;" title="Kein Text erkannt">OCR leer</span>`;
            }
            return `<span style="font-size:12px;color:#2ecc71;">OCR bereit</span>`;
        }
        if (status === 'pending') {
            return `<span style="font-size:12px;color:#f1c40f;">OCR wartet</span>`;
        }
        if (status === 'running') {
            const detail = pagesTotal ? ` (${pagesDone}/${pagesTotal})` : '';
            return `<span style="font-size:12px;color:#4aa3ff;">OCR läuft ${progress}%${detail}</span>`;
        }
        if (status === 'error') {
            const msg = this.escapeHtml(attachment.ocr_error_message || 'OCR-Fehler');
            return `<span style="font-size:12px;color:#ff7675;" title="${msg}">OCR-Fehler</span>`;
        }
        if (status === 'disabled') {
            return `<span style="font-size:12px;color:#95a5a6;">OCR deaktiviert</span>`;
        }
        return '';
    },

    async refreshCurrentAttachments(showLoadingOverlay = false) {
        if (!this.editingId) return;
        try {
            const data = await this.apiGet(`/records/${this.editingId}`, showLoadingOverlay);
            const newAttachments = data.attachments || [];
            this.currentAttachments = newAttachments;

            // Only update OCR status for existing attachments, don't re-render everything
            for (const a of newAttachments) {
                const item = document.querySelector(`.attachment-item[data-filename="${this.escapeHtml(a.filename)}"]`);
                if (item) {
                    const ocrContainer = item.querySelector('.ocr-status-container');
                    if (ocrContainer) {
                        ocrContainer.innerHTML = this.renderAttachmentOcrStatus(a);
                    }
                    // Update retry button if needed
                    const actions = item.querySelector('.attachment-actions');
                    if (actions) {
                        let retryBtn = actions.querySelector('[onclick*="retryAttachmentOcr"]');
                        if (a.ocr_status === 'error' && !retryBtn) {
                            // Add retry button
                            const newBtn = document.createElement('button');
                            newBtn.type = 'button';
                            newBtn.className = 'btn btn-sm btn-secondary';
                            newBtn.setAttribute('data-perm', 'can_write');
                            newBtn.setAttribute('title', 'OCR neu starten');
                            newBtn.setAttribute('onclick', `App.retryAttachmentOcr('${this.escapeHtml(a.filename)}')`);
                            newBtn.innerHTML = '<i class="fas fa-rotate-right"></i>';
                            actions.insertBefore(newBtn, actions.firstChild.nextSibling);
                        } else if (a.ocr_status !== 'error' && retryBtn) {
                            // Remove retry button
                            retryBtn.remove();
                        }
                    }
                }
            }

            // Re-schedule refresh if any OCR is pending/running
            clearTimeout(this.attachmentOcrRefreshTimer);
            if (newAttachments.some(a => ['pending', 'running'].includes(a.ocr_status))) {
                this.attachmentOcrRefreshTimer = setTimeout(() => {
                    this.refreshCurrentAttachments(false);
                }, 4000);
            }
        } catch (e) {
            console.error('OCR-Refresh fehlgeschlagen:', e);
        }
    },

    async processTextThumbnails() {
        const containers = document.querySelectorAll('.text-thumb-container');
        for (const container of containers) {
            const url = container.dataset.textUrl;
            const preview = container.querySelector('.text-thumb-preview');
            const icon = container.querySelector('.thumb-icon');

            if (!url || !preview || preview.textContent) continue;

            try {
                const response = await fetch(url);
                const text = await response.text();
                preview.textContent = text.substring(0, 500);
                preview.style.display = 'block';
                setTimeout(() => preview.style.opacity = '1', 50);
                if (icon) icon.style.display = 'none';
                container.classList.add('text-loaded');
            } catch (e) {
                console.error('Fehler beim Erstellen der Text-Vorschau:', e);
            }
        }
    },

    async retryAttachmentOcr(filename) {
        if (!this.editingId) return;
        try {
            await this.apiPost(`/records/${this.editingId}/files/${encodeURIComponent(filename)}/ocr/retry`, {}, false);
            this.toast('OCR wurde neu gestartet', 'success');
            await this.refreshCurrentAttachments(false);
        } catch (e) {
            this.toast(e.message, 'error');
        }
    },

    async processPdfThumbnails() {
        if (!window.pdfjsLib) return;

        const containers = document.querySelectorAll('.pdf-thumb-container');
        for (const container of containers) {
            const url = container.dataset.pdfUrl;
            const img = container.querySelector('.pdf-thumb-img');
            const icon = container.querySelector('.thumb-icon');

            if (!url || !img || img.src) continue;

            try {
                const loadingTask = window.pdfjsLib.getDocument(url);
                const pdf = await loadingTask.promise;
                const page = await pdf.getPage(1);
                
                const viewport = page.getViewport({ scale: 0.5 });
                const canvas = document.createElement('canvas');
                const context = canvas.getContext('2d');
                canvas.height = viewport.height;
                canvas.width = viewport.width;

                await page.render({ canvasContext: context, viewport: viewport }).promise;
                
                img.src = canvas.toDataURL();
                img.style.display = 'block';
                setTimeout(() => img.style.opacity = '1', 50);
                if (icon) icon.style.display = 'none';
                container.classList.add('pdf-loaded');
            } catch (e) {
                console.error('Fehler beim Erstellen der PDF-Vorschau:', e);
            }
        }
    },

    async moveAttachment(index, direction) {
        if (!this.currentAttachments || !this.editingId) return;
        
        const newIndex = index + direction;
        if (newIndex < 0 || newIndex >= this.currentAttachments.length) return;
        
        // Swap items
        const temp = this.currentAttachments[index];
        this.currentAttachments[index] = this.currentAttachments[newIndex];
        this.currentAttachments[newIndex] = temp;
        
        // UI sofort aktualisieren
        this.renderAttachments(this.currentAttachments);
        
        // In Datenbank speichern
        try {
            const filenames = this.currentAttachments.map(a => a.filename);
            await this.apiPost(`/records/${this.editingId}/reorder-attachments`, { filenames });
        } catch (e) {
            console.error('Fehler beim Speichern der Reihenfolge:', e);
            this.showToast('Reihenfolge konnte nicht gespeichert werden', 'error');
        }
    },

    async renameAttachment(oldFilename) {
        if (!this.editingId) return;
        
        // Dateiendung ermitteln
        const extMatch = oldFilename.match(/\.[^.]+$/);
        const extension = extMatch ? extMatch[0] : '';
        const nameWithoutExt = oldFilename.replace(extension, '');
        
        const newNameBase = prompt('Neuer Dateiname:', nameWithoutExt);
        if (!newNameBase || newNameBase === nameWithoutExt) return;
        
        const newFilename = newNameBase + extension;
        
        try {
            await this.apiPost(`/records/${this.editingId}/files/${encodeURIComponent(oldFilename)}/rename`, {
                new_filename: newFilename
            });
            this.toast('Datei umbenannt', 'success');
            
            // Lokale Liste aktualisieren
            if (this.currentAttachments) {
                const att = this.currentAttachments.find(a => a.filename === oldFilename);
                if (att) att.filename = newFilename;
                this.renderAttachments(this.currentAttachments);
            } else {
                // Notfalls Akte neu laden
                const record = await this.apiGet(`/records/${this.editingId}`);
                if (record) this.renderAttachments(record.attachments || []);
            }
        } catch (e) {
            this.toast(e.message, 'error');
        }
    },

    showAttachmentPreview(ev, filename, type) {
        if (!window.matchMedia("(hover: hover)").matches) return;

        const preview = document.getElementById('attachmentHoverPreview');
        if (!preview || !this.editingId) return;

        const url = `/api/records/${this.editingId}/files/${encodeURIComponent(filename)}`;
        preview.innerHTML = '';
        // Set fixed size for all previews
        preview.style.width = '320px';
        preview.style.height = '240px';
        preview.style.overflow = 'hidden';

        if (type === 'image') {
            const img = document.createElement('img');
            img.src = url;
            img.style.cssText = 'width:100%; height:100%; object-fit:cover;';
            preview.appendChild(img);
        } else if (type === 'video') {
            const video = document.createElement('video');
            video.src = url + "#t=0.5";
            video.muted = true;
            video.style.cssText = 'width:100%; height:100%; object-fit:cover;';
            preview.appendChild(video);
        } else if (type === 'pdf') {
            const thumb = ev.currentTarget.querySelector('.pdf-thumb-img');
            if (thumb && thumb.src) {
                const img = document.createElement('img');
                img.src = thumb.src;
                img.style.cssText = 'width:100%; height:100%; object-fit:cover;';
                preview.appendChild(img);
            } else {
                return;
            }
        } else if (type === 'text') {
            const textContainer = document.createElement('div');
            textContainer.style.cssText = 'padding:16px; width:100%; height:100%; overflow:hidden; background:white; font-family:monospace; font-size:12px; line-height:1.4; color:#333; word-break:break-all; box-shadow:0 4px 20px rgba(0,0,0,0.15);';
            preview.appendChild(textContainer);
            // Fetch and show text preview
            fetch(url)
                .then(response => response.text())
                .then(text => {
                    textContainer.textContent = text.substring(0, 1500);
                })
                .catch(err => {
                    textContainer.textContent = 'Vorschau nicht verfügbar';
                });
        } else {
            return;
        }

        const updatePos = (e) => {
            const modal = document.getElementById('recordModal');
            const modalRect = modal ? modal.getBoundingClientRect() : { left: 0, top: 0, right: window.innerWidth, bottom: window.innerHeight };
            
            const x = e.clientX + 20;
            const y = e.clientY + 20;
            const width = 320;
            const height = 240;
            
            let posX = x;
            let posY = y;
            
            // Erst am Bildschirmrand prüfen
            if (posX + width > window.innerWidth) posX = e.clientX - width - 20;
            if (posY + height > window.innerHeight) posY = e.clientY - height - 20;
            
            // Dann am Modal-Rand (Aktenfeld) einschränken
            if (modal) {
                posX = Math.max(modalRect.left, Math.min(posX, modalRect.right - width));
                posY = Math.max(modalRect.top, Math.min(posY, modalRect.bottom - height));
            }
            
            preview.style.left = posX + 'px';
            preview.style.top = posY + 'px';
        };

        updatePos(ev);
        preview.classList.add('show');
        ev.currentTarget.onmousemove = updatePos;
    },

    hideAttachmentPreview() {
        const preview = document.getElementById('attachmentHoverPreview');
        if (preview) {
            preview.classList.remove('show');
            preview.innerHTML = '';
        }
    },

    // Integrierter Media Player
    showMediaPlayer(filename) {
        const mt = this.getMediaType(filename);
        const url = `/api/records/${this.editingId}/files/${encodeURIComponent(filename)}`;
        const section = document.getElementById('mediaPlayerSection');
        const content = document.getElementById('mediaPlayerContent');
        document.getElementById('mediaPlayerTitle').textContent = filename;
        section.classList.add('show');

        if (mt.type === 'video') {
            const mimeType = filename.endsWith('.webm') ? 'video/webm' : (filename.endsWith('.ogg') ? 'video/ogg' : 'video/mp4');
            content.innerHTML = `<video controls disablePictureInPicture controlsList="nodownload nopictureinpicture noremoteplayback" style="max-width:100%;max-height:300px"><source src="${url}" type="${mimeType}">Browser unterstuetzt kein Video.</video>`;
        } else if (mt.type === 'audio') {
            const mimeType = filename.endsWith('.wav') ? 'audio/wav' : (filename.endsWith('.ogg') ? 'audio/ogg' : 'audio/mpeg');
            content.innerHTML = `<audio controls style="width:100%"><source src="${url}" type="${mimeType}">Browser unterstuetzt kein Audio.</audio>`;
        } else if (mt.type === 'image') {
            content.innerHTML = `<img src="${url}?t=${Date.now()}" class="media-preview-img" alt="${this.escapeHtml(filename)}">`;
        } else if (mt.type === 'pdf') {
            content.innerHTML = `<button class="btn btn-primary" onclick="window.open('viewer.html?url=${encodeURIComponent(url)}&name=${encodeURIComponent(filename)}&type=pdf', '_blank', 'width=800,height=600')"><i class="fas fa-file-pdf"></i> PDF öffnen</button>`;
        } else if (mt.type === 'text') {
            content.innerHTML = `<button class="btn btn-primary" onclick="window.open('viewer.html?url=${encodeURIComponent(url)}&name=${encodeURIComponent(filename)}&type=text', '_blank', 'width=800,height=600')"><i class="fas fa-file-alt"></i> Textdatei öffnen</button>`;
        } else {
            section.classList.remove('show');
        }
    },

    // Anhänge in neuem Tab öffnen (mit Viewer-Schutz)
    openMediaViewer(filename, options = {}) {
        const recordId = options.recordId || this.editingId;
        if (!recordId) return;
        const mt = this.getMediaType(filename);
        const fileUrl = `/api/records/${recordId}/files/${encodeURIComponent(filename)}`;
        const viewerParams = new URLSearchParams({
            url: fileUrl,
            name: filename,
            type: mt.type
        });
        if (options.page) {
            viewerParams.set('page', String(options.page));
        }
        if (options.highlight) {
            viewerParams.set('highlight', options.highlight);
        }
        // Store search matches in sessionStorage instead of URL (to avoid URL length limit)
        if (options.searchMatches && options.searchMatches.length > 0) {
            const storageKey = `ocr_matches_${recordId}_${filename}`;
            sessionStorage.setItem(storageKey, JSON.stringify(options.searchMatches));
            viewerParams.set('storageKey', storageKey);
        }
        const viewerUrl = `/viewer?${viewerParams.toString()}`;
        window.open(viewerUrl, '_blank');
    },

    async openSearchMatch(recordId, filename, page = null, snippet = '') {
        if (!recordId) return;

        // Don't open the record, just get the search matches from already loaded records
        let searchMatches = [];
        const record = this.records.find(r => r.id === recordId);
        if (record && record.search_matches) {
            searchMatches = record.search_matches;
        }

        if (!filename) return;

        const mediaType = this.getMediaType(filename).type;
        if (mediaType === 'file') {
            return;
        }

        this.openMediaViewer(filename, {
            recordId,
            page: page || null,
            highlight: snippet || '',
            searchMatches: searchMatches
        });
    },

    async openSearchMatchFromElement(element) {
        const button = element?.closest?.('.record-search-match');
        if (!button) return;

        const recordId = Number(button.dataset.recordId);
        const filename = button.dataset.filename || '';
        const pageValue = button.dataset.page;
        const page = pageValue ? Number(pageValue) : null;
        const snippet = button.dataset.snippet || '';

        if (!Number.isFinite(recordId)) return;
        await this.openSearchMatch(recordId, filename, page, snippet);
    },

    closeMediaViewer(ev) {
        // Veraltet - Anhänge werden nun in neuem Tab geöffnet
        return;
    },

    closeMediaViewerButton(ev) {
        // Veraltet - Anhänge werden nun in neuem Tab geöffnet
        return;
    },

    async handleFileUpload(ev) {
        // Prüfen ob es eine offline-Akte ist
        const record = this.records.find(r => r.id === this.editingId);
        const isOfflineRecord = record && record.is_offline;
        
        if (isOfflineRecord) {
            this.toast('Bitte synchronisieren Sie die Akte zuerst, bevor Sie Dateien hochladen', 'warning');
            ev.target.value = '';
            return;
        }
        
        if (!this.editingId) { 
            this.toast('Bitte erstellen oder öffnen Sie zuerst eine Akte', 'warning'); 
            ev.target.value = '';
            return; 
        }
        
        const files = ev.target.files;
        if (!files.length) return;
        
        // Prüfen ob Server erreichbar ist (außer bei manuellem Offline-Modus)
        let isOnline = false;
        if (!this.manualOfflineMode) {
            try {
                const response = await fetch('/api/health', {
                    method: 'GET',
                    cache: 'no-cache',
                    signal: AbortSignal.timeout(3000)
                });
                isOnline = response.ok;
                console.log(`📡 Upload-Verbindungscheck: ${isOnline ? 'Online' : 'Offline'}`);
            } catch (e) {
                console.log('❌ Upload-Verbindungscheck fehlgeschlagen:', e.message);
                isOnline = false;
            }
        }
        
        if (!isOnline) {
            this.toast('Datei-Upload nur bei Server-Verbindung möglich', 'warning');
            ev.target.value = '';
            return;
        }
        
        // Online: Normaler Upload
        for (const file of files) {
            const fd = new FormData();
            fd.append('file', file);
            this.uploadQueue.push({
                endpoint: `/records/${this.editingId}/files`,
                formData: fd,
                filename: file.name,
                recordId: this.editingId
            });
        }
        
        this.processUploadQueue();
        ev.target.value = '';
    },

    handleClipboardImport() {
        if (!this.editingId) {
            this.toast('Bitte erstellen oder öffnen Sie zuerst eine Akte', 'warning');
            return;
        }

        // Textfeld anzeigen
        const clipboardInputArea = document.getElementById('clipboardInputArea');
        const clipboardTextInput = document.getElementById('clipboardTextInput');
        const clipboardImagePreview = document.getElementById('clipboardImagePreview');
        const clipboardPreviewImg = document.getElementById('clipboardPreviewImg');
        
        if (clipboardInputArea && clipboardTextInput) {
            clipboardInputArea.classList.remove('hidden');
            clipboardTextInput.value = '';
            clipboardTextInput.focus();
            // Reset image preview
            if (clipboardImagePreview) clipboardImagePreview.classList.add('hidden');
            if (clipboardPreviewImg) clipboardPreviewImg.src = '';
            this.clipboardImageData = null; // Store image data
        }
    },

    handleClipboardPaste(e) {
        e.preventDefault();

        const clipboardTextInput = document.getElementById('clipboardTextInput');
        const clipboardImagePreview = document.getElementById('clipboardImagePreview');
        const clipboardPreviewImg = document.getElementById('clipboardPreviewImg');

        // Zuerst prüfen ob Text in der Zwischenablage (Vorrang vor Bildern)
        const text = e.clipboardData.getData('text/plain');
        if (text && text.trim().length > 0) {
            // Text gefunden - als Text behandeln
            if (clipboardTextInput) {
                clipboardTextInput.value = text;
                clipboardTextInput.readOnly = false;
            }
            if (clipboardImagePreview) clipboardImagePreview.classList.add('hidden');
            this.clipboardImageData = null;
            return;
        }

        // Wenn kein Text, dann nach Bild suchen
        const items = e.clipboardData.items;
        let hasImage = false;

        for (let i = 0; i < items.length; i++) {
            if (items[i].type.indexOf('image') !== -1) {
                hasImage = true;
                const blob = items[i].getAsFile();
                const reader = new FileReader();
                reader.onload = (event) => {
                    this.clipboardImageData = event.target.result;
                    if (clipboardPreviewImg) {
                        clipboardPreviewImg.src = event.target.result;
                        clipboardImagePreview.classList.remove('hidden');
                    }
                    if (clipboardTextInput) {
                        clipboardTextInput.value = '[Bild aus Zwischenablage]';
                        clipboardTextInput.readOnly = true;
                    }
                };
                reader.readAsDataURL(blob);
                break;
            }
        }

        // Wenn weder Text noch Bild
        if (!hasImage) {
            if (clipboardTextInput) {
                clipboardTextInput.value = '';
                clipboardTextInput.readOnly = false;
            }
            if (clipboardImagePreview) clipboardImagePreview.classList.add('hidden');
            this.clipboardImageData = null;
        }
    },

    cancelClipboardImport() {
        const clipboardInputArea = document.getElementById('clipboardInputArea');
        if (clipboardInputArea) {
            clipboardInputArea.classList.add('hidden');
        }
        this.clipboardImageData = null;
    },

    async submitClipboardContent(event) {
        if (event) event.preventDefault();
        
        const clipboardTextInput = document.getElementById('clipboardTextInput');
        if (!clipboardTextInput) return;

        let content = clipboardTextInput.value.trim();
        let type = 'text';
        
        // Prüfen ob Bild-Daten vorhanden
        if (this.clipboardImageData) {
            content = this.clipboardImageData;
            type = 'image';
        } else if (!content) {
            this.toast('Bitte geben Sie Text ein oder fügen Sie ihn ein', 'warning');
            return;
        }

        // Prüfen ob Server erreichbar ist
        let isOnline = false;
        if (!this.manualOfflineMode) {
            try {
                const response = await fetch('/api/health', {
                    method: 'GET',
                    cache: 'no-cache',
                    signal: AbortSignal.timeout(3000)
                });
                isOnline = response.ok;
            } catch (e) {
                isOnline = false;
            }
        }

        if (!isOnline) {
            this.toast('Clipboard-Import nur bei Server-Verbindung möglich', 'warning');
            return;
        }

        await this.uploadClipboardContent(type, content);
        
        // Import-Feld schließen, Akte bleibt offen
        this.cancelClipboardImport();
    },

    async uploadClipboardContent(type, content) {
        try {
            const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
            const filename = type === 'image' ? `clipboard_${timestamp}.jpg` : `clipboard_${timestamp}.md`;

            const response = await fetch(`/api/records/${this.editingId}/clipboard`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    type: type,
                    content: content,
                    filename: filename
                })
            });

            const result = await response.json();

            if (response.ok && result.success) {
                this.toast(`${type === 'image' ? 'Bild' : 'Text'} aus Zwischenablage importiert`, 'success');
                // Anhänge aktualisieren, wenn Akte noch offen ist
                if (this.editingId && !document.getElementById('recordModal').classList.contains('hidden')) {
                    try {
                        const data = await this.apiGet(`/records/${this.editingId}`);
                        this.renderAttachments(data.attachments || []);
                    } catch (e) {
                        console.error('Anhänge-Aktualisierung fehlgeschlagen:', e);
                    }
                }
            } else {
                this.toast(result.error || 'Import fehlgeschlagen', 'error');
            }
        } catch (err) {
            console.error('Clipboard-Upload Fehler:', err);
            this.toast('Import fehlgeschlagen: ' + err.message, 'error');
        }
    },

    // Datei-Upload-Feld je nach Verbindungsstatus anzeigen/ausblenden
    updateFileUploadAvailability() {
        const fileDropZone = document.getElementById('fileDropZone');
        const clipboardDropZone = document.getElementById('clipboardDropZone');
        const offlineUploadWarning = document.getElementById('offlineUploadWarning');

        if (!fileDropZone) return;

        // Manueller Offline-Modus hat Priorität
        if (this.manualOfflineMode) {
            console.log('🔒 Manueller Offline-Modus aktiv - Datei-Upload deaktiviert');
            fileDropZone.style.display = 'none';
            if (clipboardDropZone) clipboardDropZone.style.display = 'none';
            if (offlineUploadWarning) offlineUploadWarning.style.display = 'block';
            return;
        }

        // Prüfen ob Server erreichbar ist
        fetch('/api/health', {
            method: 'GET',
            cache: 'no-cache',
            signal: AbortSignal.timeout(3000)
        }).then(response => {
            const isOnline = response.ok;

            if (isOnline) {
                // Online: Datei-Upload-Feld zeigen, Warnung ausblenden
                fileDropZone.style.display = 'block';
                if (clipboardDropZone) clipboardDropZone.style.display = 'block';
                if (offlineUploadWarning) offlineUploadWarning.style.display = 'none';
                console.log('✅ Datei-Upload-Feld aktiv (Online)');
            } else {
                // Offline: Datei-Upload-Feld ausblenden, Warnung zeigen
                fileDropZone.style.display = 'none';
                if (clipboardDropZone) clipboardDropZone.style.display = 'none';
                if (offlineUploadWarning) offlineUploadWarning.style.display = 'block';
                console.log('⚠️ Datei-Upload-Feld deaktiviert (Offline)');
            }
        }).catch(e => {
            // Bei Fehler auch offline behandeln
            fileDropZone.style.display = 'none';
            if (clipboardDropZone) clipboardDropZone.style.display = 'none';
            if (offlineUploadWarning) offlineUploadWarning.style.display = 'block';
            console.log('⚠️ Datei-Upload-Feld deaktiviert (Fehler):', e.message);
        });
    },

    // Prüft ob Server erreichbar ist und gibt Status zurück
    async checkServerConnection() {
        // Manueller Offline-Modus hat Priorität
        if (this.manualOfflineMode) {
            console.log('🔒 Manueller Offline-Modus aktiv - Verbindungsprüfung übersprungen');
            return false;
        }
        try {
            const response = await fetch('/api/health', {
                method: 'GET',
                cache: 'no-cache',
                signal: AbortSignal.timeout(3000)
            });
            
            // Wenn Verbindung erfolgreich und ausstehender Logout vorhanden, diesen verarbeiten
            if (response.ok) {
                await this.processPendingLogout();
            }
            
            return response.ok;
        } catch (e) {
            console.log('❌ Server-Verbindungscheck fehlgeschlagen:', e.message);
            return false;
        }
    },

    async processPendingLogout() {
        // Verarbeitet ausstehende Logout-Anforderungen vom Offline-Modus
        // Nur für den aktuellen Benutzer, nicht für andere Benutzer!
        const pendingUserId = this.safeLocalStorage.getItem('pending_logout_user_id');
        if (!pendingUserId) {
            return;
        }

        // Nur verarbeiten, wenn wir wissen, welcher Benutzer sich einloggt
        // Das verhindert, dass Benutzer A den Logout von Benutzer B verarbeitet
        const username = document.getElementById('loginUser')?.value?.trim();
        if (!username) {
            return;
        }

        // Prüfen, ob der pending_logout_user_id zum aktuellen Benutzernamen gehört
        // Wir speichern auch den Benutzernamen im localStorage für diese Prüfung
        const pendingUsername = this.safeLocalStorage.getItem('pending_logout_username');
        
        if (pendingUsername && pendingUsername !== username) {
            // Der ausstehende Logout gehört einem anderen Benutzer - überspringen
            console.log('⏭️ Ausstehender Logout gehört nicht zum aktuellen Benutzer (' + pendingUsername + ' vs ' + username + '), wird übersprungen');
            this.safeLocalStorage.removeItem('pending_logout_user_id');
            this.safeLocalStorage.removeItem('pending_logout_username');
            return;
        }

        try {
            console.log('🔄 Verarbeite ausstehenden Logout für User-ID:', pendingUserId, 'Username:', username);
            await this.apiPost(`/auth/admin/reset-login-status/${pendingUserId}`);
            this.safeLocalStorage.removeItem('pending_logout_user_id');
            this.safeLocalStorage.removeItem('pending_logout_username');
            console.log('✅ Ausstehender Logout erfolgreich verarbeitet');
        } catch (e) {
            console.error('❌ Fehler beim Verarbeiten des ausstehenden Logout:', e);
            // Bei Fehler nicht entfernen, damit beim nächsten Versuch erneut probiert wird
        }
    },

    downloadFile(filename, size = 0) {
        if (!this.editingId) return;
        
        const url = `/api/records/${this.editingId}/files/${encodeURIComponent(filename)}?download=1`;
        
        // Bei sehr grossen Dateien (> 500MB) den nativen Browser-Download nutzen,
        // um den Arbeitsspeicher zu schonen (kein Blob-Umweg).
        if (size > 500 * 1024 * 1024) {
            const a = document.createElement('a');
            a.href = url;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            a.remove();
            this.toast('Großer Download gestartet (nativ)', 'info');
            return;
        }

        const panel = document.getElementById('downloadProgressPanel');
        const bar = document.getElementById('downloadProgressBar');
        const fileLabel = document.getElementById('downloadProgressFile');
        
        panel.classList.remove('hidden');
        bar.style.width = '0%';
        fileLabel.textContent = filename;

        const xhr = new XMLHttpRequest();
        xhr.open('GET', url, true);
        xhr.responseType = 'blob';

        xhr.onprogress = (event) => {
            if (event.lengthComputable) {
                const percent = (event.loaded / event.total) * 100;
                bar.style.width = percent + '%';
            }
        };

        xhr.onload = () => {
            if (xhr.status === 200) {
                const blob = xhr.response;
                const downloadUrl = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = downloadUrl;
                a.download = filename;
                document.body.appendChild(a);
                a.click();
                window.URL.revokeObjectURL(downloadUrl);
                a.remove();
                
                setTimeout(() => {
                    panel.classList.add('hidden');
                }, 1000);
            } else {
                this.toast('Download fehlgeschlagen', 'error');
                panel.classList.add('hidden');
            }
        };

        xhr.onerror = () => {
            this.toast('Netzwerkfehler beim Download', 'error');
            panel.classList.add('hidden');
        };

        xhr.send();
    },

    async deleteAttachment(filename) {
        if (!await this.confirm('Datei löschen?', filename, 'Ja, löschen', 'btn-danger')) return;
        try {
            await this.apiDelete(`/records/${this.editingId}/files/${encodeURIComponent(filename)}`);
            this.toast('Datei geloescht', 'success');
            const data = await this.apiGet(`/records/${this.editingId}`);
            this.renderAttachments(data.attachments || []);
        } catch (e) {
            this.toast(e.message, 'error');
        }
    },

    // ── IP-Whitelist ───────────────────────────────────
    async loadIpWhitelist() {
        try {
            const data = await this.apiGet('/settings/ip-whitelist');
            const tbody = document.getElementById('ipWhitelistBody');
            tbody.innerHTML = '';
            data.ips.forEach(ip => {
                tbody.innerHTML += `
                    <tr>
                        <td>${this.escapeHtml(ip.ip_address)}</td>
                        <td>${this.escapeHtml(ip.description || '-')}</td>
                        <td>
                            <button class="btn btn-sm btn-danger" onclick="App.removeIpFromWhitelist('${this.escapeHtml(ip.ip_address)}')">
                                <i class="fas fa-trash"></i>
                            </button>
                        </td>
                    </tr>
                `;
            });
        } catch (e) {
            console.error('Fehler beim Laden der IP-Whitelist:', e);
        }
    },

    async addIpToWhitelist() {
        const ipInput = document.getElementById('newIpAddress');
        const descInput = document.getElementById('newIpDescription');
        const ip = ipInput.value.trim();
        const description = descInput.value.trim();

        if (!ip) {
            this.toast('IP-Adresse erforderlich', 'error');
            return;
        }

        try {
            await this.apiPost('/settings/ip-whitelist', { ip_address: ip, description });
            this.toast('IP-Adresse hinzugefügt', 'success');
            ipInput.value = '';
            descInput.value = '';
            this.loadIpWhitelist();
        } catch (e) {
            this.toast(e.message, 'error');
        }
    },

    async removeIpFromWhitelist(ipAddress) {
        if (!await this.confirm('IP-Adresse entfernen?', ipAddress, 'Ja, entfernen', 'btn-danger')) return;
        try {
            await this.apiDelete(`/settings/ip-whitelist/${encodeURIComponent(ipAddress)}`);
            this.toast('IP-Adresse entfernt', 'success');
            this.loadIpWhitelist();
        } catch (e) {
            this.toast(e.message, 'error');
        }
    },

    // ── Referenzorte (Karte) ─────────────────────────────
    toggleCollapsible(sectionId) {
        const content = document.getElementById(sectionId);
        const icon = document.getElementById(sectionId + 'Icon');
        
        if (content.classList.contains('expanded')) {
            content.classList.remove('expanded');
            icon.classList.add('collapsed');
        } else {
            content.classList.add('expanded');
            icon.classList.remove('collapsed');
        }
    },

    async loadReferenzorte() {
        try {
            const data = await this.apiGet('/karte/referenzorte');
            this._referenzorte = data.orte || {};
            this._aktuellerFilter = 'all';
            this._currentPage = 1;
            this._itemsPerPage = 20;
            
            // Buchstaben-Filter generieren
            this._generiereBuchstabenFilter();
            
            // Orte anzeigen
            this._zeigeReferenzorte();
        } catch (e) {
            const tbody = document.getElementById('referenzorteBody');
            if (tbody) tbody.innerHTML = '<tr><td colspan="5" class="text-center text-danger">Fehler beim Laden</td></tr>';
        }
    },

    _generiereBuchstabenFilter() {
        const filterContainer = document.getElementById('buchstabenFilter');
        if (!filterContainer) return;

        const orte = this._referenzorte || {};
        const verfuegbareBuchstaben = new Set();
        
        // Verfügbare Anfangsbuchstaben sammeln
        Object.keys(orte).forEach(name => {
            const erster = name.charAt(0).toUpperCase();
            if (/[A-Z]/.test(erster)) {
                verfuegbareBuchstaben.add(erster);
            }
        });

        // Buttons generieren
        let html = '<button class="btn btn-sm btn-secondary filter-btn active" data-buchstabe="all" onclick="App.filterReferenzorte(\'all\')">Alle</button>';
        
        'ABCDEFGHIJKLMNOPQRSTUVWXYZ'.split('').forEach(buchstabe => {
            if (verfuegbareBuchstaben.has(buchstabe)) {
                html += `<button class="btn btn-sm btn-secondary filter-btn" data-buchstabe="${buchstabe}" onclick="App.filterReferenzorte('${buchstabe}')">${buchstabe}</button>`;
            }
        });
        
        filterContainer.innerHTML = html;
    },

    filterReferenzorte(buchstabe) {
        this._aktuellerFilter = buchstabe;
        this._currentPage = 1; // Reset to page 1 when filter changes
        
        // Button-Status aktualisieren
        document.querySelectorAll('.filter-btn').forEach(btn => {
            btn.classList.remove('active');
            if (btn.dataset.buchstabe === buchstabe) {
                btn.classList.add('active');
            }
        });
        
        this._zeigeReferenzorte();
    },

    prevOrtPage() {
        if (this._currentPage > 1) {
            this._currentPage--;
            this._zeigeReferenzorte();
        }
    },

    nextOrtPage() {
        const totalPages = this._getTotalPages();
        if (this._currentPage < totalPages) {
            this._currentPage++;
            this._zeigeReferenzorte();
        }
    },

    _getTotalPages() {
        const orte = this._referenzorte || {};
        const filter = this._aktuellerFilter || 'all';
        
        let sortedNames = Object.keys(orte).sort();
        
        if (filter !== 'all') {
            sortedNames = sortedNames.filter(name => name.charAt(0).toUpperCase() === filter);
        }
        
        return Math.ceil(sortedNames.length / this._itemsPerPage);
    },

    _zeigeReferenzorte() {
        const tbody = document.getElementById('referenzorteBody');
        if (!tbody) return;

        const orte = this._referenzorte || {};
        const filter = this._aktuellerFilter || 'all';
        
        let sortedNames = Object.keys(orte).sort();
        
        // Filter anwenden
        if (filter !== 'all') {
            sortedNames = sortedNames.filter(name => name.charAt(0).toUpperCase() === filter);
        }

        if (sortedNames.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" class="text-center">Keine Orte vorhanden</td></tr>';
            this._updatePagination(0);
            return;
        }

        // Pagination anwenden
        const startIndex = (this._currentPage - 1) * this._itemsPerPage;
        const endIndex = startIndex + this._itemsPerPage;
        const pageNames = sortedNames.slice(startIndex, endIndex);

        tbody.innerHTML = pageNames.map(name => {
            const ort = orte[name];
            return `
                <tr>
                    <td>${this.escapeHtml(name)}</td>
                    <td>${ort.lat?.toFixed(4) || '-'}</td>
                    <td>${ort.lon?.toFixed(4) || '-'}</td>
                    <td>${ort.level ?? '-'}</td>
                    <td>
                        <button class="btn btn-danger btn-sm" onclick="App.deleteReferenzort('${this.escapeHtml(name)}')">
                            <i class="fas fa-trash"></i>
                        </button>
                    </td>
                </tr>
            `;
        }).join('');

        this._updatePagination(sortedNames.length);
    },

    _updatePagination(totalItems) {
        const prevBtn = document.getElementById('prevPageBtn');
        const nextBtn = document.getElementById('nextPageBtn');
        const pageInfo = document.getElementById('pageInfo');
        
        if (!prevBtn || !nextBtn || !pageInfo) return;

        const totalPages = Math.ceil(totalItems / this._itemsPerPage);
        
        if (totalPages <= 1) {
            prevBtn.disabled = true;
            nextBtn.disabled = true;
            pageInfo.textContent = totalItems > 0 ? `Seite 1 von 1 (${totalItems} Einträge)` : 'Seite 1 von 1';
        } else {
            prevBtn.disabled = this._currentPage <= 1;
            nextBtn.disabled = this._currentPage >= totalPages;
            pageInfo.textContent = `Seite ${this._currentPage} von ${totalPages} (${totalItems} Einträge)`;
        }
    },

    async addReferenzort() {
        const nameInput = document.getElementById('newOrtName');
        const latInput = document.getElementById('newOrtLat');
        const lonInput = document.getElementById('newOrtLon');
        const levelInput = document.getElementById('newOrtLevel');

        const name = nameInput.value.trim();
        const lat = parseFloat(latInput.value);
        const lon = parseFloat(lonInput.value);
        const level = parseInt(levelInput.value);

        if (!name) {
            this.toast('Ortsname erforderlich', 'error');
            return;
        }
        if (isNaN(lat) || isNaN(lon)) {
            this.toast('Koordinaten erforderlich', 'error');
            return;
        }
        if (lat < -90 || lat > 90 || lon < -180 || lon > 180) {
            this.toast('Koordinaten außerhalb des gültigen Bereichs', 'error');
            return;
        }

        try {
            await this.apiPost('/karte/referenzorte', { name, lat, lon, level });
            this.toast('Ort hinzugefügt', 'success');
            nameInput.value = '';
            latInput.value = '';
            lonInput.value = '';
            await this.loadReferenzorte();
            // Filter zurücksetzen auf "Alle" nach Hinzufügen
            this.filterReferenzorte('all');
        } catch (e) {
            this.toast(e.message, 'error');
        }
    },

    async deleteReferenzort(name) {
        if (!await this.confirm('Ort löschen?', name, 'Ja, löschen', 'btn-danger')) return;
        try {
            await this.apiDelete(`/karte/referenzorte/${encodeURIComponent(name)}`);
            this.toast('Ort gelöscht', 'success');
            await this.loadReferenzorte();
            // Aktuellen Filter neu anwenden
            this._zeigeReferenzorte();
        } catch (e) {
            this.toast(e.message, 'error');
        }
    },

    async exportReferenzorte() {
        try {
            const data = await this.apiGet('/karte/referenzorte');
            const orte = data.orte || {};
            const jsonStr = JSON.stringify(orte, null, 2);
            const blob = new Blob([jsonStr], { type: 'application/json' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'referenzorte_export.json';
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
            this.toast('Export erfolgreich', 'success');
        } catch (e) {
            this.toast(e.message, 'error');
        }
    },

    async importReferenzorte() {
        const fileInput = document.getElementById('importOrteFile');
        const file = fileInput.files[0];
        if (!file) return;

        try {
            const text = await file.text();
            const orte = JSON.parse(text);

            if (!await this.confirm('Importieren?', 'Dies ersetzt alle vorhandenen Referenzorte. Fortfahren?', 'Ja, importieren', 'btn-danger')) {
                fileInput.value = '';
                return;
            }

            await this.apiPost('/karte/referenzorte/import', { orte });
            this.toast('Import erfolgreich', 'success');
            fileInput.value = '';
            await this.loadReferenzorte();
            this.filterReferenzorte('all');
        } catch (e) {
            this.toast('Fehler beim Import: ' + e.message, 'error');
            fileInput.value = '';
        }
    },

    // ── Editor ─────────────────────────────────────
    exec(cmd, val = null) {
        document.execCommand(cmd, false, val);
        document.getElementById('recordContent').focus();
    },
    changeFontSize(size) {
        const sel = window.getSelection();
        const contentEl = document.getElementById('recordContent');
        if (!sel || sel.rangeCount === 0) {
            contentEl.focus();
            return;
        }
        
        const range = sel.getRangeAt(0);
        if (range.collapsed) {
            // No selection, just set style for next typing
            document.execCommand('styleWithCSS', false, true);
            const span = document.createElement('span');
            span.style.fontSize = size;
            span.innerHTML = '&nbsp;';
            range.insertNode(span);
            sel.removeAllRanges();
            const newRange = document.createRange();
            newRange.setStartAfter(span);
            newRange.collapse(true);
            sel.addRange(newRange);
        } else {
            // Save selection
            const savedRange = range.cloneRange();
            
            // Create a temporary wrapper to process the selection
            const tempDiv = document.createElement('div');
            const extractedContent = range.extractContents();
            tempDiv.appendChild(extractedContent);
            
            // Process all nodes inside tempDiv
            this.processNodesForFontSize(tempDiv, size);
            
            // Insert back all children
            const fragment = document.createDocumentFragment();
            while (tempDiv.firstChild) {
                fragment.appendChild(tempDiv.firstChild);
            }
            range.insertNode(fragment);
            
            // Restore selection
            sel.removeAllRanges();
            sel.addRange(savedRange);
        }
        
        contentEl.focus();
        this.hasChanges = true;
    },
    processNodesForFontSize(container, size) {
        const walker = document.createTreeWalker(
            container,
            NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT,
            null,
            false
        );
        
        const nodesToProcess = [];
        let node;
        while ((node = walker.nextNode())) {
            nodesToProcess.push(node);
        }
        
        nodesToProcess.forEach(node => {
            if (node.nodeType === Node.TEXT_NODE) {
                // Wrap text node in span
                if (node.textContent.trim()) {
                    const span = document.createElement('span');
                    span.style.fontSize = size;
                    node.parentNode.insertBefore(span, node);
                    span.appendChild(node);
                }
            } else if (node.nodeType === Node.ELEMENT_NODE && node.tagName !== 'INPUT') {
                // Update existing span or other elements
                if (node.style) {
                    node.style.fontSize = size;
                }
            }
        });
        
        // Clean up empty spans and merge adjacent spans with same style
        this.cleanupNestedSpans(container);
    },
    cleanupNestedSpans(container) {
        const spans = container.querySelectorAll('span');
        spans.forEach(span => {
            // If span has only style fontSize and no other attributes/styles
            if (span.attributes.length === 1 && 
                span.style.length === 1 && 
                span.style.fontSize) {
                const parent = span.parentNode;
                // Merge with parent if same fontSize
                if (parent.tagName === 'SPAN' && 
                    parent.style.fontSize === span.style.fontSize) {
                    while (span.firstChild) {
                        parent.insertBefore(span.firstChild, span);
                    }
                    parent.removeChild(span);
                }
            }
        });
    },
    insertDate() { this.exec('insertText', new Date().toLocaleDateString('de-DE')); },
    insertCheckbox() {
        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.checked = false;
        this.exec('insertHTML', checkbox.outerHTML + ' ');
    },

    // Helper: Get nth weekday of a month (nth: 1-5, weekday: 0=Sun, 1=Mon, ..., 6=Sat)
    getNthWeekdayOfMonth(year, month, nth, weekday) {
        const firstDay = new Date(year, month, 1);
        const firstDayWeekday = firstDay.getDay();
        const diff = (weekday - firstDayWeekday + 7) % 7;
        const nthDay = 1 + diff + (nth - 1) * 7;
        const date = new Date(year, month, nthDay);
        return date;
    },
    
    // Helper: Get last weekday of a month (weekday: 0=Sun, 1=Mon, ..., 6=Sat)
    getLastWeekdayOfMonth(year, month, weekday) {
        const lastDay = new Date(year, month + 1, 0);
        const lastDayWeekday = lastDay.getDay();
        const diff = (lastDayWeekday - weekday + 7) % 7;
        return new Date(year, month, lastDay.getDate() - diff);
    },

    normalizeDate(date) {
        return new Date(date.getFullYear(), date.getMonth(), date.getDate());
    },

    addMonthsClamped(date, monthsToAdd) {
        const year = date.getFullYear();
        const month = date.getMonth() + monthsToAdd;
        const day = date.getDate();
        const targetYear = year + Math.floor(month / 12);
        const targetMonth = ((month % 12) + 12) % 12;
        const lastDayOfTargetMonth = new Date(targetYear, targetMonth + 1, 0).getDate();
        return new Date(targetYear, targetMonth, Math.min(day, lastDayOfTargetMonth));
    },

    addYearsClamped(date, yearsToAdd) {
        const targetYear = date.getFullYear() + yearsToAdd;
        const targetMonth = date.getMonth();
        const targetDay = date.getDate();
        const lastDayOfTargetMonth = new Date(targetYear, targetMonth + 1, 0).getDate();
        return new Date(targetYear, targetMonth, Math.min(targetDay, lastDayOfTargetMonth));
    },

    // ── Calendar ───────────────────────────────────
    isAppointmentOnDate(record, dateStr) {
        if (!record.reminder_date) {
            return false;
        }
        
        // Target date
        const targetDate = new Date(dateStr);
        const d1 = new Date(targetDate.getFullYear(), targetDate.getMonth(), targetDate.getDate());
        
        // Start date
        const startDate = new Date(record.reminder_date.substring(0,10));
        const d2 = new Date(startDate.getFullYear(), startDate.getMonth(), startDate.getDate());
        
        // End date (if provided)
        const endDate = record.reminder_end_date ? new Date(record.reminder_end_date.substring(0,10)) : null;
        const d3 = endDate ? new Date(endDate.getFullYear(), endDate.getMonth(), endDate.getDate()) : null;
        
        // Check if date is before start date
        if (d1 < d2) {
            return false;
        }
        
        // Case 1: No repeat
        if (!record.reminder_repeat) {
            if (d3) {
                return d1 >= d2 && d1 <= d3;
            } else {
                return d1.getTime() === d2.getTime();
            }
        }
        
        // Case 2: Has repeat
        // Always show the original start date first
        if (d1.getTime() === d2.getTime()) {
            return true;
        }
        
        // Check if we have an end date for the series, and d1 is past that
        if (d3 && d1 > d3) {
            return false;
        }
        
        // Calculate the duration of the original appointment (if any)
        const durationDays = d3 ? Math.round((d3.getTime() - d2.getTime()) / (1000 * 60 * 60 * 24)) : 0;
        
        // Check the repeat type
        let repeatType = record.reminder_repeat;
        let repeatData = null;
        try {
            repeatData = JSON.parse(record.reminder_repeat);
            repeatType = repeatData.type;
        } catch (e) {
            // legacy string
        }
        
        // --- Weekly (legacy or JSON) ---
        if (repeatType === 'weekly') {
            let targetWeekday = d2.getDay();
            if (repeatData && typeof repeatData.weekday === 'number') {
                targetWeekday = repeatData.weekday;
            }
            
            if (d1.getDay() === targetWeekday) {
                return true;
            }
        }
        
        // --- Weekly Interval ---
        if (repeatType === 'weekly_interval') {
            const targetWeekday = repeatData?.weekday ?? 1;
            const interval = repeatData?.interval ?? 2;
            
            if (d1.getDay() === targetWeekday) {
                let firstRepeat = new Date(d2);
                const daysToAdd = (targetWeekday - firstRepeat.getDay() + 7) % 7;
                firstRepeat.setDate(firstRepeat.getDate() + daysToAdd);
                if (firstRepeat < d2) firstRepeat.setDate(firstRepeat.getDate() +7);
                
                const diffMs = d1.getTime() - firstRepeat.getTime();
                const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
                
                if (diffDays >=0 && diffDays % (interval * 7) === 0) {
                    return true;
                }
            }
        }

        // --- Monthly Interval ---
        if (repeatType === 'monthly_interval') {
            const interval = repeatData?.interval ?? 2;
            const diffMonths = (d1.getFullYear() - d2.getFullYear()) * 12 + (d1.getMonth() - d2.getMonth());

            if (diffMonths >= 0 && diffMonths % interval === 0) {
                const mode = repeatData?.mode || 'date';
                let candidate;
                if (mode === 'weekday') {
                    const nth = repeatData?.nth ?? 1;
                    const weekday = repeatData?.weekday ?? 1;
                    const useLastWeekday = nth === 'last' || nth === 5;
                    candidate = useLastWeekday
                        ? this.getLastWeekdayOfMonth(d1.getFullYear(), d1.getMonth(), weekday)
                        : this.getNthWeekdayOfMonth(d1.getFullYear(), d1.getMonth(), nth, weekday);
                } else {
                    candidate = this.addMonthsClamped(d2, diffMonths);
                }
                if (candidate.getTime() === d1.getTime()) {
                    return true;
                }
            }
        }

        // --- Yearly Interval ---
        if (repeatType === 'yearly_interval') {
            const interval = repeatData?.interval ?? 2;
            const diffYears = d1.getFullYear() - d2.getFullYear();

            if (diffYears >= 0 && diffYears % interval === 0) {
                const candidate = this.addYearsClamped(d2, diffYears);
                if (candidate.getTime() === d1.getTime()) {
                    return true;
                }
            }
        }
        
        // --- Monthly (legacy) ---
        if (repeatType === 'monthly') {
            if (d1.getDate() === d2.getDate()) {
                return true;
            }
        }
        
        // --- Monthly Nth Weekday ---
        if (repeatType === 'monthly_nth_weekday') {
            const nth = repeatData?.nth ?? 1;
            const weekday = repeatData?.weekday ?? 1;

            const useLastWeekday = nth === 'last' || nth === 5;
            const candidate = useLastWeekday
                ? this.getLastWeekdayOfMonth(d1.getFullYear(), d1.getMonth(), weekday)
                : this.getNthWeekdayOfMonth(d1.getFullYear(), d1.getMonth(), nth, weekday);

            if (candidate.getTime() === d1.getTime()) {
                return true;
            } else if (!useLastWeekday && (candidate.getMonth() !== d1.getMonth() || candidate.getFullYear() !== d1.getFullYear())) {
                // Fallback to first of next month
                const nextMonth = this.getNthWeekdayOfMonth(d1.getFullYear(), d1.getMonth() + 1, 1, weekday);
                if (nextMonth.getTime() === d1.getTime()) {
                    return true;
                }
            }
        }
        
        // --- Monthly Last Weekday ---
        if (repeatType === 'monthly_last_weekday') {
            const weekday = repeatData?.weekday ?? 1;
            const candidate = this.getLastWeekdayOfMonth(d1.getFullYear(), d1.getMonth(), weekday);
            if (candidate.getTime() === d1.getTime()) {
                return true;
            }
        }
        
        // --- Yearly ---
        if (repeatType === 'yearly') {
            if (d1.getMonth() === d2.getMonth() && d1.getDate() === d2.getDate()) {
                return true;
            }
        }
        
        return false;
    },

    async renderCalendar(showLoadingOverlay = false) {
        // Wenn manueller Offline-Modus aktiv ist, nicht laden (Overlay wird in showSection angezeigt)
        if (this.manualOfflineMode) {
            console.log('📡 Kalender: Manueller Offline-Modus aktiv - Nicht laden');
            return;
        }

        // Load all records for calendar (ignore search filter)
        const params = new URLSearchParams({
            filter: 'all',
            search_type: 'all',
            limit: 1000,  // Load all records for calendar
            offset: 0
        });
        try {
            const data = await this.apiGet(`/records?${params.toString()}`, showLoadingOverlay);
            this.records = data.records || [];
            this.appointmentOnDateCache.clear();
        } catch (e) {
            console.error('Fehler beim Laden der Akten für den Kalender:', e);
            this.records = [];
        }

        const d = this.calendarDate;
        const year = d.getFullYear(), month = d.getMonth();
        document.getElementById('calMonth').textContent = d.toLocaleDateString('de-DE', { month: 'long', year: 'numeric' });

        const firstDay = new Date(year, month, 1).getDay();
        const daysInMonth = new Date(year, month + 1, 0).getDate();
        const startOffset = firstDay === 0 ? 6 : firstDay - 1; // Monday start

        let html = '';
        ['Mo','Di','Mi','Do','Fr','Sa','So'].forEach(w => html += `<div class="cal-weekday">${w}</div>`);
        for (let i = 0; i < startOffset; i++) html += `<div class="cal-day empty"></div>`;

        const today = new Date();
        for (let day = 1; day <= daysInMonth; day++) {
            const isToday = day === today.getDate() && month === today.getMonth() && year === today.getFullYear();
            const dateStr = `${year}-${String(month+1).padStart(2,'0')}-${String(day).padStart(2,'0')}`;
            const dayReminders = this.records.filter(r => this.isAppointmentOnDate(r, dateStr));
            const reminderCount = dayReminders.length;
            const hasReminder = reminderCount > 0;
            const selected = this.selectedCalDate === dateStr ? 'selected' : '';
            const countVariant = hasReminder && dayReminders.every(r => r.reminder_is_private) ? 'private' : 'all';
            const countBadge = hasReminder ? `<span class="reminder-count reminder-count-${countVariant}">${reminderCount}</span>` : '';
            html += `<div class="cal-day ${isToday?'today':''} ${hasReminder?'has-reminders':''} ${selected}" onclick="App.selectCalendarDay('${dateStr}', this)">${day}${countBadge}</div>`;
        }
        document.getElementById('calendarGrid').innerHTML = html;

        // If no day selected yet, auto-select today
        if (!this.selectedCalDate) {
            const todayStr = `${today.getFullYear()}-${String(today.getMonth()+1).padStart(2,'0')}-${String(today.getDate()).padStart(2,'0')}`;
            this.selectCalendarDay(todayStr);
        } else {
            this.renderCalendarReminders(this.selectedCalDate);
        }
    },

    selectCalendarDay(dateStr, el) {
        this.selectedCalDate = dateStr;
        // Update visual selection
        document.querySelectorAll('.cal-day').forEach(d => d.classList.remove('selected'));
        if (el) el.classList.add('selected');
        else {
            // Find element by matching onclick attribute
            document.querySelectorAll('.cal-day').forEach(d => {
                if (d.getAttribute('onclick')?.includes(`'${dateStr}'`)) d.classList.add('selected');
            });
        }
        this.renderCalendarReminders(dateStr);
    },

    renderCalendarReminders(dateStr) {
        const container = document.getElementById('calendarReminders');
        const reminders = this.records.filter(r => this.isAppointmentOnDate(r, dateStr));
        if (!reminders.length) {
            container.innerHTML = `
                <div class="empty-state" style="grid-column: 1 / -1;">
                    <i class="fas fa-calendar-check"></i>
                    <p>Keine Termine am ${dateStr.split('-').reverse().join('.')}</p>
                </div>`;
            return;
        }
        container.innerHTML = reminders.map(r => this.recordCardHTML(r)).join('');
    },

    changeMonth(delta) {
        this.calendarDate.setMonth(this.calendarDate.getMonth() + delta);
        this.selectedCalDate = null;
        this.renderCalendar();
    },

    // ── Users ──────────────────────────────────────
    async loadUsers(showLoadingOverlay = false) {
        // Wenn manueller Offline-Modus aktiv ist, nicht laden (Overlay wird in showSection angezeigt)
        if (this.manualOfflineMode) {
            console.log('📡 Users: Manueller Offline-Modus aktiv - Nicht laden');
            return;
        }

        if (this.currentUser?.role !== 'admin') { this.showSection('dashboard'); return; }
        try {
            const [usersData, onlineData] = await Promise.all([
                this.apiGet('/users', showLoadingOverlay),
                this.apiGet('/auth/admin/online-status', false)
            ]);
            
            // Online-Status Map erstellen für schnellen Lookup
            const onlineMap = {};
            if (onlineData && onlineData.online_users) {
                onlineData.online_users.forEach(u => {
                    onlineMap[u.id] = u;
                });
            }
            
            const tbody = document.getElementById('usersTableBody');
            tbody.innerHTML = usersData.users.map(u => {
                const onlineInfo = onlineMap[u.id] || {};
                const isOnline = onlineInfo.is_online;
                const lastSeen = onlineInfo.last_seen ? new Date(onlineInfo.last_seen).toLocaleString('de-DE') : '-';
                
                return `
                <tr>
                    <td>${this.escapeHtml(u.username)}</td>
                    <td>${u.role}</td>
                    <td>
                        <span class="status-indicator ${isOnline ? 'online' : 'offline'}" title="${isOnline ? 'Online' : 'Offline'}"></span>
                        ${isOnline ? 'Online' : 'Offline'}
                    </td>
                    <td style="text-align:center">
                        <span class="perm-tag ${u.can_read?'on':'off'}" title="Lesen"><i class="fas fa-eye"></i></span>
                        <span class="perm-tag ${u.can_write?'on':'off'}" title="Schreiben"><i class="fas fa-pen"></i></span>
                        <span class="perm-tag ${u.can_download?'on':'off'}" title="Download"><i class="fas fa-download"></i></span>
                        <span class="perm-tag ${u.can_upload?'on':'off'}" title="Upload"><i class="fas fa-upload"></i></span>
                        <span class="perm-tag ${u.can_delete?'on':'off'}" title="Löschen"><i class="fas fa-trash"></i></span>
                        <span class="perm-tag ${u.can_fill_forms?'on':'off'}" title="Formulare"><i class="fas fa-file-invoice"></i></span>
                        <span class="perm-tag ${u.can_set_category?'on':'off'}" title="Kategorie"><i class="fas fa-tag"></i></span>
                        <span class="perm-tag ${u.can_set_status?'on':'off'}" title="Status"><i class="fas fa-flag"></i></span>
                        <span class="perm-tag ${u.can_set_border_color?'on':'off'}" title="Farbe"><i class="fas fa-palette"></i></span>
                        <span class="perm-tag ${u.can_set_reminder?'on':'off'}" title="Termin"><i class="fas fa-calendar"></i></span>
                        <span class="perm-tag ${u.can_delete_termine?'on':'off'}" title="Termin löschen"><i class="fas fa-calendar-times"></i></span>
                        <span class="perm-tag ${u.can_set_erinnerung?'on':'off'}" title="Erinnerung"><i class="fas fa-bell"></i></span>
                        <span class="perm-tag ${u.can_delete_erinnerung?'on':'off'}" title="Erinnerung löschen"><i class="fas fa-bell-slash"></i></span>
                        <span class="perm-tag ${u.can_set_note?'on':'off'}" title="Notiz"><i class="fas fa-sticky-note"></i></span>
                        <span class="perm-tag ${u.can_view_stats?'on':'off'}" title="Statistik"><i class="fas fa-chart-bar"></i></span>
                        <span class="perm-tag ${u.can_chat?'on':'off'}" title="Chat"><i class="fas fa-comments"></i></span>
                        <span class="perm-tag ${u.can_view_archive?'on':'off'}" title="Archiv ansehen"><i class="fas fa-archive"></i></span>
                        <span class="perm-tag ${u.can_archive?'on':'off'}" title="Archivieren"><i class="fas fa-box-archive"></i></span>
                    </td>
                    <td>${u.active ? '<span class="status-active">Aktiv</span>' : '<span class="status-inactive">Inaktiv</span>'}</td>
                    <td class="actions">
                        ${isOnline ? 
                            `<button class="btn btn-sm btn-secondary" title="Login zurücksetzen" onclick="App.resetUserLogin(${u.id})"><i class="fas fa-sign-out-alt"></i></button>` : 
                            ''
                        }
                        <button class="btn btn-sm btn-secondary" title="${u.signature ? 'Unterschrift ändern' : 'Unterschrift hochladen'}" onclick="App.uploadSignature(${u.id})">
                            <i class="fas ${u.signature ? 'fa-signature' : 'fa-file-signature'}"></i>
                        </button>
                        <button class="btn btn-sm btn-secondary" title="Benutzer bearbeiten" onclick="App.editUser(${u.id})"><i class="fas fa-edit"></i></button>
                        <button class="btn btn-sm btn-secondary" title="Passwort ändern" onclick="App.changePassword(${u.id})"><i class="fas fa-key"></i></button>
                        <button class="btn btn-sm btn-danger" title="Benutzer löschen" ${u.role==='admin'?'disabled':''} onclick="App.deleteUser(${u.id})"><i class="fas fa-trash"></i></button>
                    </td>
                </tr>
            `}).join('');
        } catch (e) {
            this.toast(e.message, 'error');
        }
    },

    async resetUserLogin(userId) {
        if (!await this.confirm('Login zurücksetzen', 'Möchten Sie den Login-Status dieses Benutzers wirklich zurücksetzen? Der Benutzer wird dann von allen Geräten abgemeldet.', 'Ja, zurücksetzen', 'btn-warning')) {
            return;
        }
        try {
            await this.apiPost(`/auth/admin/reset-login-status/${userId}`);
            this.toast('Login-Status erfolgreich zurückgesetzt', 'success');
            this.loadUsers();
        } catch (e) {
            this.toast('Fehler beim Zurücksetzen: ' + e.message, 'error');
        }
    },

    async loadAuditLogs(showLoadingOverlay = false) {
        // Wenn manueller Offline-Modus aktiv ist, nicht laden (Overlay wird in showSection angezeigt)
        if (this.manualOfflineMode) {
            console.log('📡 Audit: Manueller Offline-Modus aktiv - Nicht laden');
            return;
        }

        if (this.currentUser?.role !== 'admin') { this.showSection('dashboard'); return; }
        try {
            const data = await this.apiGet('/admin/audit-logs', showLoadingOverlay);
            const content = data.logs || 'Keine Log-Einträge vorhanden.';
            const logEl = document.getElementById('auditLogContent');
            if (logEl) {
                // Zeilen umkehren, damit neueste Einträge oben stehen
                const lines = content.split('\n').filter(line => line.trim());
                const reversedContent = lines.reverse().join('\n');
                
                // LOGIN-Einträge grün markieren
                const loginHighlighted = reversedContent.replace(
                    /LOGIN/g,
                    '<span style="color: #28a745; font-weight: bold;">LOGIN</span>'
                );
                
                logEl.innerHTML = loginHighlighted;
                // Nach oben scrollen zum neuesten Eintrag
                logEl.scrollTop = 0;
            }
        } catch (e) {
            this.toast('Fehler beim Laden des Logbuchs: ' + e.message, 'error');
            const logEl = document.getElementById('auditLogContent');
            if (logEl) logEl.textContent = 'Fehler beim Laden des Logbuchs.';
        }
    },

    async saveUser(ev) {
        ev.preventDefault();
        const id = document.getElementById('userEditId').value;
        const body = {
            username: document.getElementById('userEditName').value.trim(),
            role: document.getElementById('userEditRole').value,
            active: document.getElementById('userEditActive').checked,
            can_read: document.getElementById('userEditRead').checked,
            can_write: document.getElementById('userEditWrite').checked,
            can_delete: document.getElementById('userEditDelete').checked,
            can_download: document.getElementById('userEditDownload').checked,
            can_upload: document.getElementById('userEditUpload').checked,
            can_fill_forms: document.getElementById('userEditFillForms').checked,
            can_set_category: document.getElementById('userEditSetCategory').checked,
            can_set_status: document.getElementById('userEditSetStatus').checked,
            can_set_border_color: document.getElementById('userEditSetBorderColor').checked,
            can_set_reminder: document.getElementById('userEditSetReminder').checked,
            can_delete_termine: document.getElementById('userEditDeleteTermine').checked,
            can_set_erinnerung: document.getElementById('userEditSetErinnerung').checked,
            can_delete_erinnerung: document.getElementById('userEditDeleteErinnerung').checked,
            can_set_note: document.getElementById('userEditSetNote').checked,
            can_view_stats: document.getElementById('userEditViewStats').checked,
            can_view_records: document.getElementById('userEditViewRecords').checked,
            can_view_gallery: document.getElementById('userEditViewGallery').checked,
            can_chat: document.getElementById('userEditChat').checked,
            can_view_map: document.getElementById('userEditViewMap').checked,
            can_view_calendar: document.getElementById('userEditViewCalendar').checked,
            can_view_assistant: document.getElementById('userEditViewAssistant').checked,
            can_view_archive: document.getElementById('userEditViewArchive').checked,
            can_archive: document.getElementById('userEditArchive').checked,
        };
        try {
            if (id) {
                await this.apiPut(`/users/${id}`, body);
                this.toast('Benutzer aktualisiert', 'success');
            } else {
                const pass = document.getElementById('userEditPass').value;
                if (!pass) { this.toast('Passwort erforderlich', 'error'); return; }
                body.password = pass;
                await this.apiPost('/users', body);
                this.toast('Benutzer erstellt', 'success');
            }
            this.closeModal();
            this.loadUsers();
        } catch (e) {
            this.toast(e.message, 'error');
        }
    },

    openUserModal(user = null) {
        document.getElementById('userEditId').value = user ? user.id : '';
        document.getElementById('userEditName').value = user ? user.username : '';
        // Set role input value
        const newRole = user ? user.role : 'user';
        document.getElementById('userEditRole').value = newRole;
        // Update custom role dropdown toggle
        const roleDropdown = document.getElementById('userRoleDropdown');
        const roleToggle = roleDropdown.querySelector('.dropdown-toggle');
        const roleMenu = roleDropdown.querySelector('.dropdown-menu');
        const selectedRoleBtn = roleMenu.querySelector(`button[data-value="${newRole}"]`);
        if (selectedRoleBtn) {
            roleToggle.innerHTML = selectedRoleBtn.innerHTML;
            roleMenu.querySelectorAll('button').forEach(b => b.classList.remove('selected'));
            selectedRoleBtn.classList.add('selected');
        }
        document.getElementById('userEditActive').checked = user ? user.active : true;
        document.getElementById('userEditRead').checked = user ? user.can_read : true;
        document.getElementById('userEditWrite').checked = user ? user.can_write : true;
        document.getElementById('userEditDelete').checked = user ? user.can_delete : false;
        document.getElementById('userEditDownload').checked = user ? user.can_download : true;
        document.getElementById('userEditUpload').checked = user ? user.can_upload : true;
        document.getElementById('userEditFillForms').checked = user ? user.can_fill_forms : true;
        document.getElementById('userEditSetCategory').checked = user ? user.can_set_category : true;
        document.getElementById('userEditSetStatus').checked = user ? user.can_set_status : true;
        document.getElementById('userEditSetBorderColor').checked = user ? user.can_set_border_color : true;
        document.getElementById('userEditSetReminder').checked = user ? user.can_set_reminder : true;
        document.getElementById('userEditDeleteTermine').checked = user ? (user.can_delete_termine ?? true) : true;
        document.getElementById('userEditSetErinnerung').checked = user ? user.can_set_erinnerung : true;
        document.getElementById('userEditDeleteErinnerung').checked = user ? (user.can_delete_erinnerung ?? true) : true;
        document.getElementById('userEditSetNote').checked = user ? user.can_set_note : true;
        document.getElementById('userEditViewStats').checked = user ? user.can_view_stats : true;
        document.getElementById('userEditViewRecords').checked = user ? (user.can_view_records ?? true) : true;
        document.getElementById('userEditViewGallery').checked = user ? (user.can_view_gallery ?? true) : true;
        document.getElementById('userEditChat').checked = user ? (user.can_chat ?? true) : true;
        document.getElementById('userEditViewMap').checked = user ? (user.can_view_map ?? true) : true;
        document.getElementById('userEditViewCalendar').checked = user ? (user.can_view_calendar ?? true) : true;
        document.getElementById('userEditViewAssistant').checked = user ? (user.can_view_assistant ?? true) : true;
        document.getElementById('userEditViewArchive').checked = user ? (user.can_view_archive ?? true) : true;
        document.getElementById('userEditArchive').checked = user ? (user.can_archive ?? true) : true;
        document.getElementById('userEditPass').value = '';
        document.getElementById('userPassGroup').style.display = user ? 'none' : 'block';
        document.getElementById('userModalTitle').textContent = user ? 'Benutzer bearbeiten' : 'Neuer Benutzer';
        this.showModal('userModal');
    },

    async editUser(id) {
        try {
            const data = await this.apiGet('/users', true);
            const user = data.users.find(u => u.id === id);
            if (user) {
                this.openUserModal(user);
            }
        } catch (e) {
            this.toast('Fehler beim Laden des Benutzers: ' + e.message, 'error');
        }
    },

    async deleteUser(id) {
        if (!await this.confirm('Benutzer löschen?', 'Dies kann nicht rückgängig gemacht werden.', 'Ja, löschen', 'btn-danger')) return;
        try {
            const result = await this.apiDelete(`/users/${id}`);
            console.log('Delete user result:', result);
            this.toast('Benutzer geloescht', 'success');
            this.loadUsers();
        } catch (e) {
            console.error('Delete user error:', e);
            this.toast(e.message || 'Fehler beim Löschen des Benutzers', 'error');
        }
    },

    async changePassword(id) {
        const pw = prompt('Neues Passwort eingeben (mind. 8 Zeichen):');
        if (!pw || pw.length < 8) { this.toast('Passwort zu kurz', 'error'); return; }
        try {
            await this.apiPut(`/users/${id}/password`, { new_password: pw });
            this.toast('Passwort geaendert', 'success');
        } catch (e) {
            this.toast(e.message, 'error');
        }
    },

    // ── Settings ───────────────────────────────────
    toggleSecretKeyVisibility() {
        const secretKeyInput = document.getElementById('settingSecretKey');
        const secretKeyToggleIcon = document.getElementById('secretKeyToggleIcon');
        
        if (secretKeyInput && secretKeyToggleIcon) {
            if (secretKeyInput.type === 'password') {
                secretKeyInput.type = 'text';
                secretKeyToggleIcon.className = 'fas fa-eye-slash';
            } else {
                secretKeyInput.type = 'password';
                secretKeyToggleIcon.className = 'fas fa-eye';
            }
        }
    },

    toggleBackupTimeEnabled() {
        const settingBackupOnStartup = document.getElementById('settingBackupOnStartup');
        const settingBackupTime = document.getElementById('settingBackupTime');
        const settingBackupInterval = document.getElementById('settingBackupInterval');
        
        if (settingBackupOnStartup && settingBackupTime && settingBackupInterval) {
            const isStartupBackup = settingBackupOnStartup.checked;
            settingBackupTime.disabled = isStartupBackup;
            settingBackupInterval.disabled = isStartupBackup;
            
            if (isStartupBackup) {
                settingBackupTime.value = '';
            }
        }
    },

    async loadOcrStatus() {
        await Promise.all([this.loadOcrQueue(), this.loadFailedOcrScans()]);
    },

    async loadOcrQueue() {
        try {
            const container = document.getElementById('ocrQueueContainer');
            
            container.innerHTML = '<div class="text-center py-5"><div class="spinner-border text-primary" role="status"></div></div>';
            
            const response = await this.apiGet('/records/ocr/queue');
            
            if (!response.queue_scans || response.queue_scans.length === 0) {
                container.innerHTML = `
                    <div class="text-center py-5">
                        <i class="fas fa-check-circle text-success fa-3x mb-3"></i>
                        <h6 class="text-muted">Keine Scans in der Warteschlange</h6>
                        <small class="text-muted">Alle OCR-Jobs wurden abgeschlossen</small>
                    </div>
                `;
                return;
            }
            
            let html = '<div class="table-responsive"><table class="table table-hover"><thead class="thead-light"><tr><th style="width: 100px;">Status</th><th>Datei</th><th>Akte</th><th style="width: 120px;">Fortschritt</th></tr></thead><tbody>';
            
            response.queue_scans.forEach(scan => {
                const statusBadge = scan.status === 'running' 
                    ? '<span class="badge badge-primary"><i class="fas fa-spinner fa-spin mr-1"></i>Läuft</span>'
                    : '<span class="badge badge-secondary"><i class="fas fa-clock mr-1"></i>Wartet</span>';
                
                const progress = scan.pages_total > 0 
                    ? `${scan.pages_done}/${scan.pages_total} (${Math.round(scan.progress * 100)}%)`
                    : 'Warte...';
                
                const progressBar = scan.status === 'running' && scan.pages_total > 0
                    ? `<div class="progress mt-2" style="height: 6px;"><div class="progress-bar progress-bar-striped progress-bar-animated bg-success" style="width: ${scan.progress * 100}%"></div></div>`
                    : '';
                
                html += `
                    <tr>
                        <td>${statusBadge}</td>
                        <td>
                            <div class="font-weight-medium text-dark">${this.escapeHtml(scan.filename)}</div>
                            ${progressBar}
                        </td>
                        <td><small class="text-muted">${scan.record_number}: ${this.escapeHtml(scan.record_title || '')}</small></td>
                        <td><small class="text-muted font-weight-medium">${progress}</small></td>
                    </tr>
                `;
            });
            
            html += '</tbody></table></div>';
            container.innerHTML = html;
        } catch (error) {
            console.error('Fehler beim Laden der OCR-Warteschlange:', error);
            const container = document.getElementById('ocrQueueContainer');
            container.innerHTML = `
                <div class="alert alert-danger" role="alert">
                    <i class="fas fa-exclamation-triangle mr-2"></i>
                    Fehler beim Laden: ${this.escapeHtml(error.message)}
                </div>
            `;
        }
    },

    async loadFailedOcrScans() {
        try {
            const container = document.getElementById('failedOcrScansContainer');
            const actions = document.getElementById('failedOcrScansActions');
            
            container.innerHTML = '<div class="text-center py-5"><div class="spinner-border text-primary" role="status"></div></div>';
            
            const response = await this.apiGet('/records/ocr/failed');
            
            if (!response.failed_scans || response.failed_scans.length === 0) {
                container.innerHTML = `
                    <div class="text-center py-5">
                        <i class="fas fa-check-circle text-success fa-3x mb-3"></i>
                        <h6 class="text-muted">Keine fehlgeschlagenen OCR-Scans</h6>
                        <small class="text-muted">Alle Scans wurden erfolgreich abgeschlossen</small>
                    </div>
                `;
                actions.classList.add('hidden');
                return;
            }
            
            let html = '<div class="table-responsive"><table class="table table-hover"><thead class="thead-light"><tr><th style="width: 40px;"><input type="checkbox" id="selectAllFailedOcr" onchange="App.toggleAllFailedOcrSelection()"></th><th>Datei</th><th>Akte</th><th>Fehler</th><th style="width: 80px;">Anzahl</th></tr></thead><tbody>';
            
            response.failed_scans.forEach(scan => {
                const rowClass = scan.failure_count >= 3 ? 'table-danger' : '';
                const badgeClass = scan.failure_count >= 3 ? 'badge-danger' : 'badge-warning';
                
                html += `
                    <tr class="${rowClass}">
                        <td><input type="checkbox" class="failed-ocr-checkbox" data-attachment-id="${scan.attachment_id}"></td>
                        <td>
                            <div class="font-weight-medium text-dark">${this.escapeHtml(scan.filename)}</div>
                        </td>
                        <td><small class="text-muted">${scan.record_number}: ${this.escapeHtml(scan.record_title || '')}</small></td>
                        <td>
                            <small class="text-muted d-block" title="${this.escapeHtml(scan.error_message || '')}" style="max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                                ${this.escapeHtml(scan.error_message || 'Unbekannter Fehler')}
                            </small>
                        </td>
                        <td><span class="badge ${badgeClass}">${scan.failure_count}x</span></td>
                    </tr>
                `;
            });
            
            html += '</tbody></table></div>';
            container.innerHTML = html;
            actions.classList.remove('hidden');
        } catch (error) {
            console.error('Fehler beim Laden fehlgeschlagener OCR-Scans:', error);
            const container = document.getElementById('failedOcrScansContainer');
            container.innerHTML = `
                <div class="alert alert-danger" role="alert">
                    <i class="fas fa-exclamation-triangle mr-2"></i>
                    Fehler beim Laden: ${this.escapeHtml(error.message)}
                </div>
            `;
        }
    },

    toggleAllFailedOcrSelection() {
        const selectAll = document.getElementById('selectAllFailedOcr');
        const checkboxes = document.querySelectorAll('.failed-ocr-checkbox');
        checkboxes.forEach(cb => cb.checked = selectAll.checked);
    },

    getSelectedFailedOcrIds() {
        const checkboxes = document.querySelectorAll('.failed-ocr-checkbox:checked');
        return Array.from(checkboxes).map(cb => parseInt(cb.dataset.attachmentId));
    },

    async requeueSelectedOcrScans() {
        const attachmentIds = this.getSelectedFailedOcrIds();
        
        if (attachmentIds.length === 0) {
            this.toast('Bitte wählen Sie mindestens einen Scan aus', 'warning');
            return;
        }
        
        try {
            const response = await this.apiPost('/records/ocr/failed/requeue', { attachment_ids: attachmentIds });
            
            const successCount = response.results.filter(r => r.success).length;
            const failCount = response.results.length - successCount;
            
            if (failCount > 0) {
                this.toast(`${successCount} Scans neu eingereiht, ${failCount} fehlgeschlagen`, 'warning');
            } else {
                this.toast(`${successCount} Scans erfolgreich neu eingereiht`, 'success');
            }
            
            this.loadFailedOcrScans();
        } catch (error) {
            console.error('Fehler beim Neu-Einreihen:', error);
            this.toast('Fehler beim Neu-Einreihen: ' + error.message, 'error');
        }
    },

    async deleteSelectedOcrScans() {
        const attachmentIds = this.getSelectedFailedOcrIds();
        
        if (attachmentIds.length === 0) {
            this.toast('Bitte wählen Sie mindestens einen Scan aus', 'warning');
            return;
        }
        
        if (!confirm(`Wollen Sie wirklich ${attachmentIds.length} OCR-Einträge löschen? Die Dateien bleiben erhalten.`)) {
            return;
        }
        
        try {
            const response = await this.apiPost('/records/ocr/failed/delete', { attachment_ids: attachmentIds });
            this.toast(`${response.deleted_count} OCR-Einträge gelöscht`, 'success');
            this.loadFailedOcrScans();
        } catch (error) {
            console.error('Fehler beim Löschen:', error);
            this.toast('Fehler beim Löschen: ' + error.message, 'error');
        }
    },

    async loadSettings(showLoadingOverlay = false) {
        // Wenn manueller Offline-Modus aktiv ist, nicht laden (Overlay wird in showSection angezeigt)
        if (this.manualOfflineMode) {
            console.log('📡 Settings: Manueller Offline-Modus aktiv - Nicht laden');
            return;
        }

        if (this.currentUser?.role !== 'admin') { this.showSection('records'); return; }
        try {
            const data = await this.apiGet('/settings', showLoadingOverlay);
            
            // Null-Prüfung für data, um Fehler beim Reiter-Wechsel zu verhindern
            if (!data) {
                console.warn('Settings konnten nicht geladen werden (data ist null)');
                return;
            }

            const settingHost = document.getElementById('settingHost');
            const settingPort = document.getElementById('settingPort');
            const settingPlzValidation = document.getElementById('settingPlzValidation');
            const settingMaxSize = document.getElementById('settingMaxSize');
            const settingSecretKey = document.getElementById('settingSecretKey');
            const settingIpFilterEnabled = document.getElementById('settingIpFilterEnabled');
            const settingDataBaseDir = document.getElementById('settingDataBaseDir');
            const settingBackupDir = document.getElementById('settingBackupDir');
            const settingBackupInterval = document.getElementById('settingBackupInterval');
            const settingBackupTime = document.getElementById('settingBackupTime');
            const settingBackupKeepCount = document.getElementById('settingBackupKeepCount');
            const settingBackupOnStartup = document.getElementById('settingBackupOnStartup');
            const settingOcrScheduleMode = document.getElementById('settingOcrScheduleMode');
            const settingOcrScheduleStart = document.getElementById('settingOcrScheduleStart');
            const settingOcrScheduleEnd = document.getElementById('settingOcrScheduleEnd');
            const settingOcrPageDelay = document.getElementById('settingOcrPageDelay');
            const settingOcrJobDelay = document.getElementById('settingOcrJobDelay');
            const settingMaxLoginAttempts = document.getElementById('settingMaxLoginAttempts');
            const settingRateLimitWindow = document.getElementById('settingRateLimitWindow');
            const settingSimilarityLimit = document.getElementById('settingSimilarityLimit');
            const settingDuplicateCandidateLimit = document.getElementById('settingDuplicateCandidateLimit');
            const settingSimilarityCandidateLimit = document.getElementById('settingSimilarityCandidateLimit');
            const settingSimilarityEnabled = document.getElementById('settingSimilarityEnabled');
            const settingServerName = document.getElementById('settingServerName');
            const settingCloudflareIps = document.getElementById('settingCloudflareIps');
            const settingCustomIps = document.getElementById('settingCustomIps');
            const settingIpWhitelistMode = document.getElementById('settingIpWhitelistMode');
            const settingOcrEnabled = document.getElementById('settingOcrEnabled');
            const settingOcrLang = document.getElementById('settingOcrLang');
            const settingOcrOem = document.getElementById('settingOcrOem');
            const settingOcrPsm = document.getElementById('settingOcrPsm');
            const settingOcrDpi = document.getElementById('settingOcrDpi');
            const settingOcrPreprocessingEnabled = document.getElementById('settingOcrPreprocessingEnabled');
            const settingOcrDenoise = document.getElementById('settingOcrDenoise');
            const settingOcrSharpen = document.getElementById('settingOcrSharpen');
            const settingOcrDeskew = document.getElementById('settingOcrDeskew');
            const settingOcrContrastEnhance = document.getElementById('settingOcrContrastEnhance');
            const settingOcrBinarize = document.getElementById('settingOcrBinarize');
            const settingRequestLimitEnabled = document.getElementById('settingRequestLimitEnabled');
            const settingMaxRequestsPerMinute = document.getElementById('settingMaxRequestsPerMinute');
            const settingAutoArchive = document.getElementById('settingAutoArchive');
            const settingAgeValue = document.getElementById('settingAgeValue');
            const settingAgeUnit = document.getElementById('settingAgeUnit');
            const settingUnusedValue = document.getElementById('settingUnusedValue');
            const settingUnusedUnit = document.getElementById('settingUnusedUnit');
            const settingRunInterval = document.getElementById('settingRunInterval');
            const settingArchiveLogic = document.getElementById('settingArchiveLogic');
            const settingArchiveScheduleMode = document.getElementById('settingArchiveScheduleMode');
            const settingArchiveScheduleStart = document.getElementById('settingArchiveScheduleStart');
            const settingArchiveScheduleEnd = document.getElementById('settingArchiveScheduleEnd');
            const settingLastRun = document.getElementById('settingLastRun');

            if (settingHost) settingHost.value = data.server?.host || '127.0.0.1';
            if (settingPort) settingPort.value = data.server?.port || 8080;
            if (settingPlzValidation) settingPlzValidation.checked = data.server?.plz_validation_enabled !== false;
            if (settingMaxSize) settingMaxSize.value = data.upload?.max_file_size_mb || 50;
            if (settingSecretKey) {
                // SECRET_KEY jetzt immer anzeigen (nicht mehr maskiert)
                settingSecretKey.value = data.security?.secret_key || '';
            }
            if (settingMaxLoginAttempts) settingMaxLoginAttempts.value = data.security?.max_login_attempts || 5;
            if (settingRateLimitWindow) settingRateLimitWindow.value = data.security?.rate_limit_window_minutes || 15;
            if (settingOcrScheduleMode) settingOcrScheduleMode.value = data.ocr?.schedule_mode || 'always';
            if (settingOcrScheduleStart) settingOcrScheduleStart.value = data.ocr?.schedule_start || '20:00';
            if (settingOcrScheduleEnd) settingOcrScheduleEnd.value = data.ocr?.schedule_end || '06:00';
            // Toggle OCR schedule time inputs based on current mode
            const timeGroup = document.getElementById('ocrScheduleTimeGroup');
            if (timeGroup && settingOcrScheduleMode) {
                timeGroup.style.display = settingOcrScheduleMode.value === 'scheduled' ? 'block' : 'none';
            }
            if (settingSimilarityLimit) settingSimilarityLimit.value = data.search?.similarity_limit || 20;
            if (settingDuplicateCandidateLimit) settingDuplicateCandidateLimit.value = data.search?.duplicate_candidate_limit || 100;
            if (settingSimilarityCandidateLimit) settingSimilarityCandidateLimit.value = data.search?.similarity_candidate_limit || 200;
            if (settingSimilarityEnabled) settingSimilarityEnabled.checked = data.search?.enabled !== false;
            if (settingServerName) settingServerName.value = data.server_name || '';
            
            // OCR-Einstellungen laden
            if (settingOcrEnabled) settingOcrEnabled.checked = data.ocr?.enabled !== false;
            if (settingOcrLang) settingOcrLang.value = data.ocr?.lang || 'deu+eng';
            if (settingOcrOem) settingOcrOem.value = data.ocr?.oem || '3';
            if (settingOcrPsm) settingOcrPsm.value = data.ocr?.psm || '6';
            if (settingOcrDpi) settingOcrDpi.value = data.ocr?.dpi || 300;
            if (settingOcrPreprocessingEnabled) settingOcrPreprocessingEnabled.checked = data.ocr?.preprocessing?.enabled !== false;
            if (settingOcrDenoise) settingOcrDenoise.checked = data.ocr?.preprocessing?.denoise !== false;
            if (settingOcrSharpen) settingOcrSharpen.checked = data.ocr?.preprocessing?.sharpen !== false;
            if (settingOcrDeskew) settingOcrDeskew.checked = data.ocr?.preprocessing?.deskew !== false;
            if (settingOcrContrastEnhance) settingOcrContrastEnhance.checked = data.ocr?.preprocessing?.contrast_enhance !== false;
            if (settingOcrBinarize) settingOcrBinarize.checked = data.ocr?.preprocessing?.binarize || false;
            if (settingRequestLimitEnabled) settingRequestLimitEnabled.checked = data.network?.request_limit_enabled || false;
            if (settingMaxRequestsPerMinute) settingMaxRequestsPerMinute.value = data.network?.max_requests_per_minute || 100;
            if (settingBlockDurationSeconds) settingBlockDurationSeconds.value = data.network?.block_duration_seconds || 60;
            if (settingAutoArchive) settingAutoArchive.checked = data.archive?.auto_archive || false;
            if (settingArchiveLogic) settingArchiveLogic.value = data.archive?.logic || 'and';
            if (settingArchiveScheduleMode) settingArchiveScheduleMode.value = data.archive?.schedule_mode || 'always';
            if (settingArchiveScheduleStart) settingArchiveScheduleStart.value = data.archive?.schedule_start || '20:00';
            if (settingArchiveScheduleEnd) settingArchiveScheduleEnd.value = data.archive?.schedule_end || '06:00';
            // Toggle archive schedule time inputs based on current mode
            const archiveTimeGroup = document.getElementById('archiveScheduleTimeGroup');
            if (archiveTimeGroup && settingArchiveScheduleMode) {
                archiveTimeGroup.style.display = settingArchiveScheduleMode.value === 'scheduled' ? 'block' : 'none';
            }
            // Convert old format (days/months/years) to new format (value + unit)
            if (settingAgeValue && settingAgeUnit) {
                const archiveAge = data.archive || {};
                if (archiveAge.age_years > 0) {
                    settingAgeValue.value = archiveAge.age_years;
                    settingAgeUnit.value = 'years';
                } else if (archiveAge.age_months > 0) {
                    settingAgeValue.value = archiveAge.age_months;
                    settingAgeUnit.value = 'months';
                } else {
                    settingAgeValue.value = archiveAge.age_days || 365;
                    settingAgeUnit.value = 'days';
                }
            }
            if (settingUnusedValue && settingUnusedUnit) {
                const archiveUnused = data.archive || {};
                if (archiveUnused.unused_years > 0) {
                    settingUnusedValue.value = archiveUnused.unused_years;
                    settingUnusedUnit.value = 'years';
                } else if (archiveUnused.unused_months > 0) {
                    settingUnusedValue.value = archiveUnused.unused_months;
                    settingUnusedUnit.value = 'months';
                } else {
                    settingUnusedValue.value = archiveUnused.unused_days || 180;
                    settingUnusedUnit.value = 'days';
                }
            }
            if (settingRunInterval) settingRunInterval.value = data.archive?.run_interval || 'daily';
            if (settingLastRun) settingLastRun.value = data.archive?.last_run || 'Noch nie ausgeführt';

            // Toggle OCR schedule time inputs based on current mode
            const whitelist = data.security?.ip_whitelist || [];
            const cloudflareIPs = [
                '103.21.244.0/22',
                '103.22.200.0/22',
                '103.31.4.0/22',
                '104.16.0.0/13',
                '104.24.0.0/14',
                '108.162.192.0/18',
                '131.0.72.0/22',
                '141.101.64.0/18',
                '162.158.0.0/15',
                '172.64.0.0/13',
                '173.245.48.0/20',
                '188.114.96.0/20',
                '190.93.240.0/20',
                '197.234.240.0/22',
                '198.41.128.0/17',
                '162.159.0.0/16',
                '172.69.0.0/16',
                '176.7.43.241'
            ];
            
            if (settingIpWhitelistMode && settingCloudflareIps && settingCustomIps) {
                const whitelistMode = data.security?.ip_whitelist_mode || 'none';
                settingIpWhitelistMode.value = whitelistMode;
                
                // Load cloudflare_ips
                const cloudflareIps = data.security?.cloudflare_ips || [];
                if (JSON.stringify(cloudflareIps.sort()) === JSON.stringify(cloudflareIPs.sort())) {
                    settingCloudflareIps.value = cloudflareIPs.join('\n');
                } else {
                    settingCloudflareIps.value = Array.isArray(cloudflareIps) ? cloudflareIps.join('\n') : '';
                }
                
                // Load custom_ips
                const customIps = data.security?.custom_ips || [];
                settingCustomIps.value = Array.isArray(customIps) ? customIps.join('\n') : '';
                
                this.toggleIpWhitelistMode();
            }

            // Gewichtungen für Ähnlichkeitssuche laden
            if (data.similarity_weights) {
                const weights = data.similarity_weights;
                document.getElementById('weightTitle').value = weights.title || 1.0;
                document.getElementById('weightTitleValue').textContent = weights.title || 1.0;
                
                document.getElementById('weightContent').value = weights.content || 1.0;
                document.getElementById('weightContentValue').textContent = weights.content || 1.0;
                
                document.getElementById('weightAddress').value = weights.address || 0.5;
                document.getElementById('weightAddressValue').textContent = weights.address || 0.5;
                
                document.getElementById('weightHashtags').value = weights.hashtags || 0.8;
                document.getElementById('weightHashtagsValue').textContent = weights.hashtags || 0.8;
                
                document.getElementById('weightCategory').value = weights.category || 0.6;
                document.getElementById('weightCategoryValue').textContent = weights.category || 0.6;
                
                document.getElementById('weightBorderColor').value = weights.border_color || 0.3;
                document.getElementById('weightBorderColorValue').textContent = weights.border_color || 0.3;
                
                document.getElementById('weightStatus').value = weights.status || 0.4;
                document.getElementById('weightStatusValue').textContent = weights.status || 0.4;
                
                document.getElementById('weightAttachments').value = weights.attachments || 0.5;
                document.getElementById('weightAttachmentsValue').textContent = weights.attachments || 0.5;
                
                document.getElementById('weightOcrText').value = weights.ocr_text || 0.7;
                document.getElementById('weightOcrTextValue').textContent = weights.ocr_text || 0.7;
                
                document.getElementById('weightCreationDate').value = weights.creation_date || 0.2;
                document.getElementById('weightCreationDateValue').textContent = weights.creation_date || 0.2;
                
                document.getElementById('weightUpdateDate').value = weights.update_date || 0.3;
                document.getElementById('weightUpdateDateValue').textContent = weights.update_date || 0.3;
            }
            
            if (settingDataBaseDir) settingDataBaseDir.value = data.paths?.data_base_dir || './Speicher';
            if (settingBackupDir) settingBackupDir.value = data.paths?.backup_dir || './Backups';
            
            if (settingBackupInterval) settingBackupInterval.value = data.backup?.interval || 'daily';
            if (settingBackupTime) settingBackupTime.value = data.backup?.time || '00:00';
            if (settingBackupKeepCount) settingBackupKeepCount.value = data.backup?.keep_count || 5;
            if (settingBackupOnStartup) settingBackupOnStartup.checked = data.backup?.backup_on_startup || false;
            if (settingIpFilterEnabled) settingIpFilterEnabled.checked = data.settings?.ip_filter_enabled === 'true';
            if (data.duplicate_threshold !== undefined) {
                const settingDuplicateThreshold = document.getElementById('settingDuplicateThreshold');
                if (settingDuplicateThreshold) settingDuplicateThreshold.value = Math.round(data.duplicate_threshold * 100);
            }

            // Settings für spätere Verwendung speichern
            this.settings = data.settings || {};

            // Toggle backup time and interval based on startup backup setting
            this.toggleBackupTimeEnabled();

            // IP-Whitelist wird jetzt über die allgemeinen Settings verwaltet (cloudflare_ips, custom_ips)
            // this.loadIpWhitelist(); // Veraltet - Endpoint existiert nicht mehr

            // Referenzorte laden
            this.loadReferenzorte();

            // Update-Check
            this.checkUpdate();
            this.updateUrlPreview();

            // Sicherstellen dass alle Settings-Checkboxen anklickbar sind (für Touch-Geräte)
            this.ensureSettingsCheckboxesClickable();
        } catch (e) {
            this.toast(e.message, 'error');
        }
    },

    ensureSettingsCheckboxesClickable() {
        // Nicht mehr benötigt - Checkboxen sind jetzt direkt im HTML ohne Label-Wrapper
        // Diese Funktion ist nur noch für Kompatibilität vorhanden
    },

    updateUrlPreview() {
        const host = document.getElementById('settingHost').value;
        const port = document.getElementById('settingPort').value;
        let displayHost = 'localhost';

        if (host === '0.0.0.0') {
            displayHost = window.location.hostname;
        } else {
            displayHost = 'localhost';
        }

        document.getElementById('settingUrlPreview').textContent = `http://${displayHost}:${port}`;
    },

    toggleIpWhitelistMode() {
        const mode = document.getElementById('settingIpWhitelistMode').value;
        const cloudflareTextarea = document.getElementById('settingCloudflareIps');
        const customContainer = document.getElementById('customIpsContainer');
        const helpText = document.getElementById('ipWhitelistHelp');
        
        const cloudflareIPs = [
            '103.21.244.0/22',
            '103.22.200.0/22',
            '103.31.4.0/22',
            '104.16.0.0/13',
            '104.24.0.0/14',
            '108.162.192.0/18',
            '131.0.72.0/22',
            '141.101.64.0/18',
            '162.158.0.0/15',
            '172.64.0.0/13',
            '173.245.48.0/20',
            '188.114.96.0/20',
            '190.93.240.0/20',
            '197.234.240.0/22',
            '198.41.128.0/17',
            '162.159.0.0/16',
            '172.69.0.0/16',
            '176.7.43.241'
        ];
        
        if (mode === 'custom') {
            cloudflareTextarea.classList.add('hidden');
            customContainer.classList.remove('hidden');
            helpText.textContent = 'Geben Sie eine IP-Adresse oder CIDR-Range pro Zeile ein. Beispiel: 192.168.1.0/24 oder 10.0.0.1';
        } else if (mode === 'cloudflare') {
            cloudflareTextarea.classList.remove('hidden');
            customContainer.classList.add('hidden');
            // Only pre-fill if textarea is empty to avoid overwriting user edits
            if (!cloudflareTextarea.value || cloudflareTextarea.value.trim() === '') {
                cloudflareTextarea.value = cloudflareIPs.join('\n');
            }
            helpText.textContent = 'Service/Tunnel IPs sind vorausgefüllt. Sie können diese bearbeiten oder weitere IPs hinzufügen.';
        } else {
            cloudflareTextarea.classList.add('hidden');
            customContainer.classList.add('hidden');
            helpText.textContent = 'Keine Whitelist - alle Verbindungen sind erlaubt (nur für lokale Netzwerke empfohlen).';
        }
    },

    async addCurrentIpToWhitelist() {
        try {
            const response = await fetch('/api/admin/get-current-ip');
            if (response.ok) {
                const data = await response.json();
                const currentIp = data.ip;
                const customIpsTextarea = document.getElementById('settingCustomIps');
                
                if (currentIp) {
                    const existingIps = customIpsTextarea.value.split('\n').map(ip => ip.trim()).filter(ip => ip !== '');
                    if (!existingIps.includes(currentIp)) {
                        customIpsTextarea.value = existingIps.length > 0 
                            ? customIpsTextarea.value + '\n' + currentIp 
                            : currentIp;
                        this.showNotification('IP hinzugefügt: ' + currentIp, 'success');
                    } else {
                        this.showNotification('IP bereits in der Whitelist', 'info');
                    }
                }
            }
        } catch (error) {
            console.error('Fehler beim Abrufen der aktuellen IP:', error);
            this.showNotification('Fehler beim Abrufen der IP', 'error');
        }
    },

    async addAllActiveIpsToWhitelist() {
        try {
            const response = await fetch('/api/admin/get-all-active-ips');
            if (response.ok) {
                const data = await response.json();
                const activeIps = data.ips;
                const customIpsTextarea = document.getElementById('settingCustomIps');
                
                if (activeIps && activeIps.length > 0) {
                    const existingIps = customIpsTextarea.value.split('\n').map(ip => ip.trim()).filter(ip => ip !== '');
                    let addedCount = 0;
                    
                    activeIps.forEach(ip => {
                        if (ip && !existingIps.includes(ip)) {
                            customIpsTextarea.value = existingIps.length > 0 || addedCount > 0
                                ? customIpsTextarea.value + '\n' + ip
                                : ip;
                            existingIps.push(ip);
                            addedCount++;
                        }
                    });
                    
                    if (addedCount > 0) {
                        this.showNotification(addedCount + ' IPs zur Whitelist hinzugefügt', 'success');
                    } else {
                        this.showNotification('Alle aktiven IPs sind bereits in der Whitelist', 'info');
                    }
                } else {
                    this.showNotification('Keine aktiven Sessions gefunden', 'info');
                }
            }
        } catch (error) {
            console.error('Fehler beim Abrufen aller aktiven IPs:', error);
            this.showNotification('Fehler beim Abrufen der IPs', 'error');
        }
    },

    toggleSecretKeyVisibility() {
        const secretKeyInput = document.getElementById('settingSecretKey');
        const secretKeyIcon = document.getElementById('secretKeyIcon');

        if (secretKeyInput.type === 'password') {
            secretKeyInput.type = 'text';
            secretKeyIcon.classList.remove('fa-eye');
            secretKeyIcon.classList.add('fa-eye-slash');
        } else {
            secretKeyInput.type = 'password';
            secretKeyIcon.classList.remove('fa-eye-slash');
            secretKeyIcon.classList.add('fa-eye');
        }
    },

    async saveSettings() {
        try {
            const settingHost = document.getElementById('settingHost');
            const settingPort = document.getElementById('settingPort');
            const settingPlzValidation = document.getElementById('settingPlzValidation');
            const settingMaxSize = document.getElementById('settingMaxSize');
            const settingSecretKey = document.getElementById('settingSecretKey');
            const settingIpFilterEnabled = document.getElementById('settingIpFilterEnabled');
            const settingDataBaseDir = document.getElementById('settingDataBaseDir');
            const settingBackupDir = document.getElementById('settingBackupDir');
            const settingBackupInterval = document.getElementById('settingBackupInterval');
            const settingBackupTime = document.getElementById('settingBackupTime');
            const settingBackupKeepCount = document.getElementById('settingBackupKeepCount');
            const settingBackupOnStartup = document.getElementById('settingBackupOnStartup');
            const settingOcrScheduleMode = document.getElementById('settingOcrScheduleMode');
            const settingOcrScheduleStart = document.getElementById('settingOcrScheduleStart');
            const settingOcrScheduleEnd = document.getElementById('settingOcrScheduleEnd');
            const settingOcrPageDelay = document.getElementById('settingOcrPageDelay');
            const settingOcrJobDelay = document.getElementById('settingOcrJobDelay');
            const settingSimilarityLimit = document.getElementById('settingSimilarityLimit');
            const settingDuplicateCandidateLimit = document.getElementById('settingDuplicateCandidateLimit');
            const settingSimilarityCandidateLimit = document.getElementById('settingSimilarityCandidateLimit');
            const settingServerName = document.getElementById('settingServerName');
            const settingCloudflareIps = document.getElementById('settingCloudflareIps');
            const settingCustomIps = document.getElementById('settingCustomIps');
            const settingIpWhitelistMode = document.getElementById('settingIpWhitelistMode');
            const settingOcrEnabled = document.getElementById('settingOcrEnabled');
            const settingOcrLang = document.getElementById('settingOcrLang');
            const settingOcrOem = document.getElementById('settingOcrOem');
            const settingOcrPsm = document.getElementById('settingOcrPsm');
            const settingOcrDpi = document.getElementById('settingOcrDpi');
            const settingOcrPreprocessingEnabled = document.getElementById('settingOcrPreprocessingEnabled');
            const settingOcrDenoise = document.getElementById('settingOcrDenoise');
            const settingOcrSharpen = document.getElementById('settingOcrSharpen');
            const settingOcrDeskew = document.getElementById('settingOcrDeskew');
            const settingOcrContrastEnhance = document.getElementById('settingOcrContrastEnhance');
            const settingOcrBinarize = document.getElementById('settingOcrBinarize');
            const settingRequestLimitEnabled = document.getElementById('settingRequestLimitEnabled');
            const settingMaxRequestsPerMinute = document.getElementById('settingMaxRequestsPerMinute');
            const settingSimilarityEnabled = document.getElementById('settingSimilarityEnabled');
            const settingAutoArchive = document.getElementById('settingAutoArchive');
            const settingAgeValue = document.getElementById('settingAgeValue');
            const settingAgeUnit = document.getElementById('settingAgeUnit');
            const settingUnusedValue = document.getElementById('settingUnusedValue');
            const settingUnusedUnit = document.getElementById('settingUnusedUnit');
            const settingRunInterval = document.getElementById('settingRunInterval');
            const settingArchiveLogic = document.getElementById('settingArchiveLogic');
            const settingArchiveScheduleMode = document.getElementById('settingArchiveScheduleMode');
            const settingArchiveScheduleStart = document.getElementById('settingArchiveScheduleStart');
            const settingArchiveScheduleEnd = document.getElementById('settingArchiveScheduleEnd');

            let cloudflareIps = [];
            let customIps = [];
            const whitelistMode = settingIpWhitelistMode ? settingIpWhitelistMode.value : 'none';
            
            // Always save both lists separately
            if (settingCloudflareIps) {
                cloudflareIps = settingCloudflareIps.value.split('\n').map(ip => ip.trim()).filter(ip => ip !== '');
            }
            if (settingCustomIps) {
                customIps = settingCustomIps.value.split('\n').map(ip => ip.trim()).filter(ip => ip !== '');
            }

            const body = {
                server: {
                    host: settingHost ? settingHost.value : '127.0.0.1',
                    port: settingPort ? parseInt(settingPort.value) : 8080,
                    plz_validation_enabled: settingPlzValidation ? settingPlzValidation.checked : true
                },
                security: {
                    secret_key: settingSecretKey ? settingSecretKey.value : '',
                    max_login_attempts: settingMaxLoginAttempts ? parseInt(settingMaxLoginAttempts.value) : 5,
                    rate_limit_window_minutes: settingRateLimitWindow ? parseInt(settingRateLimitWindow.value) : 15,
                    ip_whitelist_mode: whitelistMode,
                    cloudflare_ips: cloudflareIps,
                    custom_ips: customIps
                },
                upload: {
                    max_file_size_mb: settingMaxSize ? parseInt(settingMaxSize.value) : 50
                },
                paths: {
                    data_base_dir: settingDataBaseDir ? settingDataBaseDir.value : './Speicher',
                    backup_dir: settingBackupDir ? settingBackupDir.value : './Backups'
                },
                backup: {
                    interval: settingBackupInterval ? settingBackupInterval.value : 'daily',
                    time: settingBackupTime ? settingBackupTime.value : '00:00',
                    keep_count: settingBackupKeepCount ? parseInt(settingBackupKeepCount.value) : 5,
                    backup_on_startup: settingBackupOnStartup ? settingBackupOnStartup.checked : false
                },
                ocr: {
                    enabled: settingOcrEnabled ? settingOcrEnabled.checked : true,
                    lang: settingOcrLang ? settingOcrLang.value : 'deu+eng',
                    oem: settingOcrOem ? settingOcrOem.value : '3',
                    psm: settingOcrPsm ? settingOcrPsm.value : '6',
                    dpi: settingOcrDpi ? parseInt(settingOcrDpi.value) : 300,
                    schedule_mode: settingOcrScheduleMode ? settingOcrScheduleMode.value : 'always',
                    schedule_start: settingOcrScheduleStart ? settingOcrScheduleStart.value : '20:00',
                    schedule_end: settingOcrScheduleEnd ? settingOcrScheduleEnd.value : '06:00',
                    page_delay_seconds: settingOcrPageDelay ? parseFloat(settingOcrPageDelay.value) : 0.5,
                    job_delay_seconds: settingOcrJobDelay ? parseFloat(settingOcrJobDelay.value) : 1.0,
                    preprocessing: {
                        enabled: settingOcrPreprocessingEnabled ? settingOcrPreprocessingEnabled.checked : true,
                        denoise: settingOcrDenoise ? settingOcrDenoise.checked : true,
                        sharpen: settingOcrSharpen ? settingOcrSharpen.checked : true,
                        deskew: settingOcrDeskew ? settingOcrDeskew.checked : true,
                        contrast_enhance: settingOcrContrastEnhance ? settingOcrContrastEnhance.checked : true,
                        binarize: settingOcrBinarize ? settingOcrBinarize.checked : false
                    }
                },
                search: {
                    enabled: settingSimilarityEnabled ? settingSimilarityEnabled.checked : true,
                    similarity_limit: settingSimilarityLimit ? parseInt(settingSimilarityLimit.value) : 20,
                    duplicate_candidate_limit: settingDuplicateCandidateLimit ? parseInt(settingDuplicateCandidateLimit.value) : 100,
                    similarity_candidate_limit: settingSimilarityCandidateLimit ? parseInt(settingSimilarityCandidateLimit.value) : 200
                },
                network: {
                    request_limit_enabled: settingRequestLimitEnabled ? settingRequestLimitEnabled.checked : false,
                    max_requests_per_minute: settingMaxRequestsPerMinute ? parseInt(settingMaxRequestsPerMinute.value) : 100,
                    block_duration_seconds: settingBlockDurationSeconds ? parseInt(settingBlockDurationSeconds.value) : 60
                },
                archive: {
                    auto_archive: settingAutoArchive ? settingAutoArchive.checked : false,
                    logic: settingArchiveLogic ? settingArchiveLogic.value : 'and',
                    schedule_mode: settingArchiveScheduleMode ? settingArchiveScheduleMode.value : 'always',
                    schedule_start: settingArchiveScheduleStart ? settingArchiveScheduleStart.value : '20:00',
                    schedule_end: settingArchiveScheduleEnd ? settingArchiveScheduleEnd.value : '06:00',
                    age_days: 0,
                    age_months: 0,
                    age_years: 0,
                    unused_days: 0,
                    unused_months: 0,
                    unused_years: 0,
                    run_interval: settingRunInterval ? settingRunInterval.value : 'daily'
                },
                duplicate_threshold: document.getElementById('settingDuplicateThreshold') ? parseFloat(document.getElementById('settingDuplicateThreshold').value) / 100 : 0.5,
                similarity_weights: {
                    title: parseFloat(document.getElementById('weightTitle').value),
                    content: parseFloat(document.getElementById('weightContent').value),
                    address: parseFloat(document.getElementById('weightAddress').value),
                    hashtags: parseFloat(document.getElementById('weightHashtags').value),
                    category: parseFloat(document.getElementById('weightCategory').value),
                    border_color: parseFloat(document.getElementById('weightBorderColor').value),
                    status: parseFloat(document.getElementById('weightStatus').value),
                    attachments: parseFloat(document.getElementById('weightAttachments').value),
                    ocr_text: parseFloat(document.getElementById('weightOcrText').value),
                    creation_date: parseFloat(document.getElementById('weightCreationDate').value),
                    update_date: parseFloat(document.getElementById('weightUpdateDate').value)
                },
                ip_filter_enabled: settingIpFilterEnabled ? (settingIpFilterEnabled.checked ? 'true' : 'false') : 'false',
                server_name: settingServerName ? settingServerName.value : ''
            };

            // Convert age value + unit to days/months/years
            if (settingAgeValue && settingAgeUnit) {
                const ageValue = parseInt(settingAgeValue.value) || 0;
                const ageUnit = settingAgeUnit.value;
                if (ageUnit === 'days') {
                    body.archive.age_days = ageValue;
                    body.archive.age_months = 0;
                    body.archive.age_years = 0;
                } else if (ageUnit === 'months') {
                    body.archive.age_days = 0;
                    body.archive.age_months = ageValue;
                    body.archive.age_years = 0;
                } else if (ageUnit === 'years') {
                    body.archive.age_days = 0;
                    body.archive.age_months = 0;
                    body.archive.age_years = ageValue;
                }
            } else {
                body.archive.age_days = 365;
                body.archive.age_months = 0;
                body.archive.age_years = 0;
            }

            // Convert unused value + unit to days/months/years
            if (settingUnusedValue && settingUnusedUnit) {
                const unusedValue = parseInt(settingUnusedValue.value) || 0;
                const unusedUnit = settingUnusedUnit.value;
                if (unusedUnit === 'days') {
                    body.archive.unused_days = unusedValue;
                    body.archive.unused_months = 0;
                    body.archive.unused_years = 0;
                } else if (unusedUnit === 'months') {
                    body.archive.unused_days = 0;
                    body.archive.unused_months = unusedValue;
                    body.archive.unused_years = 0;
                } else if (unusedUnit === 'years') {
                    body.archive.unused_days = 0;
                    body.archive.unused_months = 0;
                    body.archive.unused_years = unusedValue;
                }
            } else {
                body.archive.unused_days = 180;
                body.archive.unused_months = 0;
                body.archive.unused_years = 0;
            }

            await this.apiPut('/settings', body);
            this.toast('Einstellungen gespeichert. Neustart erforderlich fuer Pfade/Port.', 'success');
            this.updateUrlPreview();
        } catch (e) {
            this.toast(e.message, 'error');
        }
    },

    async runBackup() {
        let progressInterval = null;
        let currentProgress = 0;
        
        try {
            // Ladebalken bei 0% starten
            this.updateUploadProgress(0, 'Image-Backup wird erstellt...', false, true);
            
            // Simulierter Fortschritt (da Backup auf Server läuft)
            progressInterval = setInterval(() => {
                if (currentProgress < 90) {
                    currentProgress += Math.random() * 5 + 2; // Zunehmen bis 90%
                    if (currentProgress > 90) currentProgress = 90;
                    this.updateUploadProgress(currentProgress, 'Image-Backup wird erstellt...', false, true);
                }
            }, 300);
            
            const result = await this.apiPost('/admin/image-backup/create');
            
            clearInterval(progressInterval);
            
            // Ladebalken auf 100% setzen
            this.updateUploadProgress(100, 'Image-Backup wird erstellt...', true, true);
            
            if (result.success) {
                this.toast(`Image-Backup erfolgreich erstellt! (${result.size_mb} MB)`, 'success');
                // Wenn Backup-Liste offen ist, neu laden
                const container = document.getElementById('snapshotsListContainer');
                if (!container.classList.contains('hidden')) {
                    await this.loadBackups();
                }
            } else {
                throw new Error(result.error || 'Unbekannter Fehler beim Backup');
            }
        } catch (e) {
            if (progressInterval) clearInterval(progressInterval);
            
            // Ladebalken ausblenden bei Fehler
            const panel = document.getElementById('uploadProgressPanel');
            if (panel) panel.classList.add('hidden');
            
            // Speicherplatz-Fehler speziell behandeln mit Alert-Modal
            const errorMsg = e.message || 'Unbekannter Fehler';
            if (errorMsg.includes('Nicht genügend Speicherplatz') || errorMsg.includes('Speicherplatz')) {
                await this.alert('<i class="fas fa-exclamation-triangle"></i> Nicht genügend Speicherplatz', errorMsg);
            } else {
                this.toast('Backup fehlgeschlagen: ' + errorMsg, 'error');
            }
        }
    },

    // ── Sidebar Navigation ───────────────────────────────
    initSidebarNavigation() {
        if (!this.dom.sidebarContentDisplay) return;

        this.dom.sidebarContentDisplay.addEventListener('click', () => this.navigateSidebarDisplay(1));

        if (this.dom.miniCalPrev) {
            this.dom.miniCalPrev.addEventListener('click', (e) => {
                e.stopPropagation();
                this.changeMiniCalendarMonth(-1);
            });
        }
        if (this.dom.miniCalNext) {
            this.dom.miniCalNext.addEventListener('click', (e) => {
                e.stopPropagation();
                this.changeMiniCalendarMonth(1);
            });
        }

        // Initialize console tabs
        if (this.dom.consoleTabs) {
            this.dom.consoleTabs.forEach(tab => {
                tab.addEventListener('click', (e) => {
                    e.stopPropagation();
                    this.switchConsoleTab(tab.dataset.tab);
                });
            });
        }

        // Initialize clock
        this.updateClock();
        this.clockInterval = setInterval(() => this.updateClock(), 1000);

        // Initialize mini calendar
        this.updateMiniCalendar();
    },

    switchConsoleTab(tabName) {
        // Update tab buttons
        this.dom.consoleTabs.forEach(tab => {
            tab.classList.remove('active');
            if (tab.dataset.tab === tabName) {
                tab.classList.add('active');
            }
        });

        // Update log panels
        document.querySelectorAll('.console-logs').forEach(panel => {
            panel.classList.remove('active');
            if (panel.dataset.tab === tabName) {
                panel.classList.add('active');
            }
        });

        // Load content for the active tab
        if (tabName === 'security') {
            this.loadSecurityLogs();
        } else if (tabName === 'system') {
            this.loadSystemLogs();
        } else if (tabName === 'network') {
            this.loadNetworkLogs();
        }
    },

    async loadSystemLogs() {
        try {
            const response = await fetch('/api/auth/security-logs?limit=50&event_type=system');
            if (response.ok) {
                const data = await response.json();
                const systemLogs = document.getElementById('systemConsoleLogs');
                if (systemLogs) {
                    if (!data.logs || data.logs.length === 0) {
                        systemLogs.innerHTML = '<div class="console-empty">Keine System-Meldungen</div>';
                    } else {
                        systemLogs.innerHTML = data.logs.map(log => {
                            const date = new Date(log.created_at).toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' });
                            const time = new Date(log.created_at).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' });
                            const severityClass = log.severity || 'info';
                            
                            // Zusätzliche Infos
                            let details = '';
                            if (log.ip_address) {
                                details += `<span class="console-log-detail">IP: ${this.escapeHtml(log.ip_address)}</span>`;
                            }
                            if (log.username) {
                                details += `<span class="console-log-detail">User: ${this.escapeHtml(log.username)}</span>`;
                            }
                            
                            return `
                                <div class="console-log-entry ${severityClass}">
                                    <span class="console-log-time">${date} ${time}</span>
                                    <span class="console-log-message">${this.escapeHtml(log.message)}</span>
                                    ${details ? `<div class="console-log-details">${details}</div>` : ''}
                                </div>
                            `;
                        }).join('');
                    }
                }
            }
        } catch (error) {
            console.error('Fehler beim Laden der System Logs:', error);
        }
    },

    async loadNetworkLogs() {
        try {
            const response = await fetch('/api/auth/security-logs?limit=50&event_type=network');
            if (response.ok) {
                const data = await response.json();
                const networkLogs = document.getElementById('networkConsoleLogs');
                if (networkLogs) {
                    if (!data.logs || data.logs.length === 0) {
                        networkLogs.innerHTML = '<div class="console-empty">Keine Netzwerk-Meldungen</div>';
                    } else {
                        networkLogs.innerHTML = data.logs.map(log => {
                            const date = new Date(log.created_at).toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' });
                            const time = new Date(log.created_at).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' });
                            const severityClass = log.severity || 'info';
                            
                            // Zusätzliche Infos
                            let details = '';
                            if (log.ip_address) {
                                details += `<span class="console-log-detail">IP: ${this.escapeHtml(log.ip_address)}</span>`;
                            }
                            if (log.username) {
                                details += `<span class="console-log-detail">User: ${this.escapeHtml(log.username)}</span>`;
                            }
                            
                            return `
                                <div class="console-log-entry ${severityClass}">
                                    <span class="console-log-time">${date} ${time}</span>
                                    <span class="console-log-message">${this.escapeHtml(log.message)}</span>
                                    ${details ? `<div class="console-log-details">${details}</div>` : ''}
                                </div>
                            `;
                        }).join('');
                    }
                }
            }
        } catch (error) {
            console.error('Fehler beim Laden der Network Logs:', error);
        }
    },

    navigateSidebarDisplay(direction) {
        this.sidebarDisplayIndex += direction;
        if (this.sidebarDisplayIndex < 0) {
            this.sidebarDisplayIndex = this.sidebarDisplays.length - 1;
        } else if (this.sidebarDisplayIndex >= this.sidebarDisplays.length) {
            this.sidebarDisplayIndex = 0;
        }
        this.updateSidebarDisplay();
    },

    updateSidebarDisplay() {
        const displayType = this.sidebarDisplays[this.sidebarDisplayIndex];
        
        this.dom.sidebarDisplayItems.forEach(item => {
            item.classList.remove('active');
            if (item.dataset.display === displayType) {
                item.classList.add('active');
            }
        });

        // Start/stop clock based on visibility
        if (displayType === 'clock') {
            if (!this.clockInterval) {
                this.updateClock();
                this.clockInterval = setInterval(() => this.updateClock(), 1000);
            }
        } else {
            if (this.clockInterval) {
                clearInterval(this.clockInterval);
                this.clockInterval = null;
            }
        }

        // Update mini calendar when switching to it
        if (displayType === 'calendar') {
            this.updateMiniCalendar();
        }

        // Load security logs when switching to console
        if (displayType === 'console') {
            this.loadSecurityLogs();
            if (!this.securityLogsInterval) {
                this.securityLogsInterval = setInterval(() => this.loadSecurityLogs(), 30000); // Refresh alle 30 Sekunden
            }
        } else {
            if (this.securityLogsInterval) {
                clearInterval(this.securityLogsInterval);
                this.securityLogsInterval = null;
            }
        }
    },

    async loadSecurityLogs() {
        try {
            const response = await fetch('/api/auth/security-logs?limit=50&event_type=security');
            if (response.ok) {
                const data = await response.json();
                this.displaySecurityLogs(data.logs || []);
            }
        } catch (error) {
            console.error('Fehler beim Laden der Security Logs:', error);
        }
    },

    displaySecurityLogs(logs) {
        if (!this.dom.securityConsoleLogs) return;

        if (!logs || logs.length === 0) {
            this.dom.securityConsoleLogs.innerHTML = '<div class="console-empty">Keine Warnmeldungen</div>';
            return;
        }

        this.dom.securityConsoleLogs.innerHTML = logs.map(log => {
            const date = new Date(log.created_at).toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' });
            const time = new Date(log.created_at).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' });
            const severityClass = log.severity || 'warning';
            
            // Zusätzliche Infos
            let details = '';
            if (log.ip_address) {
                details += `<span class="console-log-detail">IP: ${this.escapeHtml(log.ip_address)}</span>`;
            }
            if (log.username) {
                details += `<span class="console-log-detail">User: ${this.escapeHtml(log.username)}</span>`;
            }
            
            return `
                <div class="console-log-entry ${severityClass}">
                    <span class="console-log-time">${date} ${time}</span>
                    <span class="console-log-message">${this.escapeHtml(log.message)}</span>
                    ${details ? `<div class="console-log-details">${details}</div>` : ''}
                </div>
            `;
        }).join('');
    },

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    },

    updateClock() {
        const now = new Date();
        const hours = now.getHours();
        const minutes = now.getMinutes();
        const seconds = now.getSeconds();

        // Calculate angles for clock hands
        const hourAngle = (hours % 12) * 30 + minutes * 0.5;
        const minuteAngle = minutes * 6 + seconds * 0.1;
        const secondAngle = seconds * 6;

        if (this.dom.clockHour) {
            this.dom.clockHour.style.transform = `rotate(${hourAngle}deg)`;
        }
        if (this.dom.clockMinute) {
            this.dom.clockMinute.style.transform = `rotate(${minuteAngle}deg)`;
        }
        if (this.dom.clockSecond) {
            this.dom.clockSecond.style.transform = `rotate(${secondAngle}deg)`;
        }

        // Update digital time
        if (this.dom.digitalTime) {
            const timeStr = `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
            this.dom.digitalTime.textContent = timeStr;
        }
    },

    changeMiniCalendarMonth(direction) {
        this.miniCalendarDate.setMonth(this.miniCalendarDate.getMonth() + direction);
        this.updateMiniCalendar();
    },

    updateMiniCalendar() {
        if (!this.dom.miniCalMonth || !this.dom.miniCalGrid) return;

        const year = this.miniCalendarDate.getFullYear();
        const month = this.miniCalendarDate.getMonth();
        const today = new Date();

        // Update month label
        const monthNames = ['Januar', 'Februar', 'März', 'April', 'Mai', 'Juni', 
                           'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember'];
        this.dom.miniCalMonth.textContent = `${monthNames[month]} ${year}`;

        // Clear grid
        this.dom.miniCalGrid.innerHTML = '';

        // Add weekday headers
        const weekdays = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So'];
        weekdays.forEach(day => {
            const dayEl = document.createElement('div');
            dayEl.className = 'mini-cal-weekday';
            dayEl.textContent = day;
            this.dom.miniCalGrid.appendChild(dayEl);
        });

        // Get first day of month and number of days
        const firstDay = new Date(year, month, 1);
        const lastDay = new Date(year, month + 1, 0);
        const daysInMonth = lastDay.getDate();
        
        // Adjust for Monday-based week (0 = Sunday in JS, but we want Monday = 0)
        let startDay = firstDay.getDay() - 1;
        if (startDay < 0) startDay = 6;

        // Add empty cells for days before the first day
        for (let i = 0; i < startDay; i++) {
            const emptyEl = document.createElement('div');
            emptyEl.className = 'mini-cal-day empty';
            this.dom.miniCalGrid.appendChild(emptyEl);
        }

        // Add days
        for (let day = 1; day <= daysInMonth; day++) {
            const dayEl = document.createElement('div');
            dayEl.className = 'mini-cal-day';
            dayEl.textContent = day;

            // Check if today
            if (year === today.getFullYear() && month === today.getMonth() && day === today.getDate()) {
                dayEl.classList.add('today');
            }

            // Add click handler to navigate to main calendar
            dayEl.addEventListener('click', (e) => {
                e.stopPropagation(); // Prevent sidebar navigation
                this.calendarDate = new Date(year, month, day);
                this.showSection('calendar');
                this.renderCalendar();
                // Select the day and show reminders
                const dateStr = `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
                this.selectCalendarDay(dateStr);
            });

            this.dom.miniCalGrid.appendChild(dayEl);
        }
    },

    async toggleBackupsList() {
        const container = document.getElementById('snapshotsListContainer');
        if (container.classList.contains('hidden')) {
            container.classList.remove('hidden');
            await this.loadBackups();
        } else {
            container.classList.add('hidden');
        }
    },

    formatBackupDate(timestampStr) {
        // Konvertiert YYYYMMDD_HHMMSS oder ISO-String zu DD.MM.YYYY HH:MM:SS
        let date;
        
        if (timestampStr.includes('_')) {
            // Format: YYYYMMDD_HHMMSS
            const year = parseInt(timestampStr.substring(0, 4), 10);
            const month = parseInt(timestampStr.substring(4, 6), 10) - 1; // Monate sind 0-basiert
            const day = parseInt(timestampStr.substring(6, 8), 10);
            const hour = parseInt(timestampStr.substring(9, 11), 10);
            const minute = parseInt(timestampStr.substring(11, 13), 10);
            const second = parseInt(timestampStr.substring(13, 15), 10);
            date = new Date(year, month, day, hour, minute, second);
        } else {
            // ISO-Format
            date = new Date(timestampStr);
        }
        
        const pad = (num) => num.toString().padStart(2, '0');
        return `${pad(date.getDate())}.${pad(date.getMonth() + 1)}.${date.getFullYear()} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
    },

    async loadBackups() {
        try {
            this.toast('Lade Image-Backups...', 'info');
            const result = await this.apiGet('/admin/image-backup/list');
            const listEl = document.getElementById('snapshotsList');
            
            if (!result.backups || result.backups.length === 0) {
                listEl.innerHTML = '<p class="text-muted" style="margin:8px 0;">Keine Image-Backups verfügbar.</p>';
                this.toast('Keine Image-Backups gefunden.', 'info');
                return;
            }

            listEl.innerHTML = '';
            result.backups.forEach(backup => {
                const item = document.createElement('div');
                item.className = 'snapshot-item';

                const formattedDate = backup.created_at ? new Date(backup.created_at).toLocaleString('de-DE') : backup.timestamp;
                
                const infoDiv = document.createElement('div');
                infoDiv.innerHTML = `
                    <div style="font-weight: bold;">Image-Backup vom ${formattedDate}</div>
                    <div style="font-size: 0.85rem; color: var(--text-muted);">
                        <i class="fas fa-file-archive"></i> ${backup.size_mb} MB | 
                        <i class="fas fa-cube"></i> ${backup.items_count} Dateien | 
                        <i class="fas fa-code-branch"></i> v${backup.version}
                    </div>
                `;

                const btnRestore = document.createElement('button');
                btnRestore.className = 'btn btn-warning btn-sm';
                btnRestore.innerHTML = '<i class="fas fa-undo"></i> Wiederherstellen';
                btnRestore.onclick = () => this.restoreSnapshot(backup.filename);

                item.appendChild(infoDiv);
                item.appendChild(btnRestore);
                listEl.appendChild(item);
            });

            this.toast('Image-Backups geladen!', 'success');
        } catch (e) {
            this.toast('Fehler beim Laden der Image-Backups: ' + e.message, 'error');
        }
    },

    async restoreSnapshot(filename) {
        // Datum aus Dateinamen extrahieren
        const match = filename.match(/ORDAMA_ImageBackup_(\d{8})_(\d{6})\.zip/);
        let formattedDate = 'Unbekannt';
        if (match) {
            const dateStr = match[1];
            const timeStr = match[2];
            const year = dateStr.substring(0, 4);
            const month = dateStr.substring(4, 6);
            const day = dateStr.substring(6, 8);
            const hour = timeStr.substring(0, 2);
            const minute = timeStr.substring(2, 4);
            const second = timeStr.substring(4, 6);
            formattedDate = `${day}.${month}.${year} ${hour}:${minute}:${second}`;
        }
        
        document.getElementById('restoreModalMessage').innerHTML = `Möchten Sie wirklich den Image-Backup vom ${formattedDate} wiederherstellen?`;
        document.getElementById('restoreModalOverlay').classList.add('show');
        
        // Bind confirm button mit Filename als Data-Attribut
        const confirmBtn = document.getElementById('restoreConfirmBtn');
        confirmBtn.dataset.timestamp = filename;
        confirmBtn.onclick = () => this.doRestore();
    },

    closeRestoreModal() {
        document.getElementById('restoreModalOverlay').classList.remove('show');
    },

    async doRestore() {
        const confirmBtn = document.getElementById('restoreConfirmBtn');
        const filename = confirmBtn.dataset.timestamp;
        
        if (!filename) return;
        
        this.closeRestoreModal();
        
        let progressInterval = null;
        let currentProgress = 0;
        
        try {
            // Ladebalken bei 0% starten
            this.updateUploadProgress(0, 'Image-Backup Wiederherstellung läuft...', false, true);
            this.toast('Image-Backup Wiederherstellung läuft...', 'info', 10000);
            
            // Simulierter Fortschritt (da Restore auf Server läuft)
            progressInterval = setInterval(() => {
                if (currentProgress < 90) {
                    currentProgress += Math.random() * 5 + 2; // Zunehmen bis 90%
                    if (currentProgress > 90) currentProgress = 90;
                    this.updateUploadProgress(currentProgress, 'Image-Backup Wiederherstellung läuft...', false, true);
                }
            }, 300);
            
            const result = await this.apiPost('/admin/image-backup/restore', {
                filename: filename,
                overwrite: true
            });
            
            clearInterval(progressInterval);
            
            // Ladebalken auf 100% setzen
            this.updateUploadProgress(100, 'Image-Backup Wiederherstellung läuft...', true, true);
            
            if (result.success) {
                this.toast('Image-Backup Wiederherstellung erfolgreich! Bitte Server manuell neu starten und sich neu anmelden.', 'success', 15000);
            } else {
                throw new Error(result.error || 'Unbekannter Fehler');
            }
        } catch (e) {
            if (progressInterval) clearInterval(progressInterval);
            
            // Ladebalken ausblenden bei Fehler
            const panel = document.getElementById('uploadProgressPanel');
            if (panel) panel.classList.add('hidden');
            
            this.toast('Fehler bei der Wiederherstellung: ' + e.message, 'error');
        }
    },

    // ── Folder Browser ─────────────────────────────
    openFolderBrowser(targetId) {
        this.folderBrowserTargetId = targetId;
        const currentPath = document.getElementById(targetId).value;
        this.loadFolderList(currentPath);
        document.getElementById('folderBrowserModalOverlay').classList.add('show');
    },

    closeFolderBrowser() {
        document.getElementById('folderBrowserModalOverlay').classList.remove('show');
    },

    async loadFolderList(path = '') {
        try {
            const data = await this.apiGet(`/admin/browse-folders?path=${encodeURIComponent(path)}`);
            const listEl = document.getElementById('folderBrowserList');
            const pathEl = document.getElementById('folderBrowserCurrentPath');
            
            pathEl.textContent = data.current || (data.is_root ? 'Laufwerke / Root' : '');
            listEl.innerHTML = '';

            // Parent directory
            if (data.parent !== null) {
                const item = document.createElement('div');
                item.className = 'folder-item parent-dir';
                item.innerHTML = `<i class="fas fa-level-up-alt"></i> .. (${data.parent === '' ? 'Laufwerksübersicht' : 'Übergeordneter Ordner'})`;
                item.onclick = () => this.loadFolderList(data.parent);
                listEl.appendChild(item);
            }

            // Subdirectories
            data.folders.forEach(folder => {
                const item = document.createElement('div');
                item.className = 'folder-item';
                const folderPath = data.current ? (data.current.endsWith('\\') || data.current.endsWith('/') ? data.current + folder : data.current + (window.navigator.platform.includes('Win') ? '\\' : '/') + folder) : folder;
                item.innerHTML = `<i class="fas fa-folder"></i> ${folder}`;
                item.onclick = () => this.loadFolderList(folderPath);
                listEl.appendChild(item);
            });

        } catch (e) {
            this.toast(e.message, 'error');
        }
    },

    selectCurrentFolder() {
        const currentPath = document.getElementById('folderBrowserCurrentPath').textContent;
        if (this.folderBrowserTargetId) {
            document.getElementById(this.folderBrowserTargetId).value = currentPath;
        }
        this.closeFolderBrowser();
    },

    async restartServer() {
        if (!await this.confirm('Server neu starten?', 'Die Verbindung wird kurz unterbrochen.', 'Ja, neu starten', 'btn-danger')) return;
        try {
            // Neue URL ermitteln, falls Port/Host geaendert wurden
            const host = document.getElementById('settingHost')?.value || window.location.hostname;
            const port = document.getElementById('settingPort')?.value || window.location.port;
            const newUrl = `http://${host === '0.0.0.0' ? window.location.hostname : host}:${port}`;

            await this.apiPost('/server/restart');
            this.toast('Server wird neu gestartet...', 'warning');
            
            // Nach 5 Sekunden zur neuen URL (oder Login-Seite)
            setTimeout(() => {
                this.logout();
                if (window.location.port !== port || (host !== '0.0.0.0' && window.location.hostname !== host)) {
                    window.location.href = newUrl;
                } else {
                    window.location.reload();
                }
            }, 5000);
        } catch (e) {
            this.toast(e.message, 'error');
        }
    },

    async stopServer() {
        if (!await this.confirm('Server beenden?', 'Der Server wird komplett beendet und muss manuell neu gestartet werden.', 'Ja, beenden', 'btn-danger')) return;
        try {
            await this.apiPost('/server/stop');
            this.toast('Server wird beendet...', 'warning');
            // Nach 2 Sekunden zur Login-Seite
            setTimeout(() => {
                this.logout();
                this.toast('Server wurde beendet. Starten Sie ihn manuell neu.', 'info');
            }, 2000);
        } catch (e) {
            this.toast(e.message, 'error');
        }
    },

    // Cloudflare Tunnel Funktionen
    async loadTunnelConfig() {
        try {
            const data = await this.apiGet('/tunnel/config');
            if (data.config) {
                document.getElementById('tunnelId').value = data.config.tunnel_id || '';
                document.getElementById('tunnelToken').value = data.config.tunnel_token || '';
            }
        } catch (e) {
            console.error('Fehler beim Laden der Tunnel-Konfiguration:', e);
        }
    },

    async saveTunnelConfig() {
        try {
            const config = {
                tunnel_id: document.getElementById('tunnelId').value.trim(),
                tunnel_token: document.getElementById('tunnelToken').value.trim()
            };

            await this.apiPost('/tunnel/config', config);
            this.toast('Tunnel-Konfiguration gespeichert', 'success');
        } catch (e) {
            this.toast(e.message || 'Fehler beim Speichern der Konfiguration', 'error');
        }
    },

    // ── Formular ───────────────────────────
    async loadFormTemplates(showLoading = true) {
        // Wenn manueller Offline-Modus aktiv ist, nicht laden (Overlay wird in showSection angezeigt)
        if (this.manualOfflineMode) {
            console.log('📡 FormTemplates: Manueller Offline-Modus aktiv - Nicht laden');
            return;
        }

        try {
            const data = await this.apiGet('/formulare/vorlagen', showLoading);
            
            // Null-Prüfung für data und vorlagen
            if (!data || !data.vorlagen) {
                console.warn('Vorlagen konnten nicht geladen werden (data oder vorlagen ist null)');
                return;
            }
            
            const tbody = document.getElementById('formTemplatesTableBody');
            if (!tbody) return;
            tbody.innerHTML = '';
            
            data.vorlagen.forEach(v => {
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td><strong>${this.escapeHtml(v.name)}</strong></td>
                    <td>${new Date(v.created_at).toLocaleString('de-DE')}</td>
                    <td class="actions">
                        <button class="btn btn-secondary btn-sm" onclick="App.openFormDesigner(${v.id})" title="Layout bearbeiten">
                            <i class="fas fa-edit"></i> <span class="d-none d-sm-inline">Layout</span>
                        </button>
                        <button class="btn btn-secondary btn-sm" onclick="App.duplicateTemplate(${v.id})" title="Als Vorlage kopieren">
                            <i class="fas fa-copy"></i> <span class="d-none d-sm-inline">Kopieren</span>
                        </button>
                        <button class="btn btn-danger btn-sm" onclick="App.deleteTemplate(${v.id})" title="Löschen">
                            <i class="fas fa-trash"></i>
                        </button>
                    </td>
                `;
                tbody.appendChild(tr);
            });
        } catch (e) {
            this.toast(e.message, 'error');
        }
    },

    async showCreateTemplateModal() {
        document.getElementById('templateName').value = '';
        document.getElementById('templateStructure').value = JSON.stringify({
            width: 800,
            height: 1131,
            elements: []
        }, null, 4);
        
        // Dropdown mit vorhandenen Vorlagen füllen
        try {
            const data = await this.apiGet('/formulare/vorlagen');
            
            // Null-Prüfung für data und vorlagen
            if (!data || !data.vorlagen) {
                console.warn('Vorlagen konnten nicht geladen werden (data oder vorlagen ist null)');
                return;
            }
            
            const select = document.getElementById('templateBaseSelect');
            select.innerHTML = '<option value="">-- Leere Vorlage --</option>';
            data.vorlagen.forEach(v => {
                const opt = document.createElement('option');
                opt.value = v.id;
                opt.textContent = v.name;
                select.appendChild(opt);
            });
        } catch (e) {
            // Wenn keine Vorlagen oder Fehler, einfach lassen
        }
        
        document.getElementById('templateCreateModalOverlay').classList.add('show');
    },

    async onTemplateBaseSelect(templateId) {
        if (!templateId) {
            // Leere Vorlage
            document.getElementById('templateStructure').value = JSON.stringify({
                width: 800,
                height: 1131,
                elements: []
            }, null, 4);
            document.getElementById('templateName').value = '';
            return;
        }
        
        try {
            const data = await this.apiGet('/formulare/vorlagen');
            
            // Null-Prüfung für data und vorlagen
            if (!data || !data.vorlagen) {
                console.warn('Vorlagen konnten nicht geladen werden (data oder vorlagen ist null)');
                return;
            }
            
            const template = data.vorlagen.find(v => v.id === parseInt(templateId));
            if (template) {
                document.getElementById('templateStructure').value = JSON.stringify(template.structure, null, 4);
                document.getElementById('templateName').value = `${template.name} (Kopie)`;
            }
        } catch (e) {
            this.toast(e.message, 'error');
        }
    },

    closeTemplateCreateModal() {
        document.getElementById('templateCreateModalOverlay').classList.remove('show');
    },

    async saveTemplate() {
        const name = document.getElementById('templateName').value.trim();
        let structure;
        try {
            structure = JSON.parse(document.getElementById('templateStructure').value);
        } catch (e) {
            this.toast('Ungültiges JSON-Format', 'error');
            return;
        }

        if (!name) {
            this.toast('Bitte einen Namen angeben', 'error');
            return;
        }

        try {
            await this.apiPost('/formulare/vorlagen', { name, structure });
            this.toast('Vorlage gespeichert', 'success');
            this.closeTemplateCreateModal();
            this.loadFormTemplates();
        } catch (e) {
            this.toast(e.message, 'error');
        }
    },

    async deleteTemplate(id) {
        if (!await this.confirm('Vorlage löschen?', 'Möchten Sie diese Vorlage wirklich löschen?', 'Ja, löschen')) return;
        try {
            await this.apiDelete(`/formulare/vorlagen/${id}`);
            this.toast('Vorlage gelöscht', 'success');
            this.loadFormTemplates();
        } catch (e) {
            this.toast(e.message, 'error');
        }
    },

    async duplicateTemplate(id) {
        try {
            const data = await this.apiGet('/formulare/vorlagen');
            
            // Null-Prüfung für data und vorlagen
            if (!data || !data.vorlagen) {
                console.warn('Vorlagen konnten nicht geladen werden (data oder vorlagen ist null)');
                return;
            }
            
            const original = data.vorlagen.find(v => v.id === id);
            if (!original) {
                this.toast('Vorlage nicht gefunden', 'error');
                return;
            }
            
            const newName = `${original.name} (Kopie)`;
            const response = await this.apiPost('/formulare/vorlagen', {
                name: newName,
                structure: original.structure,
                next_number: original.next_number || 1
            });
            
            this.toast('Vorlage kopiert', 'success');
            this.loadFormTemplates();
            
            if (response && response.vorlage && response.vorlage.id) {
                this.openFormDesigner(response.vorlage.id);
            }
        } catch (e) {
            this.toast(e.message, 'error');
        }
    },

    async showFormSelectionModal() {
        try {
            const data = await this.apiGet('/formulare/vorlagen');
            
            // Null-Prüfung für data und vorlagen
            if (!data || !data.vorlagen) {
                console.warn('Vorlagen konnten nicht geladen werden (data oder vorlagen ist null)');
                this.formTemplatesCache = [];
                return;
            }
            
            this.formTemplatesCache = data.vorlagen || [];
            
            const searchInput = document.getElementById('formSelectSearch');
            if (searchInput) searchInput.value = '';
            
            this.renderFormSelectionList(this.formTemplatesCache);
            document.getElementById('formSelectModalOverlay').classList.add('show');
        } catch (e) {
            this.toast(e.message, 'error');
        }
    },

    renderFormSelectionList(vorlagen) {
        const list = document.getElementById('formSelectList');
        list.innerHTML = '';
        
        if (vorlagen.length === 0) {
            list.innerHTML = '<div class="p-3 text-center text-muted">Keine passenden Vorlagen gefunden.</div>';
        } else {
            vorlagen.forEach(v => {
                const btn = document.createElement('button');
                btn.className = 'list-group-item list-group-item-action';
                btn.innerHTML = `<i class="fas fa-file-invoice"></i> ${this.escapeHtml(v.name)}`;
                btn.onclick = () => {
                    this.closeFormSelectModal();
                    this.showFormFillModal(v);
                };
                list.appendChild(btn);
            });
        }
    },

    filterFormSelection(query) {
        if (!this.formTemplatesCache) return;
        const q = query.toLowerCase().trim();
        const filtered = this.formTemplatesCache.filter(v => 
            v.name.toLowerCase().includes(q)
        );
        this.renderFormSelectionList(filtered);
    },

    closeFormSelectModal() {
        const modal = document.getElementById('formSelectModal');
        const btn = document.getElementById('formSelectFullscreen');
        const icon = btn.querySelector('i');
        
        modal.classList.remove('fullscreen');
        icon.className = 'fas fa-expand';
        btn.title = 'Vollbildmodus';
        
        document.getElementById('formSelectModalOverlay').classList.remove('show');
    },

    showFormFillModal(template) {
        this.currentTemplate = template;
        this.formFillHasChanges = false;
        document.getElementById('formFillTitle').textContent = template.name;
        const body = document.getElementById('formFillBody');
        body.innerHTML = '';
        
        const page = document.createElement('div');
        page.className = 'form-filler-page';
        page.style.width = (template.structure.width || 800) + 'px';
        page.style.height = (template.structure.height || 1131) + 'px';
        
        if (template.structure.bg) {
            page.style.backgroundImage = `url(${template.structure.bg})`;
            
            if (template.structure.bgSize === 'manual') {
                page.style.backgroundSize = `${template.structure.bgW || 800}px ${template.structure.bgH || 1131}px`;
                page.style.backgroundPosition = `${template.structure.bgX || 0}px ${template.structure.bgY || 0}px`;
            } else {
                page.style.backgroundSize = template.structure.bgSize || 'contain';
                page.style.backgroundPosition = template.structure.bgPos || 'center';
            }
            
            page.style.backgroundRepeat = 'no-repeat';
            page.classList.remove('no-bg');
        } else {
            page.classList.add('no-bg');
        }
        
        page.onclick = () => {
            if (page.classList.contains('no-bg')) {
                document.getElementById('formFillBgUpload').click();
            }
        };
        
        (template.structure.elements || []).forEach(el => {
            const style = `position: absolute; left: ${el.x}px; top: ${el.y}px; font-family: ${el.fontFamily || 'inherit'}; `;
            
            if (el.type === 'text' || el.type === 'bullet') {
                const div = document.createElement('div');
                div.style = style + `font-size: ${el.fontSize || '14px'}; font-weight: ${el.bold ? 'bold' : 'normal'}; font-style: ${el.italic ? 'italic' : 'normal'}; white-space: nowrap; pointer-events: none; text-align: ${el.textAlign || 'center'};`;
                div.textContent = el.content || (el.type === 'bullet' ? '•' : '');
                if (el.type === 'bullet') {
                    div.style.width = (el.width || 30) + 'px';
                    div.style.height = (el.height || 30) + 'px';
                    div.style.display = 'flex';
                    div.style.alignItems = 'center';
                    div.style.justifyContent = el.textAlign || 'center';
                }
                page.appendChild(div);
            } else if (el.type === 'field' || el.type === 'date' || el.type === 'autonum') {
                const input = document.createElement('input');
                input.className = 'filler-input form-fill-input';
                input.style = style + `width: ${el.width || 100}px; font-size: ${el.fontSize || '14px'}; font-weight: ${el.bold ? 'bold' : 'normal'}; font-style: ${el.italic ? 'italic' : 'normal'}; background: transparent; text-align: ${el.textAlign || 'center'};`;
                input.dataset.id = el.id;
                if (el.content) input.placeholder = el.content;
                input.oninput = () => this.formFillHasChanges = true;
                
                // Unterstreichung anwenden
                if (el.hasUnderline) {
                    input.style.borderBottom = '1px solid #333';
                    // Falls eine spezifische Breite gewünscht ist, nutzen wir ein Wrapper-Div oder Background-Gradient?
                    // Einfacher: Wenn underlineWidth < 100%, nutzen wir ein Hintergrundbild als Linie
                    if (el.underlineWidth && el.underlineWidth !== '100%') {
                        input.style.borderBottom = 'none';
                        input.style.backgroundImage = `linear-gradient(to right, #333 ${el.underlineWidth}, transparent ${el.underlineWidth})`;
                        input.style.backgroundSize = `100% 1px`;
                        input.style.backgroundRepeat = 'no-repeat';
                        input.style.backgroundPosition = 'bottom';
                    }
                } else {
                    input.style.borderBottom = 'none';
                }

                // Automatisches Datum für Datumsfelder
                if (el.type === 'date') {
                    const today = new Date();
                    const dd = String(today.getDate()).padStart(2, '0');
                    const mm = String(today.getMonth() + 1).padStart(2, '0');
                    const yyyy = today.getFullYear();
                    input.value = `${dd}.${mm}.${yyyy}`;
                }

                // Auto-Nummer Feld (Read-Only)
                if (el.type === 'autonum') {
                    input.value = template.next_number || 1;
                    input.readOnly = true;
                    input.style.border = 'none';
                    if (el.hasUnderline) {
                        input.style.borderBottom = '1px solid #ccc';
                        if (el.underlineWidth && el.underlineWidth !== '100%') {
                            input.style.borderBottom = 'none';
                            input.style.backgroundImage = `linear-gradient(to right, #ccc ${el.underlineWidth}, transparent ${el.underlineWidth})`;
                            input.style.backgroundSize = `100% 1px`;
                            input.style.backgroundRepeat = 'no-repeat';
                            input.style.backgroundPosition = 'bottom';
                        }
                    }
                    input.style.color = 'inherit';
                    input.title = "Diese Nummer wird beim Speichern automatisch vergeben.";
                }
                
                page.appendChild(input);
            } else if (el.type === 'line') {
                const line = document.createElement('div');
                const isVert = el.orientation === 'vertical';
                line.style = style + `background: #333; width: ${isVert ? (el.thickness || '1px') : (el.length || 100) + 'px'}; height: ${isVert ? (el.length || 100) + 'px' : (el.thickness || '1px')}; pointer-events: none;`;
                page.appendChild(line);
            } else if (el.type === 'box') {
                const box = document.createElement('div');
                box.style = style + `width: ${el.width || 100}px; height: ${el.height || 100}px; border: ${el.thickness || '1px'} solid #333; pointer-events: none;`;
                page.appendChild(box);
            } else if (el.type === 'checkbox') {
                const container = document.createElement('div');
                container.style = style + `width: ${el.width || 24}px; height: ${el.height || 24}px; display: flex; align-items: center; justify-content: center; cursor: pointer;`;
                
                const checkboxWrapper = document.createElement('div');
                checkboxWrapper.style = `
                    width: ${el.width || 24}px; 
                    height: ${el.height || 24}px; 
                    border: 2px solid #333; 
                    border-radius: 3px; 
                    background: white; 
                    display: flex; 
                    align-items: center; 
                    justify-content: center;
                `;
                
                const checkSvg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
                checkSvg.setAttribute('width', '16');
                checkSvg.setAttribute('height', '16');
                checkSvg.setAttribute('viewBox', '0 0 16 16');
                checkSvg.setAttribute('fill', 'none');
                checkSvg.classList.add('hidden');
                
                const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
                path.setAttribute('d', 'M3 8L6 11L13 4');
                path.setAttribute('stroke', '#000000');
                path.setAttribute('stroke-width', '2.5');
                path.setAttribute('stroke-linecap', 'round');
                path.setAttribute('stroke-linejoin', 'round');
                checkSvg.appendChild(path);
                
                checkboxWrapper.appendChild(checkSvg);
                container.appendChild(checkboxWrapper);
                
                const input = document.createElement('input');
                input.type = 'hidden';
                input.className = 'form-fill-input';
                input.dataset.id = el.id;
                input.value = 'false';
                container.appendChild(input);
                
                container.onclick = (e) => {
                    e.stopPropagation();
                    const isChecked = input.value === 'true';
                    input.value = isChecked ? 'false' : 'true';
                    checkSvg.classList.toggle('hidden', isChecked);
                    this.formFillHasChanges = true;
                };
                page.appendChild(container);
            } else if (el.type === 'image') {
                const img = document.createElement('div');
                img.style = style + `width: ${el.width || 100}px; height: ${el.height || 100}px; background-image: url(${el.content}); background-size: 100% 100%; background-repeat: no-repeat; pointer-events: none;`;
                page.appendChild(img);
            } else if (el.type === 'signature') {
                const sig = document.createElement('div');
                const w = el.width || 200;
                const h = el.height || 60;
                sig.style = style + `width: ${w}px; height: ${h}px; border-bottom: 1px solid #333; display: flex; flex-direction: column; align-items: center; justify-content: flex-end; overflow: hidden; padding-bottom: 5px;`;
                if (this.currentUser && this.currentUser.signature) {
                    const img = document.createElement('img');
                    img.src = this.currentUser.signature;
                    img.style.width = '100%';
                    img.style.height = '100%';
                    img.style.objectFit = 'contain';
                    sig.appendChild(img);
                } else {
                    sig.innerHTML = `
                        <svg width="${Math.min(w - 20, 180)}" height="${Math.min(h - 15, 45)}" viewBox="0 0 180 45" style="opacity: 0.3;">
                            <path d="M10 35 Q20 15 35 28 Q50 40 65 25 Q80 10 95 32 Q110 50 125 28 Q140 12 155 35 Q170 55 175 30" 
                                  fill="none" stroke="#666" stroke-width="2.2" stroke-linecap="round"/>
                        </svg>
                        <div style="font-size: 8px; color: #999; margin-top: 2px;">Unterschrift</div>
                    `;
                }
                page.appendChild(sig);
            } else if (el.type === 'table') {
                const container = document.createElement('div');
                container.style = style + `width: ${el.width || 300}px; height: ${el.height || 100}px; font-size: ${el.fontSize || '14px'}; font-weight: ${el.bold ? 'bold' : 'normal'}; font-style: ${el.italic ? 'italic' : 'normal'};`;
                
                let rows = parseInt(el.rows);
                let cols = parseInt(el.cols);
                if (isNaN(rows)) rows = 3;
                if (isNaN(cols)) cols = 3;
                const cellConfigs = el.cellConfigs || {};
                const colWidths = el.colWidths || [];
                
                if (rows === 0 && cols === 0) {
                    container.style.border = '1px dashed #ccc';
                    page.appendChild(container);
                } else if (rows === 0) {
                    // Only vertical lines
                    let linesHtml = '<div style="width:100%;height:100%;position:relative;border:1px solid #333;">';
                    for (let i = 0; i <= cols; i++) {
                        linesHtml += `<div style="position:absolute;left:${i * 100 / cols}%;top:0;width:1px;height:100%;background:#333;transform:translateX(-50%);"></div>`;
                    }
                    linesHtml += '</div>';
                    container.innerHTML = linesHtml;
                    page.appendChild(container);
                } else if (cols === 0) {
                    // Only horizontal lines
                    let linesHtml = '<div style="width:100%;height:100%;position:relative;border:1px solid #333;">';
                    for (let i = 0; i <= rows; i++) {
                        linesHtml += `<div style="position:absolute;top:${i * 100 / rows}%;left:0;height:1px;width:100%;background:#333;transform:translateY(-50%);"></div>`;
                    }
                    linesHtml += '</div>';
                    container.innerHTML = linesHtml;
                    page.appendChild(container);
                } else {
                    // Normal table
                    let tableHtml = `<table class="form-fill-table" data-id="${el.id}" style="width:100%; height:100%; border-collapse:collapse; border:1px solid #333; background:transparent; table-layout:fixed;">`;
                    for (let r = 0; r < rows; r++) {
                        const rowHeight = (100 / rows) + '%';
                        tableHtml += `<tr style="height: ${rowHeight}">`;
                        for (let c = 0; c < cols; c++) {
                            const cellKey = `${r}-${c}`;
                            const config = cellConfigs[cellKey] || { type: 'input' };
                            const wStyle = colWidths[c] ? `width:${colWidths[c]}%;` : '';
                            
                            let cellStyle = `border:1px solid #333; padding:6px; ${wStyle}; white-space: pre-wrap;`;
                            if (config.bold) cellStyle += ' font-weight:bold;';
                            if (config.italic) cellStyle += ' font-style:italic;';
                            if (config.fontSize) cellStyle += ` font-size:${config.fontSize};`;
                            if (config.fontFamily && config.fontFamily !== 'inherit') cellStyle += ` font-family:${config.fontFamily};`;
                            const cellAlign = config.textAlign || (config.type === 'calc' ? 'right' : 'center');
                            cellStyle += ` text-align:${cellAlign};`;
                            
                            if (config.type === 'calc') {
                                tableHtml += `<td style="border:1px solid #333; padding:2px; background:transparent; font-weight:bold; color:#000000; ${cellStyle}" class="table-calc-cell" data-row="${r}" data-col="${c}">0</td>`;
                            } else if (config.type === 'text') {
                                cellStyle += ' background:rgba(249, 249, 249, 0.2); font-size:12px;';
                                tableHtml += `<td style="${cellStyle}">${config.content || ''}</td>`;
                            } else {
                                tableHtml += `<td style="${cellStyle}"><input type="text" class="table-input" data-row="${r}" data-col="${c}" style="width:100%; border:none; outline:none; background:transparent; font-family:inherit; font-size:inherit; font-weight:inherit; font-style:inherit; text-align:inherit;" oninput="App.handleTableInput(this)"></td>`;
                            }
                        }
                        tableHtml += '</tr>';
                    }
                    tableHtml += '</table>';
                    container.innerHTML = tableHtml;
                    page.appendChild(container);
                }
            }
        });
        
        body.appendChild(page);
        document.getElementById('formFillModalOverlay').classList.add('show');
    },

    async closeFormFillModal() {
        if (this.formFillHasChanges) {
            if (!await this.confirm('Ungespeicherte Änderungen', 'Möchten Sie das Formular wirklich verlassen? Alle Eingaben gehen verloren.', 'Ja, verlassen', 'btn-danger')) {
                return;
            }
        }
        document.getElementById('formFillModalOverlay').classList.remove('show');
    },

    handleTableInput(input) {
        this.formFillHasChanges = true;
        const table = input.closest('table');
        this.calculateTable(table);
    },

    calculateTable(table) {
        if (!this.currentTemplate) return;
        const elId = table.dataset.id;
        const el = this.currentTemplate.structure.elements.find(e => e.id === elId);
        if (!el || !el.cellConfigs) return;

        const calcCells = table.querySelectorAll('.table-calc-cell');
        calcCells.forEach(cell => {
            const r = parseInt(cell.dataset.row);
            const c = parseInt(cell.dataset.col);
            const cellKey = `${r}-${c}`;
            const config = el.cellConfigs[cellKey];
            if (!config || config.type !== 'calc') return;

            let result = 0;
            const op = config.op || '+';
            const dir = config.dir || 'row';
            const mode = config.calcMode || 'auto';

            if (mode === 'manual' && config.formula) {
                // Eigene Formel auswerten (z.B. S1 * S2)
                let formulaStr = config.formula.toUpperCase();
                const row = table.querySelectorAll('tr')[r];
                const allInputs = row.querySelectorAll('.table-input');
                
                // Ersetze S1, S2... durch die Werte aus der aktuellen Zeile
                for (let i = 1; i <= 20; i++) {
                    const pattern = new RegExp(`S${i}\\b`, 'g');
                    if (formulaStr.includes(`S${i}`)) {
                        const input = row.querySelector(`.table-input[data-col="${i-1}"]`);
                        const val = input ? (parseFloat(input.value.replace(',', '.')) || 0) : 0;
                        formulaStr = formulaStr.replace(pattern, val);
                    }
                }

                try {
                    // Vorsichtige Evaluierung der mathematischen Formel
                    // Ersetze Prozentrechnung: x % y -> x * (y/100)
                    if (formulaStr.includes('%')) {
                        formulaStr = formulaStr.replace(/([\d.]+)\s*%\s*([\d.]+)/g, "($1*($2/100))");
                    }
                    
                    // Nur erlaubte Zeichen für eval
                    if (/^[0-9+\-*/().\s]*$/.test(formulaStr)) {
                        result = eval(formulaStr);
                    }
                } catch (err) {
                    console.error("Formel-Fehler:", err);
                    result = 0;
                }
            } else if (dir === 'row') {
                // Alle Eingabefelder in dieser Zeile links von dieser Zelle
                const row = table.querySelectorAll('tr')[r];
                const inputs = row.querySelectorAll('.table-input');
                let first = true;
                inputs.forEach(input => {
                    const colIdx = parseInt(input.dataset.col);
                    if (colIdx < c) {
                        const val = parseFloat(input.value.replace(',', '.')) || 0;
                        if (first) { result = val; first = false; }
                        else {
                            if (op === '+') result += val;
                            else if (op === '-') result -= val;
                            else if (op === '*') result *= val;
                            else if (op === '%') result = result * (val / 100);
                        }
                    }
                });
            } else {
                // Alle Eingabefelder in dieser Spalte oberhalb von dieser Zelle
                const rows = table.querySelectorAll('tr');
                let first = true;
                for (let i = 0; i < r; i++) {
                    const input = rows[i].querySelector(`.table-input[data-col="${c}"]`);
                    if (input) {
                        const val = parseFloat(input.value.replace(',', '.')) || 0;
                        if (first) { result = val; first = false; }
                        else {
                            if (op === '+') result += val;
                            else if (op === '-') result -= val;
                            else if (op === '*') result *= val;
                            else if (op === '%') result = result * (val / 100);
                        }
                    }
                }
            }

            cell.textContent = result.toLocaleString('de-DE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        });
    },

    async submitFilledForm() {
        const inputs = document.querySelectorAll('.form-fill-input');
        const data = {};
        inputs.forEach(input => {
            data[input.dataset.id] = input.value === 'true';
        });

        // Tabellendaten sammeln
        const tables = document.querySelectorAll('.form-fill-table');
        tables.forEach(table => {
            const tableData = [];
            const rows = table.querySelectorAll('tr');
            rows.forEach(row => {
                const rowData = [];
                row.querySelectorAll('td').forEach(td => {
                    const input = td.querySelector('.table-input');
                    if (input) {
                        rowData.push(input.value);
                    } else if (td.classList.contains('table-calc-cell')) {
                        rowData.push(td.textContent);
                    } else {
                        rowData.push(td.textContent);
                    }
                });
                tableData.push(rowData);
            });
            data[table.dataset.id] = tableData;
        });
        
        try {
            // 1. PDF im Browser generieren
            const element = document.querySelector('.form-filler-page');
            if (!element) throw new Error('Formular-Inhalt nicht gefunden');

            this.showLoading(true);
            
            const opt = {
                margin: 0,
                filename: 'formular.pdf',
                image: { type: 'jpeg', quality: 0.98 },
                html2canvas: { 
                    scale: 2, 
                    useCORS: true, 
                    logging: false,
                    allowTaint: true,
                    backgroundColor: '#ffffff'
                },
                jsPDF: { unit: 'px', format: [element.offsetWidth, element.offsetHeight], orientation: 'portrait' }
            };
            
            // PDF als Blob erzeugen
            const pdfBlob = await html2pdf().set(opt).from(element).output('blob');
            
            // 2. PDF an das Backend senden
            const formData = new FormData();
            formData.append('file', pdfBlob, `Formular_${this.currentTemplate.name.replace(/\s+/g, '_')}_${new Date().getTime()}.pdf`);
            formData.append('record_id', this.editingId);
            formData.append('template_id', this.currentTemplate.id);
            formData.append('data', JSON.stringify(data));

            await this.apiPost('/formulare/ausfuellen-pdf', formData);
            
            this.toast('Formular als PDF gespeichert', 'success');
            this.formFillHasChanges = false;
            this.closeFormFillModal();
            
            // Anhänge neu laden
            if (this.editingId) {
                const recordData = await this.apiGet(`/records/${this.editingId}`);
                this.renderAttachments(recordData.attachments || []);
            }
        } catch (e) {
            console.error('PDF-Fehler:', e);
            this.toast('Fehler beim PDF-Speichern: ' + e.message, 'error');
        } finally {
            this.showLoading(false);
        }
    },

    // ── Form Designer Logic ────────────────────────
    designerState: {
        template: null,
        selectedIndex: -1,
        selectedCell: null, // { r, c }
        isDragging: false,
        isResizing: false,
        isColResizing: false,
        resizeColIdx: -1,
        initialColWidths: [],
        snapToGrid: true,
        gridSize: 10,
        dragStart: { x: 0, y: 0 },
        elementStart: { x: 0, y: 0 },
        sizeStart: { w: 0, h: 0 },
        hasChanges: false
    },

    async openFormDesigner(id) {
        try {
            const templates = await this.apiGet('/formulare/vorlagen');
            
            // Null-Prüfung für templates und vorlagen
            if (!templates || !templates.vorlagen) {
                console.warn('Vorlagen konnten nicht geladen werden (templates oder vorlagen ist null)');
                return;
            }
            
            const template = templates.vorlagen.find(t => t.id === id);
            if (!template) throw new Error('Vorlage nicht gefunden');
            
            this.designerState.template = template;
            this.designerState.hasChanges = false;
            if (!this.designerState.template.structure.elements) {
                this.designerState.template.structure.elements = [];
            }
            
            document.getElementById('designerTitle').textContent = `Editor: ${template.name}`;
            document.getElementById('designerTemplateName').value = template.name;
            
            // UI-Zustand Hilfsmittel synchronisieren
            const snapBtn = document.getElementById('btnDesignerSnap');
            if (snapBtn) {
                snapBtn.classList.toggle('active', this.designerState.snapToGrid);
            }

            // Hintergrund-Controls synchronisieren
            if (template.structure.bg) {
                document.getElementById('designerPropBgSize').value = template.structure.bgSize || 'contain';
                document.getElementById('designerPropBgPos').value = template.structure.bgPos || 'center';
                
                if (template.structure.bgSize === 'manual') {
                    document.getElementById('designerPropBgX').value = template.structure.bgX || 0;
                    document.getElementById('designerPropBgY').value = template.structure.bgY || 0;
                    document.getElementById('designerPropBgW').value = template.structure.bgW || 800;
                    document.getElementById('designerPropBgH').value = template.structure.bgH || 1131;
                }
            }

            this.renderDesigner();
            document.getElementById('formDesignerModalOverlay').classList.add('show');

            // Nächste Nummer in der Sidebar setzen
            const nextNumInput = document.getElementById('designerElementNextNumber');
            if (nextNumInput) nextNumInput.value = template.next_number || 1;
            
            // Event Listener für Drag & Drop
            const area = document.getElementById('designerCanvasArea');
            if (!area.dataset.listened) {
                area.addEventListener('mousemove', e => this.designerOnMouseMove(e));
                area.addEventListener('mouseup', () => this.designerOnMouseUp());
                area.dataset.listened = "true";
            }
        } catch (e) {
            this.toast(e.message, 'error');
        }
    },

    updateDesignerTemplateName() {
        const newName = document.getElementById('designerTemplateName').value.trim();
        if (newName && this.designerState.template) {
            this.designerState.template.name = newName;
            this.designerState.hasChanges = true;
            document.getElementById('designerTitle').textContent = `Editor: ${newName}`;
        }
    },

    async closeFormDesigner() {
        if (this.designerState.hasChanges) {
            if (!await this.confirm('Ungespeicherte Änderungen', 'Möchten Sie den Editor wirklich verlassen? Alle ungespeicherten Änderungen gehen verloren.', 'Ja, verlassen', 'btn-danger')) {
                return;
            }
        }
        document.getElementById('formDesignerModalOverlay').classList.remove('show');
    },

    renderDesigner() {
        const page = document.getElementById('designerPage');
        page.innerHTML = '';
        page.style.width = (this.designerState.template.structure.width || 800) + 'px';
        page.style.height = (this.designerState.template.structure.height || 1131) + 'px';
        
        const controls = document.getElementById('designerBgControls');

        if (this.designerState.template.structure.bg) {
            page.style.backgroundImage = `url(${this.designerState.template.structure.bg})`;
            
            const isManual = this.designerState.template.structure.bgSize === 'manual';
            
            if (isManual) {
                const bgX = this.designerState.template.structure.bgX || 0;
                const bgY = this.designerState.template.structure.bgY || 0;
                const bgW = this.designerState.template.structure.bgW || 800;
                const bgH = this.designerState.template.structure.bgH || 1131;
                
                page.style.backgroundSize = `${bgW}px ${bgH}px`;
                page.style.backgroundPosition = `${bgX}px ${bgY}px`;
            } else {
                page.style.backgroundSize = this.designerState.template.structure.bgSize || 'contain';
                page.style.backgroundPosition = this.designerState.template.structure.bgPos || 'center';
            }
            
            page.style.backgroundRepeat = 'no-repeat';
            page.classList.remove('no-bg');
            if (controls) controls.classList.remove('hidden');
            
            // Sichtbarkeit der manuellen Steuerung
            const manualControls = document.getElementById('designerBgManualControls');
            const posGroup = document.getElementById('propGroupBgPos');
            if (manualControls) manualControls.classList.toggle('hidden', !isManual);
            if (posGroup) posGroup.classList.toggle('hidden', isManual);

            // Transformations-Overlay für Hintergrund wenn ausgewählt
            if (this.designerState.selectedIndex === -2 && isManual) {
                const overlay = document.createElement('div');
                overlay.id = 'designerBgOverlay';
                overlay.className = 'designer-bg-overlay selected';
                overlay.style.position = 'absolute';
                overlay.style.left = (this.designerState.template.structure.bgX || 0) + 'px';
                overlay.style.top = (this.designerState.template.structure.bgY || 0) + 'px';
                overlay.style.width = (this.designerState.template.structure.bgW || 800) + 'px';
                overlay.style.height = (this.designerState.template.structure.bgH || 1131) + 'px';
                overlay.style.border = '2px solid #000000';
                overlay.style.background = 'rgba(0, 0, 0, 0.1)'; 
                overlay.style.zIndex = '5';
                overlay.style.cursor = 'move';
                overlay.style.pointerEvents = 'auto';

                const handle = document.createElement('div');
                handle.className = 'resize-handle';
                handle.style = 'position:absolute; right:-5px; bottom:-5px; width:10px; height:10px; background:#000000; cursor:nwse-resize; pointer-events:auto;';
                handle.onmousedown = (e) => {
                    e.stopPropagation();
                    this.designerStartResize(-2, e);
                };
                overlay.appendChild(handle);
                page.appendChild(overlay);

                // Draggable Bereich
                overlay.onmousedown = (e) => {
                    if (e.target === overlay) {
                        e.stopPropagation();
                        this.designerSelectElement(-2, e);
                    }
                };
            }
        } else {
            page.style.backgroundImage = 'none';
            page.classList.add('no-bg');
            if (controls) controls.classList.add('hidden');
        }

        // Automatischer Hintergrund-Upload bei Klick auf die Seite entfernt (User-Wunsch)
        /*
        page.onclick = (e) => {
            if (page.classList.contains('no-bg') && e.target === page) {
                document.getElementById('designerBgUpload').click();
            }
        };
        */
        
        this.designerState.template.structure.elements.forEach((el, index) => {
            const div = document.createElement('div');
            div.className = `designer-element designer-element-${el.type}`;
            if (this.designerState.selectedIndex === index) div.classList.add('selected');
            
            div.style.left = el.x + 'px';
            div.style.top = el.y + 'px';
            div.style.fontFamily = el.fontFamily || 'inherit';
            
            if (el.type === 'text' || el.type === 'bullet') {
                div.textContent = el.content || (el.type === 'bullet' ? '•' : 'Text');
                div.style.fontSize = el.fontSize || '14px';
                div.style.fontWeight = el.bold ? 'bold' : 'normal';
                div.style.fontStyle = el.italic ? 'italic' : 'normal';
                div.style.textAlign = el.textAlign || 'center';
                if (el.type === 'bullet') {
                    div.style.width = (el.width || 30) + 'px';
                    div.style.height = (el.height || 30) + 'px';
                    div.style.display = 'flex';
                    div.style.alignItems = 'center';
                    div.style.justifyContent = el.textAlign || 'center';
                }
            } else if (el.type === 'field' || el.type === 'date' || el.type === 'autonum') {
                div.style.width = (el.width || 100) + 'px';
                if (el.type === 'autonum') {
                    div.textContent = this.designerState.template.next_number || 1;
                    div.style.color = 'inherit';
                } else {
                    div.textContent = el.content || (el.type === 'date' ? 'Datum' : '(Eingabefeld)');
                }
                div.style.fontSize = el.fontSize || '14px';
                div.style.fontWeight = el.bold ? 'bold' : 'normal';
                div.style.fontStyle = el.italic ? 'italic' : 'normal';
                div.style.textAlign = el.textAlign || 'center';

                // Unterstreichung im Designer visualisieren
                if (el.hasUnderline) {
                    const line = document.createElement('div');
                    line.style.position = 'absolute';
                    line.style.bottom = '0';
                    line.style.left = '0';
                    line.style.width = el.underlineWidth || '100%';
                    line.style.height = '1px';
                    line.style.background = '#333';
                    line.style.pointerEvents = 'none';
                    div.appendChild(line);
                }
            } else if (el.type === 'line') {
                const isVert = el.orientation === 'vertical';
                div.style.width = isVert ? (el.thickness || '2px') : (el.length || 100) + 'px';
                div.style.height = isVert ? (el.length || 100) + 'px' : (el.thickness || '2px');
            } else if (el.type === 'box') {
                div.style.width = (el.width || 100) + 'px';
                div.style.height = (el.height || 100) + 'px';
                div.style.borderWidth = el.thickness || '1px';
                div.style.background = 'transparent';
            } else if (el.type === 'checkbox') {
                div.style.width = (el.width || 24) + 'px';
                div.style.height = (el.height || 24) + 'px';
                div.style.display = 'flex';
                div.style.alignItems = 'center';
                div.style.justifyContent = 'center';
                // Fake Checkbox, die wie die echte aussieht
                div.innerHTML = `
                    <div style="
                        width: ${el.width || 24}px; 
                        height: ${el.height || 24}px; 
                        border: 2px solid #333; 
                        border-radius: 3px; 
                        background: white; 
                        display: flex; 
                        align-items: center; 
                        justify-content: center;
                    ">
                        ${el.checked ? `
                            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                                <path d="M3 8L6 11L13 4" stroke="#000000" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
                            </svg>
                        ` : ''}
                    </div>
                `;
            } else if (el.type === 'image') {
                div.style.width = (el.width || 100) + 'px';
                div.style.height = (el.height || 100) + 'px';
                div.style.backgroundSize = '100% 100%';
                div.style.backgroundRepeat = 'no-repeat';
                div.style.backgroundPosition = 'center';
                div.classList.add('designer-element-image');
                
                if (el.content) {
                    // Verwende keine Anführungszeichen in url() für Data-URLs in JS-Styles
                    div.style.backgroundImage = `url(${el.content})`;
                } else {
                    div.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;font-size:10px;color:#999;text-align:center;">Bild wählen</div>';
                }
            } else if (el.type === 'signature') {
                const h = el.height || 60;
                const w = el.width || 200;
                div.style.width = w + 'px';
                div.style.height = h + 'px';
                div.style.border = '1px dashed #666';
                div.style.display = 'flex';
                div.style.flexDirection = 'column';
                div.style.alignItems = 'center';
                div.style.justifyContent = 'flex-end';
                div.style.background = 'rgba(0,0,0,0.02)';
                div.style.paddingBottom = '5px';
                div.innerHTML = `
                    <svg width="${Math.min(w - 20, 180)}" height="${Math.min(h - 15, 45)}" viewBox="0 0 180 45" style="opacity: 0.4;">
                        <path d="M10 35 Q20 15 35 28 Q50 40 65 25 Q80 10 95 32 Q110 50 125 28 Q140 12 155 35 Q170 55 175 30" 
                              fill="none" stroke="#666" stroke-width="2.2" stroke-linecap="round"/>
                    </svg>
                    <div style="font-size: 8px; color: #999; margin-top: 2px;">Unterschrift</div>
                `;
            } else if (el.type === 'table') {
                div.style.width = (el.width || 300) + 'px';
                div.style.height = (el.height || 100) + 'px';
                let rows = parseInt(el.rows);
                let cols = parseInt(el.cols);
                if (isNaN(rows)) rows = 3;
                if (isNaN(cols)) cols = 3;
                const cellConfigs = el.cellConfigs || {};
                const colWidths = el.colWidths || [];
                
                if (rows === 0 && cols === 0) {
                    // Both 0, show nothing?
                    div.style.border = '1px dashed #ccc';
                    div.style.display = 'flex';
                    div.style.alignItems = 'center';
                    div.style.justifyContent = 'center';
                    div.innerHTML = '<span style="color:#ccc;font-size:10px;">Zeilen/Spalten einstellen</span>';
                } else if (rows === 0) {
                    // Only horizontal lines
                    const linesContainer = document.createElement('div');
                    linesContainer.style.width = '100%';
                    linesContainer.style.height = '100%';
                    linesContainer.style.position = 'relative';
                    const numLines = cols + 1;
                    for (let i = 0; i <= cols; i++) {
                        const line = document.createElement('div');
                        line.style.position = 'absolute';
                        line.style.left = (i * 100 / cols) + '%';
                        line.style.top = '0';
                        line.style.width = '1px';
                        line.style.height = '100%';
                        line.style.background = '#333';
                        line.style.transform = 'translateX(-50%)';
                        linesContainer.appendChild(line);
                    }
                    // Add borders
                    linesContainer.style.border = '1px solid #333';
                    div.appendChild(linesContainer);
                } else if (cols === 0) {
                    // Only vertical lines
                    const linesContainer = document.createElement('div');
                    linesContainer.style.width = '100%';
                    linesContainer.style.height = '100%';
                    linesContainer.style.position = 'relative';
                    for (let i = 0; i <= rows; i++) {
                        const line = document.createElement('div');
                        line.style.position = 'absolute';
                        line.style.top = (i * 100 / rows) + '%';
                        line.style.left = '0';
                        line.style.height = '1px';
                        line.style.width = '100%';
                        line.style.background = '#333';
                        line.style.transform = 'translateY(-50%)';
                        linesContainer.appendChild(line);
                    }
                    linesContainer.style.border = '1px solid #333';
                    div.appendChild(linesContainer);
                } else {
                    // Normal table
                    const table = document.createElement('table');
                    table.style.width = '100%';
                    table.style.height = '100%';
                    table.style.borderCollapse = 'collapse';
                    table.style.border = '1px solid #333';
                    table.style.background = 'transparent';
                    table.style.tableLayout = 'fixed';

                    for (let r = 0; r < rows; r++) {
                        const tr = document.createElement('tr');
                        tr.style.height = (100 / rows) + '%';
                        
                        for (let c = 0; c < cols; c++) {
                            const td = document.createElement('td');
                            const cellKey = `${r}-${c}`;
                            const config = cellConfigs[cellKey] || {};
                            const isSelected = this.designerState.selectedIndex === index && 
                                              this.designerState.selectedCell?.r === r && 
                                              this.designerState.selectedCell?.c === c;
                            
                            td.style.border = '1px solid #333';
                            td.style.padding = '6px';
                            td.style.cursor = 'pointer';
                            td.style.position = 'relative';
                            td.style.fontSize = '12px';
                            td.style.textAlign = config.textAlign || 'center';
                            td.style.overflow = 'hidden';
                            td.style.whiteSpace = 'pre-wrap';

                            if (colWidths[c]) {
                                td.style.width = colWidths[c] + '%';
                            }
                            
                            if (config.type === 'calc') td.style.background = 'transparent';
                            if (config.type === 'text') {
                                td.style.background = 'rgba(249, 249, 249, 0.2)';
                            }
                            
                            // Apply cell formatting
                            if (config.bold) td.style.fontWeight = 'bold';
                            if (config.italic) td.style.fontStyle = 'italic';
                            if (config.fontSize) td.style.fontSize = config.fontSize;
                            if (config.fontFamily && config.fontFamily !== 'inherit') td.style.fontFamily = config.fontFamily;
                            
                            if (isSelected) {
                                td.style.outline = '2px solid #000000';
                                td.style.outlineOffset = '-2px';
                            }
                            
                            if (config.type === 'calc') {
                                const sym = config.calcMode === 'manual' ? 'f(x)' : (config.op || '+');
                                td.innerHTML = `<div style="font-size:10px; color:#000000; font-weight:bold;">${sym}</div>`;
                            } else if (config.type === 'text') {
                                td.textContent = config.content || '';
                            }

                            td.onmousedown = (e) => {
                                e.stopPropagation();
                                this.designerSelectCell(index, r, c, e);
                            };

                            // Spalten-Resizer (Excel-Style)
                            if (r === 0 && c < cols - 1) {
                                const resizer = document.createElement('div');
                                resizer.style = 'position:absolute; right:-3px; top:0; width:6px; height:100%; cursor:col-resize; z-index:10;';
                                resizer.onmousedown = (e) => {
                                    e.stopPropagation();
                                    this.designerStartColResize(index, c, e);
                                };
                                td.appendChild(resizer);
                            }

                            tr.appendChild(td);
                        }
                        table.appendChild(tr);
                    }
                    div.appendChild(table);
                }
            }
            
            // Resizer hinzufügen
            if (el.type !== 'line') {
                const resizer = document.createElement('div');
                resizer.className = 'designer-resizer';
                resizer.onmousedown = (e) => {
                    e.stopPropagation();
                    this.designerStartResize(index, e);
                };
                div.appendChild(resizer);
            }
            
            div.onmousedown = (e) => {
                e.stopPropagation();
                this.designerSelectElement(index, e);
            };
            
            page.appendChild(div);
        });
    },

    designerAddImage() {
        document.getElementById('designerImageUpload').click();
    },

    designerHandleImageUpload(e) {
        const file = e.target.files[0];
        if (!file) return;

        const reader = new FileReader();
        reader.onload = (event) => {
            const base64 = event.target.result;
            this.designerAddElement('image', { content: base64, width: 200, height: 150 });
            this.designerState.hasChanges = true;
            e.target.value = ''; // Reset für nächsten Upload
        };
        reader.readAsDataURL(file);
    },

    designerHandleBgUpload(e) {
        const file = e.target.files[0];
        if (!file) return;
        const reader = new FileReader();
        reader.onload = (ev) => {
            if (!this.designerState.template.structure) {
                this.designerState.template.structure = { elements: [] };
            }
            this.designerState.template.structure.bg = ev.target.result;
            this.designerState.hasChanges = true;
            this.renderDesigner();
            e.target.value = ''; 
        };
        reader.readAsDataURL(file);
    },

    designerClearBg() {
        if (!this.designerState.template.structure) return;
        this.designerState.template.structure.bg = null;
        this.designerState.hasChanges = true;
        if (this.designerState.selectedIndex === -2) this.designerState.selectedIndex = -1;
        this.renderDesigner();
    },

    designerSelectBg() {
        this.designerState.selectedIndex = -2;
        this.designerUpdateBgProp('bgSize', 'manual'); // Automatisch auf manuell schalten
        this.renderDesigner();
        this.designerUpdateToolbarProps();
    },

    designerUpdateBgProp(key, val) {
        if (!this.designerState.template.structure) return;
        this.designerState.template.structure[key] = val;
        this.designerState.hasChanges = true;
        
        // Initialwerte für Manuell setzen falls nötig
        if (key === 'bgSize' && val === 'manual') {
            if (this.designerState.template.structure.bgX === undefined) this.designerState.template.structure.bgX = 0;
            if (this.designerState.template.structure.bgY === undefined) this.designerState.template.structure.bgY = 0;
            if (this.designerState.template.structure.bgW === undefined) this.designerState.template.structure.bgW = 800;
            if (this.designerState.template.structure.bgH === undefined) this.designerState.template.structure.bgH = 1131;
        }

        this.renderDesigner();
        this.designerUpdateToolbarProps(); // Um die Inputs zu synchronisieren
    },

    handleFormFillBgUpload(e) {
        const file = e.target.files[0];
        if (!file) return;
        const reader = new FileReader();
        reader.onload = (ev) => {
            this.currentTemplate.structure.bg = ev.target.result;
            this.showFormFillModal(this.currentTemplate);
            e.target.value = '';
        };
        reader.readAsDataURL(file);
    },

    designerStartResize(index, e) {
        this.designerState.selectedIndex = index;
        
        this.designerState.isResizing = true;
        this.designerState.dragStart = { x: e.clientX, y: e.clientY };
        
        if (index === -2) {
            this.designerState.sizeStart = { 
                w: this.designerState.template.structure.bgW || 800, 
                h: this.designerState.template.structure.bgH || 1131 
            };
        } else {
            const el = this.designerState.template.structure.elements[index];
            this.designerState.sizeStart = { w: el.width || 100, h: el.height || 100 };
        }
        
        this.renderDesigner();
    },

    designerAddElement(type, extra = {}) {
        const newEl = {
            type,
            x: 50,
            y: 50,
            content: type === 'text' ? 'Neuer Text' : (type === 'field' ? 'Beschriftung' : (type === 'date' ? 'Datum:' : (type === 'bullet' ? '•' : (type === 'signature' ? '' : '')))),
            fontSize: '14px',
            fontFamily: 'inherit',
            bold: false,
            italic: false,
            width: type === 'checkbox' ? 24 : (type === 'line' ? 150 : (type === 'table' ? 300 : (type === 'bullet' ? 30 : (type === 'autonum' ? 100 : (type === 'signature' ? 200 : 200))))),
            height: type === 'checkbox' ? 24 : (type === 'line' ? 2 : (type === 'box' ? 100 : (type === 'table' ? 100 : (type === 'bullet' ? 30 : (type === 'signature' ? 60 : 30))))),
            length: 150,
            rows: type === 'table' ? 3 : undefined,
            cols: type === 'table' ? 3 : undefined,
            colWidths: type === 'table' ? [] : undefined,
            cellConfigs: type === 'table' ? {} : undefined,
            id: (type === 'field' || type === 'checkbox' || type === 'table' || type === 'date' || type === 'autonum' || type === 'signature') ? 'feld_' + Date.now() : undefined,
            hasUnderline: (type === 'field' || type === 'date' || type === 'autonum'),
            underlineWidth: '100%',
            checked: type === 'checkbox', // Default checked for placeholder
            ...extra
        };
        this.designerState.template.structure.elements.push(newEl);
        this.designerState.hasChanges = true;
        this.designerState.selectedIndex = this.designerState.template.structure.elements.length - 1;
        this.designerState.selectedCell = null;
        this.renderDesigner();
        this.designerUpdateToolbarProps();
    },

    designerSelectCell(elIdx, r, c, e) {
        this.designerState.selectedIndex = elIdx;
        this.designerState.selectedCell = { r, c };
        
        // Auch das Element selbst zum Verschieben auswählen
        const el = this.designerState.template.structure.elements[elIdx];
        this.designerState.isDragging = true;
        this.designerState.dragStart = { x: e.clientX, y: e.clientY };
        this.designerState.elementStart = { x: el.x, y: el.y };
        
        this.renderDesigner();
        this.designerUpdateToolbarProps();
    },

    designerUpdateCellProp(key, val) {
        if (this.designerState.selectedIndex === -1 || !this.designerState.selectedCell) return;
        const el = this.designerState.template.structure.elements[this.designerState.selectedIndex];
        if (!el.cellConfigs) el.cellConfigs = {};
        
        const cellKey = `${this.designerState.selectedCell.r}-${this.designerState.selectedCell.c}`;
        if (!el.cellConfigs[cellKey]) el.cellConfigs[cellKey] = { type: 'input', dir: 'row', op: '+' };
        
        el.cellConfigs[cellKey][key] = val;
        this.designerState.hasChanges = true;
        this.renderDesigner();
        this.designerUpdateToolbarProps();
    },

    designerUpdateColWidth(val) {
        if (this.designerState.selectedIndex === -1 || !this.designerState.selectedCell) return;
        const el = this.designerState.template.structure.elements[this.designerState.selectedIndex];
        if (!el.colWidths) el.colWidths = [];
        
        const colIdx = this.designerState.selectedCell.c;
        el.colWidths[colIdx] = val ? parseInt(val) : null;
        
        this.designerState.hasChanges = true;
        this.renderDesigner();
    },

    designerStartColResize(elIdx, colIdx, e) {
        this.designerState.selectedIndex = elIdx;
        const el = this.designerState.template.structure.elements[elIdx];
        if (!el.colWidths || el.colWidths.length === 0) {
            // Initial alle gleich breit machen (100% / cols)
            el.colWidths = Array(el.cols).fill(100 / el.cols);
        }

        this.designerState.isColResizing = true;
        this.designerState.resizeColIdx = colIdx;
        this.designerState.dragStart = { x: e.clientX, y: e.clientY };
        this.designerState.initialColWidths = [...el.colWidths];
        
        // Cursor global ändern während des Ziehens
        document.body.style.cursor = 'col-resize';
    },

    designerToggleStyle(style) {
        if (this.designerState.selectedIndex === -1) return;
        
        if (this.designerState.selectedCell) {
            // Update cell style
            const el = this.designerState.template.structure.elements[this.designerState.selectedIndex];
            const cellKey = `${this.designerState.selectedCell.r}-${this.designerState.selectedCell.c}`;
            if (!el.cellConfigs) el.cellConfigs = {};
            if (!el.cellConfigs[cellKey]) el.cellConfigs[cellKey] = { type: 'input', dir: 'row', op: '+' };
            
            if (style === 'bold') el.cellConfigs[cellKey].bold = !el.cellConfigs[cellKey].bold;
            if (style === 'italic') el.cellConfigs[cellKey].italic = !el.cellConfigs[cellKey].italic;
        } else {
            // Update element style
            const el = this.designerState.template.structure.elements[this.designerState.selectedIndex];
            if (style === 'bold') el.bold = !el.bold;
            if (style === 'italic') el.italic = !el.italic;
        }
        
        this.designerState.hasChanges = true;
        this.renderDesigner();
        this.designerUpdateToolbarProps();
    },

    designerSetAlign(align) {
        if (this.designerState.selectedIndex === -1) return;
        
        if (this.designerState.selectedCell) {
            // Update cell alignment
            const el = this.designerState.template.structure.elements[this.designerState.selectedIndex];
            const cellKey = `${this.designerState.selectedCell.r}-${this.designerState.selectedCell.c}`;
            if (!el.cellConfigs) el.cellConfigs = {};
            if (!el.cellConfigs[cellKey]) el.cellConfigs[cellKey] = { type: 'input', dir: 'row', op: '+' };
            
            el.cellConfigs[cellKey].textAlign = align;
        } else {
            // Update element alignment
            const el = this.designerState.template.structure.elements[this.designerState.selectedIndex];
            el.textAlign = align;
        }
        
        this.designerState.hasChanges = true;
        this.renderDesigner();
        this.designerUpdateToolbarProps();
    },

    designerSelectElement(index, e) {
        if (this.designerState.selectedIndex !== index) {
            this.designerState.selectedCell = null;
        }
        this.designerState.selectedIndex = index;
        
        this.designerState.isDragging = true;
        this.designerState.dragStart = { x: e.clientX, y: e.clientY };
        
        if (index === -2) {
            this.designerState.elementStart = { 
                x: this.designerState.template.structure.bgX || 0, 
                y: this.designerState.template.structure.bgY || 0 
            };
        } else {
            const el = this.designerState.template.structure.elements[index];
            this.designerState.elementStart = { x: el.x, y: el.y };
        }
        
        this.renderDesigner();
        this.designerUpdateToolbarProps();
    },

    designerUpdateToolbarProps() {
        const panel = document.getElementById('designerPropertiesPanel');
        const empty = document.getElementById('designerNoSelection');
        
        if (this.designerState.selectedIndex === -1) {
            panel.classList.add('hidden');
            empty.classList.remove('hidden');
            return;
        }

        panel.classList.remove('hidden');
        empty.classList.add('hidden');

        if (this.designerState.selectedIndex === -2) {
            // Hintergrund-Spezifische Toolbar-Anpassung
            const show = (id, condition) => {
                const elDom = document.getElementById(id);
                if (elDom) {
                    if (condition) elDom.classList.remove('hidden');
                    else elDom.classList.add('hidden');
                }
            };
            show('propGroupContent', false);
            show('propGroupId', false);
            show('propGroupFontSize', false);
            show('propGroupFontFamily', false);
            show('propGroupTextStyle', false);
            show('propGroupNextNumber', false);
            show('propGroupHeight', true);
            show('propGroupThickness', false);
            show('propGroupTable', false);
            show('propGroupUnderline', false);
            
            document.getElementById('designerPropWidth').value = this.designerState.template.structure.bgW || 800;
            document.getElementById('designerPropHeight').value = this.designerState.template.structure.bgH || 1131;
            return;
        }

        const el = this.designerState.template.structure.elements[this.designerState.selectedIndex];
        let currentAlign = 'center'; // Default
        
        if (this.designerState.selectedCell) {
            // Cell properties
            const { r, c } = this.designerState.selectedCell;
            const cellKey = `${r}-${c}`;
            const config = (el.cellConfigs && el.cellConfigs[cellKey]) || { type: 'input', dir: 'row', op: '+' };
            
            document.getElementById('designerPropContent').value = config.content || '';
            document.getElementById('designerPropId').value = '';
            document.getElementById('designerPropFontSize').value = config.fontSize ? config.fontSize.replace('px', '') : '14';
            document.getElementById('designerPropFontFamily').value = config.fontFamily || 'inherit';
            document.getElementById('designerPropWidth').value = el.width || 300;
            document.getElementById('designerPropHeight').value = el.height || 100;
            
            // Cell style buttons
            document.getElementById('btnPropBold').classList.toggle('btn-primary', !!config.bold);
            document.getElementById('btnPropBold').classList.toggle('btn-secondary', !config.bold);
            document.getElementById('btnPropItalic').classList.toggle('btn-primary', !!config.italic);
            document.getElementById('btnPropItalic').classList.toggle('btn-secondary', !config.italic);
            
            // Get cell alignment
            currentAlign = config.textAlign || 'center';
        } else {
            // Element properties
            document.getElementById('designerPropContent').value = el.content || '';
            document.getElementById('designerPropId').value = el.id || '';
            document.getElementById('designerPropFontSize').value = el.fontSize ? el.fontSize.replace('px', '') : '14';
            document.getElementById('designerPropFontFamily').value = el.fontFamily || 'inherit';
            document.getElementById('designerPropWidth').value = el.width || (el.type === 'line' ? el.length : (el.type === 'table' ? 300 : 100));
            document.getElementById('designerPropHeight').value = el.height || (el.type === 'line' ? 2 : (el.type === 'table' ? 100 : 100));
            document.getElementById('designerPropThickness').value = el.thickness ? el.thickness.replace('px', '') : '1';
            
            // Element style buttons
            document.getElementById('btnPropBold').classList.toggle('btn-primary', !!el.bold);
            document.getElementById('btnPropBold').classList.toggle('btn-secondary', !el.bold);
            document.getElementById('btnPropItalic').classList.toggle('btn-primary', !!el.italic);
            document.getElementById('btnPropItalic').classList.toggle('btn-secondary', !el.italic);
            
            // Get element alignment
            currentAlign = el.textAlign || 'center';
        }
        
        // Update alignment buttons
        document.getElementById('btnPropAlignLeft').classList.toggle('btn-primary', currentAlign === 'left');
        document.getElementById('btnPropAlignLeft').classList.toggle('btn-secondary', currentAlign !== 'left');
        document.getElementById('btnPropAlignCenter').classList.toggle('btn-primary', currentAlign === 'center');
        document.getElementById('btnPropAlignCenter').classList.toggle('btn-secondary', currentAlign !== 'center');
        document.getElementById('btnPropAlignRight').classList.toggle('btn-primary', currentAlign === 'right');
        document.getElementById('btnPropAlignRight').classList.toggle('btn-secondary', currentAlign !== 'right');
        
        // Unterstreichung Props
        const hasUnderlineCheck = document.getElementById('designerPropHasUnderline');
        const underlineWidthInput = document.getElementById('designerPropUnderlineWidth');
        if (hasUnderlineCheck) hasUnderlineCheck.checked = !!el.hasUnderline;
        if (underlineWidthInput) underlineWidthInput.value = el.underlineWidth ? el.underlineWidth.replace('%', '') : '100';
        
        if (el.type === 'table') {
            document.getElementById('designerPropRows').value = el.rows || 3;
            document.getElementById('designerPropCols').value = el.cols || 3;
            
            const cellPanel = document.getElementById('propGroupTableCell');
            const noCell = document.getElementById('designerNoCellSelection');
            
            if (this.designerState.selectedCell) {
                cellPanel.classList.remove('hidden');
                noCell.classList.add('hidden');
                
                const { r, c } = this.designerState.selectedCell;
                document.getElementById('selectedCellCoords').textContent = `Zelle ${r+1}, Spalte ${c+1}`;
                
                const cellKey = `${r}-${c}`;
                const config = (el.cellConfigs && el.cellConfigs[cellKey]) || { type: 'input', dir: 'row', op: '+' };
                
                document.getElementById('designerPropCellType').value = config.type || 'input';
                document.getElementById('designerPropCellDir').value = config.dir || 'row';
                document.getElementById('designerPropCellOp').value = config.op || '+';
                document.getElementById('designerPropCellText').value = config.content || '';
                document.getElementById('designerPropCellCalcMode').value = config.calcMode || 'auto';
                document.getElementById('designerPropCellFormula').value = config.formula || '';
                
                document.getElementById('designerCellTextOptions').classList.toggle('hidden', config.type !== 'text');
                document.getElementById('designerCellCalcOptions').classList.toggle('hidden', config.type !== 'calc');
                
                if (config.type === 'calc') {
                    const mode = config.calcMode || 'auto';
                    document.getElementById('designerCellManualFormula').classList.toggle('hidden', mode !== 'manual');
                    document.getElementById('designerCellAutoOptions').classList.toggle('hidden', mode === 'manual');
                }
            } else {
                cellPanel.classList.add('hidden');
                noCell.classList.remove('hidden');
            }
        }

        // Sichtbarkeit steuern
        const show = (id, condition) => {
            const elDom = document.getElementById(id);
            if (elDom) {
                if (condition) elDom.classList.remove('hidden');
                else elDom.classList.add('hidden');
            }
        };
        
        show('propGroupContent', el.type === 'text' || el.type === 'field' || el.type === 'date' || el.type === 'bullet' || el.type === 'signature');
        show('propGroupId', el.type === 'field' || el.type === 'checkbox' || el.type === 'table' || el.type === 'date' || el.type === 'autonum' || el.type === 'signature');
        show('propGroupFontSize', el.type === 'text' || el.type === 'field' || el.type === 'table' || el.type === 'date' || el.type === 'bullet' || el.type === 'autonum' || el.type === 'signature');
        show('propGroupFontFamily', el.type === 'text' || el.type === 'field' || el.type === 'table' || el.type === 'date' || el.type === 'bullet' || el.type === 'autonum' || el.type === 'signature');
        show('propGroupTextStyle', el.type === 'text' || el.type === 'field' || el.type === 'table' || el.type === 'date' || el.type === 'bullet' || el.type === 'autonum' || el.type === 'signature');
        show('propGroupNextNumber', el.type === 'autonum');
        show('propGroupTypography', el.type === 'text' || el.type === 'field' || el.type === 'table' || el.type === 'date' || el.type === 'bullet' || el.type === 'autonum' || el.type === 'signature');
        show('propGroupHeight', el.type !== 'text');
        show('propGroupThickness', el.type === 'line' || el.type === 'box');
        show('propGroupTable', el.type === 'table');
        show('propGroupUnderline', el.type === 'field' || el.type === 'date' || el.type === 'autonum');
        show('propGroupUnderlineWidth', !!el.hasUnderline);

        // Werte in Sidebar setzen
        if (el.type === 'autonum') {
            const nextNumInput = document.getElementById('designerElementNextNumber');
            if (nextNumInput) nextNumInput.value = this.designerState.template.next_number || 1;
        }
    },

    designerUpdateNextNumber(val) {
        this.designerState.template.next_number = parseInt(val) || 1;
        this.designerState.hasChanges = true;
        this.renderDesigner();
    },

    designerUpdateActiveProp(key, val) {
        if (this.designerState.selectedIndex === -1) return;
        
        // Table rows/cols always go to the element, not cell
        if (key === 'rows' || key === 'cols') {
            const el = this.designerState.template.structure.elements[this.designerState.selectedIndex];
            el[key] = parseInt(val) || 1; // At least 1
            this.designerState.hasChanges = true;
            this.renderDesigner();
            return;
        }
        
        if (this.designerState.selectedCell) {
            // Update cell property
            const el = this.designerState.template.structure.elements[this.designerState.selectedIndex];
            const cellKey = `${this.designerState.selectedCell.r}-${this.designerState.selectedCell.c}`;
            if (!el.cellConfigs) el.cellConfigs = {};
            if (!el.cellConfigs[cellKey]) el.cellConfigs[cellKey] = { type: 'input', dir: 'row', op: '+' };
            
            el.cellConfigs[cellKey][key] = val;
        } else {
            // Update element property
            const el = this.designerState.template.structure.elements[this.designerState.selectedIndex];
            
            // Spezialfall Line Width -> Length
            if (el.type === 'line' && key === 'width') {
                el.length = val;
            } else {
                el[key] = val;
            }
        }
        
        this.designerState.hasChanges = true;
        this.renderDesigner();
    },

    designerOnCanvasMouseDown(e) {
        if (e.target.id === 'designerCanvasArea' || e.target.id === 'designerPage') {
            this.designerState.selectedIndex = -1;
            this.designerState.selectedCell = null;
            this.renderDesigner();
            this.designerUpdateToolbarProps();
        }
    },

    designerToggleSnap() {
        this.designerState.snapToGrid = !this.designerState.snapToGrid;
        const btn = document.getElementById('btnDesignerSnap');
        if (btn) {
            btn.classList.toggle('active', this.designerState.snapToGrid);
        }
    },

    designerOnMouseMove(e) {
        if (this.designerState.selectedIndex === -1) return;
        
        if (this.designerState.isDragging) {
            const dx = e.clientX - this.designerState.dragStart.x;
            const dy = e.clientY - this.designerState.dragStart.y;
            
            let newX = this.designerState.elementStart.x + dx;
            let newY = this.designerState.elementStart.y + dy;
            
            if (this.designerState.snapToGrid) {
                newX = Math.round(newX / this.designerState.gridSize) * this.designerState.gridSize;
                newY = Math.round(newY / this.designerState.gridSize) * this.designerState.gridSize;
            }
            
            if (this.designerState.selectedIndex === -2) {
                this.designerState.template.structure.bgX = Math.round(newX);
                this.designerState.template.structure.bgY = Math.round(newY);
                
                // Direktes DOM Update für flüssiges Dragging
                const page = document.getElementById('designerPage');
                const overlay = document.getElementById('designerBgOverlay');
                if (page) page.style.backgroundPosition = `${this.designerState.template.structure.bgX}px ${this.designerState.template.structure.bgY}px`;
                if (overlay) {
                    overlay.style.left = this.designerState.template.structure.bgX + 'px';
                    overlay.style.top = this.designerState.template.structure.bgY + 'px';
                }
            } else {
                const el = this.designerState.template.structure.elements[this.designerState.selectedIndex];
                el.x = Math.round(newX);
                el.y = Math.round(newY);
                
                // Element direkt im DOM verschieben für smoothes Feedback
                const page = document.getElementById('designerPage');
                const div = page.children[this.designerState.selectedIndex];
                if (div) {
                    div.style.left = el.x + 'px';
                    div.style.top = el.y + 'px';
                }
            }
        } else if (this.designerState.isResizing) {
            const dx = e.clientX - this.designerState.dragStart.x;
            const dy = e.clientY - this.designerState.dragStart.y;
            
            let newW = this.designerState.sizeStart.w + dx;
            let newH = this.designerState.sizeStart.h + dy;
            
            if (this.designerState.snapToGrid) {
                newW = Math.round(newW / this.designerState.gridSize) * this.designerState.gridSize;
                newH = Math.round(newH / this.designerState.gridSize) * this.designerState.gridSize;
            }
            
            if (this.designerState.selectedIndex === -2) {
                this.designerState.template.structure.bgW = Math.max(10, Math.round(newW));
                this.designerState.template.structure.bgH = Math.max(10, Math.round(newH));
                
                // Direktes DOM Update für flüssiges Resizing
                const page = document.getElementById('designerPage');
                const overlay = document.getElementById('designerBgOverlay');
                if (page) page.style.backgroundSize = `${this.designerState.template.structure.bgW}px ${this.designerState.template.structure.bgH}px`;
                if (overlay) {
                    overlay.style.width = this.designerState.template.structure.bgW + 'px';
                    overlay.style.height = this.designerState.template.structure.bgH + 'px';
                }
            } else {
                const el = this.designerState.template.structure.elements[this.designerState.selectedIndex];
                el.width = Math.max(10, Math.round(newW));
                el.height = Math.max(10, Math.round(newH));
                
                // Element direkt im DOM skalieren
                const page = document.getElementById('designerPage');
                const div = page.children[this.designerState.selectedIndex];
                if (div) {
                    div.style.width = el.width + 'px';
                    div.style.height = el.height + 'px';
                }
            }
            this.designerUpdateToolbarProps();
        } else if (this.designerState.isColResizing) {
            const dx = e.clientX - this.designerState.dragStart.x;
            const el = this.designerState.template.structure.elements[this.designerState.selectedIndex];
            const colIdx = this.designerState.resizeColIdx;
            
            // Prozentuale Änderung berechnen basierend auf der Gesamtbreite der Tabelle
            const tableWidth = el.width || 300;
            const deltaPercent = (dx / tableWidth) * 100;
            
            const newWidths = [...this.designerState.initialColWidths];
            const minWidth = 5; // Minimum 5% Breite pro Spalte
            
            // Aktuelle Spalte vergrößern/verkleinern, nächste Spalte entsprechend anpassen
            let change = deltaPercent;
            if (newWidths[colIdx] + change < minWidth) change = minWidth - newWidths[colIdx];
            if (newWidths[colIdx + 1] - change < minWidth) change = newWidths[colIdx + 1] - minWidth;
            
            newWidths[colIdx] += change;
            newWidths[colIdx + 1] -= change;
            
            el.colWidths = newWidths;
            this.renderDesigner();
        }
    },

    designerOnMouseUp() {
        if (this.designerState.isDragging || this.designerState.isResizing || this.designerState.isColResizing) {
            this.designerState.isDragging = false;
            this.designerState.isResizing = false;
            this.designerState.isColResizing = false;
            this.designerState.hasChanges = true;
            document.body.style.cursor = 'default';
            this.renderDesigner();
        }
    },

    designerUpdateProp(key, val) {
        // Nicht mehr benötigt, da Panel entfernt
    },

    designerUpdatePageProp(key, val) {
        this.designerState.template.structure[key] = val;
        this.designerState.hasChanges = true;
        this.renderDesigner();
    },

    designerDeleteSelected() {
        if (this.designerState.selectedIndex === -1) return;
        this.designerState.template.structure.elements.splice(this.designerState.selectedIndex, 1);
        this.designerState.hasChanges = true;
        this.designerState.selectedIndex = -1;
        this.renderDesigner();
    },

    async saveDesignerTemplate() {
        try {
            const t = this.designerState.template;
            
            // Wichtig: next_number explizit aus dem State nehmen
            const nextNum = parseInt(t.next_number) || 1;
            
            const response = await this.apiPost('/formulare/vorlagen', {
                id: t.id,
                name: t.name,
                structure: t.structure,
                next_number: nextNum
            });
            
            // Wichtig: Die vom Backend zurückgegebene Struktur (mit wiederhergestellten Base64 Bildern) übernehmen
            if (response && response.structure) {
                this.designerState.template.structure = response.structure;
            }
            
            this.toast('Vorlage gespeichert', 'success');
            this.designerState.hasChanges = false;
            // Wir schließen den Designer nicht mehr sofort, damit man weiterarbeiten kann
            this.renderDesigner();
            this.loadFormTemplates();
        } catch (e) {
            this.toast(e.message, 'error');
        }
    },

    // ── Confirm Dialog ─────────────────────────────
    confirm(title, text, btnText = 'Ja, löschen', btnClass = 'btn-danger') {
        // Verhindert doppelte Confirm-Dialoge innerhalb von 3 Sekunden
        const confirmKey = `${title}_${text}_${btnText}`;
        const now = Date.now();
        if (this.recentConfirms.has(confirmKey)) {
            const lastShown = this.recentConfirms.get(confirmKey);
            if (now - lastShown < 3000) {
                console.log('🔒 Doppelte Confirm-Meldung verhindert:', title);
                return Promise.resolve(false); // Abbrechen bei doppeltem Klick
            }
        }

        return new Promise(resolve => {
            const ov = document.getElementById('confirmOverlay');
            const yesBtn = document.getElementById('confirmYes');
            document.getElementById('confirmTitle').textContent = title;
            document.getElementById('confirmText').textContent = text;

            // Button-Text und Klasse anpassen
            yesBtn.textContent = btnText;
            yesBtn.className = `btn ${btnClass}`;

            // Speichere Zeitstempel des Confirm-Dialogs
            this.recentConfirms.set(confirmKey, now);

            ov.classList.add('show');
            const yes = () => {
                ov.classList.remove('show');
                cleanup();
                this.recentConfirms.delete(confirmKey);
                resolve(true);
            };
            const no = () => {
                ov.classList.remove('show');
                cleanup();
                this.recentConfirms.delete(confirmKey);
                resolve(false);
            };
            const cleanup = () => {
                yesBtn.removeEventListener('click', yes);
                document.getElementById('confirmNo').removeEventListener('click', no);
            };
            yesBtn.addEventListener('click', yes);
            document.getElementById('confirmNo').addEventListener('click', no);
        });
    },

    alert(title, text) {
        // Zeigt einen Alert-Dialog im gleichen Stil wie Confirm-Dialog
        return new Promise(resolve => {
            const ov = document.getElementById('alertOverlay');
            const okBtn = document.getElementById('alertOk');
            document.getElementById('alertTitle').innerHTML = title;
            document.getElementById('alertText').textContent = text;

            ov.classList.add('show');
            const ok = () => {
                ov.classList.remove('show');
                cleanup();
                resolve(true);
            };
            const cleanup = () => {
                okBtn.removeEventListener('click', ok);
            };
            okBtn.addEventListener('click', ok);
        });
    },

    // ── Helpers ────────────────────────────────────
    // ── Hilfsfunktionen ───────────────────────────────
    formatBytes(bytes, decimals = 2) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const dm = decimals < 0 ? 0 : decimals;
        const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB', 'YB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
    },

    escapeHtml(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    },

    sanitizeHtml(html) {
        if (!html) return '';
        const div = document.createElement('div');
        div.innerHTML = html;
        
        // Scripte entfernen
        const scripts = div.querySelectorAll('script');
        scripts.forEach(s => s.remove());
        
        // Event-Handler entfernen
        const all = div.querySelectorAll('*');
        all.forEach(el => {
            Array.from(el.attributes).forEach(attr => {
                if (attr.name.toLowerCase().startsWith('on')) {
                    el.removeAttribute(attr.name);
                }
            });
            // javascript: links in href entfernen
            if (el.tagName === 'A' && el.getAttribute('href')?.toLowerCase().startsWith('javascript:')) {
                el.removeAttribute('href');
            }
        });
        
        return div.innerHTML;
    },

    // URLs im Text erkennen und in klickbare Links umwandeln
    linkifyUrls(text) {
        if (!text) return text;
        
        // Regex für URL-Erkennung (http, https, www)
        const urlRegex = /(\b(https?|ftp):\/\/[-A-Z0-9+&@#\/%?=~_|!:,.;]*[-A-Z0-9+&@#\/%=~_|])|(\bwww\.[-A-Z0-9+&@#\/%?=~_|!:,.;]*[-A-Z0-9+&@#\/%=~_|])/gi;
        
        return text.replace(urlRegex, function(url) {
            // Wenn URL kein Protokoll hat, https hinzufügen
            let fullUrl = url;
            if (url.startsWith('www.')) {
                fullUrl = 'https://' + url;
            }
            
            // Link mit data-Attribut für spätere Event-Behandlung
            return `<a href="${fullUrl}" target="_blank" rel="noopener noreferrer" class="auto-link" data-auto-link="true">${url}</a>`;
        });
    },
    stripHtml(html) {
        if (!html) return '';
        const tmp = document.createElement('div');
        tmp.innerHTML = html;
        return tmp.textContent || tmp.innerText || '';
    },
    formatDate(d) {
        if (!d) return '';
        const date = new Date(d);
        return date.toLocaleDateString('de-DE', { day:'2-digit', month:'2-digit', year:'numeric' });
    },
    formatBytes(b) {
        if (!b) return '0 B';
        const units = ['B','KB','MB','GB'];
        let i = 0;
        while (b >= 1024 && i < units.length - 1) { b /= 1024; i++; }
        return `${b.toFixed(1)} ${units[i]}`;
    },

    // ── DateTime Picker ─────────────────────────────
    dateTimePickerState: {
        currentDate: new Date(),
        selectedDate: null,
        isOpen: false,
        activeType: 'start' // 'start' oder 'end'
    },

    bulkDateTimePickerState: {
        currentDate: new Date(),
        selectedDate: null,
        isOpen: false,
        activeType: 'start' // 'start' oder 'end'
    },

    reminderDateTimePickerState: {
        currentDate: new Date(),
        selectedDate: null,
        isOpen: false
    },

    openDateTimePicker(type = 'start') {
        this.dateTimePickerState.isOpen = true;
        this.dateTimePickerState.activeType = type;
        this.dateTimePickerState.currentDate = new Date();

        // Parse existing value if any
        const inputId = type === 'start' ? 'recordReminderDate' : 'recordReminderEndDate';
        const existingValue = document.getElementById(inputId).value;
        if (existingValue) {
            // Deutsches Format DD.MM.YYYY parsen
            const parts = existingValue.split('.');
            if (parts.length === 3) {
                const date = new Date(parts[2], parts[1] - 1, parts[0]);
                if (!isNaN(date.getTime())) {
                    this.dateTimePickerState.selectedDate = date;
                    this.dateTimePickerState.currentDate = new Date(date);
                }
            }
        } else {
            // Default to today
            this.dateTimePickerState.selectedDate = new Date();
        }

        this.renderDateTimePicker();
        document.getElementById('dateTimePickerModal').classList.add('show');
    },

    closeDateTimePicker() {
        this.dateTimePickerState.isOpen = false;
        document.getElementById('dateTimePickerModal').classList.remove('show');
    },

    renderDateTimePicker() {
        const d = this.dateTimePickerState.currentDate;
        const year = d.getFullYear();
        const month = d.getMonth();
        
        // Update header
        document.getElementById('dateTimeMonthYear').textContent = 
            d.toLocaleDateString('de-DE', { month: 'long', year: 'numeric' });
        
        // Calculate calendar days
        const firstDay = new Date(year, month, 1).getDay();
        const daysInMonth = new Date(year, month + 1, 0).getDate();
        const startOffset = firstDay === 0 ? 6 : firstDay - 1; // Monday start
        
        let html = '';
        
        // Weekday headers
        ['Mo','Di','Mi','Do','Fr','Sa','So'].forEach(w => {
            html += `<div class="datetime-weekday">${w}</div>`;
        });
        
        // Empty cells before month starts
        for (let i = 0; i < startOffset; i++) {
            html += `<div class="datetime-day disabled"></div>`;
        }
        
        // Days of month
        const today = new Date();
        for (let day = 1; day <= daysInMonth; day++) {
            const currentDate = new Date(year, month, day);
            const isToday = day === today.getDate() && month === today.getMonth() && year === today.getFullYear();
            const isSelected = this.dateTimePickerState.selectedDate && 
                day === this.dateTimePickerState.selectedDate.getDate() && 
                month === this.dateTimePickerState.selectedDate.getMonth() && 
                year === this.dateTimePickerState.selectedDate.getFullYear();
            const isPast = currentDate < today && !isToday;
            
            let classes = 'datetime-day';
            if (isToday) classes += ' today';
            if (isSelected) classes += ' selected';
            if (isPast) classes += ' disabled';
            
            html += `<div class="${classes}" ${!isPast ? `onclick="App.selectDateTimeDate(${year}, ${month}, ${day})"` : ''}>${day}</div>`;
        }
        
        document.getElementById('dateTimeCalendarGrid').innerHTML = html;
    },

    selectDateTimeDate(year, month, day) {
        this.dateTimePickerState.selectedDate = new Date(year, month, day);
        this.renderDateTimePicker();
    },

    changeDateTimeMonth(delta) {
        this.dateTimePickerState.currentDate.setMonth(this.dateTimePickerState.currentDate.getMonth() + delta);
        this.renderDateTimePicker();
    },

    setDateTime() {
        if (!this.dateTimePickerState.selectedDate) {
            this.dateTimePickerState.selectedDate = new Date();
        }

        const date = this.dateTimePickerState.selectedDate;
        const year = date.getFullYear();
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const day = String(date.getDate()).padStart(2, '0');

        const formattedDate = `${year}-${month}-${day}`;
        const displayStr = `${day}.${month}.${year}`;

        const isStart = this.dateTimePickerState.activeType === 'start';
        const valId = isStart ? 'recordReminderDateValue' : 'recordReminderEndDateValue';
        const displayId = isStart ? 'recordReminderDate' : 'recordReminderEndDate';

        // Update hidden input (ISO for backend)
        document.getElementById(valId).value = formattedDate;

        // Update visible input (German format for user)
        document.getElementById(displayId).value = displayStr;

        this.closeDateTimePicker();
    },

    clearDateTime(type = 'start') {
        const isStart = type === 'start';
        const valId = isStart ? 'recordReminderDateValue' : 'recordReminderEndDateValue';
        const displayId = isStart ? 'recordReminderDate' : 'recordReminderEndDate';
        
        document.getElementById(valId).value = '';
        document.getElementById(displayId).value = '';
    },

    // ── Event Binding ──────────────────────────────
    bindEvents() {
        // Login
        document.getElementById('loginForm').addEventListener('submit', e => this.login(e));
        
        // Password visibility toggle
        document.getElementById('togglePassword').addEventListener('click', () => {
            const passInput = document.getElementById('loginPass');
            const toggleBtn = document.getElementById('togglePassword');
            const icon = toggleBtn.querySelector('i');
            
            if (passInput.type === 'password') {
                passInput.type = 'text';
                icon.classList.remove('fa-eye');
                icon.classList.add('fa-eye-slash');
            } else {
                passInput.type = 'password';
                icon.classList.remove('fa-eye-slash');
                icon.classList.add('fa-eye');
            }
        });

        // Nav
        document.querySelectorAll('[data-section]').forEach(el => {
            el.addEventListener('click', async () => {
                const sec = el.dataset.section;
                if (sec === this.currentSection) return;
                
                // Karte über Navigation:
                if (sec === 'karte') {
                    const auswahl = (this.auswahlIds && this.auswahlIds.size) ? Array.from(this.auswahlIds) : [];
                    if (auswahl.length) {
                        this.karteAktiveIds = auswahl.slice(0, 5000);
                    } else if (this.currentSection === 'records') {
                        const suchtext = document.getElementById('recordsSearch')?.value?.trim() || '';
                        const filter = document.getElementById('recordFilter')?.value || 'all';
                        const hatSucheOderFilter = (suchtext.length > 0) || (filter !== 'all') || (this.searchType && this.searchType !== 'all');
                        if (hatSucheOderFilter && Array.isArray(this.records) && this.records.length) {
                            this.karteAktiveIds = this.records.map(r => r?.id).filter(Number.isFinite).slice(0, 5000);
                        } else {
                            this.karteAktiveIds = null;
                        }
                    } else {
                        this.karteAktiveIds = null;
                    }
                }
                this.showSection(sec);
            });
        });

        // Sidebar toggle
        document.getElementById('sidebarToggle').addEventListener('click', () => this.toggleSidebar());
        document.getElementById('sidebarOverlay').addEventListener('click', () => this.toggleSidebar(false));

        // Record form
        document.getElementById('recordForm').addEventListener('submit', e => this.saveRecord(e));
        
        // Reminder form
        const reminderForm = document.getElementById('reminderForm');
        if (reminderForm) {
            reminderForm.addEventListener('submit', e => this.saveReminder(e));
        }
        
        // Category form
        if (document.getElementById('categoryForm')) {
            document.getElementById('categoryForm').addEventListener('submit', e => this.saveCategory(e));
        }

        document.getElementById('modalClose').addEventListener('click', () => this.closeModal());
        document.getElementById('modalFullscreen').addEventListener('click', () => this.toggleFullscreen());
        
        // Reminder modal close
        const reminderModalClose = document.getElementById('reminderModalClose');
        if (reminderModalClose) {
            reminderModalClose.addEventListener('click', () => this.closeReminderModal());
        }
        const reminderModalOverlay = document.getElementById('reminderModalOverlay');
        if (reminderModalOverlay) {
            reminderModalOverlay.addEventListener('click', e => { if (e.target === e.currentTarget) this.closeReminderModal(); });
        }
        
        // Form Fill Modal Events
        document.getElementById('formFillModalOverlay').addEventListener('click', e => { if (e.target === e.currentTarget) this.closeFormFillModal(); });
        
        // Form Select Modal Events
        document.getElementById('formSelectModalOverlay').addEventListener('click', e => { if (e.target === e.currentTarget) this.closeFormSelectModal(); });

        // Form Designer Modal Events

        document.getElementById('recordFiles').addEventListener('change', e => this.handleFileUpload(e));

        // Update package file selection display
        document.getElementById('updatePackageInput').addEventListener('change', e => {
            const display = document.getElementById('updatePackageDisplay');
            const file = e.target.files[0];
            if (file) {
                display.innerHTML = `<i class="fas fa-file-archive text-success"></i> <span>${file.name}</span>`;
            } else {
                display.innerHTML = `<i class="fas fa-file-archive text-muted"></i> <span>Keine Datei ausgewählt</span>`;
            }
        });

        // Record form change tracking
        document.getElementById('recordForm').addEventListener('input', () => {
            if (this.editingId || this.currentSection === 'records' || this.currentSection === 'dashboard') {
                this.hasChanges = true;
            }
        });
        document.getElementById('recordContent').addEventListener('input', () => {
            this.hasChanges = true;
        });
        // Allow standard keyboard shortcuts in content area
        document.getElementById('recordContent').addEventListener('keydown', (e) => {
            // Allow: Ctrl+C, Ctrl+V, Ctrl+X, Ctrl+A, Ctrl+Z, Ctrl+Y, Ctrl+B, Ctrl+I, Ctrl+U
            if (
                (e.ctrlKey && ['c', 'v', 'x', 'a', 'z', 'y', 'b', 'i', 'u'].includes(e.key.toLowerCase())) ||
                (e.ctrlKey && e.key === 'a') // Ctrl+A (select all)
            ) {
                // Do nothing, let browser handle it
                return;
            }
        });

        // Browser tab closing warning
        window.addEventListener('beforeunload', (e) => {
            if (this.hasChanges || this.designerState.hasChanges || this.formFillHasChanges) {
                e.preventDefault();
                e.returnValue = ''; // Standard für moderne Browser
            }
        });

        // Gallery events
        const galleryLightboxClose = document.getElementById('galleryLightboxClose');
        if (galleryLightboxClose) {
            galleryLightboxClose.addEventListener('click', () => this.closeGalleryLightbox());
        }
        const galleryLightboxOverlay = document.getElementById('galleryLightboxOverlay');
        if (galleryLightboxOverlay) {
            galleryLightboxOverlay.addEventListener('click', e => { if (e.target === e.currentTarget) this.closeGalleryLightbox(); });
        }
        const galleryLightboxPrev = document.getElementById('galleryLightboxPrev');
        if (galleryLightboxPrev) {
            galleryLightboxPrev.addEventListener('click', () => this.navigateGalleryLightbox(-1));
        }
        const galleryLightboxNext = document.getElementById('galleryLightboxNext');
        if (galleryLightboxNext) {
            galleryLightboxNext.addEventListener('click', () => this.navigateGalleryLightbox(1));
        }
        // Keyboard navigation for gallery
        document.addEventListener('keydown', e => {
            const lightbox = document.getElementById('galleryLightboxOverlay');
            if (lightbox && lightbox.classList.contains('show')) {
                if (e.key === 'Escape') {
                    this.closeGalleryLightbox();
                } else if (e.key === 'ArrowLeft') {
                    this.navigateGalleryLightbox(-1);
                } else if (e.key === 'ArrowRight') {
                    this.navigateGalleryLightbox(1);
                }
            }
        });

        // Search
        document.getElementById('recordsSearch').addEventListener('input', () => {
            this.debounceSearch();
            this.updateSearchButtonIcon();
        });
        document.getElementById('recordsSearch').addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                if (this.searchType === 'similar') {
                    const searchInput = document.getElementById('recordsSearch');
                    const searchQuery = searchInput ? searchInput.value.trim() : '';
                    if (searchQuery) {
                        this.loadSimilarRecords(searchQuery);
                    } else {
                        this.records = [];
                        this.renderRecords();
                    }
                } else {
                    this.loadRecords();
                }
            }
        });
        document.getElementById('recordFilter').addEventListener('change', () => {
            this.saveUserPreferences();
            this.loadRecords();
        });
        document.getElementById('recordSort').addEventListener('change', () => {
            this.saveUserPreferences();
            this.sortRecords();
            this.renderRecords();
        });

        // Gallery Search
        const gallerySearchInput = document.getElementById('gallerySearch');
        if (gallerySearchInput) {
            gallerySearchInput.addEventListener('input', () => {
                this.debounceGallerySearch();
                this.updateGallerySearchButtonIcon();
            });
            gallerySearchInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    this.loadGallery();
                }
            });
        }

        // Prevent Enter key from submitting forms in all input fields (except login)
        document.querySelectorAll('input[type="text"], input[type="number"], input[type="password"]').forEach(input => {
            input.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') {
                    // Wenn wir uns im Login-Screen befinden, Enter erlauben (form submit)
                    if (input.closest('#loginForm')) return;
                    
                    e.preventDefault();
                }
            });
        });

        // Search tabs (records)
        document.querySelectorAll('#recordsSection .search-tab').forEach(t => {
            t.addEventListener('click', () => this.switchSearchTab(t.dataset.type));
        });

        // Search tabs (gallery)
        document.querySelectorAll('#gallerySection .search-tab').forEach(t => {
            t.addEventListener('click', () => this.switchGallerySearchTab(t.dataset.type));
        });

        // User form
        document.getElementById('userForm').addEventListener('submit', e => this.saveUser(e));
        document.getElementById('userModalClose').addEventListener('click', () => this.closeModal());
        document.getElementById('userModalOverlay').addEventListener('click', e => { if (e.target === e.currentTarget) this.closeModal(); });

        // File drop zone click
        document.getElementById('fileDropZone').addEventListener('click', () => document.getElementById('recordFiles').click());

        // Clipboard drop zone click
        const clipboardDropZone = document.getElementById('clipboardDropZone');
        if (clipboardDropZone) {
            clipboardDropZone.addEventListener('click', () => this.handleClipboardImport());
        }

        // Clipboard text input paste event
        const clipboardTextInput = document.getElementById('clipboardTextInput');
        if (clipboardTextInput) {
            clipboardTextInput.addEventListener('paste', (e) => this.handleClipboardPaste(e));
        }

        // DateTime picker
        document.getElementById('dateTimePickerModal').addEventListener('click', e => {
            if (e.target === e.currentTarget) this.closeDateTimePicker();
        });
        // Reminder date time picker
        const reminderDateTimePickerModal = document.getElementById('reminderDateTimePickerModal');
        if (reminderDateTimePickerModal) {
            reminderDateTimePickerModal.addEventListener('click', e => {
                if (e.target === e.currentTarget) this.closeReminderDateTimePicker();
            });
        }

        // Settings: URL preview live update
        document.getElementById('settingHost').addEventListener('change', () => this.updateUrlPreview());
        document.getElementById('settingPort').addEventListener('input', () => this.updateUrlPreview());

        // Settings: Toggle backup time/interval when startup backup is checked
        const settingBackupOnStartup = document.getElementById('settingBackupOnStartup');
        if (settingBackupOnStartup) {
            settingBackupOnStartup.addEventListener('change', () => this.toggleBackupTimeEnabled());
        }

        // Settings: Toggle OCR schedule time inputs based on schedule mode
        const settingOcrScheduleMode = document.getElementById('settingOcrScheduleMode');
        if (settingOcrScheduleMode) {
            settingOcrScheduleMode.addEventListener('change', () => {
                const timeGroup = document.getElementById('ocrScheduleTimeGroup');
                if (timeGroup) {
                    timeGroup.style.display = settingOcrScheduleMode.value === 'scheduled' ? 'block' : 'none';
                }
            });
        }

        // Settings: Toggle archive schedule time inputs based on schedule mode
        const settingArchiveScheduleMode = document.getElementById('settingArchiveScheduleMode');
        if (settingArchiveScheduleMode) {
            settingArchiveScheduleMode.addEventListener('change', () => {
                const timeGroup = document.getElementById('archiveScheduleTimeGroup');
                if (timeGroup) {
                    timeGroup.style.display = settingArchiveScheduleMode.value === 'scheduled' ? 'block' : 'none';
                }
            });
        }

        // Keyboard: Escape closes modal
        document.addEventListener('keydown', e => {
            if (e.key === 'Escape') {
                this.closeModal();
                if (this.dateTimePickerState.isOpen) this.closeDateTimePicker();
                const reminderDateTimeModal = document.getElementById('reminderDateTimePickerModal');
                if (reminderDateTimeModal && !reminderDateTimeModal.classList.contains('hidden')) {
                    this.closeReminderDateTimePicker();
                }
            }
        });
    },

    async checkUpdate() {
        try {
            const data = await this.apiGet('/admin/update/check', false);
            const display = document.getElementById('currentVersionDisplay');
            if (display) {
                display.textContent = `Version ${data.current_version}`;
            }
        } catch (e) {
            // Update-Check ist optional - Fehler ignorieren
            const display = document.getElementById('currentVersionDisplay');
            if (display) {
                display.textContent = 'Update-Check nicht verfügbar';
            }
        }
    },

    async uploadUpdate() {
        const input = document.getElementById('updatePackageInput');
        if (!input || !input.files.length) {
            this.toast('Bitte wählen Sie zuerst eine ZIP-Datei aus.', 'error');
            return;
        }

        const file = input.files[0];
        const formData = new FormData();
        formData.append('file', file);

        try {
            this.toast('Update wird hochgeladen...', 'info');
            const data = await this.uploadFileWithProgress('/admin/update/upload', formData, file.name);
            
            const container = document.getElementById('updateStatusContainer');
            const text = document.getElementById('updateStatusText');
            const btn = document.getElementById('installUpdateBtn');
            
            if (container) container.classList.remove('hidden');
            if (text) text.innerHTML = `<i class="fas fa-check-circle text-success"></i> Paket erfolgreich hochgeladen und verifiziert.`;
            if (btn) btn.classList.remove('hidden');
            this.toast('Update-Paket bereit.', 'success');
        } catch (e) {
            this.toast(e.message, 'error');
        }
    },

    async exportUpdate() {
        let progressInterval = null;
        let currentProgress = 0;
        
        try {
            // Ladebalken bei 0% starten (als Download)
            this.updateUploadProgress(0, 'Update-Paket wird erstellt...', false, true);
            
            this.toast('Update-Paket wird erstellt...', 'info');
            
            // Animierter Fortschritt während des Exports
            progressInterval = setInterval(() => {
                if (currentProgress < 90) {
                    currentProgress += Math.random() * 3 + 1; // Langsam zunehmen bis 90%
                    if (currentProgress > 90) currentProgress = 90;
                    this.updateUploadProgress(currentProgress, 'Update-Paket wird erstellt...', false, true);
                }
            }, 200);
            
            const data = await this.apiPost('/admin/update/export');
            
            // Timer stoppen
            clearInterval(progressInterval);
            
            // Ladebalken komplett ausblenden
            const panel = document.getElementById('uploadProgressPanel');
            if (panel) panel.classList.add('hidden');
            
            if (data.success) {
                this.toast(`Update-Paket "${data.filename}" erfolgreich erstellt`, 'success');
                
                // Download-Link anzeigen
                const downloadUrl = `/api/admin/update/download/${data.filename}`;
                const downloadHtml = `
                    <div class="mt-2">
                        <a href="${downloadUrl}" download="${data.filename}" class="btn btn-sm btn-primary">
                            <i class="fas fa-download"></i> ${data.filename} herunterladen
                        </a>
                    </div>
                `;
                
                const container = document.getElementById('updateStatusContainer');
                const text = document.getElementById('updateStatusText');
                
                if (container) container.classList.remove('hidden');
                if (text) text.innerHTML = downloadHtml;
            }
        } catch (e) {
            // Timer stoppen bei Fehler
            if (progressInterval) clearInterval(progressInterval);
            
            // Ladebalken ausblenden bei Fehler
            const panel = document.getElementById('uploadProgressPanel');
            if (panel) panel.classList.add('hidden');
            this.toast(e.message, 'error');
        }
    },

    // ── Reminders (Erinnerungn) ─────────────────
    async loadReminders() {
        // Im Offline-Modus überspringen
        if (this.currentUser?.username === 'Offline-Modus') {
            console.log('Offline-Modus: Reminders überspringen');
            this.reminders = [];
            this.updateReminderBadge();
            return;
        }
        try {
            const data = await this.apiGet('/records/reminders?all=true&include_completed=true', false);
            this.reminders = data.reminders || [];
            this.updateReminderBadge();
            this.renderReminderPanel();
            // Re-render records to update bell icons
            this.renderRecords();
        } catch (e) {
            console.error('Fehler beim Laden der Erinnerungn:', e);
        }
    },

    updateReminderBadge() {
        const badge = document.getElementById('reminderBadge');
        if (badge) {
            const today = new Date();
            today.setHours(0,0,0,0);
            const count = this.reminders.filter(r => {
                if (r.completed === 1) return false;
                // Only count reminders assigned to current user or all (NULL)
                if (r.assigned_to !== null && r.assigned_to !== this.currentUser?.id) return false;
                const reminderDate = new Date(r.reminder_date);
                reminderDate.setHours(0,0,0,0);
                return reminderDate.getTime() === today.getTime();
            }).length;
            badge.textContent = count;
            badge.classList.toggle('hidden', count === 0);
        }
    },

    toggleReminderPanel() {
        // Only toggle filter if there are active reminders today for current user
        const today = new Date();
        today.setHours(0,0,0,0);
        const activeReminders = this.reminders.filter(r => {
            if (r.completed === 1) return false;
            // Only consider reminders assigned to current user or all (NULL)
            if (r.assigned_to !== null && r.assigned_to !== this.currentUser?.id) return false;
            const reminderDate = new Date(r.reminder_date);
            reminderDate.setHours(0,0,0,0);
            return reminderDate.getTime() === today.getTime();
        });
        
        if (activeReminders.length > 0) {
            this.reminderFilterActive = !this.reminderFilterActive;
            // Update button styling
            const bellBtn = document.getElementById('reminderBtn');
            if (bellBtn) {
                bellBtn.classList.toggle('reminder-filter-active', this.reminderFilterActive);
            }
            // Reload records to apply filter
            this.loadRecords();
        }
        const panel = document.getElementById('reminderPanel');
        if (panel) {
            panel.classList.toggle('hidden');
        }
    },

    renderReminderPanel() {
        const list = document.getElementById('reminderList');
        if (!list) return;
        
        // Filter to today's reminders only for current user or all (NULL)
        const today = new Date();
        today.setHours(0,0,0,0);
        const activeReminders = this.reminders.filter(r => {
            if (r.completed === 1) return false;
            // Only consider reminders assigned to current user or all (NULL)
            if (r.assigned_to !== null && r.assigned_to !== this.currentUser?.id) return false;
            const reminderDate = new Date(r.reminder_date);
            reminderDate.setHours(0,0,0,0);
            return reminderDate.getTime() === today.getTime();
        });
        
        if (activeReminders.length === 0) {
            list.innerHTML = '<p class="text-muted text-center py-4">Keine Erinnerungn heute</p>';
            return;
        }

        list.innerHTML = activeReminders.map(r => {
            const date = new Date(r.reminder_date);
            const dateStr = date.toLocaleDateString('de-DE');
            const assignedTo = r.assigned_to_username || 'Alle';
            const createdBy = r.created_by_username || 'Unbekannt';
            return `
                <div class="reminder-item">
                    <div class="reminder-item-header">
                        <strong>${r.number}: ${r.title}</strong>
                    </div>
                    <div style="display:flex; align-items:center; gap:12px; margin-bottom:4px;">
                        <div class="reminder-item-date">${dateStr}</div>
                        <span class="text-muted" style="font-size:12px;">Zugewiesen an: ${assignedTo} von ${createdBy}</span>
                    </div>
                    ${r.note ? `
                        <div style="display:flex; align-items:flex-start; gap:8px;">
                            <span class="reminder-item-date" style="font-size:12px; font-weight:normal;">Notiz:</span>
                            <div style="font-size:12px; color:#666; flex:1;">${this.escapeHtml(r.note)}</div>
                        </div>
                    ` : ''}
                    <div class="reminder-item-actions">
                        <button type="button" class="btn btn-sm btn-secondary" onclick="App.openRecord(${r.record_id})">
                            <i class="fas fa-folder-open"></i> Öffnen
                        </button>
                        <button type="button" class="btn btn-sm btn-success" onclick="App.completeReminder(${r.id})">
                            <i class="fas fa-check"></i> Erledigt
                        </button>
                    </div>
                </div>
            `;
        }).join('');
    },

    async loadRecordReminders(recordId) {
        try {
            const data = await this.apiGet(`/records/${recordId}/reminders`, false);
            this.renderRecordReminders(data.reminders || []);
        } catch (e) {
            console.error('Fehler beim Laden der Akten-Erinnerungn:', e);
        }
    },

    renderRecordReminders(reminders) {
        const list = document.getElementById('recordReminderList');
        const addButton = document.querySelector('.reminders-section .btn-primary');
        if (!list) return;
        
        // Hide add button if there's already an active (non-completed) reminder
        const hasActiveReminder = reminders.some(r => r.completed !== 1);
        if (addButton) {
            addButton.style.display = hasActiveReminder ? 'none' : 'inline-flex';
        }
        
        if (reminders.length === 0) {
            list.innerHTML = '';
            return;
        }

        list.innerHTML = reminders.map(r => {
            const date = new Date(r.reminder_date);
            const dateStr = date.toLocaleDateString('de-DE');
            const assignedTo = r.assigned_to_username || 'Alle';
            const createdBy = r.created_by_username || 'Unbekannt';
            return `
                <div class="reminder-item-in-modal attachment-item">
                    <div class="attachment-thumb">
                        <div class="thumb-icon">
                            <i class="fas fa-bell"></i>
                        </div>
                    </div>
                    <div style="display:flex; flex-direction:column; gap:4px; min-width:0; flex:1;">
                        <div style="display:flex; align-items:center; gap:8px;">
                            <strong>${dateStr}</strong>
                            <span class="text-muted" style="font-size:12px;">Zugewiesen an: ${assignedTo} von ${createdBy}</span>
                        </div>
                        ${r.note ? `
                            <div style="display:flex; align-items:flex-start; gap:8px;">
                                <div style="font-size:12px; color:#666; flex:1;">${this.escapeHtml(r.note)}</div>
                            </div>
                        ` : ''}
                    </div>
                    <div class="attachment-actions">
                        ${r.id ? `
                            ${!r.completed ? `
                                <button type="button" class="btn btn-sm btn-secondary" onclick="App.completeReminder(${r.id})" title="Erledigt">
                                    <i class="fas fa-check"></i>
                                </button>
                            ` : ''}
                            <button type="button" class="btn btn-sm btn-secondary" onclick="App.editReminder(${JSON.stringify(r).replace(/"/g, '&quot;')})" title="Bearbeiten">
                                <i class="fas fa-edit"></i>
                            </button>
                            <button type="button" class="btn btn-sm btn-danger" onclick="App.deleteReminder(${r.id})" title="Löschen">
                                <i class="fas fa-trash"></i>
                            </button>
                        ` : ''}
                    </div>
                </div>
            `;
        }).join('');
    },

    openReminderModal(reminder = null) {
        const modal = document.getElementById('reminderModalOverlay');
        if (!modal) return;
        
        document.getElementById('reminderRecordId').value = this.editingId;
        document.getElementById('reminderId').value = reminder ? reminder.id : '';
        document.getElementById('reminderDate').value = '';
        document.getElementById('reminderDateValue').value = '';
        document.getElementById('reminderAssignedTo').value = this.currentUser.id;
        document.getElementById('reminderNote').value = '';
        
        if (reminder) {
            // Update modal title for edit
            document.querySelector('#reminderModal h3').textContent = 'Erinnerung bearbeiten';
            // Populate fields
            const date = new Date(reminder.reminder_date);
            const dateStr = date.toLocaleDateString('de-DE');
            document.getElementById('reminderDate').value = dateStr;
            document.getElementById('reminderDateValue').value = reminder.reminder_date;
            document.getElementById('reminderAssignedTo').value = reminder.assigned_to || '';
            document.getElementById('reminderNote').value = reminder.note || '';
        } else {
            document.querySelector('#reminderModal h3').textContent = 'Erinnerung hinzufügen';
        }
        
        // Reset reminder date picker state
        this.reminderDateTimePickerState.currentDate = new Date();
        this.reminderDateTimePickerState.selectedDate = null;
        this.reminderDateTimePickerState.isOpen = false;
        
        // Load users for dropdown (sofort aktualisieren)
        this.loadUsersForReminderDropdown(reminder ? reminder.assigned_to : this.currentUser.id);
        
        modal.classList.add('show');
    },
    
    editReminder(reminder) {
        this.openReminderModal(reminder);
    },

    async loadUsersForReminderDropdown(selectedValue = null) {
        try {
            const users = await this.apiGet('/records/users', false);
            this.cachedUsers = users.users || [];
            const menu = document.getElementById('reminderAssignMenu');
            const dropdown = document.getElementById('reminderAssignDropdown');
            if (!menu || !dropdown || !users.users) return;
            
            // Keep "Alle" option
            menu.innerHTML = `
                <button type="button" data-value="">
                    <i class="fas fa-users"></i> <span>Alle</span>
                </button>
            `;
            
            users.users.forEach(u => {
                const btn = document.createElement('button');
                btn.type = 'button';
                btn.dataset.value = u.id;
                btn.innerHTML = `<i class="fas fa-user"></i> <span>${this.escapeHtml(u.username)}</span>`;
                menu.appendChild(btn);
            });
            
            // Set default to current user and update UI
            const dropdownBtn = dropdown.querySelector('.dropdown-toggle');
            const reminderInput = document.getElementById('reminderAssignedTo');
            if (dropdownBtn) {
                const valueToSet = selectedValue !== null ? selectedValue : (this.currentUser?.id);
                reminderInput.value = valueToSet;
                // Find the button for selected value and set selected class and toggle text
                const selectedBtn = menu.querySelector(`button[data-value="${valueToSet}"]`);
                if (selectedBtn) {
                    dropdownBtn.innerHTML = selectedBtn.innerHTML;
                    selectedBtn.classList.add('selected');
                }
                
                // Toggle-Event-Listener neu binden
                dropdownBtn.onclick = (e) => {
                    e.stopPropagation();
                    // Alle anderen modal dropdowns schließen
                    document.querySelectorAll('.custom-modal-dropdown').forEach(d => {
                        if (d !== dropdown) d.classList.remove('show');
                    });
                    dropdown.classList.toggle('show');
                };
                
                // Event-Listener für die neuen Buttons neu binden
                menu.querySelectorAll('button').forEach(btn => {
                    btn.addEventListener('click', () => {
                        const val = btn.dataset.value;
                        reminderInput.value = val;
                        dropdownBtn.innerHTML = btn.innerHTML;
                        dropdown.classList.remove('show');
                        // Update selected class
                        menu.querySelectorAll('button').forEach(b => b.classList.remove('selected'));
                        btn.classList.add('selected');
                    });
                });
            }
        } catch (e) {
            console.error('Fehler beim Laden der Benutzer für Dropdown (Server offline):', e);
            // Offline: Nichts tun - das ursprüngliche Dropdown-Menü bleibt erhalten
            // Das initModalDropdowns sorgt bereits für die korrekte Funktionalität
        }
    },

    closeReminderModal() {
        const modal = document.getElementById('reminderModalOverlay');
        if (modal) {
            modal.classList.remove('show');
        }
    },

    openReminderDateTimePicker() {
        this.reminderDateTimePickerState.isOpen = true;
        this.reminderDateTimePickerState.currentDate = new Date();
        
        // Parse existing value if any
        const existingValue = document.getElementById('reminderDate').value;
        if (existingValue) {
            // Deutsches Format DD.MM.YYYY parsen
            const parts = existingValue.split('.');
            if (parts.length === 3) {
                const date = new Date(parts[2], parts[1] - 1, parts[0]);
                if (!isNaN(date.getTime())) {
                    this.reminderDateTimePickerState.selectedDate = date;
                    this.reminderDateTimePickerState.currentDate = new Date(date);
                }
            }
        } else {
            // Default to today
            this.reminderDateTimePickerState.selectedDate = new Date();
        }
        
        this.renderReminderDateTimePicker();
        document.getElementById('reminderDateTimePickerModal').classList.add('show');
    },

    closeReminderDateTimePicker() {
        this.reminderDateTimePickerState.isOpen = false;
        document.getElementById('reminderDateTimePickerModal').classList.remove('show');
    },

    renderReminderDateTimePicker() {
        const d = this.reminderDateTimePickerState.currentDate;
        const year = d.getFullYear();
        const month = d.getMonth();
        
        // Update header
        const title = document.getElementById('reminderDateTimeMonthYear');
        title.textContent = d.toLocaleDateString('de-DE', { month: 'long', year: 'numeric' });
        
        // Calculate calendar days
        const firstDay = new Date(year, month, 1).getDay();
        const daysInMonth = new Date(year, month + 1, 0).getDate();
        const startOffset = firstDay === 0 ? 6 : firstDay - 1; // Monday start
        
        let html = '';
        
        // Weekday headers
        ['Mo','Di','Mi','Do','Fr','Sa','So'].forEach(w => {
            html += `<div class="datetime-weekday">${w}</div>`;
        });
        
        // Empty cells before month starts
        for (let i = 0; i < startOffset; i++) {
            html += `<div class="datetime-day disabled"></div>`;
        }
        
        // Days of month
        const today = new Date();
        for (let day = 1; day <= daysInMonth; day++) {
            const currentDate = new Date(year, month, day);
            const isToday = day === today.getDate() && month === today.getMonth() && year === today.getFullYear();
            const isSelected = this.reminderDateTimePickerState.selectedDate && 
                day === this.reminderDateTimePickerState.selectedDate.getDate() && 
                month === this.reminderDateTimePickerState.selectedDate.getMonth() && 
                year === this.reminderDateTimePickerState.selectedDate.getFullYear();
            const isPast = currentDate < today && !isToday;
            
            let classes = 'datetime-day';
            if (isToday) classes += ' today';
            if (isSelected) classes += ' selected';
            if (isPast) classes += ' disabled';
            
            html += `<div class="${classes}" ${!isPast ? `onclick="App.selectReminderDate(${year}, ${month}, ${day})"` : ''}>${day}</div>`;
        }
        
        document.getElementById('reminderDateTimeCalendarGrid').innerHTML = html;
    },

    selectReminderDate(year, month, day) {
        this.reminderDateTimePickerState.selectedDate = new Date(year, month, day);
        this.renderReminderDateTimePicker();
    },

    changeReminderDateTimeMonth(delta) {
        this.reminderDateTimePickerState.currentDate.setMonth(this.reminderDateTimePickerState.currentDate.getMonth() + delta);
        this.renderReminderDateTimePicker();
    },

    setReminderDate() {
        if (!this.reminderDateTimePickerState.selectedDate) {
            this.reminderDateTimePickerState.selectedDate = new Date();
        }
        
        const date = this.reminderDateTimePickerState.selectedDate;
        const year = date.getFullYear();
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const day = String(date.getDate()).padStart(2, '0');
        
        const formattedDate = `${year}-${month}-${day}`;
        const displayStr = `${day}.${month}.${year}`;
        
        // Update hidden input (ISO for backend)
        document.getElementById('reminderDateValue').value = formattedDate;
        
        // Update visible input (German format for user)
        document.getElementById('reminderDate').value = displayStr;
        
        this.closeReminderDateTimePicker();
    },

    clearReminderDate() {
        document.getElementById('reminderDateValue').value = '';
        document.getElementById('reminderDate').value = '';
    },

    async completeReminder(reminderId) {
        try {
            await this.apiPut(`/records/reminders/${reminderId}`, { completed: true });
            this.toast('Erinnerung als erledigt markiert.', 'success');
            await this.loadReminders();
            if (this.editingId) {
                await this.loadRecordReminders(this.editingId);
            }
            // Re-render records to update bell icons
            this.renderRecords();
        } catch (e) {
            this.toast(e.message, 'error');
        }
    },

    async deleteReminder(reminderId) {
        if (!await this.confirm('Erinnerung löschen?', 'Diese Erinnerung wird endgültig gelöscht.')) return;
        
        try {
            await this.apiDelete(`/records/reminders/${reminderId}`);
            this.toast('Erinnerung gelöscht.', 'success');
            await this.loadReminders();
            if (this.editingId) {
                await this.loadRecordReminders(this.editingId);
            }
            // Re-render records to update bell icons
            this.renderRecords();
        } catch (e) {
            this.toast(e.message, 'error');
        }
    },

    async saveReminder(e) {
        e.preventDefault();
        
        const recordId = Number(document.getElementById('reminderRecordId').value);
        const reminderId = document.getElementById('reminderId').value;
        const reminderDate = document.getElementById('reminderDateValue').value;
        const assignedTo = document.getElementById('reminderAssignedTo').value;
        const note = document.getElementById('reminderNote').value;
        
        if (!reminderDate) {
            this.toast('Bitte wählen Sie ein Datum aus.', 'error');
            return;
        }
        
        try {
            // Prüfen ob Offline-Akte
            const currentRecord = this.records.find(r => r.id === recordId);
            const isOfflineRecord = currentRecord?.is_offline || false;
            
            if (!this.editingId && !reminderId) {
                // Neue Akte wird erstellt: Erinnerung als pending speichern
                this.pendingReminder = {
                    reminder_date: reminderDate,
                    assigned_to: assignedTo ? Number(assignedTo) : null,
                    note: note
                };
                // Keine Toast-Meldung - Erinnerung wird mit der Akte gespeichert
                this.closeReminderModal();
                // Zeige die pending Reminder im Modal
                this.renderRecordReminders([{
                    id: null,
                    reminder_date: reminderDate,
                    assigned_to: assignedTo ? Number(assignedTo) : null,
                    assigned_to_username: assignedTo ? (this.cachedUsers || []).find(u => u.id === Number(assignedTo))?.username : 'Alle',
                    created_by: this.currentUser.id,
                    created_by_username: this.currentUser.username,
                    note: note,
                    completed: 0
                }]);
                // Hide add button
                const addButton = document.querySelector('.reminders-section .btn-primary');
                if (addButton) addButton.style.display = 'none';
                return;
            }
            
            if (isOfflineRecord) {
                // Offline: Erinnerung lokal speichern
                if (!currentRecord.erinnerungen) currentRecord.erinnerungen = [];
                currentRecord.erinnerungen.push({
                    id: Date.now(), // Temporäre ID
                    reminder_date: reminderDate,
                    assigned_to: assignedTo ? Number(assignedTo) : null,
                    note: note,
                    completed: 0,
                    created_by: this.currentUser.id,
                    created_by_username: this.currentUser.username
                });
                await OfflineStorage.updatePendingRecord(currentRecord.temp_id, currentRecord);
                this.toast('Erinnerung offline gespeichert (wird später synchronisiert)', 'success');
                this.closeReminderModal();
                // Nur die Erinnerungen im Modal neu rendern, nicht die ganze Liste
                this.renderRecordReminders(currentRecord.erinnerungen);
                // Glocken-Symbol in der Liste aktualisieren ohne komplettes Re-Rendering
                this.updateRecordBellIcon(currentRecord.id);
                return;
            }
            
            if (reminderId) {
                // Update existing reminder
                await this.apiPut(`/records/reminders/${reminderId}`, {
                    reminder_date: reminderDate,
                    assigned_to: assignedTo ? Number(assignedTo) : null,
                    note: note
                });
                this.toast('Erinnerung aktualisiert.', 'success');
                this.closeReminderModal();
                await this.loadReminders();
                await this.loadRecordReminders(recordId);
                // Re-render records to update bell icons
                this.renderRecords();
            } else {
                // Create new reminder for existing record
                await this.apiPost(`/records/${recordId}/reminders`, {
                    reminder_date: reminderDate,
                    assigned_to: assignedTo ? Number(assignedTo) : null,
                    note: note
                });
                this.toast('Erinnerung erstellt.', 'success');
                this.closeReminderModal();
                await this.loadReminders();
                await this.loadRecordReminders(recordId);
                // Re-render records to update bell icons
                this.renderRecords();
            }
        } catch (e) {
            this.toast(e.message, 'error');
        }
    },

    async loadGalleryPreferences() {
        // Im Offline-Modus überspringen
        if (this.currentUser?.username === 'Offline-Modus' || this.galleryIsOffline) {
            console.log('Offline-Modus: Gallery Preferences überspringen');
            return;
        }
        try {
            const data = await this.apiGet('/gallery/preferences', false);
            if (data.success && data.preferences) {
                // Werte in den UI-Elementen setzen
                const thresholdInput = document.getElementById('similarityThreshold');
                const textWeightInput = document.getElementById('textWeight');
                const thresholdValue = document.getElementById('thresholdValue');
                const textWeightValue = document.getElementById('textWeightValue');
                
                if (thresholdInput && data.preferences.similarity_threshold !== undefined) {
                    thresholdInput.value = data.preferences.similarity_threshold;
                    if (thresholdValue) thresholdValue.textContent = data.preferences.similarity_threshold;
                }
                
                if (textWeightInput && data.preferences.text_deviation !== undefined) {
                    // text_deviation ist Schlagworte-Gewichtung (0-1), direkt als Prozent anzeigen
                    const textWeightPercent = Math.round(data.preferences.text_deviation * 100);
                    textWeightInput.value = textWeightPercent;
                    if (textWeightValue) textWeightValue.textContent = textWeightPercent;
                }
            }
        } catch (e) {
            console.error('Fehler beim Laden der Galerie-Einstellungen:', e);
            // Standardwerte bei Fehler
            const thresholdInput = document.getElementById('similarityThreshold');
            const textWeightInput = document.getElementById('textWeight');
            const thresholdValue = document.getElementById('thresholdValue');
            const textWeightValue = document.getElementById('textWeightValue');
            
            if (thresholdInput) thresholdInput.value = 26;
            if (thresholdValue) thresholdValue.textContent = 26;
            if (textWeightInput) textWeightInput.value = 30;
            if (textWeightValue) textWeightValue.textContent = 30;
        }
    },

    async saveGalleryPreferences() {
        try {
            const threshold = document.getElementById('similarityThreshold')?.value || 26;
            const textAccuracy = (document.getElementById('textWeight')?.value || 30) / 100;
            
            await this.apiPost('/gallery/preferences', {
                similarity_threshold: parseInt(threshold),
                text_deviation: parseFloat(textAccuracy)
            });
        } catch (e) {
            console.error('Fehler beim Speichern der Galerie-Einstellungen:', e);
        }
    },

    async loadGallery(loadMore = false, showLoadingOverlay = true) {
        try {
            if (showLoadingOverlay) {
                this.showLoading(true);
            }

            // Wenn manueller Offline-Modus aktiv ist, nicht versuchen, Daten zu laden
            if (this.manualOfflineMode) {
                console.log('📡 Galerie: Manueller Offline-Modus aktiv - Daten werden nicht neu geladen');
                // Galerie mit vorhandenen Daten rendern (falls vorhanden)
                if (this.galleryMedia && this.galleryMedia.length > 0) {
                    this.renderGallery(false);
                } else {
                    this.galleryMedia = [];
                    this.renderGallery(false);
                }
                return;
            }

            // Prüfen ob offline (ohne Server-Verbindung)
            let isOffline = false;
            if (typeof OfflineStorage !== 'undefined') {
                isOffline = !(await OfflineStorage.isOnline());
            }

            if (isOffline) {
                console.log('Galerie: Offline-Modus erkannt, keine Server-Verbindung');
                // Keine Fehlermeldung, einfach leere Liste anzeigen wie beim Kalender
                this.galleryMedia = [];
                this.renderGallery(false);
                return;
            }
            
            const filterVal = document.getElementById('galleryFilter')?.value || 'all';
            const sortVal = document.getElementById('gallerySort')?.value || 'newest';
            const categoryVal = document.getElementById('galleryCategory')?.value || '';
            const searchVal = document.getElementById('gallerySearch')?.value?.trim() || '';

            let data;
            
            // Ähnliche Bilder Suche (Reverse Image Search)
            if (this.galleryReferenceImageIds && this.galleryReferenceImageIds.length > 0) {
                const attachmentIds = this.galleryReferenceImageIds.map(id => parseInt(id.replace('att_', '')));
                const threshold = document.getElementById('similarityThreshold')?.value || 26;
                const textAccuracy = (document.getElementById('textWeight')?.value || 30) / 100;
                const params = new URLSearchParams({
                    limit: 50,
                    max_distance: threshold,
                    text_weight: textAccuracy
                });
                
                // Mehrere Attachment-IDs als Parameter übergeben
                attachmentIds.forEach((id, index) => {
                    params.append(`reference_ids[]`, id);
                });
                
                if (loadMore) {
                    params.set('offset', this.galleryMedia.length);
                }
                data = await this.apiGet(`/gallery/similar-images?${params.toString()}`, false);
            } else {
                // Normale Suche
                const params = new URLSearchParams({
                    filter: filterVal,
                    sort: sortVal,
                    limit: 50
                });
                if (categoryVal) params.set('category', categoryVal);
                if (searchVal) params.set('search', searchVal);
                if (this.gallerySearchType) params.set('search_type', this.gallerySearchType);
                if (loadMore) {
                    params.set('offset', this.galleryMedia.length);
                }
                data = await this.apiGet(`/gallery?${params.toString()}`, false);
            }
            
            if (loadMore) {
                this.galleryMedia = [...this.galleryMedia, ...(data.media || [])];
            } else {
                this.galleryMedia = data.media || [];
            }
            this.galleryPagination = data.pagination;
            this.renderGallery(loadMore);
        } catch (e) {
            console.error('Fehler beim Laden der Galerie:', e);
            this.toast('Fehler beim Laden der Galerie: ' + e.message, 'error');
            // Bei Fehler leere Liste anzeigen
            if (!loadMore) {
                this.galleryMedia = [];
                this.renderGallery(false);
            }
        } finally {
            if (showLoadingOverlay) {
                this.showLoading(false);
            }
        }
    },

    async loadMoreGallery() {
        if (this.galleryLoadingMore) return;
        this.galleryLoadingMore = true;
        await this.loadGallery(true, false);
        this.galleryLoadingMore = false;
    },

    renderGallery(append = false) {
        const grid = document.getElementById('galleryGrid');
        const empty = document.getElementById('galleryEmpty');
        const pagination = document.getElementById('galleryPagination');
        if (!grid || !empty || !pagination) return;

        const items = this.galleryMedia;

        // Offline-Status prüfen (enters über galleryIsOffline Flag oder OfflineStorage)
        let isOffline = this.galleryIsOffline;
        if (!isOffline && typeof OfflineStorage !== 'undefined') {
            isOffline = !(OfflineStorage.isOnline && OfflineStorage.isOnline());
        }

        if (items.length === 0 && !append) {
            // Im Offline-Modus keine "Keine Medien vorhanden" Nachricht zeigen
            // UI-Elemente (Suchfelder, Filter) bleiben sichtbar durch das HTML
            if (isOffline) {
                empty.classList.add('hidden');
                grid.innerHTML = '';
                pagination.classList.add('hidden');
                // Header mit Suchfeldern bleibt automatisch sichtbar
                return;
            }
            grid.innerHTML = '';
            empty.classList.remove('hidden');
            pagination.innerHTML = '';
            pagination.classList.add('hidden');
            return;
        }

        empty.classList.add('hidden');

        // Update selection state after render
        if (this.auswahlIstAktiv && this.auswahlIds.size > 0) {
            setTimeout(() => {
                this.aktualisiereAuswahlDarstellungNachRender();
            }, 0);
        }
        
        const itemsToRender = append ? items.slice(-this.galleryPagination?.limit || 50) : items;
        
        // Performance: Virtual Scrolling für sehr große Listen (> 100 Items)
        if (itemsToRender.length > 100 && !append) {
            this.renderVirtualGallery(itemsToRender);
            return;
        }
        
        // Performance: Bei kleinen Listen (< 50 Items) direkt rendern ohne Chunking
        if (itemsToRender.length < 50 && !append) {
            // Performance: CSS Containment für bessere Rendering-Performance
            grid.style.contain = 'layout style paint';
            
            const html = itemsToRender.map((item, idx) => {
                const isVideo = item.mime_type?.startsWith('video/');
                const isAudio = item.mime_type?.startsWith('audio/');
                const isPdf = item.mime_type === 'application/pdf';
                // PDFs aus der Galerie-Bild-Ansicht ausschließen
                if (isPdf) return '';
                let mediaUrl;
                let thumbnailUrl;
                if (item.type === 'attachment') {
                    mediaUrl = `/api/records/${item.record_id}/files/${encodeURIComponent(item.filename)}`;
                    // Performance: Thumbnail für Gallery-Ansicht verwenden (direkt ID ohne Präfix)
                    thumbnailUrl = `/api/gallery/thumbnail/${item.id}?size=200`;
                } else {
                    mediaUrl = `/api/gallery/${encodeURIComponent(item.id)}`;
                    thumbnailUrl = mediaUrl; // Für Galerie-Medien keine Thumbnails verfügbar
                }
                
                const borderClass = item.record_color ? item.record_color : '';
                const createdDate = this.formatDate(item.created_at);
                const filename = item.filename || item.original_filename || 'Unbenannt';
                
                return `
                    <div class="record-card gallery-card ${borderClass}" data-record-id="${item.id}" onclick="App.openGalleryLightbox(${idx})">
                        <button class="auswahl-indikator" type="button" aria-label="Bild auswählen" aria-pressed="${this.auswahlIds.has(item.id) ? 'true' : 'false'}" onclick="event.stopPropagation(); App.umschaltenAkteAuswahl('${item.id}')">
                            <i class="fas fa-check"></i>
                        </button>
                        <div class="record-title gallery-title">${this.escapeHtml(filename)}</div>
                        <div class="gallery-media">
                            ${isAudio
                                ? `<div class="gallery-audio-wrapper" data-audio-url="${mediaUrl}">
                                    <div class="gallery-audio-viz-slot"></div>
                                    <div class="gallery-audio-controls">
                                        <button class="gallery-audio-play-btn" onclick="event.stopPropagation(); App.toggleGalleryAudio(this)">
                                            <i class="fas fa-play"></i>
                                        </button>
                                        <div class="gallery-audio-progress">
                                            <div class="gallery-audio-progress-bar"></div>
                                        </div>
                                        <div class="gallery-audio-volume">
                                            <i class="fas fa-volume-up gallery-audio-volume-icon"></i>
                                            <input type="range" class="gallery-audio-volume-slider" min="0" max="1" step="0.1" value="1" onclick="event.stopPropagation()">
                                        </div>
                                    </div>
                                    <audio src="${mediaUrl}" class="gallery-audio-hidden" preload="none"></audio>
                                   </div>`
                                : isVideo
                                ? `<video src="${mediaUrl}" class="gallery-media-element" muted playsinline disablePictureInPicture controlsList="nodownload nopictureinpicture noremoteplayback nofullscreen" preload="metadata" loading="lazy"></video>`
                                : `<img src="${thumbnailUrl}" class="gallery-media-element" alt="${this.escapeHtml(filename)}" loading="lazy" fetchpriority="low" data-full-url="${mediaUrl}">`
                            }
                        </div>
                        <div class="record-meta">
                            <div class="meta-row">
                                ${item.type === 'gallery' 
                                    ? `<span class="meta-author gallery-meta-item">
                                        <i class="fas fa-folder" style="margin-right:4px;opacity:0.6"></i>
                                        <span class="gallery-meta-value">Galerie</span>
                                    </span>` 
                                    : `<span class="meta-author gallery-meta-item">
                                        <i class="fas fa-folder" style="margin-right:4px;opacity:0.6"></i>
                                        <span class="gallery-meta-value">${this.escapeHtml(item.record_title || 'Akte ohne Namen')}</span>
                                    </span>`
                                }
                                <span class="meta-author gallery-meta-item gallery-meta-date">
                                    <span class="gallery-meta-value">${createdDate}</span>
                                </span>
                            </div>
                        </div>
                        ${item.type === 'gallery' 
                            ? `<button class="btn btn-sm btn-danger" style="position:absolute; top:12px; right:12px; z-index:10; width:32px; height:32px; padding:0; display:flex; align-items:center; justify-content:center;" onclick="event.stopPropagation(); App.deleteGalleryMedia(${item.id})"><i class="fas fa-trash"></i></button>` 
                            : ''
                        }
                    </div>
                `;
            }).join('');
            
            grid.innerHTML = html;
            this.initializeVisibleAudioVisualizers();
        } else {
            // Performance: CSS Containment für bessere Rendering-Performance
            grid.style.contain = 'layout style paint';
            
            // Performance: Hardware-Beschleunigung für Scroll-Performance
            grid.style.willChange = 'transform';
            
            // Performance: Größere Chunks für weniger requestAnimationFrame-Aufrufe
            const chunkSize = 30; // 30 Items pro Chunk (bessere Balance)
            const chunks = [];
            for (let i = 0; i < itemsToRender.length; i += chunkSize) {
                chunks.push(itemsToRender.slice(i, i + chunkSize));
            }
            
            // Performance: DocumentFragment für effizienteres DOM-Insertion
            const fragment = document.createDocumentFragment();
            const tempDiv = document.createElement('div');
        
            const renderChunk = (chunkIndex) => {
                if (chunkIndex >= chunks.length) {
                    // Alle Chunks gerendert - Audio-Visualizer nur für sichtbare initialisieren
                    this.initializeVisibleAudioVisualizers();
                    // will-change entfernen wenn nicht mehr benötigt
                    setTimeout(() => grid.style.willChange = '', 1000);
                    return;
                }
                
                const chunk = chunks[chunkIndex];
                const html = chunk.map((item, idxInChunk) => {
                    const originalIndex = append ? (items.length - itemsToRender.length + (chunkIndex * chunkSize) + idxInChunk) : (chunkIndex * chunkSize) + idxInChunk;
                    const isVideo = item.mime_type?.startsWith('video/');
                    const isAudio = item.mime_type?.startsWith('audio/');
                    const isPdf = item.mime_type === 'application/pdf';
                    // PDFs aus der Galerie-Bild-Ansicht ausschließen
                    if (isPdf) return '';
                    let mediaUrl;
                    let thumbnailUrl;
                    if (item.type === 'attachment') {
                        mediaUrl = `/api/records/${item.record_id}/files/${encodeURIComponent(item.filename)}`;
                        // Performance: Thumbnail für Gallery-Ansicht verwenden (direkt ID ohne Präfix)
                        thumbnailUrl = `/api/gallery/thumbnail/${item.id}?size=200`;
                    } else {
                        mediaUrl = `/api/gallery/${encodeURIComponent(item.id)}`;
                        thumbnailUrl = mediaUrl; // Für Galerie-Medien keine Thumbnails verfügbar
                    }
                    
                    const borderClass = item.record_color ? item.record_color : '';
                    const createdDate = this.formatDate(item.created_at);
                    const filename = item.filename || item.original_filename || 'Unbenannt';
                    
                    return `
                        <div class="record-card gallery-card ${borderClass}" data-record-id="${item.id}" onclick="App.openGalleryLightbox(${originalIndex})">
                            <button class="auswahl-indikator" type="button" aria-label="Bild auswählen" aria-pressed="${this.auswahlIds.has(item.id) ? 'true' : 'false'}" onclick="event.stopPropagation(); App.umschaltenAkteAuswahl('${item.id}')">
                                <i class="fas fa-check"></i>
                            </button>
                            <div class="record-title gallery-title">${this.escapeHtml(filename)}</div>
                            <div class="gallery-media">
                                ${isAudio
                                    ? `<div class="gallery-audio-wrapper" data-audio-url="${mediaUrl}">
                                        <div class="gallery-audio-viz-slot"></div>
                                        <div class="gallery-audio-controls">
                                            <button class="gallery-audio-play-btn" onclick="event.stopPropagation(); App.toggleGalleryAudio(this)">
                                                <i class="fas fa-play"></i>
                                            </button>
                                            <div class="gallery-audio-progress">
                                                <div class="gallery-audio-progress-bar"></div>
                                            </div>
                                            <div class="gallery-audio-volume">
                                                <i class="fas fa-volume-up gallery-audio-volume-icon"></i>
                                                <input type="range" class="gallery-audio-volume-slider" min="0" max="1" step="0.1" value="1" onclick="event.stopPropagation()">
                                            </div>
                                        </div>
                                        <audio src="${mediaUrl}" class="gallery-audio-hidden" preload="none"></audio>
                                       </div>`
                                    : isVideo
                                    ? `<video src="${mediaUrl}" class="gallery-media-element" muted playsinline disablePictureInPicture controlsList="nodownload nopictureinpicture noremoteplayback nofullscreen" preload="metadata" loading="lazy"></video>`
                                    : `<img src="${thumbnailUrl}" class="gallery-media-element" alt="${this.escapeHtml(filename)}" loading="lazy" fetchpriority="low" data-full-url="${mediaUrl}">`
                                }
                            </div>
                            <div class="record-meta">
                                <div class="meta-row">
                                    ${item.type === 'gallery' 
                                        ? `<span class="meta-author gallery-meta-item">
                                            <i class="fas fa-folder" style="margin-right:4px;opacity:0.6"></i>
                                            <span class="gallery-meta-value">Galerie</span>
                                        </span>` 
                                        : `<span class="meta-author gallery-meta-item">
                                            <i class="fas fa-folder" style="margin-right:4px;opacity:0.6"></i>
                                            <span class="gallery-meta-value">${this.escapeHtml(item.record_title || 'Akte ohne Namen')}</span>
                                        </span>`
                                    }
                                    <span class="meta-author gallery-meta-item gallery-meta-date">
                                        <span class="gallery-meta-value">${createdDate}</span>
                                    </span>
                                </div>
                            </div>
                            ${item.type === 'gallery' 
                                ? `<button class="btn btn-sm btn-danger" style="position:absolute; top:12px; right:12px; z-index:10; width:32px; height:32px; padding:0; display:flex; align-items:center; justify-content:center;" onclick="event.stopPropagation(); App.deleteGalleryMedia(${item.id})"><i class="fas fa-trash"></i></button>` 
                                : ''
                            }
                        </div>
                    `;
                }).join('');

                // Performance: DocumentFragment statt direkter DOM-Manipulation
                tempDiv.innerHTML = html;
                while (tempDiv.firstChild) {
                    fragment.appendChild(tempDiv.firstChild);
                }
                
                if (append) {
                    grid.appendChild(fragment);
                } else {
                    if (chunkIndex === 0) {
                        grid.innerHTML = '';
                        grid.appendChild(fragment);
                    } else {
                        grid.appendChild(fragment);
                    }
                }
                
                // Nächsten Chunk mit requestAnimationFrame für bessere Performance
                requestAnimationFrame(() => renderChunk(chunkIndex + 1));
            };
            
            // Start gestaffeltes Rendering
            renderChunk(0);
        }
        
        // Update pagination button
        if (this.galleryPagination && items.length < this.galleryPagination.total) {
            pagination.classList.remove('hidden');
            pagination.innerHTML = `
                <button class="btn btn-secondary" onclick="App.loadMoreGallery()" ${this.galleryLoadingMore ? 'disabled' : ''}>
                    <i class="fas fa-plus"></i>
                    Mehr laden
                </button>
            `;
        } else {
            pagination.innerHTML = '';
            pagination.classList.add('hidden');
        }
    },
    
    initializeVisibleAudioVisualizers() {
        // Performance: Nur Audio-Visualizer für sichtbare Elemente initialisieren
        const grid = document.getElementById('galleryGrid');
        if (!grid) return;
        
        // Performance: Passive Observer für bessere Scroll-Performance
        const observer = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    const wrapper = entry.target;
                    if (wrapper._audioViz) return;
                    const audio = wrapper.querySelector('.gallery-audio-hidden');
                    if (audio) this.ensureGalleryAudioVisualizer(wrapper, audio);
                    observer.unobserve(wrapper);
                }
            });
        }, { rootMargin: '100px', passive: true });
        
        grid.querySelectorAll('.gallery-audio-wrapper').forEach(wrapper => {
            observer.observe(wrapper);
        });
    },
    
    renderVirtualGallery(items) {
        // Performance: Virtual Scrolling für sehr große Listen
        const grid = document.getElementById('galleryGrid');
        if (!grid) return;
        
        grid.style.contain = 'layout style paint';
        grid.style.willChange = 'transform';
        
        const itemHeight = 280; // Geschätzte Höhe pro Item
        const visibleCount = Math.ceil(window.innerHeight / itemHeight) + 5; // +5 Puffer
        const scrollTop = grid.scrollTop || 0;
        const startIndex = Math.max(0, Math.floor(scrollTop / itemHeight) - 2);
        const endIndex = Math.min(items.length, startIndex + visibleCount);
        
        const visibleItems = items.slice(startIndex, endIndex);
        
        // Padding für Scroll-Position simulieren
        grid.style.paddingTop = `${startIndex * itemHeight}px`;
        grid.style.paddingBottom = `${(items.length - endIndex) * itemHeight}px`;
        
        // Nur sichtbare Items rendern
        const html = visibleItems.map((item, idx) => {
            const originalIndex = startIndex + idx;
            const isVideo = item.mime_type?.startsWith('video/');
            const isAudio = item.mime_type?.startsWith('audio/');
            const isPdf = item.mime_type === 'application/pdf';
            // PDFs aus der Galerie-Bild-Ansicht ausschließen
            if (isPdf) return '';
            let mediaUrl;
            let thumbnailUrl;
            if (item.type === 'attachment') {
                mediaUrl = `/api/records/${item.record_id}/files/${encodeURIComponent(item.filename)}`;
                // Performance: Thumbnail für Gallery-Ansicht verwenden (direkt ID ohne Präfix)
                thumbnailUrl = `/api/gallery/thumbnail/${item.id}?size=200`;
            } else {
                mediaUrl = `/api/gallery/${encodeURIComponent(item.id)}`;
                thumbnailUrl = mediaUrl; // Für Galerie-Medien keine Thumbnails verfügbar
            }
            
            const borderClass = item.record_color ? item.record_color : '';
            const createdDate = this.formatDate(item.created_at);
            const filename = item.filename || item.original_filename || 'Unbenannt';
            
            return `
                <div class="record-card gallery-card ${borderClass}" data-record-id="${item.id}" onclick="App.openGalleryLightbox(${originalIndex})">
                    ${this.auswahlIstAktiv ? `
                        <div class="selection-circle ${this.auswahlIds.has(item.id) ? 'selected' : ''}" onclick="event.stopPropagation(); App.umschaltenAkteAuswahl('${item.id}')">
                            ${this.auswahlIds.has(item.id) ? '<i class="fas fa-check"></i>' : ''}
                        </div>
                    ` : ''}
                    <div class="record-title gallery-title">${this.escapeHtml(filename)}</div>
                    <div class="gallery-media">
                        ${isAudio
                            ? `<div class="gallery-audio-wrapper" data-audio-url="${mediaUrl}">
                                <div class="gallery-audio-viz-slot"></div>
                                <div class="gallery-audio-controls">
                                    <button class="gallery-audio-play-btn" onclick="event.stopPropagation(); App.toggleGalleryAudio(this)">
                                        <i class="fas fa-play"></i>
                                    </button>
                                    <div class="gallery-audio-progress">
                                        <div class="gallery-audio-progress-bar"></div>
                                    </div>
                                    <div class="gallery-audio-volume">
                                        <i class="fas fa-volume-up gallery-audio-volume-icon"></i>
                                        <input type="range" class="gallery-audio-volume-slider" min="0" max="1" step="0.1" value="1" onclick="event.stopPropagation()">
                                    </div>
                                </div>
                                <audio src="${mediaUrl}" class="gallery-audio-hidden" preload="none"></audio>
                               </div>`
                            : isVideo
                            ? `<video src="${mediaUrl}" class="gallery-media-element" muted playsinline disablePictureInPicture controlsList="nodownload nopictureinpicture noremoteplayback nofullscreen" preload="metadata" loading="lazy"></video>`
                            : `<img src="${mediaUrl}" class="gallery-media-element" alt="${this.escapeHtml(filename)}" loading="lazy" fetchpriority="low">`
                        }
                    </div>
                    <div class="record-meta">
                        <div class="meta-row">
                            ${item.type === 'gallery' 
                                ? `<span class="meta-author gallery-meta-item">
                                    <i class="fas fa-folder" style="margin-right:4px;opacity:0.6"></i>
                                    <span class="gallery-meta-value">Galerie</span>
                                </span>` 
                                : `<span class="meta-author gallery-meta-item">
                                    <i class="fas fa-folder" style="margin-right:4px;opacity:0.6"></i>
                                    <span class="gallery-meta-value">${this.escapeHtml(item.record_title || 'Akte ohne Namen')}</span>
                                </span>`
                            }
                            <span class="meta-author gallery-meta-item gallery-meta-date">
                                <span class="gallery-meta-value">${createdDate}</span>
                            </span>
                        </div>
                    </div>
                    ${item.type === 'gallery' 
                        ? `<button class="btn btn-sm btn-danger" style="position:absolute; top:12px; right:12px; z-index:10; width:32px; height:32px; padding:0; display:flex; align-items:center; justify-content:center;" onclick="event.stopPropagation(); App.deleteGalleryMedia(${item.id})"><i class="fas fa-trash"></i></button>` 
                        : ''
                    }
                </div>
            `;
        }).join('');
        
        grid.innerHTML = html;
        
        // Scroll-Event-Listener für Virtual Scrolling
        if (!this._virtualScrollListener) {
            this._virtualScrollListener = this.debounce(() => {
                if (this.galleryMedia.length > 100) {
                    this.renderVirtualGallery(this.galleryMedia);
                }
            }, 100);
            grid.addEventListener('scroll', this._virtualScrollListener, { passive: true });
        }
        
        this.initializeVisibleAudioVisualizers();
        setTimeout(() => grid.style.willChange = '', 1000);
    },
    
    debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func.apply(this, args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    },

    async deleteGalleryMedia(mediaId) {
        // Galerie-Medien sind Anhänge aus Akten - über die zugehörige Akte löschen
        const mediaItem = this.galleryMedia.find(m => m.id === mediaId);
        if (!mediaItem || !mediaItem.record_id) {
            this.toast('Medium nicht gefunden oder keine zugehörige Akte', 'error');
            return;
        }

        if (!await this.confirm('Bild löschen?', 'Das Bild wird aus der Akte und der Galerie entfernt.', 'Ja, löschen', 'btn-danger')) return;

        try {
            await this.apiDelete(`/records/${mediaItem.record_id}/files/${encodeURIComponent(mediaItem.filename)}`);
            this.toast('Bild gelöscht', 'success');
            // Aus der lokalen Liste entfernen
            this.galleryMedia = this.galleryMedia.filter(m => m.id !== mediaId);
            this.renderGallery();
        } catch (e) {
            this.toast('Fehler beim Löschen: ' + e.message, 'error');
        }
    },

    async deleteSelectedGalleryMedia() {
        if (this.auswahlIds.size === 0) {
            this.toast('Bitte wählen Sie zuerst Bilder aus', 'warning');
            return;
        }

        const selectedIds = Array.from(this.auswahlIds);
        const selectedItems = this.galleryMedia.filter(m => selectedIds.includes(m.id));

        if (selectedItems.length === 0) {
            this.toast('Keine gültigen Bilder ausgewählt', 'error');
            return;
        }

        if (!await this.confirm(`${selectedItems.length} Bild(er) löschen?`, 'Die Bilder werden aus den zugehörigen Akten und der Galerie entfernt.', 'Ja, löschen', 'btn-danger')) return;

        let deletedCount = 0;
        let errorCount = 0;

        for (const item of selectedItems) {
            if (!item.record_id) {
                errorCount++;
                continue;
            }

            try {
                await this.apiDelete(`/records/${item.record_id}/files/${encodeURIComponent(item.filename)}`);
                deletedCount++;
            } catch (e) {
                console.error('Fehler beim Löschen von Bild:', item.id, e);
                errorCount++;
            }
        }

        if (deletedCount > 0) {
            this.toast(`${deletedCount} Bild(er) gelöscht`, 'success');
            // Aus der lokalen Liste entfernen
            this.galleryMedia = this.galleryMedia.filter(m => !selectedIds.includes(m.id));
            this.deaktiviereAuswahlmodus(true);
            this.renderGallery();
        }

        if (errorCount > 0) {
            this.toast(`${errorCount} Bild(er) konnten nicht gelöscht werden`, 'error');
        }
    },

    ensureGalleryAudioVisualizer(wrapper, audio) {
        if (wrapper._audioViz) return wrapper._audioViz;
        const slot = wrapper.querySelector('.gallery-audio-viz-slot');
        if (!slot || !window.AudioVisualizer) return null;
        wrapper._audioViz = window.AudioVisualizer.attach(slot, audio, {
            barCount: 12,
            className: 'audio-viz'
        });
        return wrapper._audioViz;
    },

    stopGalleryAudioVisualizer(wrapper) {
        if (wrapper && wrapper._audioViz) wrapper._audioViz.stop();
    },

    toggleGalleryAudio(btn) {
        const wrapper = btn.closest('.gallery-audio-wrapper');
        const audio = wrapper.querySelector('.gallery-audio-hidden');
        const icon = btn.querySelector('i');
        const progressBar = wrapper.querySelector('.gallery-audio-progress-bar');
        const volumeSlider = wrapper.querySelector('.gallery-audio-volume-slider');
        const volumeIcon = wrapper.querySelector('.gallery-audio-volume-icon');
        const visualizer = this.ensureGalleryAudioVisualizer(wrapper, audio);

        if (audio.paused) {
            // Stoppe alle anderen Audio-Player
            document.querySelectorAll('.gallery-audio-hidden').forEach(a => {
                if (a !== audio && !a.paused) {
                    a.pause();
                    const otherWrapper = a.closest('.gallery-audio-wrapper');
                    const otherBtn = otherWrapper.querySelector('.gallery-audio-play-btn i');
                    otherBtn.className = 'fas fa-play';
                    this.stopGalleryAudioVisualizer(otherWrapper);
                }
            });

            audio.play().then(() => {
                if (visualizer) visualizer.start();
            }).catch(() => {});
            icon.className = 'fas fa-pause';
        } else {
            audio.pause();
            icon.className = 'fas fa-play';
            if (visualizer) visualizer.stop();
        }

        // Update progress
        audio.ontimeupdate = () => {
            const percent = (audio.currentTime / audio.duration) * 100;
            progressBar.style.width = percent + '%';
        };

        audio.onended = () => {
            icon.className = 'fas fa-play';
            progressBar.style.width = '0%';
            if (visualizer) visualizer.stop();
        };

        // Volume control
        volumeSlider.oninput = () => {
            audio.volume = volumeSlider.value;
            if (audio.volume === 0) {
                volumeIcon.className = 'fas fa-volume-mute gallery-audio-volume-icon';
            } else if (audio.volume < 0.5) {
                volumeIcon.className = 'fas fa-volume-down gallery-audio-volume-icon';
            } else {
                volumeIcon.className = 'fas fa-volume-up gallery-audio-volume-icon';
            }
        };

        volumeIcon.onclick = (e) => {
            e.stopPropagation();
            if (audio.volume > 0) {
                audio.dataset.prevVolume = audio.volume;
                audio.volume = 0;
                volumeSlider.value = '0';
                volumeIcon.className = 'fas fa-volume-mute gallery-audio-volume-icon';
            } else {
                audio.volume = audio.dataset.prevVolume || '1';
                volumeSlider.value = audio.volume;
                volumeIcon.className = 'fas fa-volume-up gallery-audio-volume-icon';
            }
        };
    },

    formatTime(seconds) {
        const mins = Math.floor(seconds / 60);
        const secs = Math.floor(seconds % 60);
        return `${mins}:${secs.toString().padStart(2, '0')}`;
    },

    openGalleryLightbox(index) {
        this.galleryCurrentIndex = index;
        const lightbox = document.getElementById('galleryLightboxOverlay');
        const content = document.getElementById('galleryLightboxContent');
        const info = document.getElementById('galleryLightboxInfo');
        if (!lightbox || !content || !info) return;

        this.renderGalleryLightboxItem();
        lightbox.classList.add('show');
        document.body.style.overflow = 'hidden';
    },

    renderGalleryLightboxItem() {
        const content = document.getElementById('galleryLightboxContent');
        const info = document.getElementById('galleryLightboxInfo');
        const goToRecordBtn = document.getElementById('galleryLightboxGoToRecord');
        if (!content || !info || !goToRecordBtn) return;

        if (typeof this._galleryLightboxVideoCleanup === 'function') {
            this._galleryLightboxVideoCleanup();
            this._galleryLightboxVideoCleanup = null;
        }

        const item = this.galleryMedia[this.galleryCurrentIndex];
        const isVideo = item.mime_type?.startsWith('video/');
        const isAudio = item.mime_type?.startsWith('audio/');
        let mediaUrl;
        if (item.type === 'attachment') {
            mediaUrl = `/api/records/${item.record_id}/files/${encodeURIComponent(item.filename)}`;
            goToRecordBtn.style.display = 'flex';
            goToRecordBtn.onclick = () => this.goToRecordFromGallery(item.record_id);
        } else {
            mediaUrl = `/api/gallery/${encodeURIComponent(item.id)}`;
            goToRecordBtn.style.display = 'none';
        }

        if (isAudio) {
            content.innerHTML = `
                <div class="ordama-audio-shell">
                    <div class="ordama-audio-viz-slot"></div>
                    <div class="ordama-audio-controls-stack">
                        <div class="ordama-audio-controls">
                            <button class="ordama-audio-play-btn">
                                <i class="fas fa-play"></i>
                            </button>
                            <div class="ordama-audio-progress">
                                <div class="ordama-audio-progress-bar"></div>
                            </div>
                            <div class="ordama-audio-volume">
                                <i class="fas fa-volume-up ordama-audio-volume-icon"></i>
                                <input type="range" class="ordama-audio-volume-slider" min="0" max="1" step="0.1" value="1">
                            </div>
                        </div>
                        <div class="ordama-audio-time-row">
                            <span class="ordama-audio-current-time">0:00</span>
                            <span class="ordama-audio-duration">0:00</span>
                        </div>
                    </div>
                    <audio src="${mediaUrl}" class="ordama-audio-hidden"></audio>
                </div>
            `;
            // Initialize audio player for lightbox
            this.initLightboxAudioPlayer();
        } else if (isVideo) {
            content.innerHTML = `
                <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;width:100%;height:100%;">
                    <div class="lightbox-video-container" style="position:relative;width:90vw;height:calc(85vh - 60px);border-radius:8px;overflow:hidden;background:#000;">
                        <video src="${mediaUrl}" style="width:100%;height:100%;object-fit:contain;cursor:pointer;"></video>
                        <div class="fullscreen-overlay" style="position:absolute;top:0;left:0;width:100%;height:100%;pointer-events:none;z-index:1000;display:none;"></div>
                    </div>
                    <div style="display:flex;align-items:center;gap:12px;width:90vw;padding:10px 20px;background:#2c3e50;border-radius:8px;margin-top:10px;">
                        <button class="lightbox-video-play-btn" style="background:#3b82f6;color:white;border:none;border-radius:50%;width:40px;height:40px;cursor:pointer;display:flex;align-items:center;justify-content:center;font-size:16px;flex-shrink:0;">
                            <i class="fas fa-pause"></i>
                        </button>
                        <div class="lightbox-video-progress" style="flex:1;height:8px;background:rgba(255,255,255,0.2);border-radius:4px;overflow:hidden;cursor:pointer;">
                            <div class="lightbox-video-progress-bar" style="height:100%;background:#3b82f6;width:0%;transition:width 0.1s;"></div>
                        </div>
                        <span class="lightbox-video-time" style="color:white;font-size:14px;font-weight:500;white-space:nowrap;min-width:80px;">0:00 / 0:00</span>
                        <div style="display:flex;align-items:center;gap:8px;">
                            <i class="fas fa-volume-up lightbox-video-volume-icon" style="color:white;font-size:18px;cursor:pointer;"></i>
                            <input type="range" class="lightbox-video-volume-slider" min="0" max="1" step="0.1" value="1" style="width:80px;cursor:pointer;accent-color:#3b82f6;">
                        </div>
                        <button class="lightbox-video-fullscreen-btn" style="background:#3b82f6;color:white;border:none;border-radius:50%;width:40px;height:40px;cursor:pointer;display:flex;align-items:center;justify-content:center;font-size:16px;flex-shrink:0;">
                            <i class="fas fa-expand"></i>
                        </button>
                    </div>
                </div>
            `;
            this.initLightboxVideoPlayer();
        } else {
            content.innerHTML = `<img src="${mediaUrl}" alt="${this.escapeHtml(item.original_filename)}" style="max-width:90vw; max-height:85vh; border-radius:8px;">`;
        }

        info.innerHTML = '';
    },

    initLightboxAudioPlayer() {
        const content = document.getElementById('galleryLightboxContent');
        if (!content) return;

        const audio = content.querySelector('.ordama-audio-hidden');
        const playBtn = content.querySelector('.ordama-audio-play-btn');
        const progressBar = content.querySelector('.ordama-audio-progress-bar');
        const progressContainer = content.querySelector('.ordama-audio-progress');
        const volumeSlider = content.querySelector('.ordama-audio-volume-slider');
        const volumeIcon = content.querySelector('.ordama-audio-volume-icon');
        const currentTimeEl = content.querySelector('.ordama-audio-current-time');
        const durationEl = content.querySelector('.ordama-audio-duration');
        const vizSlot = content.querySelector('.ordama-audio-viz-slot');

        if (!audio || !playBtn) return;

        // Initialize visualizer
        const visualizer = window.AudioVisualizer && vizSlot
            ? window.AudioVisualizer.attach(vizSlot, audio, { barCount: 16, className: 'audio-viz' })
            : null;

        let isPlaying = false;

        const formatTime = (seconds) => {
            if (isNaN(seconds)) return '0:00';
            const mins = Math.floor(seconds / 60);
            const secs = Math.floor(seconds % 60);
            return `${mins}:${secs.toString().padStart(2, '0')}`;
        };

        playBtn.onclick = () => {
            if (isPlaying) {
                audio.pause();
                playBtn.innerHTML = '<i class="fas fa-play"></i>';
                isPlaying = false;
                if (visualizer) visualizer.stop();
            } else {
                audio.play().then(() => {
                    if (visualizer) visualizer.start();
                }).catch(() => {});
                playBtn.innerHTML = '<i class="fas fa-pause"></i>';
                isPlaying = true;
            }
        };

        audio.ontimeupdate = () => {
            const percent = (audio.currentTime / audio.duration) * 100;
            progressBar.style.width = percent + '%';
            currentTimeEl.textContent = formatTime(audio.currentTime);
            durationEl.textContent = formatTime(audio.duration);
        };

        audio.onloadedmetadata = () => {
            durationEl.textContent = formatTime(audio.duration);
        };

        audio.onended = () => {
            playBtn.innerHTML = '<i class="fas fa-play"></i>';
            isPlaying = false;
            progressBar.style.width = '0%';
            currentTimeEl.textContent = '0:00';
            if (visualizer) visualizer.stop();
        };

        progressContainer.onclick = (e) => {
            const rect = progressContainer.getBoundingClientRect();
            const percent = (e.clientX - rect.left) / rect.width;
            audio.currentTime = percent * audio.duration;
        };

        volumeSlider.oninput = () => {
            audio.volume = volumeSlider.value;
            if (audio.volume === 0) {
                volumeIcon.className = 'fas fa-volume-mute ordama-audio-volume-icon';
            } else if (audio.volume < 0.5) {
                volumeIcon.className = 'fas fa-volume-down ordama-audio-volume-icon';
            } else {
                volumeIcon.className = 'fas fa-volume-up ordama-audio-volume-icon';
            }
        };

        volumeIcon.onclick = () => {
            if (audio.volume > 0) {
                audio.dataset.prevVolume = audio.volume;
                audio.volume = 0;
                volumeSlider.value = '0';
                volumeIcon.className = 'fas fa-volume-mute ordama-audio-volume-icon';
            } else {
                audio.volume = audio.dataset.prevVolume || '1';
                volumeSlider.value = audio.volume;
                volumeIcon.className = 'fas fa-volume-up ordama-audio-volume-icon';
            }
        };

        // Autoplay
        audio.play().then(() => {
            playBtn.innerHTML = '<i class="fas fa-pause"></i>';
            isPlaying = true;
            if (visualizer) visualizer.start();
        }).catch(() => {
            // Autoplay might be blocked
        });
    },

    initLightboxVideoPlayer() {
        const content = document.getElementById('galleryLightboxContent');
        if (!content) return;

        const videoContainer = content.querySelector('.lightbox-video-container');
        const video = content.querySelector('video');
        const playBtn = content.querySelector('.lightbox-video-play-btn');
        const progressBar = content.querySelector('.lightbox-video-progress-bar');
        const progressContainer = content.querySelector('.lightbox-video-progress');
        const volumeSlider = content.querySelector('.lightbox-video-volume-slider');
        const volumeIcon = content.querySelector('.lightbox-video-volume-icon');
        const timeEl = content.querySelector('.lightbox-video-time');
        const fullscreenBtn = content.querySelector('.lightbox-video-fullscreen-btn');

        if (!video || !playBtn || !videoContainer) return;

        let isPlaying = false;
        const isNativeFullscreenActive = () =>
            document.fullscreenElement === videoContainer ||
            document.webkitFullscreenElement === videoContainer ||
            document.msFullscreenElement === videoContainer;

        const isFullscreenActive = () =>
            videoContainer.classList.contains('custom-fullscreen') || isNativeFullscreenActive();

        const syncFullscreenButton = () => {
            if (!fullscreenBtn) return;
            const fullscreenActive = isFullscreenActive();
            fullscreenBtn.innerHTML = fullscreenActive
                ? '<i class="fas fa-compress"></i>'
                : '<i class="fas fa-expand"></i>';
            fullscreenBtn.title = fullscreenActive ? 'Vollbild beenden' : 'Vollbild';
        };

        const requestNativeFullscreen = async () => {
            try {
                if (videoContainer.requestFullscreen) {
                    await videoContainer.requestFullscreen();
                    return true;
                }
                if (videoContainer.webkitRequestFullscreen) {
                    videoContainer.webkitRequestFullscreen();
                    return true;
                }
                if (videoContainer.msRequestFullscreen) {
                    videoContainer.msRequestFullscreen();
                    return true;
                }
            } catch (_) {}
            return false;
        };

        const exitNativeFullscreen = async () => {
            try {
                if (document.fullscreenElement === videoContainer && document.exitFullscreen) {
                    await document.exitFullscreen();
                    return true;
                }
                if (document.webkitFullscreenElement === videoContainer && document.webkitExitFullscreen) {
                    document.webkitExitFullscreen();
                    return true;
                }
                if (document.msFullscreenElement === videoContainer && document.msExitFullscreen) {
                    document.msExitFullscreen();
                    return true;
                }
            } catch (_) {}
            return false;
        };

        const setFullscreen = async (shouldEnable) => {
            if (shouldEnable) {
                const enteredNative = await requestNativeFullscreen();
                if (!enteredNative) {
                    videoContainer.classList.add('custom-fullscreen');
                }
            } else {
                if (isNativeFullscreenActive()) {
                    await exitNativeFullscreen();
                }
                videoContainer.classList.remove('custom-fullscreen');
            }
            syncFullscreenButton();
        };

        const handleFullscreenChange = () => {
            if (!isNativeFullscreenActive()) {
                videoContainer.classList.remove('custom-fullscreen');
            }
            syncFullscreenButton();
        };

        const formatTime = (seconds) => {
            if (isNaN(seconds)) return '0:00';
            const mins = Math.floor(seconds / 60);
            const secs = Math.floor(seconds % 60);
            return `${mins}:${secs.toString().padStart(2, '0')}`;
        };

        playBtn.onclick = () => {
            if (isPlaying) {
                video.pause();
                playBtn.innerHTML = '<i class="fas fa-play"></i>';
                isPlaying = false;
            } else {
                video.play().then(() => {}).catch(() => {});
                playBtn.innerHTML = '<i class="fas fa-pause"></i>';
                isPlaying = true;
            }
        };

        video.ontimeupdate = () => {
            const percent = (video.currentTime / video.duration) * 100;
            progressBar.style.width = percent + '%';
            timeEl.textContent = `${formatTime(video.currentTime)} / ${formatTime(video.duration)}`;
        };

        video.onloadedmetadata = () => {
            timeEl.textContent = `0:00 / ${formatTime(video.duration)}`;
        };

        video.onended = () => {
            playBtn.innerHTML = '<i class="fas fa-play"></i>';
            isPlaying = false;
            progressBar.style.width = '0%';
        };

        progressContainer.onclick = (e) => {
            const rect = progressContainer.getBoundingClientRect();
            const percent = (e.clientX - rect.left) / rect.width;
            video.currentTime = percent * video.duration;
        };

        volumeSlider.oninput = () => {
            video.volume = volumeSlider.value;
            if (video.volume === 0) {
                volumeIcon.className = 'fas fa-volume-mute lightbox-video-volume-icon';
            } else if (video.volume < 0.5) {
                volumeIcon.className = 'fas fa-volume-down lightbox-video-volume-icon';
            } else {
                volumeIcon.className = 'fas fa-volume-up lightbox-video-volume-icon';
            }
        };

        volumeIcon.onclick = () => {
            if (video.volume > 0) {
                video.dataset.prevVolume = video.volume;
                video.volume = 0;
                volumeSlider.value = '0';
                volumeIcon.className = 'fas fa-volume-mute lightbox-video-volume-icon';
            } else {
                video.volume = video.dataset.prevVolume || '1';
                volumeSlider.value = video.volume;
                volumeIcon.className = 'fas fa-volume-up lightbox-video-volume-icon';
            }
        };

        if (fullscreenBtn) {
            fullscreenBtn.onclick = async () => {
                await setFullscreen(!isFullscreenActive());
            };

            syncFullscreenButton();
        }

        // Klick auf Video beendet den Vollbildmodus
        video.addEventListener('click', async (e) => {
            if (isFullscreenActive()) {
                e.preventDefault();
                await setFullscreen(false);
            }
        });

        document.addEventListener('fullscreenchange', handleFullscreenChange);
        document.addEventListener('webkitfullscreenchange', handleFullscreenChange);
        document.addEventListener('msfullscreenchange', handleFullscreenChange);

        this._galleryLightboxVideoCleanup = () => {
            document.removeEventListener('fullscreenchange', handleFullscreenChange);
            document.removeEventListener('webkitfullscreenchange', handleFullscreenChange);
            document.removeEventListener('msfullscreenchange', handleFullscreenChange);
            if (videoContainer.classList.contains('custom-fullscreen')) {
                videoContainer.classList.remove('custom-fullscreen');
            }
            if (isNativeFullscreenActive()) {
                exitNativeFullscreen();
            }
        };

        video.play().then(() => {
            playBtn.innerHTML = '<i class="fas fa-pause"></i>';
            isPlaying = true;
        }).catch(() => {});
    },

    goToRecordFromGallery(recordId) {
        this.closeGalleryLightbox();
        this.showSection('records');
        // After a short delay, open the record
        setTimeout(() => {
            this.openRecord(recordId);
        }, 200);
    },

    closeGalleryLightbox() {
        const lightbox = document.getElementById('galleryLightboxOverlay');
        if (!lightbox) return;
        if (typeof this._galleryLightboxVideoCleanup === 'function') {
            this._galleryLightboxVideoCleanup();
            this._galleryLightboxVideoCleanup = null;
        }
        lightbox.classList.remove('show');
        document.body.style.overflow = '';
        const content = document.getElementById('galleryLightboxContent');
        if (content) content.innerHTML = '';
    },

    navigateGalleryLightbox(direction) {
        let newIndex = this.galleryCurrentIndex + direction;
        if (newIndex < 0) newIndex = this.galleryMedia.length - 1;
        if (newIndex >= this.galleryMedia.length) newIndex = 0;
        this.galleryCurrentIndex = newIndex;
        this.renderGalleryLightboxItem();
    },

    async installUpdate() {
        if (!await this.confirm('Update installieren?', 'Das Programm wird aktualisiert. Währenddessen ist kein Zugriff möglich. Danach ist ein manueller Neustart erforderlich.')) return;
        
        try {
            this.toast('Update wird installieren...', 'info');
            const result = await this.apiPost('/admin/update/install');
            if (result.success) {
                const text = document.getElementById('updateStatusText');
                const btn = document.getElementById('installUpdateBtn');
                if (text) text.innerHTML = `<i class="fas fa-check-circle text-success"></i> <strong>Update erfolgreich!</strong><br>Bitte schließen Sie das Programm und starten Sie es neu.`;
                if (btn) btn.classList.add('hidden');
                this.toast('Update abgeschlossen. Bitte Neustart.', 'success');
            }
        } catch (e) {
            this.toast(e.message, 'error');
        }
    },

    // ── Assistant Functions ───────────────────────────
    async assistantSendCommand() {
        const input = document.getElementById('assistantInput');
        const command = input.value.trim();
        
        if (!command) return;
        
        // Store last command for feedback
        this.lastAssistantCommand = command;
        
        // Add user message to chat
        this.assistantAddMessage(command, 'user');
        input.value = '';
        
        try {
            const data = await this.apiPost('/assistant/execute', { command });
            
            if (data.success) {
                this.assistantAddMessage(data, 'system');
            } else {
                this.assistantAddMessage({ message: data.message || 'Fehler beim Ausführen des Befehls' }, 'error');
            }
        } catch (e) {
            this.assistantAddMessage({ message: `Fehler: ${e.message}` }, 'error');
        }
    },

    assistantEscapeHtml(text) {
        return String(text ?? '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    },

    assistantFormatText(text) {
        return this.assistantEscapeHtml(text)
            .replace(/\n/g, '<br>')
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.*?)\*/g, '<em>$1</em>');
    },

    assistantOpenRecord(recordId) {
        this.showSection('records');
        setTimeout(() => {
            this.openRecord(recordId);
        }, 200);
    },

    assistantBuildResultMeta(result) {
        const parts = [];
        if (result.number) parts.push(`Akte #${this.assistantEscapeHtml(result.number)}`);
        if (result.status) parts.push(`Status: ${this.assistantEscapeHtml(result.status)}`);
        if (result.category) parts.push(`Kategorie: ${this.assistantEscapeHtml(result.category)}`);
        if (result.reminder_date_label) parts.push(`Termin: ${this.assistantEscapeHtml(result.reminder_date_label)}`);
        return parts.join(' • ');
    },

    assistantNormalizeResults(data) {
        if (Array.isArray(data?.records) && data.records.length) {
            return data.records;
        }
        if (Array.isArray(data?.results) && data.results.length) {
            return data.results;
        }
        return [];
    },

    assistantBuildResultsHtml(data) {
        const results = this.assistantNormalizeResults(data);
        if (!Array.isArray(results) || results.length === 0) return '';

        const items = results.map(result => {
            const badge = result.action_badge
                ? `<span class="assistant-result-badge">${this.assistantEscapeHtml(result.action_badge)}</span>`
                : '';
            const meta = this.assistantBuildResultMeta(result);
            const metaHtml = meta ? `<div class="assistant-result-meta">${meta}</div>` : '';
            const snippet = result.snippet
                ? `<div class="assistant-result-snippet">${this.assistantFormatText(result.snippet)}</div>`
                : '';
            const openButton = result.id
                ? `
                    <div class="assistant-result-footer">
                        <button
                            type="button"
                            class="btn btn-sm btn-primary assistant-action-btn"
                            onclick="event.stopPropagation(); App.assistantOpenRecord(${result.id})">
                            <i class="fas fa-folder-open"></i> Akte öffnen
                        </button>
                    </div>
                `
                : '';

            return `
                <div
                    class="assistant-result-card${result.id ? ' assistant-result-card-clickable' : ''}"
                    ${result.id ? `role="button" tabindex="0" onclick="App.assistantOpenRecord(${result.id})" onkeydown="if(event.key==='Enter'||event.key===' '){event.preventDefault();App.assistantOpenRecord(${result.id});}"` : ''}>
                    <div class="assistant-result-header">
                        <div class="assistant-result-title">${this.assistantEscapeHtml(result.title || 'Ohne Titel')}</div>
                        ${badge}
                    </div>
                    ${metaHtml}
                    ${snippet}
                    ${openButton}
                </div>
            `;
        }).join('');

        return `<div class="assistant-results">${items}</div>`;
    },

    assistantAddMessage(payload, type) {
        const data = typeof payload === 'string' ? { message: payload } : (payload || {});
        const chat = document.getElementById('assistantChat');
        const messageDiv = document.createElement('div');
        messageDiv.className = `assistant-message assistant-message-${type}`;
        
        const contentDiv = document.createElement('div');
        contentDiv.className = 'message-content';
        
        const messageHtml = data.message ? `<p>${this.assistantFormatText(data.message)}</p>` : '';
        const resultsHtml = this.assistantBuildResultsHtml(data);

        contentDiv.innerHTML = `${messageHtml}${resultsHtml}`;
        messageDiv.appendChild(contentDiv);
        
        // Add feedback button for system messages
        if (type === 'system' && data.action && data.action !== 'help') {
            const feedbackDiv = document.createElement('div');
            feedbackDiv.className = 'assistant-feedback';
            feedbackDiv.innerHTML = `
                <button type="button" class="btn btn-sm btn-secondary feedback-btn" onclick="App.assistantSendFeedback(this, true)">
                    <i class="fas fa-thumbs-up"></i> Das war richtig
                </button>
                <button type="button" class="btn btn-sm btn-secondary feedback-btn" onclick="App.assistantSendFeedback(this, false)">
                    <i class="fas fa-thumbs-down"></i> Das war nicht richtig
                </button>
            `;
            messageDiv.appendChild(feedbackDiv);
        }
        
        chat.appendChild(messageDiv);
        
        // Scroll to bottom
        chat.scrollTop = chat.scrollHeight;
    },

    assistantClearChat() {
        const chat = document.getElementById('assistantChat');
        chat.innerHTML = '';
    },

    async assistantShowHelp() {
        const chat = document.getElementById('assistantChat');
        
        // Check if help already exists in chat
        const existingHelp = Array.from(chat.querySelectorAll('.assistant-message-system')).find(msg => 
            msg.textContent.includes('Verfügbare Befehle') || msg.textContent.includes('Verfügbare Befehle für den Assistenten')
        );
        
        if (existingHelp) {
            // Scroll to existing help
            existingHelp.scrollIntoView({ behavior: 'smooth', block: 'center' });
            return;
        }
        
        try {
            const data = await this.apiPost('/assistant/execute', { command: 'hilfe' });
            if (data.success) {
                this.assistantAddMessage(data, 'system');
            } else {
                this.assistantAddMessage({ message: data.message || 'Fehler beim Abrufen der Hilfe' }, 'error');
            }
        } catch (e) {
            this.assistantAddMessage({ message: `Fehler: ${e.message}` }, 'error');
        }
    },

    async assistantSendFeedback(button, isCorrect) {
        const lastCommand = this.lastAssistantCommand;
        if (!lastCommand) {
            this.assistantAddMessage({ message: 'Kein Befehl zum Feedback vorhanden.' }, 'error');
            return;
        }

        try {
            const data = await this.apiPost('/assistant/feedback', {
                command: lastCommand,
                is_correct: isCorrect
            });
            
            if (data.success) {
                // Disable both feedback buttons
                const feedbackDiv = button.parentElement;
                const allButtons = feedbackDiv.querySelectorAll('.feedback-btn');
                allButtons.forEach(btn => btn.disabled = true);
                
                button.innerHTML = isCorrect 
                    ? '<i class="fas fa-check"></i> Danke!'
                    : '<i class="fas fa-check"></i> Feedback gesendet';
                
                if (isCorrect) {
                    this.assistantAddMessage({ message: 'Danke für das positive Feedback! Der Assistent wird diese Formulierung künftig bevorzugen.' }, 'system');
                } else {
                    this.assistantAddMessage({ message: 'Danke für das Feedback! Der Assistent wird diese Formulierung künftig besser verstehen.' }, 'system');
                }
            }
        } catch (e) {
            this.assistantAddMessage({ message: `Fehler: ${e.message}` }, 'error');
        }
    },

    async loadAssistantLearningData() {
        const container = document.getElementById('assistantLearningData');
        
        // Toggle: Wenn bereits sichtbar, schließen
        if (!container.classList.contains('hidden')) {
            container.classList.add('hidden');
            return;
        }
        
        try {
            const data = await this.apiGet('/assistant/learning-data');
            if (data.success) {
                this.renderAssistantLearningData(data.data);
            } else {
                alert('Fehler beim Laden der Lern-Daten: ' + (data.message || 'Unbekannter Fehler'));
            }
        } catch (e) {
            alert('Fehler beim Laden der Lern-Daten: ' + e.message);
        }
    },

    renderAssistantLearningData(data) {
        const container = document.getElementById('assistantLearningData');
        container.classList.remove('hidden');

        // Blacklist
        const blacklistList = document.getElementById('blacklistList');
        blacklistList.innerHTML = '';
        if (data.blacklist && data.blacklist.length > 0) {
            data.blacklist.forEach((item, index) => {
                const div = document.createElement('div');
                div.className = 'learning-data-item';
                div.innerHTML = `
                    <div class="learning-data-content">
                        <div class="mb-2"><i class="fas fa-ban text-danger"></i> <strong>Befehl:</strong> "${item}"</div>
                        <div class="text-muted small">
                            <em>Dieser Befehl wurde als falsch markiert und wird übersprungen.</em>
                        </div>
                    </div>
                    <button class="btn btn-sm btn-success" onclick="App.deleteLearningData('blacklist', ${index})">
                        <i class="fas fa-check"></i> Entfernen
                    </button>
                `;
                blacklistList.appendChild(div);
            });
        } else {
            blacklistList.innerHTML = '<p class="text-muted">Keine Befehle auf der Blacklist. Befehle werden auf die Blacklist gesetzt wenn du sie mit "Das war nicht richtig" markierst.</p>';
        }

        // Field Synonyms
        const fieldSynonymsList = document.getElementById('fieldSynonymsList');
        fieldSynonymsList.innerHTML = '';
        if (data.field_synonyms && Object.keys(data.field_synonyms).length > 0) {
            for (const [field, synonyms] of Object.entries(data.field_synonyms)) {
                if (synonyms && synonyms.length > 0) {
                    const fieldDiv = document.createElement('div');
                    fieldDiv.className = 'learning-data-item';
                    fieldDiv.innerHTML = `
                        <div class="learning-data-content">
                            <div class="mb-2"><i class="fas fa-tag text-primary"></i> <strong>Feld:</strong> ${this.translateFieldName(field)}</div>
                            <div class="text-muted small">
                                <strong>Synonyme:</strong> ${synonyms.join(', ')}
                            </div>
                        </div>
                        <button class="btn btn-sm btn-danger" onclick="App.deleteLearningData('field_synonyms', null, '${field}')">
                            <i class="fas fa-trash"></i> Zurücksetzen
                        </button>
                    `;
                    fieldSynonymsList.appendChild(fieldDiv);
                }
            }
        } else {
            fieldSynonymsList.innerHTML = '<p class="text-muted">Keine Feld-Synonyme vorhanden. Füge neue Synonyme hinzu, um die Erkennung zu verbessern.</p>';
        }

        // Initialize field dropdown
        this.initFieldDropdown();


        // Feedback-Beispiele
        const feedbackList = document.getElementById('feedbackExamplesList');
        feedbackList.innerHTML = '';
        if (data.feedback_examples && data.feedback_examples.length > 0) {
            data.feedback_examples.forEach((item, index) => {
                const div = document.createElement('div');
                div.className = 'learning-data-item';
                const icon = item.is_correct ? '<i class="fas fa-thumbs-up text-success"></i>' : '<i class="fas fa-thumbs-down text-danger"></i>';
                div.innerHTML = `
                    <div class="learning-data-content">
                        <div class="mb-2">${icon} <strong>Befehl:</strong> "${item.normalized_command || 'N/A'}"</div>
                        <div class="text-muted small">
                            <strong>Feedback-Typ:</strong> ${item.is_correct ? 'Positiv (wurde verstärkt)' : 'Negativ (wurde analysiert)'}<br>
                            <strong>Zeitstempel:</strong> ${item.timestamp || 'N/A'}
                        </div>
                    </div>
                    <button class="btn btn-sm btn-danger" onclick="App.deleteLearningData('feedback_examples', ${index})">
                        <i class="fas fa-trash"></i> Löschen
                    </button>
                `;
                feedbackList.appendChild(div);
            });
        } else {
            feedbackList.innerHTML = '<p class="text-muted">Keine Feedback-Beispiele vorhanden. Das System lernt aus deinem Feedback über die Daumen-Buttons im Assistenten.</p>';
        }

        // Positive Beispiele
        const positiveList = document.getElementById('positiveExamplesList');
        positiveList.innerHTML = '';
        if (data.positive_examples && data.positive_examples.length > 0) {
            data.positive_examples.forEach((item, index) => {
                const div = document.createElement('div');
                div.className = 'learning-data-item';
                const commandTypeLabel = this._translateCommandType(item.command_type);
                div.innerHTML = `
                    <div class="learning-data-content">
                        <div class="mb-2"><i class="fas fa-check-circle text-success"></i> <strong>Befehl:</strong> "${item.normalized_command || 'N/A'}"</div>
                        <div class="text-muted small">
                            <strong>Erkannt als:</strong> ${commandTypeLabel}<br>
                            <strong>Zeitstempel:</strong> ${item.timestamp || 'N/A'}<br>
                            <em>Dieser Befehl wurde erfolgreich ausgeführt und daraus wurden Synonyme gelernt.</em>
                        </div>
                    </div>
                    <button class="btn btn-sm btn-danger" onclick="App.deleteLearningData('positive_examples', ${index})">
                        <i class="fas fa-trash"></i> Löschen
                    </button>
                `;
                positiveList.appendChild(div);
            });
        } else {
            positiveList.innerHTML = '<p class="text-muted">Keine positiven Beispiele vorhanden. Das System lernt automatisch von erfolgreich ausgeführten Befehlen.</p>';
        }

        // Action-Aliase
        const actionAliasesList = document.getElementById('actionAliasesList');
        actionAliasesList.innerHTML = '';
        if (data.action_aliases && Object.keys(data.action_aliases).length > 0) {
            Object.entries(data.action_aliases).forEach(([commandType, aliases]) => {
                const div = document.createElement('div');
                div.className = 'learning-data-item';
                const commandTypeLabel = this._translateCommandType(commandType);
                div.innerHTML = `
                    <div class="learning-data-content">
                        <div class="mb-2"><strong>Für Befehl:</strong> ${commandTypeLabel}</div>
                        <div class="text-muted small">
                            <strong>Gelernte Synonyme:</strong> ${aliases.length > 0 ? aliases.join(', ') : 'Keine'}<br>
                            <em>Diese Wörter werden nun als Alternative für diesen Befehl erkannt.</em>
                        </div>
                    </div>
                    <button class="btn btn-sm btn-danger" onclick="App.deleteLearningData('action_aliases', null, '${commandType}')">
                        <i class="fas fa-trash"></i> Löschen
                    </button>
                `;
                actionAliasesList.appendChild(div);
            });
        } else {
            actionAliasesList.innerHTML = '<p class="text-muted">Keine Action-Aliase vorhanden. Das System lernt Synonyme für Befehle aus Feedback und erfolgreichen Ausführungen.</p>';
        }

        // Field-Aliase
        const fieldAliasesList = document.getElementById('fieldAliasesList');
        fieldAliasesList.innerHTML = '';
        if (data.field_aliases && Object.keys(data.field_aliases).length > 0) {
            Object.entries(data.field_aliases).forEach(([fieldType, aliases]) => {
                const div = document.createElement('div');
                div.className = 'learning-data-item';
                div.innerHTML = `
                    <div class="learning-data-content">
                        <div class="mb-2"><strong>Für Feld:</strong> ${fieldType}</div>
                        <div class="text-muted small">
                            <strong>Gelernte Synonyme:</strong> ${aliases.length > 0 ? aliases.join(', ') : 'Keine'}<br>
                            <em>Diese Wörter werden nun als Alternative für dieses Feld erkannt.</em>
                        </div>
                    </div>
                    <button class="btn btn-sm btn-danger" onclick="App.deleteLearningData('field_aliases', null, '${fieldType}')">
                        <i class="fas fa-trash"></i> Löschen
                    </button>
                `;
                fieldAliasesList.appendChild(div);
            });
        } else {
            fieldAliasesList.innerHTML = '<p class="text-muted">Keine Field-Aliase vorhanden. Das System lernt Synonyme für Felder aus Feedback und erfolgreichen Ausführungen.</p>';
        }
    },

    _translateCommandType(commandType) {
        const translations = {
            'create_record': 'Akte erstellen',
            'update_record': 'Akte bearbeiten',
            'search': 'Suche',
            'delete_record': 'Akte löschen',
            'archive_record': 'Akte archivieren',
            'set_status': 'Status setzen',
            'set_color': 'Farbe setzen',
            'set_reminder': 'Termin setzen',
            'add_note': 'Notiz hinzufügen',
            'set_category': 'Kategorie setzen',
            'summarize_record': 'Akte zusammenfassen'
        };
        return translations[commandType] || commandType;
    },

    translateFieldName(fieldName) {
        const translations = {
            'title': 'Titel',
            'address': 'Adresse',
            'content': 'Inhalt',
            'reminder_date': 'Termin (Start)',
            'reminder_end_date': 'Termin (Ende)',
            'reminder_repeat': 'Wiederholung',
            'reminder_assigned_to': 'Sichtbarkeit',
            'status': 'Status',
            'category': 'Kategorie',
            'note': 'Vermerk',
            'border_color': 'Rahmenfarbe',
            'add_reminder': 'Erinnerung hinzufügen'
        };
        return translations[fieldName] || fieldName;
    },

    async deleteLearningData(type, index = null, commandType = null, field_name = null, synonym = null, date_format = null) {
        const isBlacklist = type === 'blacklist';
        const isFieldSynonyms = type === 'field_synonyms';
        const isDateFormats = type === 'date_formats';
        
        let confirmMessage = 'Möchten Sie diesen Eintrag wirklich löschen?';
        if (isBlacklist) {
            confirmMessage = 'Möchten Sie diesen Befehl von der Blacklist entfernen? Er wird dann wieder ausgeführt.';
        } else if (isFieldSynonyms) {
            confirmMessage = 'Möchten Sie die Synonyme für dieses Feld zurücksetzen?';
        } else if (isDateFormats) {
            confirmMessage = 'Möchten Sie dieses Datumsformat löschen?';
        }
        
        if (!confirm(confirmMessage)) {
            return;
        }

        try {
            const payload = { type };
            if (index !== null) {
                payload.index = index;
            }
            if (commandType) {
                payload.command_type = commandType;
            }
            if (field_name) {
                payload.field_name = field_name;
            }
            if (synonym) {
                payload.synonym = synonym;
            }
            if (date_format) {
                payload.date_format = date_format;
            }

            const data = await this.apiDelete('/assistant/learning-data', payload);
            if (data.success) {
                alert(isBlacklist ? 'Befehl wurde von der Blacklist entfernt.' : 'Eintrag wurde gelöscht.');
                this.loadAssistantLearningData(); // Neu laden
            } else {
                alert('Fehler beim Löschen: ' + (data.message || 'Unbekannter Fehler'));
            }
        } catch (e) {
            alert('Fehler beim Löschen: ' + e.message);
        }
    },

    async addFieldSynonym() {
        const fieldSelect = document.getElementById('fieldSelect');
        const newSynonymInput = document.getElementById('newSynonym');
        
        const field_name = fieldSelect.value;
        const synonym = newSynonymInput.value.trim();
        
        if (!synonym) {
            alert('Bitte gib ein Synonym ein.');
            return;
        }
        
        try {
            const data = await this.apiPost('/assistant/learning-data', {
                type: 'field_synonyms',
                field_name: field_name,
                synonym: synonym
            });
            
            if (data.success) {
                alert('Synonym wurde hinzugefügt.');
                newSynonymInput.value = '';
                this.loadAssistantLearningData();
            } else {
                alert('Fehler beim Hinzufügen: ' + (data.message || 'Unbekannter Fehler'));
            }
        } catch (e) {
            alert('Fehler beim Hinzufügen: ' + e.message);
        }
    },

    initFieldDropdown() {
        const dropdown = document.getElementById('modalFieldDropdown');
        if (!dropdown) return;

        const toggle = dropdown.querySelector('.dropdown-toggle');
        const menu = dropdown.querySelector('.dropdown-menu');
        const hiddenInput = dropdown.querySelector('input[type="hidden"]');
        const buttons = menu.querySelectorAll('button');

        // Toggle dropdown
        toggle.addEventListener('click', (e) => {
            e.stopPropagation();
            dropdown.classList.toggle('show');
        });

        // Handle button clicks
        buttons.forEach(button => {
            button.addEventListener('click', (e) => {
                e.stopPropagation();
                const value = button.getAttribute('data-value');
                const text = button.querySelector('span').textContent;
                
                hiddenInput.value = value;
                toggle.querySelector('span').textContent = text;
                dropdown.classList.remove('show');
            });
        });

        // Close dropdown when clicking outside
        document.addEventListener('click', (e) => {
            if (!dropdown.contains(e.target)) {
                dropdown.classList.remove('show');
            }
        });
    },

    async clearAllAssistantLearningData() {
        if (!confirm('Möchten Sie wirklich alle Lern-Daten des Assistenten löschen? Dies kann nicht rückgängig gemacht werden.')) {
            return;
        }

        try {
            const data = await this.apiDelete('/assistant/learning-data', { type: 'all' });
            if (data.success) {
                alert('Alle Lern-Daten wurden gelöscht.');
                document.getElementById('assistantLearningData').classList.add('hidden');
            } else {
                alert('Fehler beim Löschen: ' + (data.message || 'Unbekannter Fehler'));
            }
        } catch (e) {
            alert('Fehler beim Löschen: ' + e.message);
        }
    },

    async apiDelete(url, data = {}) {
        try {
            // Add /api prefix like the other api methods
            const apiUrl = `/api${url}`;
            
            const options = {
                method: 'DELETE',
                credentials: 'same-origin',
                headers: {}
            };
            
            // Only add body and Content-Type header if data is provided
            if (Object.keys(data).length > 0) {
                options.headers['Content-Type'] = 'application/json';
                options.body = JSON.stringify(data);
            }
            
            const response = await fetch(apiUrl, options);
            
            // Check if response is JSON
            const contentType = response.headers.get('content-type');
            if (!contentType || !contentType.includes('application/json')) {
                const text = await response.text();
                console.error('Keine JSON-Antwort:', text);
                throw new Error('Server hat keine JSON-Antwort zurückgegeben. Möglicherweise ist der Server nicht erreichbar oder es gibt einen Fehler.');
            }
            
            return await response.json();
        } catch (e) {
            throw new Error(e.message);
        }
    },

    updateThresholdValue(value) {
        const thresholdValue = document.getElementById('thresholdValue');
        if (thresholdValue) {
            thresholdValue.textContent = value;
        }
    },

    updateTextWeightValue(value) {
        const textWeightValue = document.getElementById('textWeightValue');
        if (textWeightValue) {
            textWeightValue.textContent = value;
        }
    },

    // ── Offline Synchronisation ────────────────────────────────
    
    updateRecordBellIcon(recordId) {
        // Aktualisiert nur das Glocken-Symbol für eine bestimmte Akte
        const recordCard = document.querySelector(`.record-card[data-id="${recordId}"]`);
        if (!recordCard) return;
        
        const bellIcon = recordCard.querySelector('.record-bell');
        if (!bellIcon) return;
        
        // Prüfen ob die Akte Erinnerungen hat
        const record = this.records.find(r => r.id === recordId);
        if (!record) return;
        
        const hasReminders = record.erinnerungen && record.erinnerungen.length > 0;
        
        if (hasReminders) {
            bellIcon.classList.remove('hidden');
            bellIcon.classList.add('has-reminder');
        } else {
            bellIcon.classList.add('hidden');
            bellIcon.classList.remove('has-reminder');
        }
    },
    
    async loadOfflineRecords() {
        if (typeof OfflineStorage === 'undefined') {
            console.log('❌ OfflineStorage nicht verfügbar');
            return;
        }
        
        try {
            console.log('🔄 Lade offline Akten...');
            const pendingRecords = await OfflineStorage.getPendingRecords();
            console.log(`📊 Gefundene offline Akten: ${pendingRecords.length}`);
            
            if (pendingRecords.length > 0) {
                // Offline Akten zu this.records hinzufügen
                // Verwende temp_id als eindeutige ID für lokale Identifikation
                const offlineRecords = pendingRecords.map(record => ({
                    ...record,
                    id: record.temp_id, // temp_id als ID verwenden
                    is_offline: true,
                    number: record.number || 'OFFLINE-' + record.temp_id
                }));
                
                // Prüfen ob bereits in this.records vorhanden (Duplikate vermeiden)
                const existingTempIds = new Set(this.records.filter(r => r.is_offline).map(r => r.id));
                const newRecords = offlineRecords.filter(r => !existingTempIds.has(r.id));
                
                console.log(`📊 Neue offline Akten: ${newRecords.length}`);
                
                // Neue offline Akten am Anfang der Liste hinzufügen
                this.records = [...newRecords, ...this.records];
                this.renderRecords();
            }
        } catch (e) {
            console.error('❌ Fehler beim Laden der offline Akten:', e);
        }
    },
    
    async syncPendingRecords() {
        if (typeof OfflineStorage === 'undefined') return;

        // Button deaktivieren während der Synchronisation
        const syncButton = document.getElementById('syncButton');
        const syncButtonText = document.getElementById('syncButtonText');
        if (syncButton) {
            syncButton.disabled = true;
            syncButtonText.textContent = 'Synchronisiere...';
        }

        // Prüfen ob Online
        const isOnline = await OfflineStorage.isOnline();
        if (!isOnline) {
            console.log('⏭️ Offline - Synchronisation übersprungen');
            this.updateOfflineIndicator();
            return;
        }

        // Prüfen ob Benutzer eingeloggt ist (für Online-Sync erforderlich)
        if (!this.currentUser || this.currentUser.username === 'Offline-Modus') {
            console.log('⏭️ Nicht eingeloggt oder im Offline-Modus - Synchronisation übersprungen');
            this.updateOfflineIndicator();
            this.updateAuthButton(); // Button zu "Anmelden" wechseln
            return;
        }

        const pendingRecords = await OfflineStorage.getPendingRecords();
        const pendingFiles = await OfflineStorage.getPendingFiles();
        console.log(`Gefundene offline Akten: ${pendingRecords.length}`);
        console.log(`Gefundene offline Dateien: ${pendingFiles.length}`);

        if (pendingRecords.length === 0 && pendingFiles.length === 0) {
            console.log('Keine ausstehenden Akten/Dateien zum Synchronisieren');
            this.updateOfflineIndicator();
            return;
        }

        console.log(`Synchronisiere ${pendingRecords.length} Akten und ${pendingFiles.length} Dateien...`);
        this.toast(`Synchronisiere ${pendingRecords.length + pendingFiles.length} Elemente...`, 'info');

        try {
            let successCount = 0;
            let errorCount = 0;
            const successfullySyncedIds = [];
            const successfullySyncedFileIds = [];

            // Zuerst Akten synchronisieren
            for (const record of pendingRecords) {
                try {
                    console.log(`Synchronisiere Akte: ${record.title}`, record);

                    // Check ob bereits synchronisiert wird (Deduplizierung)
                    if (record.synced) {
                        console.log(`⏭️ Akte bereits synchronisiert, überspringe: ${record.title}`);
                        continue;
                    }

                    // Prüfen ob zu viele Sync-Versuche (um Endlosschleifen zu vermeiden)
                    const maxAttempts = 5;
                    if (record.sync_attempts >= maxAttempts) {
                        console.error(`❌ Akte "${record.title}" hat ${maxAttempts} Sync-Versuche erreicht, wird übersprungen`);
                        errorCount++;
                        this.toast(`Akte "${record.title}" konnte nicht synchronisiert werden (zu viele Versuche)`, 'error');
                        continue;
                    }

                    // Als "in Synchronisation" markieren vor dem Senden
                    await OfflineStorage.markAsSynced(record.id);

                    // Akte zum Server senden
                    const body = {
                        title: record.title,
                        address: record.address,
                        content: record.content,
                        hashtags: record.hashtags,
                        status: record.status,
                        border_color: record.border_color,
                        category_id: record.category_id,
                        reminder_date: record.reminder_date,
                        reminder_end_date: record.reminder_end_date,
                        reminder_repeat: record.reminder_repeat,
                        reminder_assigned_to: record.reminder_assigned_to
                    };

                    console.log('Sende Daten an Server:', body);
                    const result = await this.apiPost('/records', body);
                    console.log('Server-Antwort:', result);

                    // Erinnerung erstellen, wenn vorhanden
                    if (record.pending_reminder && result.record) {
                        console.log('Erstelle Erinnerung:', record.pending_reminder);
                        await this.apiPost(`/records/${result.record.id}/reminders`, record.pending_reminder);
                    }

                    // Aus lokalem Storage löschen
                    await OfflineStorage.deleteSyncedRecord(record.id);
                    console.log(`Akte "${record.title}" aus lokalem Storage gelöscht`);

                    successfullySyncedIds.push(record.temp_id);
                    successCount++;
                    console.log(`✅ Akte "${record.title}" erfolgreich synchronisiert`);
                } catch (e) {
                    errorCount++;
                    console.error(`❌ Fehler beim Synchronisieren der Akte "${record.title}":`, e);

                    // Spezielle Behandlung für Authentifizierungsfehler
                    if (e.response && (e.response.status === 401 || e.response.status === 403)) {
                        console.error('Authentifizierungsfehler bei Synchronisation - stoppe Sync');
                        this.showLogin('Nicht authentifiziert. Bitte loggen Sie sich ein.', 'error');
                        return; // Synchronisation abbrechen
                    }

                    this.toast(`Fehler bei "${record.title}": ${e.message}`, 'error');

                    // Sync-Attempt erhöhen und zurücksetzen des synced-Flags
                    record.sync_attempts = (record.sync_attempts || 0) + 1;
                    await OfflineStorage.markAsUnsynced(record.id);
                }
            }

            // Dann Dateien synchronisieren
            for (const file of pendingFiles) {
                try {
                    console.log(`Synchronisiere Datei: ${file.filename}`, file);

                    // Prüfen ob die zugehörige Akte bereits synchronisiert wurde
                    const relatedRecord = successfullySyncedIds.includes(file.temp_record_id);
                    if (!relatedRecord) {
                        console.log(`⏭️ Datei übersprungen - Akte noch nicht synchronisiert`);
                        continue;
                    }

                    // Datei hochladen
                    const formData = new FormData();
                    formData.append('file', this.base64ToFile(file.data, file.filename));

                    const response = await this.uploadFileWithProgress(`/records/${file.record_id}/files`, formData, file.filename);
                    console.log('Server-Antwort Datei-Upload:', response);

                    // Als synchronisiert markieren
                    await OfflineStorage.markFileAsSynced(file.id);
                    console.log(`Datei "${file.filename}" als synchronisiert markiert`);

                    // Aus lokalem Storage löschen
                    await OfflineStorage.deleteSyncedFile(file.id);
                    console.log(`Datei "${file.filename}" aus lokalem Storage gelöscht`);

                    successfullySyncedFileIds.push(file.id);

                    successCount++;
                    console.log(`✅ Datei "${file.filename}" erfolgreich synchronisiert`);
                } catch (e) {
                    errorCount++;
                    console.error(`❌ Fehler beim Synchronisieren der Datei "${file.filename}":`, e);
                    this.toast(`Fehler bei Datei "${file.filename}": ${e.message}`, 'error');
                    file.sync_attempts = (file.sync_attempts || 0) + 1;
                }
            }

            console.log(`Sync abgeschlossen: ${successCount} erfolgreich, ${errorCount} fehlgeschlagen`);

            // Nur erfolgreich synchronisierte Akten aus lokaler Liste entfernen
            if (successfullySyncedIds.length > 0) {
                console.log('Entferne erfolgreich synchronisierte Akten aus lokaler Liste:', successfullySyncedIds);
                this.records = this.records.filter(r => !successfullySyncedIds.includes(r.id));
                this.renderRecords();
            }

            // Liste neu laden (um die synchronisierten Akten vom Server zu laden)
            if (successCount > 0) {
                console.log('Lade Aktenliste neu...');
                await this.loadRecords();
            }

            // Offline-Indikator aktualisieren
            this.updateOfflineIndicator();

            // Button wieder aktivieren
            if (syncButton) {
                syncButton.disabled = false;
                syncButtonText.textContent = 'Synchronisieren';
            }

            // Ergebnis-Meldung
            if (errorCount === 0) {
                this.toast(`Alle ${successCount} Elemente erfolgreich synchronisiert`, 'success');
            } else {
                this.toast(`${successCount} erfolgreich, ${errorCount} fehlgeschlagen`, 'warning');
            }
        } catch (e) {
            console.error('❌ Fehler bei der Synchronisation:', e);
            this.toast('Fehler bei der Synchronisation: ' + e.message, 'error');

            // Button wieder aktivieren
            if (syncButton) {
                syncButton.disabled = false;
                syncButtonText.textContent = 'Synchronisieren';
            }

            this.updateOfflineIndicator();
        }
    },

    // Hilfsfunktion: Base64 zu File konvertieren
    base64ToFile(base64, filename) {
        const arr = base64.split(',');
        const mime = arr[0].match(/:(.*?);/)[1];
        const bstr = atob(arr[1]);
        let n = bstr.length;
        const u8arr = new Uint8Array(n);
        while (n--) {
            u8arr[n] = bstr.charCodeAt(n);
        }
        return new File([u8arr], filename, { type: mime });
    },

    async updateOfflineIndicator() {
        const syncButton = document.getElementById('syncButton');
        const syncButtonText = document.getElementById('syncButtonText');

        if (!syncButton || !syncButtonText) {
            console.log('❌ Sync-Button Elemente nicht gefunden');
            return;
        }

        // Einfache Server-Prüfung ohne OfflineStorage-Abhängigkeit
        let isOnline = false;
        let pendingCount = 0;

        // Manueller Offline-Modus hat Priorität
        if (this.manualOfflineMode) {
            console.log('🔒 Manueller Offline-Modus aktiv - Server-Check übersprungen');
            isOnline = false;
        } else {
            try {
                const response = await fetch('/api/health', {
                    method: 'GET',
                    cache: 'no-cache',
                    signal: AbortSignal.timeout(1500)
                });
                isOnline = response.ok;
                console.log(`📡 Server-Check: ${isOnline ? '✅ Online' : '❌ Offline'} (Status: ${response.status})`);
            } catch (e) {
                console.log('❌ Server-Check fehlgeschlagen (schneller Timeout):', e.message);
                isOnline = false;
            }
        }

        // Wenn OfflineStorage verfügbar und Online, pendingCount holen
        if (typeof OfflineStorage !== 'undefined' && isOnline) {
            try {
                pendingCount = await OfflineStorage.getPendingCount();
                console.log(`📊 Ausstehende Synchronisationen: ${pendingCount}`);
            } catch (e) {
                console.error('❌ getPendingCount fehlgeschlagen:', e);
            }
        }

        console.log(`🔄 Update Offline Indicator: Online=${isOnline}, Pending=${pendingCount}`);

        // Erkennen, wenn Verbindung verloren geht
        // Automatischer Offline-Modus-Wechsel deaktiviert - nur manueller Wechsel erlaubt
        if (this.wasOnline && !isOnline && !this.manualOfflineMode) {
            console.log('⚠️ Verbindung zum Server verloren - Kein automatischer Offline-Modus-Wechsel');
            this.wasOnline = false;
            // this.showOfflineModeConfirmation(); // Deaktiviert - nur manueller Wechsel erlaubt
        } else if (!this.wasOnline && isOnline) {
            console.log('✅ Verbindung wiederhergestellt');
            this.wasOnline = true;
        }

        // Sync-Button aktualisieren
        if (!isOnline) {
            syncButton.disabled = true;
            syncButtonText.textContent = `Warte auf Verbindung...`;
            syncButton.style.opacity = '0.5';
            syncButton.style.cursor = 'not-allowed';
            console.log('⚠️ Sync-Button: Server offline');
        } else if (pendingCount > 0) {
            syncButton.disabled = false;
            syncButtonText.textContent = `Synchronisieren (${pendingCount})`;
            syncButton.style.opacity = '1';
            syncButton.style.cursor = 'pointer';
            console.log('✅ Sync-Button aktiv: Synchronisieren (' + pendingCount + ')');
        } else {
            syncButton.disabled = true;
            syncButtonText.textContent = 'Alles synchronisiert';
            syncButton.style.opacity = '0.5';
            syncButton.style.cursor = 'default';
            console.log('✅ Sync-Button: Alles synchronisiert');
        }
    },

    updateOfflineIndicatorFallback() {
        const syncButton = document.getElementById('syncButton');
        const syncButtonText = document.getElementById('syncButtonText');

        if (syncButton && syncButtonText) {
            syncButton.disabled = true;
            syncButtonText.textContent = 'Alles synchronisiert';
            syncButton.style.opacity = '0.5';
            syncButton.style.cursor = 'default';
            console.log('🔄 Fallback: Sync-Button auf alles synchronisiert gesetzt');
        }
    },

    startConnectionCheck() {
        // Periodische Verbindungstprüfung alle 10 Sekunden
        if (this.connectionCheckInterval) {
            clearInterval(this.connectionCheckInterval);
        }

        // Sofort einmal prüfen
        this.checkConnectionStatus();

        // Dann alle 10 Sekunden prüfen
        this.connectionCheckInterval = setInterval(() => {
            console.log('🔄 Führe periodische Verbindungstprüfung durch...');
            this.checkConnectionStatus();
        }, 10000);

        console.log('✅ Periodische Verbindungstprüfung gestartet (alle 10 Sekunden)');
    },

    async updateConnectionStatusUI(isOnline) {
        // Status-Indikator direkt aktualisieren
        const connectionStatusSimple = document.getElementById('connectionStatusSimple');
        if (connectionStatusSimple) {
            connectionStatusSimple.className = 'connection-status-simple';
            const statusText = connectionStatusSimple.querySelector('.connection-text-simple');

            if (!isOnline) {
                connectionStatusSimple.classList.add('offline');
                if (statusText) statusText.textContent = 'Offline';
                console.log('✅ Status aktualisiert: Offline');
            } else {
                // Prüfen auf ausstehende Sync wenn OfflineStorage verfügbar
                let pendingCount = 0;
                if (typeof OfflineStorage !== 'undefined') {
                    try {
                        pendingCount = await OfflineStorage.getPendingCount();
                    } catch (e) {
                        console.error('❌ getPendingCount fehlgeschlagen:', e);
                    }
                }

                if (pendingCount > 0) {
                    connectionStatusSimple.classList.add('pending');
                    if (statusText) statusText.textContent = 'Sync...';
                    console.log('✅ Status aktualisiert: Sync...');
                } else {
                    connectionStatusSimple.classList.add('online');
                    if (statusText) statusText.textContent = 'Online';
                    console.log('✅ Status aktualisiert: Online');
                }
            }
        }
    },

    async checkConnectionStatus() {
        try {
            console.log('=== Prüfe Verbindungsstatus ===');

            // Manueller Offline-Modus hat Priorität
            if (this.manualOfflineMode) {
                console.log('🔒 Manueller Offline-Modus aktiv - Verbindungsprüfung übersprungen');
                await this.updateConnectionStatusUI(false);
                return;
            }

            // Direkter Fetch-Call auf Health-Endpoint mit schnellem Timeout (1 Sekunde)
            let isOnline = false;
            try {
                const response = await fetch('/api/health', {
                    method: 'GET',
                    cache: 'no-cache',
                    signal: AbortSignal.timeout(1500) // 1.5 Sekunden Timeout für schnelle Offline-Erkennung
                });
                isOnline = response.ok;
                console.log(`📡 Verbindungsstatus: ${isOnline ? 'Online' : 'Offline'} (Status: ${response.status})`);
            } catch (e) {
                console.log(`❌ Verbindungstprüfung fehlgeschlagen (schneller Timeout):`, e.message);
                isOnline = false;
            }
            
            // Status-Indikator direkt aktualisieren
            await this.updateConnectionStatusUI(isOnline);
            
            // Sync-Button auch aktualisieren wenn OfflineStorage verfügbar
            if (typeof OfflineStorage !== 'undefined') {
                await this.updateOfflineIndicator();
                
                // Wenn Online geworden und ausstehende Sync, automatisch syncen
                if (isOnline) {
                    const pendingCount = await OfflineStorage.getPendingCount();
                    if (pendingCount > 0) {
                        console.log('🔄 Automatische Sync bei Verbindungstprüfung');
                        this.syncPendingRecords();
                    }
                }
            }
            
            // Bei Verbindungswiederherstellung Daten neu laden
            if (isOnline && !this.wasOnline) {
                console.log('🔄 Verbindung wiederhergestellt - Daten werden neu geladen');
                this.wasOnline = true;
                
                // Aktuellen Bereich neu laden
                if (this.currentSection === 'gallery') {
                    console.log('🔄 Galerie wird neu geladen');
                    this.loadGallery(false);
                } else if (this.currentSection === 'records') {
                    console.log('🔄 Akten werden neu geladen');
                    this.loadRecords(false, false);
                } else if (this.currentSection === 'karte') {
                    console.log('🔄 Karte wird neu geladen');
                    this.loadKarte(this.karteAktiveIds || null);
                } else if (this.currentSection === 'calendar') {
                    console.log('🔄 Kalender wird neu geladen');
                    this.renderCalendar();
                }
                
                // Kategorien neu laden
                this.loadCategories();
            } else if (!isOnline) {
                this.wasOnline = false;
            }
        } catch (e) {
            console.error('❌ Fehler bei Verbindungstprüfung:', e);
            // Bei Fehler auf Offline schalten
            const connectionStatusSimple = document.getElementById('connectionStatusSimple');
            if (connectionStatusSimple) {
                connectionStatusSimple.className = 'connection-status-simple offline';
                const statusText = connectionStatusSimple.querySelector('.connection-text-simple');
                if (statusText) statusText.textContent = 'Offline';
                console.log('✅ Status aktualisiert: Offline (wegen Fehler)');
            }
            
            // Sync-Button auch auf Offline setzen
            const syncButton = document.getElementById('syncButton');
            const syncButtonText = document.getElementById('syncButtonText');
            if (syncButton && syncButtonText) {
                syncButton.disabled = true;
                syncButtonText.textContent = 'Warte auf Verbindung...';
                syncButton.style.opacity = '0.5';
                syncButton.style.cursor = 'not-allowed';
            }
            
            this.wasOnline = false;
        }
    },

    stopConnectionCheck() {
        if (this.connectionCheckInterval) {
            clearInterval(this.connectionCheckInterval);
            this.connectionCheckInterval = null;
            console.log('Periodische Verbindungstprüfung gestoppt');
        }
    },

    toggleSidebarFooter() {
        const footer = document.getElementById('sidebarFooter');
        const toggle = document.getElementById('sidebarFooterToggle');
        const icon = document.getElementById('sidebarFooterToggleIcon');

        if (footer && toggle && icon) {
            footer.classList.toggle('collapsed');
            toggle.classList.toggle('collapsed');

            // Warten bis Animation fertig ist, dann Pfeil ändern
            setTimeout(() => {
                if (footer.classList.contains('collapsed')) {
                    // Footer ist eingeklappt -> Pfeil nach oben (zum Ausklappen)
                    icon.classList.remove('fa-chevron-down');
                    icon.classList.add('fa-chevron-up');
                } else {
                    // Footer ist ausgeklappt -> Pfeil nach unten (zum Einklappen)
                    icon.classList.remove('fa-chevron-up');
                    icon.classList.add('fa-chevron-down');
                }
            }, 300); // 300ms = CSS transition Zeit
        }
    },

    // ── Chat Functions ───────────────────────────
    currentChatRoom: null,
    currentConversation: null,
    chatTab: 'rooms',
    chatPollingInterval: null,
    chatEventSource: null,

    chatSaveState() {
        // Speichert den aktuellen Chat-Zustand im localStorage
        this.safeLocalStorage.setItem('lastChatRoom', this.currentChatRoom || '');
        this.safeLocalStorage.setItem('lastConversation', this.currentConversation || '');
        this.safeLocalStorage.setItem('lastChatTab', this.chatTab);
    },

    chatRestoreState() {
        // Stellt den letzten Chat-Zustand wieder her
        const lastRoom = this.safeLocalStorage.getItem('lastChatRoom');
        const lastConversation = this.safeLocalStorage.getItem('lastConversation');
        const lastTab = this.safeLocalStorage.getItem('lastChatTab') || 'rooms';

        // Tab wiederherstellen
        this.chatTab = lastTab;
        document.querySelectorAll('.chat-tab').forEach(t => {
            t.classList.toggle('active', t.dataset.tab === lastTab);
        });
        document.getElementById('chatRoomsList').classList.toggle('hidden', lastTab !== 'rooms');
        document.getElementById('chatConversationsList').classList.toggle('hidden', lastTab !== 'conversations');

        const title = document.getElementById('chatSidebarTitle');
        const newBtn = document.getElementById('chatNewBtn');

        if (lastTab === 'rooms') {
            title.innerHTML = '<i class="fas fa-comments"></i> Chat-Räume';
            if (newBtn) {
                newBtn.innerHTML = '<i class="fas fa-plus"></i> Neuer Raum';
                newBtn.onclick = () => this.chatCreateRoom();
                newBtn.classList.remove('hidden');
            }
            this.chatLoadRooms();
        } else {
            title.innerHTML = '<i class="fas fa-user"></i> Privat';
            if (newBtn) {
                newBtn.classList.add('hidden');
            }
            this.chatLoadUsers();
        }

        // Raum oder Konversation wiederherstellen
        if (lastTab === 'rooms' && lastRoom) {
            // Raum wiederherstellen
            const roomId = parseInt(lastRoom);
            const roomItem = document.querySelector(`.chat-room-item[onclick*="${roomId}"]`);
            if (roomItem) {
                roomItem.click();
            }
        } else if (lastTab === 'conversations' && lastConversation) {
            // Konversation wiederherstellen
            const userId = parseInt(lastConversation);
            const convItem = document.querySelector(`.chat-room-item[onclick*="${userId}"]`);
            if (convItem) {
                convItem.click();
            }
        }
    },

    chatSwitchTab(tab) {
        this.chatTab = tab;

        // Update tab UI
        document.querySelectorAll('.chat-tab').forEach(t => {
            t.classList.toggle('active', t.dataset.tab === tab);
        });

        document.getElementById('chatRoomsList').classList.toggle('hidden', tab !== 'rooms');
        document.getElementById('chatConversationsList').classList.toggle('hidden', tab !== 'conversations');

        const title = document.getElementById('chatSidebarTitle');
        const newBtn = document.getElementById('chatNewBtn');

        if (tab === 'rooms') {
            title.innerHTML = '<i class="fas fa-comments"></i> Chat-Räume';
            if (newBtn) {
                newBtn.innerHTML = '<i class="fas fa-plus"></i> Neuer Raum';
                newBtn.onclick = () => this.chatCreateRoom();
                newBtn.classList.remove('hidden');
            }
            this.chatLoadRooms();
            // Stop user list refresh interval
            if (this.chatUserListInterval) {
                clearInterval(this.chatUserListInterval);
                this.chatUserListInterval = null;
            }
        } else {
            title.innerHTML = '<i class="fas fa-user"></i> Privat';
            if (newBtn) {
                newBtn.classList.add('hidden');
            }
            this.chatLoadUsers();
            // Start user list refresh interval (every 30 seconds)
            if (this.chatUserListInterval) {
                clearInterval(this.chatUserListInterval);
            }
            this.chatUserListInterval = setInterval(() => {
                this.chatLoadUsers();
            }, 30000);
        }

        // Reset main view
        this.currentChatRoom = null;
        this.currentConversation = null;
        this.chatStopPolling();
        document.getElementById('chatRoomTitle').textContent = tab === 'rooms' ? 'Wähle einen Chat-Raum' : 'Wähle eine Konversation';
        document.getElementById('chatInputContainer').classList.add('hidden');
        document.getElementById('chatDeleteRoomBtn').classList.add('hidden');
        document.getElementById('chatClearChatBtn').classList.add('hidden');
        document.getElementById('chatMessages').innerHTML = '<div class="chat-empty-state"><i class="fas fa-comments"></i><p>' + (tab === 'rooms' ? 'Wähle einen Chat-Raum aus der Liste' : 'Wähle eine Konversation aus der Liste') + '</p></div>';
    },

    async chatLoadRooms() {
        try {
            const data = await this.apiGet('/chat/rooms', false);
            if (data.success) {
                // Ungelesene Nachrichten pro Raum zählen
                let totalUnread = 0;
                data.rooms.forEach(room => {
                    totalUnread += room.unread_count || 0;
                });
                this.chatRenderRooms(data.rooms);
                // Tab-Badge aktualisieren
                this.chatUpdateTabBadge('rooms', totalUnread);
            }
        } catch (e) {
            console.error('Fehler beim Laden der Chat-Räume:', e);
        }
    },

    async chatLoadUsers() {
        try {
            const data = await this.apiGet('/records/users', false);
            console.log('Benutzer-Daten vom Server:', data);
            if (data.success) {
                // Ungelesene Nachrichten laden
                const unreadData = await this.apiGet('/chat/unread-counts', false);
                const unreadCounts = {};
                let totalUnread = 0;
                if (unreadData.success) {
                    unreadData.unread_counts.forEach(uc => {
                        unreadCounts[uc.other_user_id] = uc.unread_count;
                        totalUnread += uc.unread_count;
                    });
                }
                console.log('Ungelesene Counts:', unreadCounts);
                this.chatRenderUsers(data.users, unreadCounts);
                // Tab-Badge aktualisieren
                this.chatUpdateTabBadge('conversations', totalUnread);
            }
        } catch (e) {
            console.error('Fehler beim Laden der Benutzer:', e);
        }
    },

    chatUpdateTabBadge(tab, count) {
        const badge = document.getElementById(`${tab}TabBadge`);
        if (badge) {
            if (count > 0) {
                badge.textContent = count > 99 ? '99+' : count;
                badge.classList.add('active');
            } else {
                badge.classList.remove('active');
            }
        }
    },

    chatUpdateSidebarBadge(totalUnread) {
        const badge = document.getElementById('sidebarChatBadge');
        if (badge) {
            if (totalUnread > 0) {
                badge.textContent = totalUnread > 99 ? '99+' : totalUnread;
                badge.classList.remove('hidden');
            } else {
                badge.classList.add('hidden');
            }
        }
    },

    async chatUpdateUnreadCount() {
        try {
            // Ungelesene Nachrichten aus Räumen abrufen
            const roomsData = await this.apiGet('/chat/rooms', false);
            let totalUnread = 0;
            if (roomsData.success) {
                roomsData.rooms.forEach(room => {
                    totalUnread += room.unread_count || 0;
                });
            }

            // Ungelesene Nachrichten aus privaten Konversationen abrufen
            const conversationsData = await this.apiGet('/chat/conversations', false);
            if (conversationsData.success) {
                conversationsData.conversations.forEach(conv => {
                    totalUnread += conv.unread_count || 0;
                });
            }

            // Badge aktualisieren
            this.chatUpdateSidebarBadge(totalUnread);
        } catch (e) {
            console.error('Fehler beim Abrufen der ungelesenen Nachrichten:', e);
        }
    },

    chatRenderUsers(users, unreadCounts = {}) {
        const container = document.getElementById('chatConversationsList');
        if (!container) return;

        console.log('Benutzer zum Rendern:', users);
        console.log('Ungelesene Counts:', unreadCounts);
        console.log('Aktueller Benutzer:', this.currentUser);

        if (users.length === 0) {
            container.innerHTML = '<div class="chat-empty-state"><p>Keine Benutzer gefunden</p></div>';
            return;
        }

        // Filter out current user
        const otherUsers = users.filter(u => u.id !== this.currentUser?.id);
        console.log('Gefilterte Benutzer:', otherUsers);

        if (otherUsers.length === 0) {
            container.innerHTML = '<div class="chat-empty-state"><p>Keine anderen Benutzer verfügbar</p></div>';
            return;
        }

        container.innerHTML = otherUsers.map(user => {
            const unreadCount = unreadCounts[user.id] || 0;
            const unreadBadge = unreadCount > 0 ? `<span class="chat-unread-badge">${unreadCount}</span>` : '';
            return `
            <div class="chat-room-item" onclick="App.chatSelectConversation(${user.id})">
                <div class="chat-room-name">${this.escapeHtml(user.username)}</div>
                <div class="chat-room-meta">
                    <span class="user-status ${user.is_online ? 'online' : 'offline'}">
                        <i class="fas fa-circle"></i> ${user.is_online ? 'Online' : 'Offline'}
                    </span>
                    ${unreadBadge}
                </div>
            </div>
        `;
        }).join('');
    },

    chatRenderRooms(rooms) {
        const container = document.getElementById('chatRoomsList');
        if (!container) return;

        if (rooms.length === 0) {
            container.innerHTML = '<div class="chat-empty-state"><p>Keine Chat-Räume vorhanden</p></div>';
            return;
        }

        container.innerHTML = rooms.map(room => `
            <div class="chat-room-item ${this.currentChatRoom === room.id ? 'active' : ''}" 
                 onclick="App.chatSelectRoom(${room.id})">
                <div class="chat-room-name">${this.escapeHtml(room.name)}</div>
                <div class="chat-room-meta">
                    <span>${room.message_count || 0} Nachrichten</span>
                    <span>${room.last_message_at ? this.formatDate(room.last_message_at) : ''}</span>
                </div>
            </div>
        `).join('');
    },

    async chatLoadConversations() {
        try {
            const data = await this.apiGet('/chat/conversations');
            if (data.success) {
                this.chatRenderConversations(data.conversations);
            }
        } catch (e) {
            console.error('Fehler beim Laden der Konversationen:', e);
        }
    },

    chatRenderConversations(conversations) {
        const container = document.getElementById('chatConversationsList');
        if (!container) return;

        if (conversations.length === 0) {
            container.innerHTML = '<div class="chat-empty-state"><p>Keine Konversationen vorhanden</p></div>';
            return;
        }

        container.innerHTML = conversations.map(conv => `
            <div class="chat-room-item ${this.currentConversation === conv.other_user_id ? 'active' : ''}" 
                 onclick="App.chatSelectConversation(${conv.other_user_id}, '${this.escapeHtml(conv.other_username)}')">
                <div class="chat-room-name">${this.escapeHtml(conv.other_username)}</div>
                <div class="chat-room-meta">
                    <span>${conv.unread_count > 0 ? `<span style="color: var(--primary); font-weight: bold;">${conv.unread_count} neu</span>` : 'Keine neuen'}</span>
                    <span>${conv.last_message_at ? this.formatDate(conv.last_message_at) : ''}</span>
                </div>
            </div>
        `).join('');
    },

    async chatStartNewConversation() {
        const username = prompt('Benutzername für private Nachricht:');
        if (!username) return;

        try {
            // Get user ID from username
            const usersData = await this.apiGet('/users');
            if (usersData.success) {
                const user = usersData.users.find(u => u.username === username);
                if (!user) {
                    this.toast('Benutzer nicht gefunden', 'error');
                    return;
                }
                this.chatSelectConversation(user.id, user.username);
            }
        } catch (e) {
            console.error('Fehler beim Starten der Konversation:', e);
            this.toast('Fehler beim Starten der Konversation', 'error');
        }
    },

    async chatSelectRoom(roomId) {
        this.currentChatRoom = roomId;
        this.currentConversation = null;

        // Update active state in UI
        document.querySelectorAll('.chat-room-item').forEach(item => {
            item.classList.remove('active');
        });
        event.currentTarget.classList.add('active');

        // Show input container
        document.getElementById('chatInputContainer').classList.remove('hidden');
        document.getElementById('chatDeleteRoomBtn').classList.remove('hidden');

        // Load room info
        try {
            const data = await this.apiGet(`/chat/rooms/${roomId}/info`);
            if (data.success) {
                document.getElementById('chatRoomTitle').textContent = data.room.name;
            }
        } catch (e) {
            console.error('Fehler beim Laden der Raum-Info:', e);
        }

        // Load messages
        await this.chatLoadMessages(roomId);

        // Start polling for new messages
        this.chatStartPolling();

        // Badge sofort aktualisieren
        this.chatUpdateUnreadCount();

        // Zustand speichern
        this.chatSaveState();
    },

    async chatSelectConversation(otherUserId, otherUsername) {
        this.currentConversation = otherUserId;
        this.currentChatRoom = null;

        // Update active state in UI
        document.querySelectorAll('.chat-room-item').forEach(item => {
            item.classList.remove('active');
        });
        event.currentTarget.classList.add('active');

        // Show input container
        document.getElementById('chatInputContainer').classList.remove('hidden');
        document.getElementById('chatDeleteRoomBtn').classList.add('hidden');
        document.getElementById('chatClearChatBtn').classList.remove('hidden');

        // Set title
        document.getElementById('chatRoomTitle').textContent = otherUsername;

        // Load messages
        await this.chatLoadPrivateMessages(otherUserId);

        // Start polling for new messages
        this.chatStartPolling();

        // Badge sofort aktualisieren
        this.chatUpdateUnreadCount();

        // Zustand speichern
        this.chatSaveState();
    },

    async chatLoadMessages(roomId) {
        try {
            const data = await this.apiGet(`/chat/rooms/${roomId}/messages`);
            if (data.success) {
                this.chatRenderMessages(data.messages);
            }
        } catch (e) {
            console.error('Fehler beim Laden der Nachrichten:', e);
        }
    },

    async chatLoadPrivateMessages(otherUserId) {
        try {
            const data = await this.apiGet(`/chat/conversations/${otherUserId}/messages`);
            if (data.success) {
                this.chatRenderMessages(data.messages);
            }
        } catch (e) {
            console.error('Fehler beim Laden der privaten Nachrichten:', e);
        }
    },

    chatRenderMessages(messages) {
        const container = document.getElementById('chatMessages');
        if (!container) return;

        if (messages.length === 0) {
            container.innerHTML = '<div class="chat-empty-state"><i class="fas fa-comments"></i><p>Noch keine Nachrichten</p></div>';
            return;
        }

        const isPrivate = !!this.currentConversation;

        // Farben für Avatare basierend auf Username
        const avatarColors = [
            '#e91e63', '#9c27b0', '#673ab7', '#3f51b5', '#2196f3',
            '#03a9f4', '#00bcd4', '#009688', '#4caf50', '#8bc34a',
            '#cddc39', '#ffc107', '#ff9800', '#ff5722', '#795548'
        ];

        const getAvatarColor = (username) => {
            let hash = 0;
            for (let i = 0; i < username.length; i++) {
                hash = username.charCodeAt(i) + ((hash << 5) - hash);
            }
            return avatarColors[Math.abs(hash) % avatarColors.length];
        };

        container.innerHTML = messages.map(msg => {
            const isOwn = msg.is_own || msg.username === this.currentUser?.username;
            const username = msg.username || msg.sender_username || msg.receiver_username;
            const avatar = username.charAt(0).toUpperCase();
            const avatarColor = isOwn ? 'var(--primary)' : getAvatarColor(username);

            let contentHtml = '';
            if (msg.message_type === 'file' && msg.file_name && msg.file_path) {
                // Prüfen ob es ein Bild ist
                const isImage = msg.file_name.match(/\.(jpg|jpeg|png|gif|webp)$/i);
                if (isImage) {
                    // Bild anzeigen mit error-handler
                    const fileEndpoint = isPrivate ? `/api/chat/private-file/${msg.id}` : `/api/chat/file/${msg.id}`;
                    contentHtml = `
                        <div class="chat-message-bubble">
                            <img src="${fileEndpoint}" class="chat-message-image" alt="${this.escapeHtml(msg.file_name)}" onclick="App.openImageModal('${fileEndpoint}')" onerror="this.style.display='none'; this.nextElementSibling.style.display='flex';">
                            <div class="chat-message-file" style="display: none;">
                                <i class="fas fa-file"></i>
                                <div class="chat-message-file-info">
                                    <div class="chat-message-file-name">${this.escapeHtml(msg.file_name)}</div>
                                    <div class="chat-message-file-size">Datei nicht verfügbar</div>
                                </div>
                            </div>
                        </div>
                    `;
                } else {
                    // Datei-Icon anzeigen
                    const fileSize = this.formatFileSize(msg.file_size);
                    contentHtml = `
                        <div class="chat-message-bubble">
                            <div class="chat-message-file">
                                <i class="fas fa-file"></i>
                                <div class="chat-message-file-info">
                                    <div class="chat-message-file-name">${this.escapeHtml(msg.file_name)}</div>
                                    <div class="chat-message-file-size">${fileSize}</div>
                                </div>
                            </div>
                        </div>
                    `;
                }
            } else if (msg.message_type === 'file' && (!msg.file_path || !msg.file_name)) {
                // Datei wurde gelöscht oder ist nicht verfügbar
                contentHtml = `
                    <div class="chat-message-bubble">
                        <div class="chat-message-file">
                            <i class="fas fa-file"></i>
                            <div class="chat-message-file-info">
                                <div class="chat-message-file-name">Datei nicht verfügbar</div>
                                <div class="chat-message-file-size">Gelöscht</div>
                            </div>
                        </div>
                    </div>
                `;
            } else {
                contentHtml = `<div class="chat-message-bubble">${this.escapeHtml(msg.message)}</div>`;
            }

            // Lösch-Button nur für eigene Nachrichten
            const deleteButton = isOwn ? `
                <button class="chat-message-delete" onclick="App.chatDeleteMessage(${msg.id})">
                    <i class="fas fa-trash"></i>
                </button>
            ` : '';

            return `
                <div class="chat-message ${isOwn ? 'own' : ''}">
                    <div class="chat-message-avatar" style="background: ${avatarColor}">${avatar}</div>
                    <div class="chat-message-content">
                        <div class="chat-message-header">
                            <span class="chat-message-username">${this.escapeHtml(username)}</span>
                            <span class="chat-message-time">${this.formatDate(msg.created_at)}</span>
                            ${deleteButton}
                        </div>
                        ${contentHtml}
                    </div>
                </div>
            `;
        }).join('');

        // Scroll to bottom
        container.scrollTop = container.scrollHeight;
    },

    async chatSendMessage() {
        const input = document.getElementById('chatInput');
        const message = input.value.trim();

        console.log('chatSendMessage aufgerufen. Message:', message, 'pendingImageFile:', this.pendingImageFile);

        // Prüfen ob Text oder Bild vorhanden ist
        if (!message && !this.pendingImageFile) {
            console.log('Kein Text und kein Bild vorhanden - abbrechen');
            return;
        }

        input.value = '';

        try {
            let data;

            // Wenn ein Bild vorhanden ist, dieses zuerst hochladen
            if (this.pendingImageFile) {
                console.log('Sende Bild:', this.pendingImageFile.name);
                const formData = new FormData();
                formData.append('file', this.pendingImageFile);

                if (this.currentChatRoom) {
                    data = await this.apiPost(`/chat/rooms/${this.currentChatRoom}/messages`, formData, true);
                    console.log('Bild an Raum gesendet:', data);
                    if (data.success) {
                        await this.chatLoadMessages(this.currentChatRoom);
                        await this.chatLoadRooms();
                    } else {
                        this.toast(data.error || 'Fehler beim Hochladen', 'error');
                    }
                } else if (this.currentConversation) {
                    data = await this.apiPost(`/chat/conversations/${this.currentConversation}/messages`, formData, true);
                    console.log('Bild an Benutzer gesendet:', data);
                    if (data.success) {
                        await this.chatLoadPrivateMessages(this.currentConversation);
                        await this.chatLoadUsers();
                    } else {
                        this.toast(data.error || 'Fehler beim Hochladen', 'error');
                    }
                }

                // Vorschau entfernen
                this.chatRemoveImagePreview();
            }

            // Wenn Text vorhanden ist, diesen senden
            if (message) {
                if (this.currentChatRoom) {
                    data = await this.apiPost(`/chat/rooms/${this.currentChatRoom}/messages`, { message });
                    if (data.success) {
                        await this.chatLoadMessages(this.currentChatRoom);
                        await this.chatLoadRooms();
                    }
                } else if (this.currentConversation) {
                    console.log('Sende private Nachricht an Benutzer:', this.currentConversation);
                    data = await this.apiPost(`/chat/conversations/${this.currentConversation}/messages`, { message });
                    console.log('Antwort vom Server:', data);
                    if (data.success) {
                        await this.chatLoadPrivateMessages(this.currentConversation);
                    } else {
                        console.error('Fehler beim Senden:', data.error);
                        this.toast(data.error || 'Fehler beim Senden', 'error');
                    }
                }
            }
        } catch (e) {
            console.error('Fehler beim Senden der Nachricht:', e);
            this.toast('Fehler beim Senden der Nachricht', 'error');
        }
    },

    chatHandleFileSelect(event) {
        const file = event.target.files[0];
        if (!file) return;

        // Nur Bilder akzeptieren
        if (!file.type.startsWith('image/')) {
            this.toast('Nur Bilder sind erlaubt', 'error');
            event.target.value = '';
            return;
        }

        // Bild-Vorschau anzeigen
        const reader = new FileReader();
        reader.onload = (e) => {
            const preview = document.getElementById('chatImagePreview');
            const previewImage = document.getElementById('chatPreviewImage');
            previewImage.src = e.target.result;
            preview.classList.remove('hidden');
        };
        reader.readAsDataURL(file);

        // Datei speichern für späteren Upload
        this.pendingImageFile = file;
    },

    chatRemoveImagePreview() {
        const preview = document.getElementById('chatImagePreview');
        const previewImage = document.getElementById('chatPreviewImage');
        const fileInput = document.getElementById('chatFileInput');

        preview.classList.add('hidden');
        previewImage.src = '';
        fileInput.value = '';
        this.pendingImageFile = null;
    },

    async chatHandleFileUpload(event) {
        const file = event.target.files[0];
        if (!file || (!this.currentChatRoom && !this.currentConversation)) return;

        console.log('Datei hochladen:', file.name, file.type, file.size);
        const formData = new FormData();
        formData.append('file', file);

        try {
            let data;
            if (this.currentChatRoom) {
                console.log('Sende Datei an Raum:', this.currentChatRoom);
                data = await this.apiPost(`/chat/rooms/${this.currentChatRoom}/messages`, formData, true);
                console.log('Antwort vom Server:', data);
                if (data.success) {
                    await this.chatLoadMessages(this.currentChatRoom);
                    await this.chatLoadRooms();
                } else {
                    this.toast(data.error || 'Fehler beim Hochladen', 'error');
                }
            } else if (this.currentConversation) {
                console.log('Sende Datei an Benutzer:', this.currentConversation);
                data = await this.apiPost(`/chat/conversations/${this.currentConversation}/messages`, formData, true);
                console.log('Antwort vom Server:', data);
                if (data.success) {
                    await this.chatLoadPrivateMessages(this.currentConversation);
                    await this.chatLoadUsers();
                } else {
                    this.toast(data.error || 'Fehler beim Hochladen', 'error');
                }
            }
        } catch (e) {
            console.error('Fehler beim Hochladen der Datei:', e);
            this.toast('Fehler beim Hochladen der Datei', 'error');
        }
        // Reset file input
        event.target.value = '';
    },

    async chatCreateRoom() {
        const modal = document.getElementById('chatCreateRoomModal');
        const input = document.getElementById('chatRoomName');
        input.value = '';
        modal.classList.add('show');
    },

    closeChatCreateRoomModal() {
        const modal = document.getElementById('chatCreateRoomModal');
        modal.classList.remove('show');
    },

    showConfirmModal(title, message, onConfirm) {
        const modal = document.getElementById('confirmModal');
        const titleEl = document.getElementById('confirmModalTitle');
        const messageEl = document.getElementById('confirmModalMessage');
        const confirmBtn = document.getElementById('confirmModalConfirmBtn');

        titleEl.innerHTML = title;
        messageEl.textContent = message;

        // Remove old event listener
        const newConfirmBtn = confirmBtn.cloneNode(true);
        confirmBtn.parentNode.replaceChild(newConfirmBtn, confirmBtn);

        // Add new event listener
        newConfirmBtn.addEventListener('click', () => {
            onConfirm();
            this.closeConfirmModal();
        });

        modal.classList.add('show');
    },

    closeConfirmModal() {
        const modal = document.getElementById('confirmModal');
        modal.classList.remove('show');
    },

    async submitChatCreateRoom() {
        const name = document.getElementById('chatRoomName').value.trim();
        if (!name) {
            this.toast('Bitte einen Namen eingeben', 'error');
            return;
        }

        try {
            const data = await this.apiPost('/chat/rooms', { name });
            if (data.success) {
                this.toast('Chat-Raum erstellt', 'success');
                await this.chatLoadRooms();
                this.closeChatCreateRoomModal();
            }
        } catch (e) {
            console.error('Fehler beim Erstellen des Chat-Raums:', e);
            this.toast('Fehler beim Erstellen des Chat-Raums', 'error');
        }
    },

    async chatDeleteRoom() {
        if (!this.currentChatRoom) return;

        this.showConfirmModal(
            '<i class="fas fa-trash"></i> Chat-Raum löschen',
            'Chat-Raum wirklich löschen?',
            async () => {
                try {
                    const data = await this.apiDelete(`/chat/rooms/${this.currentChatRoom}`);
                    if (data.success) {
                        this.toast('Chat-Raum gelöscht', 'success');
                        this.currentChatRoom = null;
                        document.getElementById('chatRoomTitle').textContent = 'Wähle einen Chat-Raum';
                        document.getElementById('chatInputContainer').classList.add('hidden');
                        document.getElementById('chatDeleteRoomBtn').classList.add('hidden');
                        document.getElementById('chatMessages').innerHTML = '<div class="chat-empty-state"><i class="fas fa-comments"></i><p>Wähle einen Chat-Raum aus der Liste</p></div>';
                        await this.chatLoadRooms();
                        this.chatStopPolling();
                    }
                } catch (e) {
                    console.error('Fehler beim Löschen des Chat-Raums:', e);
                    this.toast('Fehler beim Löschen des Chat-Raums', 'error');
                }
            }
        );
    },

    async chatDeleteMessage(messageId) {
        this.showConfirmModal(
            '<i class="fas fa-trash"></i> Nachricht löschen',
            'Nachricht wirklich löschen?',
            async () => {
                try {
                    const endpoint = this.currentConversation
                        ? `/chat/conversations/${this.currentConversation}/messages/${messageId}`
                        : `/chat/messages/${messageId}`;

                    const data = await this.apiDelete(endpoint);
                    if (data.success) {
                        this.toast('Nachricht gelöscht', 'success');
                        if (this.currentConversation) {
                            await this.chatLoadPrivateMessages(this.currentConversation);
                        } else if (this.currentChatRoom) {
                            await this.chatLoadMessages(this.currentChatRoom);
                        }
                    }
                } catch (e) {
                    console.error('Fehler beim Löschen der Nachricht:', e);
                    this.toast('Fehler beim Löschen der Nachricht', 'error');
                }
            }
        );
    },

    async chatClearConversation() {
        if (!this.currentConversation) return;

        this.showConfirmModal(
            '<i class="fas fa-eraser"></i> Chatverlauf löschen',
            'Wirklich den kompletten Chatverlauf löschen?',
            async () => {
                try {
                    const data = await this.apiDelete(`/chat/conversations/${this.currentConversation}/clear`);
                    if (data.success) {
                        this.toast('Chatverlauf gelöscht', 'success');
                        await this.chatLoadPrivateMessages(this.currentConversation);
                    }
                } catch (e) {
                    console.error('Fehler beim Löschen des Chatverlaufs:', e);
                    this.toast('Fehler beim Löschen des Chatverlaufs', 'error');
                }
            }
        );
    },

    chatStartPolling() {
        this.chatStopPolling();
        
        // Use SSE for real-time updates
        try {
            this.chatEventSource = new EventSource('/api/chat/stream');
            
            this.chatEventSource.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    
                    // Update if we have new messages in current room/conversation
                    if (this.currentChatRoom && data.rooms) {
                        const roomUpdate = data.rooms.find(r => r.room_id === this.currentChatRoom);
                        if (roomUpdate) {
                            this.chatLoadMessages(this.currentChatRoom);
                        }
                        this.chatLoadRooms();
                    }
                    
                    if (this.currentConversation && data.private) {
                        const privateUpdate = data.private.find(p => p.sender_id === this.currentConversation);
                        if (privateUpdate) {
                            this.chatLoadPrivateMessages(this.currentConversation);
                        }
                        this.chatLoadConversations();
                    }
                } catch (e) {
                    console.error('Error parsing SSE data:', e);
                }
            };
            
            this.chatEventSource.onerror = () => {
                console.error('SSE connection error, falling back to polling');
                this.chatEventSource.close();
                this.chatEventSource = null;
                // Fallback to polling
                this.chatStartPollingFallback();
            };
        } catch (e) {
            console.error('SSE not supported, falling back to polling');
            this.chatStartPollingFallback();
        }
    },

    chatStartPollingFallback() {
        this.chatStopPolling();
        this.chatPollingInterval = setInterval(() => {
            if (this.currentChatRoom) {
                this.chatLoadMessages(this.currentChatRoom);
                this.chatLoadRooms();
            } else if (this.currentConversation) {
                this.chatLoadPrivateMessages(this.currentConversation);
                this.chatLoadConversations();
            }
        }, 5000); // Poll every 5 seconds as fallback
    },

    chatStopPolling() {
        if (this.chatEventSource) {
            this.chatEventSource.close();
            this.chatEventSource = null;
        }
        if (this.chatPollingInterval) {
            clearInterval(this.chatPollingInterval);
            this.chatPollingInterval = null;
        }
    },

    // ── Archiv-Funktionen ────────────────────────────────────────────────────

    async archiveSelected() {
        const selectedIds = Array.from(this.auswahlIds || []);
        if (selectedIds.length === 0) {
            this.toast('Bitte wählen Sie mindestens eine Akte aus', 'warning');
            return;
        }

        if (!await this.confirm('Ausgewählte Akten archivieren', `Wollen Sie ${selectedIds.length} Akte(n) wirklich ins Archiv verschieben?`, 'Ja, archivieren', 'btn-primary')) {
            return;
        }

        try {
            const data = await this.apiPost('/records/archive', {
                record_ids: selectedIds,
                archive_reason: null
            });

            if (data.success) {
                this.toast(`${data.archived_count} Akte(n) archiviert`, 'success');
                this.deaktiviereAuswahlmodus(true);
                this.loadRecords();
            } else {
                this.toast(data.error || 'Archivierung fehlgeschlagen', 'error');
            }
        } catch (e) {
            console.error('Fehler bei Archivierung:', e);
            this.toast('Fehler bei Archivierung', 'error');
        }
    },

    async archiveRestoreSelected() {
        const selectedIds = Array.from(this.archiveAuswahlIds || []);
        if (selectedIds.length === 0) {
            this.toast('Bitte wählen Sie mindestens eine Akte aus', 'warning');
            return;
        }

        if (!await this.confirm('Ausgewählte Akten wiederherstellen', `Wollen Sie ${selectedIds.length} Akte(n) wirklich aus dem Archiv wiederherstellen?`, 'Ja, wiederherstellen', 'btn-primary')) {
            return;
        }

        try {
            const data = await this.apiPost('/records/restore', {
                record_ids: selectedIds
            });

            if (data.success) {
                this.toast(`${data.restored_count} Akte(n) wiederhergestellt`, 'success');
                this.deaktiviereArchivAuswahlmodus(true);
                this.loadArchiveRecords();
            } else {
                this.toast(data.error || 'Wiederherstellung fehlgeschlagen', 'error');
            }
        } catch (e) {
            console.error('Fehler bei Wiederherstellung:', e);
            this.toast('Fehler bei Wiederherstellung', 'error');
        }
    },

    async archiveDeleteSelected() {
        const selectedIds = Array.from(this.archiveAuswahlIds || []);
        console.log('archiveDeleteSelected aufgerufen, IDs:', selectedIds);
        if (selectedIds.length === 0) {
            this.toast('Bitte wählen Sie mindestens eine Akte aus', 'warning');
            return;
        }

        if (!await this.confirm('Ausgewählte Akten löschen', `Wollen Sie ${selectedIds.length} Akte(n) wirklich endgültig löschen? Diese Aktion kann nicht rückgängig gemacht werden.`, 'Ja, löschen', 'btn-danger')) {
            return;
        }

        try {
            const data = await this.apiPost('/records/massen-loeschen', {
                ids: selectedIds
            });

            if (data.success) {
                this.toast(`${data.deleted_numbers.length} Akte(n) gelöscht`, 'success');
                this.deaktiviereArchivAuswahlmodus(true);
                this.loadArchiveRecords();
            } else {
                this.toast(data.error || 'Löschung fehlgeschlagen', 'error');
            }
        } catch (e) {
            console.error('Fehler bei Löschung:', e);
            this.toast('Fehler bei Löschung', 'error');
        }
    },

    async loadArchiveRecords(loadMore = false) {
        try {
            // Auswahl nur zurücksetzen, wenn nicht im Auswahlmodus
            if (!loadMore && !this.archiveAuswahlIstAktiv && typeof this.deaktiviereArchivAuswahlmodus === 'function') {
                this.deaktiviereArchivAuswahlmodus(true);
            }

            const searchEl = document.getElementById('archiveSearch');
            const search = searchEl ? searchEl.value : '';
            const filterEl = document.getElementById('archiveFilter');
            const filter = filterEl ? filterEl.value : 'all';
            const sortEl = document.getElementById('archiveSort');
            const sort = sortEl ? sortEl.value : 'updated_desc';
            const categoryEl = document.getElementById('archiveCategoryFilter');
            const category = categoryEl ? categoryEl.value : '';

            const params = new URLSearchParams({
                search,
                filter,
                search_type: 'all',
                limit: 50,
                offset: loadMore ? (this.archiveOffset || 0) : 0
            });

            if (category) params.append('category_id', category);

            const data = await this.apiGet(`/records/archived?${params}`);

            if (data.records) {
                this.renderArchiveRecords(data.records, loadMore);
                this.archiveOffset = (this.archiveOffset || 0) + data.records.length;

                const paginationEl = document.getElementById('archivePagination');
                if (paginationEl) {
                    const total = data.pagination?.total || 0;
                    const current = this.archiveOffset || 0;
                    paginationEl.classList.toggle('hidden', current >= total);
                }
            }
        } catch (e) {
            console.error('Fehler beim Laden archivierter Akten:', e);
            this.toast('Fehler beim Laden archivierter Akten', 'error');
        }
    },

    loadMoreArchiveRecords() {
        this.loadArchiveRecords(true);
    },

    clearArchiveSearch() {
        const searchEl = document.getElementById('archiveSearch');
        if (searchEl) {
            searchEl.value = '';
            this.archiveOffset = 0;
            this.loadArchiveRecords();
        }
    },

    toggleArchiveMobileFilters() {
        const content = document.getElementById('archiveMobileFilterContent');
        if (content) {
            content.classList.toggle('show');
        }
    },

    aktiviereArchivAuswahlmodus() {
        if (this.archiveAuswahlIstAktiv) return;
        this.archiveAuswahlIstAktiv = true;
        this.archiveAuswahlIds = new Set();

        document.getElementById('archiveAuswahlStartBtn').classList.add('hidden');
        document.getElementById('archiveAuswahlFertigBtn').classList.remove('hidden');
        document.getElementById('archiveAuswahlToolbar').classList.remove('hidden');
        document.getElementById('archiveSection').classList.add('auswahl-aktiv');

        // Dropdown-Event für Aktionen-Button hinzufügen
        const actionsBtn = document.getElementById('archiveAuswahlActionsBtn');
        const actionsDropdown = document.getElementById('archiveAuswahlActionsDropdown');
        if (actionsBtn && actionsDropdown && !actionsBtn.hasAttribute('data-dropdown-initialized')) {
            actionsBtn.setAttribute('data-dropdown-initialized', 'true');
            actionsBtn.addEventListener('click', (e) => {
                e.stopPropagation();
                actionsDropdown.classList.toggle('show');
            });
            document.addEventListener('click', () => {
                actionsDropdown.classList.remove('show');
            });
        }

        this.renderArchiveRecords();
    },

    deaktiviereArchivAuswahlmodus(clearSelection = false) {
        if (!this.archiveAuswahlIstAktiv && (!clearSelection || (this.archiveAuswahlIds || new Set()).size === 0)) return;

        this.archiveAuswahlIstAktiv = false;
        if (clearSelection) {
            this.archiveAuswahlIds = new Set();
        }

        document.getElementById('archiveAuswahlStartBtn').classList.remove('hidden');
        document.getElementById('archiveAuswahlFertigBtn').classList.add('hidden');
        document.getElementById('archiveAuswahlToolbar').classList.add('hidden');
        document.getElementById('archiveSection').classList.remove('auswahl-aktiv');

        this.renderArchiveRecords();
    },

    umschaltenAlleSichtbarenArchivAkten() {
        if (!this.archiveAuswahlIstAktiv) return;

        const visibleCards = document.querySelectorAll('#archiveList .record-card');
        const allSelected = visibleCards.length > 0 && Array.from(visibleCards).every(card => {
            const id = parseInt(card.dataset.recordId);
            return this.archiveAuswahlIds.has(id);
        });

        if (allSelected) {
            visibleCards.forEach(card => {
                const id = parseInt(card.dataset.recordId);
                this.archiveAuswahlIds.delete(id);
            });
        } else {
            visibleCards.forEach(card => {
                const id = parseInt(card.dataset.recordId);
                this.archiveAuswahlIds.add(id);
            });
        }

        this.updateArchiveAuswahlAnzahl();
        this.renderArchiveRecords();
    },

    updateArchiveAuswahlAnzahl() {
        const count = (this.archiveAuswahlIds || new Set()).size;
        document.getElementById('archiveAuswahlAnzahl').textContent = `${count} ausgewählt`;
    },

    renderArchiveRecords(records = null, append = false) {
        if (!records) {
            // Wenn keine records übergeben, aktuelle Liste verwenden
            records = this.currentArchiveRecords || [];
        }

        if (!append) {
            this.currentArchiveRecords = records;
            this.archiveOffset = records.length;
        } else {
            this.currentArchiveRecords = [...(this.currentArchiveRecords || []), ...records];
        }

        const container = document.getElementById('archiveList');
        if (!container) return;

        if (!append) {
            container.innerHTML = '';
        }

        records.forEach(record => {
            const card = this.createArchiveRecordCard(record);
            container.appendChild(card);
        });

        // Auswahl-Indikatoren aktualisieren
        if (this.archiveAuswahlIstAktiv) {
            container.querySelectorAll('.record-card').forEach(card => {
                const id = parseInt(card.dataset.recordId);
                const indicator = card.querySelector('.auswahl-indikator');
                if (indicator) {
                    indicator.classList.toggle('selected', this.archiveAuswahlIds.has(id));
                    indicator.setAttribute('aria-pressed', this.archiveAuswahlIds.has(id));
                }
            });
        }
    },

    createArchiveRecordCard(record) {
        const borderClass = record.border_color ? `border-${record.border_color.replace('border-', '')}` : '';
        const locked = record.locked ? '<i class="fas fa-lock lock-indicator"></i>' : '';
        const attachmentCount = record.attachments ? record.attachments.length : 0;

        // Status-Icon bestimmen
        let statusIcon = { icon: 'fas fa-info-circle', label: 'Neutral' };
        if (record.status === 'erledigt') {
            statusIcon = { icon: 'fas fa-check-circle', label: 'Erledigt' };
        } else if (record.status === 'bearbeitung') {
            statusIcon = { icon: 'fas fa-spinner fa-spin', label: 'In Bearbeitung' };
        } else if (record.status === 'offen') {
            statusIcon = { icon: 'fas fa-clock', label: 'Offen' };
        }

        const isSelected = this.archiveAuswahlIds && this.archiveAuswahlIds.has(record.id);

        const html = `
        <div class="record-card ${borderClass}" data-record-id="${record.id}" role="button" tabindex="0">
            <button class="auswahl-indikator ${this.archiveAuswahlIstAktiv ? '' : 'hidden'} ${isSelected ? 'selected' : ''}" type="button" aria-label="Akte auswählen" aria-pressed="${isSelected}">
                <i class="fas fa-check"></i>
            </button>
            ${locked}
            <div class="record-number">${record.number}</div>
            <div class="record-title">${this.escapeHtml(record.title)}</div>
            <div class="record-content">${this.escapeHtml(record.content || '').substring(0, 150)}</div>
            <div class="record-meta">
                <span class="record-status"><i class="${statusIcon.icon}"></i> ${statusIcon.label}</span>
                <span class="record-attachments"><i class="fas fa-paperclip"></i> ${attachmentCount}</span>
                <span class="record-date">${this.formatDate(record.updated_at)}</span>
            </div>
        </div>`;

        const tempDiv = document.createElement('div');
        tempDiv.innerHTML = html;
        const card = tempDiv.firstElementChild;

        // Klick-Event für Auswahl
        card.addEventListener('click', (e) => {
            if (this.archiveAuswahlIstAktiv) {
                e.preventDefault();
                const id = parseInt(record.id);
                console.log('Archiv-Auswahl geklickt:', id, 'aktuelle IDs:', Array.from(this.archiveAuswahlIds));
                if (this.archiveAuswahlIds.has(id)) {
                    this.archiveAuswahlIds.delete(id);
                } else {
                    this.archiveAuswahlIds.add(id);
                }
                this.updateArchiveAuswahlAnzahl();
                const indicator = card.querySelector('.auswahl-indikator');
                indicator.classList.toggle('selected', this.archiveAuswahlIds.has(id));
                indicator.setAttribute('aria-pressed', this.archiveAuswahlIds.has(id));
                console.log('Nach Auswahl:', Array.from(this.archiveAuswahlIds));
            } else {
                // Normaler Klick - Akte öffnen (TODO: Implementieren)
                this.toast('Archiv-Akten können nur angezeigt, aber nicht bearbeitet werden', 'info');
            }
        });

        return card;
    }
};

// Start
document.addEventListener('DOMContentLoaded', () => {
    App.init();
    
    // Service Worker für PWA registrieren
    if ('serviceWorker' in navigator) {
        window.addEventListener('load', () => {
            navigator.serviceWorker.register('./service-worker.js')
                .then(reg => console.log('PWA: Service Worker registriert'))
                .catch(err => console.log('PWA: Service Worker Fehler', err));
        });
    }
});
