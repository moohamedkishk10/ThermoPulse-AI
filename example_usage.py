"""
Example usage of the FortyGuard async wrapper.

Run with:  python example_usage.py
Requires a .env file (see .env.example) with a real FORTYGUARD_API_KEY.
"""

import asyncio
import logging

from fortyguard import FortyGuardClient, polygon_from_bbox

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


async def main() -> None:
    # A small area of interest (~1km bbox). Swap in your demo location.
    aoi = polygon_from_bbox(min_lon=-74.017, min_lat=40.705, max_lon=-74.003, max_lat=40.718)

    async with FortyGuardClient() as client:
        # 1. Create Heatmap — single hour, plain temperature (tcm)
        heatmap = await client.create_heatmap(
            polygon_aoi=aoi,
            start_date="2024-07-15",
            filter_type=1,
            start_time="14:00",
            granularity=100,
            analytic_type="tcm",
        )
        stats_df = client.heatmap_stats_to_dataframe(heatmap)
        print("\n=== Heatmap temperature stats ===")
        print(stats_df)

        # 2. Satellite View Segmentation — one point inside the AOI
        sat = await client.satellite_segmentation(
            latitude=40.7128, longitude=-74.0060,
            start_date="2024-07-15", filter_type=1, start_time="14:00",
            granularity=80,
        )
        print("\n=== Satellite segmentation classes ===")
        print(sat.get("segmentation", {}).get("segments"))

        # 3. Street View Segmentation — same point, looking east
        street = await client.street_segmentation(
            latitude=40.7128, longitude=-74.0060,
            vertical_angle=10.0, horizontal_angle=90.0,
        )
        print("\n=== Street-level segmentation classes ===")
        print(street.get("front", {}).get("segments"))

        # 4. Environmental Parameters — a few key comfort/AQI metrics
        env = await client.environmental_parameters(
            latitude=40.7128, longitude=-74.0060, temperature=32.5,
            start_date="2024-07-15", filter_type=1, start_time="14:00",
            analysis=["heat_index_celsius", "relative_humidity_percent", "air_quality:idx"],
        )
        env_df = client.environmental_parameters_to_dataframe(env)
        print("\n=== Environmental parameters ===")
        print(env_df)

        # 5. Heat Intelligence — generates a PDF; download immediately
        heat_intel = await client.heat_intelligence(
            latitude=40.7128, longitude=-74.0060, temperature=32.5,
            date_="2024-07-15", analysis=["environmental", "urban"],
        )
        pdf_path = await client.download_heat_intelligence_pdf(heat_intel, output_path="heat_intelligence_report.pdf")
        print(f"\n=== Heat Intelligence PDF saved to: {pdf_path} ===")

        # 6. Check API Credits Usage (best-effort endpoint — see client.py note)
        try:
            credits = await client.check_credits_usage()
            print("\n=== Credits usage ===")
            print(credits)
        except Exception as e:
            print(f"\n(Credits usage check skipped — endpoint unconfirmed: {e})")


if __name__ == "__main__":
    asyncio.run(main())