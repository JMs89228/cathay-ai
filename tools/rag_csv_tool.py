import os
import pandas as pd
from datetime import datetime, timedelta
from langchain_community.embeddings import OllamaEmbeddings
from langchain_community.vectorstores import Chroma
from langchain.chains import RetrievalQA
from langchain_community.chat_models import ChatOllama
from langchain.schema import Document
from dotenv import load_dotenv

# 載入環境變數
load_dotenv()

CHROMA_DIR = "chroma_db"
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "nomic-embed-text:latest")
LLM_MODEL = os.getenv("MODEL_NAME", "gemma3:12b")

# 會議室完整資訊
meeting_rooms = {
    "4": {  # 仁愛
        "15F": {
            "第1會議室": 20, "第2會議室": 12, "第3會議室": 15,
            "第4會議室": 15, "第6會議室": 60, "第8會議室": 12
        }
    },
    "6": {  # 松仁
        "10F": {"1001會議室": 5, "1002會議室": 10, "1003會議室": 10, "1004會議室": 10, "1005會議室": 10, "1006會議室": 10, "1008會議室": 7},
        "B1": {"歐洲區維也納": 8, "歐洲區羅馬": 10, "歐洲區倫敦": 20, "歐洲區巴黎": 9, "歐洲區慕尼黑": 10, "美洲區紐約": 54, "美洲區波士頓": 6, "美洲區芝加哥": 12}
    },
    "12": {  # 瑞湖
        "8F": {"第6會議室": 12, "第4會議室": 12, "第3會議室": 20},
        "7F": {"第2會議室": 12, "第1會議室": 30},
        "6F": {"第9會議室": 12, "第8會議室": 12}
    },
    "15": {  # 信義安和
        "11F": {"第1會議室": 17, "第2會議室": 14, "第3會議室": 6, "第4會議室": 16},
        "8F": {"神隱少女": 6}
    },
    "19": {  # 台中忠明
        "23F": {"23F會議室": 8},
        "16F": {"16F視訊會議室": 10, "16F大會議室": 30}
    }
}

building_map = {"仁愛大樓": "4", "松仁大樓": "6", "瑞湖大樓": "12", "信義安和大樓": "15", "台中忠明大樓": "19"}

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

def convert_to_slots(start, end, all_slots):
    fmt = "%H:%M"
    reserve_start = datetime.strptime(start, fmt)
    reserve_end = datetime.strptime(end, fmt)
    result = []
    for s_start, s_end in all_slots:
        slot_start = datetime.strptime(s_start, fmt)
        slot_end = datetime.strptime(s_end, fmt)
        if slot_start < reserve_end and reserve_start < slot_end:
            result.append((s_start, s_end))
    return result

def build_vectorstore_from_csv(csv_path: str):
    df = pd.read_csv(csv_path)
    building_code = building_map.get(df.iloc[0]['building']) if not df.empty else None
    date = str(df.iloc[0]['date']) if not df.empty else ""
    
    documents = []
    all_slots = generate_all_slots()
    
    # 處理已預約會議
    occupied_rooms = set()
    for _, row in df.iterrows():
        room = row['room']
        occupied_rooms.add(room)
        
        # 會議預約資訊
        meeting_info = f"會議室: {row['building']} {room}\n日期: {date}\n時間: {row['start_time']}-{row['end_time']}\n主題: {row['topic']}\n主辦: {row['host']}\n狀態: 已預約"
        documents.append(Document(page_content=meeting_info, metadata={"type": "reserved", "room": room, "date": date}))
    
    # 處理空閒會議室和時段
    if building_code and building_code in meeting_rooms:
        room_availability = {}
        
        # 計算每間會議室的佔用時段
        for _, row in df.iterrows():
            room = row['room']
            reserved_slots = convert_to_slots(row['start_time'], row['end_time'], all_slots)
            room_availability.setdefault(room, []).extend(reserved_slots)
        
        # 為所有會議室生成可用時段資訊
        for floor, rooms in meeting_rooms[building_code].items():
            for room_name, capacity in rooms.items():
                reserved_slots = set(room_availability.get(room_name, []))
                available_slots = [f"{s}-{e}" for s, e in all_slots if (s, e) not in reserved_slots]
                
                # 會議室基本資訊
                room_info = f"會議室: {list(building_map.keys())[list(building_map.values()).index(building_code)]} {room_name}\n樓層: {floor}\n容納人數: {capacity}人\n日期: {date}\n可用時段: {', '.join(available_slots) if available_slots else '無'}\n狀態: {'部分可用' if available_slots else '全日預約'}"
                documents.append(Document(page_content=room_info, metadata={"type": "availability", "room": room_name, "capacity": capacity, "date": date}))
    
    embeddings = OllamaEmbeddings(model=EMBEDDING_MODEL)
    vectorstore = Chroma.from_documents(documents, embeddings, persist_directory=CHROMA_DIR)
    vectorstore.persist()
    return vectorstore

def load_qa_chain():
    vectorstore = Chroma(persist_directory=CHROMA_DIR, embedding_function=OllamaEmbeddings(model=EMBEDDING_MODEL))
    retriever = vectorstore.as_retriever(search_kwargs={"k": 5})
    llm = ChatOllama(model=LLM_MODEL)
    qa_chain = RetrievalQA.from_chain_type(llm=llm, retriever=retriever, return_source_documents=True)
    return qa_chain
