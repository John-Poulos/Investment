// Price chart (M00_UI D29): TradingView Lightweight Charts 5.2.1, attribution logo on (S67).
// Colours come from the CSS variables in app.css (D-UI-5), with a fallback when one is empty.
// M09 overlays (D-UI-35): price-level σ bands and the 40-week MA from /api/overlay, toggled
// in the chart bar; fetched once on first use; the choice is remembered in this browser.
// The ±2σ and ±1σ zones are shaded under the candles by a series primitive (BandFill).
(function () {
  const el = document.getElementById("chart");
  if (!el || !window.LightweightCharts) return;
  const LC = window.LightweightCharts;
  const css = getComputedStyle(document.documentElement);
  const FALLBACK = {
    "--panel": "#ffffff", "--text-2": "#5f5e5a", "--line": "#e2e0d8", "--line-2": "#c9c7bd",
    "--up": "#3b6d11", "--down": "#a32d2d", "--accent": "#185fa5",
    "--band": "#7a4fb0", "--ma": "#b7791f",
    "--band-fill-2": "rgba(122, 79, 176, 0.07)", "--band-fill-1": "rgba(122, 79, 176, 0.09)",
  };
  const v = (name) => css.getPropertyValue(name).trim() || FALLBACK[name];
  const info = document.getElementById("ov-info");
  function fail(what, e) {
    console.error(`chart: ${what} failed`, e);
    if (info) {
      info.hidden = false;
      info.textContent = `${what} failed: ${e && e.message ? e.message : e}`;
    }
  }
  const json = (url) => fetch(url).then((r) => {
    if (!r.ok) throw new Error(`HTTP ${r.status} from ${url}`);
    return r.json();
  });

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
  const index = new Map(); // bar time -> logical index (the fill's x)
  json(`/api/bars/${ticker}?bar=${el.dataset.bar}`)
    .then((d) => {
      d.bars.forEach((b, i) => index.set(b.time, i));
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
    })
    .catch((e) => fail("price bars", e));

  // --- σ zone shading: a series primitive (Lightweight Charts has no fill-between) ---------
  // zones: [{fill, pts: [{x: logical index, hi, lo}]}]; drawn under the candles (zOrder
  // "bottom"); on daily bars each point holds until the next one, like the stepped lines.
  class BandFill {
    constructor(stepped) {
      this.stepped = stepped;
      this.zones = [];
      this.visible = false;
      this.ctx = null;
      const self = this;
      this.view = {
        zOrder: () => "bottom",
        renderer: () => ({ draw: (target) => self.draw(target) }),
      };
    }
    attached(p) { this.ctx = p; }
    detached() { this.ctx = null; }
    paneViews() { return [this.view]; }
    update(zones, visible) {
      this.zones = zones;
      this.visible = visible;
      if (this.ctx) this.ctx.requestUpdate();
    }
    draw(target) {
      if (!this.visible || !this.ctx || !this.zones.length) return;
      const ts = this.ctx.chart.timeScale();
      const series = this.ctx.series;
      const range = ts.getVisibleLogicalRange();
      if (!range) return;
      const first = (pts, x) => { // the first point at or after logical index x
        let a = 0, b = pts.length;
        while (a < b) { const m = (a + b) >> 1; if (pts[m].x < x) a = m + 1; else b = m; }
        return a;
      };
      target.useBitmapCoordinateSpace((scope) => {
        const c = scope.context, hr = scope.horizontalPixelRatio, vr = scope.verticalPixelRatio;
        const X = (i) => { const x = ts.logicalToCoordinate(i); return x === null ? null : x * hr; };
        const Y = (p) => { const y = series.priceToCoordinate(p); return y === null ? null : y * vr; };
        for (const z of this.zones) {
          // the visible points plus one on each side, split where the band has a gap
          const a = Math.max(0, first(z.pts, range.from) - 1);
          const b = Math.min(z.pts.length, first(z.pts, range.to + 1) + 1);
          const runs = [];
          let run = [];
          for (let k = a; k < b; k++) {
            if (run.length && z.pts[k].x !== run[run.length - 1].x + 1) { runs.push(run); run = []; }
            run.push(z.pts[k]);
          }
          if (run.length) runs.push(run);
          c.fillStyle = z.fill;
          for (const r of runs) {
            const pts = r.map((p) => ({ x: X(p.x), hi: Y(p.hi), lo: Y(p.lo) }))
              .filter((p) => p.x !== null && p.hi !== null && p.lo !== null);
            if (pts.length < 2) continue;
            c.beginPath();
            c.moveTo(pts[0].x, pts[0].hi);
            for (let k = 1; k < pts.length; k++) {
              if (this.stepped) c.lineTo(pts[k].x, pts[k - 1].hi);
              c.lineTo(pts[k].x, pts[k].hi);
            }
            for (let k = pts.length - 1; k >= 0; k--) {
              c.lineTo(pts[k].x, pts[k].lo);
              if (this.stepped && k > 0) c.lineTo(pts[k].x, pts[k - 1].lo);
            }
            c.closePath();
            c.fill();
          }
        }
      });
    }
  }

  // --- M09 overlays ---------------------------------------------------------------------
  function overlays() {
    const boxes = { band: document.getElementById("ov-band"), ma: document.getElementById("ov-ma") };
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
    const fill = new BandFill(daily);
    candles.attachPrimitive(fill);
    let zones = [];
    let data = null;
    let pending = null;
    const series = {};
    function zone(d, up, down, color) {
      const lower = new Map(d.series[down].map((p) => [p.time, p.value]));
      const pts = [];
      for (const p of d.series[up]) {
        const x = index.get(p.time);
        const l = lower.get(p.time);
        if (x !== undefined && l !== undefined) pts.push({ x, hi: p.value, lo: l });
      }
      return { fill: color, pts };
    }
    function load() {
      if (data) return Promise.resolve(data);
      if (!pending) {
        pending = json(`/api/overlay/${ticker}?bar=${el.dataset.bar}`).then((d) => {
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
          zones = [zone(d, "p2", "m2", v("--band-fill-2")), zone(d, "p1", "m1", v("--band-fill-1"))];
          data = d;
          return d;
        }).catch((e) => {
          pending = null; // a later toggle tries again
          throw e;
        });
      }
      return pending;
    }
    function apply() {
      const on = { band: boxes.band.checked, ma: boxes.ma.checked };
      store.set("m09-ov-band", on.band);
      store.set("m09-ov-ma", on.ma);
      if (!on.band && !on.ma && !data) { info.hidden = true; return; }
      load().then((d) => {
        for (const k of ["band", "ma"]) series[k].forEach((s) => s.applyOptions({ visible: on[k] }));
        fill.update(zones, on.band);
        const empty = (on.band && !d.series.mean.length) || (on.ma && !d.series.ma.length);
        info.hidden = !(on.band || on.ma);
        info.textContent = d.as_of
          ? `as of the week to ${d.as_of}` + (empty ? " · too few completed weeks for some lines" : "")
          : "no completed weekly bars";
        info.title = d.note;
      }).catch((e) => fail("overlay", e));
    }
    boxes.band.checked = store.get("m09-ov-band");
    boxes.ma.checked = store.get("m09-ov-ma");
    boxes.band.addEventListener("change", apply);
    boxes.ma.addEventListener("change", apply);
    apply();
  }
})();
