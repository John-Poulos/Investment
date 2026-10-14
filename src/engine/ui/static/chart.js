// Price chart (M00_UI D29): TradingView Lightweight Charts 5.2.1, attribution logo on (S67).
// Colours come from the CSS variables in app.css (D-UI-5).
// M09 overlays (D-UI-35): price-level σ bands and the 40-week MA from /api/overlay, toggled
// in the chart bar; fetched once on first use; the choice is remembered in this browser.
(function () {
  const el = document.getElementById("chart");
  if (!el || !window.LightweightCharts) return;
  const LC = window.LightweightCharts;
  const css = getComputedStyle(document.documentElement);
  const v = (name) => css.getPropertyValue(name).trim();

  const chart = LC.createChart(el, {
    autoSize: true,
    layout: { background: { color: v("--panel") }, textColor: v("--text-2"), attributionLogo: true },
    grid: { vertLines: { color: v("--line") }, horzLines: { color: v("--line") } },
    rightPriceScale: { borderColor: v("--line") },
    timeScale: { borderColor: v("--line") },
  });
  const candles = chart.addSeries(LC.CandlestickSeries, {
    upColor: v("--up"), downColor: v("--down"), borderVisible: false,
    wickUpColor: v("--up"), wickDownColor: v("--down"),
  });
  const volume = chart.addSeries(LC.HistogramSeries, {
    priceScaleId: "vol", priceFormat: { type: "volume" }, color: v("--line-2"),
  });
  chart.priceScale("vol").applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });

  const ticker = encodeURIComponent(el.dataset.ticker);
  const daily = el.dataset.bar !== "W";
  fetch(`/api/bars/${ticker}?bar=${el.dataset.bar}`)
    .then((r) => r.json())
    .then((d) => {
      candles.setData(d.bars.map((b) => ({ time: b.time, open: b.open, high: b.high, low: b.low, close: b.close })));
      volume.setData(d.bars.map((b) => ({ time: b.time, value: b.volume })));
      LC.createSeriesMarkers(candles, d.markers.map((m) => ({
        time: m.time, position: "belowBar", shape: "arrowUp", color: v("--accent"), text: m.text,
      })));
      const n = d.bars.length;
      const show = el.dataset.bar === "W" ? 260 : 500; // ~5 years weekly, ~2 years daily
      if (n > show) chart.timeScale().setVisibleLogicalRange({ from: n - show, to: n });
      else chart.timeScale().fitContent();
      if (d.stale) document.getElementById("stale").hidden = false;
      overlays();
    });

  // --- M09 overlays ---------------------------------------------------------------------
  function overlays() {
    const boxes = { band: document.getElementById("ov-band"), ma: document.getElementById("ov-ma") };
    const info = document.getElementById("ov-info");
    if (!boxes.band || !boxes.ma) return;
    const store = {
      get(k) { try { return window.localStorage.getItem(k) === "1"; } catch (e) { return false; } },
      set(k, on) { try { window.localStorage.setItem(k, on ? "1" : "0"); } catch (e) { /* none */ } },
    };
    const line = (color, style, width) => chart.addSeries(LC.LineSeries, {
      color, lineStyle: style, lineWidth: width,
      lineType: daily ? LC.LineType.WithSteps : LC.LineType.Simple,
      priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false,
    });
    let data = null;
    let pending = null;
    const series = {};
    function load() {
      if (data) return Promise.resolve(data);
      if (!pending) {
        pending = fetch(`/api/overlay/${ticker}?bar=${el.dataset.bar}`).then((r) => r.json()).then((d) => {
          data = d;
          series.band = [
            ["p2", LC.LineStyle.Solid], ["p1", LC.LineStyle.Dotted], ["mean", LC.LineStyle.Dashed],
            ["m1", LC.LineStyle.Dotted], ["m2", LC.LineStyle.Solid],
          ].map(([k, style]) => {
            const s = line(v("--band"), style, 1);
            s.setData(d.series[k]);
            return s;
          });
          const ma = line(v("--ma"), LC.LineStyle.Solid, 2);
          ma.setData(d.series.ma);
          series.ma = [ma];
          return d;
        });
      }
      return pending;
    }
    function apply() {
      const on = { band: boxes.band.checked, ma: boxes.ma.checked };
      store.set("m09-ov-band", on.band);
      store.set("m09-ov-ma", on.ma);
      if (!on.band && !on.ma && !data) return;
      load().then((d) => {
        for (const k of ["band", "ma"]) series[k].forEach((s) => s.applyOptions({ visible: on[k] }));
        const empty = (on.band && !d.series.mean.length) || (on.ma && !d.series.ma.length);
        info.hidden = !(on.band || on.ma);
        info.textContent = d.as_of
          ? `as of the week to ${d.as_of}` + (empty ? " · too few completed weeks for some lines" : "")
          : "no completed weekly bars";
        info.title = d.note;
      });
    }
    boxes.band.checked = store.get("m09-ov-band");
    boxes.ma.checked = store.get("m09-ov-ma");
    boxes.band.addEventListener("change", apply);
    boxes.ma.addEventListener("change", apply);
    apply();
  }
})();
