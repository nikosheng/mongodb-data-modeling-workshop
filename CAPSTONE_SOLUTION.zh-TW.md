# 期末綜合練習解答：推薦好友計畫

這是 `notebook/kfc_loyalty_schema_workshop.zh-TW.ipynb`（英文版請見
`kfc_loyalty_schema_workshop.ipynb`）Part 5 期末綜合練習的完整書面解答。
請先在 notebook 中自己試著做過一遍，再閱讀這份解答。

## 功能描述

現有顧客分享一組推薦碼。當新顧客使用該推薦碼註冊、並完成第一筆訂單後，
推薦人與被推薦人**兩者**都會獲得點數獎勵。

## 1. 推薦關係應該放在哪裡？

**顧客文件上新增一個欄位 + 新增一個 `referrals` 集合，兩者都要** ——
這其實又是一次 Part 1 內嵌 vs. 參照的推理過程：

- **`customers.referralCode`**（新欄位）：一組簡短、唯一、有建立索引的
  字串，供每位顧客分享（例如 `"JORDAN2K4"`）。這跟顧客是 1:1 關係、
  永遠不會變動、而且總是跟著個人資料一起被讀取——明顯該**內嵌**。

- **`referrals` 集合**（新集合）：每一組「推薦人 → 被推薦人」關係對應
  一份文件。單一顧客可能在**數年間**推薦**許多**人——這正是我們在
  Part 4.1 的 `point_transactions` 已經看過的、典型的 1:多、無界成長
  形狀。如果把推薦紀錄陣列內嵌進推薦人的顧客文件裡，幾乎馬上就會
  重現**無界陣列反模式**（一組熱門的推薦碼可能會產生數百筆推薦紀錄）。
  所以結論是：用**參照**，放進它自己獨立的集合，不要內嵌。

```json
// referrals 集合
{
  "_id": ObjectId("..."),
  "referralCode": "JORDAN2K4",
  "referrerId": ObjectId("..."),           // 分享推薦碼的顧客
  "refereeId": ObjectId("..."),            // 使用該推薦碼註冊的顧客
  "referrerRef": { "name": "Jordan Lee", "tier": "Gold" },   // 延伸參照
  "refereeRef": { "name": "Alex Kim" },                      // 延伸參照
  "status": "completed",                   // 在被推薦人完成第一筆訂單之前為 "pending"
  "referrerBonusPoints": 100,
  "refereeBonusPoints": 50,
  "createdAt": ISODate("2024-03-01T00:00:00Z"),
  "completedAt": ISODate("2024-03-04T18:22:00Z")
}
```

```json
// customers 集合（節錄）— 新增欄位以粗體標示概念
{
  "_id": ObjectId("..."),
  "name": "Jordan Lee",
  "tier": "Gold",
  "referralCode": "JORDAN2K4",
  "loyaltyStats": {
    "lifetimePoints": 4200,
    "currentBalance": 1850,
    "totalOrders": 37,
    "totalReferrals": 12,
    "referralBonusPoints": 1200,
    "lastComputedAt": ISODate("...")
  }
}
```

## 2. 套用了哪些模式？為什麼？

| 模式 | 套用位置 | 原因 |
|---|---|---|
| **參照（Referencing）** | `referrals` 集合，透過 `referrerId`／`refereeId` 參照 | 每位推薦人對應的是 1:多、無界成長的關係——跟 `point_transactions`（Part 4.1）的推理完全一樣。若內嵌，最終會重現無界陣列反模式。 |
| **延伸參照（Extended Reference）** | `referrals.referrerRef` / `referrals.refereeRef`（姓名、等級快照） | 後台「推薦活動」儀表板需要列出推薦人／被推薦人的姓名，且不想每一列都做一次 `$lookup`——正是 Part 2 的問題，用同樣的方式解決。 |
| **計算模式（Computed）** | `customers.loyaltyStats.totalReferrals` 與 `referralBonusPoints` | 顧客個人檔案畫面每次載入都需要「已推薦人數」與「推薦賺到的點數」（就跟 Part 4.2 的 `lifetimePoints` 一樣）——用預先計算取代每次都即時聚合 `referrals`。 |
| **繼承（多型）模式** *（若計畫持續演進）* | 未來若新增 `referral_campaigns` 集合，而行銷推出多種獎勵結構不同的推薦活動（固定獎勵 vs. 百分比 vs. 免費品項） | 跟 Part 4.5 的 `rewards.type` 是同一種「結構分歧」問題——一個集合、一個 `type` 判別欄位、一個該類型專屬的巢狀物件。 |
| **屬性模式（Attribute）** *（若有需要）* | `referral_campaigns` 上的活動資格規則（例如「僅限德州的新顧客」、「僅限上市月份」） | 跟 Part 4.3 的 `rewards.eligibility[]` 是同一種稀疏／可選條件問題——一個通用的 `(k, v)` 陣列 + 一個索引，就能涵蓋現有及未來所有條件。 |

