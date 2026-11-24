"use strict";
/* World Viewer panel (web/panels/world_viewer.py): the interface hardware's sensed map, in
   world coordinates (m, +y up, (0, 0) at the map's center), with a marker for every sensed
   Pose in Knowledge, plus a trajectory drawer whose output is Trajectory text to copy.

   Gestures: the wheel zooms about the cursor; drag pans. With Draw on: click adds a waypoint,
   drag a waypoint to move it, right-click a waypoint to delete it. */

mtofr.registerPanel("world_viewer", (element, api) => {
  const ui = mtofr.ui;
  const make = ui.make;


  //==========// Config //==========//

  const SVG_NAMESPACE = "http://www.w3.org/2000/svg";
  const ASSET_PATH = "/panels/world_viewer/assets/";
  const DEFAULT_EXTENT_METERS = 40;   // view span with no map
  const FIT_FRACTION = 0.95;          // of the canvas a fitted map fills
  const ZOOM_FACTOR = 1.15;           // per wheel notch
  const MIN_PIXELS_PER_METER = 0.5;
  const MAX_PIXELS_PER_METER = 200;
  const OVERLAY_OPACITY = 0.45;       // TRAVERSABILITY_ALPHA / REGIONS_ALPHA in viz/plane_plotter.py
  const POSE_RADIUS = 6;              // px
  const HEADING_LENGTH = 16;          // px
  const LABEL_OFFSET = 10;            // px
  const WAYPOINT_RADIUS = 8;          // px
  const DRAG_THRESHOLD = 4;           // screen px a press must travel before it counts as a drag
  const WAYPOINT_DECIMALS = 2;        // m, in the copied text
  const READOUT_DECIMALS = 2;
  const AGE_DECIMALS = 1;
  const PRIMARY_BUTTON = 0;
  const MIDDLE_BUTTON = 1;


  //==========// State //==========//

  let panelState = null;
  let mapVersion = null;      // the map whose images are loaded
  let fitted = false;         // the view has been fitted once (to the map, or the default extent)
  const view = {x: 0, y: 0, zoom: 1};   // screen px = (world x * zoom + view.x, -world y * zoom + view.y)
  let points = [];            // the drawn trajectory: [[x, y], ...] m, world frame
  let drawing = false;
  let drag = null;            // {kind: "pan" | "waypoint" | "press", ...} while a press is in progress
  const shownOverlays = new Set();


  //==========// Geometry //==========//

  const toScreen = ([x, y]) => [x * view.zoom + view.x, -y * view.zoom + view.y];
  const toWorld = ([screenX, screenY]) => [(screenX - view.x) / view.zoom, -(screenY - view.y) / view.zoom];
  const clampZoom = (zoom) => Math.min(MAX_PIXELS_PER_METER, Math.max(MIN_PIXELS_PER_METER, zoom));
  const round = (value) => Number(value.toFixed(WAYPOINT_DECIMALS));

  /** The pointer's position in the canvas, in screen px. */
  function canvasPoint(event) {
    const bounds = svg.getBoundingClientRect();
    return [event.clientX - bounds.left, event.clientY - bounds.top];
  }

  /** Centers the view on the map (or the default extent), scaled to fit. Needs the canvas laid out. */
  function fitView() {
    const width = svg.clientWidth;
    const height = svg.clientHeight;
    if (!width || !height) {
      return;
    }
    const map = panelState?.map;
    const spanX = map ? map.width_meters : DEFAULT_EXTENT_METERS;
    const spanY = map ? map.height_meters : DEFAULT_EXTENT_METERS;
    view.zoom = clampZoom(FIT_FRACTION * Math.min(width / spanX, height / spanY));
    view.x = width / 2;
    view.y = height / 2;
    fitted = true;
    render();
  }


  //==========// Text Format //==========//
  // NOTE: restates the Trajectory format; the single source of truth is
  // database/knowledge_types/trajectory.py (parse_waypoints()).

  /** The drawn points as Trajectory text, e.g. "[[0, 0], [10.5, -3]]". */
  const formatPoints = () => `[${points.map(([x, y]) => `[${round(x)}, ${round(y)}]`).join(", ")}]`;

  /** Trajectory text as [[x, y], ...]; throws an Error naming the problem. */
  function parsePoints(text) {
    if (!text.trim()) {
      return [];
    }
    const parsed = JSON.parse(text);
    const isPair = (point) => Array.isArray(point) && point.length === 2
      && point.every((coordinate) => typeof coordinate === "number" && Number.isFinite(coordinate));
    if (!Array.isArray(parsed) || !parsed.every(isPair)) {
      throw new Error("expected a JSON list of [x, y] number pairs");
    }
    return parsed;
  }


  //==========// DOM //==========//

  /** Builds an SVG element with attributes and children. */
  function svgElement(tag, attributes = {}, children = []) {
    const created = document.createElementNS(SVG_NAMESPACE, tag);
    for (const [name, value] of Object.entries(attributes)) {
      if (value !== null && value !== undefined && value !== false) {
        created.setAttribute(name, value);
      }
    }
    created.append(...[].concat(children));
    return created;
  }

  /** An SVG element whose text content is set as text, never markup. */
  function svgTextElement(tag, attributes, text) {
    const created = svgElement(tag, attributes);
    created.textContent = text;
    return created;
  }

  const svg = svgElement("svg", {class: "world-svg"});
  const imageLayer = svgElement("g");       // persistent <image>s, so a redraw never refetches them
  const markerLayer = svgElement("g");      // poses and the trajectory, rebuilt by render()
  svg.append(imageLayer, markerLayer);
  const images = {};                         // asset name -> <image>
  const emptyNote = make("div", {class: "graph-empty", text: "No map sensed yet (the interface platform has no map, or hasn't ticked)."});

  const readout = make("span", {class: "note"});
  const textStatus = make("span", {class: "note"});
  const drawButton = make("button", {type: "button", text: "Draw: off", onclick: () => setDrawing(!drawing),
                                     title: "Click adds a waypoint, drag moves one, right-click deletes one"});
  const overlayChecks = make("span", {class: "button-row"});
  const textBox = make("textarea", {class: "trajectory-text", rows: 3, spellcheck: "false",
                                    placeholder: "[[x, y], ...] (m, world frame)"});

  element.append(
    make("p", {class: "help", text:
      "The map this interface platform senses, with every platform's sensed pose (each <id>/pose key). " +
      "Turn on Draw to lay out a trajectory, then Copy its text into a Trajectory value (Live Control, " +
      "or a key in the Graph editor) for follow_trajectory. Paste text and press Load to edit an existing one."}),
    make("div", {class: "button-row"}, [
      drawButton,
      ...ui.buttonRow([
        {label: "Undo point", onClick: () => setPoints(points.slice(0, -1))},
        {label: "Clear", onClick: () => setPoints([])},
        {label: "Fit view", onClick: fitView},
      ]).children,
      overlayChecks,
      make("span", {class: "toolbar-gap"}),
      readout,
    ]),
    make("div", {class: "graph-canvas world-canvas"}, [svg, emptyNote]),
    make("div", {class: "trajectory-tools"}, [
      textBox,
      make("div", {class: "button-row"}, [
        ...ui.buttonRow([
          {label: "Copy", onClick: copyText},
          {label: "Load", onClick: loadText, title: "Redraw the trajectory from the text"},
        ]).children,
        textStatus,
      ]),
    ]),
  );


  //==========// Trajectory //==========//

  /** Replaces the drawn points, refreshing the text and the canvas. */
  function setPoints(newPoints) {
    points = newPoints;
    textBox.value = points.length ? formatPoints() : "";
    textStatus.textContent = "";
    render();
  }

  function setDrawing(on) {
    drawing = on;
    drawButton.textContent = `Draw: ${on ? "on" : "off"}`;
    drawButton.classList.toggle("selected", on);
  }

  /** Copies the text box to the clipboard (falling back to select-and-copy). */
  async function copyText() {
    try {
      await navigator.clipboard.writeText(textBox.value);
    } catch (error) {
      // NOTE: the async clipboard can be unavailable (permissions, an insecure origin); fall back.
      textBox.select();
      document.execCommand("copy");
    }
    textStatus.textContent = "Copied.";
  }

  /** Redraws the trajectory from the text box. */
  function loadText() {
    try {
      const loaded = parsePoints(textBox.value);
      setPoints(loaded.map(([x, y]) => [x, y]));
      textStatus.textContent = `Loaded ${loaded.length} waypoint(s).`;
    } catch (error) {
      textStatus.textContent = `Not a trajectory: ${error.message}`;
    }
  }


  //==========// Rendering //==========//

  /** Loads the map's layer images when the map changes, and builds the overlay checkboxes. */
  function syncMap(map, layers) {
    const version = map ? map.version : null;
    if (version === mapVersion) {
      return;
    }
    mapVersion = version;
    imageLayer.replaceChildren();
    overlayChecks.replaceChildren();
    for (const name of Object.keys(images)) {
      delete images[name];
    }
    if (map) {
      layers.forEach((layer, index) => {
        const isOverlay = index > 0;   // the first layer (cosmetic) is always shown
        images[layer] = svgElement("image", {
          href: `${ASSET_PATH}${layer}?v=${version}`, preserveAspectRatio: "none", class: "map-image",
          opacity: isOverlay ? OVERLAY_OPACITY : null,
        });
        imageLayer.append(images[layer]);
        if (isOverlay) {
          const label = layer.replace(/\.png$/, "");
          const check = make("input", {type: "checkbox", checked: shownOverlays.has(layer), onchange: (event) => {
            if (event.target.checked) {
              shownOverlays.add(layer);
            } else {
              shownOverlays.delete(layer);
            }
            render();
          }});
          overlayChecks.append(make("label", {}, [check, ` ${label[0].toUpperCase()}${label.slice(1)}`]));
        }
      });
    }
    fitted = false;
  }

  /** Redraws the map placement, the poses, and the trajectory for the current view. */
  function render() {
    const map = panelState?.map;
    emptyNote.hidden = !!map;
    if (map) {
      const [left, top] = toScreen([-map.width_meters / 2, map.height_meters / 2]);
      for (const [layer, image] of Object.entries(images)) {
        const shown = layer === panelState.layers[0] || shownOverlays.has(layer);
        image.setAttribute("x", left);
        image.setAttribute("y", top);
        image.setAttribute("width", map.width_meters * view.zoom);
        image.setAttribute("height", map.height_meters * view.zoom);
        image.setAttribute("visibility", shown ? "visible" : "hidden");
      }
    }

    const markers = [];
    for (const pose of panelState?.poses ?? []) {
      const [x, y] = toScreen([pose.x, pose.y]);
      const age = pose.age === null ? "" : `, written ${pose.age.toFixed(AGE_DECIMALS)} s ago`;
      markers.push(svgElement("g", {class: "pose-marker"}, [
        svgTextElement("title", {}, `${pose.key} (from ${pose.origin ?? "?"}${age}): ` +
                                    `x ${pose.x.toFixed(READOUT_DECIMALS)}, y ${pose.y.toFixed(READOUT_DECIMALS)}`),
        svgElement("line", {x1: x, y1: y, x2: x + HEADING_LENGTH * Math.cos(pose.theta),
                            y2: y - HEADING_LENGTH * Math.sin(pose.theta)}),
        svgElement("circle", {cx: x, cy: y, r: POSE_RADIUS}),
        svgTextElement("text", {x: x + LABEL_OFFSET, y: y - LABEL_OFFSET}, pose.key.replace(/\/pose$/, "")),
      ]));
    }

    if (points.length) {
      const screenPoints = points.map(toScreen);
      markers.push(svgElement("polyline", {class: "trajectory-line", points: screenPoints.map((point) => point.join(",")).join(" ")}));
      screenPoints.forEach(([x, y], index) => {
        markers.push(svgElement("g", {class: "waypoint", "data-index": index}, [
          svgElement("circle", {cx: x, cy: y, r: WAYPOINT_RADIUS}),
          svgTextElement("text", {x, y}, String(index + 1)),
        ]));
      });
    }
    markerLayer.replaceChildren(...markers);
  }


  //==========// Gestures //==========//

  /** The waypoint index under a pointer event, or null. */
  function waypointAt(event) {
    const waypoint = event.target.closest?.(".waypoint");
    return waypoint ? Number(waypoint.dataset.index) : null;
  }

  svg.addEventListener("wheel", (event) => {
    event.preventDefault();
    const [screenX, screenY] = canvasPoint(event);
    const [worldX, worldY] = toWorld([screenX, screenY]);
    view.zoom = clampZoom(view.zoom * (event.deltaY < 0 ? ZOOM_FACTOR : 1 / ZOOM_FACTOR));
    view.x = screenX - worldX * view.zoom;   // keep the point under the cursor fixed
    view.y = screenY + worldY * view.zoom;
    render();
  }, {passive: false});

  svg.addEventListener("pointerdown", (event) => {
    if (event.button !== PRIMARY_BUTTON && event.button !== MIDDLE_BUTTON) {
      return;
    }
    const start = canvasPoint(event);
    const index = waypointAt(event);
    if (drawing && event.button === PRIMARY_BUTTON && index !== null) {
      drag = {kind: "waypoint", index};
    } else {
      drag = {kind: "press", start, origin: {x: view.x, y: view.y}};
    }
    svg.setPointerCapture(event.pointerId);
  });

  svg.addEventListener("pointermove", (event) => {
    const here = canvasPoint(event);
    const [worldX, worldY] = toWorld(here);
    readout.textContent = `x ${worldX.toFixed(READOUT_DECIMALS)}, y ${worldY.toFixed(READOUT_DECIMALS)} m`;
    if (!drag) {
      return;
    }
    if (drag.kind === "waypoint") {
      points[drag.index] = [worldX, worldY];
      setPoints(points);
      return;
    }
    if (drag.kind === "press" && Math.hypot(here[0] - drag.start[0], here[1] - drag.start[1]) > DRAG_THRESHOLD) {
      drag.kind = "pan";
    }
    if (drag.kind === "pan") {
      view.x = drag.origin.x + here[0] - drag.start[0];
      view.y = drag.origin.y + here[1] - drag.start[1];
      render();
    }
  });

  svg.addEventListener("pointerup", (event) => {
    // A press that never moved is a click: in Draw mode, it adds a waypoint
    if (drag?.kind === "press" && drawing && event.button === PRIMARY_BUTTON) {
      setPoints([...points, toWorld(canvasPoint(event))]);
    }
    drag = null;
  });

  svg.addEventListener("contextmenu", (event) => {
    const index = waypointAt(event);
    if (drawing && index !== null) {
      event.preventDefault();
      setPoints(points.filter((_, candidate) => candidate !== index));
    }
  });


  return {
    update(state) {
      panelState = state;
      syncMap(state.map, state.layers);
      if (!fitted && api.isVisible()) {
        fitView();   // a no-op until the canvas has a size
      }
      if (!drag) {
        render();
      }
    },
  };
});
