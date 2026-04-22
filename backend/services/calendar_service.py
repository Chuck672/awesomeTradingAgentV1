import json
import os
import time
import datetime
import urllib.request
import urllib.error
from typing import List, Dict, Any

CALENDAR_JSON_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "calendar.json")

# ForexFactory / FairEconomy Public JSON API
FF_CALENDAR_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"

WEEKDAY_ZH = ["星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日"]

# 常见高影响力经济数据的汉化字典
TITLE_TRANSLATIONS = {
    "Core CPI m/m": "核心CPI月率",
    "CPI m/m": "CPI月率",
    "CPI y/y": "CPI年率",
    "Non-Farm Employment Change": "非农就业人数",
    "Unemployment Rate": "失业率",
    "FOMC Economic Projections": "美联储经济预期",
    "FOMC Statement": "美联储利率决议声明",
    "Federal Funds Rate": "美联储利率决议",
    "FOMC Press Conference": "美联储新闻发布会",
    "Core PCE Price Index m/m": "核心PCE物价指数月率",
    "Core Retail Sales m/m": "核心零售销售月率",
    "Retail Sales m/m": "零售销售月率",
    "ISM Services PMI": "ISM非制造业PMI",
    "ISM Manufacturing PMI": "ISM制造业PMI",
    "Advance GDP q/q": "GDP季率初值",
    "Prelim GDP q/q": "GDP季率修正值",
    "Final GDP q/q": "GDP季率终值",
    "CB Consumer Confidence": "CB消费者信心指数",
    "JOLTS Job Openings": "JOLTS职位空缺",
    "Fed Chair Powell Speaks": "美联储主席鲍威尔讲话",
    "PPI m/m": "PPI月率",
    "Core PPI m/m": "核心PPI月率",
    "Unemployment Claims": "初请失业金人数",
    "Building Permits": "营建许可",
    "Housing Starts": "新屋开工",
    "Existing Home Sales": "成屋销售",
    "New Home Sales": "新屋销售",
    "Crude Oil Inventories": "EIA原油库存",
    "Flash Manufacturing PMI": "制造业PMI初值",
    "Flash Services PMI": "服务业PMI初值",
    "API Weekly Statistical Bulletin": "API原油库存",
    "Natural Gas Storage": "EIA天然气库存",
    "Pending Home Sales m/m": "成屋签约销售指数月率",
    "Business Inventories m/m": "商业库存月率",
    "Revised UoM Consumer Sentiment": "密歇根大学消费者信心指数终值",
    "Revised UoM Inflation Expectations": "密歇根大学通胀预期终值",
    "ADP Weekly Employment Change": "ADP就业人数"
}

def translate_title(title: str) -> str:
    """翻译事件标题"""
    for en, zh in TITLE_TRANSLATIONS.items():
        if en.lower() in title.lower():
            return zh
    return title

async def fetch_and_update_calendar() -> List[Dict[str, Any]]:
    """
    使用 ForexFactory 的公开接口获取本周财经日历，
    获取所有 USD 的事件（不限影响力），并转换为前端所需的格式（北京时间）。
    """
    current_time = int(time.time())
    events_list = []
    
    try:
        req = urllib.request.Request(FF_CALENDAR_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
            
            for item in data:
                # 过滤：只要 USD 的事件
                impact = item.get("impact", "Low")
                if item.get("country") != "USD":
                    continue
                    
                # 解析时间：FF API 返回如 "2026-04-19T18:45:00-04:00"
                date_str = item.get("date", "")
                if not date_str:
                    continue
                    
                try:
                    # 转换为北京时间 (UTC+8)
                    dt_obj = datetime.datetime.fromisoformat(date_str)
                    bj_dt = dt_obj.astimezone(datetime.timezone(datetime.timedelta(hours=8)))
                    
                    timestamp = int(bj_dt.timestamp())
                    weekday_idx = bj_dt.weekday()
                    
                    # 格式化 date_group: "2026年04月16日 星期四"
                    date_group = f"{bj_dt.year}年{bj_dt.month:02d}月{bj_dt.day:02d}日 {WEEKDAY_ZH[weekday_idx]}"
                    time_str = bj_dt.strftime("%H:%M")
                    
                    events_list.append({
                        "id": f"{timestamp}_{item.get('title')}",
                        "title": translate_title(item.get("title", "")),
                        "impact": impact,
                        "date_group": date_group,
                        "time_str": time_str,
                        "weekday": weekday_idx,
                        "timestamp": timestamp,
                        "previous": item.get("previous", ""),
                        "forecast": item.get("forecast", ""),
                        "actual": item.get("actual", "")
                    })
                except Exception as parse_err:
                    print(f"Error parsing date {date_str}: {parse_err}")
                    continue

        # 爬取完成后，保存到本地 JSON 文件
        with open(CALENDAR_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump({"updated_at": current_time, "events": events_list}, f, ensure_ascii=False, indent=2)
            
    except Exception as e:
        print(f"Failed to fetch or save calendar json: {e}")
        # 爬取失败时，如果本地有旧文件则返回旧文件数据，否则返回空
        if os.path.exists(CALENDAR_JSON_PATH):
            with open(CALENDAR_JSON_PATH, "r", encoding="utf-8") as f:
                old_data = json.load(f)
                return old_data.get("events", [])
        
        # 没有任何数据时（例如因为 429 限流），返回本周的一条提示性伪数据
        today = datetime.datetime.now()
        timestamp = int(today.timestamp())
        weekday_idx = today.weekday()
        date_group = f"{today.year}年{today.month:02d}月{today.day:02d}日 {WEEKDAY_ZH[weekday_idx]}"
        
        return [{
            "id": "dummy_event",
            "title": "API 限流，请稍后刷新重试",
            "impact": "High",
            "date_group": date_group,
            "time_str": "00:00",
            "weekday": weekday_idx,
            "timestamp": timestamp,
            "previous": "-",
            "forecast": "-",
            "actual": "-"
        }]
        
    return events_list

async def get_calendar_events(force: bool = False) -> List[Dict[str, Any]]:
    """
    获取财经日历数据。
    逻辑：优先读取本地 calendar.json 文件。
    如果文件不存在、数据过期（例如超过 12 小时），或者 force 为 True，则触发爬虫更新。
    """
    if force:
        return await fetch_and_update_calendar()

    if os.path.exists(CALENDAR_JSON_PATH):
        try:
            with open(CALENDAR_JSON_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                
            updated_at = data.get("updated_at", 0)
            events = data.get("events", [])
            
            # 判断是否过期（例如 12 小时 = 43200 秒）
            if time.time() - updated_at < 43200:
                return events
            else:
                # 过期则重新爬取
                return await fetch_and_update_calendar()
        except Exception as e:
            print(f"Error reading calendar JSON, re-fetching: {e}")
            return await fetch_and_update_calendar()
    else:
        # 本地没有 JSON 文件，初次爬取
        return await fetch_and_update_calendar()
