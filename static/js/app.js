const { createApp, ref, computed, onMounted, watch } = Vue;

function getOrCreateBrowserId() {
    const key = 'realtyvision_browser_id';
    let id = localStorage.getItem(key);
    if (!id) {
        id = crypto.randomUUID();
        localStorage.setItem(key, id);
    }
    return id;
}

const MODE_LABELS = {
    full: 'AI-оцінка повна',
    full_with_cached_prices: 'Ціни з кешу',
    degraded: 'AI обмежений',
    offline: 'Без AI',
    checking: 'Перевірка...',
};

const SOURCE_NAMES = {
    domria_live: 'DOM.RIA',
    cache: 'DOM.RIA (кеш)',
    cache_stale: 'DOM.RIA (застарілий кеш)',
    fallback: 'статичний довідник',
};

const PRIORITY_UA = { high: 'Пріоритет', medium: 'Середній', low: 'Низький' };

createApp({
    setup() {
        // ── Core state ──────────────────────────────────────────────────────
        const currentPage = ref('evaluate');
        const browserId = ref(getOrCreateBrowserId());
        const currentMode = ref('checking');
        const regions = ref([]);
        const currentYear = new Date().getFullYear();

        // ── Auth ────────────────────────────────────────────────────────────
        const user = ref(null);
        const showAuthModal = ref(false);
        const authTab = ref('login');
        const authForm = ref({ email: '', name: '', password: '', confirm: '' });
        const authLoading = ref(false);
        const authError = ref('');

        // ── Evaluate form ───────────────────────────────────────────────────
        const form = ref({
            photos: [],
            photoPreviews: [],
            stateId: null,
            cityId: null,
            cities: [],
            realtyType: 'apartment',
            roomsCount: 2,
            floor: null,
            totalFloors: null,
            yearBuilt: null,
            userArea: null,
            userDescription: '',
        });

        const isDragging = ref(false);
        const isLoading = ref(false);
        const evaluation = ref(null);
        const savedEvalId = ref(null);
        const photoIds = ref([]);
        const evalError = ref(null);
        const isSaved = ref(false);

        const loadingSteps = ref([
            { id: 'upload', label: 'Фото завантажено', done: false, active: false },
            { id: 'vision', label: 'Аналіз фото через AI...', done: false, active: false },
            { id: 'prices', label: 'Отримання ринкових цін...', done: false, active: false },
            { id: 'calc', label: 'Розрахунок коригувань...', done: false, active: false },
            { id: 'explain', label: 'Генерація пояснення...', done: false, active: false },
        ]);
        let progressTimer = null;

        // ── Renovation ──────────────────────────────────────────────────────
        const renovationPlan = ref(null);
        const renovationLoading = ref(false);

        // ── History ─────────────────────────────────────────────────────────
        const history = ref([]);
        const historyTotal = ref(0);
        const historyLoading = ref(false);
        const selectedItem = ref(null);

        const historyFilters = ref({
            realty_type: '',
            state_id: null,
            price_min: null,
            price_max: null,
            date_from: '',
            date_to: '',
            condition_min: null,
            sort: 'date_desc',
            page: 1,
            per_page: 20,
        });

        // ── Compare ─────────────────────────────────────────────────────────
        const compareIds = ref([]);
        const compareData = ref(null);
        const compareLoading = ref(false);

        // ── Analytics ───────────────────────────────────────────────────────
        const analyticsFilters = ref({
            state_id: null,
            city_id: null,
            realty_type: 'apartment',
            rooms_count: 2,
        });
        const analyticsData = ref([]);
        const analyticsSummary = ref(null);
        const analyticsLoading = ref(false);
        let priceChart = null;

        // ── Computed ────────────────────────────────────────────────────────
        const modeLabel = computed(() => MODE_LABELS[currentMode.value] || 'Перевірка...');
        const canSubmit = computed(() =>
            form.value.photos.length > 0 &&
            form.value.stateId !== null &&
            form.value.cityId !== null
        );
        const historyPages = computed(() =>
            Math.ceil(historyTotal.value / historyFilters.value.per_page)
        );
        const compareSelected = computed(() => compareIds.value.length);

        // ── Auth ────────────────────────────────────────────────────────────
        async function checkMe() {
            try {
                const r = await fetch('/api/auth/me');
                const data = await r.json();
                user.value = data.user || null;
            } catch { user.value = null; }
        }

        function openAuth(tab = 'login') {
            authTab.value = tab;
            authError.value = '';
            authForm.value = { email: '', name: '', password: '', confirm: '' };
            showAuthModal.value = true;
        }

        async function submitAuth() {
            authError.value = '';
            if (authTab.value === 'register' && authForm.value.password !== authForm.value.confirm) {
                authError.value = 'Паролі не збігаються';
                return;
            }
            authLoading.value = true;
            const endpoint = authTab.value === 'login' ? '/api/auth/login' : '/api/auth/register';
            const body = {
                email: authForm.value.email,
                password: authForm.value.password,
                ...(authTab.value === 'register' ? { name: authForm.value.name } : {}),
            };
            try {
                const resp = await fetch(endpoint, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body),
                });
                const data = await resp.json();
                if (!resp.ok) {
                    authError.value = data.error || 'Помилка авторизації';
                } else {
                    user.value = data.user;
                    showAuthModal.value = false;
                }
            } catch {
                authError.value = 'Помилка мережі';
            } finally {
                authLoading.value = false;
            }
        }

        async function logout() {
            await fetch('/api/auth/logout', { method: 'POST' });
            user.value = null;
            history.value = [];
            historyTotal.value = 0;
            compareIds.value = [];
            compareData.value = null;
            if (currentPage.value !== 'evaluate') {
                currentPage.value = 'evaluate';
            }
        }

        // ── Health & Regions ────────────────────────────────────────────────
        async function checkHealth() {
            try {
                const r = await fetch('/api/health');
                const data = await r.json();
                currentMode.value = data.current_mode || 'offline';
            } catch {
                currentMode.value = 'offline';
            }
        }

        async function loadRegions() {
            try {
                const r = await fetch('/api/regions');
                regions.value = await r.json();
            } catch (e) {
                console.error('Помилка завантаження регіонів:', e);
            }
        }

        async function loadCities() {
            form.value.cityId = null;
            form.value.cities = [];
            if (!form.value.stateId) return;
            try {
                const r = await fetch(`/api/cities/${form.value.stateId}`);
                form.value.cities = await r.json();
                if (form.value.cities.length > 0) {
                    form.value.cityId = form.value.cities[0].city_id;
                }
            } catch (e) {
                console.error('Помилка завантаження міст:', e);
            }
        }

        // ── Photo handling ──────────────────────────────────────────────────
        function onFileSelect(e) {
            addFiles(Array.from(e.target.files));
            e.target.value = '';
        }

        function onDrop(e) {
            isDragging.value = false;
            addFiles(Array.from(e.dataTransfer.files));
        }

        function addFiles(files) {
            const allowed = ['image/jpeg', 'image/png', 'image/webp'];
            for (const file of files) {
                if (!allowed.includes(file.type)) continue;
                if (form.value.photos.length >= 10) break;
                form.value.photos.push(file);
                const reader = new FileReader();
                reader.onload = (ev) => form.value.photoPreviews.push(ev.target.result);
                reader.readAsDataURL(file);
            }
        }

        function removePhoto(idx) {
            form.value.photos.splice(idx, 1);
            form.value.photoPreviews.splice(idx, 1);
        }

        // ── Progress ────────────────────────────────────────────────────────
        function startProgress() {
            loadingSteps.value.forEach(s => { s.done = false; s.active = false; });
            let step = 0;
            const delays = [300, 800, 12000, 2000, 4000];
            function next() {
                if (step < loadingSteps.value.length) {
                    if (step > 0) loadingSteps.value[step - 1].done = true;
                    loadingSteps.value[step].active = true;
                    progressTimer = setTimeout(() => { step++; next(); }, delays[step] || 2000);
                }
            }
            next();
        }

        function stopProgress() {
            if (progressTimer) { clearTimeout(progressTimer); progressTimer = null; }
            loadingSteps.value.forEach(s => { s.done = true; s.active = false; });
        }

        // ── Evaluate ────────────────────────────────────────────────────────
        async function submitEvaluation() {
            if (!canSubmit.value || isLoading.value) return;
            isLoading.value = true;
            evaluation.value = null;
            evalError.value = null;
            isSaved.value = false;
            photoIds.value = [];
            renovationPlan.value = null;
            savedEvalId.value = null;
            startProgress();

            const fd = new FormData();
            form.value.photos.forEach(f => fd.append('photos[]', f));
            fd.append('state_id', form.value.stateId);
            fd.append('city_id', form.value.cityId);
            fd.append('realty_type', form.value.realtyType);
            fd.append('rooms_count', form.value.roomsCount);
            if (form.value.floor) fd.append('floor', form.value.floor);
            if (form.value.totalFloors) fd.append('total_floors', form.value.totalFloors);
            if (form.value.yearBuilt) fd.append('year_built', form.value.yearBuilt);
            if (form.value.userArea) fd.append('user_area', form.value.userArea);
            if (form.value.userDescription) fd.append('user_description', form.value.userDescription);

            try {
                const resp = await fetch('/api/evaluate', { method: 'POST', body: fd });
                stopProgress();
                const data = await resp.json();
                if (!resp.ok) {
                    evalError.value = data.error || 'Невідома помилка';
                } else {
                    evaluation.value = data.evaluation;
                    photoIds.value = data.photo_ids || [];
                    currentMode.value = data.evaluation.mode;
                }
            } catch (e) {
                stopProgress();
                evalError.value = 'Помилка мережі: ' + e.message;
            } finally {
                isLoading.value = false;
            }
        }

        async function saveEvaluation() {
            if (!evaluation.value || isSaved.value) return;
            try {
                const resp = await fetch('/api/save', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        browser_id: browserId.value,
                        evaluation: evaluation.value,
                        photo_ids: photoIds.value,
                        input: {},
                    }),
                });
                if (resp.ok) {
                    const data = await resp.json();
                    isSaved.value = true;
                    savedEvalId.value = data.id || null;
                }
            } catch (e) {
                console.error('Помилка збереження:', e);
            }
        }

        function resetEvaluation() {
            evaluation.value = null;
            evalError.value = null;
            isSaved.value = false;
            photoIds.value = [];
            savedEvalId.value = null;
            renovationPlan.value = null;
            form.value.photos = [];
            form.value.photoPreviews = [];
        }

        function openPdf() {
            if (!savedEvalId.value) return;
            window.open(`/print/${savedEvalId.value}?browser_id=${encodeURIComponent(browserId.value)}`, '_blank');
        }

        // ── Renovation Advisor ──────────────────────────────────────────────
        async function requestRenovation() {
            if (!evaluation.value || renovationLoading.value) return;
            renovationLoading.value = true;
            try {
                const body = {
                    browser_id: browserId.value,
                    evaluation: evaluation.value,
                };
                if (savedEvalId.value) body.eval_id = savedEvalId.value;

                const resp = await fetch('/api/renovations', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(body),
                });
                const data = await resp.json();
                if (resp.ok) renovationPlan.value = data.plan;
            } catch (e) {
                console.error('Renovation error:', e);
            } finally {
                renovationLoading.value = false;
            }
        }

        // ── History ─────────────────────────────────────────────────────────
        async function goHistory() {
            currentPage.value = 'history';
            historyFilters.value.page = 1;
            compareIds.value = [];
            compareData.value = null;
            await loadHistory();
        }

        async function loadHistory() {
            historyLoading.value = true;
            const f = historyFilters.value;
            const params = new URLSearchParams({ browser_id: browserId.value });
            if (f.realty_type) params.set('realty_type', f.realty_type);
            if (f.state_id) params.set('state_id', f.state_id);
            if (f.price_min != null) params.set('price_min', f.price_min);
            if (f.price_max != null) params.set('price_max', f.price_max);
            if (f.date_from) params.set('date_from', f.date_from);
            if (f.date_to) params.set('date_to', f.date_to);
            if (f.condition_min != null) params.set('condition_min', f.condition_min);
            params.set('sort', f.sort);
            params.set('page', f.page);
            params.set('per_page', f.per_page);

            try {
                const r = await fetch(`/api/history?${params}`);
                const data = await r.json();
                history.value = data.items || [];
                historyTotal.value = data.total || 0;
            } catch {
                history.value = [];
                historyTotal.value = 0;
            } finally {
                historyLoading.value = false;
            }
        }

        function resetFilters() {
            historyFilters.value = {
                realty_type: '',
                state_id: null,
                price_min: null,
                price_max: null,
                date_from: '',
                date_to: '',
                condition_min: null,
                sort: 'date_desc',
                page: 1,
                per_page: 20,
            };
            loadHistory();
        }

        function applyFilters() {
            historyFilters.value.page = 1;
            loadHistory();
        }

        function setPage(p) {
            historyFilters.value.page = p;
            loadHistory();
        }

        async function openHistoryItem(id) {
            try {
                const r = await fetch(`/api/history/${id}?browser_id=${encodeURIComponent(browserId.value)}`);
                if (r.ok) selectedItem.value = await r.json();
            } catch (e) {
                console.error('Помилка відкриття запису:', e);
            }
        }

        async function deleteHistoryItem(id) {
            if (!confirm('Видалити цю оцінку?')) return;
            try {
                await fetch(`/api/history/${id}?browser_id=${encodeURIComponent(browserId.value)}`, { method: 'DELETE' });
                history.value = history.value.filter(h => h.id !== id);
                historyTotal.value = Math.max(0, historyTotal.value - 1);
                compareIds.value = compareIds.value.filter(cid => cid !== id);
            } catch (e) {
                console.error('Помилка видалення:', e);
            }
        }

        function openHistoryPdf(id) {
            window.open(`/print/${id}?browser_id=${encodeURIComponent(browserId.value)}`, '_blank');
        }

        // ── Compare ─────────────────────────────────────────────────────────
        function toggleCompare(id) {
            const idx = compareIds.value.indexOf(id);
            if (idx >= 0) {
                compareIds.value.splice(idx, 1);
            } else if (compareIds.value.length < 2) {
                compareIds.value.push(id);
            }
        }

        function isInCompare(id) {
            return compareIds.value.includes(id);
        }

        async function startCompare() {
            if (compareIds.value.length < 2) return;
            compareLoading.value = true;
            try {
                const ids = compareIds.value.join(',');
                const r = await fetch(`/api/compare?ids=${ids}&browser_id=${encodeURIComponent(browserId.value)}`);
                const data = await r.json();
                if (r.ok) compareData.value = data.items;
            } catch (e) {
                console.error('Compare error:', e);
            } finally {
                compareLoading.value = false;
            }
        }

        // ── Analytics ───────────────────────────────────────────────────────
        async function goAnalytics() {
            currentPage.value = 'analytics';
            await Promise.all([loadAnalyticsSummary(), loadAnalyticsPrices()]);
        }

        async function loadAnalyticsSummary() {
            try {
                const r = await fetch(`/api/analytics/summary?browser_id=${encodeURIComponent(browserId.value)}`);
                if (r.ok) analyticsSummary.value = await r.json();
            } catch {}
        }

        async function loadAnalyticsPrices() {
            if (!analyticsFilters.value.state_id) return;
            analyticsLoading.value = true;
            try {
                const f = analyticsFilters.value;
                const params = new URLSearchParams({
                    state_id: f.state_id,
                    realty_type: f.realty_type,
                    rooms_count: f.rooms_count,
                });
                if (f.city_id) params.set('city_id', f.city_id);
                const r = await fetch(`/api/analytics/prices?${params}`);
                const data = await r.json();
                analyticsData.value = data.data || [];
                renderPriceChart();
            } catch {} finally {
                analyticsLoading.value = false;
            }
        }

        function renderPriceChart() {
            const canvas = document.getElementById('priceChart');
            if (!canvas) return;
            if (priceChart) { priceChart.destroy(); priceChart = null; }
            if (!analyticsData.value.length) return;

            const labels = analyticsData.value.map(d => d.day);
            const prices = analyticsData.value.map(d => Math.round(d.avg_price));

            priceChart = new Chart(canvas, {
                type: 'line',
                data: {
                    labels,
                    datasets: [{
                        label: 'Ціна за м² (USD)',
                        data: prices,
                        borderColor: '#ff4500',
                        backgroundColor: 'rgba(255,69,0,0.08)',
                        borderWidth: 2,
                        pointRadius: 4,
                        pointBackgroundColor: '#ff4500',
                        fill: true,
                        tension: 0.3,
                    }],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { display: false },
                        tooltip: {
                            callbacks: {
                                label: ctx => `$${ctx.parsed.y.toLocaleString('uk-UA')}/м²`,
                            },
                        },
                    },
                    scales: {
                        x: {
                            grid: { color: 'rgba(255,255,255,0.04)' },
                            ticks: { color: '#6b6560', font: { size: 11 } },
                        },
                        y: {
                            grid: { color: 'rgba(255,255,255,0.04)' },
                            ticks: {
                                color: '#6b6560',
                                font: { size: 11 },
                                callback: v => `$${v.toLocaleString('uk-UA')}`,
                            },
                        },
                    },
                },
            });
        }

        // ── Formatters ──────────────────────────────────────────────────────
        function formatNum(n) {
            if (n == null) return '—';
            return Number(n).toLocaleString('uk-UA');
        }

        function formatDate(iso) {
            if (!iso) return '';
            try {
                const d = new Date(iso);
                return d.toLocaleString('uk-UA', { day: 'numeric', month: 'long', year: 'numeric', hour: '2-digit', minute: '2-digit' });
            } catch { return iso; }
        }

        function sourceName(src) { return SOURCE_NAMES[src] || src; }

        function coefClass(val) {
            if (val == null) return 'coef-neutral';
            const v = parseFloat(val);
            if (v > 1.01) return 'coef-positive';
            if (v < 0.99) return 'coef-negative';
            return 'coef-neutral';
        }

        function priorityClass(p) { return `renov-priority-${p || 'low'}`; }
        function priorityLabel(p) { return PRIORITY_UA[p] || p; }

        function userInitials() {
            if (!user.value || !user.value.name) return '?';
            return user.value.name.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase();
        }

        // ── Mount ───────────────────────────────────────────────────────────
        onMounted(async () => {
            await Promise.all([checkHealth(), loadRegions(), checkMe()]);
        });

        return {
            currentPage, currentMode, modeLabel, regions, currentYear,
            user, showAuthModal, authTab, authForm, authLoading, authError,
            form, isDragging, isLoading, loadingSteps,
            evaluation, evalError, isSaved, photoIds, savedEvalId,
            renovationPlan, renovationLoading,
            history, historyTotal, historyLoading, selectedItem,
            historyFilters, historyPages,
            compareIds, compareSelected, compareData, compareLoading,
            analyticsFilters, analyticsData, analyticsSummary, analyticsLoading,
            canSubmit,
            openAuth, submitAuth, logout, authTab,
            loadCities, onFileSelect, onDrop, removePhoto,
            submitEvaluation, saveEvaluation, resetEvaluation, openPdf,
            requestRenovation,
            goHistory, applyFilters, resetFilters, setPage,
            openHistoryItem, deleteHistoryItem, openHistoryPdf,
            toggleCompare, isInCompare, startCompare,
            goAnalytics, loadAnalyticsPrices,
            formatNum, formatDate, sourceName, coefClass,
            priorityClass, priorityLabel, userInitials,
        };
    },
}).mount('#app');
