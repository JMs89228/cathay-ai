import os
import time
import pandas as pd
from datetime import datetime, timedelta
from tools.mcp_search import search_meeting_rooms
from tools.memory import SimpleMemory
from tools.rag_csv_tool import build_vectorstore_from_csv, load_qa_chain
from langchain_community.chat_models import ChatOllama
from dotenv import load_dotenv

# 載入環境變數
load_dotenv()

RAG_DIR = "rag-file"
MODEL_NAME = os.getenv("MODEL_NAME", "gemma3:12b")

# 建築對應表
building_map = {
    "仁愛": "4",
    "松仁": "6",
    "瑞湖": "12",
    "信義安和": "15",
    "台中忠明": "19"
}

# 日期解析函數
def parse_relative_date(query: str) -> str:
    """解析相對日期表達"""
    today = datetime.now()
    
    if "今天" in query or "今日" in query:
        return today.strftime("%Y%m%d")
    elif "明天" in query or "明日" in query:
        return (today + timedelta(days=1)).strftime("%Y%m%d")
    elif "後天" in query:
        return (today + timedelta(days=2)).strftime("%Y%m%d")
    elif "大後天" in query:
        return (today + timedelta(days=3)).strftime("%Y%m%d")
    elif "下週" in query or "下周" in query:
        return (today + timedelta(days=7)).strftime("%Y%m%d")
    
    return None

# 找出最新的某天 CSV
def find_latest_csv(date_str: str) -> str:
    pattern = f"{date_str}_query_"
    candidates = [f for f in os.listdir(RAG_DIR) if f.startswith(pattern) and f.endswith(".csv")]
    if not candidates:
        return None
    candidates.sort(reverse=True)
    return os.path.join(RAG_DIR, candidates[0])

# 建立所有可能時段（30 分鐘間隔）
def generate_all_slots(start="07:00", end="18:00", step=30):
    fmt = "%H:%M"
    start_time = datetime.strptime(start, fmt)
    end_time = datetime.strptime(end, fmt)
    result = []
    while start_time < end_time:
        next_time = start_time + timedelta(minutes=step)
        result.append((start_time.strftime(fmt), next_time.strftime(fmt)))
        start_time = next_time
    return result

# 取得可用時段
def get_available_slots(reserved_slots, all_slots):
    return [slot for slot in all_slots if slot not in reserved_slots]

# 將 reserved start~end 轉為 slot list
def convert_to_slots(start, end, all_slots):
    return [slot for slot in all_slots if slot[0] >= start and slot[1] <= end]

# 根據 CSV 判斷空閒時段（room → available slot list）
def calculate_room_availability(csv_path: str):
    df = pd.read_csv(csv_path)
    all_slots = generate_all_slots()

    room_reserved = {}
    for _, row in df.iterrows():
        key = f"{row['building']} {row['room']}"
        reserved = convert_to_slots(row['start_time'], row['end_time'], all_slots)
        room_reserved.setdefault(key, []).extend(reserved)

    availability = {
        room: get_available_slots(reserved, all_slots)
        for room, reserved in room_reserved.items()
    }
    return df, availability

# 使用者狀態
user_state = {
    "building": None,
    "date": None,
    "confirmed": False,
    "schedule_df": None,
    "availability": None
}

last_loaded_csv = None
memory = SimpleMemory()
llm = ChatOllama(model=MODEL_NAME)
qa_chain = None
use_rag = False

print(f"您好，我是您的 AI 會議助理，有什麼我可以幫忙的嗎？ (模型: {MODEL_NAME})" )


