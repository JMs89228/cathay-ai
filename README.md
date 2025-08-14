# Term Project
### ⚙️ 初次安裝與設定指引（支援 macOS / Windows）

1. 安裝 Python 3.8+
2. 安裝 [`uv`](https://github.com/astral-sh/uv)
   - **macOS：**
     ```bash
     curl -LsSf https://astral.sh/uv/install.sh | sh
     ```
   - **Windows：**
     ```powershell
     iwr -useb https://astral.sh/uv/install.ps1 | iex
     ```

3. 建立虛擬環境並啟動
   - 初始專案資料夾
     ```cmd
     uv init my-project
     ```
   - **macOS：**
     ```bash
     uv venv
     source .venv/bin/activate
     ```
   - **Windows：**
     ```cmd
     uv venv
     .venv\Scripts\activate
     ```

4. 安裝套件
   ```bash
   uv pip install -r requirements.txt

5. 專案架構
- main方法：application的starting point
- driver_service: 可視為啟用API服務的端點，可以先打開，selenium會先進行驗證(在tools folder裡)
- mcp_tool: ai主要會呼叫到的工具，其中search_meeting_rooms會是由AI進行判斷後呼叫
- rag-file:存放一些爬下來的檔案