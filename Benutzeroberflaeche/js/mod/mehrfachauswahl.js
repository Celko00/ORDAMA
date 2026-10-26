/**
 * Mehrfachauswahl-Modul (Mobile: Long-Press, Desktop: Strg-Klick)
 * Ziel: mehrere Akten selektieren und Massenaktionen ausführen.
 *
 * Hinweis: Dieses Modul erweitert das globale App-Objekt aus app.js.
 */
(() => {
    if (typeof App === 'undefined') return;

    // ── State ──────────────────────────────────────
    App.auswahlIstAktiv = false;
    App.auswahlIds = new Set();
    App.auswahlLetzteId = null;
    App._auswahlLongPressTimer = null;
    App._auswahlPointerDown = null;
    App._auswahlKlickUnterdrueckenBis = 0;

    // ── Helpers ────────────────────────────────────
    App._holeAkteIdAusElement = function(element) {
        const card = element?.closest?.('.record-card');
        if (!card) return null;
        const id = card.dataset.recordId;
        // Gallery uses string IDs like "att_123", Akten use numeric IDs
        // Return the ID as-is for consistency with auswahlIds Set
        return id || null;
    };

    // Hilfsfunktion: UI nach Bulk-Aktion aktualisieren
    App._aktualisiereUINachBulkAktion = async function() {
        const isGallery = this.currentSection === 'gallery';
        if (isGallery) {
            await this.loadGallery();
        } else {
            await this.loadRecords();
        }
    };

    // ── Mobile Auswahl Modal ───────────────────────
    App.openMobileAuswahlModal = function(btnId) {
        const overlay = document.getElementById('mobileAuswahlModalOverlay');
        const titleEl = document.getElementById('mobileAuswahlTitle');
        const content = document.getElementById('mobileAuswahlContent');
        if (!overlay || !titleEl || !content) return;

        // Check permissions first
        let shouldShow = true;
        if (btnId === 'bulkReminderBtn') {
            shouldShow = this.currentUser?.role === 'admin' || this.currentUser?.can_set_reminder;
        } else if (btnId === 'bulkErinnerungBtn') {
            shouldShow = this.currentUser?.role === 'admin' || this.currentUser?.can_set_erinnerung;
        } else if (btnId === 'bulkDeleteTerminBtn') {
            shouldShow = this.currentUser?.role === 'admin' || this.currentUser?.can_delete_termine;
        } else if (btnId === 'bulkDeleteErinnerungBtn') {
            shouldShow = this.currentUser?.role === 'admin' || this.currentUser?.can_delete_erinnerung;
        } else if (btnId === 'bulkMoveBtn') {
            shouldShow = this.currentUser?.role === 'admin' || this.currentUser?.can_set_category;
        } else if (btnId === 'auswahlStatusBtn') {
            shouldShow = this.currentUser?.role === 'admin' || this.currentUser?.can_set_status;
        } else if (btnId === 'auswahlFarbeBtn') {
            shouldShow = this.currentUser?.role === 'admin' || this.currentUser?.can_set_border_color;
        } else if (btnId === 'bulkNoteBtn') {
            shouldShow = this.currentUser?.role === 'admin' || this.currentUser?.can_set_note;
        } else if (btnId === 'bulkArchiveBtn') {
            shouldShow = this.currentUser?.role === 'admin' || this.currentUser?.can_archive;
        }
        if (!shouldShow) {
            this.toast('Keine Berechtigung für diese Aktion', 'error');
            return;
        }

        let html = '';
        let title = '';

        if (btnId === 'bulkReminderBtn') {
            App.closeMobileAuswahlModal();
            App.openBulkReminderModal();
            return;
        } else if (btnId === 'bulkErinnerungBtn') {
            App.closeMobileAuswahlModal();
            App.openBulkErinnerungModal();
            return;
        } else if (btnId === 'bulkDeleteTerminBtn') {
            App.closeMobileAuswahlModal();
            App.deleteSelectedRecordsTermine();
            return;
        } else if (btnId === 'bulkDeleteErinnerungBtn') {
            App.closeMobileAuswahlModal();
            App.deleteSelectedRecordsErinnerungn();
            return;
        } else if (btnId === 'auswahlStatusBtn') {
            title = 'Status ändern';
            html = `
                <div class="auswahl-option" onclick="App.updateSelectedRecordsStatus('neutral'); App.closeMobileAuswahlModal();">
                    <i class="fas fa-info-circle text-neutral"></i> <span>Neutral</span>
                </div>
                <div class="auswahl-option" onclick="App.updateSelectedRecordsStatus('offen'); App.closeMobileAuswahlModal();">
                    <i class="fas fa-clock text-offen"></i> <span>Offen</span>
                </div>
                <div class="auswahl-option" onclick="App.updateSelectedRecordsStatus('bearbeitung'); App.closeMobileAuswahlModal();">
                    <i class="fas fa-spinner text-bearbeitung"></i> <span>In Bearbeitung</span>
                </div>
                <div class="auswahl-option" onclick="App.updateSelectedRecordsStatus('erledigt'); App.closeMobileAuswahlModal();">
                    <i class="fas fa-check-circle text-erledigt"></i> <span>Erledigt</span>
                </div>
            `;
        } else if (btnId === 'auswahlFarbeBtn') {
            title = 'Farbe ändern';
            html = `
                <div class="auswahl-option" onclick="App.updateSelectedRecordsColor(''); App.closeMobileAuswahlModal();">
                    <i class="fas fa-square" style="color:#e9ecef"></i> Standard
                </div>
                <div class="auswahl-option" onclick="App.updateSelectedRecordsColor('border-red'); App.closeMobileAuswahlModal();">
                    <i class="fas fa-square" style="color:#dc3545"></i> Rot
                </div>
                <div class="auswahl-option" onclick="App.updateSelectedRecordsColor('border-yellow'); App.closeMobileAuswahlModal();">
                    <i class="fas fa-square" style="color:#ffc107"></i> Gelb
                </div>
                <div class="auswahl-option" onclick="App.updateSelectedRecordsColor('border-green'); App.closeMobileAuswahlModal();">
                    <i class="fas fa-square" style="color:#28a745"></i> Grün
                </div>
                <div class="auswahl-option" onclick="App.updateSelectedRecordsColor('border-blue'); App.closeMobileAuswahlModal();">
                    <i class="fas fa-square" style="color:#007bff"></i> Blau
                </div>
                <div class="auswahl-option" onclick="App.updateSelectedRecordsColor('border-magenta'); App.closeMobileAuswahlModal();">
                    <i class="fas fa-square" style="color:#ff00ff"></i> Magenta
                </div>
            `;
        } else if (btnId === 'bulkMoveBtn') {
            title = 'Kategorie ändern';
            // Kategorien aus der App holen
            const categories = this.categories || [];
            html = categories.map(cat => `
                <div class="auswahl-option" onclick="App.moveSelectedRecords(${cat.id}); App.closeMobileAuswahlModal();">
                    <i class="fas fa-tag"></i> ${this.escapeHtml(cat.name)}
                </div>
            `).join('');
            if (!html) {
                html = '<div class="auswahl-option" style="color: #999;">Keine Kategorien verfügbar</div>';
            }
        } else if (btnId === 'bulkNoteBtn') {
            App.closeMobileAuswahlModal();
            App.openBulkNoteModal();
            return;
        }

        titleEl.textContent = title;
        content.innerHTML = html;
        overlay.classList.add('show');
    };

    App.closeMobileAuswahlModal = function() {
        const overlay = document.getElementById('mobileAuswahlModalOverlay');
        if (overlay) overlay.classList.remove('show');
    };

    App._setzeCardAuswahlklasse = function(recordId, istAusgewaehlt) {
        const card = document.querySelector(`.record-card[data-record-id="${recordId}"]`);
        if (!card) return;
        card.classList.toggle('ausgewaehlt', !!istAusgewaehlt);
        const btn = card.querySelector('.auswahl-indikator');
        if (btn) btn.setAttribute('aria-pressed', istAusgewaehlt ? 'true' : 'false');
    };

    App._holeSichtbareAuswahlCards = function() {
        const isGallery = this.currentSection === 'gallery';
        const container = document.getElementById(isGallery ? 'galleryGrid' : 'recordsList');
        if (!container) return [];

        return Array.from(container.querySelectorAll('.record-card[data-record-id]')).filter(card => {
            const style = window.getComputedStyle(card);
            return style.display !== 'none' && style.visibility !== 'hidden';
        });
    };

    // Bulk Erinnerung state
    App.bulkErinnerungDateTimePickerState = {
        isOpen: false,
        activeType: 'start',
        currentDate: new Date(),
        selectedDate: null
    };

    App._aktualisiereAuswahlToolbar = function() {
        const isGallery = this.currentSection === 'gallery';
        const toolbar = document.getElementById(isGallery ? 'galleryAuswahlToolbar' : 'auswahlToolbar');
        const anzeige = document.getElementById(isGallery ? 'galleryAuswahlAnzahl' : 'auswahlAnzahl');
        const auswahlAlleBtn = document.getElementById(isGallery ? 'galleryAuswahlAlleBtn' : 'auswahlAlleBtn');
        const auswahlActionsBtn = document.getElementById(isGallery ? 'galleryAuswahlActionsBtn' : 'auswahlActionsBtn');
        const auswahlActionsDropdown = document.getElementById(isGallery ? 'galleryAuswahlActionsDropdown' : 'auswahlActionsDropdown');

        if (!toolbar || !anzeige) return;

        const anzahl = this.auswahlIds.size;
        anzeige.textContent = `${anzahl} ausgewählt`;

        // Button-Text für "Alle auswählen" / "Keine auswählen" aktualisieren
        if (auswahlAlleBtn) {
            const cards = this._holeSichtbareAuswahlCards();
            const alleAusgewaehlt = cards.length > 0 && cards.every(card => {
                const id = card.dataset.recordId;
                return id && this.auswahlIds.has(id);
            });
            const icon = auswahlAlleBtn.querySelector('i');
            if (alleAusgewaehlt) {
                auswahlAlleBtn.title = 'Alle abwählen';
                if (icon) icon.className = 'fas fa-times';
                auswahlAlleBtn.innerHTML = '<i class="fas fa-times"></i> Keine auswählen';
            } else {
                auswahlAlleBtn.title = isGallery ? 'Alle sichtbaren Bilder auswählen' : 'Alle sichtbaren Akten auswählen';
                if (icon) icon.className = 'fas fa-check-double';
                auswahlAlleBtn.innerHTML = '<i class="fas fa-check-double"></i> Alle auswählen';
            }
        }

        // Berechtigungsprüfung für Dropdown-Menü-Items
        if (auswahlActionsDropdown) {
            const bulkNoteBtn = auswahlActionsDropdown.querySelector('#bulkNoteBtn');
            const bulkReminderBtn = auswahlActionsDropdown.querySelector('#bulkReminderBtn');
            const bulkErinnerungBtn = auswahlActionsDropdown.querySelector('#bulkErinnerungBtn');
            const bulkDeleteTerminBtn = auswahlActionsDropdown.querySelector('#bulkDeleteTerminBtn');
            const bulkDeleteErinnerungBtn = auswahlActionsDropdown.querySelector('#bulkDeleteErinnerungBtn');
            const bulkArchiveBtn = auswahlActionsDropdown.querySelector('#bulkArchiveBtn');
            const kategorieSection = auswahlActionsDropdown.querySelector('.dropdown-section:nth-of-type(1)');
            const statusSection = auswahlActionsDropdown.querySelector('.dropdown-section:nth-of-type(2)');
            const farbeSection = auswahlActionsDropdown.querySelector('.dropdown-section:nth-of-type(3)');

            if (bulkNoteBtn) {
                const hasNotePermission = this.currentUser?.role === 'admin' || this.currentUser?.can_set_note;
                bulkNoteBtn.style.display = hasNotePermission ? '' : 'none';
            }
            if (bulkReminderBtn) {
                const hasReminderPermission = this.currentUser?.role === 'admin' || this.currentUser?.can_set_reminder;
                bulkReminderBtn.style.display = hasReminderPermission ? '' : 'none';
            }
            if (bulkErinnerungBtn) {
                const hasErinnerungPermission = this.currentUser?.role === 'admin' || this.currentUser?.can_set_erinnerung;
                bulkErinnerungBtn.style.display = hasErinnerungPermission ? '' : 'none';
            }
            if (bulkDeleteTerminBtn) {
                const hasDeleteTerminPermission = this.currentUser?.role === 'admin' || this.currentUser?.can_delete_termine;
                bulkDeleteTerminBtn.style.display = hasDeleteTerminPermission ? '' : 'none';
            }
            if (bulkDeleteErinnerungBtn) {
                const hasDeleteErinnerungPermission = this.currentUser?.role === 'admin' || this.currentUser?.can_delete_erinnerung;
                bulkDeleteErinnerungBtn.style.display = hasDeleteErinnerungPermission ? '' : 'none';
            }
            if (bulkArchiveBtn) {
                const hasArchivePermission = this.currentUser?.role === 'admin' || this.currentUser?.can_archive;
                bulkArchiveBtn.style.display = hasArchivePermission ? '' : 'none';
            }
            if (kategorieSection) {
                const hasCategoryPermission = this.currentUser?.role === 'admin' || this.currentUser?.can_set_category;
                kategorieSection.style.display = hasCategoryPermission ? '' : 'none';
            }
            if (statusSection) {
                const hasStatusPermission = this.currentUser?.role === 'admin' || this.currentUser?.can_set_status;
                statusSection.style.display = hasStatusPermission ? '' : 'none';
            }
            if (farbeSection) {
                const hasColorPermission = this.currentUser?.role === 'admin' || this.currentUser?.can_set_border_color;
                farbeSection.style.display = hasColorPermission ? '' : 'none';
            }
        }
    };

    // ── Modus-Steuerung ────────────────────────────
    App.aktiviereAuswahlmodus = function() {
        if (this.auswahlIstAktiv) return;
        this.auswahlIstAktiv = true;

        const isGallery = this.currentSection === 'gallery';
        if (isGallery) {
            document.getElementById('gallerySection')?.classList.add('auswahl-aktiv');
            document.getElementById('galleryAuswahlToolbar')?.classList.remove('hidden');
            document.getElementById('galleryAuswahlStartBtn')?.classList.add('hidden');
            document.getElementById('galleryAuswahlFertigBtn')?.classList.remove('hidden');
        } else {
            document.getElementById('recordsSection')?.classList.add('auswahl-aktiv');
            document.getElementById('auswahlToolbar')?.classList.remove('hidden');
            document.getElementById('auswahlStartBtn')?.classList.add('hidden');
            document.getElementById('auswahlFertigBtn')?.classList.remove('hidden');
        }

        this._aktualisiereAuswahlToolbar();
    };

    App.deaktiviereAuswahlmodus = function(allesAbwaehlen = true) {
        if (!this.auswahlIstAktiv && this.auswahlIds.size === 0) return;

        this.auswahlIstAktiv = false;
        this.auswahlLetzteId = null;

        const isGallery = this.currentSection === 'gallery';
        if (isGallery) {
            document.getElementById('gallerySection')?.classList.remove('auswahl-aktiv');
            document.getElementById('galleryAuswahlToolbar')?.classList.add('hidden');
            document.getElementById('galleryAuswahlStartBtn')?.classList.remove('hidden');
            document.getElementById('galleryAuswahlFertigBtn')?.classList.add('hidden');
        } else {
            document.getElementById('recordsSection')?.classList.remove('auswahl-aktiv');
            document.getElementById('auswahlToolbar')?.classList.add('hidden');
            document.getElementById('auswahlStartBtn')?.classList.remove('hidden');
            document.getElementById('auswahlFertigBtn')?.classList.add('hidden');
        }
        
        // Dropdown schließen falls offen
        document.querySelector('.dropdown-bulk-status .dropdown-content')?.classList.remove('show');

        if (allesAbwaehlen) {
            this.auswahlIds.clear();
        }

        this._aktualisiereAuswahlToolbar();
    };

    // ── Auswahl-Operationen ────────────────────────
    App.umschaltenAkteAuswahl = function(recordId) {
        // Accept both numeric IDs (Akten) and string IDs (Gallery like "att_123")
        if (recordId === null || recordId === undefined || recordId === '') return;
        if (!this.auswahlIstAktiv) this.aktiviereAuswahlmodus();

        if (this.auswahlIds.has(recordId)) {
            this.auswahlIds.delete(recordId);
            this._setzeCardAuswahlklasse(recordId, false);
        } else {
            this.auswahlIds.add(recordId);
            this._setzeCardAuswahlklasse(recordId, true);
        }

        this.auswahlLetzteId = recordId;
        this._aktualisiereAuswahlToolbar();

        // Karte automatisch zoomen, wenn wir im Karten-Modus sind und Punkte ausgewählt sind
        if (this.currentSection === 'karte' && this.auswahlIds.size > 0) {
            this._karteFokusAufAuswahl();
        }

        // Auswahlmodus NICHT automatisch beenden - Benutzer muss manuell beenden
    };

    App.aktualisiereAuswahlDarstellungNachRender = function() {
        if (!this.auswahlIstAktiv || this.auswahlIds.size === 0) return;
        for (const id of this.auswahlIds) this._setzeCardAuswahlklasse(id, true);
        this._aktualisiereAuswahlToolbar();
    };

    App.waehleAlleSichtbarenAkten = function() {
        if (!this.auswahlIstAktiv) this.aktiviereAuswahlmodus();

        const cards = this._holeSichtbareAuswahlCards();
        if (!cards.length) {
            this.toast('Keine Akten zum Auswählen vorhanden', 'warning');
            return;
        }

        cards.forEach(card => {
            const id = card.dataset.recordId;
            if (!id) return;
            this.auswahlIds.add(id);
            this._setzeCardAuswahlklasse(id, true);
            this.auswahlLetzteId = id;
        });

        this._aktualisiereAuswahlToolbar();

        // Karte automatisch zoomen, wenn wir im Karten-Modus sind
        if (this.currentSection === 'karte' && this.auswahlIds.size > 0) {
            this._karteFokusAufAuswahl();
        }
    };

    App.waehleKeineSichtbarenAkten = function() {
        const cards = this._holeSichtbareAuswahlCards();
        if (!cards.length) return;

        cards.forEach(card => {
            const id = card.dataset.recordId;
            if (!id) return;
            this.auswahlIds.delete(id);
            this._setzeCardAuswahlklasse(id, false);
        });

        this._aktualisiereAuswahlToolbar();

        // Karte zurücksetzen, wenn wir im Karten-Modus sind und keine Auswahl mehr
        if (this.currentSection === 'karte' && this.auswahlIds.size === 0) {
            this._karteFokusAufAuswahl();
        }
    };

    App.umschaltenAlleSichtbarenAkten = function() {
        if (!this.auswahlIstAktiv) this.aktiviereAuswahlmodus();

        const cards = this._holeSichtbareAuswahlCards();
        if (!cards.length) {
            this.toast('Keine Akten zum Auswählen vorhanden', 'warning');
            return;
        }

        // Prüfen, ob alle sichtbaren Akten bereits ausgewählt sind
        const alleAusgewaehlt = cards.every(card => {
            const id = card.dataset.recordId;
            return id && this.auswahlIds.has(id);
        });

        if (alleAusgewaehlt) {
            // Alle abwählen
            this.waehleKeineSichtbarenAkten();
        } else {
            // Alle auswählen
            this.waehleAlleSichtbarenAkten();
        }

        // Karte automatisch zoomen, wenn wir im Karten-Modus sind
        if (this.currentSection === 'karte' && this.auswahlIds.size > 0) {
            this._karteFokusAufAuswahl();
        }
    };

    // ── Aktionen ───────────────────────────────────
    App.loescheAusgewaehlteAkten = async function() {
        const ids = Array.from(this.auswahlIds);
        if (!ids.length) {
            this.toast('Keine Akten ausgewählt', 'warning');
            return;
        }
        if (!await this.confirm('Akten löschen?', `${ids.length} Akten werden endgültig gelöscht.`)) return;

        try {
            // Prüfen ob Offline-Akten dabei sind (anhand von temp_id)
            const offlineRecords = [];
            const onlineIds = [];
            
            ids.forEach(id => {
                const record = this.records.find(r => r.id === id || r.temp_id === id);
                if (record?.is_offline) {
                    offlineRecords.push(record);
                } else {
                    onlineIds.push(id);
                }
            });
            
            // Offline-Akten löschen
            let offlineDeleted = 0;
            for (const record of offlineRecords) {
                try {
                    await OfflineStorage.deletePendingRecord(record.temp_id);
                    offlineDeleted++;
                } catch (e) {
                    console.error('Fehler beim Löschen der Offline-Akte:', record.temp_id, e);
                }
            }
            
            // Online-Akten löschen
            let onlineDeleted = 0;
            if (onlineIds.length > 0) {
                const data = await this.apiPost('/records/massen-loeschen', { ids: onlineIds });
                onlineDeleted = data?.deleted_count ?? onlineIds.length;
            }
            
            const totalDeleted = offlineDeleted + onlineDeleted;
            this.toast(`${totalDeleted} Akten geloescht (${offlineDeleted} offline, ${onlineDeleted} online)`, 'success');
            
            // Debug: Logge IDs und Records vor dem Filtern
            console.log('🗑️ IDs zum Löschen:', ids);
            console.log('🗑️ Offline-Akten zum Löschen:', offlineRecords.map(r => ({ id: r.id, temp_id: r.temp_id })));
            console.log('🗑️ Records vor dem Filtern:', this.records.length);
            
            // IDs in Zahlen umwandeln für korrekten Vergleich (außer für Offline temp_ids)
            const numericIds = ids.map(id => {
                const num = Number(id);
                return isNaN(num) ? id : num;
            });
            
            // Aus lokaler Liste entfernen (sowohl nach id als auch nach temp_id)
            const beforeCount = this.records.length;
            this.records = this.records.filter(r => !numericIds.includes(r.id) && !numericIds.includes(r.temp_id));
            const afterCount = this.records.length;
            console.log(`🗑️ Records gefiltert: ${beforeCount} -> ${afterCount} (entfernt: ${beforeCount - afterCount})`);
            
            this.deaktiviereAuswahlmodus(true);
            this.renderRecords();
            await this.updateOfflineIndicator();
            await this.checkConnectionStatus();
            
            if (this.currentSection === 'dashboard') this.loadDashboard();
            if (this.currentSection === 'dashboard') this.renderCalendarChart();
        } catch (e) {
            this.toast(e.message, 'error');
        }
    };

    App.updateSelectedRecordsStatus = async function(newStatus) {
        const ids = Array.from(this.auswahlIds);
        if (!ids.length) {
            this.toast('Keine Akten ausgewählt', 'warning');
            return;
        }

        const statusLabels = {
            'offen': 'Offen',
            'neutral': 'Neutral',
            'erledigt': 'Erledigt'
        };

        const statusLabel = statusLabels[newStatus] || newStatus;
        if (!await this.confirm('Status ändern?', `Soll der Status für ${ids.length} Akten auf "${statusLabel}" gesetzt werden?`, 'Ja, ändern', 'btn-primary')) return;

        try {
            // Prüfen ob Offline-Akten dabei sind
            const offlineRecords = [];
            const onlineIds = [];
            
            ids.forEach(id => {
                const record = this.records.find(r => r.id === id);
                if (record?.is_offline) {
                    offlineRecords.push(record);
                } else {
                    onlineIds.push(id);
                }
            });
            
            // Offline-Akten aktualisieren
            let offlineUpdated = 0;
            for (const record of offlineRecords) {
                try {
                    record.status = newStatus;
                    await OfflineStorage.updatePendingRecord(record.temp_id, record);
                    offlineUpdated++;
                } catch (e) {
                    console.error('Fehler beim Aktualisieren der Offline-Akte:', record.id, e);
                }
            }
            
            // Online-Akten aktualisieren
            let onlineUpdated = 0;
            if (onlineIds.length > 0) {
                const data = await this.apiPost('/records/massen-status', { ids: onlineIds, status: newStatus });
                onlineUpdated = data?.updated_count ?? onlineIds.length;
            }
            
            const totalUpdated = offlineUpdated + onlineUpdated;
            this.toast(`${totalUpdated} Akten aktualisiert (${offlineUpdated} offline, ${onlineUpdated} online)`, 'success');

            // Auswahl leeren aber Auswahlmodus aktiv lassen
            this.auswahlIds.clear();
            this._aktualisiereAuswahlToolbar();

            // Dropdown schließen
            document.querySelector('.dropdown-bulk-actions .dropdown-content')?.classList.remove('show');

            // Daten neu laden für sofortige Sichtbarkeit der Änderungen
            await this._aktualisiereUINachBulkAktion();

            if (this.currentSection === 'dashboard') this.loadDashboard();
        } catch (e) {
            this.toast(e.message, 'error');
        }
    };

    App.updateSelectedRecordsColor = async function(newColor) {
        const ids = Array.from(this.auswahlIds);
        if (!ids.length) {
            this.toast('Keine Akten ausgewählt', 'warning');
            return;
        }

        const colorLabels = {
            '': 'Standard',
            'border-red': 'Rot',
            'border-yellow': 'Gelb',
            'border-green': 'Grün',
            'border-blue': 'Blau',
            'border-magenta': 'Magenta'
        };

        const label = colorLabels[newColor] || 'Standard';
        if (!await this.confirm('Farbe ändern?', `Soll die Rahmenfarbe für ${ids.length} Akten auf "${label}" gesetzt werden?`, 'Ja, ändern', 'btn-primary')) return;

        try {
            // Prüfen ob Offline-Akten dabei sind
            const offlineRecords = [];
            const onlineIds = [];
            
            ids.forEach(id => {
                const record = this.records.find(r => r.id === id);
                if (record?.is_offline) {
                    offlineRecords.push(record);
                } else {
                    onlineIds.push(id);
                }
            });
            
            // Offline-Akten aktualisieren
            let offlineUpdated = 0;
            for (const record of offlineRecords) {
                try {
                    record.border_color = newColor;
                    await OfflineStorage.updatePendingRecord(record.temp_id, record);
                    offlineUpdated++;
                } catch (e) {
                    console.error('Fehler beim Aktualisieren der Offline-Akte:', record.id, e);
                }
            }
            
            // Online-Akten aktualisieren
            let onlineUpdated = 0;
            if (onlineIds.length > 0) {
                const data = await this.apiPost('/records/massen-farbe', { ids: onlineIds, color: newColor });
                onlineUpdated = data?.updated_count ?? onlineIds.length;
            }

            const totalUpdated = offlineUpdated + onlineUpdated;
            this.toast(`${totalUpdated} Akten aktualisiert (${offlineUpdated} offline, ${onlineUpdated} online)`, 'success');

            // Lokale Liste sofort aktualisieren für sofortige Sichtbarkeit
            this.records.forEach(r => {
                if (ids.includes(r.id)) {
                    r.border_color = newColor;
                }
            });
            this.renderRecords();

            // Auswahl leeren aber Auswahlmodus aktiv lassen
            this.auswahlIds.clear();
            this._aktualisiereAuswahlToolbar();

            // Dropdown schließen
            document.querySelector('.dropdown-bulk-actions .dropdown-content')?.classList.remove('show');

            // Daten neu laden für Konsistenz
            await this._aktualisiereUINachBulkAktion();
        } catch (e) {
            this.toast(e.message, 'error');
        }
    };

    App.updateSelectedRecordsNote = async function(newNote) {
        const ids = Array.from(this.auswahlIds);
        if (!ids.length) {
            this.toast('Keine Akten ausgewählt', 'warning');
            return;
        }

        const noteDisplay = newNote || 'leer';
        if (!await this.confirm('Vermerk ändern?', `Soll der Vermerk für ${ids.length} Akten auf "${noteDisplay}" gesetzt werden?`, 'Ja, ändern', 'btn-primary')) return;

        try {
            // Prüfen ob Offline-Akten dabei sind
            const offlineRecords = [];
            const onlineIds = [];
            
            ids.forEach(id => {
                const record = this.records.find(r => r.id === id);
                if (record?.is_offline) {
                    offlineRecords.push(record);
                } else {
                    onlineIds.push(id);
                }
            });
            
            // Offline-Akten aktualisieren
            let offlineUpdated = 0;
            for (const record of offlineRecords) {
                try {
                    record.hashtags = newNote;
                    await OfflineStorage.updatePendingRecord(record.temp_id, record);
                    offlineUpdated++;
                } catch (e) {
                    console.error('Fehler beim Aktualisieren der Offline-Akte:', record.id, e);
                }
            }
            
            // Online-Akten aktualisieren
            let onlineUpdated = 0;
            if (onlineIds.length > 0) {
                const data = await this.apiPost('/records/massen-note', { ids: onlineIds, note: newNote });
                onlineUpdated = data?.updated_count ?? onlineIds.length;
            }
            
            const totalUpdated = offlineUpdated + onlineUpdated;
            this.toast(`${totalUpdated} Akten aktualisiert (${offlineUpdated} offline, ${onlineUpdated} online)`, 'success');
            
            // Lokale Liste aktualisieren
            this.records.forEach(r => {
                if (ids.includes(r.id)) {
                    r.hashtags = newNote;
                }
            });
            
            this.deaktiviereAuswahlmodus(true);
            this.renderRecords();
        } catch (e) {
            this.toast(e.message, 'error');
        }
    };

    App.updateBulkMoveDropdownMod = function() {
        const dropdown = document.getElementById('bulkMoveDropdown');
        const galleryDropdown = document.getElementById('galleryBulkMoveDropdown');
        
        if (dropdown) {
            dropdown.innerHTML = '';
            // Keine Kategorie Option
            const noneBtn = document.createElement('button');
            noneBtn.type = 'button';
            noneBtn.innerHTML = '<i class="fas fa-tag"></i> Keine Kategorie';
            noneBtn.onclick = () => this.moveSelectedRecords(null);
            dropdown.appendChild(noneBtn);
            
            // Kategorien
            this.categories.forEach(cat => {
                const btn = document.createElement('button');
                btn.type = 'button';
                btn.innerHTML = `<i class="fas fa-tag"></i> ${cat.name}`;
                btn.onclick = () => this.moveSelectedRecords(cat.id);
                dropdown.appendChild(btn);
            });
        }
        
        if (galleryDropdown) {
            galleryDropdown.innerHTML = '<button type="button" onclick="App.moveSelectedRecords(null)">Keine Kategorie</button>';
            this.categories.forEach(cat => {
                const btn = document.createElement('button');
                btn.type = 'button';
                btn.innerHTML = `<i class="fas fa-tag"></i> ${cat.name}`;
                btn.onclick = () => this.moveSelectedRecords(cat.id);
                galleryDropdown.appendChild(btn);
            });
        }
    };

    App.moveSelectedRecords = async function(categoryId) {
        const ids = Array.from(this.auswahlIds);
        if (!ids.length) return;

        const category = this.categories.find(c => c.id === categoryId);
        const label = category ? category.name : 'Keine Kategorie';
        
        if (!await this.confirm('Kategorisieren?', `Sollen ${ids.length} Akten als "${label}" kategorisiert werden?`, 'Ja, kategorisieren', 'btn-primary')) return;

        try {
            // Prüfen ob Offline-Akten dabei sind
            const offlineRecords = [];
            const onlineIds = [];
            
            ids.forEach(id => {
                const record = this.records.find(r => r.id === id);
                if (record?.is_offline) {
                    offlineRecords.push(record);
                } else {
                    onlineIds.push(id);
                }
            });
            
            // Offline-Akten aktualisieren
            let offlineUpdated = 0;
            for (const record of offlineRecords) {
                try {
                    record.category_id = categoryId;
                    await OfflineStorage.updatePendingRecord(record.temp_id, record);
                    offlineUpdated++;
                } catch (e) {
                    console.error('Fehler beim Aktualisieren der Offline-Akte:', record.id, e);
                }
            }
            
            // Online-Akten aktualisieren
            let onlineUpdated = 0;
            if (onlineIds.length > 0) {
                await this.apiPost('/categories/move', { record_ids: onlineIds, category_id: categoryId });
                onlineUpdated = onlineIds.length;
            }

            const totalUpdated = offlineUpdated + onlineUpdated;
            this.toast(`${totalUpdated} Akten kategorisiert (${offlineUpdated} offline, ${onlineUpdated} online)`, 'success');

            // Lokale Liste sofort aktualisieren für sofortige Sichtbarkeit
            this.records.forEach(r => {
                if (ids.includes(r.id)) {
                    r.category_id = categoryId;
                }
            });

            // Cache leeren für sofortige Sichtbarkeit der Änderungen
            if (this._recordCardCache) {
                this._recordCardCache.clear();
            }

            this.renderRecords();

            // Auswahl leeren aber Auswahlmodus aktiv lassen
            this.auswahlIds.clear();
            this._aktualisiereAuswahlToolbar();

            // Dropdown schließen
            document.querySelector('.dropdown-bulk-actions .dropdown-content')?.classList.remove('show');

            // Daten neu laden für Konsistenz
            await this._aktualisiereUINachBulkAktion();
        } catch (e) {
            this.toast(e.message, 'error');
        }
    };

    // ── Bulk Reminder Functions ────────────────────────────────
    App.openBulkReminderModal = function() {
        const hasPermission = this.currentUser?.role === 'admin' || this.currentUser?.can_delete_termine;
        if (!hasPermission) {
            this.toast('Keine Berechtigung für diese Aktion', 'error');
            return;
        }

        const ids = Array.from(this.auswahlIds);
        if (!ids.length) {
            this.toast('Keine Akten ausgewählt', 'warning');
            return;
        }

        // Reset form
        document.getElementById('bulkReminderDate').value = '';
        document.getElementById('bulkReminderDateValue').value = '';
        document.getElementById('bulkReminderEndDate').value = '';
        document.getElementById('bulkReminderEndDateValue').value = '';
        App.updateModalDropdownUI('bulkModalRepeatDropdown', '');
        App.updateModalDropdownUI('bulkReminderVisibilityDropdown', 'all');

        document.getElementById('bulkReminderModalOverlay').classList.add('show');
    };

    App.closeBulkReminderModal = function() {
        document.getElementById('bulkReminderModalOverlay').classList.remove('show');
    };

    App.openBulkNoteModal = function() {
        const hasPermission = this.currentUser?.role === 'admin' || this.currentUser?.can_set_note;
        if (!hasPermission) {
            this.toast('Keine Berechtigung für diese Aktion', 'error');
            return;
        }

        const ids = Array.from(this.auswahlIds);
        if (!ids.length) {
            this.toast('Keine Akten ausgewählt', 'warning');
            return;
        }

        // Reset form
        document.getElementById('bulkNoteInput').value = '';

        document.getElementById('bulkNoteModalOverlay').classList.add('show');
    };

    App.closeBulkNoteModal = function() {
        document.getElementById('bulkNoteModalOverlay').classList.remove('show');
    };

    App.saveBulkNote = async function() {
        const ids = Array.from(this.auswahlIds);
        if (!ids.length) return;

        const note = document.getElementById('bulkNoteInput').value || '';

        try {
            // Prüfen ob Offline-Akten dabei sind
            const offlineRecords = [];
            const onlineIds = [];
            
            ids.forEach(id => {
                const record = this.records.find(r => r.id === id);
                if (record?.is_offline) {
                    offlineRecords.push(record);
                } else {
                    onlineIds.push(id);
                }
            });
            
            // Online-Akten aktualisieren (zuerst, damit Fehler erkannt werden)
            let onlineUpdated = 0;
            if (onlineIds.length > 0) {
                const data = await this.apiPost('/records/massen-note', { ids: onlineIds, note: note });
                
                if (!data) {
                    throw new Error('Keine Antwort vom Server');
                }
                
                if (data.error) {
                    throw new Error(data.error);
                }
                
                onlineUpdated = data.updated_count ?? 0;
                
                if (onlineUpdated === 0 && onlineIds.length > 0) {
                    console.warn('Keine Akten wurden aktualisiert, obwohl IDs gesendet wurden');
                }
            }
            
            // Offline-Akten aktualisieren
            let offlineUpdated = 0;
            for (const record of offlineRecords) {
                try {
                    record.hashtags = note;
                    await OfflineStorage.updatePendingRecord(record.temp_id, record);
                    offlineUpdated++;
                } catch (e) {
                    console.error('Fehler beim Aktualisieren der Offline-Akte:', record.id, e);
                }
            }
            
            const totalUpdated = offlineUpdated + onlineUpdated;

            if (totalUpdated > 0) {
                this.toast(`${totalUpdated} Akten aktualisiert (${offlineUpdated} offline, ${onlineUpdated} online)`, 'success');

                this.closeBulkNoteModal();

                // Auswahl leeren aber Auswahlmodus aktiv lassen
                this.auswahlIds.clear();
                this._aktualisiereAuswahlToolbar();

                // Daten neu laden für sofortige Sichtbarkeit der Änderungen
                await this._aktualisiereUINachBulkAktion();
            } else {
                throw new Error('Keine Akten wurden aktualisiert');
            }
        } catch (e) {
            console.error('Fehler beim Speichern des Vermerks:', e);
            this.toast(e.message || 'Fehler beim Speichern des Vermerks', 'error');
        }
    };

    App.saveBulkReminder = async function() {
        const ids = Array.from(this.auswahlIds);
        if (!ids.length) return;

        const reminderDate = document.getElementById('bulkReminderDateValue').value || null;
        const reminderEndDate = document.getElementById('bulkReminderEndDateValue').value || null;
        const reminderRepeat = document.getElementById('bulkReminderRepeat').value || null;
        const reminderAssignedTo = document.getElementById('bulkReminderVisibility').value === 'private' ? this.currentUser.id : null;

        try {
            // Prüfen ob Offline-Akten dabei sind
            const offlineRecords = [];
            const onlineIds = [];
            
            ids.forEach(id => {
                const record = this.records.find(r => r.id === id);
                if (record?.is_offline) {
                    offlineRecords.push(record);
                } else {
                    onlineIds.push(id);
                }
            });
            
            // Offline-Akten aktualisieren
            let offlineUpdated = 0;
            for (const record of offlineRecords) {
                try {
                    record.reminder_date = reminderDate;
                    record.reminder_end_date = reminderEndDate;
                    record.reminder_repeat = reminderRepeat;
                    record.reminder_assigned_to = reminderAssignedTo;
                    await OfflineStorage.updatePendingRecord(record.temp_id, record);
                    offlineUpdated++;
                } catch (e) {
                    console.error('Fehler beim Aktualisieren der Offline-Akte:', record.id, e);
                }
            }
            
            // Online-Akten aktualisieren
            let onlineUpdated = 0;
            if (onlineIds.length > 0) {
                await this.apiPost('/records/massen-termin', { 
                    ids: onlineIds, 
                    reminder_date: reminderDate,
                    reminder_end_date: reminderEndDate,
                    reminder_repeat: reminderRepeat,
                    reminder_assigned_to: reminderAssignedTo
                });
                onlineUpdated = onlineIds.length;
            }
            
            const totalUpdated = offlineUpdated + onlineUpdated;
            this.toast(`${totalUpdated} Termine gesetzt (${offlineUpdated} offline, ${onlineUpdated} online)`, 'success');
            this.closeBulkReminderModal();

            // Auswahl leeren aber Auswahlmodus aktiv lassen
            this.auswahlIds.clear();
            this._aktualisiereAuswahlToolbar();

            // Daten neu laden für sofortige Sichtbarkeit der Änderungen
            await this._aktualisiereUINachBulkAktion();

            this.loadReminders();
            if (this.currentSection === 'dashboard') this.loadDashboard();
            if (this.currentSection === 'dashboard') this.renderCalendarChart();
        } catch (e) {
            this.toast(e.message, 'error');
        }
    };

    // Bulk Erinnerung Functions
    App.openBulkErinnerungModal = async function() {
        const hasPermission = this.currentUser?.role === 'admin' || this.currentUser?.can_delete_erinnerung;
        if (!hasPermission) {
            this.toast('Keine Berechtigung für diese Aktion', 'error');
            return;
        }

        const ids = Array.from(this.auswahlIds);
        if (!ids.length) {
            this.toast('Keine Akten ausgewählt', 'warning');
            return;
        }

        // Reset form
        document.getElementById('bulkErinnerungDate').value = '';
        document.getElementById('bulkErinnerungDateValue').value = '';
        document.getElementById('bulkErinnerungNote').value = '';
        
        // Load users for dropdown (mit Offline-Support)
        try {
            const users = await this.apiGet('/records/users', false);
            const menu = document.getElementById('bulkErinnerungAssignMenu');
            if (menu && users.users) {
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
                
                // Set default to current user
                const dropdownBtn = document.querySelector('#bulkErinnerungAssignDropdown .dropdown-toggle');
                const reminderInput = document.getElementById('bulkErinnerungAssignedTo');
                if (dropdownBtn) {
                    const valueToSet = this.currentUser?.id;
                    reminderInput.value = valueToSet;
                    const selectedBtn = menu.querySelector(`button[data-value="${valueToSet}"]`);
                    if (selectedBtn) {
                        dropdownBtn.innerHTML = selectedBtn.innerHTML;
                        selectedBtn.classList.add('selected');
                    }
                }
            }
        } catch (e) {
            console.error('Fehler beim Laden der Benutzer für Dropdown (Server offline):', e);
            // Offline: Nur aktuellen Benutzer im Dropdown anzeigen
            const menu = document.getElementById('bulkErinnerungAssignMenu');
            if (menu) {
                menu.innerHTML = `
                    <button type="button" data-value="${this.currentUser?.id}">
                        <i class="fas fa-user"></i> <span>${this.escapeHtml(this.currentUser?.username || 'Ich')}</span>
                    </button>
                `;
                
                const dropdownBtn = document.querySelector('#bulkErinnerungAssignDropdown .dropdown-toggle');
                const reminderInput = document.getElementById('bulkErinnerungAssignedTo');
                if (dropdownBtn) {
                    const valueToSet = this.currentUser?.id;
                    reminderInput.value = valueToSet;
                    const selectedBtn = menu.querySelector(`button[data-value="${valueToSet}"]`);
                    if (selectedBtn) {
                        dropdownBtn.innerHTML = selectedBtn.innerHTML;
                        selectedBtn.classList.add('selected');
                    }
                }
            }
        }

        // Reset date picker state
        this.bulkErinnerungDateTimePickerState.currentDate = new Date();
        this.bulkErinnerungDateTimePickerState.selectedDate = null;

        document.getElementById('bulkErinnerungModalOverlay').classList.add('show');
    };

    App.closeBulkErinnerungModal = function() {
        document.getElementById('bulkErinnerungModalOverlay').classList.remove('show');
    };

    App.saveBulkErinnerung = async function(e) {
        if (e) e.preventDefault();
        const ids = Array.from(this.auswahlIds);
        if (!ids.length) return;

        const reminderDate = document.getElementById('bulkErinnerungDateValue').value;
        if (!reminderDate) {
            this.toast('Bitte ein Datum auswählen', 'warning');
            return;
        }

        const assignedTo = document.getElementById('bulkErinnerungAssignedTo').value || null;
        const note = document.getElementById('bulkErinnerungNote').value || null;

        try {
            // Prüfen ob Offline-Akten dabei sind
            const offlineRecords = [];
            const onlineIds = [];
            
            ids.forEach(id => {
                const record = this.records.find(r => r.id === id);
                if (record?.is_offline) {
                    offlineRecords.push(record);
                } else {
                    onlineIds.push(id);
                }
            });
            
            // Offline-Akten aktualisieren - Erinnerungen werden in IndexedDB gespeichert
            let offlineUpdated = 0;
            for (const record of offlineRecords) {
                try {
                    // Erinnerung als Objekt im Record speichern
                    if (!record.erinnerungen) record.erinnerungen = [];
                    record.erinnerungen.push({
                        reminder_date: reminderDate,
                        assigned_to: assignedTo,
                        note: note,
                        completed: 0
                    });
                    await OfflineStorage.updatePendingRecord(record.temp_id, record);
                    offlineUpdated++;
                } catch (e) {
                    console.error('Fehler beim Aktualisieren der Offline-Akte:', record.id, e);
                }
            }
            
            // Online-Akten aktualisieren
            let onlineUpdated = 0;
            if (onlineIds.length > 0) {
                await this.apiPost('/records/massen-erinnerung', { 
                    ids: onlineIds, 
                    reminder_date: reminderDate,
                    assigned_to: assignedTo,
                    note: note
                });
                onlineUpdated = onlineIds.length;
            }
            
            const totalUpdated = offlineUpdated + onlineUpdated;
            this.toast(`${totalUpdated} Erinnerungen gesetzt (${offlineUpdated} offline, ${onlineUpdated} online)`, 'success');
            this.closeBulkErinnerungModal();

            // Auswahl leeren aber Auswahlmodus aktiv lassen
            this.auswahlIds.clear();
            this._aktualisiereAuswahlToolbar();

            // Daten neu laden für sofortige Sichtbarkeit der Änderungen
            await this._aktualisiereUINachBulkAktion();

            this.loadReminders();
            if (this.currentSection === 'dashboard') this.loadDashboard();
        } catch (e) {
            this.toast(e.message, 'error');
        }
    };

    App.deleteSelectedRecordsTermine = async function() {
        const ids = Array.from(this.auswahlIds);
        if (!ids.length) {
            this.toast('Keine Akten ausgewählt', 'warning');
            return;
        }

        const hasPermission = this.currentUser?.role === 'admin' || this.currentUser?.can_set_reminder;
        if (!hasPermission) {
            this.toast('Keine Berechtigung für diese Aktion', 'error');
            return;
        }

        if (!await this.confirm('Termine löschen?', `Sollen alle Kalender-Termine für ${ids.length} Akten gelöscht werden?`, 'Ja, löschen', 'btn-danger')) return;

        try {
            // Prüfen ob Offline-Akten dabei sind
            const offlineRecords = [];
            const onlineIds = [];
            
            ids.forEach(id => {
                const record = this.records.find(r => r.id === id);
                if (record?.is_offline) {
                    offlineRecords.push(record);
                } else {
                    onlineIds.push(id);
                }
            });
            
            // Offline-Akten aktualisieren
            let offlineUpdated = 0;
            for (const record of offlineRecords) {
                try {
                    record.reminder_date = null;
                    record.reminder_end_date = null;
                    record.reminder_repeat = null;
                    record.reminder_assigned_to = null;
                    await OfflineStorage.updatePendingRecord(record.temp_id, record);
                    offlineUpdated++;
                } catch (e) {
                    console.error('Fehler beim Aktualisieren der Offline-Akte:', record.id, e);
                }
            }
            
            // Online-Akten aktualisieren
            let onlineUpdated = 0;
            if (onlineIds.length > 0) {
                await this.apiPost('/records/massen-termin-loeschen', { ids: onlineIds });
                onlineUpdated = onlineIds.length;
            }
            
            const totalUpdated = offlineUpdated + onlineUpdated;
            this.toast(`${totalUpdated} Termine gelöscht (${offlineUpdated} offline, ${onlineUpdated} online)`, 'success');

            // Auswahl leeren aber Auswahlmodus aktiv lassen
            this.auswahlIds.clear();
            this._aktualisiereAuswahlToolbar();

            // Daten neu laden für sofortige Sichtbarkeit der Änderungen
            await this._aktualisiereUINachBulkAktion();

            this.loadReminders();
            if (this.currentSection === 'dashboard') this.loadDashboard();
        } catch (e) {
            this.toast(e.message, 'error');
        }
    };

    App.deleteSelectedRecordsErinnerungn = async function() {
        const ids = Array.from(this.auswahlIds);
        if (!ids.length) {
            this.toast('Keine Akten ausgewählt', 'warning');
            return;
        }

        const hasPermission = this.currentUser?.role === 'admin' || this.currentUser?.can_set_erinnerung;
        if (!hasPermission) {
            this.toast('Keine Berechtigung für diese Aktion', 'error');
            return;
        }

        if (!await this.confirm('Erinnerungn löschen?', `Sollen alle Erinnerungn für ${ids.length} Akten gelöscht werden?`, 'Ja, löschen', 'btn-danger')) return;

        try {
            // Prüfen ob Offline-Akten dabei sind
            const offlineRecords = [];
            const onlineIds = [];
            
            ids.forEach(id => {
                const record = this.records.find(r => r.id === id);
                if (record?.is_offline) {
                    offlineRecords.push(record);
                } else {
                    onlineIds.push(id);
                }
            });
            
            // Offline-Akten aktualisieren
            let offlineUpdated = 0;
            for (const record of offlineRecords) {
                try {
                    record.erinnerungen = [];
                    await OfflineStorage.updatePendingRecord(record.temp_id, record);
                    offlineUpdated++;
                } catch (e) {
                    console.error('Fehler beim Aktualisieren der Offline-Akte:', record.id, e);
                }
            }
            
            // Online-Akten aktualisieren
            let onlineUpdated = 0;
            if (onlineIds.length > 0) {
                await this.apiPost('/records/massen-erinnerung-loeschen', { ids: onlineIds });
                onlineUpdated = onlineIds.length;
            }
            
            const totalUpdated = offlineUpdated + onlineUpdated;
            this.toast(`${totalUpdated} Erinnerungen gelöscht (${offlineUpdated} offline, ${onlineUpdated} online)`, 'success');

            // Auswahl leeren aber Auswahlmodus aktiv lassen
            this.auswahlIds.clear();
            this._aktualisiereAuswahlToolbar();

            // Daten neu laden für sofortige Sichtbarkeit der Änderungen
            await this._aktualisiereUINachBulkAktion();

            this.loadReminders();
            if (this.currentSection === 'dashboard') this.loadDashboard();
        } catch (e) {
            this.toast(e.message, 'error');
        }
    };

    // Wrapper-Funktionen für das neue Dropdown-Menü
    App.bulkReminder = function() {
        this.openBulkReminderModal();
    };

    App.bulkErinnerung = function() {
        this.openBulkErinnerungModal();
    };

    App.bulkDeleteTermin = function() {
        this.deleteSelectedRecordsTermine();
    };

    App.bulkDeleteErinnerung = function() {
        this.deleteSelectedRecordsErinnerungn();
    };

    App.auswahlLoeschen = function() {
        this.loescheAusgewaehlteAkten();
    };

    // Bulk Erinnerung Date Time Picker Functions
    App.openBulkErinnerungDateTimePicker = function() {
        this.bulkErinnerungDateTimePickerState.isOpen = true;
        this.bulkErinnerungDateTimePickerState.currentDate = new Date();
        
        // Parse existing value if any
        const existingValue = document.getElementById('bulkErinnerungDate').value;
        if (existingValue) {
            const parts = existingValue.split('.');
            if (parts.length === 3) {
                const date = new Date(parts[2], parts[1] - 1, parts[0]);
                if (!isNaN(date.getTime())) {
                    this.bulkErinnerungDateTimePickerState.selectedDate = date;
                    this.bulkErinnerungDateTimePickerState.currentDate = new Date(date);
                }
            }
        } else {
            this.bulkErinnerungDateTimePickerState.selectedDate = new Date();
        }
        
        this.renderBulkErinnerungDateTimePicker();
        document.getElementById('bulkErinnerungDateTimePickerModal').classList.add('show');
    };

    App.closeBulkErinnerungDateTimePicker = function() {
        this.bulkErinnerungDateTimePickerState.isOpen = false;
        document.getElementById('bulkErinnerungDateTimePickerModal').classList.remove('show');
    };

    App.renderBulkErinnerungDateTimePicker = function() {
        const d = this.bulkErinnerungDateTimePickerState.currentDate;
        const year = d.getFullYear();
        const month = d.getMonth();
        
        document.getElementById('bulkErinnerungDateTimeMonthYear').textContent = 
            d.toLocaleDateString('de-DE', { month: 'long', year: 'numeric' });
        
        const firstDay = new Date(year, month, 1).getDay();
        const daysInMonth = new Date(year, month + 1, 0).getDate();
        const startOffset = firstDay === 0 ? 6 : firstDay - 1;
        
        let html = '';
        
        ['Mo','Di','Mi','Do','Fr','Sa','So'].forEach(w => {
            html += `<div class="datetime-weekday">${w}</div>`;
        });
        
        for (let i = 0; i < startOffset; i++) {
            html += `<div class="datetime-day disabled"></div>`;
        }
        
        const today = new Date();
        for (let day = 1; day <= daysInMonth; day++) {
            const currentDate = new Date(year, month, day);
            const isToday = day === today.getDate() && month === today.getMonth() && year === today.getFullYear();
            const isSelected = this.bulkErinnerungDateTimePickerState.selectedDate && 
                day === this.bulkErinnerungDateTimePickerState.selectedDate.getDate() && 
                month === this.bulkErinnerungDateTimePickerState.selectedDate.getMonth() && 
                year === this.bulkErinnerungDateTimePickerState.selectedDate.getFullYear();
            
            let classes = 'datetime-day';
            if (isToday) classes += ' today';
            if (isSelected) classes += ' selected';
            
            html += `<div class="${classes}" onclick="App.selectBulkErinnerungDateTimeDate(${year}, ${month}, ${day})">${day}</div>`;
        }
        
        document.getElementById('bulkErinnerungDateTimeCalendarGrid').innerHTML = html;
    };

    App.selectBulkErinnerungDateTimeDate = function(year, month, day) {
        this.bulkErinnerungDateTimePickerState.selectedDate = new Date(year, month, day);
        this.renderBulkErinnerungDateTimePicker();
    };

    App.changeBulkErinnerungDateTimeMonth = function(delta) {
        this.bulkErinnerungDateTimePickerState.currentDate.setMonth(this.bulkErinnerungDateTimePickerState.currentDate.getMonth() + delta);
        this.renderBulkErinnerungDateTimePicker();
    };

    App.setBulkErinnerungDate = function() {
        if (!this.bulkErinnerungDateTimePickerState.selectedDate) {
            this.bulkErinnerungDateTimePickerState.selectedDate = new Date();
        }

        const date = this.bulkErinnerungDateTimePickerState.selectedDate;
        const year = date.getFullYear();
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const day = String(date.getDate()).padStart(2, '0');

        const formattedDate = `${year}-${month}-${day}`;
        const displayStr = `${day}.${month}.${year}`;

        document.getElementById('bulkErinnerungDateValue').value = formattedDate;
        document.getElementById('bulkErinnerungDate').value = displayStr;

        this.closeBulkErinnerungDateTimePicker();
    };

    App.clearBulkErinnerungDate = function() {
        document.getElementById('bulkErinnerungDateValue').value = '';
        document.getElementById('bulkErinnerungDate').value = '';
    };

    // Bulk Date Time Picker Functions
    App.openBulkDateTimePicker = function(type = 'start') {
        this.bulkDateTimePickerState.isOpen = true;
        this.bulkDateTimePickerState.activeType = type;
        this.bulkDateTimePickerState.currentDate = new Date();

        // Parse existing value if any
        const inputId = type === 'start' ? 'bulkReminderDate' : 'bulkReminderEndDate';
        const existingValue = document.getElementById(inputId).value;
        if (existingValue) {
            const parts = existingValue.split('.');
            if (parts.length === 3) {
                const date = new Date(parts[2], parts[1] - 1, parts[0]);
                if (!isNaN(date.getTime())) {
                    this.bulkDateTimePickerState.selectedDate = date;
                    this.bulkDateTimePickerState.currentDate = new Date(date);
                }
            }
        } else {
            this.bulkDateTimePickerState.selectedDate = new Date();
        }

        this.renderBulkDateTimePicker();
        document.getElementById('bulkDateTimePickerModal').classList.add('show');
    };

    App.closeBulkDateTimePicker = function() {
        this.bulkDateTimePickerState.isOpen = false;
        document.getElementById('bulkDateTimePickerModal').classList.remove('show');
    };

    App.renderBulkDateTimePicker = function() {
        const d = this.bulkDateTimePickerState.currentDate;
        const year = d.getFullYear();
        const month = d.getMonth();
        
        document.getElementById('bulkDateTimeMonthYear').textContent = 
            d.toLocaleDateString('de-DE', { month: 'long', year: 'numeric' });
        
        const firstDay = new Date(year, month, 1).getDay();
        const daysInMonth = new Date(year, month + 1, 0).getDate();
        const startOffset = firstDay === 0 ? 6 : firstDay - 1;
        
        let html = '';
        
        ['Mo','Di','Mi','Do','Fr','Sa','So'].forEach(w => {
            html += `<div class="datetime-weekday">${w}</div>`;
        });
        
        for (let i = 0; i < startOffset; i++) {
            html += `<div class="datetime-day disabled"></div>`;
        }
        
        const today = new Date();
        for (let day = 1; day <= daysInMonth; day++) {
            const currentDate = new Date(year, month, day);
            const isToday = day === today.getDate() && month === today.getMonth() && year === today.getFullYear();
            const isSelected = this.bulkDateTimePickerState.selectedDate && 
                day === this.bulkDateTimePickerState.selectedDate.getDate() && 
                month === this.bulkDateTimePickerState.selectedDate.getMonth() && 
                year === this.bulkDateTimePickerState.selectedDate.getFullYear();
            const isPast = currentDate < today && !isToday;
            
            let classes = 'datetime-day';
            if (isToday) classes += ' today';
            if (isSelected) classes += ' selected';
            if (isPast) classes += ' disabled';
            
            html += `<div class="${classes}" ${!isPast ? `onclick="App.selectBulkDateTimeDate(${year}, ${month}, ${day})"` : ''}>${day}</div>`;
        }
        
        document.getElementById('bulkDateTimeCalendarGrid').innerHTML = html;
    };

    App.selectBulkDateTimeDate = function(year, month, day) {
        this.bulkDateTimePickerState.selectedDate = new Date(year, month, day);
        this.renderBulkDateTimePicker();
    };

    App.changeBulkDateTimeMonth = function(delta) {
        this.bulkDateTimePickerState.currentDate.setMonth(this.bulkDateTimePickerState.currentDate.getMonth() + delta);
        this.renderBulkDateTimePicker();
    };

    App.setBulkDateTime = function() {
        if (!this.bulkDateTimePickerState.selectedDate) {
            this.bulkDateTimePickerState.selectedDate = new Date();
        }

        const date = this.bulkDateTimePickerState.selectedDate;
        const year = date.getFullYear();
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const day = String(date.getDate()).padStart(2, '0');

        const formattedDate = `${year}-${month}-${day}`;
        const displayStr = `${day}.${month}.${year}`;

        const isStart = this.bulkDateTimePickerState.activeType === 'start';
        const valId = isStart ? 'bulkReminderDateValue' : 'bulkReminderEndDateValue';
        const displayId = isStart ? 'bulkReminderDate' : 'bulkReminderEndDate';

        document.getElementById(valId).value = formattedDate;
        document.getElementById(displayId).value = displayStr;

        this.closeBulkDateTimePicker();
    };

    App.clearBulkDateTime = function(type = 'start') {
        const isStart = type === 'start';
        const valId = isStart ? 'bulkReminderDateValue' : 'bulkReminderEndDateValue';
        const displayId = isStart ? 'bulkReminderDate' : 'bulkReminderEndDate';
        
        document.getElementById(valId).value = '';
        document.getElementById(displayId).value = '';
    };

    // ── Event Wiring ───────────────────────────────
    App.initMehrfachAuswahl = function() {
        const containers = [
            document.getElementById('recordsList'),
            document.getElementById('calendarReminders'),
            document.getElementById('galleryGrid')
        ].filter(Boolean);

        if (containers.length === 0) return;

        // Start / Ende (nur einmal, da globale Buttons) - prüfen ob bereits initialisiert
        if (!this._auswahlInitialized) {
            // auswahlStartBtn wird bereits über onclick im HTML gesteuert
            document.getElementById('auswahlFertigBtn')?.addEventListener('click', () => this.deaktiviereAuswahlmodus(true));

            // Gallery toolbar buttons
            const galleryAuswahlActionsBtn = document.getElementById('galleryAuswahlActionsBtn');
            const galleryAuswahlActionsDropdown = document.getElementById('galleryAuswahlActionsDropdown');

            if (galleryAuswahlActionsBtn && galleryAuswahlActionsDropdown) {
                const toggleGalleryActionsDropdown = (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    galleryAuswahlActionsDropdown.classList.toggle('show');
                };

                galleryAuswahlActionsBtn.addEventListener('click', toggleGalleryActionsDropdown);
                galleryAuswahlActionsBtn.addEventListener('touchend', toggleGalleryActionsDropdown);

                // Globales Schließen beim Klick außerhalb
                document.addEventListener('click', (e) => {
                    if (!e.target.closest('.dropdown-bulk-actions')) {
                        galleryAuswahlActionsDropdown?.classList.remove('show');
                    }
                });
            }

            // Neues einzelnes Dropdown-Menü für Aktionen (Records)
            const auswahlActionsBtn = document.getElementById('auswahlActionsBtn');
            const auswahlActionsDropdown = document.getElementById('auswahlActionsDropdown');
            
            if (auswahlActionsBtn && auswahlActionsDropdown) {
                const toggleActionsDropdown = (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    auswahlActionsDropdown.classList.toggle('show');
                };
                
                auswahlActionsBtn.addEventListener('click', toggleActionsDropdown);
                auswahlActionsBtn.addEventListener('touchend', toggleActionsDropdown);
                
                // Globales Schließen beim Klick außerhalb
                document.addEventListener('click', (e) => {
                    if (!e.target.closest('.dropdown-bulk-actions')) {
                        auswahlActionsDropdown?.classList.remove('show');
                    }
                });
            }
            
            // Modal- und Form-Handler (bleiben gleich)
            document.getElementById('bulkReminderModalClose')?.addEventListener('click', () => this.closeBulkReminderModal());
            document.getElementById('bulkErinnerungModalClose')?.addEventListener('click', () => this.closeBulkErinnerungModal());
            document.getElementById('bulkErinnerungForm')?.addEventListener('submit', (e) => this.saveBulkErinnerung(e));

            // Bulk Erinnerung Assign Dropdown
            const bulkErinnerungAssignDropdown = document.getElementById('bulkErinnerungAssignDropdown');
            if (bulkErinnerungAssignDropdown) {
                const toggle = bulkErinnerungAssignDropdown.querySelector('.dropdown-toggle');
                const menu = bulkErinnerungAssignDropdown.querySelector('.dropdown-menu');
                if (toggle && menu) {
                    toggle.addEventListener('click', (e) => {
                        e.stopPropagation();
                        menu.classList.toggle('show');
                    });
                    menu.querySelectorAll('button').forEach(btn => {
                        btn.addEventListener('click', (e) => {
                            e.stopPropagation();
                            const value = btn.dataset.value;
                            document.getElementById('bulkErinnerungAssignedTo').value = value;
                            toggle.innerHTML = btn.innerHTML;
                            menu.querySelectorAll('button').forEach(b => b.classList.remove('selected'));
                            btn.classList.add('selected');
                            menu.classList.remove('show');
                        });
                    });
                }
            }

            // Globales Schließen für andere Dropdowns
            document.addEventListener('click', (e) => {
                if (!e.target.closest('#bulkErinnerungAssignDropdown')) {
                    document.querySelectorAll('#bulkErinnerungAssignDropdown .dropdown-menu').forEach(el => {
                        el.classList.remove('show');
                    });
                }
            });

            this._auswahlInitialized = true;
        }

        document.getElementById('auswahlKarteBtn')?.addEventListener('click', () => {
            const ids = Array.from(this.auswahlIds);
            if (!ids.length) {
                this.toast('Keine Akten ausgewählt', 'warning');
                return;
            }
            // Karte laden und anzeigen
            if (typeof this.loadKarte === 'function') {
                this.karteAktiveIds = ids;
                this.showSection('karte');
            } else {
                this.toast('Kartenfunktion nicht verfügbar', 'error');
            }
        });

        containers.forEach(container => {
            // Klick: Desktop/Allgemein
            container.addEventListener('click', (e) => {
                const ocrMatchButton = e.target.closest('.record-search-match');
                if (ocrMatchButton) {
                    e.preventDefault();
                    e.stopPropagation();
                    this.openSearchMatchFromElement(ocrMatchButton);
                    return;
                }

                const id = this._holeAkteIdAusElement(e.target);
                if (!id) return;

                // Klick nach Long-Press unterdrücken (verhindert versehentliches Öffnen)
                if (Date.now() < this._auswahlKlickUnterdrueckenBis) return;

                // Klick auf Indikator: immer Auswahl toggeln, kein Öffnen
                if (e.target.closest('.auswahl-indikator')) {
                    e.preventDefault();
                    e.stopPropagation();
                    e.stopImmediatePropagation();
                    this.umschaltenAkteAuswahl(id);
                    return;
                }

                // Auswahlmodus: Klick toggelt Auswahl
                if (this.auswahlIstAktiv) {
                    e.preventDefault();
                    this.umschaltenAkteAuswahl(id);
                    return;
                }

                // Desktop: Strg/Meta-Klick startet Auswahlmodus
                if (e.ctrlKey || e.metaKey) {
                    e.preventDefault();
                    this.aktiviereAuswahlmodus();
                    this.umschaltenAkteAuswahl(id);
                    return;
                }

                // Normal: Akte öffnen
                this.openRecord(id);
            }, { passive: false });

            // Long-Press: Mobile
            container.addEventListener('pointerdown', (e) => {
                if (e.pointerType !== 'touch') return;
                const id = this._holeAkteIdAusElement(e.target);
                if (!id) return;

                this._auswahlPointerDown = {
                    pointerId: e.pointerId,
                    recordId: id,
                    startX: e.clientX,
                    startY: e.clientY,
                    startZeit: Date.now()
                };

                clearTimeout(this._auswahlLongPressTimer);
                this._auswahlLongPressTimer = setTimeout(() => {
                    // Long-Press erkannt
                    this._auswahlKlickUnterdrueckenBis = Date.now() + 700;
                    this.aktiviereAuswahlmodus();
                    this.umschaltenAkteAuswahl(id);
                }, 450);
            }, { passive: true });

            container.addEventListener('pointermove', (e) => {
                const d = this._auswahlPointerDown;
                if (!d || e.pointerId !== d.pointerId) return;
                const dx = Math.abs(e.clientX - d.startX);
                const dy = Math.abs(e.clientY - d.startY);
                // Beim Scrollen/Wischen: Long-Press abbrechen
                if (dx > 10 || dy > 10) {
                    clearTimeout(this._auswahlLongPressTimer);
                    this._auswahlLongPressTimer = null;
                    this._auswahlPointerDown = null;
                }
            }, { passive: true });

            const pointerEnd = (e) => {
                const d = this._auswahlPointerDown;
                if (!d || e.pointerId !== d.pointerId) return;
                clearTimeout(this._auswahlLongPressTimer);
                this._auswahlLongPressTimer = null;
                this._auswahlPointerDown = null;
            };
            container.addEventListener('pointerup', pointerEnd, { passive: true });
            container.addEventListener('pointercancel', pointerEnd, { passive: true });
        });
    };
})();
