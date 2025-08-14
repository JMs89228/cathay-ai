from fastapi import FastAPI, HTTPException
from selenium import webdriver
from selenium.webdriver.common.by import By
import uvicorn
from datetime import datetime
import threading
import time

app = FastAPI()

# 全域變數儲存 driver 實例
driver_instance = None
driver_lock = threading.Lock()

BOOKING_URL = "https://booking.cathayholdings.com/frontend/mrm101w/index?"
USERNAME = "00897772"
PASSWORD = "Cz@832789239"

def create_driver():
    options = webdriver.ChromeOptions()
    options.add_experimental_option("detach", True)
    driver = webdriver.Chrome(options=options)
    driver.implicitly_wait(5)
    return driver

def login_driver(driver, username, password):
    driver.get(BOOKING_URL)
    driver.find_element(By.NAME, 'username').send_keys(username)
    driver.find_element(By.ID, 'KEY').send_keys(password)
    driver.find_element(By.ID, 'btnLogin').click()
    driver.implicitly_wait(100)

@app.post("/initialize_driver")
async def initialize_driver():
    global driver_instance
    with driver_lock:
        if driver_instance is None:
            try:
                driver_instance = create_driver()
                login_driver(driver_instance, USERNAME, PASSWORD)
                return {"status": "success", "message": "Driver initialized and logged in"}
            except Exception as e:
                return {"status": "error", "message": str(e)}
        else:
            return {"status": "success", "message": "Driver already initialized"}

@app.get("/driver_status")
async def driver_status():
    global driver_instance
    with driver_lock:
        if driver_instance is None:
            return {"status": "not_initialized"}
        try:
            # 檢查 driver 是否還活著
            driver_instance.current_url
            return {"status": "active"}
        except:
            driver_instance = None
            return {"status": "inactive"}

@app.get("/get_page_source")
async def get_page_source():
    global driver_instance
    with driver_lock:
        if driver_instance is None:
            raise HTTPException(status_code=400, detail="Driver not initialized")
        try:
            return {"html": driver_instance.page_source}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

@app.post("/set_date_and_building")
async def set_date_and_building(start_date: str, end_date: str, building_code: str, period: str):
    global driver_instance
    with driver_lock:
        if driver_instance is None:
            raise HTTPException(status_code=400, detail="Driver not initialized")
        
        try:
            # 設定日期
            start_input = driver_instance.find_element(By.ID, 'startDate')
            end_input = driver_instance.find_element(By.ID, 'endDate')
            
            for elem, value in zip([start_input, end_input], [start_date, end_date]):
                driver_instance.execute_script("""
                    arguments[0].value = arguments[1];
                    arguments[0].dispatchEvent(new Event('change', { bubbles: true }));
                """, elem, value)
            
            # 選擇建築物
            from selenium.webdriver.support.ui import Select
            dropdown = driver_instance.find_element(By.ID, 'searchBeanBuildingPK')
            select = Select(dropdown)
            select.select_by_value(building_code)
            
            # 點選早上或下午
            driver_instance.find_element(By.XPATH, f'//button[@name="selectedTimePeriod" and @value="{period}"]').click()
            
            time.sleep(2)  # 等待頁面載入
            return {"status": "success"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

@app.post("/close_driver")
async def close_driver():
    global driver_instance
    with driver_lock:
        if driver_instance:
            try:
                driver_instance.quit()
            except:
                pass
            driver_instance = None
        return {"status": "success", "message": "Driver closed"}

if __name__ == "__main__":
    # 啟動時自動初始化 driver
    try:
        driver_instance = create_driver()
        login_driver(driver_instance, USERNAME, PASSWORD)
        print("✅ Driver 已自動初始化並登入完成")
    except Exception as e:
        print(f"❌ Driver 初始化失敗：{e}")
    
    uvicorn.run(app, host="127.0.0.1", port=8888)