while True:
    query = input("\n> ")
    # 如果出現 "/exit" 或 "/quit" 或 "/bye"，則退出對話
    if query.lower() in ["/exit", "/quit", "/bye"]:
        break

    # 簡化的 system prompt（只在初始化時設定一次）
    if len(memory.messages()) == 0:
        current_date = datetime.now().strftime("%Y年%m月%d日")
        system_prompt = f"你是會議室排程助理，今天是{current_date}，根據提供的資訊精確回答會議室相關問題。"
        memory.append("system", system_prompt)

    # 還沒收集到足夠參數 → 進入收集模式
    if not user_state["confirmed"]:
        for bname in building_map:
            if bname in query:
                user_state["building"] = bname
                break

        # 先嘗試解析相對日期
        relative_date = parse_relative_date(query)
        if relative_date:
            user_state["date"] = relative_date
        else:
            # 再嘗試解析絕對日期
            for fmt in ["%Y/%m/%d", "%Y-%m-%d", "%Y%m%d"]:
                try:
                    dt = datetime.strptime(query[:10], fmt)
                    user_state["date"] = dt.strftime("%Y%m%d")
                    break
                except:
                    continue

        if user_state["building"] and user_state["date"]:
            print(f"確認查詢資訊如下：\n- 大樓：{user_state['building']}\n- 日期：{user_state['date']}")
            confirm = input("是否確認以上查詢？(y/n): ")
            if confirm.lower() == "y":
                user_state["confirmed"] = True
        else:
            print("請提供查詢的建築名稱與日期（如 2025/07/14 仁愛 或 20250714）。")
            continue

    # 已確認查詢條件，進行資料載入與處理
    if user_state["confirmed"] and user_state["schedule_df"] is None:
        found_csv = find_latest_csv(user_state["date"])

        if not found_csv:
            print(f"⚠️ 找不到 {user_state['date']} 的會議室資料，啟動 MCP 爬蟲工具查詢...")
            try:
                formatted_date = f"{user_state['date'][:4]}/{user_state['date'][4:6]}/{user_state['date'][6:]}"
                search_meeting_rooms(start_date=formatted_date, building_code=building_map[user_state["building"]])
                time.sleep(3)
                found_csv = find_latest_csv(user_state["date"])
            except Exception as e:
                print("❌ MCP 工具執行失敗：", e)

        if not found_csv:
            print(f"❌ 無法獲取 {user_state['date']} 的資料，請稍後再試。")
            continue

        print("📥 資料處理中...")
        df, availability = calculate_room_availability(found_csv)
        user_state["schedule_df"] = df
        user_state["availability"] = availability
        last_loaded_csv = found_csv

        # 建立 RAG 向量資料庫
        try:
            print("🔄 建立向量資料庫...")
            build_vectorstore_from_csv(found_csv)
            qa_chain = load_qa_chain()
            use_rag = True
            print("✅ RAG 系統已啟用")
        except Exception as e:
            print(f"⚠️ RAG 初始化失敗，使用基本模式: {e}")

        # 清理記憶，只保留對話上下文
        memory.clear_context()  # 清除舊的資料上下文

        print("✅ 載入完成，您現在可以詢問與會議室預約或空閒時段相關的問題。")
        continue

    # 已完成載入 → 直接使用 RAG
    if user_state["schedule_df"] is not None:
        memory.append("user", query)
        
        # 直接使用 RAG 檢索（跳過第一次 LLM 判斷）
        if use_rag and qa_chain:
            try:
                print("🔍 RAG 檢索中...")
                rag_response = qa_chain({"query": query})
                rag_answer = rag_response["result"]
                sources = rag_response.get("source_documents", [])
                
                # 直接結合 RAG 結果回答
                context_prompt = f"使用者問題：{query}\n\n檢索到的相關資訊：{rag_answer}\n\n請根據以上資訊精確回答使用者的問題。"
                
                # 使用簡化的上下文（只包含最近 3 輪對話）
                recent_messages = memory.get_recent_messages(3)
                final_response = llm.invoke(recent_messages + [{"role": "user", "content": context_prompt}])
                
                memory.append("assistant", final_response.content)
                print("\nAI 回答：", final_response.content)
                
                if sources:
                    print("\n📚 相關資料：")
                    for i, doc in enumerate(sources[:2], 1):
                        print(f"{i}. {doc.page_content[:80]}...")
                        
            except Exception as e:
                print(f"⚠️ RAG 檢索失敗： {e}")
                # 降級到基本模式
                response = llm.invoke(memory.get_recent_messages(3) + [{"role": "user", "content": query}])
                memory.append("assistant", response.content)
                print("\nAI 回答（基本模式）：", response.content)
        else:
            # 沒有 RAG 時的基本模式
            response = llm.invoke(memory.get_recent_messages(3) + [{"role": "user", "content": query}])
            memory.append("assistant", response.content)
            print("\nAI 回答：", response.content)
