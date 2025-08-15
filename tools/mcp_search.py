import requests
from datetime import datetime, timedelta
import os
import re
import pandas as pd
from bs4 import BeautifulSoup
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("search_meeting_rooms", log_level="ERROR")
DRIVER_SERVICE_URL = "http://127.0.0.1:8888"

# 建築代碼對應中文
building_map = {
    "仁愛": "4",
    "松仁": "6",
    "瑞湖": "12",
    "信義安和": "15",
    "台中忠明": "19"
}

# 每棟大樓的會議室定義
meeting_rooms = {
    "4": {  # 仁愛
        "15F": {
            "第1會議室": 20,
            "第2會議室": 12,
            "第3會議室": 15,
            "第4會議室": 15,
            "第6會議室": 60,
            "第8會議室": 12
        }
    },
    "6": {  # 松仁
        "10F": {
            "1001會議室": 5,
            "1002會議室": 10,
            "1003會議室": 10,
            "1004會議室": 10,
            "1005會議室": 10,
            "1006會議室": 10,
            "1008會議室": 7
        },
        "B1": {
            "歐洲區維也納": 8,
            "歐洲區羅馬": 10,
            "歐洲區倫敦": 20,
            "歐洲區巴黎": 9,
            "歐洲區慕尼黑": 10,
            "美洲區紐約": 54,
            "美洲區波士頓": 6,
            "美洲區芝加哥": 12
        }
    },
    "12": {  # 瑞湖
        "8F": {
            "第6會議室": 12,
            "第4會議室": 12,
            "第3會議室": 20
        },
        "7F": {
            "第2會議室": 12,
            "第1會議室": 30
        },
        "6F": {
            "第9會議室": 12,
            "第8會議室": 12
        }
    },
    "15": {  # 信義安和
        "11F": {
            "第1會議室": 17,
            "第2會議室": 14,
            "第3會議室": 6,
            "第4會議室": 16
        },
        "8F": {
            "神隱少女": 6
        }
    },
    "19": {  # 台中忠明
        "23F": {
            "23F會議室": 8
        },
        "16F": {
            "16F視訊會議室": 10,
            "16F大會議室": 30
        }
    }
}


def parse_html_content(html_content, query_date_str, period):
    soup = BeautifulSoup(html_content, "html.parser")

    building_select = soup.find("select", {"id": "searchBeanBuildingPK"})
    building_option = building_select.find("option", selected=True)
    building_name = building_option.text.strip()

    meeting_data = []
    for booking_area in soup.select(".Booking_area"):
        title = booking_area.find("div", class_="Title")
        if not title:
            continue
        floor = title.find("div", class_="Floor").text.strip()
        room = title.find("div", class_="Room").text.strip()

        for button in booking_area.select("button.meetingRecordBtn"):
            start_time = button.get("data-starttime")
            end_time = button.get("data-endtime")
            fields = button.find_all("div", recursive=False)
            if len(fields) < 4:
                continue

            topic = fields[0].text.strip()
            host_org = fields[1].text.strip()
            department = fields[2].text.strip()
            person_name = re.sub(r"\s*\d{7,}", "", fields[3].text.strip())
            host = f"{host_org} {department} {person_name}"

            meeting_data.append({
                "building": building_name,
                "room": room,
                "date": query_date_str,
                "start_time": start_time,
                "end_time": end_time,
                "topic": topic,
                "host": host
            })

    return meeting_data


def save_to_csv(meeting_data, query_date_str, output_dir, timestamp=None):
    if timestamp is None:
        timestamp = datetime.now().strftime("%H%M%S")
    filename = f"{query_date_str}_query_{timestamp}.csv"
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, filename)
    df = pd.DataFrame(meeting_data)
    df.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"✅ 已將資料儲存至 CSV 檔案: {output_path}")
    return output_path


def process_and_save_data(meeting_data, query_date_str):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if meeting_data:
        save_to_csv(meeting_data, query_date_str, output_dir=os.path.join(script_dir, "..", "rag-file"), timestamp=datetime.now().strftime('%H%M%S'))
    else:
        print(f"⚠️ 沒有找到任何會議資料，無法儲存 CSV 檔案")


def ensure_driver_ready():
    try:
        response = requests.get(f"{DRIVER_SERVICE_URL}/driver_status")
        if response.json()["status"] != "active":
            requests.post(f"{DRIVER_SERVICE_URL}/initialize_driver")
    except:
        requests.post(f"{DRIVER_SERVICE_URL}/initialize_driver")


@mcp.tool()
def search_meeting_rooms(start_date, building_code):
    end_date = start_date
    ensure_driver_ready()

    meeting_data = []
    query_date_str = start_date.replace("/", "")

    for period in ["MORNING", "AFTERNOON"]:
        print(f"正在查詢 {period} 的會議室資料...")

        requests.post(f"{DRIVER_SERVICE_URL}/set_date_and_building",
                      params={"start_date": start_date, "end_date": end_date,
                              "building_code": building_code, "period": period})

        response = requests.get(f"{DRIVER_SERVICE_URL}/get_page_source")
        html = response.json()["html"]
        partial_data = parse_html_content(html, query_date_str, period)
        meeting_data.extend(partial_data)

    process_and_save_data(meeting_data, query_date_str)


def compress_schedule_data(csv_path: str, building_code: str) -> dict:
    df = pd.read_csv(csv_path)
    df = df.sort_values(by=["room", "start_time"])
    all_slots = generate_all_slots()

    occupied = {}
    available = {}

    for _, row in df.iterrows():
        room = row["room"]
        reserved = convert_to_slots(row["start_time"], row["end_time"], all_slots)
        occupied.setdefault(room, []).extend(reserved)

    for room in occupied:
        reserved = set(occupied[room])
        available[room] = [f"{s}-{e}" for s, e in all_slots if (s, e) not in reserved]

    # 補上未出現的會議室（全日可用）
    if building_code in meeting_rooms:
        for floor, rooms in meeting_rooms[building_code].items():
            for room in rooms:
                if room not in occupied:
                    occupied[room] = []
                    available[room] = [f"{s}-{e}" for s, e in all_slots]

    return {
        "date": str(df.iloc[0]["date"]) if not df.empty else "",
        "building": str(df.iloc[0]["building"]) if not df.empty else "",
        "reserved_meetings": df.to_dict(orient="records"),
        "available_slots": [{"room": r, "available_time": t} for r, times in available.items() for t in times]
    }


def generate_all_slots(start="08:00", end="18:00", step=30):
    fmt = "%H:%M"
    start_time = datetime.strptime(start, fmt)
    end_time = datetime.strptime(end, fmt)
    result = []
    while start_time < end_time:
        next_time = start_time + timedelta(minutes=step)
        result.append((start_time.strftime(fmt), next_time.strftime(fmt)))
        start_time = next_time
    return result


def time_overlap(slot_start, slot_end, reserve_start, reserve_end):
    return slot_start < reserve_end and reserve_start < slot_end

def convert_to_slots(start, end, all_slots):
    fmt = "%H:%M"
    reserve_start = datetime.strptime(start, fmt)
    reserve_end = datetime.strptime(end, fmt)
    
    result = []
    for s_start, s_end in all_slots:
        slot_start = datetime.strptime(s_start, fmt)
        slot_end = datetime.strptime(s_end, fmt)
        if time_overlap(slot_start, slot_end, reserve_start, reserve_end):
            result.append((s_start, s_end))
    return result

if __name__ == "__main__":
    mcp.run(transport="stdio")
