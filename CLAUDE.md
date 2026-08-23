# CLAUDE.md

## 先讀 AGENTS.md

**本專案的工作規則全部在 [`AGENTS.md`](AGENTS.md)，開工前先讀完。**
那裡有：絕對禁止事項（不可憑記憶寫營業時間／座標）、資料來源等級、標準流程、
五類常犯錯、回報規則、環境細節。這份檔案只補 AGENTS.md 沒寫的東西，不重複。

---

## 省 context：這個專案最容易浪費 input 的三件事

### 1. 在 scratchpad 建 `.py` 腳本檔（最大一筆）

只要腳本檔留在磁碟上，之後任何一次變動，系統就會把整份 Python 回噴一次。
**改用一次性 heredoc，不留檔：**

```bash
python - <<'PYEOF'
# ...
PYEOF
```

需要反覆執行的才寫成檔案（如 `check_all.py`），寫了就進 repo，不要放 scratchpad。

### 2. 整段 dump `trip.js` 的 note

單一站點的 `note` 常有 300–600 字。要確認內容時**用 grep 抓需要的欄位**，
不要 `sed -n` 印整個 day block：

```bash
grep -o 't:"[^"]*", *kind:"[a-z]*", *name:"[^"]*"' trip.js
```

`data.js` 有 589 KB、14000 行，**永遠不要整檔讀**——需要哪筆就 grep 哪筆，
或用 `python -c` 讀 `PLACES` 後只印要的欄位。

### 3. 別的 session 同時在改檔

動手前先 `git log --oneline -3` ＋ 確認 `SITE_VERSION`，
不要拿記憶中的版本當現況。

---

## 使用者偏好

- 回覆用繁體中文。
- **只講現況，不講修改歷程**——這條同時適用於站點 note 與對話回覆。
- 所有查到的問題都要講，包含判斷為無害的，由使用者決定。
- 明確標示資訊來源等級：①高德實查 ②官方公眾號／官網 ③攻略推測 ④查不到。
