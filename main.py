import os
import httpx
import uvicorn
from mcp.server.fastmcp import FastMCP

API_KEY = os.environ.get("QWEATHER_API_KEY", "")
BASE_URL = "https://devapi.qweather.com/v7"

mcp = FastMCP("weather", allowed_hosts=["*"])


async def qweather_get(path: str, params: dict) -> dict:
    params["key"] = API_KEY
    async with httpx.AsyncClient() as client:
        r = await client.get(f"{BASE_URL}{path}", params=params, timeout=10)
        r.raise_for_status()
        return r.json()


async def get_location_id(city: str) -> tuple[str, str]:
    """用城市名查询LocationID，返回 (location_id, 城市全名)"""
    async with httpx.AsyncClient() as client:
        r = await client.get(
            "https://geoapi.qweather.com/v2/city/lookup",
            params={"location": city, "key": API_KEY, "lang": "zh"},
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()
    if data.get("code") != "200" or not data.get("location"):
        raise ValueError(f"找不到城市：{city}")
    loc = data["location"][0]
    return loc["id"], f"{loc['adm1']} {loc['name']}"


@mcp.tool()
async def get_weather_now(city: str) -> str:
    """查询城市实时天气，包含温度、体感温度、湿度、风向风速、天气描述等。"""
    loc_id, full_name = await get_location_id(city)
    data = await qweather_get("/weather/now", {"location": loc_id, "lang": "zh", "unit": "m"})
    if data.get("code") != "200":
        return f"查询失败，错误码：{data.get('code')}"
    now = data["now"]
    return (
        f"📍 {full_name} 实时天气\n"
        f"天气：{now['text']}\n"
        f"温度：{now['temp']}°C（体感 {now['feelsLike']}°C）\n"
        f"湿度：{now['humidity']}%\n"
        f"风向：{now['windDir']}  风速：{now['windSpeed']} km/h\n"
        f"能见度：{now['vis']} km\n"
        f"更新时间：{now['obsTime']}"
    )


@mcp.tool()
async def get_weather_forecast(city: str, days: int = 3) -> str:
    """查询城市未来天气预报，days 可选 3、7、10，默认3天。"""
    if days not in (3, 7, 10):
        days = 3
    loc_id, full_name = await get_location_id(city)
    data = await qweather_get(f"/weather/{days}d", {"location": loc_id, "lang": "zh", "unit": "m"})
    if data.get("code") != "200":
        return f"查询失败，错误码：{data.get('code')}"
    lines = [f"📅 {full_name} 未来{days}天预报\n"]
    for d in data["daily"]:
        lines.append(
            f"{d['fxDate']}  {d['textDay']} / {d['textNight']}\n"
            f"  🌡 {d['tempMin']}~{d['tempMax']}°C  💧 {d['humidity']}%  ☔ 降水 {d['precip']}mm\n"
            f"  风：{d['windDirDay']} {d['windScaleDay']}级"
        )
    return "\n".join(lines)


@mcp.tool()
async def get_weather_hourly(city: str) -> str:
    """查询城市未来24小时逐小时天气预报。"""
    loc_id, full_name = await get_location_id(city)
    data = await qweather_get("/weather/24h", {"location": loc_id, "lang": "zh", "unit": "m"})
    if data.get("code") != "200":
        return f"查询失败，错误码：{data.get('code')}"
    lines = [f"⏱ {full_name} 未来24小时预报\n"]
    for h in data["hourly"][:12]:  # 取前12小时
        lines.append(f"{h['fxTime'][11:16]}  {h['text']}  {h['temp']}°C  💨{h['windDir']}{h['windScale']}级")
    return "\n".join(lines)


@mcp.tool()
async def get_air_quality(city: str) -> str:
    """查询城市实时空气质量，包含AQI、PM2.5、PM10、等级描述。"""
    loc_id, full_name = await get_location_id(city)
    data = await qweather_get("/air/now", {"location": loc_id, "lang": "zh"})
    if data.get("code") != "200":
        return f"查询失败，错误码：{data.get('code')}"
    air = data["now"]
    return (
        f"🌬 {full_name} 实时空气质量\n"
        f"AQI：{air['aqi']}  等级：{air['category']}\n"
        f"PM2.5：{air['pm2p5']}  PM10：{air['pm10']}\n"
        f"NO₂：{air['no2']}  O₃：{air['o3']}  SO₂：{air['so2']}"
    )


@mcp.tool()
async def get_weather_warning(city: str) -> str:
    """查询城市当前气象灾害预警信息。"""
    loc_id, full_name = await get_location_id(city)
    data = await qweather_get("/warning/now", {"location": loc_id, "lang": "zh"})
    if data.get("code") != "200":
        return f"查询失败，错误码：{data.get('code')}"
    warnings = data.get("warning", [])
    if not warnings:
        return f"✅ {full_name} 当前无气象预警"
    lines = [f"⚠️ {full_name} 气象预警\n"]
    for w in warnings:
        lines.append(f"【{w['typeName']}·{w['level']}级】{w['title']}\n{w['text'][:100]}...")
    return "\n".join(lines)


if __name__ == "__main__":
    app = mcp.sse_app()
    uvicorn.run(app, host="0.0.0.0", port=8000, forwarded_allow_ips="*")

