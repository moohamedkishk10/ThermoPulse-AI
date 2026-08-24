import asyncio
import json
from fortyguard import FortyGuardClient, polygon_from_bbox


async def main():
    aoi = polygon_from_bbox(-74.017, 40.705, -74.003, 40.718)
    async with FortyGuardClient() as client:
        result = await client.create_heatmap(
            polygon_aoi=aoi,
            start_date="2024-07-15",
            filter_type=1,
            start_time="14:00",
            granularity=100,
        )
        print("KEYS:", list(result.keys()))
        print(json.dumps(result.get("stats_data", {}), indent=2)[:3000])


asyncio.run(main())
