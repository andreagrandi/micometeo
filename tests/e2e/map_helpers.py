from __future__ import annotations

from collections.abc import Sequence

from playwright.sync_api import Page


def wait_for_map_settled(page: Page, *, date: str | None = None, timeout: int = 10_000) -> None:
    """Wait until the map shows the squares of one date and no longer moves.

    The old squares stay on screen, dimmed, while the new date loads, so drawn features alone prove nothing.
    """
    page.wait_for_function(
        """
        (date) => {
          const exposed = window.MicometeoMap;
          if (!exposed?.map) return false;
          const diagnostics = exposed.getDiagnostics();
          return document.querySelector('[data-map-app]').dataset.mapStale !== 'true'
            && diagnostics.displayedDate === (date || diagnostics.targetDate)
            && !exposed.map.isMoving();
        }
        """,
        arg=date,
        timeout=timeout,
    )


def click_square(
    page: Page,
    *,
    lng_lat: tuple[float, float],
    cell_id: str,
    date: str | None = None,
    layer: str | Sequence[str] = "micometeo-square-estimates",
) -> None:
    """Click a square once the map shows its date and the square is drawn there.

    The app ignores clicks while the map is stale, so the click waits for the settled map first.
    """
    wait_for_map_settled(page, date=date)
    layers = [layer] if isinstance(layer, str) else list(layer)
    page.wait_for_function(
        """
        ({lngLat, cellId, layers}) => {
          const map = window.MicometeoMap.map;
          return map.queryRenderedFeatures(map.project(lngLat), {layers})
            .some((feature) => feature.properties?.cell_id === cellId);
        }
        """,
        arg={"lngLat": list(lng_lat), "cellId": cell_id, "layers": layers},
        timeout=10_000,
    )
    page.evaluate(
        """
        (lngLat) => {
          const map = window.MicometeoMap.map;
          const point = map.project(lngLat);
          map.fire('click', {
            point,
            lngLat: map.unproject(point),
            originalEvent: {type: 'click', target: map.getCanvas()},
          });
        }
        """,
        list(lng_lat),
    )
