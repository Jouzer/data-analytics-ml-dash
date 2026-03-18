    let dailyChart = null;
    let hourlyChart = null;
    let timelineChart = null;
    let heatmapChart = null;

    function destroyChart(chart) {
      if (chart) chart.destroy();
    }

    function setSummary(summary) {
      document.getElementById("totalPeople").textContent = summary.total_people ?? 0;
      document.getElementById("rowsCount").textContent = summary.rows ?? 0;
      document.getElementById("avgPerRecord").textContent = summary.avg_per_record ?? 0;
      document.getElementById("timeRange").textContent =
        summary.from && summary.to ? `${summary.from} → ${summary.to}` : "No data";
    }

    function renderCharts(data) {
    destroyChart(dailyChart);
    destroyChart(hourlyChart);
    destroyChart(timelineChart);
    destroyChart(heatmapChart);

    dailyChart = new Chart(document.getElementById("dailyChart"), {
        type: "bar",
        data: {
        labels: data.daily_totals.labels,
        datasets: [{
            label: "Kävijämäärä viikonpäivien mukaan",
            data: data.daily_totals.values
        }]
        },
        options: {
        responsive: true,
        maintainAspectRatio: false
        }
    });

    hourlyChart = new Chart(document.getElementById("hourlyChart"), {
    type: "line",
    data: {
        labels: data.hourly_profile.labels,
        datasets: [
        {
            label: "_Q25",
            data: data.hourly_profile.q25,
            borderColor: "rgba(0,0,0,0)",
            pointRadius: 0,
            tension: 0.25,
            options: {plugins: {legend: {display: false}}}
        },
        {
            label: "Tyypillinen vaihteluväli",
            data: data.hourly_profile.q75,
            fill: "-1",
            borderColor: "rgba(0,0,0,0)",
            backgroundColor: "rgba(54, 162, 235, 0.18)",
            pointRadius: 0,
            tension: 0.25
        },
        {
        label: "7 päivän mediaani",
        data: data.hourly_profile.median,
        borderColor: "rgb(54, 162, 235)",
        backgroundColor: "rgb(54, 162, 235)",
        borderWidth: 2,
        pointRadius: 2,
        tension: 0.25
        },
        {
        label: "Tänään",
        data: data.hourly_profile.today,
        borderColor: "rgb(255, 99, 132)",
        backgroundColor: "rgb(255, 99, 132)",
        borderWidth: 2,
        pointRadius: 3,
        tension: 0.25,
        spanGaps: false   // tärkeä nullien kanssa
        }
        ]
    },
    options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
            legend: {
                labels: {
                    // This filters out any label starting with an underscore
                    filter: function(item, chartData) {
                        return !item.text.includes('_');
                    }}}}
    }
    });

    timelineChart = new Chart(document.getElementById("timelineChart"), {
        type: "line",
        data: {
        labels: data.timeline.labels,
        datasets: [{
            label: "Kävijämäärä",
            data: data.timeline.values,
            tension: 0.2
        }]
        },
        options: {
        responsive: true,
        maintainAspectRatio: false
        }
    });

    renderHeatmap(data.heatmap);
    }

    function getHeatColor(value, maxValue) {
    if (maxValue === 0) return "rgba(220,220,220,0.6)";

    const alpha = Math.max(0.08, value / maxValue);
    return `rgba(54, 162, 235, ${alpha})`;
    }

    function renderHeatmap(heatmap) {
    const days = heatmap.days || [];
    const hours = heatmap.hours || [];
    const values = heatmap.values || [];

    const textValues = values.map(row =>
        row.map(v => Number(v).toFixed(1))
    );

    const data = [{
        z: values,
        x: hours.map(h => `${h}:00`),
        y: days,
        type: "heatmap",
        colorscale: "Reds",
        reversescale: false,
        text: textValues,
        texttemplate: "%{text}",
        textfont: {
        size: 12,
        color: "white"
        },
        hovertemplate: "Day: %{y}<br>Hour: %{x}<br>Visitors: %{z}<extra></extra>",
        colorbar: {
        title: "Vierailijat"
        }
    }];

    const layout = {
        margin: { t: 20, r: 20, b: 50, l: 90 },
        xaxis: {
        title: ""
        },
        yaxis: {
        title: "",
        autorange: "reversed"
        }
    };

    Plotly.newPlot("heatmapChart", data, layout, { responsive: true });
    }

    async function loadDevice(deviceKey) {
      const response = await fetch(`/api/device/${deviceKey}`);
      const data = await response.json();

      setSummary(data.summary);
      renderCharts(data);
    }

    document.querySelectorAll(".device-btn").forEach(btn => {
      btn.addEventListener("click", async () => {
        document.querySelectorAll(".device-btn").forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
        await loadDevice(btn.dataset.device);
      });
    });

    loadDevice("simulated");