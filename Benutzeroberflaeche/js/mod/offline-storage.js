/**
 * Offline Storage Modul - IndexedDB für offline Akten
 * Ermöglicht Akten-Erstellung ohne Server-Verbindung
 * Robuste Daten-Sicherung gegen Datenverlust
 */

const OfflineStorage = {
    dbName: 'ORDAMA_OfflineDB',
    dbVersion: 3, // Version erhöhen für Backup-Store
    db: null,
    dbInitPromise: null, // Cache für Initialisierung-Promise
    dbReady: false, // Flag für schnellere Checks
    backupKey: 'ordama_offline_backup', // LocalStorage Backup-Key
    indexedDBAvailable: true, // Flag ob IndexedDB verfügbar ist

    // Initialisiert die IndexedDB
    async init() {
        // Wenn bereits initialisiert, direkt zurückgeben
        if (this.dbReady && this.db) return this.db;
        if (this.dbInitPromise) return this.dbInitPromise;
        
        // Wenn IndexedDB bereits als nicht verfügbar markiert wurde, null zurückgeben
        if (!this.indexedDBAvailable) {
            console.warn('⚠️ IndexedDB ist nicht verfügbar, Offline-Storage deaktiviert');
            return null;
        }

        this.dbInitPromise = new Promise((resolve, reject) => {
            try {
                const request = indexedDB.open(this.dbName, this.dbVersion);

                request.onerror = () => {
                    console.error('❌ IndexedDB konnte nicht geöffnet werden:', request.error);
                    this.indexedDBAvailable = false;
                    this.dbReady = false;
                    this.db = null;
                    resolve(null); // Nicht rejecten, sondern null zurückgeben für graceful degradation
                };
                
                request.onblocked = () => {
                    console.warn('⚠️ IndexedDB Öffnen blockiert');
                    this.indexedDBAvailable = false;
                    resolve(null);
                };
                
                request.onsuccess = () => {
                    this.db = request.result;
                    this.dbReady = true;
                    console.log('✅ IndexedDB erfolgreich geöffnet');
                    resolve(this.db);
                };

                request.onupgradeneeded = (event) => {
                    const db = event.target.result;
                    const currentVersion = event.oldVersion;

                    // Store für offline erstellte Akten
                    if (!db.objectStoreNames.contains('pending_records')) {
                        const store = db.createObjectStore('pending_records', { keyPath: 'id', autoIncrement: true });
                        store.createIndex('created_at', 'created_at', { unique: false });
                        store.createIndex('synced', 'synced', { unique: false });
                    }

                    // Store für Synchronisations-Status
                    if (!db.objectStoreNames.contains('sync_status')) {
                        const statusStore = db.createObjectStore('sync_status', { keyPath: 'key' });
                    }

                    // Store für offline Dateien (neu in Version 2)
                    if (!db.objectStoreNames.contains('pending_files')) {
                        const fileStore = db.createObjectStore('pending_files', { keyPath: 'id', autoIncrement: true });
                        fileStore.createIndex('record_id', 'record_id', { unique: false });
                        fileStore.createIndex('synced', 'synced', { unique: false });
                    }

                    // Store für Backup-Daten (neu in Version 3)
                    if (!db.objectStoreNames.contains('backup_data')) {
                        const backupStore = db.createObjectStore('backup_data', { keyPath: 'id', autoIncrement: true });
                        backupStore.createIndex('timestamp', 'timestamp', { unique: false });
                    }
                };
            } catch (e) {
                console.error('❌ IndexedDB nicht verfügbar:', e);
                this.indexedDBAvailable = false;
                this.dbReady = false;
                this.db = null;
                resolve(null);
            }
        });

        return this.dbInitPromise;
    },

    // Speichert eine offline erstellte Akte
    async savePendingRecord(recordData) {
        // Wenn IndexedDB nicht verfügbar, nur LocalStorage Backup verwenden
        if (!this.indexedDBAvailable) {
            console.warn('⚠️ IndexedDB nicht verfügbar, nur LocalStorage Backup');
            this.saveToLocalStorageBackup(recordData);
            throw new Error('Offline-Speicher nicht verfügbar');
        }
        
        // Schnelle Initialisierung mit Timeout
        if (!this.db) {
            try {
                await Promise.race([
                    this.init(),
                    new Promise((_, reject) => setTimeout(() => reject(new Error('Timeout')), 1000))
                ]);
            } catch (e) {
                console.error('❌ IndexedDB Initialisierung fehlgeschlagen:', e);
                // Fallback zu LocalStorage Backup
                this.saveToLocalStorageBackup(recordData);
                throw new Error('Offline-Speicher nicht verfügbar, Daten in LocalStorage gesichert');
            }
        }
        
        // Wenn immer noch keine DB, nur LocalStorage Backup
        if (!this.db) {
            this.saveToLocalStorageBackup(recordData);
            throw new Error('Offline-Speicher nicht verfügbar');
        }

        return new Promise((resolve, reject) => {
            try {
                const transaction = this.db.transaction(['pending_records'], 'readwrite');
                const store = transaction.objectStore('pending_records');

                // Nur essentielle Daten speichern für Performance
                const record = {
                    title: recordData.title,
                    address: recordData.address,
                    content: recordData.content,
                    hashtags: recordData.hashtags,
                    status: recordData.status,
                    border_color: recordData.border_color,
                    category_id: recordData.category_id,
                    reminder_date: recordData.reminder_date,
                    reminder_end_date: recordData.reminder_end_date,
                    reminder_repeat: recordData.reminder_repeat,
                    reminder_assigned_to: recordData.reminder_assigned_to,
                    pending_reminder: recordData.pending_reminder,
                    user_id: recordData.user_id,
                    user_name: recordData.user_name,
                    temp_id: recordData.temp_id,
                    number: recordData.number,
                    created_at: new Date().toISOString(),
                    synced: false,
                    sync_attempts: 0
                };

                console.log('💾 Speichere offline Akte:', record.title);
                const request = store.add(record);

                request.onsuccess = async () => {
                    console.log('✅ Offline Akte gespeichert mit ID:', request.result);
                    // Automatisches Backup nach erfolgreicher Speicherung
                    await this.createBackup();
                    resolve(request.result);
                };

                request.onerror = () => {
                    console.error('❌ Fehler beim Speichern der offline Akte:', request.error);
                    // Fallback zu LocalStorage Backup
                    this.saveToLocalStorageBackup(recordData);
                    reject(request.error);
                };

                // Timeout für die Transaktion
                setTimeout(() => {
                    if (request.readyState !== 'done') {
                        this.saveToLocalStorageBackup(recordData);
                        reject(new Error('IndexedDB Timeout, Daten in LocalStorage gesichert'));
                    }
                }, 500);
            } catch (e) {
                console.error('❌ Fehler bei IndexedDB Transaktion:', e);
                this.saveToLocalStorageBackup(recordData);
                reject(e);
            }
        });
    },

    // Speichert eine offline Datei
    async savePendingFile(fileData) {
        if (!this.db) await this.init();

        return new Promise((resolve, reject) => {
            const transaction = this.db.transaction(['pending_files'], 'readwrite');
            const store = transaction.objectStore('pending_files');

            const file = {
                ...fileData,
                created_at: new Date().toISOString(),
                synced: false,
                sync_attempts: 0
            };

            console.log('Speichere offline Datei:', file.filename);
            const request = store.add(file);
            request.onsuccess = () => {
                console.log('✅ Offline Datei gespeichert mit ID:', request.result);
                resolve(request.result);
            };
            request.onerror = () => {
                console.error('❌ Fehler beim Speichern der offline Datei:', request.error);
                reject(request.error);
            };
        });
    },

    // Holt alle offline erstellten, nicht synchronisierten Akten
    async getPendingRecords() {
        if (!this.db) await this.init();

        return new Promise((resolve, reject) => {
            const transaction = this.db.transaction(['pending_records'], 'readonly');
            const store = transaction.objectStore('pending_records');
            
            // Alle Akten holen und im JavaScript filtern
            const request = store.getAll();

            request.onsuccess = () => {
                const allRecords = request.result;
                // Nur nicht synchronisierte Akten zurückgeben
                const pendingRecords = allRecords.filter(record => !record.synced);
                console.log(`Gefundene Records: ${allRecords.length}, Davon pending: ${pendingRecords.length}`);
                resolve(pendingRecords);
            };
            request.onerror = () => reject(request.error);
        });
    },

    // Holt alle offline Dateien
    async getPendingFiles() {
        if (!this.db) await this.init();

        return new Promise((resolve, reject) => {
            const transaction = this.db.transaction(['pending_files'], 'readonly');
            const store = transaction.objectStore('pending_files');
            
            const request = store.getAll();

            request.onsuccess = () => {
                const allFiles = request.result;
                const pendingFiles = allFiles.filter(file => !file.synced);
                console.log(`Gefundene Dateien: ${allFiles.length}, Davon pending: ${pendingFiles.length}`);
                resolve(pendingFiles);
            };
            request.onerror = () => reject(request.error);
        });
    },

    // Markiert eine Akte als synchronisiert
    async markAsSynced(recordId) {
        if (!this.db) await this.init();

        return new Promise((resolve, reject) => {
            const transaction = this.db.transaction(['pending_records'], 'readwrite');
            const store = transaction.objectStore('pending_records');

            const request = store.get(recordId);
            request.onsuccess = () => {
                const record = request.result;
                if (record) {
                    record.synced = true;
                    record.synced_at = new Date().toISOString();
                    const updateRequest = store.put(record);
                    updateRequest.onsuccess = () => resolve();
                    updateRequest.onerror = () => reject(updateRequest.error);
                } else {
                    resolve();
                }
            };
            request.onerror = () => reject(request.error);
        });
    },

    // Markiert eine Akte als nicht synchronisiert (für Retry nach Fehler)
    async markAsUnsynced(recordId) {
        if (!this.db) await this.init();

        return new Promise((resolve, reject) => {
            const transaction = this.db.transaction(['pending_records'], 'readwrite');
            const store = transaction.objectStore('pending_records');

            const request = store.get(recordId);
            request.onsuccess = () => {
                const record = request.result;
                if (record) {
                    record.synced = false;
                    record.sync_attempts = (record.sync_attempts || 0) + 1;
                    const updateRequest = store.put(record);
                    updateRequest.onsuccess = () => resolve();
                    updateRequest.onerror = () => reject(updateRequest.error);
                } else {
                    resolve();
                }
            };
            request.onerror = () => reject(request.error);
        });
    },

    // Markiert eine Datei als synchronisiert
    async markFileAsSynced(fileId) {
        if (!this.db) await this.init();

        return new Promise((resolve, reject) => {
            const transaction = this.db.transaction(['pending_files'], 'readwrite');
            const store = transaction.objectStore('pending_files');

            const request = store.get(fileId);
            request.onsuccess = () => {
                const file = request.result;
                if (file) {
                    file.synced = true;
                    file.synced_at = new Date().toISOString();
                    const updateRequest = store.put(file);
                    updateRequest.onsuccess = () => resolve();
                    updateRequest.onerror = () => reject(updateRequest.error);
                } else {
                    resolve();
                }
            };
            request.onerror = () => reject(request.error);
        });
    },

    // Löscht eine synchronisierte Akte aus dem Offline-Storage
    async deleteSyncedRecord(recordId) {
        if (!this.db) await this.init();

        return new Promise((resolve, reject) => {
            const transaction = this.db.transaction(['pending_records'], 'readwrite');
            const store = transaction.objectStore('pending_records');
            const request = store.delete(recordId);

            request.onsuccess = () => resolve();
            request.onerror = () => reject(request.error);
        });
    },

    // Löscht eine synchronisierte Datei aus dem Offline-Storage
    async deleteSyncedFile(fileId) {
        if (!this.db) await this.init();

        return new Promise((resolve, reject) => {
            const transaction = this.db.transaction(['pending_files'], 'readwrite');
            const store = transaction.objectStore('pending_files');
            const request = store.delete(fileId);

            request.onsuccess = () => resolve();
            request.onerror = () => reject(request.error);
        });
    },

    // Aktualisiert eine Offline-Akte
    async updatePendingRecord(recordId, updateData) {
        if (!this.db) await this.init();

        console.log('🔍 updatePendingRecord aufgerufen mit recordId:', recordId);
        console.log('🔍 recordId Typ:', typeof recordId);
        console.log('🔍 recordId ist undefined:', recordId === undefined);
        console.log('🔍 recordId ist null:', recordId === null);
        console.log('🔍 updateData:', updateData);

        if (!recordId) {
            console.error('❌ recordId ist undefined oder null');
            throw new Error('recordId ist undefined oder null');
        }

        // Immer über temp_id suchen, da dies die eindeutige ID ist
        console.log('🔍 Suche Record über temp_id:', recordId);
        return new Promise((resolve, reject) => {
            const transaction = this.db.transaction(['pending_records'], 'readwrite');
            const store = transaction.objectStore('pending_records');
            
            // Alle Records holen und nach temp_id suchen
            const getAllRequest = store.getAll();
            getAllRequest.onsuccess = () => {
                const allRecords = getAllRequest.result;
                console.log('🔍 Alle Records in IndexedDB:', allRecords);
                const record = allRecords.find(r => r.temp_id === recordId);
                
                if (record) {
                    console.log('✅ Record über temp_id gefunden:', record.id);
                    // Aktualisiere die Felder
                    Object.assign(record, updateData);
                    record.updated_at = new Date().toISOString();
                    const updateRequest = store.put(record);
                    updateRequest.onsuccess = () => {
                        console.log('✅ Offline-Akte aktualisiert:', record.id);
                        resolve();
                    };
                    updateRequest.onerror = () => reject(updateRequest.error);
                } else {
                    console.error('❌ Record nicht gefunden mit temp_id:', recordId);
                    console.error('❌ Verfügbare temp_ids:', allRecords.map(r => r.temp_id));
                    reject(new Error('Record nicht gefunden'));
                }
            };
            getAllRequest.onerror = () => reject(getAllRequest.error);
        });
    },

    // Löscht eine Offline-Akte
    async deletePendingRecord(recordId) {
        if (!this.db) await this.init();

        console.log('🔍 deletePendingRecord aufgerufen mit recordId:', recordId);
        console.log('🔍 recordId Typ:', typeof recordId);

        // Suche zuerst nach temp_id, da dies die eindeutige ID ist
        return new Promise((resolve, reject) => {
            const transaction = this.db.transaction(['pending_records'], 'readwrite');
            const store = transaction.objectStore('pending_records');
            
            // Alle Records holen und nach temp_id suchen
            const getAllRequest = store.getAll();
            getAllRequest.onsuccess = () => {
                const allRecords = getAllRequest.result;
                console.log('🔍 Alle Records in IndexedDB:', allRecords);
                const record = allRecords.find(r => r.temp_id === recordId);
                
                if (record) {
                    console.log('✅ Record über temp_id gefunden, lösche mit IndexedDB ID:', record.id);
                    const deleteRequest = store.delete(record.id);
                    deleteRequest.onsuccess = () => {
                        console.log('✅ Offline-Akte gelöscht:', recordId);
                        resolve();
                    };
                    deleteRequest.onerror = () => reject(deleteRequest.error);
                } else {
                    // Wenn nicht über temp_id gefunden, versuche es direkt mit der ID (für Kompatibilität)
                    console.log('⚠️ Record nicht über temp_id gefunden, versuche direkte Löschung mit:', recordId);
                    const deleteRequest = store.delete(recordId);
                    deleteRequest.onsuccess = () => {
                        console.log('✅ Offline-Akte gelöscht (direkt):', recordId);
                        resolve();
                    };
                    deleteRequest.onerror = () => reject(deleteRequest.error);
                }
            };
            getAllRequest.onerror = () => reject(getAllRequest.error);
        });
    },

    // Holt die Anzahl der ausstehenden Synchronisationen
    async getPendingCount() {
        // Wenn IndexedDB nicht verfügbar, 0 zurückgeben
        if (!this.indexedDBAvailable || !this.db) {
            return 0;
        }
        
        try {
            await this.init();
            if (!this.db) return 0;
        } catch (e) {
            console.warn('⚠️ IndexedDB Initialisierung fehlgeschlagen:', e);
            return 0;
        }

        return new Promise((resolve, reject) => {
            try {
                const transaction = this.db.transaction(['pending_records', 'pending_files'], 'readonly');
                const recordStore = transaction.objectStore('pending_records');
                const fileStore = transaction.objectStore('pending_files');
                
                let recordCount = 0;
                let fileCount = 0;
                let completed = 0;

                recordStore.getAll().onsuccess = (e) => {
                    const records = e.target.result;
                    recordCount = records.filter(r => !r.synced).length;
                    completed++;
                    if (completed === 2) resolve(recordCount + fileCount);
                };

                fileStore.getAll().onsuccess = (e) => {
                    const files = e.target.result;
                    fileCount = files.filter(f => !f.synced).length;
                    completed++;
                    if (completed === 2) resolve(recordCount + fileCount);
                };

                transaction.onerror = () => {
                    console.warn('⚠️ IndexedDB Transaktion fehlgeschlagen');
                    resolve(0);
                };
            } catch (e) {
                console.warn('⚠️ getPendingCount fehlgeschlagen:', e);
                resolve(0);
            }
        });
    },

    // Speichert Synchronisations-Status
    async setSyncStatus(key, value) {
        if (!this.db) await this.init();

        return new Promise((resolve, reject) => {
            const transaction = this.db.transaction(['sync_status'], 'readwrite');
            const store = transaction.objectStore('sync_status');

            const request = store.put({ key, value, updated_at: new Date().toISOString() });
            request.onsuccess = () => resolve();
            request.onerror = () => reject(request.error);
        });
    },

    // Holt Synchronisations-Status
    async getSyncStatus(key) {
        if (!this.db) await this.init();

        return new Promise((resolve, reject) => {
            const transaction = this.db.transaction(['sync_status'], 'readonly');
            const store = transaction.objectStore('sync_status');
            const request = store.get(key);

            request.onsuccess = () => resolve(request.result ? request.result.value : null);
            request.onerror = () => reject(request.error);
        });
    },

    // Prüft ob Online und Server erreichbar
    async isOnline() {
        // Manueller Offline-Modus hat Priorität
        if (window.App && window.App.manualOfflineMode) {
            console.log('🔒 Manueller Offline-Modus aktiv - Verbindungsprüfung übersprungen');
            return false;
        }

        if (!navigator.onLine) {
            console.log('❌ Offline: navigator.onLine = false');
            return false;
        }

        try {
            // Prüfen ob Server erreichbar ist
            console.log('🔍 Prüfe Server-Verbindung...');
            const response = await fetch('/api/health', {
                method: 'GET',
                cache: 'no-cache',
                signal: AbortSignal.timeout(5000) // 5 Sekunden Timeout
            });
            const isOk = response.ok;
            console.log(`📡 Server-Verbindung: ${isOk ? '✅ OK' : '❌ FAILED'} (Status: ${response.status})`);
            return isOk;
        } catch (e) {
            console.log('❌ Server nicht erreichbar:', e.message);
            return false;
        }
    },

    // Erstellt ein Backup aller Offline-Daten
    async createBackup() {
        if (!this.db) await this.init();

        try {
            const pendingRecords = await this.getPendingRecords();
            const pendingFiles = await this.getPendingFiles();

            const backupData = {
                timestamp: new Date().toISOString(),
                records: pendingRecords,
                files: pendingFiles,
                version: this.dbVersion
            };

            // Speichern in IndexedDB Backup-Store
            const transaction = this.db.transaction(['backup_data'], 'readwrite');
            const store = transaction.objectStore('backup_data');
            const request = store.add(backupData);

            await new Promise((resolve, reject) => {
                request.onsuccess = () => resolve();
                request.onerror = () => reject(request.error);
            });

            // Auch in LocalStorage speichern als doppelte Sicherung
            localStorage.setItem(this.backupKey, JSON.stringify(backupData));

            console.log('💾 Backup erstellt:', backupData.records.length, 'Akten,', backupData.files.length, 'Dateien');
            return true;
        } catch (e) {
            console.error('❌ Backup-Erstellung fehlgeschlagen:', e);
            return false;
        }
    },

    // Speichert Daten in LocalStorage als Fallback
    saveToLocalStorageBackup(recordData) {
        try {
            let backupData = JSON.parse(localStorage.getItem(this.backupKey) || '{"records":[],"files":[],"timestamp":"","version":1}');
            backupData.records.push({
                ...recordData,
                created_at: new Date().toISOString(),
                synced: false,
                sync_attempts: 0
            });
            backupData.timestamp = new Date().toISOString();
            localStorage.setItem(this.backupKey, JSON.stringify(backupData));
            console.log('💾 LocalStorage Backup erstellt für:', recordData.title);
        } catch (e) {
            console.error('❌ LocalStorage Backup fehlgeschlagen:', e);
        }
    },

    // Stellt Daten aus Backup wieder her
    async restoreFromBackup() {
        try {
            // Zuerst IndexedDB Backup prüfen
            if (this.db) {
                const transaction = this.db.transaction(['backup_data'], 'readonly');
                const store = transaction.objectStore('backup_data');
                const request = store.getAll();

                const backups = await new Promise((resolve, reject) => {
                    request.onsuccess = () => resolve(request.result);
                    request.onerror = () => reject(request.error);
                });

                if (backups && backups.length > 0) {
                    const latestBackup = backups[backups.length - 1];
                    console.log('📦 Wiederherstellung aus IndexedDB Backup:', latestBackup.timestamp);
                    return latestBackup;
                }
            }

            // Fallback zu LocalStorage Backup
            const localStorageBackup = localStorage.getItem(this.backupKey);
            if (localStorageBackup) {
                const backupData = JSON.parse(localStorageBackup);
                console.log('📦 Wiederherstellung aus LocalStorage Backup:', backupData.timestamp);
                return backupData;
            }

            return null;
        } catch (e) {
            console.error('❌ Backup-Wiederherstellung fehlgeschlagen:', e);
            return null;
        }
    },

    // Exportiert Offline-Daten als JSON-Datei
    async exportOfflineData() {
        try {
            const pendingRecords = await this.getPendingRecords();
            const pendingFiles = await this.getPendingFiles();

            const exportData = {
                timestamp: new Date().toISOString(),
                records: pendingRecords,
                files: pendingFiles,
                version: this.dbVersion
            };

            const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' });
            const url = URL.createObjectURL(blob);

            const a = document.createElement('a');
            a.href = url;
            a.download = `ordama_offline_backup_${new Date().toISOString().split('T')[0]}.json`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);

            console.log('📤 Offline-Daten exportiert');
            return true;
        } catch (e) {
            console.error('❌ Export fehlgeschlagen:', e);
            return false;
        }
    },

    // Importiert Offline-Daten aus JSON-Datei
    async importOfflineData(file) {
        try {
            const text = await file.text();
            const importData = JSON.parse(text);

            if (importData.records && importData.records.length > 0) {
                for (const record of importData.records) {
                    await this.savePendingRecord(record);
                }
            }

            if (importData.files && importData.files.length > 0) {
                for (const fileData of importData.files) {
                    await this.savePendingFile(fileData);
                }
            }

            console.log('📥 Offline-Daten importiert:', importData.records.length, 'Akten,', importData.files.length, 'Dateien');
            return true;
        } catch (e) {
            console.error('❌ Import fehlgeschlagen:', e);
            return false;
        }
    },

    // Synchrone Prüfung für schnelle UI-Updates
    isOnlineSync() {
        return navigator.onLine;
    }
};

// Event Listener für Online/Offline Status
window.addEventListener('online', async () => {
    console.log('🌐 Netzwerk wiederhergestellt - Prüfe Server-Verbindung...');
    if (window.App && window.App.updateOfflineIndicator) {
        await window.App.updateOfflineIndicator();
        // Prüfe ob Server wirklich erreichbar ist
        const isOnline = await OfflineStorage.isOnline();
        console.log('Server-Verbindungsstatus:', isOnline);
        if (isOnline && window.App.syncPendingRecords) {
            console.log('Starte automatische Synchronisation...');
            window.App.syncPendingRecords();
        } else {
            console.log('Server noch nicht erreichbar, warte auf manuelle Sync');
        }
    }
});

window.addEventListener('offline', () => {
    console.log('📡 Netzwerk verloren - Offline-Modus aktiv');
    if (window.App && window.App.updateOfflineIndicator) {
        window.App.updateOfflineIndicator();
    }
});
