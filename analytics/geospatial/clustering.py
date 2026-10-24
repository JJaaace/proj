"""
clustering.py - Spatial clustering of customer outage reports to locate damage.

Owner: Person 2 (Predictions & Geospatial)
Layer: Layer 2 Analytics (analytics/geospatial)

Groups multiple customer outage reports geographically into damage clusters,
calculating cluster centroids and spatial dispersion to assist root-cause inference.
"""

from __future__ import annotations
from typing import List, Dict, Any, Tuple
import math

from analytics.geospatial.storm_overlay import haversine_distance_km


def cluster_outages(
    outage_reports: List[Dict[str, Any]],
    max_distance_km: float = 0.50,
) -> List[Dict[str, Any]]:
    """
    Cluster customer outage reports by spatial proximity using single-linkage agglomeration.

    Parameters:
        outage_reports: List of dicts, each having 'customer_id' (or 'id'), 'lat', 'lon'
        max_distance_km: Neighborhood distance threshold (default 0.50 km = 500 meters)

    Returns:
        List of cluster dicts:
            {
                "cluster_id": str,
                "count": int,
                "centroid_lat": float,
                "centroid_lon": float,
                "customer_ids": list[str],
                "spread_km": float,
            }
    """
    if not outage_reports:
        return []

    # Clean input
    points = []
    for r in outage_reports:
        cid = r.get("customer_id") or r.get("id") or "UNKNOWN"
        lat = float(r.get("lat", 0.0))
        lon = float(r.get("lon", 0.0))
        points.append({"id": str(cid), "lat": lat, "lon": lon})

    visited = set()
    clusters = []

    for i, pt in enumerate(points):
        if i in visited:
            continue

        # Start new cluster
        cluster_indices = [i]
        visited.add(i)
        queue = [i]

        while queue:
            curr_idx = queue.pop(0)
            curr_pt = points[curr_idx]

            for j, candidate_pt in enumerate(points):
                if j not in visited:
                    dist = haversine_distance_km(
                        curr_pt["lat"], curr_pt["lon"],
                        candidate_pt["lat"], candidate_pt["lon"]
                    )
                    if dist <= max_distance_km:
                        visited.add(j)
                        cluster_indices.append(j)
                        queue.append(j)

        cluster_pts = [points[idx] for idx in cluster_indices]
        c_lat = sum(p["lat"] for p in cluster_pts) / len(cluster_pts)
        c_lon = sum(p["lon"] for p in cluster_pts) / len(cluster_pts)

        # Calculate max spread from centroid
        spread = max(
            haversine_distance_km(c_lat, c_lon, p["lat"], p["lon"])
            for p in cluster_pts
        ) if len(cluster_pts) > 1 else 0.0

        clusters.append({
            "cluster_id": f"CLUSTER-{len(clusters) + 1}",
            "count": len(cluster_pts),
            "centroid_lat": round(c_lat, 6),
            "centroid_lon": round(c_lon, 6),
            "customer_ids": [p["id"] for p in cluster_pts],
            "spread_km": round(spread, 3),
        })

    # Sort largest clusters first
    clusters.sort(key=lambda c: c["count"], reverse=True)
    return clusters
