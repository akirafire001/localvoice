/* Equirectangular world. land.json is Natural Earth 110m land (public domain), rounded to 0.1°. */
(function () {
  const root = document.getElementById("world-map");
  const data = document.getElementById("map-points");
  if (!root || !data) return;
  const points = JSON.parse(data.textContent || "[]");
  const width = 1000;
  const height = 500;
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 " + width + " " + height);
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-labelledby", "world-caption");
  root.appendChild(svg);

  const caption = document.createElement("p");
  caption.id = "world-caption";
  caption.className = "hint";
  caption.textContent = points.length
    ? "生成されたガイドが集まっている場所を、色の濃さで示しています。"
    : "生成されたガイドがまだないため、陸地だけを表示しています。";
  root.before(caption);

  function el(name, attrs) {
    const node = document.createElementNS("http://www.w3.org/2000/svg", name);
    Object.entries(attrs).forEach(function (pair) { node.setAttribute(pair[0], pair[1]); });
    return node;
  }

  function project(lon, lat) {
    return [(Number(lon) + 180) / 360 * width, (90 - Number(lat)) / 180 * height];
  }

  svg.appendChild(el("rect", { width: width, height: height, fill: "#e4eee9" }));
  for (let lon = -180; lon <= 180; lon += 30) {
    const x = project(lon, 0)[0];
    svg.appendChild(el("line", { x1: x, y1: 0, x2: x, y2: height, stroke: "#d3e4db", "stroke-width": 1 }));
  }
  for (let lat = -60; lat <= 60; lat += 30) {
    const y = project(0, lat)[1];
    svg.appendChild(el("line", { x1: 0, y1: y, x2: width, y2: y, stroke: "#d3e4db", "stroke-width": 1 }));
  }

  const land = el("g", { fill: "#b7cfc2", "fill-rule": "evenodd", stroke: "#fbfaf5", "stroke-width": "0.5" });
  svg.appendChild(land);
  fetch(root.dataset.land)
    .then(function (response) { return response.json(); })
    .then(function (polygons) {
      polygons.forEach(function (rings) {
        const d = rings.map(function (ring) {
          return ring.map(function (pt, index) {
            const xy = project(pt[0], pt[1]);
            return (index ? "L" : "M") + xy[0].toFixed(1) + " " + xy[1].toFixed(1);
          }).join("") + "Z";
        }).join("");
        land.appendChild(el("path", { d: d }));
      });
    })
    .catch(function () {
      caption.textContent = "陸地の読み込みに失敗しました。下の一覧で生成量を確認できます。";
    });

  const max = points.reduce(function (top, point) { return Math.max(top, point.count); }, 1);
  points.slice().sort(function (a, b) { return a.count - b.count; }).forEach(function (point) {
    const xy = project(point.lon, point.lat);
    const strength = Math.sqrt(point.count / max);
    const circle = el("circle", {
      cx: xy[0].toFixed(1),
      cy: xy[1].toFixed(1),
      r: "2.4",
      fill: "#c45c2a",
      "fill-opacity": (0.22 + 0.33 * strength).toFixed(2),
      stroke: "#8a3418",
      "stroke-opacity": (0.18 + 0.32 * strength).toFixed(2),
      "stroke-width": "0.35",
    });
    const title = document.createElementNS("http://www.w3.org/2000/svg", "title");
    title.textContent = point.label + "、" + point.count + "本";
    circle.appendChild(title);
    svg.appendChild(circle);
  });
})();
