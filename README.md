# 寵物健康管理 (自用)

多寵物健康日誌 + 飲食計算 + 到期提醒推播 + 每月花費 + 寵物狀態總覽 + 寵物用品比價。個人工具，不做多使用者帳號系統。

首頁是 4 個分頁：我的寵物／每月花費／寵物狀態／用品價格。

## 功能

- **多寵物管理**：新增/編輯/刪除多隻狗貓，各自獨立紀錄，可設定體重目標、晶片號碼；品種欄位有依物種切換的常見品種建議清單(可直接打字)。
- **健康日誌**：體重趨勢圖、體態評分(BCS 1~9)、看診紀錄、疫苗/驅蟲紀錄、檢驗數值、病史時間線（把以上全部依時間排序合併顯示）。
- **飲食計算**：依 RER/MER 公式（見 [diet.py](diet.py)）估算建議每日熱量，可從常見飼料資料庫（`food_presets`，見 [db.py](db.py)）快速帶入熱量密度、依每日餐數分配、對照體重目標算出還差多少。此為通用公式估算起點，非精確醫囑，實際餵食量要搭配體態評分持續調整。
- **到期提醒推播**：疫苗/驅蟲/自訂提醒到期前 N 天推播到手機（Web Push/VAPID，iOS 需先「加入主畫面」才支援）。自訂提醒支援分類（洗牙/美容/趾甲/心絲蟲/除蚤/回診等）與週期重複（例如每 30 天自動產生下一筆），有獨立的推播歷史紀錄頁。
- **每月花費**：獨立的花費記錄（分類/金額/日期/可選歸屬寵物），月份切換檢視、分類統計、近 6 個月趨勢圖。
- **寵物狀態總覽**：一頁看到所有寵物的最新體重/BCS，卡片右上角小徽章顯示待處理提醒數量。
- **寵物用品比價**：追蹤零食/飼料/保健品/用品在 PChome 24h 的歷史價格走勢（見下方「用品比價現況」）。

## 用品比價現況

跟 [luxury-tracker](../luxury-tracker/) 專案共用同一套「每平台獨立 scraper」架構（[scrapers/](scrapers/)）。目前只有 **PChome 24h**（`ecshweb.pchome.com.tw/search/v3.3/all/results`）驗證過能穩定回傳乾淨JSON；momo API 直接403、Yahoo奇摩購物是前端SPA（初始HTML沒有資料），都先不支援，之後有需要再評估無頭瀏覽器。`/api/platforms` 會回傳目前哪些平台可用。

## 架構

- Flask + SQLite（單檔案 `pet_care.db`），無前端框架，純 HTML/CSS/JS，前端用分頁籤（總覽/健康/飲食/提醒）組織單一寵物的各項紀錄。
- **不用常駐背景執行緒**：Render 免費方案的 web 服務閒置會休眠，常駐執行緒不可靠。到期提醒與商品比價抓取都改成受 token 保護的內部端點（`/api/internal/check-reminders`、`/api/internal/run-product-scrape`），由 GitHub Actions cron（見 [.github/workflows/cron.yml](.github/workflows/cron.yml)）分別每天/每12小時呼叫觸發。
- Render 免費方案沒有掛 Disk，**每次重新部署 SQLite 會重置**。這是成本考量下的取捨；之後如果要長期保留資料，可以加一顆 Render Disk 並設定 `DB_PATH` 環境變數指過去。

## 本機開發

```bash
pip install -r requirements-dev.txt
python app.py        # http://localhost:5001
pytest                # 跑 diet.py / reminders.py 的單元測試
```

## 部署 (Render 免費方案 + GitHub Actions)

1. 本機 git repo 已經 init + commit 好了（分支 `main`）。到 GitHub 新增一個空的 repo（不要勾選自動產生 README/.gitignore，不然會跟本機的檔案衝突），然後在這個資料夾執行：
   ```bash
   git remote add origin https://github.com/<你的帳號>/<repo名稱>.git
   git push -u origin main
   ```
2. Render 新增 Web Service，選這個 repo，套用 `render.yaml`（`plan: free`）。
3. Render 後台手動設定環境變數 `INTERNAL_TOKEN`（自己生一組隨機字串，例如 `openssl rand -hex 16`）。
4. GitHub repo → Settings → Secrets and variables → Actions，新增：
   - `PET_CARE_URL`：部署後的網址（例如 `https://pet-care-xxxx.onrender.com`，不要結尾斜線）
   - `PET_CARE_INTERNAL_TOKEN`：跟 Render 上設定的 `INTERNAL_TOKEN` 同一組
5. 到 GitHub Actions 頁面手動 `Run workflow` 一次，會同時觸發 `check-reminders` 和 `run-product-scrape` 兩個 job，確認都能成功打到網站（第一次因為免費方案冷啟動可能較慢）。

## 推播訂閱

VAPID 金鑰第一次啟動時自動產生並存到 `vapid_private_key.pem`（不用手動申請），**這個檔案不能被刪除或重新產生**，不然使用者手機上原本的推播訂閱會全部失效。免費方案沒有 Disk 的情況下，每次重新部署都會產生新的金鑰，使用者需要重新按一次「開啟提醒推播」。