請注意這裡**不需要離群值模式**：因為我們從一開始就已經把 `referrals`
放在它自己獨立的集合裡做參照（沒有犯下「先內嵌再說」的錯誤），所以
並不存在「一般情況 vs. 離群值情況」這種文件結構問題需要解決——
Part 4.1 學到的教訓，這裡已經提前主動套用了。

## 3. 如何回答「顧客 X 成功推薦了多少人？透過推薦功能賺了多少點數獎勵？」

**不要每次請求都去聚合 `referrals`。** 完全比照 Part 4.2 的計算模式：
在顧客文件上維護計數器欄位，在每次推薦完成的當下以增量方式更新。

```python
def complete_referral(db, referral_id):
    """
    當被推薦人完成第一筆訂單時呼叫。將該筆推薦標記為完成，並在同一個
    邏輯操作中，增量更新「兩位」顧客預先計算好的統計資料（正式環境中
    應該用多文件交易把這些寫入包起來以確保原子性，跟 Part 4.2 提到的
    注意事項相同）。
    """
    referral = db.referrals.find_one({"_id": referral_id})

    db.referrals.update_one(
        {"_id": referral_id},
        {"$set": {"status": "completed", "completedAt": datetime.now(timezone.utc)}},
    )

    # 推薦人獲得一次成功推薦的紀錄 + 對應的獎勵點數
    db.customers.update_one(
        {"_id": referral["referrerId"]},
        {"$inc": {
            "loyaltyStats.totalReferrals": 1,
            "loyaltyStats.referralBonusPoints": referral["referrerBonusPoints"],
            "loyaltyStats.lifetimePoints": referral["referrerBonusPoints"],
            "loyaltyStats.currentBalance": referral["referrerBonusPoints"],
        }},
    )

    # 被推薦人也拿到自己的註冊獎勵
    db.customers.update_one(
        {"_id": referral["refereeId"]},
        {"$inc": {
            "loyaltyStats.lifetimePoints": referral["refereeBonusPoints"],
            "loyaltyStats.currentBalance": referral["refereeBonusPoints"],
        }},
    )
```

現在，個人檔案畫面上「你已經推薦了 12 位朋友，賺到 1,200 點獎勵！」
這個橫幅，只需要一次有索引的文件查詢：

```python
db.customers.find_one({"_id": customer_id}, {"loyaltyStats": 1})
```

——不論這位顧客推薦了 2 個人還是 2,000 個人，都是 O(1)。

至於**後台報表／對帳**用途（不是熱門路徑，可以容忍較高延遲——跟
Part 4.2 討論的取捨相同），你仍然可以定期用即時聚合 `referrals` 的方式
來驗證計算出來的計數器是否正確：

```python
db.referrals.aggregate([
    {"$match": {"referrerId": customer_id, "status": "completed"}},
    {"$group": {
        "_id": "$referrerId",
        "totalReferrals": {"$sum": 1},
        "referralBonusPoints": {"$sum": "$referrerBonusPoints"},
    }},
])
```

## 新增／變更的索引

```python
db.customers.create_index("referralCode", unique=True)
db.referrals.create_index("referrerId")
db.referrals.create_index("refereeId", unique=True)  # 一位被推薦人只能被推薦一次
db.referrals.create_index([("status", 1), ("createdAt", -1)])  # 供後台「待完成推薦」畫面使用
```
