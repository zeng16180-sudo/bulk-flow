# 散裝貨流觀察 · GitHub 每日更新套件

## 啟用 GitHub Pages

1. 解壓縮。把解壓縮後的檔案按原路徑上傳到既有 GitHub 專案的**根目錄**，覆蓋同名檔。這份更新包只包含此次需要新增或覆蓋的檔案，其餘網站資料和 `requirements.txt` 保留原位。GitHub 的 Code 頁應可看到 `.github/workflows/bulk-flow-daily.yml`、`scripts/equity_market.py` 與 `site/equity-market-data.js`。
2. 進入 **Settings → Pages → Build and deployment**，將 **Source** 選成 **GitHub Actions**。
3. 進入 **Actions → Bulk Flow Daily Update → Run workflow**，選預設分支。第一次保留 `Publish the verified update to GitHub Pages` 未勾選，執行完整抓取與驗證。查看該次執行的 **Summary**，確認各來源的抓取結果。
4. 手動再執行一次，勾選發布選項。等 **deploy** 工作完成，再開 GitHub Pages 查看「台灣船公司 → 股價與估值」和「資料與來源」。預設分支每天台灣時間 **08:17** 檢查原有市場資料，**20:17** 檢查航商盤後資料。GitHub 可能延後開始執行。

正式執行會把驗證通過的資料寫回 `site/`，並從同一次執行部署。直接寫回需要預設分支允許 GitHub Actions 的專案權杖提交。若專案已設定另一個發布流程，請在 Actions 停用舊的 Pages 發布工作，避免交替發布舊版。在長時間無活動的公開專案，GitHub 可能停用排程，屆時可在 Actions 重新啟用。

如果拖曳上傳漏掉 `.github`，用 **Code → Add file → Create new file**，名稱填 `.github/workflows/bulk-flow-daily.yml`，內容使用套件同名檔案。

## 資料與比較基期

| 網站資料 | 每天檢查的入口 | 觀察資料頻率 |
|---|---|---|
| BDI、BCI、BPI、BSI | 東方財富產業指標 API，Baltic Exchange 指數公開轉載 | 交易日 |
| 美國玉米、黃豆、小麥船運出口檢驗 | USDA AgTransport FGIS，限定 SHIP | 週 |
| 巴西玉米、黃豆、小麥及鐵礦砂海運出口 | MDIC Comex Stat，HS 1005／1201／1001／2601，海運代碼 01 | 月 |
| 中國黃豆與鐵礦砂進口 | 中國商務部 FDI 海關月報轉載。隨附快訊補值標示轉載來源，官方月報上線後自動覆核。歷史黃豆基線保留 UN Comtrade | 月 |
| 中國生鐵與粗鋼 | 中國國家統計局規模以上工業增加值報告 | 月 |
| Port Hedland | Pilbara Ports Cargo Statistics by Destination 官方 PDF 的 LOAD／Iron Ore | 月 |
| Vale | 公司投資人頁的季度產銷報告 | 季 |
| 全球消耗、庫存、進口預測與中國黃豆壓榨 | USDA WASDE 官方 PDF，同版 World／China 供需表 | 月報修訂年度值 |
| 全球散裝船供需、交付與拆船展望 | BIMCO 官方報告索引，搭配可驗證的公開聲明及媒體轉載 | 季度及不定期 |
| 台灣七家航商船隊 | 裕民、慧洋、中航、新興、台航、四維航、正德的官網 | 不定期 |
| 台灣七家航商日行情及估值 | 證交所與櫃買中心的個股收盤行情、日估值報表 | 交易日 |
| 台灣七家航商籌碼 | 證交所與櫃買中心的三大法人買賣超、融資融券餘額 | 交易日 |

同組來源的字卡、折線圖、資料期與 CSV／JSON 由一次更新產生。美國 WoW 對比 7 天前，YoY 對比 364 天前。月度 MoM 與 YoY 比較同口徑月量，缺基期留空。官方已公布的 YoY 沿用原值。

網站的「資料與來源」和 Actions 的 **Summary** 會列出每組結果。來源無新一期時保留資料期。抓取失敗、欄位改變或新版 BIMCO 缺少可驗證數字時，保留上次有效值並標示。BIMCO 交付、拆船和供需各自標報告版次，公開數字未能取得時保留已有可核驗版次。Port Hedland 索引若出現防護頁，會嘗試仍公開可讀的官方 PDF，並從 PDF 內文核對期間。中國海關月報的轉載頁可能晚於快訊。

共用下載程式遇到 503、429 或短暫連線故障時會延遲重試。有 `Retry-After` 時依來源指定的等待時間處理，超出本次等待上限就交由後續排程。若仍無法取得，Summary 會顯示「暫時故障」，連續三個查核日才加上「請留意」。其他來源繼續查核。憑證、欄位或資料驗證錯誤會列出原因，供人工檢查。

## 航商盤後資料

現有版本包含近一年股價與估值，以及近 60 個交易日的籌碼資料。河流圖的倍數帶採各公司近一年有效估值倍數的百分位，並逐日對應收盤價。籌碼頁的「近 5 日」及「近 20 日」以來源最新法人交易日為終點。

盤後工作依證交所交易日表確認可更新日期，以股票代碼及交易日補入缺漏。每次會核對最新一期，以及較早尚缺的交易日。來源尚未更新、回傳日期不符或欄位驗證失敗時，保留有效資料，下一次排程會重試。Actions **Summary → 航商盤後資料查核** 會逐市場列出本次核驗的官方交易日、網站採用交易日和待補項目。手動試跑顯示候選結果，部署成功後才生效。

「資料與來源」分列證交所與櫃買中心的盤後資料，顯示網站採用交易日及本次核驗日。月營收和財報列出本版已核對的資料期間。20:17 排程更新股價、估值、三大法人和融資融券。

## 本機核對

```shell
python -m pip install -r requirements.txt
python scripts/update_data.py --verify-only
python scripts/equity_market.py --verify-only
python scripts/update_data.py --check-only
python scripts/equity_market.py --check-only
```

第一個檢查驗證已有資料與網頁檔案，第二個會實際抓來源並驗證候選資料。執行 `python scripts/update_data.py` 才會在本機寫入 `site/`。這份套件無須設定資料來源金鑰。
