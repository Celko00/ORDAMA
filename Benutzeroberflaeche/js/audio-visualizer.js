/**
 * ORDAMA - Dokumentenmanagement-System
 * Copyright (C) 2026 Marcel Kohl
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program.  If not, see <https://www.gnu.org/licenses/>.
 *
 * Pegelebalken für Audio-Player (Web Audio Analyser).
 * Ersetzt das Musik-Icon durch Balken, die mit dem Pegel mitlaufen.
 */
(function (global) {
    function createBars(container, barCount, className) {
        const viz = document.createElement('div');
        viz.className = className;
        viz.setAttribute('aria-hidden', 'true');
        const bars = [];
        for (let i = 0; i < barCount; i++) {
            const bar = document.createElement('span');
            bar.className = className + '-bar';
            bar.style.transform = 'scaleY(0.15)';
            bar.style.animationDelay = (i % 8) * 0.08 + 's';
            viz.appendChild(bar);
            bars.push(bar);
        }
        container.appendChild(viz);
        return { viz, bars };
    }

    function pickLevel(data, barIndex, barCount) {
        // Mittlere Frequenzen wirken musikalischer als reine Bass-/Höhen-Bins
        const usable = Math.max(1, Math.floor(data.length * 0.55));
        const start = Math.floor((barIndex / barCount) * usable);
        const end = Math.max(start + 1, Math.floor(((barIndex + 1) / barCount) * usable));
        let sum = 0;
        for (let i = start; i < end; i++) sum += data[i];
        return (sum / (end - start)) / 255;
    }

    /**
     * @param {HTMLElement} container – Platzhalter (z. B. Icon-Slot)
     * @param {HTMLAudioElement} audio
     * @param {{ barCount?: number, className?: string }} [options]
     * @returns {{ start: Function, stop: Function, destroy: Function, el: HTMLElement }}
     */
    function attach(container, audio, options) {
        options = options || {};
        const barCount = options.barCount || 12;
        const className = options.className || 'audio-viz';

        container.innerHTML = '';
        const { viz, bars } = createBars(container, barCount, className);

        let ctx = null;
        let analyser = null;
        let rafId = null;
        let data = null;
        let useFallback = false;

        function ensureGraph() {
            if (analyser) return true;
            if (audio._ordamaVizSource) {
                analyser = audio._ordamaVizAnalyser;
                ctx = audio._ordamaVizCtx;
                data = new Uint8Array(analyser.frequencyBinCount);
                return true;
            }
            const AC = global.AudioContext || global.webkitAudioContext;
            if (!AC) {
                useFallback = true;
                return false;
            }
            try {
                ctx = new AC();
                analyser = ctx.createAnalyser();
                analyser.fftSize = 128;
                analyser.smoothingTimeConstant = 0.72;
                const source = ctx.createMediaElementSource(audio);
                source.connect(analyser);
                analyser.connect(ctx.destination);
                data = new Uint8Array(analyser.frequencyBinCount);
                audio._ordamaVizSource = source;
                audio._ordamaVizAnalyser = analyser;
                audio._ordamaVizCtx = ctx;
                return true;
            } catch (err) {
                useFallback = true;
                return false;
            }
        }

        function settle() {
            bars.forEach(function (bar) {
                bar.style.transform = 'scaleY(0.15)';
            });
        }

        function tick() {
            if (!analyser) return;
            analyser.getByteFrequencyData(data);
            bars.forEach(function (bar, i) {
                const level = pickLevel(data, i, bars.length);
                const scale = Math.max(0.15, Math.min(1, level * 1.35));
                bar.style.transform = 'scaleY(' + scale + ')';
            });
            rafId = requestAnimationFrame(tick);
        }

        function start() {
            viz.classList.add('is-playing');
            if (!ensureGraph()) {
                viz.classList.add('is-fallback');
                return;
            }
            viz.classList.remove('is-fallback');
            if (ctx && ctx.state === 'suspended') {
                ctx.resume().catch(function () {});
            }
            if (!rafId) tick();
        }

        function stop() {
            viz.classList.remove('is-playing', 'is-fallback');
            if (rafId) {
                cancelAnimationFrame(rafId);
                rafId = null;
            }
            settle();
        }

        function destroy() {
            stop();
            viz.remove();
        }

        return { start: start, stop: stop, destroy: destroy, el: viz };
    }

    global.AudioVisualizer = { attach: attach };
})(typeof window !== 'undefined' ? window : this);
