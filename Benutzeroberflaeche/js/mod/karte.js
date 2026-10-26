/**
 * Karten-Modul (Web, Canvas-basiert, offline-freundlich)
 * - Holt Koordinaten über /api/karte/punkte
 * - Rendert Punkte + Referenzorte auf ein Canvas (keine externen Karten-Provider nötig)
 */
(() => {
    if (typeof App === 'undefined') return;

    App.kartePunkte = [];
    App.karteReferenzorte = {};
    App.karteAktiveIds = null; // null = alle, Array = Filter
    App._karteHitZonen = [];
    // sc = Pixel pro Grad (Längengrad). 
    // Wir nutzen einen stabilen Startwert für Deutschland.
    App.karteAnsicht = { fLat: 51.1657, fLon: 10.4515, sc: 40.0 }; 
    App._kartePointer = new Map(); // pointerId -> {x,y}
    App._karteDrag = null;         // {x,y,fLat,fLon}
    App._karteHatBewegt = false;   // verhindert "Klick" nach Drag (Mobile)
    App._karteLetzteBewegungTs = 0;
    App._karteRenderVersuche = 0;
    App._karteRenderGeplant = false;
    App._karteAktiverPointerId = null;
    App._karteMultiTouchBlockTs = 0;
    App.karteInteraktionAktiv = false;
    App.karteZielpunkt = null;     // {lat, lon} – für Zoom/Reset auf "unseren Punkt"
    App._karteStartAnsicht = null; // Startzustand wie "frisch geladen"
    App._karteAnsichtNachRender = false;
    App.karteDragAktiv = false;    // Verschieben per Wischgeste deaktiviert (User-Wunsch), Steuerung über Buttons
    App.karteLadeStatus = null;    // null | 'lade' – verhindert "weißen Bildschirm" bei Reload
    // Hinweis: Pinch-Zoom & Mausrad-Zoom wurden bewusst deaktiviert, da es
    // browserübergreifend (Mobile/PC) zu Sprüngen/Inkonsistenzen kam.
    // Zoom erfolgt zuverlässig über +/- Buttons.

    App._karteInteraktionBeenden = function() {
        // Defensive: Manche Mobile-Browser verlieren pointerup/touchend bei UI-Animationen.
        // Wir beenden die Interaktion hart, damit Zoom/Reset nicht "kaputt" bleibt.
        try { this._kartePointer?.clear?.(); } catch (_) {}
        this._karteDrag = null;
        this._karteAktiverPointerId = null;
        this.karteInteraktionAktiv = false;
    };

    App._karteRenderAnfordern = function() {
        if (this._karteRenderGeplant) return;
        this._karteRenderGeplant = true;
        requestAnimationFrame(() => {
            this._karteRenderGeplant = false;
            this.renderKarte();
        });
    };

    App.initKarte = function() {
        if (this._karteInit) return;
        this._karteInit = true;

        // Tooltip Element erstellen
        const tooltip = document.createElement('div');
        tooltip.id = 'karteTooltip';
        tooltip.style.position = 'fixed';
        tooltip.style.display = 'none';
        tooltip.style.backgroundColor = 'rgba(0, 0, 0, 0.85)';
        tooltip.style.color = '#fff';
        tooltip.style.padding = '6px 10px';
        tooltip.style.borderRadius = '6px';
        tooltip.style.fontSize = '12px';
        tooltip.style.pointerEvents = 'none';
        tooltip.style.zIndex = '10000';
        tooltip.style.boxShadow = '0 2px 8px rgba(0,0,0,0.3)';
        tooltip.style.transition = 'opacity 0.15s ease';
        tooltip.style.whiteSpace = 'nowrap';
        document.body.appendChild(tooltip);
        this._karteTooltipEl = tooltip;

        window.addEventListener('resize', () => {
            if (this._karteAktiv) {
                this._karteBerechneMinZoom();
                this.renderKarte();
            }
        });

        const zurueckBtn = document.getElementById('karteZurueckBtn');
        const zoomInBtn = document.getElementById('karteZoomInBtn');
        const zoomOutBtn = document.getElementById('karteZoomOutBtn');
        
        // Navigation Buttons
        const navUpBtn = document.getElementById('karteNavUpBtn');
        const navDownBtn = document.getElementById('karteNavDownBtn');
        const navLeftBtn = document.getElementById('karteNavLeftBtn');
        const navRightBtn = document.getElementById('karteNavRightBtn');

        // Zoom Buttons Logik
        const setupZoomBtn = (el, faktor) => {
            if (!el) return;
            const action = (e) => {
                try { if (e.cancelable) e.preventDefault(); } catch (_) {}
                this._karteInteraktionBeenden();
                this._karteZoomRelativ(faktor);
            };

            if ('PointerEvent' in window) {
                el.addEventListener('pointerdown', action);
            } else {
                el.addEventListener('touchstart', action, { passive: false });
            }
            // Zusätzlich click als Fallback für Desktop
            el.addEventListener('click', (e) => {
                if (Date.now() - (this._karteLetzteButtonAusloesung?.[el.id] || 0) < 150) return;
                action(e);
            });
        };

        setupZoomBtn(zoomInBtn, 1.25);
        setupZoomBtn(zoomOutBtn, 0.8);
        
        // Navigation Buttons mit flüssiger "Halten"-Funktion
        const navState = { dx: 0, dy: 0, timer: null };
        const loop = () => {
            if (navState.dx !== 0 || navState.dy !== 0) {
                // Beim Halten bewegen wir uns flüssig (multiplier massiv gedrosselt für präzise Steuerung)
                this._karteNavigiere(navState.dx * 0.1, navState.dy * 0.1);
                navState.timer = requestAnimationFrame(loop);
            } else {
                navState.timer = null;
            }
        };

        const setupNavBtn = (el, dx, dy) => {
            if (!el) return;
            
            const start = (e) => {
                try { 
                    if (e.cancelable) e.preventDefault(); 
                } catch (_) {}
                
                this._karteInteraktionBeenden();
                
                // Erster Schritt sofort
                this._karteNavigiere(dx, dy);
                
                // Dann flüssige Bewegung vorbereiten
                navState.dx = dx;
                navState.dy = dy;
                
                // Nur einen Loop starten, falls noch keiner läuft
                if (!navState.timer) {
                    navState.timer = requestAnimationFrame(loop);
                }
            };
            
            const stop = (e) => {
                // Nur stoppen, wenn die Richtung auch diesem Button entspricht
                // (verhindert Stoppen beim Loslassen eines anderen Buttons)
                if ((dx !== 0 && navState.dx === dx) || (dy !== 0 && navState.dy === dy)) {
                    navState.dx = 0;
                    navState.dy = 0;
                    if (navState.timer) {
                        cancelAnimationFrame(navState.timer);
                        navState.timer = null;
                    }
                }
            };

            // Pointer-Events sind moderner und decken Maus + Touch ab
            if ('PointerEvent' in window) {
                el.addEventListener('pointerdown', start);
                el.addEventListener('pointerup', stop);
                el.addEventListener('pointerleave', stop);
                el.addEventListener('pointercancel', stop);
            } else {
                // Fallback für sehr alte Geräte
                el.addEventListener('touchstart', start, { passive: false });
                el.addEventListener('touchend', stop);
                el.addEventListener('touchcancel', stop);
            }
        };

        setupNavBtn(navUpBtn, 0, 1);
        setupNavBtn(navDownBtn, 0, -1);
        setupNavBtn(navLeftBtn, -1, 0);
        setupNavBtn(navRightBtn, 1, 0);

        // Globaler Stop-Fallback: Wenn der Finger/Maus außerhalb losgelassen wird
        window.addEventListener('pointerup', () => {
            navState.dx = 0;
            navState.dy = 0;
            if (navState.timer) {
                cancelAnimationFrame(navState.timer);
                navState.timer = null;
            }
        });
        window.addEventListener('touchend', () => {
            navState.dx = 0;
            navState.dy = 0;
            if (navState.timer) {
                cancelAnimationFrame(navState.timer);
                navState.timer = null;
            }
        });

        // Keyboard Pfeiltasten support mit flüssiger Bewegung
        document.addEventListener('keydown', (e) => {
            if (!document.body.classList.contains('karte-aktiv')) return;
            let moved = false;
            if (e.key === 'ArrowUp') { navState.dy = 1; moved = true; }
            if (e.key === 'ArrowDown') { navState.dy = -1; moved = true; }
            if (e.key === 'ArrowLeft') { navState.dx = -1; moved = true; }
            if (e.key === 'ArrowRight') { navState.dx = 1; moved = true; }
            
            if (moved) {
                e.preventDefault();
                if (!navState.timer) loop();
            }

            if (e.key === '+' || e.key === '=') { e.preventDefault(); this._karteZoomRelativ(1.1); }
            if (e.key === '-') { e.preventDefault(); this._karteZoomRelativ(0.9); }
        });

        document.addEventListener('keyup', (e) => {
            if (['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight'].includes(e.key)) {
                navState.dx = 0;
                navState.dy = 0;
                cancelAnimationFrame(navState.timer);
                navState.timer = null;
            }
        });

        // Mobile: sofort reagieren (click kann je nach Browser "verschluckt" werden).
        const schnelleTaste = (el, key, fn) => {
            if (!el) return;
            // Nav-Buttons und Zoom-Buttons haben eigene Logik
            if (el.id && (el.id.includes('Nav') || el.id.includes('Zoom'))) return; 
            
            if ('PointerEvent' in window) {
                el.addEventListener('pointerdown', (e) => {
                    try { e.preventDefault(); } catch (_) {}
                    this._karteInteraktionBeenden();
                    this._karteLetzteButtonAusloesung = this._karteLetzteButtonAusloesung || {};
                    this._karteLetzteButtonAusloesung[key] = Date.now();
                    fn();
                }, { passive: false });
            } else {
                el.addEventListener('touchstart', (e) => {
                    try { e.preventDefault(); } catch (_) {}
                    this._karteInteraktionBeenden();
                    this._karteLetzteButtonAusloesung = this._karteLetzteButtonAusloesung || {};
                    this._karteLetzteButtonAusloesung[key] = Date.now();
                    fn();
                }, { passive: false });
            }
        };
        schnelleTaste(zurueckBtn, 'zurueck', () => this.showSection('records'));
        
        // Navigation und Zoom erfolgen AUSSCHLIESSLICH über ihre eigenen setup-Funktionen!
        // (Doppelte Listener führen auf Mobile zu Endlosschleifen/Weglaufen der Karte)

        const canvas = document.getElementById('karteCanvas');
        if (canvas) {
            canvas.addEventListener('click', (e) => this._karteKlick(e));
            // Drag aktiv (Pinch/Mehrfinger wird weiterhin geblockt).
            if (this.karteDragAktiv) {
                if ('PointerEvent' in window) {
                    canvas.addEventListener('pointerdown', (e) => this._kartePointerDown(e), { passive: false });
                    canvas.addEventListener('pointermove', (e) => this._kartePointerMove(e), { passive: false });
                    canvas.addEventListener('pointerup', (e) => this._kartePointerUp(e), { passive: false });
                    canvas.addEventListener('pointercancel', (e) => this._kartePointerUp(e), { passive: false });
                    canvas.addEventListener('lostpointercapture', (e) => this._kartePointerUp(e), { passive: false });
                    canvas.addEventListener('pointerleave', (e) => this._kartePointerUp(e), { passive: false });
                } else {
                    canvas.addEventListener('touchstart', (ev) => this._karteTouchStart(ev), { passive: false });
                    canvas.addEventListener('touchmove', (ev) => this._karteTouchMove(ev), { passive: false });
                    canvas.addEventListener('touchend', (ev) => this._karteTouchEnd(ev), { passive: false });
                    canvas.addEventListener('touchcancel', (ev) => this._karteTouchEnd(ev), { passive: false });
                }
            }
            window.addEventListener('resize', () => this.renderKarte());

            // iOS/Safari: Browser-Gesten (Pinch-Zoom) zuverlässig unterbinden.
            const gestenStoppen = (ev) => { try { ev.preventDefault(); } catch (_) {} };
            document.addEventListener('gesturestart', gestenStoppen, { passive: false });
            document.addEventListener('gesturechange', gestenStoppen, { passive: false });
            document.addEventListener('gestureend', gestenStoppen, { passive: false });

            // Global: Pinch/Mehrfinger in Kartenansicht blocken (User-Wunsch: nur Buttons nutzen)
            const multiTouchStoppen = (ev) => {
                if (!document.body?.classList?.contains('karte-aktiv')) return;
                if (!ev.touches || ev.touches.length <= 1) return;
                const ziel = ev.target;
                if (ziel && (ziel.id === 'karteCanvas' || ziel.closest?.('#karteSection'))) {
                    try { ev.preventDefault(); } catch (_) {}
                    this._karteMultiTouchBlockTs = Date.now();
                }
            };

            // Hover-Effekt (Tooltip)
            canvas.addEventListener('pointermove', (e) => {
                if (!document.body.classList.contains('karte-aktiv')) {
                    if (this._karteTooltipEl) this._karteTooltipEl.style.display = 'none';
                    return;
                }

                if (this.karteInteraktionAktiv) {
                    if (this._karteTooltipEl) this._karteTooltipEl.style.display = 'none';
                    return;
                }
                
                const rect = canvas.getBoundingClientRect();
                const x = e.clientX - rect.left;
                const y = e.clientY - rect.top;

                let best = null;
                let bestD2 = Infinity;
                for (const h of this._karteHitZonen) {
                    const dx = x - h.x;
                    const dy = y - h.y;
                    const d2 = dx * dx + dy * dy;
                    if (d2 <= h.r * h.r && d2 < bestD2) {
                        best = h;
                        bestD2 = d2;
                    }
                }

                if (best?.recordId) {
                    const p = (this.kartePunkte || []).find(it => it.id === best.recordId);
                    if (p && this._karteTooltipEl) {
                        this._karteTooltipEl.textContent = p.title || `Akte #${p.number}`;
                        this._karteTooltipEl.style.display = 'block';
                        this._karteTooltipEl.style.left = (e.clientX + 15) + 'px';
                        this._karteTooltipEl.style.top = (e.clientY - 15) + 'px';
                        canvas.style.cursor = 'pointer';
                        return;
                    }
                }
                
                if (this._karteTooltipEl) this._karteTooltipEl.style.display = 'none';
                canvas.style.cursor = 'default';
            });

            canvas.addEventListener('pointerleave', () => {
                if (this._karteTooltipEl) this._karteTooltipEl.style.display = 'none';
            });
            document.addEventListener('touchstart', multiTouchStoppen, { passive: false });
            document.addEventListener('touchmove', multiTouchStoppen, { passive: false });
        }
    };

    App.loadKarte = async function(ids = null, showLoadingOverlay = false) {
        this.karteAktiveIds = ids && ids.length ? ids : null;
        this._karteStartAnsicht = null;
        this._karteAnsichtNachRender = true;
        this._karteReset();

        // Wenn manueller Offline-Modus aktiv ist, nicht versuchen, Daten zu laden
        if (this.manualOfflineMode) {
            console.log('📡 Karte: Manueller Offline-Modus aktiv - Daten werden nicht neu geladen');
            this.karteLadeStatus = null;
            // Karte mit vorhandenen Daten rendern (falls vorhanden)
            if (this.kartePunkte && this.kartePunkte.length > 0) {
                this._karteSetzeZielpunktAuto();
                this._karteBerechneDatenBounds();
                this.renderKarte();
            }
            return;
        }

        try {
            this.karteLadeStatus = 'lade';
            this._karteDatenBounds = null;
            const data = await this.apiPost('/karte/punkte', { ids: this.karteAktiveIds, limit: 5000, offset: 0 }, showLoadingOverlay);
            this.kartePunkte = data.punkte || [];
            this.karteReferenzorte = data.referenzorte || {};
            this.karteLadeStatus = null;
            this._karteLastDataTs = Date.now(); // Zeitstempel für Cache-Validierung

            // Zielpunkt automatisch wählen:
            this._karteSetzeZielpunktAuto();
            this._karteBerechneDatenBounds();

            // Wenn eine Auswahl aktiv ist, automatisch auf die Auswahl fokussieren
            if (this.karteAktiveIds && this.karteAktiveIds.length > 0) {
                this._karteFokusAufAuswahl();
            }

            this.renderKarte();
        } catch (e) {
            this.karteLadeStatus = null;
            this.toast(e.message, 'error');
        }
    };

    App._karteAuswahlPunkte = function() {
        const punkte = (this.kartePunkte || []).filter(p => p && typeof p.lat === 'number' && typeof p.lon === 'number');

        // "Markierte Punkte" robust bestimmen:
        // 1) expliziter Karten-Filter (karteAktiveIds)
        // 2) sonst: Mehrfachauswahl aus der Aktenliste (auswahlIds), falls vorhanden
        // 3) sonst: alle Punkte
        const ids = this._karteAktiveAuswahlIds?.();
        if (Array.isArray(ids) && ids.length) {
            const set = new Set(ids);
            return punkte.filter(p => set.has(p.id));
        }
        return punkte;
    };

    App._karteAktiveAuswahlIds = function() {
        if (Array.isArray(this.karteAktiveIds) && this.karteAktiveIds.length) return this.karteAktiveIds;
        if (this.auswahlIds && this.auswahlIds.size) {
            return Array.from(this.auswahlIds).filter(Number.isFinite).slice(0, 5000);
        }
        return null;
    };

    App._karteBerechneDatenBounds = function() {
        const punkte = this.kartePunkte || [];
        const ref = this.karteReferenzorte || {};
        
        let latMin = Infinity, latMax = -Infinity, lonMin = Infinity, lonMax = -Infinity;
        let hat = false;

        // Aktenpunkte
        for (const p of punkte) {
            if (!p || typeof p.lat !== 'number' || typeof p.lon !== 'number') continue;
            hat = true;
            latMin = Math.min(latMin, p.lat);
            latMax = Math.max(latMax, p.lat);
            lonMin = Math.min(lonMin, p.lon);
            lonMax = Math.max(lonMax, p.lon);
        }
        
        // Referenzorte (nur die Sichtbaren/Wichtigen einbeziehen)
        for (const name in ref) {
            const o = ref[name];
            if (!o || typeof o.lat !== 'number' || typeof o.lon !== 'number') continue;
            // Nur Level 0-2 (Städte/Regionen) für die Begrenzung nutzen, 
            // damit die Karte nicht unnötig groß wird durch kleine Dörfer am Rand.
            if (o.level > 2) continue; 
            
            hat = true;
            latMin = Math.min(latMin, o.lat);
            latMax = Math.max(latMax, o.lat);
            lonMin = Math.min(lonMin, o.lon);
            lonMax = Math.max(lonMax, o.lon);
        }

        if (!hat) {
            this._karteDatenBounds = null;
            return;
        }

        // Minimale Ausdehnung erzwingen (ca. 1km)
        if (Math.abs(latMax - latMin) < 0.01) { latMax += 0.005; latMin -= 0.005; }
        if (Math.abs(lonMax - lonMin) < 0.01) { lonMax += 0.005; lonMin -= 0.005; }

        this._karteDatenBounds = { latMin, latMax, lonMin, lonMax };
    };

    App._karteFarbeAusRahmenklasse = function(borderClass) {
        // Standard: Grau (für Akten ohne Rahmenfarbe)
        const standard = '#6c757d';
        
        // Null, undefined oder kein String -> Grau
        if (!borderClass || typeof borderClass !== 'string') return standard;
        
        const bc = borderClass.trim();
        
        // Leerer String nach Trim -> Grau
        if (!bc || bc === '' || bc === 'null' || bc === 'undefined') return standard;
        
        // Nur explizit erlaubte CSS-Klassen zulassen
        const map = {
            'border-red': '#dc3545',
            'border-blue': '#007bff', 
            'border-yellow': '#ffc107',
            'border-green': '#28a745',
            'border-magenta': '#ff00ff',
            'border-gray': '#6c757d',
            'border-grey': '#6c757d',
        };
        
        // Nur wenn im Mapping gefunden -> entsprechende Farbe, sonst Grau
        // Hex-Werte NICHT mehr direkt zulassen, um Probleme zu vermeiden
        return map[bc] || standard;
    };

    App._karteVerteileUeberlappungen = function(punkte, xyFn, cssW, cssH) {
        // Spiderfy-Logik: Punkte die zu nah beieinander liegen, werden im Kreis verteilt.
        const abstand = 16;
        const zellenGroesse = 22;

        const clusters = [];
        const bucket = new Map();

        const bucketKey = (ix, iy) => `${ix},${iy}`;
        const findeCluster = (x, y, ix, iy) => {
            for (let dx = -1; dx <= 1; dx++) {
                for (let dy = -1; dy <= 1; dy++) {
                    const arr = bucket.get(bucketKey(ix + dx, iy + dy));
                    if (!arr) continue;
                    for (const ci of arr) {
                        const c = clusters[ci];
                        const ddx = x - c.cx;
                        const ddy = y - c.cy;
                        if ((ddx * ddx + ddy * ddy) <= (abstand * abstand)) return ci;
                    }
                }
            }
            return -1;
        };

        for (const p of punkte) {
            const pos = xyFn(p.lat, p.lon);
            if (!pos || !isFinite(pos.x) || !isFinite(pos.y)) continue;
            const x = pos.x;
            const y = pos.y;
            const ix = Math.floor(x / zellenGroesse);
            const iy = Math.floor(y / zellenGroesse);

            const ci = findeCluster(x, y, ix, iy);
            if (ci >= 0) {
                const c = clusters[ci];
                c.pts.push({ p, x, y });
                const n = c.pts.length;
                c.cx = c.cx + (x - c.cx) / n;
                c.cy = c.cy + (y - c.cy) / n;
            } else {
                const idx = clusters.length;
                clusters.push({ cx: x, cy: y, pts: [{ p, x, y }] });
                const k = bucketKey(ix, iy);
                const arr = bucket.get(k);
                if (arr) arr.push(idx); else bucket.set(k, [idx]);
            }
        }

        const out = [];
        const a = this.karteAnsicht;
        const rad = a.fLat * (Math.PI / 180);
        const lonFaktor = Math.cos(rad);

        for (const c of clusters) {
            const n = c.pts.length;
            if (n <= 1) {
                out.push({ p: c.pts[0].p });
                continue;
            }

            c.pts.sort((a, b) => (a.p?.id ?? 0) - (b.p?.id ?? 0));
            const radius = Math.min(12, 7 + (n - 2) * 1.0);
            const step = (Math.PI * 2) / n;

            for (let i = 0; i < n; i++) {
                const it = c.pts[i];
                const ang = i * step;
                // Offset in Pixeln
                const offX = Math.cos(ang) * radius;
                const offY = Math.sin(ang) * radius;
                
                // Offset in Geo-Koordinaten umrechnen, damit es beim Panning stabil bleibt
                const dLon = offX / (a.sc * lonFaktor);
                const dLat = -offY / a.sc;

                out.push({ 
                    p: { 
                        ...it.p, 
                        lat: it.p.lat + dLat, 
                        lon: it.p.lon + dLon 
                    } 
                });
            }
        }
        return out;
    };

    App._karteSetzeAnsichtFuerAuswahl = function() {
        const canvas = document.getElementById('karteCanvas');
        const w = canvas?.clientWidth || 800;
        const h = canvas?.clientHeight || 500;

        const pts = this._karteAuswahlPunkte();
        if (!pts.length) return;

        // Ein Punkt: reinzoomen + zentrieren
        if (pts.length === 1) {
            this.karteZielpunkt = { lat: pts[0].lat, lon: pts[0].lon };
            this.karteAnsicht.fLat = pts[0].lat;
            this.karteAnsicht.fLon = pts[0].lon;
            this.karteAnsicht.sc = 3000.0;
            return;
        }

        // Bounding Box der Punkte berechnen
        let latMin = Infinity, latMax = -Infinity, lonMin = Infinity, lonMax = -Infinity;
        for (const p of pts) {
            latMin = Math.min(latMin, p.lat);
            latMax = Math.max(latMax, p.lat);
            lonMin = Math.min(lonMin, p.lon);
            lonMax = Math.max(lonMax, p.lon);
        }

        // Mitte der Bounding Box
        const centerLat = (latMin + latMax) / 2;
        const centerLon = (lonMin + lonMax) / 2;

        this.karteZielpunkt = { lat: centerLat, lon: centerLon };
        this.karteAnsicht.fLat = centerLat;
        this.karteAnsicht.fLon = centerLon;

        const latSpan = latMax - latMin;
        const lonSpan = lonMax - lonMin;

        // Wenn alle Punkte am gleichen Ort sind
        if (latSpan < 0.0001 && lonSpan < 0.0001) {
            this.karteAnsicht.sc = 3000.0;
            return;
        }

        // Binäre Suche nach dem optimalen Zoom
        const padding = 80; // Padding (80px) für mehr Abstand zum Kartenrand
        const rad = centerLat * (Math.PI / 180);
        const lonFaktor = Math.max(0.1, Math.cos(rad));

        // Hilfsfunktion: Prüft ob alle Punkte mit gegebenem Zoom sichtbar sind
        const areAllVisible = (sc) => {
            for (const p of pts) {
                const x = w / 2 + (p.lon - centerLon) * sc * lonFaktor;
                const y = h / 2 - (p.lat - centerLat) * sc;
                if (x < padding || x > w - padding || y < padding || y > h - padding) {
                    return false;
                }
            }
            return true;
        };

        // Binäre Suche: Finde den maximalen Zoom bei dem alle Punkte noch sichtbar sind
        let minSc = 10;
        let maxSc = 500000;
        let optimalSc = minSc;

        // Zuerst prüfen ob überhaupt ein Zoom existiert bei dem alle sichtbar sind
        if (!areAllVisible(minSc)) {
            // Selbst bei minimalem Zoom nicht alle sichtbar -> minimales Zoom verwenden
            this.karteAnsicht.sc = minSc;
            return;
        }

        // Binäre Suche
        for (let i = 0; i < 40; i++) {
            const midSc = (minSc + maxSc) / 2;
            if (areAllVisible(midSc)) {
                optimalSc = midSc;
                minSc = midSc; // Versuche höheren Zoom
            } else {
                maxSc = midSc; // Zu hoch, reduziere
            }
        }

        // Keine Sicherheitsmarge - wirklich bis zur Grenze zoomen
        this.karteAnsicht.sc = optimalSc;
    };

    App._karteSetzeZielpunktAuto = function() {
        const punkte = this.kartePunkte || [];
        if (!punkte.length) { this.karteZielpunkt = null; return; }

        // Falls genau eine ID aktiv ist, diesen Punkt nehmen (sofern vorhanden)
        if (Array.isArray(this.karteAktiveIds) && this.karteAktiveIds.length === 1) {
            const id = this.karteAktiveIds[0];
            const p = punkte.find(x => x && x.id === id);
            if (p && typeof p.lat === 'number' && typeof p.lon === 'number') {
                this.karteZielpunkt = { lat: p.lat, lon: p.lon };
                return;
            }
        }

        // Schwerpunkt berechnen (robust + performant)
        let sLat = 0, sLon = 0, n = 0;
        for (const p of punkte) {
            if (!p || typeof p.lat !== 'number' || typeof p.lon !== 'number') continue;
            sLat += p.lat; sLon += p.lon; n++;
        }
        if (!n) { this.karteZielpunkt = null; return; }
        this.karteZielpunkt = { lat: sLat / n, lon: sLon / n };
    };

    App._karteReset = function() {
        this._karteInteraktionBeenden();
        this._karteHatBewegt = false;
        this._karteLetzteBewegungTs = 0;

        // "Frisch geladen" exakt wiederherstellen, wenn wir ihn schon kennen
        if (this._karteStartAnsicht) {
            this.karteAnsicht = { ...this._karteStartAnsicht };
        } else {
            this.karteAnsicht = { fLat: 51.1657, fLon: 10.4515, sc: 40.0 };
            this._karteSetzeAnsichtFuerAuswahl();
            this._karteAnsichtNachRender = true;
        }

        this._karteRenderAnfordern();
    };

    App._karteClamp = function(v, min, max) {
        return Math.min(max, Math.max(min, v));
    };

    App._kartePixelZuGeo = function(clientX, clientY) {
        const canvas = document.getElementById('karteCanvas');
        if (!canvas) return null;
        const rect = canvas.getBoundingClientRect();
        const x = clientX - rect.left;
        const y = clientY - rect.top;

        const a = this.karteAnsicht;
        const cssW = canvas.clientWidth || 800;
        const cssH = canvas.clientHeight || 500;
        const cx = cssW / 2;
        const cy = cssH / 2;

        const rad = a.fLat * (Math.PI / 180);
        const lonFaktor = Math.cos(rad);

        const lon = a.fLon + (x - cx) / (a.sc * lonFaktor);
        const lat = a.fLat - (y - cy) / a.sc;
        return { lat, lon };
    };

    App._karteBegrenzeAnsichtNurSicherheit = function() {
        // Nur harte Sicherheitsgrenzen (verhindert extreme Werte)
        const a = this.karteAnsicht || { fLat: 51.1657, fLon: 10.4515, sc: 40 };
        // sc = Pixel pro Grad. 5 = ganz Europa, 500000 = extremster Zoom
        a.sc = Math.max(2, Math.min(1000000, a.sc));
        
        // Lat/Lon Grenzen (Weltweit)
        a.fLat = this._karteClamp(a.fLat, -85, 85);
        a.fLon = this._karteClamp(a.fLon, -180, 180);
    };

    App._karteFokusAufAuswahl = function() {
        // Button unter dem Minus: Immer die aktuell ausgewählten roten Punkte in den Fokus setzen:
        // - 1 Punkt: exakt mittig + sinnvoller Zoom
        // - mehrere Punkte: Mittelpunkt mittig + Zoom so, dass alle sichtbar bleiben
        this._karteInteraktionBeenden();

        // Wenn wir keine Projektion haben, kann das Fitten noch nicht berechnet werden.
        // Dann beim nächsten Render nachholen.
        if (this._karteProjekt) {
            this._karteSetzeAnsichtFuerAuswahl();
            // Diese Ansicht gilt als "sinnvoller Ausgang" für weitere Bedienung
            this._karteStartAnsicht = { ...this.karteAnsicht };
        } else {
            // Projektion kommt erst beim nächsten Render – dann nachziehen
            this._karteAnsichtNachRender = true;
        }

        this._karteRenderAnfordern();
    };

    App._karteNeuLadenUndFokus = async function() {
        // Gewünscht: "wirklich neu laden" und danach die Punkte wieder sauber in den Fokus bringen.
        // -> Daten erneut vom Server holen (auch falls sich Koordinaten inzwischen geändert haben)
        // -> danach Fit/Zentrierung auf Auswahl
        if (this._karteNeuLadenLaeuft) return; // Mehrfachklick-Schutz (verhindert White-Screen durch Rennen)
        this._karteNeuLadenLaeuft = true;
        try {
            // IDs robust bestimmen (Mobile: Navigation/Selection kann kurz "null" sein)
            let ids = this._karteAktiveAuswahlIds?.();
            // Vorab: Interaktion hart beenden, damit Pointer-States nicht reinfunken
            this._karteInteraktionBeenden();

            // Optionales Feedback (nur Mobile, damit Desktop nicht nervt)
            let istMobile = false;
            try { istMobile = !!(window.matchMedia && window.matchMedia('(max-width: 899px)').matches); } catch (_) {}
            if (istMobile) this.toast('Karte wird neu geladen...', 'info');

            // Backup, damit bei Fehlern die Karte nicht "leer" bleibt
            const altPunkte = this.kartePunkte;
            const altRef = this.karteReferenzorte;
            const altAnsicht = this.karteAnsicht;

            // Ziel: wie "erstes Öffnen" – aber ohne globales Loading-Overlay
            this.karteAktiveIds = ids && ids.length ? ids : null;
            this.karteLadeStatus = 'lade';
            this.kartePunkte = [];
            this.karteReferenzorte = {};
            try { this.renderKarte(); } catch (_) {}

            const controller = ('AbortController' in window) ? new AbortController() : null;
            const timeout = setTimeout(() => { try { controller?.abort?.(); } catch (_) {} }, 15000);
            try {
                const res = await fetch('/api/karte/punkte', {
                    method: 'POST',
                    credentials: 'same-origin',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ ids: this.karteAktiveIds, limit: 5000, offset: 0 }),
                    signal: controller ? controller.signal : undefined
                });

                const ct = res.headers.get('content-type') || '';
                const data = ct.includes('application/json') ? await res.json() : null;
                if (!res.ok) throw new Error((data && data.error) ? data.error : `Fehler ${res.status}`);

                // Daten übernehmen (erst NACH erfolgreichem Load -> verhindert "weiß" bei Fehlern)
                this.kartePunkte = data?.punkte || [];
                this.karteReferenzorte = data?.referenzorte || {};
                this.karteLadeStatus = null;
                this._karteLastDataTs = Date.now();
            } finally {
                clearTimeout(timeout);
            }

            // Wie "zum ersten Mal": Projektions-/Startzustand verwerfen und sauber neu aufziehen
            this._karteProjekt = null;
            this._karteStartAnsicht = null;
            this._karteAnsichtNachRender = true;
            this.karteAnsicht = { fLat: 51.1657, fLon: 10.4515, sc: 1.0 };
            this._karteSetzeZielpunktAuto();
            this._karteBerechneDatenBounds();
            this._karteBerechneMinZoom();

            // Globales Loading-Overlay vorsichtshalber weg, falls es doch irgendwo "hängen" blieb
            try { document.getElementById('loadingOverlay')?.classList?.remove?.('show'); } catch (_) {}

            // Render + Fokus (mehrfach nachziehen wegen Mobile-Layout)
            try { this.renderKarte(); } catch (_) {}
            requestAnimationFrame(() => {
                requestAnimationFrame(() => {
                    try { this._karteFokusAufAuswahl(); } catch (_) {}
                });
            });
            setTimeout(() => { try { this._karteFokusAufAuswahl(); } catch (_) {} }, 180);

            if (istMobile) this.toast('Karte neu geladen', 'success');
        } catch (e) {
            // Wenn Reload scheitert: alte Karte wiederherstellen (kein "leerer/weißer" Zustand)
            try {
                this.karteLadeStatus = null;
                if (typeof altPunkte !== 'undefined') this.kartePunkte = altPunkte;
                if (typeof altRef !== 'undefined') this.karteReferenzorte = altRef;
                if (typeof altAnsicht !== 'undefined') this.karteAnsicht = altAnsicht;
                this._karteRenderAnfordern();
            } catch (_) {}
            try { console.error('Karte-Neuladen fehlgeschlagen:', e); } catch (_) {}
            try { this.toast(e?.message || 'Neuladen fehlgeschlagen', 'error'); } catch (_) {}
        } finally {
            this._karteNeuLadenLaeuft = false;
        }
    };

    App._karteBegrenzeAnsicht = function() {
        // Harte Grenzen: Wir verhindern, dass der Bildschirmrand extrem weit weg driftet.
        // Wir entspannen die Grenzen jedoch massiv, um "Snap-Back" Effekte beim Navigieren zu vermeiden.
        const a = this.karteAnsicht || { fLat: 51.1657, fLon: 10.4515, sc: 40 };
        
        // 1. Zoom-Untergrenze (Sicherheit, damit man nicht unendlich weit rauszoomt)
        // Wir erlauben einen sehr weiten Zoom (sc=2), was ganz Europa/Welt abdeckt.
        a.sc = Math.max(2, Math.min(1000000, a.sc));

        // 2. Positions-Grenzen (Weltweit)
        // Wir erlauben dem Nutzer, sich frei zu bewegen, begrenzen aber auf reale Koordinaten.
        a.fLat = this._karteClamp(a.fLat, -85, 85);
        a.fLon = this._karteClamp(a.fLon, -180, 180);

        // Die aggressive Begrenzung auf Daten-Bounds entfernen wir hier, 
        // da sie auf Mobile oft zu unerwünschten Sprüngen führt, wenn man am Rand navigiert.
    };

    App._karteBerechneMinZoom = function() {
        // Deaktiviert: Der Nutzer soll frei zoomen können, ohne dass die Karte "kämpft".
        this._karteMinSc = 2;
    };

    App._karteNormierePunkt = function(px, py) {
        const canvas = document.getElementById('karteCanvas');
        if (!canvas) return { px, py, w: 800, h: 500 };
        const w = canvas.clientWidth || 800;
        const h = canvas.clientHeight || 500;
        return {
            px: this._karteClamp(px, 0, w),
            py: this._karteClamp(py, 0, h),
            w,
            h
        };
    };

    App._karteNavigiere = function(dx, dy) {
        const a = this.karteAnsicht;
        const rad = a.fLat * (Math.PI / 180);
        const lonFaktor = Math.cos(rad);

        // Schrittweite abhängig vom aktuellen Zoom (sc)
        // Wir bewegen uns um ca. 2.5% des aktuellen Bildschirmausschnitts pro Klick
        const canvas = document.getElementById('karteCanvas');
        const w = canvas ? (canvas.clientWidth || 800) : 800;
        const h = canvas ? (canvas.clientHeight || 500) : 500;
        
        const schrittLat = (h * 0.025) / a.sc;
        const schrittLon = (w * 0.025) / (a.sc * lonFaktor);

        a.fLat += dy * schrittLat;
        a.fLon += dx * schrittLon;

        this._karteBegrenzeAnsicht();
        this._karteRenderAnfordern();
    };

    App._karteZoomRelativ = function(faktor) {
        const a = this.karteAnsicht || { fLat: 51.1657, fLon: 10.4515, sc: 1.0 };
        
        // Immer in die Mitte der Karte zoomen (Viewport-Mitte)
        // Die aktuelle Ansicht (fLat, fLon) ist bereits der Mittelpunkt der Karte
        // Wir ändern nur den Zoom-Faktor (sc), ohne die Position zu ändern
        
        a.sc = a.sc * faktor;
        
        this._karteBegrenzeAnsicht();
        this._karteRenderAnfordern();
    };

    App._karteBasisAusGeo = function(lat, lon) {
        const prj = this._karteProjekt;
        if (!prj) return null;
        // Wichtig: Auf Mobile/PC absolut identische Koordinaten-Basis
        const x = prj.innenX + ((lon - prj.lonMin) * prj.skala);
        const y = prj.innenY + ((prj.latMax - lat) * prj.skala);
        return { x, y };
    };

    App._karteZentriereAufZielpunkt = function(scNeu = null) {
        if (!this.karteZielpunkt) return;
        const a = this.karteAnsicht || { fLat: 51.1657, fLon: 10.4515, sc: 1.0 };
        a.fLat = this.karteZielpunkt.lat;
        a.fLon = this.karteZielpunkt.lon;
        if (scNeu !== null) a.sc = scNeu;
        this._karteBegrenzeAnsichtNurSicherheit();
        this._karteRenderAnfordern();
    };

    /**
     * Initialisiert die Karte mit Fokus auf alle geladenen Punkte
     * Sorgt dafür, dass alle Punkte exakt ins Sichtfeld passen.
     */
    App._karteInitialerFokus = function() {
        const punkte = this.kartePunkte || [];
        if (punkte.length === 0) return;
        
        // 1. Bounds der aktuellen Auswahl berechnen
        let latMin = 100, latMax = -100, lonMin = 100, lonMax = -100;
        for (const p of punkte) {
            latMin = Math.min(latMin, p.lat);
            latMax = Math.max(latMax, p.lat);
            lonMin = Math.min(lonMin, p.lon);
            lonMax = Math.max(lonMax, p.lon);
        }

        // 2. Fokuspunkt (Mitte) setzen
        this.karteZielpunkt = {
            lat: (latMin + latMax) / 2,
            lon: (lonMin + lonMax) / 2
        };
        
        // 3. Zoomstufe berechnen
        if (this._karteProjekt) {
            const w = this._karteProjekt.cssW;
            const h = this._karteProjekt.cssH;
            
            // Puffer (Padding) einplanen
            const padding = Math.min(w, h) * 0.25; 
            const latSpan = Math.max(0.005, latMax - latMin);
            const lonSpan = Math.max(0.005, lonMax - lonMin);
            
            const verfügbareW = Math.max(50, w - padding);
            const verfügbareH = Math.max(50, h - padding);
            
            const pxProGradLon = verfügbareW / lonSpan;
            const pxProGradLat = verfügbareH / latSpan;
            
            const zielSkala = Math.min(pxProGradLon, pxProGradLat);
            const sc = zielSkala / this._karteProjekt.skala;
            
            // Zentrieren mit berechnetem Zoom
            this._karteZentriereAufZielpunkt(Math.max(0.4, Math.min(10, sc)));
            
            // Auf Mobile: Nochmaliges Rendern erzwingen, um sicher zu gehen
            this._karteRenderAnfordern();
        } else {
            this._karteZentriereAufZielpunkt(1.0);
        }
    };

    App._karteZoomUndZentriere = function(px, py, faktor) {
        // Veraltet: Zoom erfolgt jetzt stabil über _karteZoomRelativ auf den Zielpunkt
        this._karteZoomRelativ(faktor);
    };

    App._karteZoomZuPunkt = function(faktor, px, py) {
        // Veraltet: Zoom erfolgt jetzt stabil über _karteZoomRelativ auf den Zielpunkt
        this._karteZoomRelativ(faktor);
    };

    App._kartePointerDown = function(e) {
        try { e.preventDefault(); } catch (_) {}
        const canvas = e.currentTarget;
        canvas.setPointerCapture?.(e.pointerId);
        
        this._karteHatBewegt = false;
        this.karteInteraktionAktiv = true;

        if (this._kartePointer.size === 0) {
            this._karteDrag = { x: e.clientX, y: e.clientY };
            this._karteAktiverPointerId = e.pointerId;
        }
        this._kartePointer.set(e.pointerId, { x: e.clientX, y: e.clientY });
    };

    App._kartePointerMove = function(e) {
        if (!this._kartePointer.has(e.pointerId)) return;
        try { e.preventDefault(); } catch (_) {}
        
        if (this._karteDrag && this._karteAktiverPointerId === e.pointerId) {
            const dx = e.clientX - this._karteDrag.x;
            const dy = e.clientY - this._karteDrag.y;
            
            // Sofortige Aktualisierung des Referenzpunktes (verhindert Drift)
            this._karteDrag.x = e.clientX;
            this._karteDrag.y = e.clientY;

            if (Math.abs(dx) > 0 || Math.abs(dy) > 0) {
                this._karteHatBewegt = true;
                const a = this.karteAnsicht;
                const rad = a.fLat * (Math.PI / 180);
                const lonFaktor = Math.cos(rad);

                // Einfache Delta-Verschiebung
                a.fLon -= dx / (a.sc * lonFaktor);
                a.fLat += dy / a.sc;
                
                this._karteBegrenzeAnsicht(); 
                this._karteRenderAnfordern();
            }
        }
        this._kartePointer.set(e.pointerId, { x: e.clientX, y: e.clientY });
    };

    App._kartePointerUp = function(e) {
        try { e.preventDefault(); } catch (_) {}
        this._kartePointer.delete(e.pointerId);
        if (this._karteAktiverPointerId === e.pointerId) this._karteAktiverPointerId = null;
        if (this._kartePointer.size === 0) {
            this._karteDrag = null;
            this.karteInteraktionAktiv = false;
            this._karteBegrenzeAnsicht();
            this._karteRenderAnfordern();
            // Wenn gezogen wurde, kurze Sperre für den Klick (Mobile-Browser feuern oft noch "click")
            if (this._karteHatBewegt) this._karteLetzteBewegungTs = Date.now();
        }
        if (this._kartePointer.size === 1) {
            const pt = Array.from(this._kartePointer.values())[0];
            this._karteDrag = { x: pt.x, y: pt.y };
            // aktiven Pointer neu setzen (der verbleibende)
            this._karteAktiverPointerId = Array.from(this._kartePointer.keys())[0] || null;
        }
    };

    App._karteKlick = function(ev) {
        // Klick nach Drag ignorieren, damit die Bedienung nicht "hakt"
        if (this._karteHatBewegt && (Date.now() - (this._karteLetzteBewegungTs || 0) < 450)) return;
        // Klick kurz nach blockiertem MultiTouch ebenfalls ignorieren
        if (Date.now() - (this._karteMultiTouchBlockTs || 0) < 600) return;

        const canvas = ev.currentTarget;
        if (!canvas) return;

        const rect = canvas.getBoundingClientRect();
        const x = ev.clientX - rect.left;
        const y = ev.clientY - rect.top;

        // Nächstgelegene Hit-Zone finden
        let best = null;
        let bestD2 = Infinity;
        for (const h of this._karteHitZonen) {
            const dx = x - h.x;
            const dy = y - h.y;
            const d2 = dx * dx + dy * dy;
            if (d2 <= h.r * h.r && d2 < bestD2) {
                best = h;
                bestD2 = d2;
            }
        }
        if (best?.recordId) {
            // Wenn Auswahlmodus aktiv ist, Punkt zur Auswahl hinzufügen und zoomen
            if (this.auswahlIstAktiv) {
                this.umschaltenAkteAuswahl(best.recordId);
            } else {
                this.openRecord(best.recordId);
            }
        }
    };

    App._karteTouchStart = function(ev) {
        try { ev.preventDefault(); } catch (_) {}
        const t = ev.touches && ev.touches[0];
        if (!t) return;
        if (ev.touches.length > 1) { this._karteDrag = null; return; }
        
        this.karteInteraktionAktiv = true;
        this._karteHatBewegt = false;
        this._karteDrag = { x: t.clientX, y: t.clientY };
    };

    App._karteTouchMove = function(ev) {
        try { ev.preventDefault(); } catch (_) {}
        const t = ev.touches && ev.touches[0];
        if (!t || !this._karteDrag) return;
        if (ev.touches.length > 1) return;

        const dx = t.clientX - this._karteDrag.x;
        const dy = t.clientY - this._karteDrag.y;
        
        // Sofortige Aktualisierung (verhindert Dauerscrollen)
        this._karteDrag.x = t.clientX;
        this._karteDrag.y = t.clientY;

        if (Math.abs(dx) > 0 || Math.abs(dy) > 0) {
            this._karteHatBewegt = true;
            const a = this.karteAnsicht;
            const rad = a.fLat * (Math.PI / 180);
            const lonFaktor = Math.cos(rad);

            a.fLon -= dx / (a.sc * lonFaktor);
            a.fLat += dy / a.sc;
            
            this._karteBegrenzeAnsicht(); 
            this._karteRenderAnfordern();
        }
    };

    App._karteTouchEnd = function(ev) {
        try { ev.preventDefault(); } catch (_) {}
        this._karteDrag = null;
        this.karteInteraktionAktiv = false;
        this._karteBegrenzeAnsicht();
        this._karteRenderAnfordern();
        if (this._karteHatBewegt) this._karteLetzteBewegungTs = Date.now();
    };

    App._karteBerechneGitterSchritt = function(sc) {
        // Berechnet einen "schönen" metrischen Gitterschritt in Kilometern
        // 111.32 km entspricht ca. 1 Grad (Breitengrad)
        const kmProPixel = 111.32 / sc;
        const zielPixelAbstand = 80; // Wir wollen Kästchen von ca. 80-120px
        const zielKm = zielPixelAbstand * kmProPixel;

        if (zielKm > 500) return 500;
        if (zielKm > 200) return 200;
        if (zielKm > 100) return 100;
        if (zielKm > 50) return 50;
        if (zielKm > 20) return 20;
        if (zielKm > 10) return 10;
        if (zielKm > 5) return 5;
        if (zielKm > 2) return 2;
        if (zielKm > 1) return 1;
        if (zielKm > 0.5) return 0.5;
        if (zielKm > 0.2) return 0.2;
        if (zielKm > 0.1) return 0.1;
        if (zielKm > 0.05) return 0.05;
        return 0.01;
    };

    App._karteZeichneGitter = function(ctx, xy, bnd, sc, cssW, cssH) {
        const schrittKm = this._karteBerechneGitterSchritt(sc);
        const schrittDeg = schrittKm / 111.32;
        
        const isDark = document.body.classList.contains('dark-mode');

        ctx.save();
        // Gitternetzstruktur: deutlichere Linien für Kästchen-Optik
        ctx.strokeStyle = isDark ? 'rgba(0, 0, 0, 0.12)' : 'rgba(0, 0, 0, 0.08)';
        ctx.lineWidth = 1;
        ctx.font = '10px Segoe UI';
        ctx.fillStyle = isDark ? 'rgba(0, 0, 0, 0.4)' : 'rgba(0, 0, 0, 0.3)';

        // Vertikale Linien (Längengrade)
        // Wir nutzen den gleichen schrittDeg für X und Y, damit es Kästchen (Squares) werden
        // ABER: Längengrade müssen mit cos(lat) korrigiert werden für echte km
        const a = this.karteAnsicht;
        const rad = a.fLat * (Math.PI / 180);
        const lonFaktor = Math.cos(rad);
        const schrittDegLon = schrittDeg / lonFaktor;

        const lonStart = Math.floor(bnd.lonMin / schrittDegLon) * schrittDegLon;
        const lonEnd = Math.ceil(bnd.lonMax / schrittDegLon) * schrittDegLon;
        for (let lon = lonStart; lon <= lonEnd; lon += schrittDegLon) {
            const p = xy(a.fLat, lon);
            ctx.beginPath();
            ctx.moveTo(p.x, 0);
            ctx.lineTo(p.x, cssH);
            ctx.stroke();
        }

        // Horizontale Linien (Breitengrade)
        const latStart = Math.floor(bnd.latMin / schrittDeg) * schrittDeg;
        const latEnd = Math.ceil(bnd.latMax / schrittDeg) * schrittDeg;
        for (let lat = latStart; lat <= latEnd; lat += schrittDeg) {
            const p = xy(lat, a.fLon);
            ctx.beginPath();
            ctx.moveTo(0, p.y);
            ctx.lineTo(cssW, p.y);
            ctx.stroke();
        }
        
        // Info-Text in der Ecke (optional, hilft aber enorm)
        const info = schrittKm >= 1 ? `${schrittKm} km` : `${schrittKm * 1000} m`;
        ctx.fillText(`Raster: ${info}`, 10, cssH - 10);
        
        ctx.restore();
    };

    App._karteZeichneMassstab = function(ctx, sc, cssW, cssH) {
        // 1 Grad Breitengrad ist ca. 111.32 km
        // sc sind Pixel pro Grad Breitengrad
        const kmProPixel = 111.32 / sc;
        
        // Ziel: Einen Balken zeichnen, der eine "schöne" Zahl an km repräsentiert
        const zielPixelBreite = 100;
        const zielKm = zielPixelBreite * kmProPixel;
        
        let massstabKm = 1;
        if (zielKm > 1000) massstabKm = 1000;
        else if (zielKm > 500) massstabKm = 500;
        else if (zielKm > 200) massstabKm = 200;
        else if (zielKm > 100) massstabKm = 100;
        else if (zielKm > 50) massstabKm = 50;
        else if (zielKm > 20) massstabKm = 20;
        else if (zielKm > 10) massstabKm = 10;
        else if (zielKm > 5) massstabKm = 5;
        else if (zielKm > 2) massstabKm = 2;
        else if (zielKm > 1) massstabKm = 1;
        else if (zielKm > 0.5) massstabKm = 0.5;
        else massstabKm = 0.1;

        const balkenPixelBreite = massstabKm / kmProPixel;
        const x = cssW - balkenPixelBreite - 20;
        const y = 40; // Oben rechts (User-Wunsch)

        ctx.save();
        ctx.strokeStyle = '#343a40';
        ctx.fillStyle = '#343a40';
        ctx.lineWidth = 2;
        ctx.font = 'bold 11px Segoe UI';

        // Balken zeichnen
        ctx.beginPath();
        ctx.moveTo(x, y - 5);
        ctx.lineTo(x, y);
        ctx.lineTo(x + balkenPixelBreite, y);
        ctx.lineTo(x + balkenPixelBreite, y - 5);
        ctx.stroke();

        // Text (mittig über dem Balken)
        const text = massstabKm >= 1 ? `${massstabKm} km` : `${massstabKm * 1000} m`;
        const tw = ctx.measureText(text).width;
        ctx.fillText(text, x + (balkenPixelBreite - tw) / 2, y - 10);
        ctx.restore();
    };

    App._karteBerechneFokuspunkt = function() {
        // Nutzt _karteAuswahlPunkte, um sicherzustellen, dass bei aktiver Auswahl (rot markiert)
        // auch wirklich diese Punkte im Fokus stehen, nicht die gesamte geladene Liste.
        const punkte = this._karteAuswahlPunkte();
        if (!punkte || punkte.length === 0) {
            this.karteZielpunkt = null;
            return;
        }

        let sumLat = 0, sumLon = 0;
        for (const p of punkte) {
            sumLat += p.lat;
            sumLon += p.lon;
        }
        
        this.karteZielpunkt = {
            lat: sumLat / punkte.length,
            lon: sumLon / punkte.length
        };
    };

    App.renderKarte = function() {
        const canvas = document.getElementById('karteCanvas');
        if (!canvas) return;

        const ctx = canvas.getContext('2d');
        const cssW = canvas.clientWidth || 800;
        const cssH = canvas.clientHeight || 500;

        // Mobile-Browser Stabilisierung
        if (cssW < 80 || cssH < 120) {
            if ((this._karteRenderVersuche || 0) < 40) {
                this._karteRenderVersuche = (this._karteRenderVersuche || 0) + 1;
                requestAnimationFrame(() => this.renderKarte());
            }
            return;
        }
        this._karteRenderVersuche = 0;

        const dpr = window.devicePixelRatio || 1;
        const targetW = Math.floor(cssW * dpr);
        const targetH = Math.floor(cssH * dpr);

        // PERFORMANCE: Nur skalieren, wenn sich die Größe wirklich geändert hat
        if (canvas.width !== targetW || canvas.height !== targetH) {
            canvas.width = targetW;
            canvas.height = targetH;
            ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        }

        try {
            // clearRect ist schneller als fillRect für den gesamten Bereich
            ctx.clearRect(0, 0, cssW, cssH);
            
            const isDark = document.body.classList.contains('dark-mode');
            
            // Hintergrund für eine modernere Optik (Immer hell/weiß, wie vom User gewünscht)
            ctx.fillStyle = '#ffffff';
            ctx.fillRect(0, 0, cssW, cssH);

            if (this.karteLadeStatus === 'lade' && (!this.kartePunkte || !this.kartePunkte.length)) {
                ctx.fillStyle = '#6c757d';
                ctx.font = '14px Segoe UI';
                ctx.fillText('Karte wird geladen...', 16, 28);
                this._karteHitZonen = [];
                return;
            }

            const punkte = this.kartePunkte || [];
            const ref = this.karteReferenzorte || {};

            if (!punkte.length) {
                ctx.fillStyle = '#6c757d';
                ctx.font = '14px Segoe UI';
                ctx.fillText('Keine Akten mit PLZ/Ort gefunden.', 16, 28);
                this._karteHitZonen = [];
                return;
            }

            // Fokuspunkt (Mitte der Auswahl) berechnen
            this._karteBerechneFokuspunkt();

            const a = this.karteAnsicht || { fLat: 51.1657, fLon: 10.4515, sc: 40 };
            const cx = cssW / 2;
            const cy = cssH / 2;

            // ── DIREKTE TRANSFORMATION (Pixel pro Grad) ──────────────
            const rad = a.fLat * (Math.PI / 180);
            const lonFaktor = Math.cos(rad);

            const xy = (lat, lon) => {
                const x = (lon - a.fLon) * a.sc * lonFaktor + cx;
                const y = (a.fLat - lat) * a.sc + cy;
                return { x, y };
            };

            // Viewport Bounds in Grad berechnen für Gitter/Inhalt
            const lonPadding = (cx / (a.sc * lonFaktor));
            const latPadding = (cy / a.sc);
            const vBnd = {
                lonMin: a.fLon - lonPadding,
                lonMax: a.fLon + lonPadding,
                latMin: a.fLat - latPadding,
                latMax: a.fLat + latPadding
            };

            // 1. Gitter zeichnen (basiert auf Viewport)
            this._karteZeichneGitter(ctx, xy, vBnd, a.sc, cssW, cssH);

            // 2. Referenzorte
            ctx.strokeStyle = isDark ? 'rgba(255,255,255,0.3)' : 'rgba(0,0,0,0.3)';
            ctx.fillStyle = isDark ? '#333333' : '#333333';
            ctx.lineWidth = 1;
            
            // Kollisionsprüfung für Texte (verhindert Überlappungen)
            const belegteZonen = [];
            const checkKollision = (x, y, w, h) => {
                for (const z of belegteZonen) {
                    if (!(x + w < z.x || x > z.x + z.w || y + h < z.y || y > z.y + z.h)) return true;
                }
                return false;
            };
            
            // Sortieren nach Level, damit wichtige Städte zuerst kommen
            const sortierteOrte = Object.entries(ref).sort((a, b) => {
                const lvlA = a[1].level || 0;
                const lvlB = b[1].level || 0;
                return lvlA - lvlB;
            });

            for (const [name, o] of sortierteOrte) {
                if (!o) continue;

                const level = typeof o.level === 'number' ? o.level : 0;
                let sichtbar = true;
                
                // Aggressivere Schwellenwerte für Zoomstufen
                if (level === 0 && a.sc < 10) sichtbar = false;      // Welt-Ebene: gar keine Städte
                if (level === 1 && a.sc < 250) sichtbar = false;     // Deutschland-Ebene: nur Metropolen (Level 0)
                if (level === 2 && a.sc < 800) sichtbar = false;     // Regional-Ebene: nur größere Städte
                if (level === 3 && a.sc < 2500) sichtbar = false;    // Nah-Ebene
                if (level >= 4 && a.sc < 6000) sichtbar = false;     // Detail-Ebene

                if (!sichtbar) continue;

                const pos = xy(o.lat, o.lon);
                // Nur zeichnen, wenn im Viewport
                if (pos.x < -100 || pos.x > cssW + 100 || pos.y < -100 || pos.y > cssH + 100) continue;

                // Text-Maße berechnen
                ctx.font = '11px Segoe UI';
                const metrics = ctx.measureText(name);
                const textW = metrics.width + 10;
                const textH = 20;
                const textX = pos.x + 6;
                const textY = pos.y - 8;

                // Kollisionsprüfung (Punkt + Text)
                if (checkKollision(pos.x - 5, pos.y - 15, textW + 10, textH + 10)) continue;

                // Zeichnen
                ctx.beginPath();
                ctx.arc(pos.x, pos.y, 4, 0, Math.PI * 2);
                ctx.stroke();

                ctx.fillText(name, textX, textY);
                
                // Zone als belegt markieren
                belegteZonen.push({ x: pos.x - 5, y: pos.y - 15, w: textW + 10, h: textH + 10 });
            }

            // 3. Punkte zeichnen
            // PERFORMANCE: Nur neu berechnen, wenn sich Zoom (sc) oder Daten geändert haben
            if (!this._karteCachePlatzierung || this._karteCacheSc !== a.sc || this._karteCacheDataTs !== this._karteLastDataTs) {
                this._karteCachePlatzierung = this._karteVerteileUeberlappungen(punkte, xy, cssW, cssH);
                this._karteCacheSc = a.sc;
                this._karteCacheDataTs = this._karteLastDataTs;
            }
            
            const platzierung = this._karteCachePlatzierung;
            this._karteHitZonen = [];
            for (const it of platzierung) {
                // Die XY-Koordinaten im Cache müssen neu berechnet werden, da sie sich beim Schieben ändern!
                // ABER: Die Verteilung (Cluster) bleibt gleich.
                // Korrektur: xy() muss auf die Geo-Koordinaten des Punktes angewendet werden.
                const pos = xy(it.p.lat, it.p.lon);
                
                // PERFORMANCE: Nur zeichnen, wenn im sichtbaren Bereich
                if (pos.x < -20 || pos.x > cssW + 20 || pos.y < -20 || pos.y > cssH + 20) continue;

                const p = it.p;
                const isSelected = this.auswahlIds && this.auswahlIds.has(p.id);
                const size = isSelected ? 14 : 10;
                const color = this._karteFarbeAusRahmenklasse(p.border_color);
                
                ctx.save();
                ctx.translate(pos.x, pos.y);
                
                // Schatten für Tiefe
                ctx.shadowBlur = (isSelected ? 8 : 4) * dpr;
                ctx.shadowColor = isSelected ? 'rgba(37, 99, 235, 0.5)' : 'rgba(0,0,0,0.3)';
                ctx.shadowOffsetY = 2 * dpr;

                // Marker-Körper (Modernes Google-Style Pin Design - exakt wie im Produktblatt)
                ctx.beginPath();
                ctx.fillStyle = color;
                ctx.strokeStyle = '#ffffff';
                ctx.lineWidth = isSelected ? 2.5 : 1.5;
                
                // Wir zeichnen einen Pin, der fa-map-marker-alt entspricht:
                // Ein Kreis oben und eine scharfe Spitze unten.
                const headRadius = size;
                const headCenterY = -size * 2.2; // Etwas höher für bessere Proportion
                
                // Kopf (Kreis oben)
                ctx.arc(0, headCenterY, headRadius, 0.15 * Math.PI, 0.85 * Math.PI, true);
                // Spitze unten (0,0)
                ctx.lineTo(0, 0);
                ctx.closePath();
                
                ctx.fill();
                ctx.stroke();

                // Innerer weißer Kreis (Loch/Auge)
                ctx.shadowBlur = 0;
                ctx.shadowOffsetY = 0;
                ctx.beginPath();
                ctx.fillStyle = '#ffffff';
                ctx.arc(0, headCenterY, size * 0.4, 0, Math.PI * 2);
                ctx.fill();

                ctx.restore();

                // Hit-Zone für Klicks (angepasst an die neue Pin-Höhe)
                this._karteHitZonen.push({ x: pos.x, y: pos.y - size * 2.2, r: isSelected ? 24 : 20, recordId: p.id });
            }

            // 4. Maßstab
            this._karteZeichneMassstab(ctx, a.sc, cssW, cssH);

            if (this._karteAnsichtNachRender) {
                this._karteAnsichtNachRender = false;
                this._karteSetzeAnsichtFuerAuswahl();
                this._karteRenderAnfordern();
            }

        } catch (e) {
            console.error('Karten-Renderfehler:', e);
        }
    };

    // Direkt nach Laden initialisieren (DOM ist bereits da, weil Script am Ende geladen wird)
    App.initKarte();
})();
