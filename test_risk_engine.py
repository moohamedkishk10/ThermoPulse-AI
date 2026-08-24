"""
Test the Heat Risk Engine end-to-end: Create Heatmap -> sample hottest tiles
-> Satellite Segmentation on each -> Heat Risk score + explanation.
"""

import asyncio
from fortyguard import FortyGuardClient, polygon_from_bbox
from spatial_engine import HeatRiskEngine


async def main():
    aoi = polygon_from_bbox(-74.017, 40.705, -74.003, 40.718)

    async with FortyGuardClient() as client:
        heatmap = await client.create_heatmap(
            polygon_aoi=aoi,
            start_date="2024-07-15",
            filter_type=1,
            start_time="14:00",
            granularity=100,
        )

        engine = HeatRiskEngine(client)
        assessments = await engine.assess_area(
            heatmap_result=heatmap,
            start_date="2024-07-15",
            filter_type=1,
            start_time="14:00",
            top_n_hottest=3,  # small number to keep this test cheap
        )

        print("\n=== Heat Risk Assessments (hottest 3 tiles) ===\n")
        for a in assessments:
            print(a.risk.explain())

        df = HeatRiskEngine.to_dataframe(assessments)
        print("\n=== As DataFrame ===")
        print(df[["tile_id", "temperature_c", "risk_score", "risk_category"]])


if __name__ == "__main__":
    asyncio.run(main())