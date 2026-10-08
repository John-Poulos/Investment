// Price chart (M00_UI D29): TradingView Lightweight Charts 5.2.1, attribution logo on (S67).
// Colours come from the CSS variables in app.css (D-UI-5).
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

  fetch(`/api/bars/${encodeURIComponent(el.dataset.ticker)}?bar=${el.dataset.bar}`)
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
    });
})();
