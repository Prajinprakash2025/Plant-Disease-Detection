(function () {
    window.PlantGuardDashboard = window.PlantGuardDashboard || {};

    const analyticsNode = document.getElementById("dashboardAnalyticsPayload");
    const weeklyCardsNode = document.getElementById("dashboardWeeklyCardsPayload");
    const analytics = analyticsNode ? JSON.parse(analyticsNode.textContent) : null;
    const weeklyCards = weeklyCardsNode ? JSON.parse(weeklyCardsNode.textContent) : null;
    const palette = ["#00c062", "#84cc16", "#facc15", "#fb7185", "#14532d", "#86efac"];

    let trendChart;
    let doughnutChart;
    let fieldChart;
    let sparklineCharts = [];

    function hidePlaceholders(root) {
        root.querySelectorAll(".dashboard-chart-placeholder").forEach((node) => {
            node.classList.add("is-hidden");
        });
    }

    function showChartError(root, message) {
        root.querySelectorAll(".dashboard-chart-placeholder").forEach((node) => {
            node.textContent = message;
            node.classList.remove("is-hidden");
        });
    }

    function loadChartJs() {
        if (window.Chart) return Promise.resolve(window.Chart);
        if (window.__plantGuardChartPromise) return window.__plantGuardChartPromise;

        window.__plantGuardChartPromise = new Promise((resolve, reject) => {
            const script = document.createElement("script");
            script.src = "https://cdn.jsdelivr.net/npm/chart.js@4.4.3/dist/chart.umd.min.js";
            script.async = true;
            script.onload = () => resolve(window.Chart);
            script.onerror = () => reject(new Error("Chart.js failed to load."));
            document.head.appendChild(script);
        });

        return window.__plantGuardChartPromise;
    }

    function lineGradient(ctx, area, from, to) {
        const gradient = ctx.createLinearGradient(area.left, 0, area.right, 0);
        gradient.addColorStop(0, from);
        gradient.addColorStop(1, to);
        return gradient;
    }

    function sparklineColor(tone) {
        if (tone === "red") return "#ef4444";
        if (tone === "amber") return "#f59e0b";
        if (tone === "slate") return "#64748b";
        return "#00c062";
    }

    function destroyAnalyticsCharts() {
        if (trendChart) trendChart.destroy();
        if (doughnutChart) doughnutChart.destroy();
        if (fieldChart) fieldChart.destroy();

        sparklineCharts.forEach((chart) => chart.destroy());

        trendChart = null;
        doughnutChart = null;
        fieldChart = null;
        sparklineCharts = [];
    }

    function setToggleState(root, days) {
        root.querySelectorAll(".dashboard-toggle").forEach((button) => {
            button.dataset.active = button.dataset.range === String(days) ? "true" : "false";
        });
    }

    function buildTrendChart(root, days) {
        const canvas = root.querySelector("#cropHealthTrendChart");
        if (!canvas || !analytics) return;

        const source = days === 7 ? analytics.trend_7 : analytics.trend_30;
        const ctx = canvas.getContext("2d");
        if (trendChart) trendChart.destroy();

        trendChart = new window.Chart(ctx, {
            type: "line",
            data: {
                labels: source.map((item) => item.date),
                datasets: [
                    {
                        label: "Overall health",
                        data: source.map((item) => item.health),
                        borderWidth: 3,
                        tension: 0.38,
                        pointRadius: 0,
                        pointHoverRadius: 5,
                        pointBackgroundColor: "#00c062",
                        spanGaps: true,
                        borderColor(context) {
                            const area = context.chart.chartArea;
                            return area ? lineGradient(context.chart.ctx, area, "#00c062", "#7ce95f") : "#00c062";
                        },
                    },
                    {
                        label: "Disease detected cases",
                        data: source.map((item) => item.disease),
                        borderWidth: 3,
                        tension: 0.38,
                        pointRadius: 0,
                        pointHoverRadius: 5,
                        pointBackgroundColor: "#f59e0b",
                        spanGaps: true,
                        borderColor(context) {
                            const area = context.chart.chartArea;
                            return area ? lineGradient(context.chart.ctx, area, "#facc15", "#ef4444") : "#f59e0b";
                        },
                    },
                ],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                interaction: { mode: "index", intersect: false },
                plugins: {
                    legend: {
                        position: "top",
                        align: "start",
                        labels: {
                            usePointStyle: true,
                            boxWidth: 12,
                            color: "#334235",
                            font: { family: "Inter, system-ui, sans-serif", weight: 700 },
                        },
                    },
                    tooltip: {
                        backgroundColor: "rgba(13, 31, 15, 0.94)",
                        titleColor: "#f5fff9",
                        bodyColor: "#d9f8e7",
                        padding: 14,
                        callbacks: {
                            afterBody(items) {
                                const item = source[items[0].dataIndex];
                                return `Scans: ${item?.scans || 0}`;
                            },
                            label(context) {
                                const value = context.parsed.y;
                                return `${context.dataset.label}: ${value === null || value === undefined ? "--" : `${value}%`}`;
                            },
                        },
                    },
                },
                scales: {
                    x: { grid: { display: false }, ticks: { color: "#6b7a6d", maxRotation: 0 } },
                    y: {
                        beginAtZero: true,
                        suggestedMax: 100,
                        ticks: {
                            color: "#6b7a6d",
                            callback(value) {
                                return `${value}%`;
                            },
                        },
                        grid: { color: "rgba(15, 38, 20, 0.08)" },
                    },
                },
            },
        });

        setToggleState(root, days);
    }

    function buildDoughnutChart(root) {
        const canvas = root.querySelector("#diseaseDistributionChart");
        if (!canvas || !analytics) return;

        const ctx = canvas.getContext("2d");
        if (doughnutChart) doughnutChart.destroy();

        doughnutChart = new window.Chart(ctx, {
            type: "doughnut",
            data: {
                labels: analytics.distribution.map((item) => item.label),
                datasets: [{
                    data: analytics.distribution.map((item) => item.value),
                    backgroundColor: analytics.distribution.map((_, index) => palette[index % palette.length]),
                    borderWidth: 0,
                    hoverOffset: 10,
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                cutout: "72%",
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        backgroundColor: "rgba(13, 31, 15, 0.94)",
                        titleColor: "#f5fff9",
                        bodyColor: "#d9f8e7",
                        padding: 14,
                        callbacks: {
                            label(context) {
                                const total = context.dataset.data.reduce((sum, item) => sum + item, 0);
                                const value = context.parsed;
                                const pct = total ? ((value / total) * 100).toFixed(1) : "0.0";
                                return `${context.label}: ${value} (${pct}%)`;
                            },
                        },
                    },
                },
            },
        });
    }

    function sortedPlantIssues(mode) {
        if (!analytics) return [];

        const values = [...analytics.plant_issues];
        return mode === "alpha"
            ? values.sort((left, right) => left.label.localeCompare(right.label))
            : values.sort((left, right) => right.issues - left.issues);
    }

    function buildFieldChart(root, mode) {
        const canvas = root.querySelector("#fieldIssuesChart");
        if (!canvas) return;

        const values = sortedPlantIssues(mode || "highest");
        const ctx = canvas.getContext("2d");
        if (fieldChart) fieldChart.destroy();

        fieldChart = new window.Chart(ctx, {
            type: "bar",
            data: {
                labels: values.map((item) => item.label),
                datasets: [{
                    label: "Issues",
                    data: values.map((item) => item.issues),
                    borderRadius: 14,
                    borderSkipped: false,
                    backgroundColor: values.map((_, index) => index === 0 ? "#ef4444" : index === 1 ? "#f59e0b" : "#00c062"),
                    hoverBackgroundColor: values.map((_, index) => index === 0 ? "#dc2626" : index === 1 ? "#d97706" : "#009650"),
                }],
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        backgroundColor: "rgba(13, 31, 15, 0.94)",
                        titleColor: "#f5fff9",
                        bodyColor: "#d9f8e7",
                        padding: 14,
                    },
                },
                scales: {
                    x: { ticks: { color: "#6b7a6d" }, grid: { display: false } },
                    y: { beginAtZero: true, ticks: { precision: 0, color: "#6b7a6d" }, grid: { color: "rgba(15, 38, 20, 0.08)" } },
                },
            },
        });
    }

    function buildSparklines(root) {
        if (!weeklyCards) return;

        root.querySelectorAll("[data-sparkline-key]").forEach((canvas) => {
            const card = weeklyCards.find((item) => item.id === canvas.dataset.sparklineKey);
            if (!card) return;

            const color = sparklineColor(card.tone);
            const chart = new window.Chart(canvas.getContext("2d"), {
                type: "line",
                data: {
                    labels: card.sparkline.map((_, index) => index + 1),
                    datasets: [{
                        data: card.sparkline,
                        borderColor: color,
                        backgroundColor: `${color}22`,
                        tension: 0.42,
                        fill: true,
                        borderWidth: 2.5,
                        pointRadius: 0,
                        pointHoverRadius: 0,
                    }],
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false }, tooltip: { enabled: false } },
                    scales: { x: { display: false }, y: { display: false } },
                },
            });

            sparklineCharts.push(chart);
        });
    }

    function bindChartControls(root) {
        const last7Button = root.querySelector("#trendToggle7");
        const last30Button = root.querySelector("#trendToggle30");
        const fieldSort = root.querySelector("#fieldAnalysisSort");

        if (last7Button) {
            last7Button.addEventListener("click", () => buildTrendChart(root, 7));
        }

        if (last30Button) {
            last30Button.addEventListener("click", () => buildTrendChart(root, 30));
        }

        if (fieldSort) {
            fieldSort.addEventListener("change", (event) => {
                buildFieldChart(root, event.target.value);
            });
        }
    }

    function initDynamicContent(root) {
        const scope = root || document;
        const hasCharts = scope.querySelector("#cropHealthTrendChart, #diseaseDistributionChart, #fieldIssuesChart, [data-sparkline-key]");

        if (window.lucide) {
            window.lucide.createIcons();
        }

        if (!hasCharts || !analytics || !weeklyCards) {
            return Promise.resolve();
        }

        return loadChartJs()
            .then(() => {
                window.Chart.defaults.font.family = "Inter, system-ui, sans-serif";
                window.Chart.defaults.color = "#6b7a6d";
                destroyAnalyticsCharts();
                buildTrendChart(scope, 30);
                buildDoughnutChart(scope);
                buildFieldChart(scope, "highest");
                buildSparklines(scope);
                bindChartControls(scope);
                hidePlaceholders(scope);
            })
            .catch(() => {
                showChartError(scope, "Analytics could not load right now.");
            });
    }

    window.PlantGuardDashboard.destroyAnalyticsCharts = destroyAnalyticsCharts;
    window.PlantGuardDashboard.initDynamicContent = initDynamicContent;

    const viewport = document.querySelector("[data-dashboard-viewport]");
    const navLinks = Array.from(document.querySelectorAll("[data-dashboard-nav]"));
    const viewportTitle = document.getElementById("dashboardViewportTitle");
    const activeViewLabel = document.getElementById("dashboardActiveViewLabel");

    if (!viewport || !navLinks.length) {
        initDynamicContent(document);
        return;
    }

    let activeController = null;
    let requestToken = 0;

    function getLink(sectionKey) {
        return navLinks.find((link) => link.dataset.sectionKey === sectionKey);
    }

    function setActiveSection(sectionKey, label) {
        navLinks.forEach((link) => {
            link.classList.toggle("is-active", link.dataset.sectionKey === sectionKey);
        });

        viewport.dataset.activeSection = sectionKey;

        if (viewportTitle && label) {
            viewportTitle.textContent = label;
        }

        if (activeViewLabel && label) {
            activeViewLabel.textContent = label;
        }
    }

    function renderLoading(label) {
        viewport.innerHTML = `
            <div class="grid min-h-[360px] place-items-center rounded-[1.5rem] border border-dashed border-emerald-200 bg-emerald-50/60 p-10 text-center">
                <div>
                    <div class="mx-auto mb-4 h-12 w-12 animate-spin rounded-full border-4 border-emerald-100 border-t-emerald-500"></div>
                    <p class="text-lg font-black text-gray-900">Loading ${label}</p>
                    <p class="mt-2 text-sm text-gray-600">Bringing that workspace into view now.</p>
                </div>
            </div>
        `;
    }

    function renderError(sectionKey, ajaxUrl, historyUrl, label) {
        viewport.innerHTML = `
            <div class="grid min-h-[360px] place-items-center rounded-[1.5rem] border border-rose-200 bg-rose-50/70 p-10 text-center">
                <div class="max-w-md">
                    <p class="text-lg font-black text-gray-900">This section could not load.</p>
                    <p class="mt-2 text-sm text-gray-600">Please try again. The rest of your dashboard is still available.</p>
                    <button type="button" data-dashboard-retry class="btn btn-primary mt-5">Try again</button>
                </div>
            </div>
        `;

        const retryButton = viewport.querySelector("[data-dashboard-retry]");
        if (retryButton) {
            retryButton.addEventListener("click", () => {
                loadSection(sectionKey, ajaxUrl, historyUrl, label, false);
            });
        }
    }

    function loadSection(sectionKey, ajaxUrl, historyUrl, label, pushHistory) {
        if (!ajaxUrl) return;

        requestToken += 1;
        const currentToken = requestToken;

        if (activeController) {
            activeController.abort();
        }

        activeController = new AbortController();
        destroyAnalyticsCharts();
        setActiveSection(sectionKey, label);
        renderLoading(label);

        fetch(ajaxUrl, {
            headers: { "X-Requested-With": "XMLHttpRequest" },
            signal: activeController.signal,
        })
            .then((response) => {
                if (!response.ok) {
                    throw new Error("Section request failed.");
                }

                return response.text();
            })
            .then((html) => {
                if (currentToken !== requestToken) return;

                viewport.innerHTML = html;
                setActiveSection(sectionKey, label);
                initDynamicContent(viewport);

                if (pushHistory !== false) {
                    window.history.pushState({ section: sectionKey }, "", historyUrl);
                }
            })
            .catch((error) => {
                if (error.name === "AbortError") return;
                renderError(sectionKey, ajaxUrl, historyUrl, label);
            });
    }

    navLinks.forEach((link) => {
        link.addEventListener("click", (event) => {
            event.preventDefault();

            const sectionKey = link.dataset.sectionKey;
            const label = link.dataset.sectionLabel;
            if (viewport.dataset.activeSection === sectionKey) {
                setActiveSection(sectionKey, label);
                return;
            }

            loadSection(
                sectionKey,
                link.dataset.sectionUrl,
                link.getAttribute("href"),
                label,
                true,
            );
        });
    });

    window.addEventListener("popstate", () => {
        const params = new URLSearchParams(window.location.search);
        const requestedSection = params.get("section") || "overview";
        const link = getLink(requestedSection) || navLinks[0];
        if (!link) return;

        if (viewport.dataset.activeSection === link.dataset.sectionKey) {
            setActiveSection(link.dataset.sectionKey, link.dataset.sectionLabel);
            return;
        }

        loadSection(
            link.dataset.sectionKey,
            link.dataset.sectionUrl,
            link.getAttribute("href"),
            link.dataset.sectionLabel,
            false,
        );
    });

    const initialLink = getLink(viewport.dataset.activeSection) || navLinks[0];
    if (initialLink) {
        setActiveSection(initialLink.dataset.sectionKey, initialLink.dataset.sectionLabel);
    }

    initDynamicContent(viewport);
})();
